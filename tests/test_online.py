from __future__ import annotations

import numpy as np
import pytest

from stream_recoverability.evaluation.online import score_online_predictions
from stream_recoverability.models.online import (
    CausalGRUImputer,
    LastObservationPersistence,
    TrainingDOYClimatology,
)


def _series() -> np.ndarray:
    time = np.arange(36, dtype=np.float32)
    values = np.empty((36, 2, 2), dtype=np.float32)
    values[:, 0, 0] = np.sin(time / 4)
    values[:, 0, 1] = np.cos(time / 6)
    values[:, 1, 0] = 0.5 * np.sin(time / 5) + 1
    values[:, 1, 1] = time / 20
    return values


def _fitted_gru() -> CausalGRUImputer:
    values = _series()[:24]
    train_mask = np.zeros_like(values, dtype=bool)
    train_mask[2::4, 0, 0] = True
    train_mask[3::5, 1, 1] = True
    validation_mask = np.zeros_like(values, dtype=bool)
    validation_mask[4::6, 0, 0] = True
    return CausalGRUImputer(2, 2, hidden_size=6, seed=5).fit(
        values,
        train_mask,
        validation_values=values,
        validation_mask=validation_mask,
        epochs=1,
        chunk_size=8,
        patience=1,
    )


def test_future_value_perturbation_cannot_change_past_prediction() -> None:
    model = _fitted_gru()
    values = _series()
    artificial = np.zeros_like(values, dtype=bool)
    artificial[8:12, 0, 0] = True
    original = model.predict(values, artificial)
    changed = values.copy()
    changed[20:] += 100_000
    perturbed = model.predict(changed, artificial)
    assert np.array_equal(original[:20], perturbed[:20])


@pytest.mark.parametrize("model_name", ["climatology", "persistence", "causal_gru"])
def test_hidden_truth_perturbation_does_not_change_hidden_prediction(
    model_name: str,
) -> None:
    values = _series()
    artificial = np.zeros_like(values, dtype=bool)
    artificial[28:32, 0, 0] = True
    approved = np.ones_like(values, dtype=bool)
    train = np.arange(len(values)) < 24
    if model_name == "climatology":
        dates = np.arange(
            np.datetime64("2020-01-01"), np.datetime64("2020-02-06")
        )
        model = TrainingDOYClimatology(window=2).fit(
            values, dates, train, approved=approved
        )
        original = model.predict(values, dates, artificial, approved=approved)
    elif model_name == "persistence":
        model = LastObservationPersistence().fit(values, train, approved=approved)
        original = model.predict(values, artificial, approved=approved)
    else:
        model = _fitted_gru()
        original = model.predict(values, artificial, approved=approved)
    changed = values.copy()
    changed[artificial] -= 50_000
    if model_name == "climatology":
        changed_prediction = model.predict(
            changed, dates, artificial, approved=approved
        )
    else:
        changed_prediction = model.predict(changed, artificial, approved=approved)
    assert np.array_equal(original[artificial], changed_prediction[artificial])


def test_full_3d_auxiliary_mask_is_applied_before_gru_input() -> None:
    values = _series()[:6]
    artificial = np.zeros_like(values, dtype=bool)
    artificial[2, 1, 1] = True
    model = CausalGRUImputer(2, 2, hidden_size=4, seed=3)
    clean, input_observed, _, all_observed = model.prepare_inputs(values, artificial)
    channel = 1 * 2 + 1
    assert clean[2, channel] == 0.0
    assert not input_observed[2, channel]
    assert not all_observed[2, channel]
    assert input_observed[2, 0]

    train = np.arange(len(values)) < 4
    persistence = LastObservationPersistence().fit(values, train)
    prediction = persistence.predict(values, artificial)
    assert prediction[2, 1, 1] == values[1, 1, 1]
    assert prediction[2, 1, 1] != values[2, 1, 1]


def test_online_score_uses_only_approved_and_artificial_cells() -> None:
    truth = np.array([0.0, 10.0, 20.0, 30.0]).reshape(4, 1, 1)
    prediction = np.array([9999.0, 12.0, -9999.0, 9999.0]).reshape(4, 1, 1)
    climatology = np.array([-9999.0, 14.0, 9999.0, -9999.0]).reshape(4, 1, 1)
    approved = np.array([True, True, False, True]).reshape(4, 1, 1)
    artificial = np.array([False, True, True, False]).reshape(4, 1, 1)
    overall, horizons = score_online_predictions(
        truth, prediction, approved, artificial, climatology
    )
    assert overall["hidden_cells"] == 1
    assert overall["MAE"] == 2.0
    assert overall["RMSE"] == 2.0
    assert overall["climatology_MAE"] == 4.0
    assert overall["skill"] == 0.5
    assert horizons.loc[0, "horizon_bin"] == "1"


def test_climatology_fit_is_unchanged_by_validation_and_test_values() -> None:
    values = _series()
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-02-06"))
    train = np.arange(len(values)) < 24
    first = TrainingDOYClimatology(window=3).fit(values, dates, train)
    changed = values.copy()
    changed[~train] += 1_000_000
    second = TrainingDOYClimatology(window=3).fit(changed, dates, train)
    assert np.array_equal(first.climatology_, second.climatology_)
