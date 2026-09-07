#!/usr/bin/env python3
"""Step 8: inventory held-out QC networks and score them only after design freeze."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    read_temperature_panel,
    year_split,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PANEL_ROOT,
    FIRST_PLACEMENTS,
    P0_SECOND,
    RESULTS_ROOT,
    SECOND_PANEL_ROOT,
)
from stream_recoverability.experiments.wrr_revision.score import (  # noqa: E402
    crossing_day,
    recoverer_duration_summary,
    score_network,
)

OUTPUT = RESULTS_ROOT / "step8_confirmation"
FREEZE = RESULTS_ROOT / "DESIGN_FREEZE.json"


def panel_ids(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {path.name for path in root.iterdir() if path.is_dir()}


def inventory() -> pd.DataFrame:
    first = set(pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str))
    second = set()
    if P0_SECOND.exists():
        second = set(pd.read_csv(P0_SECOND, usecols=["network_id"])["network_id"].astype(str))
    qc = panel_ids(FIRST_PANEL_ROOT)
    rows = []
    for network_id in sorted(qc):
        path = FIRST_PANEL_ROOT / network_id / "daily_wide_temperature.csv"
        role = (
            "first_panel_development"
            if network_id in first
            else "second_panel_descriptive"
            if network_id in second
            else "held_out_confirmation_candidate"
        )
        raw = pd.read_csv(path, parse_dates=["date"])
        if raw.empty or raw["date"].isna().all():
            rows.append(
                {
                    "network_id": network_id,
                    "role": role,
                    "n_stations": max(0, int(raw.shape[1]) - 1),
                    "n_days": 0,
                    "start": None,
                    "end": None,
                    "n_train_years": 0,
                    "n_eval_years": 0,
                    "eligible_years": 0,
                }
            )
            continue
        panel = read_temperature_panel(str(path))
        _, train_years, eval_years = year_split(panel.index)
        rows.append(
            {
                "network_id": network_id,
                "role": role,
                "n_stations": int(panel.shape[1]),
                "n_days": int(len(panel)),
                "start": str(panel.index.min().date()),
                "end": str(panel.index.max().date()),
                "n_train_years": len(train_years),
                "n_eval_years": len(eval_years),
                "eligible_years": int(len(train_years) >= 4 and len(eval_years) >= 2),
            }
        )
    extra = panel_ids(SECOND_PANEL_ROOT) - qc
    for network_id in sorted(extra):
        rows.append(
            {
                "network_id": network_id,
                "role": "second_daily_qc_only",
                "n_stations": None,
                "n_days": None,
                "start": None,
                "end": None,
                "n_train_years": None,
                "n_eval_years": None,
                "eligible_years": 0,
            }
        )
    return pd.DataFrame(rows)


def _score(network_id: str) -> pd.DataFrame:
    path = FIRST_PANEL_ROOT / network_id / "daily_wide_temperature.csv"
    panel = read_temperature_panel(str(path))
    return score_network(
        network_id,
        panel,
        placements=pd.DataFrame(),
        include_external=False,
        generate_extra_gaps=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--max-networks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--force-unfrozen", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    roster = inventory()
    roster.to_csv(OUTPUT / "network_inventory.csv", index=False)
    counts = roster.groupby("role").size().to_dict()
    (OUTPUT / "inventory_summary.json").write_text(json.dumps(counts, indent=2))
    print(json.dumps(counts, indent=2))
    if args.inventory_only:
        return
    if not FREEZE.exists() and not args.force_unfrozen:
        raise SystemExit(
            "DESIGN_FREEZE.json is absent. Freeze recoverer, default, rule, and "
            "endpoint on the first panel before confirmation scoring."
        )
    candidates = roster.loc[
        roster["role"].eq("held_out_confirmation_candidate")
        & roster["eligible_years"].eq(1)
    ]["network_id"].tolist()
    if args.max_networks is not None:
        candidates = candidates[: args.max_networks]
    frames = []
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        fmap = {pool.submit(_score, n): n for n in candidates}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                frames.append(fut.result())
                print(f"confirm {network_id}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc)})
                print(f"failed {network_id}: {exc}", flush=True)
    if not frames:
        raise SystemExit("no confirmation scores")
    scores = pd.concat(frames, ignore_index=True)
    scores.to_csv(OUTPUT / "placement_scores.csv", index=False)
    recoverer_duration_summary(scores).to_csv(OUTPUT / "duration_summary.csv", index=False)
    pd.concat(
        [crossing_day(g, recoverer=str(r)) for r, g in scores.groupby("recoverer")],
        ignore_index=True,
    ).to_csv(OUTPUT / "crossing_days.csv", index=False)
    pd.DataFrame(failures).to_csv(OUTPUT / "failures.csv", index=False)
    (OUTPUT / "summary.json").write_text(
        json.dumps(
            {
                "n_networks": int(scores["network_id"].nunique()),
                "n_rows": int(len(scores)),
                "frozen": FREEZE.exists(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
