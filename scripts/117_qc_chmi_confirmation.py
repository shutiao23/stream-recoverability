#!/usr/bin/env python3
"""Download and QC official Czech CHMI historical water temperatures."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.chmi_temperature import (
    candidate_plan,
    download_stations,
    file_inventory,
    station_catalog,
)
from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network
from stream_recoverability.data.gkd_bayern_temperature import merge_provider_rows

OUTPUT = ROOT / "results/development_v11/chmi_temperature"
QC_OUTPUT = ROOT / "results/development_v11/confirmation_daily_qc"
CANDIDATES = ROOT / "results/development_v11/confirmation_candidates.csv"
SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"
SHARED_COLUMNS = [
    "network_id",
    "provider",
    "domain",
    "river_group",
    "n_catalog_stations",
    "site_ids",
    "latitude",
    "longitude",
    "prior_temperature_values_seen",
    "candidate_status",
]


def main() -> None:
    inventory = file_inventory()
    catalog = station_catalog()
    candidates, station_files = candidate_plan(catalog, inventory)
    frames, density = download_stations(station_files, OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(OUTPUT / "official_file_inventory.csv", index=False)
    catalog.to_csv(OUTPUT / "official_station_catalog.csv", index=False)
    candidates.to_csv(OUTPUT / "candidate_networks.csv", index=False)
    density.to_csv(OUTPUT / "station_density_summary.csv", index=False)

    qc_rows = []
    for candidate in candidates.to_dict("records"):
        site_ids = str(candidate["site_ids"]).split("|")
        raw = pd.concat([frames[site_id] for site_id in site_ids], ignore_index=True)
        result = qc_candidate_network(candidate, raw, QC_OUTPUT)
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
    local_summary.to_csv(OUTPUT / "network_qc_summary.csv", index=False)
    shared = candidates[SHARED_COLUMNS].copy()
    shared["candidate_status"] = "metadata_candidate_daily_qc_completed"
    merged_candidates = merge_provider_rows(CANDIDATES, shared)
    merged_summary = merge_provider_rows(SUMMARY, local_summary)
    print(f"official_files={len(inventory)}")
    print(f"official_temperature_stations={inventory['site_id'].nunique()}")
    print(f"candidate_networks={len(candidates)}")
    print(f"candidate_stations={len(station_files)}")
    print(f"downloaded_station_years={int(density['n_source_files'].sum())}")
    print(f"daily_rows={int(density['n_daily_rows'].sum())}")
    print(f"stations_with_8_dense_years={int(density['years_with_300_days'].ge(8).sum())}")
    print(f"qualified_networks={int(local_summary['complete_enough'].sum())}")
    print(f"merged_candidates={len(merged_candidates)}")
    print(f"merged_summary={len(merged_summary)}")


if __name__ == "__main__":
    main()
