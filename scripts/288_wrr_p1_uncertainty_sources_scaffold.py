#!/usr/bin/env python3
"""P1-01: source-tagged uncertainty table scaffold (SI-ready).

Lists measurement, climate-window, reconstruction, selection, transport, and
missingness-mechanism uncertainties with what is data-supported versus scenario.
Does not invent numerical bounds beyond existing amendments.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "wrr_submission_ready" / "amendments" / "p1_01_uncertainty_sources"

ROWS = [
    {
        "source": "input_measurement",
        "assumption": "Provider daily °C after noData/unit/QC mapping is the true daily water temperature",
        "evidence_status": "partial",
        "artifact": "amendments/p0_02_qc_ledger/; measurement_provenance_dictionary.csv",
        "supported_now": "USGS −999999 mapped; SMHI 80289 quarantined; daily-statistic contract disclosed by provider",
        "scenario_only": "Unverified Hub'Eau/SMHI aggregation error magnitudes",
    },
    {
        "source": "climate_window_location",
        "assumption": "Training-year climatological hottest-30 window is the decision-time support proxy",
        "evidence_status": "supported_as_predictor",
        "artifact": "results/v17_fitness/step5_mechanism/; amendments/position_length_paired/",
        "supported_now": "Hidden-share predicts consequential-error risk on development/reserved",
        "scenario_only": "Paired length×overlap does not establish that position governs length",
    },
    {
        "source": "reconstruction_error",
        "assumption": "Chosen fill yields a finite hottest-30 comparable to complete-year truth",
        "evidence_status": "supported_with_contract",
        "artifact": "V/screen.py supported(); amendments/p0_03_retention/; sanitized reanalyses",
        "supported_now": "After sanitize+contract, admitted cases have finite metrics on rebuilt panels",
        "scenario_only": "True MNAR tails beyond day-level δ offsets",
    },
    {
        "source": "method_selection",
        "assumption": "Certificate choice among library estimators is stable under feature noise",
        "evidence_status": "partial",
        "artifact": "results/v17_fitness/step6_screen/; step9_freeze/certificate.joblib",
        "supported_now": "Frozen model loads under sklearn 1.2.2; reserved retrospective contrast archived",
        "scenario_only": "Selection vs reconstructor contribution decomposition (P1-03)",
    },
    {
        "source": "network_transport",
        "assumption": "Screen calibrated on development transports to new agencies at Δ≤−1 pp",
        "evidence_status": "pending_confirmation",
        "artifact": "P0_07_NEW_CONFIRMATION_SEAL.json; opened seals preserved but audit-failed",
        "supported_now": "None as first confirmation",
        "scenario_only": "Sanitized opened-panel reanalyses (not first confirmation)",
    },
    {
        "source": "missingness_mechanism",
        "assumption": "Designed masks / empirical transplants represent operational outages",
        "evidence_status": "partial",
        "artifact": "amendments/mnar_day_level/; e1 real_gaps; F05 notes",
        "supported_now": "Day-level δ re-peak on reserved subset (exploratory); real-gap seasonality described",
        "scenario_only": "Identification bound for MNAR; full-year/cross-year masks with joint donor failure",
    },
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    frame = pd.DataFrame(ROWS)
    frame.to_csv(OUT / "uncertainty_sources.csv", index=False)
    summary = {
        "purpose": "P1-01 SI table: uncertainty by source",
        "n_rows": len(ROWS),
        "may_enter_abstract_or_conclusions": False,
        "note": "Scaffold binds claims to evidence class; fill quantitative cells only from frozen amendments.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
