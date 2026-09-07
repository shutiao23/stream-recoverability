#!/usr/bin/env python3
"""Score confirmation networks missing from the first Step-8 pass (including 1-station)."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    read_temperature_panel,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PANEL_ROOT,
    RESULTS_ROOT,
)
from stream_recoverability.experiments.wrr_revision.score import (  # noqa: E402
    crossing_day,
    recoverer_duration_summary,
    score_network,
)

OUTPUT = RESULTS_ROOT / "step8_confirmation"


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
    inv = pd.read_csv(OUTPUT / "network_inventory.csv")
    eligible = set(
        inv.loc[
            inv["role"].eq("held_out_confirmation_candidate") & inv["eligible_years"].eq(1),
            "network_id",
        ].astype(str)
    )
    existing = pd.read_csv(OUTPUT / "placement_scores.csv") if (OUTPUT / "placement_scores.csv").exists() else pd.DataFrame()
    have = set(existing["network_id"].astype(str)) if len(existing) else set()
    missing = sorted(eligible - have)
    print(json.dumps({"eligible": len(eligible), "have": len(have), "missing": missing}, indent=2), flush=True)
    frames = [] if existing.empty else [existing]
    failures = []
    if missing:
        with ProcessPoolExecutor(max_workers=min(12, len(missing))) as pool:
            fmap = {pool.submit(_score, n): n for n in missing}
            for fut in as_completed(fmap):
                network_id = fmap[fut]
                try:
                    frame = fut.result()
                    if frame is not None and not frame.empty:
                        frames.append(frame)
                    print(f"confirm-missing {network_id} rows={0 if frame is None else len(frame)}", flush=True)
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
                "n_eligible": len(eligible),
                "n_missing_after": len(eligible - set(scores["network_id"].astype(str))),
                "frozen": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
