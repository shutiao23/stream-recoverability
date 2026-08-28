from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.recurrent_sensitivity import (
    artificial_block_windows,
    nested_training_years,
    provider_stratified_subset,
    recurrently_usable_years,
    score_existing_placements,
)


def test_provider_subset_is_deterministic_and_compute_bounded() -> None:
    qualified = pd.DataFrame(
        {
            "network_id": ["z", "a", "b", "c"],
            "provider": ["p1", "p1", "p2", "p2"],
            "qc_status": ["qualified"] * 4,
            "n_eligible_stations": [3, 3, 5, 4],
        }
    )
    result = provider_stratified_subset(qualified, ["z", "a", "b", "c"])
    assert result["network_id"].tolist() == ["a", "c"]


def test_artificial_windows_never_leave_named_training_years() -> None:
    index = pd.date_range("2018-01-01", "2021-12-31", freq="D")
    panel = pd.DataFrame(
        {
            "s1": np.sin(np.arange(len(index)) / 20),
            "s2": np.cos(np.arange(len(index)) / 30),
        },
        index=index,
    )
    fit, validation = nested_training_years((2018, 2019, 2020, 2021))
    assert fit == (2018, 2019, 2020)
    assert validation == (2021,)
    values, mask = artificial_block_windows(
        panel, fit, gap_lengths=(7, 30), window_length=64, max_windows=8
    )
    assert values.shape == mask.shape == (8, 64, 2)
    assert mask.any(axis=(1, 2)).all()
    assert np.isfinite(values[mask]).all()


def test_recurrent_availability_drops_univariate_early_years() -> None:
    index = pd.date_range("2018-01-01", "2020-12-31", freq="D")
    panel = pd.DataFrame({"s1": 1.0, "s2": np.nan}, index=index)
    panel.loc[panel.index.year >= 2019, "s2"] = 2.0
    assert recurrently_usable_years(panel, (2018, 2019, 2020)) == (2019, 2020)


class _MeanImputer:
    def predict(self, values: np.ndarray, hidden: np.ndarray) -> np.ndarray:
        result = values.copy()
        result[hidden] = 0.0
        return np.nan_to_num(result)


def test_scoring_uses_existing_bd_placements_and_hides_truth() -> None:
    index = pd.date_range("2020-01-01", periods=160, freq="D")
    panel = pd.DataFrame(
        {"s1": np.ones(160), "s2": np.arange(160, dtype=float)}, index=index
    )
    placements = pd.DataFrame(
        {
            "network_id": ["n1", "n1"],
            "station_id": ["s1", "s1"],
            "gap_length": [7, 7],
            "placement": [0, 1],
            "gap_start": [index[60], index[80]],
            "information_condition": ["B_union_D", "other"],
            "mae_deg_c": [0.5, 99.0],
        }
    )
    result = score_existing_placements(
        _MeanImputer(),
        panel,
        placements,
        gap_lengths=(7,),
        window_length=32,
    )
    assert len(result) == 1
    assert result.loc[0, "brits_mae_deg_c"] == 1.0
    assert result.loc[0, "xgboost_mae_deg_c"] == 0.5
