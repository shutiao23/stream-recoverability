"""Prediction-interval coverage, width, and calibration by gap length."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def interval_calibration_by_gap(
    daily_predictions: pd.DataFrame,
    *,
    truth_col: str = "y_true",
    lower_col: str = "q05",
    upper_col: str = "q95",
    quality_col: str = "quality_approved",
    artificial_col: str = "artificial_mask",
    gap_col: str = "gap_length",
    nominal_coverage: float = 0.90,
    group_cols: Sequence[str] = ("model", "station_id", "target", "gap_length"),
) -> pd.DataFrame:
    """Calculate q05/q95 calibration strictly on approved artificial cells."""

    required = {
        truth_col,
        lower_col,
        upper_col,
        quality_col,
        artificial_col,
        gap_col,
    }
    missing = sorted(required - set(daily_predictions.columns))
    if missing:
        raise ValueError(f"interval calibration requires columns: {missing}")
    if not 0 < nominal_coverage < 1:
        raise ValueError("nominal_coverage must be between zero and one")
    data = daily_predictions.copy()
    for column in (truth_col, lower_col, upper_col, gap_col):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    quality = data[quality_col].fillna(False).astype(bool)
    artificial = data[artificial_col].fillna(False).astype(bool)
    valid = (
        quality
        & artificial
        & data[[truth_col, lower_col, upper_col, gap_col]].notna().all(axis=1)
    )
    data = data.loc[valid].copy()
    active_groups = [column for column in group_cols if column in data]
    if gap_col not in active_groups:
        active_groups.append(gap_col)
    grouped = data.groupby(active_groups, dropna=False, observed=True)
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key, strict=True))
        truth = group[truth_col].to_numpy(dtype=float)
        lower = group[lower_col].to_numpy(dtype=float)
        upper = group[upper_col].to_numpy(dtype=float)
        crossing = lower > upper
        covered = (truth >= lower) & (truth <= upper)
        coverage = float(np.mean(covered)) if len(group) else np.nan
        width = upper - lower
        rows.append(
            {
                **metadata,
                "nominal_coverage": float(nominal_coverage),
                "empirical_coverage": coverage,
                "calibration_error": coverage - nominal_coverage,
                "absolute_calibration_error": abs(coverage - nominal_coverage),
                "mean_interval_width": float(np.mean(width)),
                "median_interval_width": float(np.median(width)),
                "quantile_crossing_rate": float(np.mean(crossing)),
                "n": int(len(group)),
                "reason": None,
            }
        )
    return pd.DataFrame(rows)


def uncertainty_growth(
    calibration: pd.DataFrame,
    *,
    gap_col: str = "gap_length",
    width_col: str = "mean_interval_width",
    group_cols: Sequence[str] = ("model", "station_id", "target"),
) -> pd.DataFrame:
    """Diagnose whether interval width increases with gap length."""

    missing = sorted({gap_col, width_col} - set(calibration.columns))
    if missing:
        raise ValueError(f"uncertainty-growth analysis requires columns: {missing}")
    active_groups = [column for column in group_cols if column in calibration]
    grouped = calibration.groupby(active_groups, dropna=False, observed=True) if active_groups else [((), calibration)]
    rows = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key if active_groups else (), strict=True))
        finite = group[[gap_col, width_col]].dropna()
        if len(finite) < 3 or finite[gap_col].nunique() < 2:
            correlation = p_value = np.nan
            reason = "at least three rows and two gap lengths are required"
        else:
            result = spearmanr(finite[gap_col], finite[width_col])
            correlation, p_value = float(result.statistic), float(result.pvalue)
            reason = None
        rows.append(
            {
                **metadata,
                "gap_width_spearman": correlation,
                "p_value": p_value,
                "n_gap_rows": int(len(finite)),
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def overall_calibration(
    calibration: pd.DataFrame,
    *,
    group_cols: Sequence[str] = ("model", "target"),
) -> pd.DataFrame:
    """Pool already aggregated gap rows using their evaluated-cell counts."""

    required = {"empirical_coverage", "mean_interval_width", "n", "nominal_coverage"}
    missing = sorted(required - set(calibration.columns))
    if missing:
        raise ValueError(f"overall calibration requires columns: {missing}")
    active_groups = [column for column in group_cols if column in calibration]
    grouped = calibration.groupby(active_groups, dropna=False, observed=True) if active_groups else [((), calibration)]
    rows = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_groups, group_key if active_groups else (), strict=True))
        weights = pd.to_numeric(group["n"], errors="coerce").fillna(0).to_numpy(dtype=float)
        if weights.sum() <= 0:
            rows.append({**metadata, "coverage": np.nan, "width": np.nan, "n": 0, "reason": "no evaluated cells"})
            continue
        coverage = float(np.average(group["empirical_coverage"], weights=weights))
        nominal = float(np.average(group["nominal_coverage"], weights=weights))
        rows.append(
            {
                **metadata,
                "coverage": coverage,
                "nominal_coverage": nominal,
                "calibration_error": coverage - nominal,
                "width": float(np.average(group["mean_interval_width"], weights=weights)),
                "n": int(weights.sum()),
                "reason": None,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "interval_calibration_by_gap",
    "overall_calibration",
    "uncertainty_growth",
]
