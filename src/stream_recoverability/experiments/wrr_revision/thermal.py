"""Thermal-regime losses and incremental benefit for the WRR revision."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.paths import (
    EXCEEDANCE_THRESHOLD_C,
    HOTTEST_WINDOW_DAYS,
)

METRIC_NAMES = (
    "mae",
    "hottest_30",
    "exceed_days_20",
    "annual_mean",
    "summer_mean",
    "amplitude",
    "p90",
)


def _as_series(values: pd.Series | np.ndarray, index: pd.Index | None = None) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce")
    if index is None:
        raise ValueError("index is required when values are not a Series")
    return pd.Series(np.asarray(values, dtype=float), index=index)


def hottest_consecutive_mean(
    values: pd.Series | np.ndarray,
    *,
    index: pd.Index | None = None,
    window: int = HOTTEST_WINDOW_DAYS,
) -> float:
    """Maximum of the fully observed ``window``-day rolling mean."""

    series = _as_series(values, index)
    if window < 1:
        raise ValueError("window must be positive")
    rolled = series.rolling(int(window), min_periods=int(window)).mean()
    finite = rolled.to_numpy(dtype=float)
    if not np.isfinite(finite).any():
        return float("nan")
    return float(np.nanmax(finite))


def exceedance_days(
    values: pd.Series | np.ndarray,
    *,
    index: pd.Index | None = None,
    threshold_c: float = EXCEEDANCE_THRESHOLD_C,
) -> float:
    series = _as_series(values, index)
    present = np.isfinite(series.to_numpy(dtype=float))
    if not present.any():
        return float("nan")
    return float(np.sum(series.to_numpy(dtype=float)[present] > float(threshold_c)))


def daily_mae(truth: np.ndarray, alternative: np.ndarray) -> float:
    left = np.asarray(truth, dtype=float)
    right = np.asarray(alternative, dtype=float)
    if left.shape != right.shape:
        raise ValueError("truth and alternative must have the same shape")
    ok = np.isfinite(left) & np.isfinite(right)
    if not ok.any():
        return float("nan")
    return float(np.mean(np.abs(left[ok] - right[ok])))


def thermal_metrics(values: pd.Series) -> dict[str, float]:
    """Summarise one completed daily series. MAE is filled by the caller."""

    series = pd.to_numeric(values, errors="coerce")
    present = series.dropna()
    out = {name: float("nan") for name in METRIC_NAMES}
    if present.empty:
        return out
    out["hottest_30"] = hottest_consecutive_mean(series)
    out["exceed_days_20"] = exceedance_days(series)
    out["annual_mean"] = float(present.mean())
    out["p90"] = float(present.quantile(0.9))
    jja = present.loc[present.index.month.isin((6, 7, 8))]
    if len(jja) >= 20:
        out["summer_mean"] = float(jja.mean())
    july = present.loc[present.index.month == 7]
    january = present.loc[present.index.month == 1]
    if len(july) >= 15 and len(january) >= 15:
        out["amplitude"] = float(july.mean() - january.mean())
    return out


def metric_loss(
    truth: Mapping[str, float],
    alternative: Mapping[str, float],
    metric: str,
) -> float:
    left = truth.get(metric, float("nan"))
    right = alternative.get(metric, float("nan"))
    if not np.isfinite(left) or not np.isfinite(right):
        return float("nan")
    return float(abs(float(left) - float(right)))


def benefit(
    default_loss: float,
    alternative_loss: float,
) -> float:
    """B = L(default, truth) - L(alternative, truth). Positive is an improvement."""

    if not np.isfinite(default_loss) or not np.isfinite(alternative_loss):
        return float("nan")
    return float(default_loss) - float(alternative_loss)


def series_losses(
    truth: pd.Series,
    default: pd.Series,
    alternative: pd.Series,
) -> dict[str, float]:
    """Daily MAE plus thermal-regime losses and benefits on one completed series."""

    truth_metrics = thermal_metrics(truth)
    default_metrics = thermal_metrics(default)
    alternative_metrics = thermal_metrics(alternative)
    truth_y = truth.to_numpy(dtype=float)
    result = {
        "mae_default": daily_mae(truth_y, default.to_numpy(dtype=float)),
        "mae_alternative": daily_mae(truth_y, alternative.to_numpy(dtype=float)),
    }
    result["mae_benefit"] = benefit(result["mae_default"], result["mae_alternative"])
    for metric in ("hottest_30", "exceed_days_20", "annual_mean", "summer_mean", "amplitude"):
        default_loss = metric_loss(truth_metrics, default_metrics, metric)
        alt_loss = metric_loss(truth_metrics, alternative_metrics, metric)
        result[f"{metric}_truth"] = float(truth_metrics[metric])
        result[f"{metric}_default"] = float(default_metrics[metric])
        result[f"{metric}_alternative"] = float(alternative_metrics[metric])
        result[f"{metric}_default_loss"] = default_loss
        result[f"{metric}_alternative_loss"] = alt_loss
        result[f"{metric}_benefit"] = benefit(default_loss, alt_loss)
    return result
