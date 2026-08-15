"""Prediction-interval coverage, width, and calibration by gap length."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

UNCERTAINTY_REGIME_COLUMNS = (
    "experiment",
    "mask_type",
    "layout",
    "outage_mode",
    "overlap_ratio",
    "variable_pattern",
    "pattern",
    "station_id",
    "target",
    "model",
    "missing_rate",
    "event_type",
    "window_length",
    "training_protocol",
    "fit_split",
    "tuning_split",
    "evaluation_split",
    "validation_scope",
    "is_external_validation",
    "external_validation_status",
    "information_combination",
    "component_estimator",
    "target_station_id",
    "failed_station_ids",
    "failed_stations",
    "failure_count",
    "network_size",
)
UNCERTAINTY_UNIT_COLUMNS = ("scenario_id", "training_seed", "mask_seed")
UNCERTAINTY_BY_GAP_COLUMNS = (
    *UNCERTAINTY_REGIME_COLUMNS,
    "gap_length",
    *UNCERTAINTY_UNIT_COLUMNS,
)


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
    group_cols: Sequence[str] = UNCERTAINTY_BY_GAP_COLUMNS,
) -> pd.DataFrame:
    """Calculate calibration for each design x scenario x training-seed unit."""

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
                "n": len(group),
                "reason": None,
            }
        )
    return pd.DataFrame(rows)


def uncertainty_growth(
    calibration: pd.DataFrame,
    *,
    gap_col: str = "gap_length",
    width_col: str = "mean_interval_width",
    group_cols: Sequence[str] = UNCERTAINTY_REGIME_COLUMNS,
) -> pd.DataFrame:
    """Diagnose width growth after unit-first aggregation within each regime."""

    missing = sorted({gap_col, width_col} - set(calibration.columns))
    if missing:
        raise ValueError(f"uncertainty-growth analysis requires columns: {missing}")
    active_groups = [column for column in group_cols if column in calibration]
    grouped = (
        calibration.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), calibration)]
    )
    rows = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        finite = group[
            [gap_col, width_col, *(column for column in ("n",) if column in group)]
        ].copy()
        finite[gap_col] = pd.to_numeric(finite[gap_col], errors="coerce")
        finite[width_col] = pd.to_numeric(finite[width_col], errors="coerce")
        finite = finite.dropna(subset=[gap_col, width_col])
        gap_rows: list[dict[str, float]] = []
        for gap, units in finite.groupby(gap_col, sort=True, observed=True):
            if "n" in units:
                weights = (
                    pd.to_numeric(units["n"], errors="coerce")
                    .fillna(0)
                    .to_numpy(dtype=float)
                )
            else:
                weights = np.ones(len(units), dtype=float)
            values = units[width_col].to_numpy(dtype=float)
            usable = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
            width = (
                float(np.average(values[usable], weights=weights[usable]))
                if usable.any()
                else np.nan
            )
            gap_rows.append({gap_col: float(gap), width_col: width})
        gap_curve = pd.DataFrame(gap_rows).dropna()
        if len(gap_curve) < 3:
            correlation = p_value = np.nan
            reason = (
                "at least three distinct gap lengths are required within one regime"
            )
        elif gap_curve[width_col].nunique() < 2:
            correlation = p_value = np.nan
            reason = "interval width is constant across gap lengths"
        else:
            result = spearmanr(gap_curve[gap_col], gap_curve[width_col])
            correlation, p_value = float(result.statistic), float(result.pvalue)
            reason = None
        rows.append(
            {
                **metadata,
                "gap_width_spearman": correlation,
                "p_value": p_value,
                "n_gap_rows": len(gap_curve),
                "n_units": len(finite),
                "aggregation_scope": "scenario/training-seed units within one design regime",
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def overall_calibration(
    calibration: pd.DataFrame,
    *,
    group_cols: Sequence[str] = UNCERTAINTY_REGIME_COLUMNS,
) -> pd.DataFrame:
    """Pool unit-level rows across gaps, never across design regimes."""

    required = {"empirical_coverage", "mean_interval_width", "n", "nominal_coverage"}
    missing = sorted(required - set(calibration.columns))
    if missing:
        raise ValueError(f"overall calibration requires columns: {missing}")
    active_groups = [column for column in group_cols if column in calibration]
    grouped = (
        calibration.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), calibration)]
    )
    rows = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        weights = (
            pd.to_numeric(group["n"], errors="coerce").fillna(0).to_numpy(dtype=float)
        )
        coverage_values = pd.to_numeric(
            group["empirical_coverage"], errors="coerce"
        ).to_numpy(dtype=float)
        width_values = pd.to_numeric(
            group["mean_interval_width"], errors="coerce"
        ).to_numpy(dtype=float)
        nominal_values = pd.to_numeric(
            group["nominal_coverage"], errors="coerce"
        ).to_numpy(dtype=float)
        usable = (
            (weights > 0)
            & np.isfinite(coverage_values)
            & np.isfinite(width_values)
            & np.isfinite(nominal_values)
        )
        if not usable.any():
            rows.append(
                {
                    **metadata,
                    "coverage": np.nan,
                    "width": np.nan,
                    "n": 0,
                    "n_units": 0,
                    "aggregation_scope": "across gap lengths within one design regime",
                    "reason": "no evaluated cells",
                }
            )
            continue
        coverage = float(np.average(coverage_values[usable], weights=weights[usable]))
        nominal = float(np.average(nominal_values[usable], weights=weights[usable]))
        rows.append(
            {
                **metadata,
                "coverage": coverage,
                "nominal_coverage": nominal,
                "calibration_error": coverage - nominal,
                "width": float(
                    np.average(width_values[usable], weights=weights[usable])
                ),
                "n": int(weights[usable].sum()),
                "n_units": int(usable.sum()),
                "aggregation_scope": "across gap lengths within one design regime",
                "reason": None,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "UNCERTAINTY_BY_GAP_COLUMNS",
    "UNCERTAINTY_REGIME_COLUMNS",
    "UNCERTAINTY_UNIT_COLUMNS",
    "interval_calibration_by_gap",
    "overall_calibration",
    "uncertainty_growth",
]
