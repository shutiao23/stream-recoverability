"""Selected-risk tests over independent groups with arbitrary within-group dependence."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.special import xlogy


def bounded_mean_upper(mean: float, n_groups: int, *, alpha: float) -> float:
    """Chernoff-KL upper bound for the mean of independent bounded [0, 1] units."""

    if not 0 < alpha < 1 or n_groups < 1 or not 0 <= mean <= 1:
        raise ValueError("Require alpha in (0,1), positive groups and mean in [0,1]")
    if mean == 1:
        return 1.0
    radius = np.log(1 / alpha) / n_groups
    if mean == 0:
        return float(-np.expm1(-radius))

    def equation(candidate: float) -> float:
        divergence = xlogy(mean, mean / candidate) + xlogy(1 - mean, (1 - mean) / (1 - candidate))
        return float(divergence - radius)

    upper_endpoint = np.nextafter(1.0, 0.0)
    if equation(upper_endpoint) <= 0:
        return 1.0
    return float(brentq(equation, mean, upper_endpoint))


@dataclass(frozen=True)
class AdmissionSelection:
    threshold: float
    status: str
    n_groups: int
    candidates: np.ndarray
    retention: np.ndarray
    selected_risk: np.ndarray
    bounded_loss_upper: np.ndarray
    risk_cap: float
    alpha: float


def select_group_threshold(
    scores: np.ndarray,
    failures: np.ndarray,
    groups: np.ndarray,
    candidates: np.ndarray,
    *,
    risk_cap: float = 0.05,
    alpha: float = 0.05,
    weights: np.ndarray | None = None,
) -> AdmissionSelection:
    """Test E[B_g] <= risk_cap E[A_g] using a training-fixed candidate family.

    A_g and B_g are within-group mean admission and failure-and-admission.
    X_g = B_g + risk_cap(1-A_g) is bounded in [0,1]. An upper bound on E[X_g]
    at most risk_cap certifies the ratio for a uniformly drawn new group and
    its declared within-group sampling scheme. Groups must be independent and
    sampled from the deployment distribution; this does not promise every
    subgroup's risk. Candidate thresholds and the score model must be fixed
    independently of calibration groups. Bonferroni permits searching the
    complete fixed family, including nonmonotone selected risk.
    """

    scores = np.asarray(scores, dtype=float)
    failures = np.asarray(failures, dtype=bool)
    groups = np.asarray(groups).astype(str)
    candidates = np.unique(np.asarray(candidates, dtype=float))
    candidates = candidates[np.isfinite(candidates)]
    if scores.ndim != 1 or scores.shape != failures.shape or scores.shape != groups.shape:
        raise ValueError("Scores, failure flags and groups must be equal-length vectors")
    if not len(scores) or not len(candidates):
        raise ValueError("Calibration records and fixed candidate thresholds cannot be empty")
    if not 0 < risk_cap < 1 or not 0 < alpha < 1:
        raise ValueError("Risk cap and alpha must be in (0,1)")
    if weights is None:
        weights = np.ones(len(scores))
    weights = np.asarray(weights, dtype=float)
    if weights.shape != scores.shape or not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Within-group sampling weights must be finite and strictly positive")
    units, group_index = np.unique(groups, return_inverse=True)
    totals = np.bincount(group_index, weights=weights, minlength=len(units))
    normalized = weights / totals[group_index]
    retention, selected_risk, upper = [], [], []
    for threshold in candidates:
        admitted = np.isfinite(scores) & (scores <= threshold)
        admitted_group = np.bincount(group_index, weights=normalized * admitted, minlength=len(units))
        bad_group = np.bincount(group_index, weights=normalized * admitted * failures, minlength=len(units))
        average_admitted = float(admitted_group.mean())
        average_bad = float(bad_group.mean())
        loss = bad_group + risk_cap * (1 - admitted_group)
        retention.append(average_admitted)
        selected_risk.append(average_bad / average_admitted if average_admitted else np.nan)
        upper.append(bounded_mean_upper(float(np.clip(loss.mean(), 0, 1)), len(units), alpha=alpha / len(candidates)))
    retention = np.asarray(retention)
    selected_risk = np.asarray(selected_risk)
    upper = np.asarray(upper)
    eligible = np.flatnonzero((upper <= risk_cap) & (retention > 0))
    threshold = float(candidates[eligible[-1]]) if len(eligible) else -float("inf")
    return AdmissionSelection(
        threshold=threshold,
        status="certified" if len(eligible) else "insufficient_independent_calibration_evidence",
        n_groups=len(units),
        candidates=candidates,
        retention=retention,
        selected_risk=selected_risk,
        bounded_loss_upper=upper,
        risk_cap=risk_cap,
        alpha=alpha,
    )


def fixed_training_candidates(scores: np.ndarray, n_candidates: int = 21) -> np.ndarray:
    values = np.asarray(scores, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        raise ValueError("Training scores contain no finite value")
    return np.unique(np.quantile(values, np.linspace(0, 1, n_candidates), method="inverted_cdf"))
