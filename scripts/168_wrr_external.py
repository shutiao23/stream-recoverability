#!/usr/bin/env python3
"""External-information group only: air ridge vs donor-only vs climatology."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    AIR2STREAM_FORCING,
    FIRST_PLACEMENTS,
    RESULTS_ROOT,
)
from stream_recoverability.experiments.wrr_revision.score import (  # noqa: E402
    load_panel,
    recoverer_duration_summary,
    score_network,
)

OUTPUT = RESULTS_ROOT / "step2_external"
POWER = RESULTS_ROOT / "forcing" / "nasa_power_t2m.parquet"
NAMES = ("doy_climatology", "donor_only_ridge", "air_ridge", "air_flow_ridge", "air2stream")


def _air_for_network(network_id: str) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    air: dict[str, pd.Series] = {}
    discharge: dict[str, pd.Series] = {}
    if POWER.exists():
        frame = pd.read_parquet(POWER)
        frame["date"] = pd.to_datetime(frame["date"])
        sub = frame.loc[frame["network_id"].astype(str).eq(network_id)]
        for station, group in sub.groupby("station_id"):
            air[str(station)] = group.set_index("date")["air_temperature_c"]
    if AIR2STREAM_FORCING.exists():
        frame = pd.read_parquet(AIR2STREAM_FORCING)
        frame["date"] = pd.to_datetime(frame["date"])
        sub = frame.loc[frame["network_id"].astype(str).eq(network_id)]
        for station, group in sub.groupby("station_id"):
            series = group.set_index("date")
            air[str(station)] = series["air_temperature_c"]
            discharge[str(station)] = series["discharge_m3s"]
    return air, discharge


def _score(network_id: str) -> pd.DataFrame:
    panel = load_panel(network_id, "first")
    air, discharge = _air_for_network(network_id)
    if not air:
        return pd.DataFrame()
    scored = score_network(
        network_id,
        panel,
        air_by_station=air,
        discharge_by_station=discharge or None,
        include_external=True,
        generate_extra_gaps=False,
        include_names=NAMES,
    )
    if scored.empty:
        return scored
    return scored.loc[scored["recoverer"].isin(NAMES)].copy()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    scores_path = OUTPUT / "placement_scores.csv"
    if scores_path.exists():
        scores_path.unlink()
    first_ids = sorted(
        pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str).unique()
    )
    power_ids = set()
    if POWER.exists():
        power_ids = set(pd.read_parquet(POWER, columns=["network_id"])["network_id"].astype(str))
    ids = [n for n in first_ids if n in power_ids]
    print(json.dumps({"n_networks_with_power": len(ids)}), flush=True)
    n_ok = 0
    with ProcessPoolExecutor(max_workers=8) as pool:
        fmap = {pool.submit(_score, n): n for n in ids}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                frame = fut.result()
                if frame is not None and not frame.empty:
                    frame.to_csv(
                        scores_path,
                        mode="a",
                        header=not scores_path.exists(),
                        index=False,
                    )
                    n_ok += 1
                print(f"external {network_id} rows={0 if frame is None else len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"failed {network_id}: {exc}", flush=True)
    if not scores_path.exists():
        raise SystemExit("no external scores")
    out = pd.read_csv(scores_path)
    recoverer_duration_summary(out).to_csv(OUTPUT / "duration_summary.csv", index=False)
    (OUTPUT / "summary.json").write_text(
        json.dumps(
            {
                "n_networks": int(out["network_id"].nunique()),
                "n_rows": int(len(out)),
                "recoverers": sorted(out["recoverer"].astype(str).unique().tolist()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
