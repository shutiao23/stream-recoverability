#!/usr/bin/env python3
"""Step 2: fair recovery controls on matched first-panel placements."""

from __future__ import annotations

import argparse
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
    crossing_day,
    load_panel,
    recoverer_duration_summary,
    score_network,
)

OUTPUT = RESULTS_ROOT / "step2_fair_recovery"


def network_ids(max_networks: int | None) -> list[str]:
    frame = pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])
    ids = sorted(frame["network_id"].astype(str).unique())
    if max_networks is not None:
        return ids[: int(max_networks)]
    return ids


def load_forcing() -> tuple[dict[str, dict[str, pd.Series]], dict[str, dict[str, pd.Series]]]:
    air: dict[str, dict[str, pd.Series]] = {}
    discharge: dict[str, dict[str, pd.Series]] = {}
    if not AIR2STREAM_FORCING.exists():
        return air, discharge
    frame = pd.read_parquet(AIR2STREAM_FORCING)
    frame["date"] = pd.to_datetime(frame["date"])
    for (network, station), group in frame.groupby(["network_id", "station_id"]):
        series = group.set_index("date")
        air.setdefault(str(network), {})[str(station)] = series["air_temperature_c"]
        discharge.setdefault(str(network), {})[str(station)] = series["discharge_m3s"]
    return air, discharge


def _score_one(network_id: str) -> pd.DataFrame:
    panel = load_panel(network_id, "first")
    air_all, q_all = load_forcing()
    return score_network(
        network_id,
        panel,
        air_by_station=air_all.get(network_id),
        discharge_by_station=q_all.get(network_id),
        include_external=True,
        generate_extra_gaps=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-networks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--networks", nargs="*", default=None)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ids = args.networks if args.networks else network_ids(args.max_networks)
    frames: list[pd.DataFrame] = []
    failures: list[dict[str, str]] = []
    with ProcessPoolExecutor(max_workers=int(args.workers)) as pool:
        future_map = {pool.submit(_score_one, network_id): network_id for network_id in ids}
        for future in as_completed(future_map):
            network_id = future_map[future]
            try:
                frame = future.result()
                frames.append(frame)
                print(f"scored {network_id} rows={len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc)})
                print(f"failed {network_id}: {exc}", flush=True)
    if not frames:
        raise SystemExit("no networks scored")
    placements = pd.concat(frames, ignore_index=True)
    placements.to_csv(OUTPUT / "placement_scores.csv", index=False)
    summary = recoverer_duration_summary(placements)
    summary.to_csv(OUTPUT / "duration_summary.csv", index=False)
    crossings = []
    for recoverer, group in placements.groupby("recoverer"):
        crossings.append(crossing_day(group, recoverer=str(recoverer)))
    crossing = pd.concat(crossings, ignore_index=True)
    crossing.to_csv(OUTPUT / "crossing_days.csv", index=False)
    pd.DataFrame(failures).to_csv(OUTPUT / "failures.csv", index=False)
    same = placements.loc[placements["information_group"].ne("external")]
    pivot = (
        same.groupby(["gap_length", "recoverer"])["mae_benefit"]
        .mean()
        .unstack("recoverer")
        .sort_index()
    )
    pivot.to_csv(OUTPUT / "same_information_benefit_by_duration.csv")
    manifest = {
        "n_networks": int(placements["network_id"].nunique()),
        "n_stations": int(placements["station_id"].nunique()),
        "n_rows": int(len(placements)),
        "recoverers": sorted(placements["recoverer"].unique().tolist()),
        "n_failures": len(failures),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
