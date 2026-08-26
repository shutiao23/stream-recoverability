"""Thermal-science record metrics that a low MAE can still destroy (E8)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.science_metrics import mann_kendall_test, sen_slope
from stream_recoverability.evaluation.metrics import (
    boundary_jump_metrics,
    temperature_metrics,
)


def _annual(values: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame({"date": dates, "value": values})
    grouped = frame.groupby(frame["date"].dt.year)["value"]
    return pd.DataFrame(
        {
            "year": grouped.mean().index.astype(int),
            "mean": grouped.mean().to_numpy(dtype=float),
            "min": grouped.min().to_numpy(dtype=float),
            "max": grouped.max().to_numpy(dtype=float),
            "amplitude": (grouped.max() - grouped.min()).to_numpy(dtype=float),
            "p90": grouped.quantile(0.90).to_numpy(dtype=float),
            "p95": grouped.quantile(0.95).to_numpy(dtype=float),
        }
    )


def seasonal_phase(values: np.ndarray, dates: pd.DatetimeIndex) -> float:
    """Day of year of the first harmonic maximum; NaN if amplitude is zero."""

    doy = dates.dayofyear.to_numpy(dtype=float)
    angle = 2.0 * np.pi * doy / 365.25
    valid = np.isfinite(values)
    if int(valid.sum()) < 12:
        return float("nan")
    sine = np.sin(angle[valid])
    cosine = np.cos(angle[valid])
    design = np.column_stack([np.ones(int(valid.sum())), sine, cosine])
    coef = np.linalg.lstsq(design, values[valid], rcond=None)[0]
    if coef[1] == 0 and coef[2] == 0:
        return float("nan")
    return float((np.degrees(np.arctan2(coef[1], coef[2])) % 360.0) * 365.25 / 360.0)


def science_record_metrics(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    quality_approved: Sequence[bool],
    artificial_mask: Sequence[bool],
    *,
    dates: Sequence[object],
    climatology_pred: Sequence[float] | None = None,
    high_threshold: float | None = None,
    ecological_threshold: float | None = None,
) -> dict[str, Any]:
    """MAE plus annual, percentile, heatwave, trend, and boundary metrics."""

    truth = np.asarray(pd.to_numeric(pd.Series(y_true), errors="coerce"), dtype=float)
    prediction = np.asarray(
        pd.to_numeric(pd.Series(y_pred), errors="coerce"), dtype=float
    )
    parsed = pd.DatetimeIndex(pd.to_datetime(dates))
    if len(parsed) != len(truth):
        raise ValueError("dates must align with y_true")
    reconstructed = truth.copy()
    mask = np.asarray(artificial_mask, dtype=bool)
    reconstructed[mask] = prediction[mask]
    result = dict(
        temperature_metrics(
            truth,
            prediction,
            quality_approved,
            artificial_mask,
            climatology_pred=climatology_pred,
            high_threshold=high_threshold,
            ecological_threshold=ecological_threshold,
            dates=parsed,
        )
    )
    result.update(
        boundary_jump_metrics(truth, prediction, quality_approved, artificial_mask)
    )
    true_annual = _annual(truth, parsed)
    pred_annual = _annual(reconstructed, parsed)
    result["annual_mean_mae"] = float(
        np.mean(np.abs(pred_annual["mean"] - true_annual["mean"]))
    )
    result["annual_amplitude_mae"] = float(
        np.mean(np.abs(pred_annual["amplitude"] - true_annual["amplitude"]))
    )
    result["annual_min_mae"] = float(
        np.mean(np.abs(pred_annual["min"] - true_annual["min"]))
    )
    result["annual_max_mae"] = float(
        np.mean(np.abs(pred_annual["max"] - true_annual["max"]))
    )
    result["p90_mae"] = float(np.mean(np.abs(pred_annual["p90"] - true_annual["p90"])))
    result["p95_mae"] = float(np.mean(np.abs(pred_annual["p95"] - true_annual["p95"])))
    result["seasonal_phase_true"] = seasonal_phase(truth, parsed)
    result["seasonal_phase_pred"] = seasonal_phase(reconstructed, parsed)
    result["seasonal_phase_error_days"] = (
        result["seasonal_phase_pred"] - result["seasonal_phase_true"]
    )
    true_trend = mann_kendall_test(true_annual["mean"], times=true_annual["year"])
    pred_trend = mann_kendall_test(pred_annual["mean"], times=pred_annual["year"])
    result["trend_direction_true"] = true_trend["direction"]
    result["trend_direction_pred"] = pred_trend["direction"]
    result["trend_direction_match"] = (
        true_trend["direction"] == pred_trend["direction"]
        if true_trend["direction"] is not None
        else None
    )
    true_sen = sen_slope(true_annual["mean"], times=true_annual["year"])
    pred_sen = sen_slope(pred_annual["mean"], times=pred_annual["year"])
    result["sen_slope_error"] = float(pred_sen["slope"] - true_sen["slope"])
    return result


__all__ = ["science_record_metrics", "seasonal_phase"]
