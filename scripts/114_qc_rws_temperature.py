#!/usr/bin/env python3
"""Download Rijkswaterstaat raw temperature and derive daily candidate panels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network
from stream_recoverability.data.rws_temperature import (
    RIVER_NETWORKS,
    candidate_table,
    catalog_document,
    download_station,
    temperature_locations,
)


CATALOG = ROOT / "results/framework/public_catalog"
DEVELOPMENT = ROOT / "results/development_v11"
CANDIDATES = DEVELOPMENT / "confirmation_candidates.csv"
OUTPUT = DEVELOPMENT / "confirmation_daily_qc"
SUMMARY = DEVELOPMENT / "confirmation_qc_summary.csv"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--networks", help="comma-separated network ids")
    parser.add_argument("--max-networks", type=int)
    parser.add_argument("--start-year", type=int, default=2017)
    parser.add_argument("--end-year", type=int, default=2025)
    return parser.parse_args()


def main() -> None:
    args = arguments()
    locations = temperature_locations(catalog_document())
    candidates = candidate_table(locations)
    CATALOG.mkdir(parents=True, exist_ok=True)
    locations.to_csv(CATALOG / "rws_temperature_locations.csv", index=False)
    candidates.to_csv(CATALOG / "rws_temperature_network_candidates.csv", index=False)

    existing = pd.read_csv(CANDIDATES, dtype={"site_ids": str})
    existing = existing.loc[~existing["provider"].eq("rws_waterwebservices")]
    columns = list(existing.columns)
    combined = pd.concat(
        [existing, candidates.reindex(columns=columns)], ignore_index=True
    ).sort_values(["domain", "network_id"])
    combined.to_csv(CANDIDATES, index=False)

    selected = candidates.copy()
    requested = (
        None
        if args.networks is None
        else {value for value in args.networks.split(",") if value}
    )
    if requested is not None:
        selected = selected.loc[selected["network_id"].isin(requested)]
    if args.max_networks is not None:
        selected = selected.head(args.max_networks)
    years = tuple(range(args.start_year, args.end_year))
    for candidate in selected.to_dict("records"):
        frames = [
            download_station(station, years)
            for station in str(candidate["site_ids"]).split("|")
        ]
        raw_daily = pd.concat(frames, ignore_index=True)
        result = qc_candidate_network(candidate, raw_daily, OUTPUT)
        print(
            f"{candidate['network_id']}: values={result['n_stations_with_values']} "
            f"eligible={result['n_eligible_stations']} "
            f"complete={result['complete_enough']}",
            flush=True,
        )

    for candidate in candidates.loc[
        ~candidates["network_id"].isin(RIVER_NETWORKS)
    ].to_dict("records"):
        directory = OUTPUT / "networks" / str(candidate["network_id"])
        result_path = directory / "network_qc_summary.csv"
        if result_path.is_file():
            result = pd.read_csv(result_path)
            result["complete_enough"] = False
            result["qc_status"] = "non_river_domain_excluded"
            result.to_csv(result_path, index=False)
            station_path = directory / "network_qc.csv"
            station_qc = pd.read_csv(station_path)
            station_qc["eligible_for_network"] = False
            station_qc["domain_eligible"] = False
            station_qc.to_csv(station_path, index=False)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=["date"]).to_csv(
                directory / "daily_wide_temperature.csv", index=False
            )
            pd.DataFrame(
                {
                    "site_id": str(candidate["site_ids"]).split("|"),
                    "network_id": str(candidate["network_id"]),
                    "provider": "rws_waterwebservices",
                    "verdict": "non_river_domain_excluded",
                    "eligible_for_network": False,
                    "domain_eligible": False,
                }
            ).to_csv(directory / "network_qc.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "network_id": str(candidate["network_id"]),
                        "provider": "rws_waterwebservices",
                        "river_group": str(candidate["river_group"]),
                        "n_requested_stations": int(
                            candidate["n_catalog_stations"]
                        ),
                        "n_stations_with_values": 0,
                        "n_eligible_stations": 0,
                        "n_daily_rows": 0,
                        "n_concurrent_days": 0,
                        "overlap_start": None,
                        "overlap_end": None,
                        "overlap_years": 0.0,
                        "complete_enough": False,
                        "qc_status": "non_river_domain_excluded",
                    }
                ]
            ).to_csv(result_path, index=False)

    completed = pd.concat(
        [
            pd.read_csv(path)
            for path in sorted(OUTPUT.glob("networks/*/network_qc_summary.csv"))
        ],
        ignore_index=True,
    )
    summary = combined[
        ["network_id", "provider", "domain", "river_group", "n_catalog_stations"]
    ].merge(completed, on=["network_id", "provider", "river_group"], how="left")
    summary["qc_status"] = summary["qc_status"].fillna("not_processed")
    summary.to_csv(SUMMARY, index=False)

    provider_summary = summary.loc[
        summary["provider"].eq("rws_waterwebservices")
    ]
    audit = {
        "provider": "Rijkswaterstaat WaterWebservices",
        "official_documentation": (
            "https://rijkswaterstaatdata.nl/projecten/waterwebservices-overschakeling/"
        ),
        "catalog_operation": "POST OphalenCatalogus",
        "observations_operation": "POST OphalenWaarnemingen",
        "temperature_domain": "T in OW",
        "source_resolution": "raw measurement NVT",
        "derived_resolution": "daily mean",
        "years_requested": list(years),
        "n_candidate_networks": len(candidates),
        "n_river_candidate_networks": len(RIVER_NETWORKS),
        "n_qualified_networks": int(
            provider_summary["complete_enough"].fillna(False).sum()
        ),
        "request_token_persisted": False,
    }
    (DEVELOPMENT / "rws_source_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
