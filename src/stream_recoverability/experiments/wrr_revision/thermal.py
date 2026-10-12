"""Thermal-regime losses and incremental benefit for the WRR revision."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.paths import (
    EXCEEDANCE_THRESHOLD_C,
    HOTTEST_WINDOW_DAYS,
    JJA_MONTHS,
    WARM_SEASON_MONTHS,
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


def calendar_year_index(year: int) -> pd.DatetimeIndex:
    """Every calendar day of ``year``, including 29 February in leap years."""

    return pd.date_range(f"{int(year)}-01-01", f"{int(year)}-12-31", freq="D")


def reindex_calendar_year(values: pd.Series | np.ndarray, year: int) -> pd.Series:
    """Place observations onto the full calendar year. Missing days stay NA."""

    index = calendar_year_index(year)
    series = _as_series(values)
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("values must be indexed by dates to score a calendar year")
    return series.reindex(index)


def calendar_year_is_complete(values: pd.Series | np.ndarray, year: int) -> bool:
    return bool(reindex_calendar_year(values, year).notna().all())


def month_block_is_complete(
    values: pd.Series | np.ndarray,
    year: int,
    months: tuple[int, ...] = WARM_SEASON_MONTHS,
) -> bool:
    series = reindex_calendar_year(values, year)
    block = series.loc[series.index.month.isin(months)]
    return bool(len(block) > 0 and block.notna().all())


def hottest_consecutive_mean(
    values: pd.Series | np.ndarray,
    *,
    index: pd.Index | None = None,
    window: int = HOTTEST_WINDOW_DAYS,
) -> float:
    """Maximum of the fully observed ``window``-day rolling mean.

    This returns a number whenever any complete window exists. It is **not**
    an annual thermal peak if the calendar year has unobserved days. Use
    ``annual_hottest_consecutive_mean`` for complete-year truth.
    """

    series = _as_series(values, index)
    if window < 1:
        raise ValueError("window must be positive")
    rolled = series.rolling(int(window), min_periods=int(window)).mean()
    finite = rolled.to_numpy(dtype=float)
    if not np.isfinite(finite).any():
        return float("nan")
    return float(np.nanmax(finite))


def annual_hottest_consecutive_mean(
    values: pd.Series | np.ndarray,
    year: int,
    *,
    window: int = HOTTEST_WINDOW_DAYS,
) -> float:
    """Hottest consecutive ``window``-day mean on a fully observed calendar year.

    Returns NaN when any calendar day is missing. Reference series are never
    imputed to manufacture this endpoint.
    """

    series = reindex_calendar_year(values, year)
    if not bool(series.notna().all()):
        return float("nan")
    return hottest_consecutive_mean(series, window=window)


def seasonal_hottest_consecutive_mean(
    values: pd.Series | np.ndarray,
    year: int,
    *,
    months: tuple[int, ...] = WARM_SEASON_MONTHS,
    window: int = HOTTEST_WINDOW_DAYS,
) -> float:
    """Hottest consecutive window inside a fully observed month block.

    The block itself must have no missing days. This is a defined warm-season
    endpoint, not a substitute for an incomplete annual peak.
    """

    series = reindex_calendar_year(values, year)
    block = series.loc[series.index.month.isin(months)]
    if len(block) < int(window) or not bool(block.notna().all()):
        return float("nan")
    return hottest_consecutive_mean(block, window=window)


def annual_exceedance_days(
    values: pd.Series | np.ndarray,
    year: int,
    *,
    threshold_c: float = EXCEEDANCE_THRESHOLD_C,
) -> float:
    """Count of days above threshold on a fully observed calendar year."""

    series = reindex_calendar_year(values, year)
    if not bool(series.notna().all()):
        return float("nan")
    return exceedance_days(series, threshold_c=threshold_c)


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
    jja = present.loc[present.index.month.isin(JJA_MONTHS)]
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
