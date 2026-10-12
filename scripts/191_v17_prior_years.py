#!/usr/bin/env python3
"""Sensitivity: estimators fit on strictly prior years.

The main protocol fits leave-one-year-out within the station, which is correct
for offline archive repair — the analyst repairing a 2015 outage in 2026 holds
the rest of the record. An archivist who repairs as the record accrues does
not. This script re-runs the whole screen under that stricter protocol so the
claim does not rest on the more generous one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    frontier_for_score,
    incumbent_operating_points,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402
from stream_recoverability.experiments.v17_fitness.screen import out_of_fold_certificates  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP3_CASES,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP13 = RESULTS_ROOT / "step13_prior_years"
RETENTION = 0.70


def _at_seventy(score: pd.Series, error: pd.Series) -> dict:
    frame = frontier_for_score(score, error)
    row = frame.loc[frame["retention"].eq(RETENTION)].iloc[0]
    return {
        "rate_above_0.5": float(row[f"rate_above_{PRIMARY_TOLERANCE_C}"]),
        "mean_abs_error_c": float(row["mean_abs_error_c"]),
    }


def _panel(cases: pd.DataFrame, certificates: pd.DataFrame, label: str, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    length = pd.to_numeric(cases["longest_run"], errors="coerce") + rng.random(len(cases))
    policy_error = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    incumbent = incumbent_operating_points(cases, certificates)
    johnson = incumbent.loc[incumbent["rule"].str.contains("91")].iloc[0]
    contrast = operating_point_contrast(cases, certificates, retention=RETENTION, seed=seed, draws=1500)
    return {
        "protocol": label,
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_station_years": int(cases.groupby(["network_id", "station_id", "year"]).ngroups),
        "length_rule_at_70": _at_seventy(length, policy_error),
        "certificate_at_70": _at_seventy(
            pd.to_numeric(certificates["certificate_bound"], errors="coerce"),
            pd.to_numeric(certificates["certificate_abs_error"], errors="coerce"),
        ),
        "contrast_points": float(contrast["point"] * 100),
        "ci_points": [float(contrast["low"] * 100), float(contrast["high"] * 100)],
        "johnson91_retention": float(johnson["retention"]),
        "johnson91_rate": float(johnson["rate_above_0.5"]),
        "certificate_at_johnson_retention": float(johnson["certificate_rate_above_0.5_at_equal_retention"]),
        "mean_abs_error_policy_c": float(policy_error.mean()),
        "coverage": float(pd.to_numeric(certificates["covered"], errors="coerce").mean()),
    }


def main() -> int:
    STEP13.mkdir(parents=True, exist_ok=True)
    prior = pd.read_parquet(STEP3_CASES / "cases_prior_years.parquet")
    prior = prior.loc[prior["split_role"].eq("development")].reset_index(drop=True)
    prior = attach_policy_errors(prior)
    prior_cert = out_of_fold_certificates(prior, seed=0)
    prior_cert.to_parquet(STEP13 / "development_certificates.parquet", index=False)

    main_cases = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    main_cert = pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet").reset_index(drop=True)

    results = [
        _panel(main_cases, main_cert, "leave_one_year_out (main)", seed=0),
        _panel(prior, prior_cert, "strictly_prior_years (sensitivity)", seed=0),
    ]
    (STEP13 / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    table = pd.DataFrame(
        [
            {
                "protocol": r["protocol"],
                "cases": r["n_cases"],
                "station_years": r["n_station_years"],
                "policy_mean_abs_error_c": r["mean_abs_error_policy_c"],
                "length_rule_at_70": r["length_rule_at_70"]["rate_above_0.5"],
                "certificate_at_70": r["certificate_at_70"]["rate_above_0.5"],
                "contrast_points": r["contrast_points"],
                "ci_low": r["ci_points"][0],
                "ci_high": r["ci_points"][1],
                "coverage": r["coverage"],
            }
            for r in results
        ]
    )
    table.to_csv(STEP13 / "protocol_comparison.csv", index=False)

    lines = ["# Step 13 — estimators fit on strictly prior years", ""]
    lines.append(
        "The main protocol is leave-one-year-out within the station, which is what offline "
        "archive repair actually permits. This is the stricter alternative: only years before "
        "the outage are available, so at least two prior complete years are required and the "
        "earliest years of every station drop out."
    )
    lines.append("")
    lines.append(table.round(4).to_string(index=False))
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(results, indent=2))
    lines.append("```")
    (STEP13 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
