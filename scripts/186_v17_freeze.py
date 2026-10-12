#!/usr/bin/env python3
"""Step 9 of the v17 programme: freeze the design and pre-register the test.

Everything is fit on development networks only. The success criterion is
written here, before the reserved networks are opened, and it contains the
precision calculation that the v16 programme never performed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast  # noqa: E402
from stream_recoverability.experiments.v17_fitness.screen import (  # noqa: E402
    Certificate,
    SCREEN_FEATURES,
    SCREENED_ESTIMATORS,
    split_networks,
)
from stream_recoverability.experiments.v17_fitness.stats import resolvable_margin  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NATURAL_SCALE_C,
    NOMINAL_COVERAGE,
    PRIMARY_TOLERANCE_C,
    STEP1_PANEL,
    STEP4_CEILING,
    STEP6_SCREEN,
    STEP7_FRONTIER,
    STEP9_FREEZE,
    TOLERANCES_C,
)

PRIMARY_RETENTION = 0.70
DECLARED_EFFECT_POINTS = 5.0


def main() -> int:
    STEP9_FREEZE.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    n_reserved = int((split["split_role"] == "reserved").sum())

    fit_ids, cal_ids = split_networks(
        cases["network_id"].astype(str).unique(), fraction=0.3, seed=777
    )
    fit_cases = cases.loc[cases["network_id"].astype(str).isin(fit_ids)]
    cal_cases = cases.loc[cases["network_id"].astype(str).isin(cal_ids)]
    model = Certificate(coverage=NOMINAL_COVERAGE).fit(fit_cases, cal_cases, seed=777)
    joblib.dump(model, STEP9_FREEZE / "certificate.joblib")

    # Precision: the between-network SD of the headline contrast, from development.
    development_contrast = operating_point_contrast(
        cases,
        pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet"),
        retention=PRIMARY_RETENTION,
        seed=0,
    )
    n_dev = int(development_contrast["n_clusters"])
    between_sd = float(development_contrast["se"]) * np.sqrt(n_dev)
    margin = resolvable_margin(between_sd, n_reserved)

    criterion = {
        "frozen_on": "2026-09-23",
        "programme": "v17 fitness-for-use certification",
        "population": "river waterbodies with fully observed calendar years; reference never imputed",
        "unit_of_analysis": "station-year with a simulated outage realization",
        "clustering_unit": "river network",
        "primary_endpoint": (
            "share of retained station-years whose completed-year hottest-30 absolute error "
            f"exceeds {PRIMARY_TOLERANCE_C} °C, at matched retention"
        ),
        "natural_scale_c": NATURAL_SCALE_C,
        "tolerance_justification": (
            f"{PRIMARY_TOLERANCE_C} °C is 0.47 of the interannual standard deviation of the endpoint at these "
            "stations, so a year carrying that error can move a warm year into the normal range. "
            "It is not a probe-precision number; probe precision is the wrong scale for a screening decision."
        ),
        "incumbent": "fixed outage-length threshold, the axis used by published guidance and agency completeness standards",
        "primary_claim": {
            "statement": (
                "On reserved networks, at the retention of the matched fixed-length rule, the certificate "
                f"reduces the consequential-error rate by at least {DECLARED_EFFECT_POINTS} percentage points, "
                "with a network-clustered bootstrap interval excluding zero."
            ),
            "retention": PRIMARY_RETENTION,
            "declared_effect_points": DECLARED_EFFECT_POINTS,
        },
        "secondary_claims": {
            "coverage": {
                "statement": f"marginal conformal coverage of the nominal {NOMINAL_COVERAGE:.2f} interval lies in [0.87, 0.93]",
                "conditional_band": [0.85, 0.95],
                "strata": ["donor_regime", "longest_run bucket", "peak_overlap bucket"],
            },
            "mechanism": "peak-window overlap outranks outage length in permutation importance on reserved networks",
            "per_year_use": "misclassification of the 20 °C exceedance among retained years is lower than the matched length rule",
        },
        "precision": {
            "development_contrast_points": float(development_contrast["point"] * 100),
            "development_bootstrap_se_points": float(development_contrast["se"] * 100),
            "n_development_networks": n_dev,
            "between_network_sd_points": float(between_sd * 100),
            "n_reserved_networks": n_reserved,
            "resolvable_margin_points": float(margin * 100),
            "declared_effect_over_resolvable_margin": float(DECLARED_EFFECT_POINTS / (margin * 100)),
            "note": (
                "The reserved panel must resolve the declared effect by a comfortable multiple. "
                "v16 declared a 0.05 °C margin against a resolvable margin several times larger, "
                "so its confirmation could neither accept nor reject."
            ),
        },
        "failure_conditions": {
            "primary_fails": (
                "report that the certificate does not beat fixed-length screening out of sample, keep the "
                "mechanism result (H1) and the calibrated-interval result (H3), and do not claim a screening advantage"
            ),
            "coverage_fails": "report the interval as uncalibrated out of sample and restrict the certificate to ranking only",
            "both_fail": "the paper reduces to the mechanism finding plus the v16 training-mismatch diagnosis",
        },
        "model": {
            "features": list(SCREEN_FEATURES),
            "estimators": list(SCREENED_ESTIMATORS),
            "calibration": "selection-conditional multiplicative split conformal, networks disjoint between fit, calibration and test",
            "n_fit_networks": int(len(fit_ids)),
            "n_calibration_networks": int(len(cal_ids)),
            "tolerances_c": list(TOLERANCES_C),
        },
        "reserved_networks_opened": False,
    }
    (STEP9_FREEZE / "SUCCESS_CRITERION_v17.json").write_text(json.dumps(criterion, indent=2), encoding="utf-8")

    lines = ["# Step 9 — freeze and pre-registration", ""]
    lines.append("The certificate below is fit on development networks only and is the object scored once")
    lines.append("on the reserved networks in Step 10. Nothing downstream may retune it.")
    lines.append("")
    lines.append("## Precision calculation")
    lines.append("")
    lines.append(
        f"Development contrast at {PRIMARY_RETENTION:.0%} retention: "
        f"**{development_contrast['point']*100:.2f} points** "
        f"(bootstrap SE {development_contrast['se']*100:.2f} points over {n_dev} networks). "
        f"Implied between-network SD **{between_sd*100:.2f} points**."
    )
    lines.append("")
    lines.append(
        f"With **{n_reserved}** reserved networks the resolvable margin is "
        f"**{margin*100:.2f} points**, so the declared effect of {DECLARED_EFFECT_POINTS:.0f} points is "
        f"**{DECLARED_EFFECT_POINTS/(margin*100):.1f}×** the resolution. The test can speak in either direction."
    )
    lines.append("")
    lines.append("## Criterion")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(criterion, indent=2))
    lines.append("```")
    (STEP9_FREEZE / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(criterion["precision"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
