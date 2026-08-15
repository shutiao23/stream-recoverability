"""Extreme-event preservation and non-parametric trend diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from stream_recoverability.evaluation.metrics import (
    flow_metrics,
    level_metrics,
    temperature_metrics,
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
        if pd.api.types.is_datetime64_any_dtype(parsed) or not pd.api.types.is_numeric_dtype(parsed):
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
    direction = "increasing" if score > 0 else "decreasing" if score < 0 else "no_change"
    significant = direction if np.isfinite(p_value) and p_value < alpha else "no_significant_trend"
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
        "pairs_used": int(len(slopes)),
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
        "trend_direction_match": true_mk["direction"] == predicted_mk["direction"],
        "trend_significance_match": (
            true_mk["significant_trend"] == predicted_mk["significant_trend"]
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
        "reason": true_mk["reason"] or predicted_mk["reason"] or true_sen["reason"] or predicted_sen["reason"],
    }


def scientific_metrics_by_event(
    daily_predictions: pd.DataFrame,
    *,
    group_cols: Sequence[str] = ("scenario_id", "station_id", "target", "model", "mask_seed"),
    truth_col: str = "y_true",
    prediction_col: str = "y_pred",
    quality_col: str = "quality_approved",
    artificial_col: str = "artificial_mask",
    date_col: str = "date",
    high_threshold_col: str = "high_threshold",
    low_threshold_col: str = "low_threshold",
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
    grouped = daily_predictions.groupby(active_groups, dropna=False, observed=True) if active_groups else [((), daily_predictions)]
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key if active_groups else (), strict=True))
        group = group.sort_values(date_col)
        target = str(group["target"].iloc[0]).split("_")[-1].upper()
        high_threshold = (
            float(pd.to_numeric(group[high_threshold_col], errors="coerce").dropna().iloc[0])
            if high_threshold_col in group and pd.to_numeric(group[high_threshold_col], errors="coerce").notna().any()
            else None
        )
        low_threshold = (
            float(pd.to_numeric(group[low_threshold_col], errors="coerce").dropna().iloc[0])
            if low_threshold_col in group and pd.to_numeric(group[low_threshold_col], errors="coerce").notna().any()
            else None
        )
        common = {
            "dates": group[date_col],
            "climatology_pred": group["climatology_pred"] if "climatology_pred" in group else None,
        }
        if target == "T":
            metrics = temperature_metrics(
                group[truth_col],
                group[prediction_col],
                group[quality_col],
                group[artificial_col],
                high_threshold=high_threshold,
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
        elif target == "F":
            metrics = flow_metrics(
                group[truth_col],
                group[prediction_col],
                group[quality_col],
                group[artificial_col],
                high_threshold=high_threshold,
                low_threshold=low_threshold,
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
        elif target == "L":
            metrics = level_metrics(
                group[truth_col],
                group[prediction_col],
                group[quality_col],
                group[artificial_col],
                high_threshold=high_threshold,
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
        else:
            keep = {}
        artificial_values = group[artificial_col].fillna(False).astype(bool)
        quality_values = group[quality_col].fillna(False).astype(bool)
        if ((~artificial_values) & quality_values).any():
            reconstructed = pd.to_numeric(group[truth_col], errors="coerce").copy()
            reconstructed.loc[artificial_values] = pd.to_numeric(
                group.loc[artificial_values, prediction_col], errors="coerce"
            )
            trends = trend_preservation(
                group[truth_col],
                reconstructed,
                dates=group[date_col],
                quality_approved=group[quality_col],
            )
            trend_scope = "provided full reconstruction"
        else:
            trends = trend_preservation(
                group[truth_col],
                group[prediction_col],
                dates=group[date_col],
                quality_approved=group[quality_col],
                artificial_mask=group[artificial_col],
            )
            trend_scope = "artificial cells only; full-series trend unavailable"
        rows.append(
            {
                **metadata,
                **keep,
                **trends,
                "trend_scope": trend_scope,
                "threshold_source": (
                    high_threshold_col if high_threshold is not None else "evaluated-truth 90th percentile"
                ),
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "mann_kendall_test",
    "scientific_metrics_by_event",
    "sen_slope",
    "trend_preservation",
]
