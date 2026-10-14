#!/usr/bin/env python3
"""P0-06 scaffold: eligibility + case rebuild plan from sanitized USGS panels.

Full case regeneration uses v17 cases.build and is compute-heavy. This script
writes the post-QA roster and a machine-readable rebuild plan without touching
sealed verdict bytes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
ELIG = READY / "amendments" / "p0_02_eligibility_rebuild" / "station_year_eligibility.csv"
OUT = READY / "amendments" / "p0_06_corrected_reanalysis"


def main() -> int:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    if not ELIG.is_file():
        raise SystemExit("run scripts/275_wrr_eligibility_from_sanitized.py first")
    elig = pd.read_csv(ELIG)
    usgs = elig.loc[elig["provider_label"].eq("usgs_confirmation") & elig["eligible_ge4"]].copy()
    nets = (
        usgs.groupby("network_id")
        .agg(n_stations=("station_id", "nunique"), n_station_years=("n_complete_years", "sum"))
        .reset_index()
    )
    nets = nets.loc[nets["n_stations"] >= 2].sort_values("network_id")
    nets.to_csv(OUT / "usgs_sanitized_eligible_networks.csv", index=False)
    usgs.to_csv(OUT / "usgs_sanitized_eligible_stations.csv", index=False)

    plan = {
        "status": "ready_for_case_rebuild",
        "claim_status": "corrected_reanalysis_not_first_confirmation",
        "n_networks_ge2_stations": int(len(nets)),
        "n_stations": int(usgs["station_id"].nunique()),
        "n_complete_station_years": int(usgs["n_complete_years"].sum()),
        "historical_scored_networks": 39,
        "historical_scored_cases": 8973,
        "steps": [
            "Point case builder at sanitized daily panels (amendments/p0_02_sanitized_panels/panels/confirmation_ingest)",
            "Rebuild cases with crossed length×overlap for mechanism cells (P0-05)",
            "Apply Certificate with reconstructability-aware supported()",
            "Score operating_point_contrast with full denominator (frontier.py)",
            "Write amendment verdict; do not overwrite p0_07_sealed_confirmation/verdict.json",
            "Label result corrected reanalysis of an opened panel",
        ],
        "note": "Below historical 39-network seal after QA; new confirmation still required for first-pass claims (P0-07).",
    }
    (OUT / "rebuild_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
