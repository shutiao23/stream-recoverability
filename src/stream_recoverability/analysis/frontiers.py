"""Recoverability curves, thresholds, change points, and cluster-bootstrap CIs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd


DENSE_T_GAPS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)
DENSE_FLOW_LEVEL_GAPS = (3, 10, 30, 60, 90, 120, 180, 365)


def dense_gap_coverage(
    gap_lengths: Sequence[float], target: str
) -> dict[str, Any]:
    tested = sorted(set(float(value) for value in gap_lengths if np.isfinite(value)))
    recommended = DENSE_T_GAPS if str(target).upper().split("_")[-1] == "T" else DENSE_FLOW_LEVEL_GAPS
    missing = [value for value in recommended if not any(np.isclose(value, tested_value) for tested_value in tested)]
    return {
        "tested_gap_lengths": tested,
        "missing_recommended_gap_lengths": missing,
        "dense_grid_complete": not missing,
    }

def interpolate_threshold_crossing(
    gap_lengths: Sequence[float],
    values: Sequence[float],
    *,
    threshold: float = 0.0,
    feasible: str = "above",
    inclusive: bool = False,
) -> float:
    """Interpolate the uppermost feasible-to-infeasible threshold crossing."""

    x = np.asarray(gap_lengths, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if not len(x):
        return np.nan
    order = np.argsort(x)
    x, y = x[order], y[order]
    if feasible == "above":
        accepted = y >= threshold if inclusive else y > threshold
    elif feasible == "below":
        accepted = y <= threshold if inclusive else y < threshold
    else:
        raise ValueError("feasible must be 'above' or 'below'")
    positions = np.flatnonzero(accepted)
    if not positions.size:
        return np.nan
    last = int(positions[-1])
    if last == len(x) - 1:
        return float(x[last])
    next_position = last + 1
    if accepted[next_position] or y[next_position] == y[last]:
        return float(x[last])
    fraction = (threshold - y[last]) / (y[next_position] - y[last])
    return float(x[last] + fraction * (x[next_position] - x[last]))


def _cluster_bootstrap_mean(
    group: pd.DataFrame,
    value_col: str,
    cluster_col: str,
    n_boot: int,
    rng: np.random.Generator,
) -> np.ndarray:
    clusters = [
        values[value_col].to_numpy(dtype=float)
        for _, values in group.groupby(cluster_col, dropna=False, observed=True)
    ]
    draws = np.empty(n_boot, dtype=float)
    for draw in range(n_boot):
        chosen = rng.integers(0, len(clusters), size=len(clusters))
        sample = np.concatenate([clusters[index] for index in chosen])
        draws[draw] = float(np.mean(sample))
    return draws


def skill_curve(
    events: pd.DataFrame,
    *,
    gap_col: str = "gap_length",
    skill_col: str = "skill",
    cluster_col: str = "scenario_id",
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> pd.DataFrame:
    """Mean skill and cluster-bootstrap CI at each tested gap length."""

    missing = sorted({gap_col, skill_col, cluster_col} - set(events.columns))
    if missing:
        raise ValueError(f"skill-curve analysis requires columns: {missing}")
    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    data = events[[gap_col, skill_col, cluster_col]].copy()
    data[gap_col] = pd.to_numeric(data[gap_col], errors="coerce")
    data[skill_col] = pd.to_numeric(data[skill_col], errors="coerce")
    data = data.dropna(subset=[gap_col, skill_col, cluster_col])
    rng = np.random.default_rng(seed)
    alpha = (1.0 - confidence) / 2.0
    rows: list[dict[str, Any]] = []
    for gap, group in data.groupby(gap_col, sort=True, observed=True):
        n_clusters = int(group[cluster_col].nunique())
        if n_clusters < 2:
            lower = upper = np.nan
            reason = "at least two event clusters are required for a CI"
        else:
            draws = _cluster_bootstrap_mean(group, skill_col, cluster_col, n_boot, rng)
            lower = float(np.quantile(draws, alpha))
            upper = float(np.quantile(draws, 1.0 - alpha))
            reason = None
        rows.append(
            {
                "gap_length": float(gap),
                "mean_skill": float(group[skill_col].mean()),
                "ci_lower": lower,
                "ci_upper": upper,
                "n_events": int(len(group)),
                "n_clusters": n_clusters,
                "reason": reason,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "gap_length",
            "mean_skill",
            "ci_lower",
            "ci_upper",
            "n_events",
            "n_clusters",
            "reason",
        ],
    )


def statistical_frontier(curve: pd.DataFrame) -> dict[str, Any]:
    """Largest gap whose lower 95% skill CI remains above zero."""

    required = {"gap_length", "ci_lower"}
    missing = sorted(required - set(curve.columns))
    if missing:
        raise ValueError(f"statistical frontier requires columns: {missing}")
    usable = curve.dropna(subset=["gap_length", "ci_lower"]).sort_values("gap_length")
    if usable.empty:
        return {"statistical_frontier_days": np.nan, "reason": "no finite lower confidence bounds"}
    frontier = interpolate_threshold_crossing(
        usable["gap_length"], usable["ci_lower"], threshold=0.0, feasible="above"
    )
    if not np.isfinite(frontier):
        reason = "lower confidence bound is never above zero"
    elif usable.iloc[-1]["ci_lower"] > 0:
        reason = "right-censored at the largest tested gap"
    else:
        reason = None
    return {"statistical_frontier_days": frontier, "reason": reason}


def application_frontier(
    curve: pd.DataFrame,
    criteria: Mapping[str, tuple[str, float]],
    *,
    gap_col: str = "gap_length",
) -> dict[str, Any]:
    """Find the largest gap satisfying all predeclared application criteria."""

    missing = sorted({gap_col, *criteria} - set(curve.columns))
    if missing:
        return {
            "application_frontier_days": np.nan,
            "limiting_metric": None,
            "reason": f"missing application columns: {missing}",
        }
    candidates: list[tuple[str, float]] = []
    for metric, (operator, threshold) in criteria.items():
        values = pd.to_numeric(curve[metric], errors="coerce").to_numpy(dtype=float)
        gaps = pd.to_numeric(curve[gap_col], errors="coerce").to_numpy(dtype=float)
        if operator in {"<=", "<"}:
            frontier = interpolate_threshold_crossing(
                gaps,
                threshold - values,
                threshold=0.0,
                feasible="above",
                inclusive=operator == "<=",
            )
        elif operator in {">=", ">"}:
            frontier = interpolate_threshold_crossing(
                gaps,
                values - threshold,
                threshold=0.0,
                feasible="above",
                inclusive=operator == ">=",
            )
        else:
            raise ValueError(f"unsupported application operator: {operator}")
        candidates.append((metric, frontier))
    finite = [(metric, value) for metric, value in candidates if np.isfinite(value)]
    if len(finite) != len(candidates):
        failed = [metric for metric, value in candidates if not np.isfinite(value)]
        return {
            "application_frontier_days": np.nan,
            "limiting_metric": failed[0] if failed else None,
            "reason": f"criteria never met: {failed}",
        }
    limiting_metric, frontier = min(finite, key=lambda item: item[1])
    finite_gaps = pd.to_numeric(curve[gap_col], errors="coerce").dropna()
    right_censored = bool(
        len(finite_gaps) and np.isclose(frontier, float(finite_gaps.max()))
    )
    return {
        "application_frontier_days": float(frontier),
        "limiting_metric": limiting_metric,
        "reason": "right-censored at the largest tested gap" if right_censored else None,
    }


def segmented_sse_breakpoint(
    gap_lengths: Sequence[float],
    values: Sequence[float],
    *,
    min_segment_points: int = 2,
) -> dict[str, Any]:
    """Choose the shared two-line breakpoint with minimum total SSE."""

    x = np.asarray(gap_lengths, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if len(x):
        aggregated = pd.DataFrame({"x": x, "y": y}).groupby("x", as_index=False)["y"].mean()
        x = aggregated["x"].to_numpy(dtype=float)
        y = aggregated["y"].to_numpy(dtype=float)
    if len(x) < 2 * min_segment_points - 1:
        return {
            "breakpoint_days": np.nan,
            "sse": np.nan,
            "left_slope": np.nan,
            "right_slope": np.nan,
            "reason": "insufficient distinct gap lengths",
        }
    best: tuple[float, int, np.ndarray, np.ndarray] | None = None
    for breakpoint in range(min_segment_points - 1, len(x) - min_segment_points + 1):
        left_x, left_y = x[: breakpoint + 1], y[: breakpoint + 1]
        right_x, right_y = x[breakpoint:], y[breakpoint:]
        left_fit = np.polyfit(left_x, left_y, 1)
        right_fit = np.polyfit(right_x, right_y, 1)
        sse = float(
            np.sum(np.square(left_y - np.polyval(left_fit, left_x)))
            + np.sum(np.square(right_y - np.polyval(right_fit, right_x)))
        )
        candidate = (sse, breakpoint, left_fit, right_fit)
        if best is None or candidate[0] < best[0]:
            best = candidate
    assert best is not None
    return {
        "breakpoint_days": float(x[best[1]]),
        "sse": best[0],
        "left_slope": float(best[2][0]),
        "right_slope": float(best[3][0]),
        "reason": None,
    }


def cluster_bootstrap_frontier_ci(
    events: pd.DataFrame,
    *,
    gap_col: str = "gap_length",
    value_col: str = "skill",
    cluster_col: str = "scenario_id",
    threshold: float = 0.0,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    """Cluster-bootstrap the interpolated mean-skill frontier within each gap."""

    missing = sorted({gap_col, value_col, cluster_col} - set(events.columns))
    if missing:
        raise ValueError(f"frontier bootstrap requires columns: {missing}")
    data = events[[gap_col, value_col, cluster_col]].copy()
    data[gap_col] = pd.to_numeric(data[gap_col], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna()
    if data[gap_col].nunique() < 2:
        return {
            "frontier_days": np.nan,
            "frontier_ci_lower": np.nan,
            "frontier_ci_upper": np.nan,
            "n_boot_valid": 0,
            "reason": "at least two gap lengths are required",
        }
    grouped = list(data.groupby(gap_col, sort=True, observed=True))
    if any(group[cluster_col].nunique() < 2 for _, group in grouped):
        return {
            "frontier_days": np.nan,
            "frontier_ci_lower": np.nan,
            "frontier_ci_upper": np.nan,
            "n_boot_valid": 0,
            "reason": "each gap needs at least two event clusters",
        }
    original_x = np.asarray([gap for gap, _ in grouped], dtype=float)
    original_y = np.asarray([group[value_col].mean() for _, group in grouped], dtype=float)
    estimate = interpolate_threshold_crossing(original_x, original_y, threshold=threshold)
    rng = np.random.default_rng(seed)
    draws: list[float] = []
    cluster_arrays = [
        [values[value_col].to_numpy(dtype=float) for _, values in group.groupby(cluster_col, dropna=False)]
        for _, group in grouped
    ]
    for _ in range(n_boot):
        curve_values = []
        for clusters in cluster_arrays:
            chosen = rng.integers(0, len(clusters), size=len(clusters))
            curve_values.append(float(np.mean(np.concatenate([clusters[index] for index in chosen]))))
        frontier = interpolate_threshold_crossing(original_x, curve_values, threshold=threshold)
        if np.isfinite(frontier):
            draws.append(frontier)
    if not draws:
        return {
            "frontier_days": estimate,
            "frontier_ci_lower": np.nan,
            "frontier_ci_upper": np.nan,
            "n_boot_valid": 0,
            "reason": "no bootstrap replicate had a finite crossing",
        }
    alpha = (1.0 - confidence) / 2.0
    return {
        "frontier_days": estimate,
        "frontier_ci_lower": float(np.quantile(draws, alpha)),
        "frontier_ci_upper": float(np.quantile(draws, 1.0 - alpha)),
        "n_boot_valid": int(len(draws)),
        "reason": (
            "right-censored at the largest tested gap"
            if original_y[-1] > threshold
            else None
        ),
    }


def estimate_frontiers(
    events: pd.DataFrame,
    *,
    group_cols: Sequence[str] = ("station_id", "target", "model", "pattern"),
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return grouped skill curves and frontier summaries."""

    active_groups = [column for column in group_cols if column in events]
    grouped = events.groupby(active_groups, dropna=False, observed=True) if active_groups else [((), events)]
    curves: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    for offset, (group_key, group) in enumerate(grouped):
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key if active_groups else (), strict=True))
        curve = skill_curve(group, n_boot=n_boot, seed=seed + offset)
        for column, value in metadata.items():
            curve[column] = value
        curves.append(curve)
        statistical = statistical_frontier(curve)
        knee = segmented_sse_breakpoint(curve["gap_length"], curve["mean_skill"])
        boot = cluster_bootstrap_frontier_ci(group, n_boot=n_boot, seed=seed + offset)
        coverage = dense_gap_coverage(
            curve["gap_length"], metadata.get("target", "T")
        )
        summaries.append(
            {
                **metadata,
                **statistical,
                **coverage,
                "breakpoint_days": knee["breakpoint_days"],
                "breakpoint_sse": knee["sse"],
                "breakpoint_reason": knee["reason"],
                "frontier_ci_lower": boot["frontier_ci_lower"],
                "frontier_ci_upper": boot["frontier_ci_upper"],
                "frontier_bootstrap_reason": boot["reason"],
            }
        )
    return (
        pd.concat(curves, ignore_index=True) if curves else pd.DataFrame(),
        pd.DataFrame(summaries),
    )


__all__ = [
    "application_frontier",
    "cluster_bootstrap_frontier_ci",
    "dense_gap_coverage",
    "DENSE_FLOW_LEVEL_GAPS",
    "DENSE_T_GAPS",
    "estimate_frontiers",
    "interpolate_threshold_crossing",
    "segmented_sse_breakpoint",
    "skill_curve",
    "statistical_frontier",
]
