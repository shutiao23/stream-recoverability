"""Recoverability curves, thresholds, change points, and cluster-bootstrap CIs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

DENSE_T_GAPS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)
DENSE_FLOW_LEVEL_GAPS = (3, 10, 30, 60, 90, 120, 180, 365)
FRONTIER_EXPERIMENT = "SCI_DENSE"
FRONTIER_GROUP_COLUMNS = (
    "experiment",
    "mask_type",
    "layout",
    "window_length",
    "training_protocol",
    "validation_scope",
    "station_id",
    "target",
    "model",
    "pattern",
)


def frontier_design_subset(events: pd.DataFrame) -> pd.DataFrame:
    """Select the predeclared dense, single-block, fixed-window design.

    A result table may contain several experiment suites.  Only ``SCI_DENSE``
    rows are eligible for a recoverability frontier.  ``mask_type`` and
    ``layout`` are filled from that experiment's fixed contract when an older
    event export omitted them; conflicting explicit values are rejected.
    ``window_length`` is never inferred because mixing context windows changes
    the estimand.
    """

    required = {"experiment", "window_length"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(
            "frontier analysis requires an explicit SCI_DENSE design with columns: "
            f"{missing}"
        )
    data = events.loc[
        events["experiment"].astype(str).str.upper().eq(FRONTIER_EXPERIMENT)
    ].copy()
    if data.empty:
        raise ValueError("frontier analysis requires experiment='SCI_DENSE'")

    if "mask_type" in data:
        mask_type = data["mask_type"].astype("string").str.lower()
        accepted = mask_type.isna() | mask_type.isin(
            {"block", "single_block", "single-block"}
        )
        data = data.loc[accepted].copy()
        data["mask_type"] = mask_type.loc[accepted].fillna("block")
    else:
        data["mask_type"] = "block"
    if "layout" in data:
        layout = data["layout"].astype("string").str.lower()
        accepted = layout.isna() | layout.isin(
            {"single", "single_block", "single-block"}
        )
        data = data.loc[accepted].copy()
        data["layout"] = layout.loc[accepted].fillna("single")
    else:
        data["layout"] = "single"
    if data.empty:
        raise ValueError("SCI_DENSE frontier rows must use a single contiguous block")

    data["window_length"] = pd.to_numeric(data["window_length"], errors="coerce")
    data = data.dropna(subset=["window_length"])
    if data.empty:
        raise ValueError("SCI_DENSE frontier rows require a finite window_length")
    return data


def dense_gap_coverage(gap_lengths: Sequence[float], target: str) -> dict[str, Any]:
    tested = sorted({float(value) for value in gap_lengths if np.isfinite(value)})
    recommended = (
        DENSE_T_GAPS
        if str(target).upper().split("_")[-1] == "T"
        else DENSE_FLOW_LEVEL_GAPS
    )
    missing = [
        value
        for value in recommended
        if not any(np.isclose(value, tested_value) for tested_value in tested)
    ]
    return {
        "tested_gap_lengths": tested,
        "missing_recommended_gap_lengths": missing,
        "dense_grid_complete": not missing,
    }


def _monotone_first_loss_frontier(
    gap_lengths: Sequence[float],
    values: Sequence[float],
    *,
    threshold: float = 0.0,
    inclusive: bool = False,
) -> dict[str, Any]:
    """Estimate the first loss after imposing a non-increasing envelope."""

    x = np.asarray(gap_lengths, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if not len(x):
        return {
            "frontier_days": np.nan,
            "censoring": None,
            "reason": "no finite frontier values",
        }
    aggregated = (
        pd.DataFrame({"gap": x, "value": y})
        .groupby("gap", as_index=False, observed=True)["value"]
        .mean()
        .sort_values("gap")
    )
    x = aggregated["gap"].to_numpy(dtype=float)
    monotone = np.minimum.accumulate(aggregated["value"].to_numpy(dtype=float))
    feasible = monotone >= threshold if inclusive else monotone > threshold
    if not feasible[0]:
        return {
            "frontier_days": 0.0,
            "censoring": "left",
            "reason": "left-censored below the smallest tested gap",
        }
    losses = np.flatnonzero(~feasible)
    if not losses.size:
        return {
            "frontier_days": float(x[-1]),
            "censoring": "right",
            "reason": "right-censored at the largest tested gap",
        }
    right = int(losses[0])
    left = right - 1
    if monotone[right] == monotone[left]:
        frontier = float(x[left])
    else:
        fraction = (threshold - monotone[left]) / (monotone[right] - monotone[left])
        frontier = float(x[left] + fraction * (x[right] - x[left]))
    return {"frontier_days": frontier, "censoring": None, "reason": None}


def interpolate_threshold_crossing(
    gap_lengths: Sequence[float],
    values: Sequence[float],
    *,
    threshold: float = 0.0,
    feasible: str = "above",
    inclusive: bool = False,
) -> float:
    """Interpolate the monotone first loss of feasibility.

    A return value of zero denotes left censoring below the smallest tested gap;
    the largest tested gap denotes right censoring when feasibility is never lost.
    """

    x = np.asarray(gap_lengths, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if not len(x):
        return np.nan
    if feasible == "above":
        margin = y - threshold
    elif feasible == "below":
        margin = threshold - y
    else:
        raise ValueError("feasible must be 'above' or 'below'")
    estimate = _monotone_first_loss_frontier(
        x,
        margin,
        threshold=0.0,
        inclusive=inclusive,
    )
    return float(estimate["frontier_days"])


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
                "n_events": len(group),
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


_REPO_ROOT = Path(__file__).resolve().parents[3]
STATISTICAL_RECOVERABILITY_DESIGN_PATH = _REPO_ROOT / "configs/design_freeze_v4.yaml"
STATISTICAL_FRONTIER_DEFINITION = "monotone_first_loss_lower_confidence_bound"
STATISTICAL_FRONTIER_THRESHOLD = 0.0


def load_statistical_recoverability_rule(
    design_path: str | Path = STATISTICAL_RECOVERABILITY_DESIGN_PATH,
) -> dict[str, Any]:
    """Return the frozen T-frontier recoverability criterion."""

    with Path(design_path).open(encoding="utf-8") as handle:
        design = yaml.safe_load(handle)
    if not isinstance(design, Mapping):
        raise TypeError("design freeze must be a mapping")
    try:
        rule = design["statistics"]["statistical_recoverability"]
    except (KeyError, TypeError) as error:
        raise ValueError("design freeze omits statistical_recoverability") from error
    if not isinstance(rule, Mapping):
        raise TypeError("statistical_recoverability must be a mapping")
    definition = str(rule["frontier_definition"])
    threshold = float(rule["threshold"])
    event = str(rule["recoverability_event"])
    if definition != STATISTICAL_FRONTIER_DEFINITION:
        raise ValueError("statistical_recoverability frontier_definition drifted from code")
    if not abs(threshold - STATISTICAL_FRONTIER_THRESHOLD) <= 1e-12:
        raise ValueError("statistical_recoverability threshold drifted from code")
    if event != "lower_95_percent_skill_ci_strictly_above_zero":
        raise ValueError("statistical_recoverability event is not the frozen CI>0 rule")
    if bool(rule.get("not_an_application_or_regulatory_threshold")) is not True:
        raise ValueError("statistical recoverability must not be treated as an application threshold")
    return {
        "status": str(rule["status"]),
        "recoverability_event": event,
        "frontier_definition": definition,
        "threshold": threshold,
        "interpolation": str(rule["interpolation"]),
        "dual_baseline_required": tuple(
            str(value) for value in rule["dual_baseline_required"]
        ),
    }


def statistical_frontier(
    curve: pd.DataFrame,
    *,
    design_path: str | Path | None = STATISTICAL_RECOVERABILITY_DESIGN_PATH,
) -> dict[str, Any]:
    """Monotone first-loss frontier where the 95% lower skill CI loses zero."""

    if design_path is not None:
        rule = load_statistical_recoverability_rule(design_path)
        definition = rule["frontier_definition"]
        threshold = float(rule["threshold"])
    else:
        definition = STATISTICAL_FRONTIER_DEFINITION
        threshold = STATISTICAL_FRONTIER_THRESHOLD

    required = {"gap_length", "ci_lower"}
    missing = sorted(required - set(curve.columns))
    if missing:
        raise ValueError(f"statistical frontier requires columns: {missing}")
    usable = curve.dropna(subset=["gap_length", "ci_lower"]).sort_values("gap_length")
    if usable.empty:
        return {
            "statistical_frontier_days": np.nan,
            "frontier_censoring": None,
            "frontier_definition": definition,
            "reason": "no finite lower confidence bounds",
        }
    estimate = _monotone_first_loss_frontier(
        usable["gap_length"], usable["ci_lower"], threshold=threshold
    )
    return {
        "statistical_frontier_days": estimate["frontier_days"],
        "frontier_censoring": estimate["censoring"],
        "frontier_definition": definition,
        "reason": estimate["reason"],
    }


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
    numeric = curve[[gap_col, *criteria]].apply(pd.to_numeric, errors="coerce")
    invalid = {
        column: numeric.loc[~np.isfinite(numeric[column]), gap_col].tolist()
        for column in criteria
        if (~np.isfinite(numeric[column])).any()
    }
    if (~np.isfinite(numeric[gap_col])).any() or invalid:
        return {
            "application_frontier_days": np.nan,
            "limiting_metric": None,
            "reason": f"non-finite application values at tested gaps: {invalid}",
        }
    candidates: list[tuple[str, float]] = []
    candidate_censoring: dict[str, str | None] = {}
    for metric, (operator, threshold) in criteria.items():
        values = pd.to_numeric(curve[metric], errors="coerce").to_numpy(dtype=float)
        gaps = pd.to_numeric(curve[gap_col], errors="coerce").to_numpy(dtype=float)
        if operator in {"<=", "<"}:
            estimate = _monotone_first_loss_frontier(
                gaps,
                threshold - values,
                threshold=0.0,
                inclusive=operator == "<=",
            )
        elif operator in {">=", ">"}:
            estimate = _monotone_first_loss_frontier(
                gaps,
                values - threshold,
                threshold=0.0,
                inclusive=operator == ">=",
            )
        else:
            raise ValueError(f"unsupported application operator: {operator}")
        frontier = (
            np.nan if estimate["censoring"] == "left" else estimate["frontier_days"]
        )
        candidates.append((metric, frontier))
        candidate_censoring[metric] = estimate["censoring"]
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
        "reason": (
            "right-censored at the largest tested gap"
            if right_censored and candidate_censoring[limiting_metric] == "right"
            else None
        ),
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
        aggregated = (
            pd.DataFrame({"x": x, "y": y}).groupby("x", as_index=False)["y"].mean()
        )
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
    pair_cols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Paired bootstrap CI for the monotone first-loss mean-skill frontier.

    The default paired unit is ``mask_seed x training_seed`` when available.
    Each sampled unit contributes its complete curve, so a draw cannot combine
    unrelated masks at different gap lengths.  Draws that remain feasible at
    the largest tested gap are retained at that tested boundary and reported as
    right-censored.
    """

    missing = sorted({gap_col, value_col} - set(events.columns))
    if missing:
        raise ValueError(f"frontier bootstrap requires columns: {missing}")
    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    if pair_cols is None:
        pair_cols = [
            column for column in ("mask_seed", "training_seed") if column in events
        ]
        if not pair_cols and cluster_col in events:
            pair_cols = [cluster_col]
    else:
        pair_cols = list(pair_cols)
        missing_pairs = sorted(set(pair_cols) - set(events.columns))
        if missing_pairs:
            raise ValueError(
                f"frontier bootstrap requires pairing columns: {missing_pairs}"
            )
    if not pair_cols:
        raise ValueError("frontier bootstrap requires a cross-gap pairing unit")

    data = events[[gap_col, value_col, *pair_cols]].copy()
    data[gap_col] = pd.to_numeric(data[gap_col], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=[gap_col, value_col])
    if data[gap_col].nunique() < 2:
        return {
            "frontier_days": np.nan,
            "frontier_ci_lower": np.nan,
            "frontier_ci_upper": np.nan,
            "n_boot_valid": 0,
            "n_boot_right_censored": 0,
            "n_boot_left_censored": 0,
            "reason": "at least two gap lengths are required",
        }

    pair_values = data.loc[:, pair_cols].astype(object)
    pair_values = pair_values.where(pair_values.notna(), "<NA>")
    data["_frontier_unit"] = [
        tuple(values) for values in pair_values.itertuples(index=False, name=None)
    ]
    collapsed = (
        data.groupby(["_frontier_unit", gap_col], dropna=False, observed=True)[
            value_col
        ]
        .mean()
        .unstack(gap_col)
        .sort_index(axis=1)
    )
    complete = collapsed.notna().all(axis=1)
    n_excluded = int((~complete).sum())
    panel = collapsed.loc[complete]
    if panel.empty:
        return {
            "frontier_days": np.nan,
            "frontier_ci_lower": np.nan,
            "frontier_ci_upper": np.nan,
            "n_boot_valid": 0,
            "n_boot_right_censored": 0,
            "n_boot_left_censored": 0,
            "n_paired_units": 0,
            "n_incomplete_units_excluded": n_excluded,
            "bootstrap_unit": "+".join(pair_cols),
            "reason": "no pairing unit has finite values at every gap length",
        }
    original_x = panel.columns.to_numpy(dtype=float)
    original_y = panel.mean(axis=0).to_numpy(dtype=float)
    point = _monotone_first_loss_frontier(original_x, original_y, threshold=threshold)
    common = {
        "frontier_days": point["frontier_days"],
        "frontier_censoring": point["censoring"],
        "frontier_definition": "monotone_first_loss_mean_skill",
        "n_paired_units": len(panel),
        "n_incomplete_units_excluded": n_excluded,
        "bootstrap_unit": "+".join(pair_cols),
    }
    if len(panel) < 2:
        return {
            **common,
            "frontier_ci_lower": np.nan,
            "frontier_ci_upper": np.nan,
            "n_boot_valid": 0,
            "n_boot_right_censored": 0,
            "n_boot_left_censored": 0,
            "reason": "at least two complete paired units are required for a CI",
        }

    rng = np.random.default_rng(seed)
    panel_values = panel.to_numpy(dtype=float)
    draws = np.empty(n_boot, dtype=float)
    right_censored = 0
    left_censored = 0
    for draw in range(n_boot):
        chosen = rng.integers(0, len(panel_values), size=len(panel_values))
        estimate = _monotone_first_loss_frontier(
            original_x,
            panel_values[chosen].mean(axis=0),
            threshold=threshold,
        )
        draws[draw] = float(estimate["frontier_days"])
        right_censored += estimate["censoring"] == "right"
        left_censored += estimate["censoring"] == "left"
    alpha = (1.0 - confidence) / 2.0
    return {
        **common,
        "frontier_ci_lower": float(np.quantile(draws, alpha)),
        "frontier_ci_upper": float(np.quantile(draws, 1.0 - alpha)),
        "n_boot_valid": int(n_boot),
        "n_boot_right_censored": int(right_censored),
        "n_boot_left_censored": int(left_censored),
        "reason": point["reason"],
    }


def estimate_frontiers(
    events: pd.DataFrame,
    *,
    group_cols: Sequence[str] = FRONTIER_GROUP_COLUMNS,
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return fixed-design paired skill curves and frontier summaries."""

    data = frontier_design_subset(events)
    active_groups = [column for column in group_cols if column in data]
    grouped = (
        data.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), data)]
    )
    curves: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    for offset, (group_key, group) in enumerate(grouped):
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        pair_cols = [
            column for column in ("mask_seed", "training_seed") if column in group
        ]
        if not pair_cols and "scenario_id" in group:
            pair_cols = ["scenario_id"]
        paired = group[["gap_length", "skill", *pair_cols]].copy()
        paired["gap_length"] = pd.to_numeric(paired["gap_length"], errors="coerce")
        paired["skill"] = pd.to_numeric(paired["skill"], errors="coerce")
        paired = paired.dropna(subset=["gap_length", "skill"])
        pair_values = paired.loc[:, pair_cols].astype(object)
        pair_values = pair_values.where(pair_values.notna(), "<NA>")
        paired["_frontier_unit"] = [
            tuple(values) for values in pair_values.itertuples(index=False, name=None)
        ]
        panel = (
            paired.groupby(["_frontier_unit", "gap_length"], observed=True)["skill"]
            .mean()
            .unstack("gap_length")
            .sort_index(axis=1)
        )
        panel = panel.loc[panel.notna().all(axis=1)]
        if panel.empty:
            curve = pd.DataFrame()
        else:
            stacked = panel.rename_axis(columns="gap_length")
            try:
                curve_series = stacked.stack(future_stack=True)
            except TypeError:
                curve_series = stacked.stack(dropna=False)
            curve_data = curve_series.rename("skill").reset_index()
            curve = skill_curve(
                curve_data,
                cluster_col="_frontier_unit",
                n_boot=n_boot,
                seed=seed + offset,
            )
            for column, value in metadata.items():
                curve[column] = value
            curves.append(curve)
        statistical = (
            statistical_frontier(curve)
            if not curve.empty
            else {
                "statistical_frontier_days": np.nan,
                "frontier_censoring": None,
                "frontier_definition": "monotone_first_loss_lower_confidence_bound",
                "reason": "no complete paired skill curve",
            }
        )
        knee = segmented_sse_breakpoint(
            curve["gap_length"] if not curve.empty else [],
            curve["mean_skill"] if not curve.empty else [],
        )
        coverage = dense_gap_coverage(
            curve["gap_length"] if not curve.empty else [],
            metadata.get("target", "T"),
        )
        if coverage["dense_grid_complete"]:
            boot = cluster_bootstrap_frontier_ci(
                group, n_boot=n_boot, seed=seed + offset
            )
        else:
            missing_gaps = coverage["missing_recommended_gap_lengths"]
            incomplete_reason = (
                f"incomplete predeclared dense gap grid; missing {missing_gaps}"
            )
            statistical = {
                "statistical_frontier_days": np.nan,
                "frontier_censoring": None,
                "frontier_definition": ("monotone_first_loss_lower_confidence_bound"),
                "reason": incomplete_reason,
            }
            knee = {
                "breakpoint_days": np.nan,
                "sse": np.nan,
                "reason": incomplete_reason,
            }
            boot = {
                "frontier_days": np.nan,
                "frontier_censoring": None,
                "frontier_definition": "monotone_first_loss_mean_skill",
                "frontier_ci_lower": np.nan,
                "frontier_ci_upper": np.nan,
                "reason": incomplete_reason,
                "bootstrap_unit": "+".join(pair_cols),
                "n_paired_units": len(panel),
                "n_incomplete_units_excluded": 0,
                "n_boot_valid": 0,
                "n_boot_right_censored": 0,
                "n_boot_left_censored": 0,
            }
        summaries.append(
            {
                **metadata,
                "statistical_frontier_days": statistical["statistical_frontier_days"],
                "statistical_frontier_censoring": statistical["frontier_censoring"],
                "statistical_frontier_definition": statistical["frontier_definition"],
                "reason": statistical["reason"],
                "mean_frontier_days": boot["frontier_days"],
                "mean_frontier_censoring": boot.get("frontier_censoring"),
                "mean_frontier_definition": boot.get("frontier_definition"),
                **coverage,
                "breakpoint_days": knee["breakpoint_days"],
                "breakpoint_sse": knee["sse"],
                "breakpoint_reason": knee["reason"],
                "frontier_ci_lower": boot["frontier_ci_lower"],
                "frontier_ci_upper": boot["frontier_ci_upper"],
                "frontier_ci_estimand": boot.get("frontier_definition"),
                "mean_frontier_ci_lower": boot["frontier_ci_lower"],
                "mean_frontier_ci_upper": boot["frontier_ci_upper"],
                "frontier_bootstrap_reason": boot["reason"],
                "frontier_bootstrap_unit": boot.get("bootstrap_unit"),
                "n_frontier_paired_units": boot.get("n_paired_units", 0),
                "n_incomplete_frontier_units_excluded": boot.get(
                    "n_incomplete_units_excluded", 0
                ),
                "n_boot_valid": boot.get("n_boot_valid", 0),
                "n_boot_right_censored": boot.get("n_boot_right_censored", 0),
                "n_boot_left_censored": boot.get("n_boot_left_censored", 0),
            }
        )
    return (
        pd.concat(curves, ignore_index=True) if curves else pd.DataFrame(),
        pd.DataFrame(summaries),
    )


SIMPLE_BASELINE_MODELS = (
    "climatology",
    "linear",
    "pchip",
    "kalman",
    "air_only",
    "air_hydro",
    "donor_regression",
    "random_forest",
    "xgboost",
)
DEFAULT_RELATIVE_PAIR_COLUMNS = (
    "experiment",
    "scenario_id",
    "station_id",
    "target",
    "gap_length",
    "mask_seed",
    "window_length",
    "condition_id",
)


def condition_family_key(frame: pd.DataFrame) -> pd.Series:
    """Return a cross-split family that never includes exact gap or condition ID."""

    def values(column: str, default: str) -> pd.Series:
        return (
            frame[column].fillna(default).astype(str)
            if column in frame
            else pd.Series(default, index=frame.index, dtype="string")
        )

    station = values("station_id", "NA")
    target = values("target", "T")
    geometry = values("mask_type", "block")
    information = values("information_combination", "S0+A+B+C+D")
    mode = values("recovery_mode", "offline")
    return station + "|" + target + "|" + geometry + "|" + information + "|" + mode


def select_best_simple_baselines(
    validation_events: pd.DataFrame,
    *,
    metric: str = "MAE",
    models: Sequence[str] = SIMPLE_BASELINE_MODELS,
) -> pd.DataFrame:
    """Freeze one best traditional baseline per validation condition family.

    Selection uses validation events only. Development-test or confirmatory
    tables must consume this lookup and not re-rank baselines.
    """

    required = {"model", metric}
    missing = sorted(required.difference(validation_events.columns))
    if missing:
        raise ValueError(f"best-simple baseline selection requires columns: {missing}")
    data = validation_events.loc[
        validation_events["model"].astype(str).isin(set(models))
    ].copy()
    if data.empty:
        raise ValueError("best-simple baseline selection found no traditional models")
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.dropna(subset=[metric])
    data["condition_family"] = condition_family_key(data)
    data["selection_gap"] = pd.to_numeric(
        data["gap_length"]
        if "gap_length" in data
        else pd.Series(np.nan, index=data.index),
        errors="coerce",
    ).fillna(-1)
    scenario_means = data.groupby(
        ["condition_family", "model", "selection_gap"],
        as_index=False,
        observed=True,
    )[metric].mean()
    ranked = scenario_means.groupby(
        ["condition_family", "model"], as_index=False, observed=True
    )[metric].mean()
    tie_order = {model: index for index, model in enumerate(models)}
    ranked["tie_break_order"] = ranked["model"].map(tie_order).fillna(len(tie_order))
    ranked = ranked.sort_values(
        ["condition_family", metric, "tie_break_order"], kind="mergesort"
    )
    best = ranked.groupby("condition_family", as_index=False, observed=True).first()
    best = best.rename(
        columns={"model": "best_simple_baseline", metric: "validation_mean_MAE"}
    )
    counts = (
        scenario_means.groupby("condition_family", as_index=False, observed=True)[
            "selection_gap"
        ]
        .nunique()
        .rename(columns={"selection_gap": "validation_scenario_count"})
    )
    best = best.merge(counts, on="condition_family", how="left", validate="one_to_one")
    family_parts = best["condition_family"].str.split("|", expand=True)
    for index, column in enumerate(
        (
            "station_id",
            "target",
            "mask_geometry",
            "information_contract",
            "recovery_mode",
        )
    ):
        best[column] = family_parts[index]
    best["selection_split"] = "validation"
    best["formal_evidence"] = False
    best["selection_rule"] = "equal_weight_across_validation_gap_lengths"
    best["tie_break_rule"] = "frozen_simple_model_order"
    return best


def add_relative_skills(
    events: pd.DataFrame,
    *,
    climatology_model: str = "climatology",
    best_simple: pd.DataFrame | None = None,
    metric: str = "MAE",
    pair_columns: Sequence[str] = DEFAULT_RELATIVE_PAIR_COLUMNS,
) -> pd.DataFrame:
    """Add climatology-relative and best-simple-relative skill columns."""

    if metric not in events.columns:
        raise ValueError(f"relative skill requires column {metric!r}")
    result = events.copy()
    result[metric] = pd.to_numeric(result[metric], errors="coerce")
    keys = [column for column in pair_columns if column in result.columns]
    if not keys:
        raise ValueError("relative skill requires at least one pairing column")

    climatology = (
        result.loc[result["model"].astype(str).eq(climatology_model), [*keys, metric]]
        .groupby(keys, as_index=False, observed=True)[metric]
        .mean()
        .rename(columns={metric: "climatology_mae"})
    )
    result = result.merge(climatology, on=keys, how="left")
    denom = result["climatology_mae"]
    result["skill_vs_climatology"] = np.where(
        np.isfinite(result[metric]) & np.isfinite(denom) & (denom > 0),
        1.0 - result[metric] / denom,
        np.nan,
    )

    if best_simple is None:
        result["skill_vs_best_simple"] = np.nan
        result["best_simple_baseline"] = pd.NA
        return result
    if "condition_family" not in result.columns:
        result["condition_family"] = condition_family_key(result)
    lookup = best_simple.loc[
        :, ["condition_family", "best_simple_baseline"]
    ].drop_duplicates("condition_family")
    result = result.merge(lookup, on="condition_family", how="left")
    baseline_rows = result.loc[
        result["model"].astype(str).eq(result["best_simple_baseline"].astype(str)),
        [*keys, metric],
    ].rename(columns={metric: "best_simple_mae"})
    baseline_rows = baseline_rows.groupby(keys, as_index=False, observed=True)[
        "best_simple_mae"
    ].mean()
    result = result.merge(baseline_rows, on=keys, how="left")
    simple_denom = result["best_simple_mae"]
    result["skill_vs_best_simple"] = np.where(
        np.isfinite(result[metric]) & np.isfinite(simple_denom) & (simple_denom > 0),
        1.0 - result[metric] / simple_denom,
        np.nan,
    )
    return result


def estimate_dual_frontiers(
    events: pd.DataFrame,
    *,
    best_simple: pd.DataFrame | None = None,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, pd.DataFrame]:
    """Estimate climatology-relative and best-simple-relative frontiers."""

    scored = add_relative_skills(events, best_simple=best_simple)
    climatology_events = scored.copy()
    climatology_events["skill"] = climatology_events["skill_vs_climatology"]
    climatology_curves, climatology_summary = estimate_frontiers(
        climatology_events, n_boot=n_boot, seed=seed
    )
    climatology_summary["frontier_denominator"] = "climatology"
    climatology_summary["hypothesis_family"] = "frontier_model_vs_climatology"
    simple_events = scored.copy()
    simple_events["skill"] = simple_events["skill_vs_best_simple"]
    if best_simple is None or not np.isfinite(simple_events["skill"]).any():
        simple_curves = pd.DataFrame()
        simple_summary = pd.DataFrame(
            [
                {
                    "frontier_denominator": "best_simple_baseline",
                    "hypothesis_family": "frontier_model_vs_best_simple_baseline",
                    "statistical_frontier_days": np.nan,
                    "reason": "best-simple baseline lookup is missing or has no finite skill",
                }
            ]
        )
    else:
        simple_curves, simple_summary = estimate_frontiers(
            simple_events, n_boot=n_boot, seed=seed + 10_000
        )
        simple_summary["frontier_denominator"] = "best_simple_baseline"
        simple_summary["hypothesis_family"] = "frontier_model_vs_best_simple_baseline"
    return {
        "scored_events": scored,
        "climatology_curves": climatology_curves,
        "climatology_frontiers": climatology_summary,
        "best_simple_curves": simple_curves,
        "best_simple_frontiers": simple_summary,
        "dual_frontiers": pd.concat(
            [climatology_summary, simple_summary], ignore_index=True, sort=False
        ),
    }


__all__ = [
    "DENSE_FLOW_LEVEL_GAPS",
    "DENSE_T_GAPS",
    "SIMPLE_BASELINE_MODELS",
    "add_relative_skills",
    "application_frontier",
    "cluster_bootstrap_frontier_ci",
    "condition_family_key",
    "dense_gap_coverage",
    "estimate_dual_frontiers",
    "estimate_frontiers",
    "load_statistical_recoverability_rule",
    "frontier_design_subset",
    "interpolate_threshold_crossing",
    "segmented_sse_breakpoint",
    "select_best_simple_baselines",
    "skill_curve",
    "statistical_frontier",
]
