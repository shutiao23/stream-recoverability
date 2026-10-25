#!/usr/bin/env python3
"""TR2-M3/M4: the second preregistration (sealed endpoints N1-N4 on new USGS stations).

Writes the machine-readable preregistration. The first preregistration and its
four primary endpoints are not changed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import wrr_tr_common as T

OUT = T.OUT / "e2_prereg"
DOCUMENT = T.ROOT / "docs/reviews/wrr_target_recovery_20261022/PREREGISTRATION_2_ZH.md"

ENDPOINTS = {
    "N1_expected_risk": {
        "role": "primary", "score": "R7b (direct failure probability of the calibrated D2* median)",
        "rule": "admit cases in increasing score order while k * mean admitted score <= alpha, within each population over all sealed cases; no sealed label used",
        "populations": ["deploy (own real calendars)", "mech (controlled gaps)"],
        "success": "realised risk <= 0.07 in both populations and admitted share > 0; group-bootstrap 95% interval reported",
    },
    "N2_hardest_bin_coverage": {
        "role": "secondary", "stratum": "decision-time climatological peak window hidden > 75% (bin4), both populations and all layers pooled",
        "success": "coverage of the calibrated 90% interval >= 0.85",
    },
    "N3_P1_bias_reduction": {
        "role": "secondary", "stratum": "mech, air_ridge layer, true peak window at least half hidden",
        "quantity": "1 - |mean signed error of D2*| / |mean signed error of P0|", "success": ">= 0.50; both biases reported",
    },
    "N4_ranking_gain": {
        "role": "descriptive, no threshold", "quantity": "retention of R7b (delivering D2*) minus the best current-practice rule (R1-R3, delivering P0 or recorded days) at 5% realised risk, thresholds chosen on sealed labels",
        "expectation": "positive in mech, about zero in deploy",
    },
}

SECONDARY = [
    "R7a with k_R7a, and both scores with k = 1",
    "deploy risk and retention by high and low missingness stratum",
    "worst HUC2 region with >= 200 cases and worst independence group with >= 20 admitted cases",
    "sensitivity without the 13 targets sharing a HUC8 with earlier records; rule applied within each HUC2 region",
    "recovery law v2 and v2p predicted plug-in failure rate against the observed rate",
    "estimator table (P0, recorded days, Air2stream-3, P3, P3raw, D2*) and every published rule's retention, risk and failure rate among rejected years",
    "local calibration need: k re-estimated on m = 2, 4, 8, 16 labelled local groups, applied to the rest, 500 repeats; smallest m with >= 80% of repeats at <= 7%",
]


def main() -> int:
    target = OUT / "prereg2.json"
    settings = T.settings()
    meta = json.loads((OUT / "candidate_bundle/bundle.json").read_text())
    prereg = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "document": str(DOCUMENT.relative_to(T.ROOT)),
        "first_preregistration_unchanged": True, "primary_target": "h30", "tolerance_c": settings["tolerance_c"],
        "test_region": "new USGS stations retained by the earlier metadata intake; eligibility, networks, groups and strata from approved-date availability only",
        "gate_2": json.loads((T.OUT / "e10_sealed_usgs/availability_summary.json").read_text())["gate_2"],
        "rule": {"alpha": meta["expected_risk"]["alpha"], "primary_score": "R7b", "factor_k": meta["expected_risk"]["factor_k"]},
        "endpoints": ENDPOINTS, "secondary_and_descriptive": SECONDARY,
        "inference": {"bootstrap": f"{settings['bootstrap_draws']} draws over independence groups", "multiplicity": "none; N1-N3 are point-estimate criteria judged separately"},
        "paper": {"N1 met": "paper/wrr_tr/transfer_versions/transfer_pass.tex", "N1 not met": "paper/wrr_tr/transfer_versions/transfer_fail.tex"},
    }
    T.write_json(target, prereg)
    print(json.dumps({key: prereg[key] for key in ("created_utc", "gate_2", "rule")}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
