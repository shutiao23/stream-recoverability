from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.air2stream_equivalent import (
    fit_air2stream8,
    simulate_air2stream8,
)


def test_crank_nicolson_step_matches_published_update() -> None:
    index = pd.date_range("2020-01-01", periods=2, freq="D")
    air = np.array([2.0, 3.0])
    flow = np.array([4.0, 6.0])
    parameters = np.array([0.1, 0.2, 0.3, 0.0, 0.4, 0.5, 0.25, 0.1])
    observed = simulate_air2stream8(
        index,
        air,
        flow,
        parameters,
        initial_water_temperature_c=5.0,
        discharge_reference=5.0,
    )
    theta_0, theta_1 = flow / 5.0
    phase = index.dayofyear.to_numpy(dtype=float) / 366.0
    seasonal_0 = np.cos(2.0 * np.pi * (phase[0] - parameters[6]))
    seasonal_1 = np.cos(2.0 * np.pi * (phase[1] - parameters[6]))
    explicit = (
        parameters[0]
        + parameters[1] * air[0]
        - parameters[2] * 5.0
        + theta_0
        * (parameters[4] + parameters[5] * seasonal_0 - parameters[7] * 5.0)
    )
    implicit = (
        parameters[0]
        + parameters[1] * air[1]
        + theta_1 * (parameters[4] + parameters[5] * seasonal_1)
    )
    expected = (5.0 + 0.5 * explicit + 0.5 * implicit) / (
        1.0 + 0.5 * parameters[7] * theta_1 + 0.5 * parameters[2]
    )
    assert observed[1] == pytest.approx(expected)


def test_fit_is_invariant_to_unseen_evaluation_values() -> None:
    index = pd.date_range("2010-01-01", periods=3 * 365, freq="D")
    air = 8.0 + 7.0 * np.sin(2.0 * np.pi * np.arange(len(index)) / 365.0)
    flow = np.full(len(index), 5.0)
    parameters = np.array([0.1, 0.3, 0.4, 0.0, 0.2, 0.4, 0.2, 0.1])
    water = simulate_air2stream8(
        index,
        air,
        flow,
        parameters,
        initial_water_temperature_c=5.0,
        discharge_reference=5.0,
    )
    train = slice(0, 2 * 365)
    first = fit_air2stream8(
        index[train],
        water[train],
        air[train],
        flow[train],
        minimum_training_observations=300,
        warmup_days=100,
        max_nfev=80,
    )
    changed = water.copy()
    changed[2 * 365 :] += 1000.0
    second = fit_air2stream8(
        index[train],
        changed[train],
        air[train],
        flow[train],
        minimum_training_observations=300,
        warmup_days=100,
        max_nfev=80,
    )
    np.testing.assert_allclose(first.parameters, second.parameters)


def test_nonpositive_flow_fails_closed() -> None:
    index = pd.date_range("2020-01-01", periods=3, freq="D")
    with pytest.raises(ValueError, match="strictly positive"):
        simulate_air2stream8(
            index,
            np.ones(3),
            np.array([1.0, 0.0, 1.0]),
            np.zeros(8),
            initial_water_temperature_c=1.0,
            discharge_reference=1.0,
        )
