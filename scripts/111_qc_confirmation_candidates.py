#!/usr/bin/env python3
"""Download new confirmation candidates and run real daily-temperature QC."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.confirmation_daily_qc import (
    download_foen_station,
    download_hubeau_station,
    download_usgs_network,
    qc_candidate_network,
    site_ids,
)


CANDIDATES = ROOT / "results/development_v11/confirmation_candidates.csv"
OUTPUT = ROOT / "results/development_v11/confirmation_daily_qc"
SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--providers", default="usgs,hubeau,foen")
    parser.add_argument("--networks", help="comma-separated network ids")
    parser.add_argument("--max-networks", type=int)
    parser.add_argument("--candidate-status")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--start", default="2000-01-01")
    parser.add_argument("--end", default="2026-08-26")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    candidates = pd.read_csv(args.candidates, dtype={"site_ids": str})
    providers = {item for item in args.providers.split(",") if item}
    requested_networks = (
        None
        if args.networks is None
        else {item for item in args.networks.split(",") if item}
    )
    selected = candidates.loc[candidates["provider"].isin(providers)].copy()
    if args.candidate_status is not None:
        selected = selected.loc[
            selected["candidate_status"].eq(args.candidate_status)
        ]
    if requested_networks is not None:
        selected = selected.loc[selected["network_id"].isin(requested_networks)]
    if args.max_networks is not None:
        selected = selected.head(args.max_networks)

    results = []
    for row in selected.to_dict("records"):
        existing_summary = (
            args.output / "networks" / str(row["network_id"]) / "network_qc_summary.csv"
        )
        if args.skip_existing and existing_summary.is_file():
            print(f"{row['network_id']}: existing QC retained", flush=True)
            continue
        stations = site_ids(row["site_ids"])
        start = (
            str(row.get("catalog_common_start"))
            if pd.notna(row.get("catalog_common_start"))
            else args.start
        )
        end = (
            str(row.get("catalog_common_end"))
            if pd.notna(row.get("catalog_common_end"))
            else args.end
        )
        try:
            if row["provider"] == "usgs":
                raw = download_usgs_network(stations, start, end)
            elif row["provider"] == "hubeau":
                raw = pd.concat(
                    [
                        download_hubeau_station(station, start, end)
                        for station in stations
                    ],
                    ignore_index=True,
                )
            else:
                raw = pd.concat(
                    [
                        download_foen_station(station, start, end)
                        for station in stations
                    ],
                    ignore_index=True,
                )
            result = qc_candidate_network(row, raw, args.output)
        except Exception as error:  # provider/network failures remain local
            result = {
                "network_id": str(row["network_id"]),
                "provider": str(row["provider"]),
                "river_group": str(row["river_group"]),
                "n_requested_stations": len(stations),
                "n_stations_with_values": 0,
                "n_eligible_stations": 0,
                "n_daily_rows": 0,
                "n_concurrent_days": 0,
                "overlap_start": None,
                "overlap_end": None,
                "overlap_years": 0.0,
                "complete_enough": False,
                "qc_status": "source_download_failed",
                "source_error_type": type(error).__name__,
                "source_error": str(error)[:500],
            }
            directory = args.output / "networks" / str(row["network_id"])
            directory.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([result]).to_csv(
                directory / "network_qc_summary.csv", index=False
            )
        results.append(result)
        print(
            f"{row['network_id']}: values={result['n_stations_with_values']} "
            f"eligible={result['n_eligible_stations']} "
            f"complete={result['complete_enough']}",
            flush=True,
        )

    completed = pd.concat(
        [
            pd.read_csv(path)
            for path in sorted(args.output.glob("networks/*/network_qc_summary.csv"))
        ],
        ignore_index=True,
    )
    summary = candidates[
        ["network_id", "provider", "domain", "river_group", "n_catalog_stations"]
    ].copy()
    summary = summary.merge(completed, on=["network_id", "provider", "river_group"], how="left")
    summary["qc_status"] = summary["qc_status"].fillna("not_selected_this_run")
    summary.loc[
        summary["provider"].eq("foen")
        & summary["qc_status"].eq("not_selected_this_run"),
        "qc_status",
    ] = (
        "not_downloaded_old_foen_values_out_of_scope"
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary, index=False)
    print(
        summary.groupby(["provider", "qc_status"], dropna=False).size().to_string(),
        flush=True,
    )


if __name__ == "__main__":
    main()
