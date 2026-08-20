from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.donor_falsification import (
    EXPERIMENT,
    build_donor_falsification_grid,
    transform_donor_values,
)


def test_donor_grid_closes_target_donor_contrast_inventory() -> None:
    grid, specs = build_donor_falsification_grid()
    assert grid.suite == "science_donor_falsification"
    assert len(grid.conditions) == 336
    assert len(grid.scenarios) == 6_720
    assert len(specs) == 336
    assert {condition.experiment for condition in grid.conditions} == {EXPERIMENT}
    assert all(scenario.condition.anchor_id for scenario in grid.scenarios)
    assert {spec["contrast"] for spec in specs.values()} == {
        "observed_same_day_C",
        "lagged_C",
        "past_only_C",
        "station_identity_permutation",
        "seasonal_residual_block_permutation",
    }


def test_lag_transform_changes_only_declared_donor() -> None:
    station_ids = ("B1", "S2", "P3")
    variable_names = ("T", "F", "L", "Ta")
    values = np.arange(12 * 3 * 4, dtype=np.float32).reshape(12, 3, 4)
    transformed = transform_donor_values(
        values,
        dates=pd.date_range("2016-01-01", periods=12, freq="D"),
        train_rows=np.array([True] * 6 + [False] * 6),
        station_ids=station_ids,
        variable_names=variable_names,
        spec={
            "contrast": "lagged_C",
            "lag_days": 1,
            "target_station": "B1",
            "donor_station": "S2",
        },
    )
    np.testing.assert_array_equal(transformed[:, 0], values[:, 0])
    np.testing.assert_array_equal(transformed[:, 2], values[:, 2])
    np.testing.assert_array_equal(transformed[:, 1, 3], values[:, 1, 3])
    assert np.isnan(transformed[0, 1, :3]).all()
    np.testing.assert_array_equal(transformed[1:, 1, :3], values[:-1, 1, :3])


def test_seasonal_permutation_is_deterministic_and_preserves_target() -> None:
    values = np.arange(90 * 3 * 4, dtype=np.float32).reshape(90, 3, 4)
    arguments = {
        "dates": pd.date_range("2016-01-01", periods=90, freq="D"),
        "train_rows": np.array([True] * 45 + [False] * 45),
        "station_ids": ("B1", "S2", "P3"),
        "variable_names": ("T", "F", "L", "Ta"),
        "spec": {
            "contrast": "seasonal_residual_block_permutation",
            "seed": 11,
            "target_station": "B1",
            "donor_station": "S2",
        },
    }
    first = transform_donor_values(values, **arguments)
    second = transform_donor_values(values, **arguments)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first[:, 0], values[:, 0])
    assert not np.array_equal(first[:, 1, :3], values[:, 1, :3])
