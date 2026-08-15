"""Extreme-event preservation and non-parametric trend diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from stream_recoverability.evaluation.metrics import (
    flow_metrics,
    level_metrics,
    temperature_metrics,
)

SCIENTIFIC_GROUP_COLUMNS = (
    "scenario_id",
    "training_seed",
    "mask_seed",
    "experiment",
    "mask_type",
    "layout",
    "outage_mode",
    "overlap_ratio",
    "window_length",
    "training_protocol",
    "fit_split",
    "tuning_split",
    "evaluation_split",
    "validation_scope",
    "is_external_validation",
    "external_validation_status",
    "station_id",
    "target",
    "model",
    "variable_pattern",
    "pattern",
    "gap_length",
    "missing_rate",
    "event_type",
    "information_combination",
    "component_estimator",
)


def _ordered_valid_series(
    values: Sequence[float] | np.ndarray | pd.Series,
    times: Sequence[object] | np.ndarray | pd.Series | None,
) -> tuple[np.ndarray, np.ndarray]:
    y = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    if times is None:
        x = np.arange(len(y), dtype=float)
    else:
        parsed = pd.Series(times)
        if len(parsed) != len(y):
            raise ValueError("times and values must align")
        if pd.api.types.is_datetime64_any_dtype(
            parsed
        ) or not pd.api.types.is_numeric_dtype(parsed):
            converted = pd.to_datetime(parsed, errors="coerce")
            origin = converted.min()
            x = (converted - origin).dt.total_seconds().to_numpy(dtype=float) / 86400.0
        else:
            x = pd.to_numeric(parsed, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    order = np.argsort(x, kind="stable")
    return x[order], y[order]


def mann_kendall_test(
    values: Sequence[float] | np.ndarray | pd.Series,
    *,
    times: Sequence[object] | np.ndarray | pd.Series | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Mann-Kendall S, tie-corrected variance, z, p, and trend direction."""

    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    _, y = _ordered_valid_series(values, times)
    n = len(y)
    if n < 3:
        return {
            "n": n,
            "s": np.nan,
            "variance_s": np.nan,
            "z": np.nan,
            "p_value": np.nan,
            "tau": np.nan,
            "direction": None,
            "significant_trend": None,
            "reason": "at least three finite observations are required",
        }

    unique = np.unique(y)
    ranks = np.searchsorted(unique, y) + 1
    tree = np.zeros(len(unique) + 1, dtype=int)

    def query(position: int) -> int:
        total = 0
        while position > 0:
            total += int(tree[position])
            position -= position & -position
        return total

    def update(position: int) -> None:
        while position < len(tree):
            tree[position] += 1
            position += position & -position

    score = 0
    for index, rank in enumerate(ranks):
        less = query(int(rank) - 1)
        less_or_equal = query(int(rank))
        greater = index - less_or_equal
        score += less - greater
        update(int(rank))

    ties = Counter(y.tolist())
    tie_term = sum(count * (count - 1) * (2 * count + 5) for count in ties.values())
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if variance <= 0:
        z_score = p_value = np.nan
        reason = "trend variance is zero"
    else:
        if score > 0:
            z_score = (score - 1) / np.sqrt(variance)
        elif score < 0:
            z_score = (score + 1) / np.sqrt(variance)
        else:
            z_score = 0.0
        p_value = float(2.0 * norm.sf(abs(z_score)))
        reason = None
    direction = (
        "increasing" if score > 0 else "decreasing" if score < 0 else "no_change"
    )
    significant = (
        direction
        if np.isfinite(p_value) and p_value < alpha
        else "no_significant_trend"
    )
    return {
        "n": int(n),
        "s": int(score),
        "variance_s": float(variance),
        "z": float(z_score),
        "p_value": float(p_value),
        "tau": float(score / (0.5 * n * (n - 1))),
        "direction": direction,
        "significant_trend": significant,
        "reason": reason,
    }


def sen_slope(
    values: Sequence[float] | np.ndarray | pd.Series,
    *,
    times: Sequence[object] | np.ndarray | pd.Series | None = None,
    max_pairs: int = 2_000_000,
    seed: int = 0,
) -> dict[str, Any]:
    """Exact Sen slope when feasible, otherwise a declared sampled-pair estimate."""

    if max_pairs < 1:
        raise ValueError("max_pairs must be positive")
    x, y = _ordered_valid_series(values, times)
    n = len(y)
    if n < 2:
        return {
            "slope": np.nan,
            "intercept": np.nan,
            "n": n,
            "pairs_used": 0,
            "total_pairs": 0,
            "method": None,
            "reason": "at least two finite observations are required",
        }
    total_pairs = n * (n - 1) // 2
    if total_pairs <= max_pairs:
        pieces = []
        for index in range(n - 1):
            delta_x = x[index + 1 :] - x[index]
            nonzero = delta_x != 0
            pieces.append((y[index + 1 :][nonzero] - y[index]) / delta_x[nonzero])
        slopes = np.concatenate(pieces) if pieces else np.empty(0)
        method = "exact_all_pairs"
    else:
        rng = np.random.default_rng(seed)
        first: list[np.ndarray] = []
        second: list[np.ndarray] = []
        remaining = max_pairs
        while remaining > 0:
            draw_size = min(max(remaining * 2, 1000), max_pairs * 2)
            left = rng.integers(0, n, size=draw_size)
            right = rng.integers(0, n, size=draw_size)
            valid = left != right
            lo = np.minimum(left[valid], right[valid])[:remaining]
            hi = np.maximum(left[valid], right[valid])[:remaining]
            first.append(lo)
            second.append(hi)
            remaining -= len(lo)
        lo = np.concatenate(first)
        hi = np.concatenate(second)
        delta_x = x[hi] - x[lo]
        nonzero = delta_x != 0
        slopes = (y[hi][nonzero] - y[lo][nonzero]) / delta_x[nonzero]
        method = "uniform_sampled_pairs"
    if not len(slopes):
        return {
            "slope": np.nan,
            "intercept": np.nan,
            "n": n,
            "pairs_used": 0,
            "total_pairs": int(total_pairs),
            "method": method,
            "reason": "all time differences are zero",
        }
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * x))
    return {
        "slope": slope,
        "intercept": intercept,
        "n": int(n),
        "pairs_used": len(slopes),
        "total_pairs": int(total_pairs),
        "method": method,
        "reason": None,
    }


def trend_preservation(
    y_true: Sequence[float] | np.ndarray | pd.Series,
    y_pred: Sequence[float] | np.ndarray | pd.Series,
    *,
    dates: Sequence[object] | np.ndarray | pd.Series | None = None,
    quality_approved: Sequence[bool] | np.ndarray | pd.Series | None = None,
    artificial_mask: Sequence[bool] | np.ndarray | pd.Series | None = None,
    max_sen_pairs: int = 2_000_000,
    seed: int = 0,
) -> dict[str, Any]:
    """Compare Mann-Kendall direction/significance and Sen slopes."""

    truth = pd.to_numeric(pd.Series(y_true), errors="coerce")
    prediction = pd.to_numeric(pd.Series(y_pred), errors="coerce")
    if len(truth) != len(prediction):
        raise ValueError("truth and prediction must align")
    selected = truth.notna() & prediction.notna()
    if quality_approved is not None:
        selected &= pd.Series(quality_approved).fillna(False).astype(bool)
    if artificial_mask is not None:
        selected &= pd.Series(artificial_mask).fillna(False).astype(bool)
    selected_dates = pd.Series(dates).loc[selected] if dates is not None else None
    true_values = truth.loc[selected]
    predicted_values = prediction.loc[selected]
    true_mk = mann_kendall_test(true_values, times=selected_dates)
    predicted_mk = mann_kendall_test(predicted_values, times=selected_dates)
    true_sen = sen_slope(
        true_values, times=selected_dates, max_pairs=max_sen_pairs, seed=seed
    )
    predicted_sen = sen_slope(
        predicted_values,
        times=selected_dates,
        max_pairs=max_sen_pairs,
        seed=seed + 1,
    )
    return {
        "n_trend": int(selected.sum()),
        "true_mk_tau": true_mk["tau"],
        "pred_mk_tau": predicted_mk["tau"],
        "mk_tau_error": (
            predicted_mk["tau"] - true_mk["tau"]
            if np.isfinite(predicted_mk["tau"]) and np.isfinite(true_mk["tau"])
            else np.nan
        ),
        "true_mk_p": true_mk["p_value"],
        "pred_mk_p": predicted_mk["p_value"],
        "trend_direction_match": (
            true_mk["direction"] == predicted_mk["direction"]
            if true_mk["direction"] is not None
            and predicted_mk["direction"] is not None
            else None
        ),
        "trend_significance_match": (
            true_mk["significant_trend"] == predicted_mk["significant_trend"]
            if true_mk["significant_trend"] is not None
            and predicted_mk["significant_trend"] is not None
            else None
        ),
        "true_sen_slope": true_sen["slope"],
        "pred_sen_slope": predicted_sen["slope"],
        "sen_slope_error": (
            predicted_sen["slope"] - true_sen["slope"]
            if np.isfinite(predicted_sen["slope"]) and np.isfinite(true_sen["slope"])
            else np.nan
        ),
        "true_sen_method": true_sen["method"],
        "pred_sen_method": predicted_sen["method"],
        "reason": true_mk["reason"]
        or predicted_mk["reason"]
        or true_sen["reason"]
        or predicted_sen["reason"],
    }


def _local_slope_summary(
    group: pd.DataFrame,
    *,
    truth_col: str,
    prediction_col: str,
    quality_col: str,
    artificial_col: str,
    date_col: str,
    max_sen_pairs: int,
    seed: int,
) -> dict[str, Any]:
    truth = pd.to_numeric(group[truth_col], errors="coerce")
    prediction = pd.to_numeric(group[prediction_col], errors="coerce")
    selected = (
        group[quality_col].fillna(False).astype(bool)
        & group[artificial_col].fillna(False).astype(bool)
        & truth.notna()
        & prediction.notna()
    )
    dates = group.loc[selected, date_col]
    true_sen = sen_slope(
        truth.loc[selected], times=dates, max_pairs=max_sen_pairs, seed=seed
    )
    pred_sen = sen_slope(
        prediction.loc[selected],
        times=dates,
        max_pairs=max_sen_pairs,
        seed=seed + 1,
    )

    def shape(slope: float) -> str | None:
        if not np.isfinite(slope):
            return None
        if slope > 0:
            return "increasing"
        if slope < 0:
            return "decreasing"
        return "flat"

    true_shape = shape(true_sen["slope"])
    pred_shape = shape(pred_sen["slope"])
    return {
        "n_local_slope": int(selected.sum()),
        "local_true_sen_slope": true_sen["slope"],
        "local_pred_sen_slope": pred_sen["slope"],
        "local_sen_slope_error": (
            pred_sen["slope"] - true_sen["slope"]
            if np.isfinite(pred_sen["slope"]) and np.isfinite(true_sen["slope"])
            else np.nan
        ),
        "local_true_shape": true_shape,
        "local_pred_shape": pred_shape,
        "local_shape_match": (
            true_shape == pred_shape
            if true_shape is not None and pred_shape is not None
            else None
        ),
        "local_true_sen_method": true_sen["method"],
        "local_pred_sen_method": pred_sen["method"],
        "local_reason": true_sen["reason"] or pred_sen["reason"],
    }


def _unavailable_long_term(reason: str) -> dict[str, Any]:
    return {
        "n_trend": 0,
        "true_mk_tau": np.nan,
        "pred_mk_tau": np.nan,
        "mk_tau_error": np.nan,
        "true_mk_p": np.nan,
        "pred_mk_p": np.nan,
        "trend_direction_match": None,
        "trend_significance_match": None,
        "true_sen_slope": np.nan,
        "pred_sen_slope": np.nan,
        "sen_slope_error": np.nan,
        "true_sen_method": None,
        "pred_sen_method": None,
        "reason": reason,
    }


def _complete_test_reconstruction(
    group: pd.DataFrame,
    *,
    truth_col: str,
    prediction_col: str,
    quality_col: str,
    artificial_col: str,
    date_col: str,
    complete_period_col: str,
) -> tuple[pd.Series | None, str | None]:
    if complete_period_col not in group:
        return None, f"missing {complete_period_col!r} completeness declaration"
    declared = group[complete_period_col].fillna(False).astype(bool)
    if not declared.all():
        return None, "test-period coverage is not declared complete"
    if (
        "evaluation_split" in group
        and not group["evaluation_split"].astype(str).eq("test").all()
    ):
        return None, "rows do not all belong to the test split"

    dates = pd.to_datetime(group[date_col], errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        return None, "complete reconstruction requires unique finite daily dates"
    ordered_dates = dates.sort_values()
    if (
        len(ordered_dates) > 1
        and not ordered_dates.diff().dropna().eq(pd.Timedelta(days=1)).all()
    ):
        return None, "complete reconstruction requires an unbroken daily test axis"

    artificial = group[artificial_col].fillna(False).astype(bool)
    if not artificial.any() or artificial.all():
        return (
            None,
            "complete reconstruction requires both observed and predicted test cells",
        )
    quality = group[quality_col].fillna(False).astype(bool)
    truth = pd.to_numeric(group[truth_col], errors="coerce")
    prediction = pd.to_numeric(group[prediction_col], errors="coerce")
    if (quality & truth.isna()).any():
        return None, "approved test truth is incomplete"
    if (quality & artificial & prediction.isna()).any():
        return None, "approved artificial test predictions are incomplete"
    reconstructed = truth.copy()
    reconstructed.loc[artificial] = prediction.loc[artificial]
    if int((quality & truth.notna() & reconstructed.notna()).sum()) < 3:
        return None, "fewer than three reconstructed test observations are available"
    return reconstructed, None


def scientific_metrics_by_event(
    daily_predictions: pd.DataFrame,
    *,
    group_cols: Sequence[str] = SCIENTIFIC_GROUP_COLUMNS,
    truth_col: str = "y_true",
    prediction_col: str = "y_pred",
    quality_col: str = "quality_approved",
    artificial_col: str = "artificial_mask",
    date_col: str = "date",
    high_threshold_col: str = "high_threshold",
    low_threshold_col: str = "low_threshold",
    complete_period_col: str = "test_period_complete",
    max_sen_pairs: int = 2_000_000,
    seed: int = 0,
) -> pd.DataFrame:
    """Evaluate T/F/L extremes, thresholds, water balance, and trend preservation."""

    required = {
        truth_col,
        prediction_col,
        quality_col,
        artificial_col,
        date_col,
        "target",
    }
    missing = sorted(required - set(daily_predictions.columns))
    if missing:
        raise ValueError(f"scientific metrics require columns: {missing}")
    active_groups = [column for column in group_cols if column in daily_predictions]
    grouped = (
        daily_predictions.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), daily_predictions)]
    )
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        group = group.sort_values(date_col)
        target = str(group["target"].iloc[0]).split("_")[-1].upper()
        high_values = (
            pd.to_numeric(group[high_threshold_col], errors="coerce")
            if high_threshold_col in group
            else pd.Series(dtype=float)
        )
        high_values = high_values.loc[np.isfinite(high_values)]
        high_threshold = float(high_values.iloc[0]) if len(high_values) else None
        low_values = (
            pd.to_numeric(group[low_threshold_col], errors="coerce")
            if low_threshold_col in group
            else pd.Series(dtype=float)
        )
        low_values = low_values.loc[np.isfinite(low_values)]
        low_threshold = float(low_values.iloc[0]) if len(low_values) else None
        threshold_reasons: list[str] = []
        common = {
            "dates": group[date_col],
            "climatology_pred": group.get("climatology_pred", None),
        }
        if target == "T":
            metrics = temperature_metrics(
                group[truth_col],
                group[prediction_col],
                group[quality_col],
                group[artificial_col],
                high_threshold=(
                    high_threshold if high_threshold is not None else np.nan
                ),
                **common,
            )
            keep = {
                key: metrics.get(key)
                for key in (
                    "high_temp_threshold",
                    "high_temp_n",
                    "high_temp_mae",
                    "high_temp_bias",
                    "extreme_peak_error",
                    "threshold_days_bias",
                    "heatwave_duration_error",
                    "daily_change_mae",
                    "annual_max_error",
                    "annual_peak_timing_error_days",
                )
            }
            if high_threshold is None:
                threshold_reasons.append("missing training-derived high_threshold")
                for key in (
                    "high_temp_threshold",
                    "high_temp_n",
                    "high_temp_mae",
                    "high_temp_bias",
                    "extreme_peak_error",
                    "threshold_days_bias",
                    "heatwave_duration_error",
                ):
                    keep[key] = np.nan
        elif target == "F":
            metrics = flow_metrics(
                group[truth_col],
                group[prediction_col],
                group[quality_col],
                group[artificial_col],
                high_threshold=(
                    high_threshold if high_threshold is not None else np.nan
                ),
                low_threshold=(low_threshold if low_threshold is not None else np.nan),
                **common,
            )
            keep = {
                key: metrics.get(key)
                for key in (
                    "volume_bias",
                    "volume_bias_percent",
                    "pbias",
                    "nse",
                    "kge",
                    "high_flow_mae",
                    "low_flow_mae",
                    "peak_magnitude_error",
                    "peak_timing_error_days",
                )
            }
            if high_threshold is None:
                threshold_reasons.append("missing training-derived high_threshold")
                keep["high_flow_mae"] = np.nan
            if low_threshold is None:
                threshold_reasons.append("missing training-derived low_threshold")
                keep["low_flow_mae"] = np.nan
        elif target == "L":
            metrics = level_metrics(
                group[truth_col],
                group[prediction_col],
                group[quality_col],
                group[artificial_col],
                high_threshold=(
                    high_threshold if high_threshold is not None else np.nan
                ),
                **common,
            )
            keep = {
                key: metrics.get(key)
                for key in (
                    "high_level_mae",
                    "high_level_duration_bias",
                    "peak_level_error",
                    "peak_timing_error_days",
                )
            }
            if high_threshold is None:
                threshold_reasons.append("missing training-derived high_threshold")
                keep["high_level_mae"] = np.nan
                keep["high_level_duration_bias"] = np.nan
        else:
            keep = {}
        local = _local_slope_summary(
            group,
            truth_col=truth_col,
            prediction_col=prediction_col,
            quality_col=quality_col,
            artificial_col=artificial_col,
            date_col=date_col,
            max_sen_pairs=max_sen_pairs,
            seed=seed,
        )
        reconstructed, reconstruction_reason = _complete_test_reconstruction(
            group,
            truth_col=truth_col,
            prediction_col=prediction_col,
            quality_col=quality_col,
            artificial_col=artificial_col,
            date_col=date_col,
            complete_period_col=complete_period_col,
        )
        sequence_metric_reason: str | None = None
        if target == "T":
            sequence_keys = (
                "heatwave_duration_error",
                "daily_change_mae",
                "annual_max_error",
                "annual_peak_timing_error_days",
            )
            if reconstructed is None:
                for key in sequence_keys:
                    keep[key] = np.nan
                sequence_metric_reason = (
                    "complete test reconstruction unavailable: "
                    f"{reconstruction_reason}"
                )
            else:
                complete_metrics = temperature_metrics(
                    group[truth_col],
                    reconstructed,
                    group[quality_col],
                    group[artificial_col],
                    high_threshold=(
                        high_threshold if high_threshold is not None else np.nan
                    ),
                    ecological_threshold=None,
                    dates=group[date_col],
                )
                for key in sequence_keys:
                    keep[key] = complete_metrics[key]
        if reconstructed is not None:
            trends = trend_preservation(
                group[truth_col],
                reconstructed,
                dates=group[date_col],
                quality_approved=group[quality_col],
                max_sen_pairs=max_sen_pairs,
                seed=seed,
            )
            long_term_available = trends["reason"] is None
            trend_scope = "complete_test_period_reconstruction"
            trend_reason = trends["reason"]
        else:
            trend_reason = (
                "long-term trend unavailable: "
                f"{reconstruction_reason}; reporting masked-period local slopes only"
            )
            trends = _unavailable_long_term(trend_reason)
            long_term_available = False
            trend_scope = "masked_period_local_shape_only"
        rows.append(
            {
                **metadata,
                **keep,
                **trends,
                **local,
                "trend_scope": trend_scope,
                "long_term_trend_available": bool(long_term_available),
                "trend_reason": trend_reason,
                "high_threshold_source": high_threshold_col
                if high_threshold is not None
                else None,
                "low_threshold_source": low_threshold_col
                if low_threshold is not None
                else None,
                "ecological_threshold_source": None,
                "ecological_threshold_reason": (
                    "no predeclared ecological threshold"
                    if target == "T"
                    else None
                ),
                "threshold_reason": "; ".join(threshold_reasons)
                if threshold_reasons
                else None,
                "sequence_metric_reason": sequence_metric_reason,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "SCIENTIFIC_GROUP_COLUMNS",
    "mann_kendall_test",
    "scientific_metrics_by_event",
    "sen_slope",
    "trend_preservation",
]
