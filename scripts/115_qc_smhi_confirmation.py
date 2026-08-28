#!/usr/bin/env python3
"""Download G-quality SMHI stream temperatures and run confirmation QC."""

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
from stream_recoverability.data.smhi_water_temperature import (
    candidate_networks,
    download_stations,
    station_catalog,
)

OUTPUT = ROOT / "results/development_v11/smhi_water_temperature"
QC_OUTPUT = ROOT / "results/development_v11/confirmation_daily_qc"
CANDIDATES = ROOT / "results/development_v11/confirmation_candidates.csv"
SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"


def main() -> None:
    catalog = station_catalog()
    frames, quality = download_stations(catalog, OUTPUT)
    candidates = candidate_networks(catalog, quality)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(OUTPUT / "official_station_catalog.csv", index=False)
    quality.to_csv(OUTPUT / "station_quality_summary.csv", index=False)
    candidates.to_csv(OUTPUT / "candidate_networks.csv", index=False)

    qc_rows = []
    for candidate in candidates.to_dict("records"):
        site_ids = str(candidate["site_ids"]).split("|")
        raw = pd.concat([frames[site_id] for site_id in site_ids], ignore_index=True)
        result = qc_candidate_network(candidate, raw, QC_OUTPUT)
        qc_rows.append(result)
    local_summary = pd.DataFrame(qc_rows)
    local_summary.to_csv(OUTPUT / "network_qc_summary.csv", index=False)
    if len(candidates):
        candidates["candidate_status"] = "metadata_candidate_daily_qc_completed"
        merge_provider_rows(CANDIDATES, candidates)
        merge_provider_rows(SUMMARY, local_summary)
    print(f"official_stations={len(catalog)}")
    print(f"g_days={int(quality['n_g_days'].sum())}")
    print(f"y_days={int(quality['n_y_days'].sum())}")
    print(f"o_days={int(quality['n_o_days'].sum())}")
    print(f"blank_quality_days={int(quality['n_blank_quality_days'].sum())}")
    print(f"stations_with_g={int(quality['n_g_days'].gt(0).sum())}")
    print(f"candidate_networks={len(candidates)}")
    print(f"qualified_networks={int(local_summary.get('complete_enough', pd.Series(dtype=bool)).sum())}")


if __name__ == "__main__":
    main()
