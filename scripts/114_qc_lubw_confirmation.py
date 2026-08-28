#!/usr/bin/env python3
"""Acquire and QC official LUBW daily-temperature river networks."""

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
from stream_recoverability.data.lubw_temperature import (
    candidate_networks,
    session_table,
    station_catalog,
    write_station_tables,
)

OUTPUT = ROOT / "results/development_v11/lubw_temperature"
QC_OUTPUT = ROOT / "results/development_v11/confirmation_daily_qc"
CANDIDATES = ROOT / "results/development_v11/confirmation_candidates.csv"
SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"


def main() -> None:
    daily = session_table()
    catalog = station_catalog(daily)
    candidates = candidate_networks(catalog)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(OUTPUT / "daily_temperature.parquet", index=False)
    catalog.to_csv(OUTPUT / "official_station_catalog.csv", index=False)
    candidates.to_csv(OUTPUT / "candidate_networks.csv", index=False)
    write_station_tables(daily, candidates, OUTPUT)

    qc_rows = []
    for candidate in candidates.to_dict("records"):
        site_ids = str(candidate["site_ids"]).split("|")
        raw = daily.loc[daily["site_id"].isin(site_ids)].copy()
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
    print(f"stations_with_temperature={len(catalog)}")
    print(f"daily_rows={len(daily)}")
    print(f"candidate_networks={len(candidates)}")
    print(f"candidate_stations={int(candidates['n_catalog_stations'].sum())}")
    print(f"qualified_networks={int(local_summary['complete_enough'].sum())}")
    print(f"merged_candidates={len(merged_candidates)}")
    print(f"merged_summary={len(merged_summary)}")


if __name__ == "__main__":
    main()
