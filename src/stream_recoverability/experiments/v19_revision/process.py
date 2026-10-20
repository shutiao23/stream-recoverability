"""Compiled versions of the existing published Air2stream integration equations."""

from __future__ import annotations

import numpy as np
from numba import njit

from stream_recoverability.experiments import air2stream_equivalent as reference


@njit(cache=True)
def integrate_three(air, parameters, initial, floor):
    rate = 1 / (2 * parameters[2])
    result = np.empty(len(air))
    result[0] = max(initial, floor)
    for day in range(len(air) - 1):
        right = (1 - rate) * result[day] + rate * (2 * parameters[0] + parameters[1] * (air[day] + air[day + 1]))
        result[day + 1] = max(right / (1 + rate), floor)
    return result


@njit(cache=True)
def integrate_eight(phase, air, discharge, parameters, initial, discharge_reference, floor):
    ratio = discharge / discharge_reference
    depth = ratio ** parameters[3]
    result = np.empty(len(air))
    result[0] = max(initial, floor)
    for day in range(len(air) - 1):
        seasonal_now = np.cos(2 * np.pi * (phase[day] - parameters[6]))
        seasonal_next = np.cos(2 * np.pi * (phase[day + 1] - parameters[6]))
        current = result[day]
        explicit = parameters[0] + parameters[1] * air[day] - parameters[2] * current + ratio[day] * (parameters[4] + parameters[5] * seasonal_now - parameters[7] * current)
        implicit = parameters[0] + parameters[1] * air[day + 1] + ratio[day + 1] * (parameters[4] + parameters[5] * seasonal_next)
        denominator = 1 + 0.5 * parameters[7] * ratio[day + 1] / depth[day + 1] + 0.5 * parameters[2] / depth[day + 1]
        if not np.isfinite(denominator) or abs(denominator) < 1e-8:
            raise ValueError("Unstable Crank-Nicolson denominator")
        predicted = (current + 0.5 * explicit / depth[day] + 0.5 * implicit / depth[day + 1]) / denominator
        if not np.isfinite(predicted) or abs(predicted) > 1000:
            raise ValueError("Unstable Air2stream trajectory")
        result[day + 1] = max(predicted, floor)
    return result


def simulate_three(index, air_temperature_c, parameters, *, initial_water_temperature_c, ice_floor_c=0.0):
    air = np.asarray(air_temperature_c, dtype=float)
    parameters = np.asarray(parameters, dtype=float)
    if len(index) != len(air) or len(air) < 2 or not np.isfinite(air).all() or parameters.shape != (3,) or parameters[2] <= 0:
        raise ValueError("Invalid Air2stream-3 forcing or parameters")
    return integrate_three(air, parameters, float(initial_water_temperature_c), float(ice_floor_c))


def simulate_eight(index, air_temperature_c, discharge_m3s, parameters, *, initial_water_temperature_c, discharge_reference, ice_floor_c=0.0):
    air, discharge = np.asarray(air_temperature_c, dtype=float), np.asarray(discharge_m3s, dtype=float)
    parameters = np.asarray(parameters, dtype=float)
    reference._validate_forcing(air, discharge)
    if parameters.shape != (8,) or not np.isfinite(parameters).all() or discharge_reference <= 0 or len(index) != len(air):
        raise ValueError("Invalid Air2stream-8 parameters or dates")
    return integrate_eight(reference.annual_phase(index), air, discharge, parameters, float(initial_water_temperature_c), float(discharge_reference), float(ice_floor_c))


def enable_compiled_reference() -> None:
    reference.simulate_air2stream3 = simulate_three
    reference.simulate_air2stream8 = simulate_eight
