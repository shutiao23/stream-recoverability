#!/usr/bin/env python3
"""Inspect and materialize Austria eHYD's official derived WT series."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.ehyd_temperature import (
    PACKAGE_URL,
    STATION_URL,
    exact_river_candidates,
    get_bytes,
    monthly_network,
    surface_temperature_stations,
)


CATALOG = ROOT / "results/framework/public_catalog"
DEVELOPMENT = ROOT / "results/development_v11"
CANDIDATES = DEVELOPMENT / "confirmation_candidates.csv"
OUTPUT = DEVELOPMENT / "confirmation_daily_qc"
SUMMARY = DEVELOPMENT / "confirmation_qc_summary.csv"


def main() -> None:
    feature_document = json.loads(get_bytes(STATION_URL).decode("utf-8"))
    package = get_bytes(PACKAGE_URL)
    stations = surface_temperature_stations(feature_document, package)
    candidates = exact_river_candidates(stations)
    CATALOG.mkdir(parents=True, exist_ok=True)
    stations.to_csv(CATALOG / "ehyd_surface_temperature_stations.csv", index=False)
    candidates.to_csv(
        CATALOG / "ehyd_temperature_network_candidates.csv", index=False
    )

    existing = pd.read_csv(CANDIDATES, dtype={"site_ids": str})
    existing = existing.loc[~existing["provider"].eq("ehyd")]
    candidate_columns = list(existing.columns)
    combined = pd.concat(
        [existing, candidates.reindex(columns=candidate_columns)], ignore_index=True
    ).sort_values(["domain", "network_id"])
    combined.to_csv(CANDIDATES, index=False)

    for candidate in candidates.to_dict("records"):
        network_id = str(candidate["network_id"])
        station_roster = tuple(str(candidate["site_ids"]).split("|"))
        monthly = monthly_network(package, stations, station_roster)
        monthly_wide = monthly.pivot(
            index="date", columns="site_id", values="temperature_c"
        ).sort_index()
        directory = OUTPUT / "networks" / network_id
        directory.mkdir(parents=True, exist_ok=True)
        monthly_wide.to_csv(directory / "monthly_mean_temperature.csv")
        pd.DataFrame(columns=["date"]).to_csv(
            directory / "daily_wide_temperature.csv", index=False
        )
        station_qc = (
            monthly.groupby("site_id", as_index=False)
            .agg(
                n_months=("temperature_c", "count"),
                first_month=("date", "min"),
                last_month=("date", "max"),
            )
            .assign(
                network_id=network_id,
                provider="ehyd",
                temporal_resolution="monthly_mean",
                qualified_years=0,
                verdict="rejected_monthly_resolution",
                eligible_for_network=False,
            )
        )
        station_qc.to_csv(directory / "network_qc.csv", index=False)
        network_summary = {
            "network_id": network_id,
            "provider": "ehyd",
            "river_group": str(candidate["river_group"]),
            "n_requested_stations": len(station_roster),
            "n_stations_with_values": int(monthly["site_id"].nunique()),
            "n_eligible_stations": 0,
            "n_daily_rows": 0,
            "n_concurrent_days": 0,
            "overlap_start": None,
            "overlap_end": None,
            "overlap_years": 0.0,
            "complete_enough": False,
            "qc_status": "source_qc_failed_monthly_only",
        }
        pd.DataFrame([network_summary]).to_csv(
            directory / "network_qc_summary.csv", index=False
        )

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

    audit = {
        "provider": "Austria eHYD",
        "official_general_document": (
            "https://ehyd.gv.at/assets/eHYD/pdf/eHYD_Allgemein.pdf"
        ),
        "official_station_data_document": (
            "https://ehyd.gv.at/assets/eHYD/pdf/Messstellen_und_Daten.pdf"
        ),
        "station_endpoint": STATION_URL,
        "official_surface_water_package": PACKAGE_URL,
        "n_surface_water_temperature_stations": len(stations),
        "n_exact_river_metadata_candidates": len(candidates),
        "n_monthly_files_read": int(candidates["n_catalog_stations"].sum()),
        "water_temperature_file_kind": "WT-Monatsmittel",
        "daily_water_temperature_file_offered": False,
        "daily_confirmation_networks_added": 0,
        "reason": "official derived surface-water temperature is monthly, not daily",
        "pegelonline_used": False,
        "pegelonline_reason": "31-day records cannot meet the eight-year criterion",
    }
    (DEVELOPMENT / "ehyd_source_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
