#!/usr/bin/env python3
"""Download and QC official ECCC automated water-temperature networks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network
from stream_recoverability.data.eccc_automated_temperature import (
    candidate_networks,
    directory_inventory,
    download_stations,
    read_station_catalog,
    station_file_map,
)
from stream_recoverability.data.gkd_bayern_temperature import merge_provider_rows

DEFAULT_OUTPUT = ROOT / "results/development_v11/eccc_automated_temperature"
DEFAULT_QC_OUTPUT = ROOT / "results/development_v11/confirmation_daily_qc"
DEFAULT_CANDIDATES = ROOT / "results/development_v11/confirmation_candidates.csv"
DEFAULT_SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qc-output", type=Path, default=DEFAULT_QC_OUTPUT)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = arguments()
    inventory = directory_inventory()
    files = station_file_map(inventory)
    stations = read_station_catalog(inventory)
    candidates = candidate_networks(stations, files)
    selected_ids = sorted(
        {
            item
            for value in candidates["site_ids"]
            for item in str(value).split("|")
        }
    )
    frames = download_stations(
        files, selected_ids, args.output, workers=args.workers
    )
    args.output.mkdir(parents=True, exist_ok=True)
    stations.to_csv(args.output / "official_station_catalog.csv", index=False)
    candidates.to_csv(args.output / "candidate_networks.csv", index=False)
    pd.DataFrame(
        [
            {
                "site_id": site_id,
                "n_source_files": len(files[site_id]),
                "n_daily_rows": len(frames[site_id]),
                "start": frames[site_id]["date"].min(),
                "end": frames[site_id]["date"].max(),
            }
            for site_id in selected_ids
        ]
    ).to_csv(args.output / "selected_station_summary.csv", index=False)

    qc_rows = []
    for candidate in candidates.to_dict("records"):
        site_ids = str(candidate["site_ids"]).split("|")
        raw = pd.concat([frames[site_id] for site_id in site_ids], ignore_index=True)
        result = qc_candidate_network(candidate, raw, args.qc_output)
        qc_rows.append(result)
        print(
            f"{candidate['network_id']}: eligible={result['n_eligible_stations']} "
            f"complete={result['complete_enough']}",
            flush=True,
        )
    qc = pd.DataFrame(qc_rows)
    local_summary = candidates[
        ["network_id", "provider", "domain", "river_group", "n_catalog_stations"]
    ].merge(qc, on=["network_id", "provider", "river_group"], how="left")
    local_summary.to_csv(args.output / "network_qc_summary.csv", index=False)
    candidates["candidate_status"] = "metadata_candidate_daily_qc_completed"
    merged_candidates = merge_provider_rows(args.candidates, candidates)
    merged_summary = merge_provider_rows(args.summary, local_summary)
    print(f"official_catalog_stations={len(stations)}")
    print(f"stations_with_files={len(files)}")
    print(f"candidate_networks={len(candidates)}")
    print(f"selected_stations={len(selected_ids)}")
    print(f"qualified_networks={int(local_summary['complete_enough'].sum())}")
    print(f"merged_candidates={len(merged_candidates)}")
    print(f"merged_summary={len(merged_summary)}")


if __name__ == "__main__":
    main()
