#!/usr/bin/env python3
"""Download and QC official Finland SYKE surface temperatures."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network
from stream_recoverability.data.gkd_bayern_temperature import merge_provider_rows
from stream_recoverability.data.syke_surface_temperature import (
    candidate_networks,
    download_stations,
    station_catalog,
)

OUTPUT = ROOT / "results/development_v11/syke_surface_temperature"
QC_OUTPUT = ROOT / "results/development_v11/confirmation_daily_qc"
CANDIDATES = ROOT / "results/development_v11/confirmation_candidates.csv"
SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"


def main() -> None:
    catalog = station_catalog()
    candidates = candidate_networks(catalog)
    selected_ids = sorted(
        {
            item
            for value in candidates["site_ids"]
            for item in str(value).split("|")
        }
    )
    frames, density = download_stations(selected_ids, OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(OUTPUT / "official_station_catalog.csv", index=False)
    density.to_csv(OUTPUT / "station_density_summary.csv", index=False)
    candidates.to_csv(OUTPUT / "candidate_networks.csv", index=False)

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
    candidates["candidate_status"] = "metadata_candidate_daily_qc_completed"
    merged_candidates = merge_provider_rows(CANDIDATES, candidates)
    merged_summary = merge_provider_rows(SUMMARY, local_summary)
    print(f"official_stations={len(catalog)}")
    print(f"candidate_networks={len(candidates)}")
    print(f"candidate_stations={len(selected_ids)}")
    print(f"daily_rows={int(density['n_daily_rows'].sum())}")
    print(f"stations_with_8_dense_years={int(density['years_with_300_days'].ge(8).sum())}")
    print(f"qualified_networks={int(local_summary['complete_enough'].sum())}")
    print(f"merged_candidates={len(merged_candidates)}")
    print(f"merged_summary={len(merged_summary)}")


if __name__ == "__main__":
    main()
