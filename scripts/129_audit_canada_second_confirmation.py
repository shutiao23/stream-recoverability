#!/usr/bin/env python3
"""Audit the only identified multi-station Canadian daily source fail closed."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.ccg_temperature import candidate, download_archive
from stream_recoverability.data.confirmation_daily_qc import qc_candidate_network

SECOND = ROOT / "results/development_v11/second_confirmation"


def main() -> None:
    item = candidate()
    raw = download_archive()
    result = qc_candidate_network(item, raw, SECOND / "daily_qc")
    pd.DataFrame([item]).to_csv(SECOND / "canada_candidate.csv", index=False)
    audit = {
        "provider": "Canadian Coast Guard",
        "official_source": (
            "https://navigation-electronique.canada.ca/topics/"
            "water-levels/central/temperatures-en"
        ),
        "n_stations": int(raw["site_id"].nunique()),
        "n_observed_daily_values": int(len(raw)),
        "first_observation": str(raw["date"].min().date()),
        "last_observation": str(raw["date"].max().date()),
        "provider_quality_statement": "not validated or checked",
        "strict_confirmation_status": result["qc_status"],
        "eligible_stations": int(result["n_eligible_stations"]),
        "reason": "provider does not publish validated/checked observations",
    }
    (SECOND / "canada_source_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
