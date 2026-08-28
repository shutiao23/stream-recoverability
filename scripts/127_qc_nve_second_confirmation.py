#!/usr/bin/env python3
"""Acquire NVE daily water temperature and QC new Norwegian networks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network
from stream_recoverability.data.nve_water_temperature import (
    candidate_networks,
    discover_public_hydapi_key,
    observations,
    series_catalog,
)

OUTPUT = ROOT / "results/development_v11/second_confirmation/nve"
DAILY_QC = ROOT / "results/development_v11/second_confirmation/daily_qc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-networks", type=int, default=15)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    key = discover_public_hydapi_key()
    catalog = series_catalog(key)
    candidates = candidate_networks(catalog).head(args.max_networks).copy()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(OUTPUT / "series_catalog.csv", index=False)
    candidates.to_csv(OUTPUT / "candidates.csv", index=False)
    rows = []
    for candidate in candidates.to_dict("records"):
        summary_path = (
            DAILY_QC
            / "networks"
            / str(candidate["network_id"])
            / "network_qc_summary.csv"
        )
        if args.skip_existing and summary_path.is_file():
            rows.append(pd.read_csv(summary_path).iloc[0].to_dict())
            continue
        try:
            raw = observations(
                key,
                str(candidate["site_ids"]).split("|"),
                str(candidate["catalog_common_start"]),
                str(candidate["catalog_common_end"]),
            )
            result = qc_candidate_network(candidate, raw, DAILY_QC)
        except Exception as error:
            result = {
                "network_id": candidate["network_id"],
                "provider": candidate["provider"],
                "river_group": candidate["river_group"],
                "complete_enough": False,
                "qc_status": "source_download_failed",
                "source_error_type": type(error).__name__,
                "source_error": str(error)[:500],
            }
        rows.append(result)
        print(
            f"{candidate['network_id']}: {result['qc_status']}", flush=True
        )
    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT / "network_qc_summary.csv", index=False)
    (OUTPUT / "source_audit.md").write_text(
        "# NVE HydAPI source audit\n\n"
        "The current public-client API key was discovered at runtime from the "
        "official Sildre application bundle and was not persisted. Only measured "
        "river series with daily means were considered. Observation rows require "
        "quality code 2 or 3 and correction code 0. NVE reports the NLOD license "
        "in every API response.\n",
        encoding="utf-8",
    )
    print(summary.groupby("qc_status").size().to_string())


if __name__ == "__main__":
    main()
