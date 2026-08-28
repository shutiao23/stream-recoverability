"""Train-only Python implementation of the published air2stream-8 equation.

The state equation and Crank--Nicolson update follow Toffolon and Piccolroaz
(2015) and the authors' air2stream 1.0 source.  Calibration deliberately uses
deterministic bounded least squares instead of the original particle swarm
optimizer, so this is a method-equivalent implementation, not the published
executable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

AIR2STREAM8_LOWER = np.array([-5.0, -5.0, -5.0, -1.0, 0.0, 0.0, 0.0, -1.0])
AIR2STREAM8_UPPER = np.array([15.0, 1.5, 5.0, 1.0, 20.0, 10.0, 1.0, 5.0])


@dataclass(frozen=True)
class Air2StreamFit:
    parameters: np.ndarray
    discharge_reference: float
    training_rmse: float
    n_training_observations: int
    n_function_evaluations: int
    optimizer_status: int


def annual_phase(index: pd.DatetimeIndex) -> np.ndarray:
    """Return the original model's within-year time coordinate in [0, 1]."""

    days = np.where(index.is_leap_year, 366.0, 365.0)
    return index.dayofyear.to_numpy(dtype=float) / days


def _validate_forcing(air: np.ndarray, discharge: np.ndarray) -> None:
    if air.ndim != 1 or discharge.ndim != 1 or air.shape != discharge.shape:
        raise ValueError("air temperature and discharge must be aligned vectors")
    if len(air) < 2 or not np.isfinite(air).all() or not np.isfinite(discharge).all():
        raise ValueError("air2stream forcing must be complete and finite")
    if np.any(discharge <= 0.0):
        raise ValueError("air2stream-8 requires strictly positive discharge")


def simulate_air2stream8(
    index: pd.DatetimeIndex,
    air_temperature_c: np.ndarray,
    discharge_m3s: np.ndarray,
    parameters: np.ndarray,
    *,
    initial_water_temperature_c: float,
    discharge_reference: float,
    ice_floor_c: float = 0.0,
) -> np.ndarray:
    """Integrate the 8-parameter equation with its Crank--Nicolson update."""

    air = np.asarray(air_temperature_c, dtype=float)
    discharge = np.asarray(discharge_m3s, dtype=float)
    par = np.asarray(parameters, dtype=float)
    _validate_forcing(air, discharge)
    if par.shape != (8,) or not np.isfinite(par).all():
        raise ValueError("air2stream-8 requires eight finite parameters")
    if not np.isfinite(discharge_reference) or discharge_reference <= 0.0:
        raise ValueError("discharge reference must be finite and positive")
    if not np.isfinite(initial_water_temperature_c):
        raise ValueError("initial water temperature must be finite")
    if len(index) != len(air):
        raise ValueError("forcing length differs from date index")

    phase = annual_phase(index)
    result = np.empty(len(index), dtype=float)
    result[0] = max(float(initial_water_temperature_c), float(ice_floor_c))
    theta = discharge / float(discharge_reference)
    depth = np.power(theta, par[3])
    if not np.isfinite(depth).all() or np.any(depth <= 0.0):
        raise ValueError("invalid flow-depth scaling")
    for day in range(len(index) - 1):
        theta_0, theta_1 = theta[day], theta[day + 1]
        depth_0, depth_1 = depth[day], depth[day + 1]
        seasonal_0 = np.cos(2.0 * np.pi * (phase[day] - par[6]))
        seasonal_1 = np.cos(2.0 * np.pi * (phase[day + 1] - par[6]))
        current = result[day]
        explicit = (
            par[0]
            + par[1] * air[day]
            - par[2] * current
            + theta_0 * (par[4] + par[5] * seasonal_0 - par[7] * current)
        )
        implicit_numerator = (
            par[0]
            + par[1] * air[day + 1]
            + theta_1 * (par[4] + par[5] * seasonal_1)
        )
        denominator = 1.0 + 0.5 * par[7] * theta_1 / depth_1 + 0.5 * par[2] / depth_1
        if not np.isfinite(denominator) or abs(denominator) < 1e-8:
            raise ValueError("unstable Crank--Nicolson denominator")
        predicted = (
            current + 0.5 * explicit / depth_0 + 0.5 * implicit_numerator / depth_1
        ) / denominator
        if not np.isfinite(predicted) or abs(predicted) > 1000.0:
            raise ValueError("unstable air2stream trajectory")
        result[day + 1] = max(float(predicted), float(ice_floor_c))
    return result


def fit_air2stream8(
    index: pd.DatetimeIndex,
    water_temperature_c: np.ndarray,
    air_temperature_c: np.ndarray,
    discharge_m3s: np.ndarray,
    *,
    minimum_training_observations: int = 730,
    warmup_days: int = 365,
    max_nfev: int = 500,
    seed: int = 20260828,
) -> Air2StreamFit:
    """Calibrate only against the supplied fitting-period water temperatures."""

    water = np.asarray(water_temperature_c, dtype=float)
    air = np.asarray(air_temperature_c, dtype=float)
    discharge = np.asarray(discharge_m3s, dtype=float)
    _validate_forcing(air, discharge)
    if water.shape != air.shape or len(index) != len(water):
        raise ValueError("water temperature and forcing must be date aligned")
    finite_water = np.flatnonzero(np.isfinite(water))
    if not len(finite_water):
        raise ValueError("no observed fitting-period water temperature")
    first = int(finite_water[0])
    objective_mask = np.isfinite(water)
    objective_mask[: min(len(water), first + warmup_days)] = False
    n_observed = int(objective_mask.sum())
    if n_observed < minimum_training_observations:
        raise ValueError("insufficient fitting observations after warm-up")
    q_reference = float(np.mean(discharge))
    initial = float(water[first])
    fit_index = index[first:]
    fit_air = air[first:]
    fit_discharge = discharge[first:]
    fit_water = water[first:]
    fit_mask = objective_mask[first:]

    def residual(parameters: np.ndarray) -> np.ndarray:
        try:
            predicted = simulate_air2stream8(
                fit_index,
                fit_air,
                fit_discharge,
                parameters,
                initial_water_temperature_c=initial,
                discharge_reference=q_reference,
            )
            values = predicted[fit_mask] - fit_water[fit_mask]
            if not np.isfinite(values).all():
                raise ValueError("non-finite residual")
            return values
        except ValueError:
            return np.full(n_observed, 1e3, dtype=float)

    rng = np.random.default_rng(seed)
    starts = [
        np.array([0.0, 0.5, 0.5, 0.0, 0.5, 0.5, 0.5, 0.1]),
        (AIR2STREAM8_LOWER + AIR2STREAM8_UPPER) / 2.0,
    ]
    starts.extend(
        rng.uniform(AIR2STREAM8_LOWER, AIR2STREAM8_UPPER) for _ in range(2)
    )
    best = None
    best_cost = np.inf
    for start in starts:
        fitted = least_squares(
            residual,
            np.clip(start, AIR2STREAM8_LOWER + 1e-8, AIR2STREAM8_UPPER - 1e-8),
            bounds=(AIR2STREAM8_LOWER, AIR2STREAM8_UPPER),
            max_nfev=max_nfev,
            method="trf",
        )
        current = residual(fitted.x)
        cost = float(np.mean(np.square(current)))
        if cost < best_cost:
            best, best_cost = fitted, cost
    if best is None or not np.isfinite(best_cost) or best_cost >= 1e5:
        raise ValueError("air2stream calibration failed")
    return Air2StreamFit(
        parameters=np.asarray(best.x, dtype=float),
        discharge_reference=q_reference,
        training_rmse=float(np.sqrt(best_cost)),
        n_training_observations=n_observed,
        n_function_evaluations=int(best.nfev),
        optimizer_status=int(best.status),
    )


__all__ = [
    "AIR2STREAM8_LOWER",
    "AIR2STREAM8_UPPER",
    "Air2StreamFit",
    "annual_phase",
    "fit_air2stream8",
    "simulate_air2stream8",
]
