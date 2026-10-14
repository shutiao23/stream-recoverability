"""Step 7 — the retention-error frontier against the incumbent screening rules.

The comparison is not a scalar mean. A screening rule buys accuracy among the
station-years it keeps by discarding others, so it must be judged on the whole
exchange rate. The incumbent is a fixed outage-length threshold, which is what
published guidance and agency completeness standards use.

Johnson et al. (2021) give two limits and this module used to mis-state the
second. Their abstract reads "datasets with less than seven weeks of
consecutively missing data enabled estimation of all annual signal parameters
with reasonable accuracy" and "imputation of missing data expanded this range
to approximately 20 weeks"; their closing guideline names "more than
approximately seven consecutive weeks of missing data or 20 weeks of imputed
data". So the filled limit is 140 days, not the 91 days used through v17. The
error made the incumbent look stricter, and therefore better, than the guidance
it stands for.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C, TOLERANCES_C
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap

RETENTION_GRID = tuple(np.round(np.arange(0.30, 1.001, 0.05), 3))
JOHNSON_UNFILLED_DAYS = 49
JOHNSON_FILLED_DAYS = 140


def estimator_disagreement(cases: pd.DataFrame) -> pd.Series:
    """A model-free internal uncertainty proxy: spread across supported estimators."""

    columns = [c for c in cases.columns if c.startswith("metric_") and c != "metric_observed_days"]
    block = cases[columns].apply(pd.to_numeric, errors="coerce")
    return block.max(axis=1) - block.min(axis=1)


def screening_scores(cases: pd.DataFrame, certificates: pd.DataFrame, *, seed: int = 0) -> pd.DataFrame:
    """Every screen, expressed as 'lower means keep first'."""

    rng = np.random.default_rng(int(seed))

    def jitter(values: pd.Series, scale: float) -> pd.Series:
        """Break ties at random.

        A threshold rule on a discrete quantity cannot reach an arbitrary
        retention; within a tied block a practitioner keeps an arbitrary
        subset. Resolving ties deterministically by row order would silently
        hand the incumbent either the best or the worst of each block.
        """

        return pd.to_numeric(values, errors="coerce") + rng.random(len(values)) * float(scale)

    scores = pd.DataFrame(index=cases.index)
    scores["certificate"] = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    scores["length_rule"] = jitter(cases["longest_run"], 1.0)
    scores["missing_fraction_rule"] = jitter(cases["missing_fraction"], 1e-3)
    scores["warm_coverage_rule"] = jitter(-pd.to_numeric(cases["warm_observed_fraction"], errors="coerce"), 1e-3)
    scores["peak_overlap_rule"] = jitter(cases["peak_overlap"], 1e-3)
    scores["estimator_disagreement"] = estimator_disagreement(cases)
    scores["random"] = rng.random(len(cases))
    scores["oracle"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    return scores


def frontier_for_score(
    score: pd.Series,
    errors: pd.Series,
    signed: pd.Series | None = None,
    *,
    grid: Sequence[float] = RETENTION_GRID,
    tolerances: Sequence[float] = TOLERANCES_C,
) -> pd.DataFrame:
    values = pd.to_numeric(score, errors="coerce").to_numpy(dtype=float)
    err = pd.to_numeric(errors, errors="coerce").to_numpy(dtype=float)
    good = np.isfinite(err)
    values = np.where(np.isfinite(values), values, np.inf)[good]
    err = err[good]
    sgn = (
        pd.to_numeric(signed, errors="coerce").to_numpy(dtype=float)[good]
        if signed is not None
        else np.full(err.shape, np.nan)
    )
    order = np.argsort(values, kind="mergesort")
    rows = []
    for retention in grid:
        k = max(1, int(round(float(retention) * len(err))))
        keep = order[:k]
        row = {
            "retention": float(retention),
            "n_retained": int(k),
            "mean_abs_error_c": float(err[keep].mean()),
        }
        for tolerance in tolerances:
            row[f"rate_above_{tolerance}"] = float((err[keep] > float(tolerance)).mean())
        finite_signed = sgn[keep]
        row["severe_underestimate_rate"] = (
            float(np.nanmean(finite_signed < -1.0)) if np.isfinite(finite_signed).any() else float("nan")
        )
        rows.append(row)
    return pd.DataFrame(rows)


def all_frontiers(
    cases: pd.DataFrame,
    certificates: pd.DataFrame,
    *,
    seed: int = 0,
) -> pd.DataFrame:
    scores = screening_scores(cases, certificates, seed=seed)
    policy_error = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    policy_signed = pd.to_numeric(cases["err_policy"], errors="coerce")
    cert_error = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce")
    cert_signed = pd.to_numeric(certificates["certificate_signed_error"], errors="coerce")

    pieces = []
    for name in scores.columns:
        if name == "certificate":
            frame = frontier_for_score(scores[name], cert_error, cert_signed)
            frame["screen"] = "certificate"
            pieces.append(frame)
            ablation = frontier_for_score(scores[name], policy_error, policy_signed)
            ablation["screen"] = "certificate_screen_only"
            pieces.append(ablation)
            continue
        frame = frontier_for_score(scores[name], policy_error, policy_signed)
        frame["screen"] = name
        pieces.append(frame)
    return pd.concat(pieces, ignore_index=True)


def incumbent_operating_points(cases: pd.DataFrame, certificates: pd.DataFrame) -> pd.DataFrame:
    """Johnson-style fixed-length cut-offs, and the certificate at equal retention."""

    length = pd.to_numeric(cases["longest_run"], errors="coerce")
    policy_error = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    cert_error = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce")
    bound = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    rows = []
    for label, threshold in [
        ("length <= 49 d (Johnson, unfilled)", JOHNSON_UNFILLED_DAYS),
        ("length <= 140 d (Johnson, with imputation)", JOHNSON_FILLED_DAYS),
        ("length <= 180 d", 180),
    ]:
        keep = length <= threshold
        retention = float(keep.mean())
        row = {
            "rule": label,
            "retention": retention,
            "rate_above_0.5": float((policy_error[keep] > PRIMARY_TOLERANCE_C).mean()),
            "mean_abs_error_c": float(policy_error[keep].mean()),
        }
        order = np.argsort(np.where(np.isfinite(bound), bound, np.inf), kind="mergesort")
        k = max(1, int(round(retention * len(cases))))
        matched = cert_error.to_numpy()[order[:k]]
        matched = matched[np.isfinite(matched)]
        row["certificate_rate_above_0.5_at_equal_retention"] = float((matched > PRIMARY_TOLERANCE_C).mean())
        row["certificate_mean_abs_error_at_equal_retention"] = float(matched.mean())
        row["absolute_points_saved"] = (row["rate_above_0.5"] - row["certificate_rate_above_0.5_at_equal_retention"]) * 100
        rows.append(row)
    return pd.DataFrame(rows)


def operating_point_contrast(
    cases: pd.DataFrame,
    certificates: pd.DataFrame,
    *,
    retention: float = 0.7,
    tolerance: float = PRIMARY_TOLERANCE_C,
    seed: int = 0,
    draws: int = 2000,
) -> dict:
    """Network-clustered interval on the headline contrast at matched retention.

    The denominator is the full candidate case set. Reconstruction failures
    (non-finite selected errors) stay in the ledger and count as consequential
    failures when selected into the retention slice — they are never dropped
    before choosing the 70% operating point.
    """

    frame = cases[["network_id"]].copy()
    frame["cert_score"] = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    frame["cert_error"] = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce")
    rng = np.random.default_rng(int(seed) + 991)
    frame["length"] = pd.to_numeric(cases["longest_run"], errors="coerce") + rng.random(len(cases))
    frame["policy_error"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    # Missing scores sort last so they are not silently preferred; they remain
    # in the population denominator.
    frame["cert_score"] = frame["cert_score"].fillna(np.inf)
    n_full = int(len(frame))
    n_cert_finite = int(np.isfinite(frame["cert_error"].to_numpy(dtype=float)).sum())
    n_policy_finite = int(np.isfinite(frame["policy_error"].to_numpy(dtype=float)).sum())

    def _failure_rate(errors: np.ndarray, tol: float) -> float:
        bad = (~np.isfinite(errors)) | (errors > tol)
        return float(bad.mean()) if len(errors) else float("nan")

    def contrast(block: pd.DataFrame) -> float:
        k = max(1, int(round(float(retention) * len(block))))
        if k > len(block):
            # Target retention unreachable on this bootstrap draw.
            return float("nan")
        cert = block.nsmallest(k, "cert_score")["cert_error"].to_numpy(dtype=float)
        length = block.nsmallest(k, "length")["policy_error"].to_numpy(dtype=float)
        return _failure_rate(cert, tolerance) - _failure_rate(length, tolerance)

    stat = cluster_bootstrap(frame, contrast, draws=draws, seed=seed)
    stat["retention"] = float(retention)
    stat["tolerance_c"] = float(tolerance)
    stat["n_candidate_cases"] = n_full
    stat["n_cert_error_finite"] = n_cert_finite
    stat["n_policy_error_finite"] = n_policy_finite
    stat["n_cert_reconstruction_failures"] = n_full - n_cert_finite
    target_k = max(1, int(round(float(retention) * n_full)))
    selected = frame.nsmallest(target_k, "cert_score")
    sel_err = selected["cert_error"].to_numpy(dtype=float)
    stat["retention_of_full_denominator"] = float(target_k / n_full) if n_full else float("nan")
    stat["selected_reconstruction_failure_rate"] = (
        float((~np.isfinite(sel_err)).mean()) if target_k else float("nan")
    )
    return stat


def coverage_table(cases: pd.DataFrame, certificates: pd.DataFrame, *, strata: Sequence[str] = ("donor_regime",)) -> pd.DataFrame:
    """H3: marginal and conditional coverage of the conformal interval."""

    frame = cases.copy()
    frame["covered"] = pd.to_numeric(certificates["covered"], errors="coerce")
    frame["bound_covered"] = pd.to_numeric(certificates.get("bound_covered"), errors="coerce")
    frame["interval_width"] = pd.to_numeric(certificates["interval_width"], errors="coerce")
    rows = [
        {
            "stratum": "all",
            "level": "marginal",
            "n": int(frame["covered"].notna().sum()),
            "coverage": float(frame["covered"].mean()),
            "bound_coverage": float(frame["bound_covered"].mean()),
            "median_width_c": float(frame["interval_width"].median()),
        }
    ]
    for column in strata:
        if column not in frame.columns:
            continue
        for value, block in frame.groupby(column):
            rows.append(
                {
                    "stratum": f"{column}={value}",
                    "level": "conditional",
                    "n": int(block["covered"].notna().sum()),
                    "coverage": float(block["covered"].mean()),
                    "bound_coverage": float(block["bound_covered"].mean()),
                    "median_width_c": float(block["interval_width"].median()),
                }
            )
    bucket = pd.cut(pd.to_numeric(frame["longest_run"], errors="coerce"), [0, 30, 90, 180, 400])
    for value, block in frame.groupby(bucket, observed=True):
        rows.append(
            {
                "stratum": f"longest_run={value}",
                "level": "conditional",
                "n": int(block["covered"].notna().sum()),
                "coverage": float(block["covered"].mean()),
                "bound_coverage": float(block["bound_covered"].mean()),
                "median_width_c": float(block["interval_width"].median()),
            }
        )
    overlap = pd.cut(pd.to_numeric(frame["peak_overlap"], errors="coerce"), [-0.001, 0.001, 0.5, 1.001])
    for value, block in frame.groupby(overlap, observed=True):
        rows.append(
            {
                "stratum": f"peak_overlap={value}",
                "level": "conditional",
                "n": int(block["covered"].notna().sum()),
                "coverage": float(block["covered"].mean()),
                "bound_coverage": float(block["bound_covered"].mean()),
                "median_width_c": float(block["interval_width"].median()),
            }
        )
    return pd.DataFrame(rows)
