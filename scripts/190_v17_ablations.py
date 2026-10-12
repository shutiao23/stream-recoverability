#!/usr/bin/env python3
"""Adversarial ablations of the certificate (round-2 review).

Four questions a hostile referee will ask, each answered by removing something
and re-running the whole out-of-fold pipeline:

1. Is the advantage just the observed-peak margin — that is, is the certificate
   merely noticing when the annual maximum is already pinned by recorded days?
2. Does the donor information earn its place in the screen, as opposed to in
   the reconstruction?
3. Is the machine-learning machinery needed at all, or does a three-variable
   logistic regression get there?
4. Does the conformal guarantee hold *within* networks, or only on average
   across them?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    frontier_for_score,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.screen import (  # noqa: E402
    SCREEN_FEATURES,
    out_of_fold_certificates,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
)

STEP12 = RESULTS_ROOT / "step12_ablations"
RETENTION = 0.70

DONOR_FEATURES = ("n_visible_donors", "donor_corr_mean", "donor_corr_max", "donor_corr_min", "donor_coverage_mean")
PINNED_FEATURES = ("observed_peak_margin", "observed_peak", "has_complete_window")
TIMING_ONLY = (
    "longest_run",
    "total_missing",
    "missing_fraction",
    "n_runs",
    "peak_overlap",
    "warm_observed_fraction",
    "month_sin",
    "month_cos",
)
THREE = ("peak_overlap", "warm_observed_fraction", "longest_run")

VARIANTS = {
    "full": SCREEN_FEATURES,
    "drop_observed_peak_margin": tuple(f for f in SCREEN_FEATURES if f not in PINNED_FEATURES),
    "drop_donor_features": tuple(f for f in SCREEN_FEATURES if f not in DONOR_FEATURES),
    "geometry_and_timing_only": TIMING_ONLY,
    "three_features": THREE,
}


def simple_logit_score(cases: pd.DataFrame, features=THREE, *, seed: int = 0) -> np.ndarray:
    """A three-variable logistic screen: does the machinery earn its keep?"""

    X = cases[list(features)].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = (pd.to_numeric(cases["abserr_policy"], errors="coerce") > PRIMARY_TOLERANCE_C).astype(int)
    groups = cases["network_id"].to_numpy()
    out = np.full(len(y), np.nan)
    for train_idx, test_idx in GroupKFold(n_splits=5).split(X, y, groups):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=seed))
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        out[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
    return out


def per_network_coverage(cases: pd.DataFrame, certificates: pd.DataFrame, *, minimum: int = 40) -> pd.DataFrame:
    frame = cases[["network_id", "provider"]].copy()
    frame["covered"] = pd.to_numeric(certificates["covered"], errors="coerce")
    grouped = frame.groupby(["network_id", "provider"]).agg(n=("covered", "size"), coverage=("covered", "mean"))
    return grouped.loc[grouped["n"] >= minimum].reset_index()


def main() -> int:
    STEP12.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    policy_error = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    length = pd.to_numeric(cases["longest_run"], errors="coerce")
    rng = np.random.default_rng(11)
    length_jittered = pd.Series(length.to_numpy() + rng.random(len(length)), index=cases.index)

    rows = []

    def record(name: str, score: pd.Series, error: pd.Series, kind: str) -> None:
        frame = frontier_for_score(score, error)
        at70 = frame.loc[frame["retention"].eq(RETENTION)].iloc[0]
        rows.append(
            {
                "variant": name,
                "kind": kind,
                "rate_above_0.5_at_70": float(at70["rate_above_0.5"]),
                "mean_abs_error_at_70": float(at70["mean_abs_error_c"]),
            }
        )

    record("outage-length rule (incumbent)", length_jittered, policy_error, "baseline")
    record("three-variable logistic screen", pd.Series(simple_logit_score(cases), index=cases.index), policy_error, "baseline")
    record("peak-overlap rule", pd.to_numeric(cases["peak_overlap"], errors="coerce"), policy_error, "baseline")

    certificates = {}
    for name, features in VARIANTS.items():
        applied = out_of_fold_certificates(cases, seed=0, features=features)
        certificates[name] = applied
        record(name, applied["certificate_bound"], applied["certificate_abs_error"], "certificate")
        record(
            name + " (screen only)",
            applied["certificate_bound"],
            policy_error,
            "certificate_screen_only",
        )

    table = pd.DataFrame(rows)
    baseline = float(table.loc[table["variant"].eq("outage-length rule (incumbent)"), "rate_above_0.5_at_70"].iloc[0])
    table["points_vs_incumbent"] = (table["rate_above_0.5_at_70"] - baseline) * 100
    table.to_csv(STEP12 / "ablations.csv", index=False)

    contrasts = {}
    for name in VARIANTS:
        contrasts[name] = operating_point_contrast(cases, certificates[name], retention=RETENTION, seed=0, draws=1200)

    reserved = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    reserved_cert = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True)
    coverage = per_network_coverage(reserved, reserved_cert)
    coverage.to_csv(STEP12 / "per_network_coverage.csv", index=False)
    dispersion = {
        "n_networks": int(len(coverage)),
        "mean": float(coverage["coverage"].mean()),
        "median": float(coverage["coverage"].median()),
        "q10": float(coverage["coverage"].quantile(0.10)),
        "min": float(coverage["coverage"].min()),
        "share_below_0.80": float((coverage["coverage"] < 0.80).mean()),
        "share_below_0.85": float((coverage["coverage"] < 0.85).mean()),
    }

    summary = {"contrasts_vs_length_rule": contrasts, "per_network_coverage": dispersion}
    (STEP12 / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["# Step 12 — adversarial ablations of the certificate", ""]
    lines.append(f"Development cases, out-of-fold, at {RETENTION:.0%} retention. "
                 "Lower is better; the incumbent is the first row.")
    lines.append("")
    lines.append(table.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Contrast against the outage-length rule, network-clustered")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(contrasts, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Conformal coverage within individual reserved networks")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(dispersion, indent=2))
    lines.append("```")
    (STEP12 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(table.round(4).to_string(index=False))
    print()
    print(json.dumps({k: {"point": round(v["point"] * 100, 2), "ci": [round(v["low"] * 100, 2), round(v["high"] * 100, 2)]} for k, v in contrasts.items()}, indent=2))
    print()
    print(json.dumps(dispersion, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
