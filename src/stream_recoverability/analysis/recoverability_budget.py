"""Train-only analytic recoverability-budget decomposition."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def _temperature_anomalies(
    frame: pd.DataFrame, stations: Sequence[str]
) -> dict[str, np.ndarray]:
    dates = pd.to_datetime(frame["date"])
    calendar_day = dates.dt.strftime("%m-%d")
    anomalies: dict[str, np.ndarray] = {}
    for station in stations:
        values = pd.to_numeric(frame[f"{station}_T"], errors="coerce")
        climatology = values.groupby(calendar_day).transform("median")
        anomalies[station] = (values - climatology).to_numpy(dtype=float)
    return anomalies


def _donor_r2(target: np.ndarray, donors: Sequence[np.ndarray]) -> float:
    design = np.column_stack([np.ones(len(target)), *donors])
    valid = np.isfinite(target) & np.isfinite(design).all(axis=1)
    y = target[valid]
    x = design[valid]
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    residual_sum = float(np.square(y - x @ coefficients).sum())
    total_sum = float(np.square(y - y.mean()).sum())
    return float(np.clip(1.0 - residual_sum / total_sum, 0.0, 1.0))


def _autocorrelation(values: np.ndarray, lag: int) -> float:
    left = values[:-lag]
    right = values[lag:]
    valid = np.isfinite(left) & np.isfinite(right)
    return float(np.corrcoef(left[valid], right[valid])[0, 1])


def _rho_at_distance(values: np.ndarray, distance: float) -> tuple[float, float]:
    # One day is the smallest identifiable lag in a daily record. Fractional
    # distances above one day are linearly interpolated between adjacent ACF lags.
    effective = max(1.0, float(distance))
    lower = int(np.floor(effective))
    upper = int(np.ceil(effective))
    lower_rho = _autocorrelation(values, lower)
    if lower == upper:
        return effective, lower_rho
    upper_rho = _autocorrelation(values, upper)
    weight = effective - lower
    return effective, float((1.0 - weight) * lower_rho + weight * upper_rho)


def budget_decomposition(
    train_frame: pd.DataFrame,
    station: str,
    donors: Sequence[str],
    gap_lengths: Sequence[int],
) -> pd.DataFrame:
    """Return the train-only analytic recoverability budget for one station.

    The seasonal cycle is removed with an exact calendar-day training median.
    ``R2_donor`` is the in-sample coefficient of determination for target
    anomalies regressed on simultaneous donor anomalies. For a block of length
    ``d``, local memory is evaluated at the average boundary distance ``d / 4``.
    """

    station_ids = (str(station), *(str(value) for value in donors))
    anomalies = _temperature_anomalies(train_frame, station_ids)
    target = anomalies[str(station)]
    donor_r2 = _donor_r2(target, [anomalies[value] for value in donors])
    raw = pd.to_numeric(train_frame[f"{station}_T"], errors="coerce").to_numpy(
        dtype=float
    )
    seasonal_variance_fraction = 1.0 - float(np.nanvar(target) / np.nanvar(raw))

    rows = []
    for gap in gap_lengths:
        average_distance = float(gap) / 4.0
        effective_lag, rho = _rho_at_distance(target, average_distance)
        memory_component = (1.0 - donor_r2) * rho**2
        available_r2 = float(np.clip(donor_r2 + memory_component, 0.0, 1.0))
        rows.append(
            {
                "station": str(station),
                "donors": ",".join(str(value) for value in donors),
                "gap_length_days": int(gap),
                "average_boundary_distance_days": average_distance,
                "effective_acf_lag_days": effective_lag,
                "seasonal_variance_fraction": seasonal_variance_fraction,
                "anomaly_sd_degC": float(np.nanstd(target, ddof=1)),
                "R2_donor": donor_r2,
                "rho": rho,
                "donor_component": donor_r2,
                "memory_component": memory_component,
                "R2_avail": available_r2,
                "predicted_skill": 1.0 - np.sqrt(1.0 - available_r2),
            }
        )
    return pd.DataFrame(rows)


__all__ = ["budget_decomposition"]
