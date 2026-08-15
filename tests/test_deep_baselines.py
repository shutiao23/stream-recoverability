from __future__ import annotations

import numpy as np
import pytest
import torch

from stream_recoverability.models.deep_baselines import BRITSImputer, SAITSImputer
from stream_recoverability.models.training import compute_time_gaps, masked_mae_loss


def _data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(123)
    values = rng.normal(size=(3, 10, 3)).astype(np.float32)
    values[:, 0, 2] = np.nan
    train_mask = np.zeros_like(values, dtype=bool)
    train_mask[:, 3:5, 0] = True
    train_mask[:, 6, 1] = True
    validation_mask = np.zeros_like(values, dtype=bool)
    validation_mask[:, 5:7, 0] = True
    return values, train_mask, validation_mask


def _model(name: str, seed: int = 7):
    if name == "brits":
        return BRITSImputer(3, hidden_size=8, seed=seed)
    return SAITSImputer(
        3, d_model=8, n_heads=2, n_layers=1, d_ff=16, dropout=0.0, seed=seed
    )


@pytest.mark.parametrize("name", ["brits", "saits"])
def test_deep_baseline_shape_finite_and_fixed_validation(name: str) -> None:
    values, train_mask, validation_mask = _data()
    model = _model(name).fit(
        values,
        train_mask,
        validation_values=values,
        validation_mask=validation_mask,
        epochs=2,
        batch_size=2,
        patience=2,
    )
    prediction = model.predict(values, validation_mask)
    assert prediction.shape == values.shape
    assert np.isfinite(prediction).all()
    observed = np.isfinite(values) & ~validation_mask
    assert np.array_equal(prediction[observed], values[observed])
    assert 1 <= model.history_["best_epoch"] <= model.history_["epochs_ran"] <= 2


def test_masked_only_loss_ignores_unselected_targets() -> None:
    prediction = torch.tensor([[[1.0, 2.0], [3.0, 4.0]]])
    target = torch.tensor([[[0.0, 2.0], [3.0, 8.0]]])
    mask = torch.tensor([[[True, False], [False, True]]])
    first = masked_mae_loss(prediction, target, mask)
    changed = target.clone()
    changed[~mask] = 10000.0
    second = masked_mae_loss(prediction, changed, mask)
    assert torch.equal(first, second)
    assert first.item() == pytest.approx(2.5)


@pytest.mark.parametrize("name", ["brits", "saits"])
def test_deep_baseline_is_deterministic(name: str) -> None:
    values, train_mask, _ = _data()
    first = _model(name, seed=19).fit(
        values, train_mask, epochs=1, batch_size=2, patience=1
    )
    first_prediction = first.predict(values, train_mask)
    second = _model(name, seed=19).fit(
        values, train_mask, epochs=1, batch_size=2, patience=1
    )
    second_prediction = second.predict(values, train_mask)
    assert np.array_equal(first_prediction, second_prediction)


@pytest.mark.parametrize("name", ["brits", "saits"])
def test_hidden_truth_is_not_an_input(name: str) -> None:
    values, train_mask, _ = _data()
    model = _model(name).fit(
        values, train_mask, epochs=1, batch_size=2, patience=1
    )
    altered = values.copy()
    altered[train_mask] += 10000.0
    original_prediction = model.predict(values, train_mask)
    altered_prediction = model.predict(altered, train_mask)
    assert np.array_equal(
        original_prediction[train_mask], altered_prediction[train_mask]
    )


@pytest.mark.parametrize("name", ["brits", "saits"])
def test_checkpoint_round_trip(name: str, tmp_path) -> None:
    values, train_mask, _ = _data()
    model = _model(name).fit(
        values, train_mask, epochs=1, batch_size=2, patience=1
    )
    expected = model.predict(values, train_mask)
    checkpoint = model.save_checkpoint(tmp_path / f"{name}.pt")
    loaded = type(model).load_checkpoint(checkpoint)
    assert np.array_equal(expected, loaded.predict(values, train_mask))


def test_brits_time_gap_accumulates_through_missing_steps() -> None:
    observed = torch.tensor([[[True], [False], [False], [True]]])
    gaps = compute_time_gaps(observed)
    assert torch.equal(gaps[:, :, 0], torch.tensor([[0.0, 1.0, 2.0, 3.0]]))

