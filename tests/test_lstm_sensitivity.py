from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from torch import nn

from stream_recoverability.experiments.lstm_sensitivity import (
    provider_domain_subset,
)
from stream_recoverability.models.lstm_baseline import BidirectionalLSTMImputer


def _values() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    values = rng.normal(size=(4, 16, 3)).astype(np.float32)
    hidden = np.zeros_like(values, dtype=bool)
    hidden[:, 6:10, 0] = True
    return values, hidden


def test_lstm_baseline_is_an_actual_bidirectional_lstm() -> None:
    model = BidirectionalLSTMImputer(3, hidden_size=8, seed=7)
    assert isinstance(model.lstm, nn.LSTM)
    assert model.lstm.bidirectional is True
    assert not any(
        isinstance(module, (nn.GRU, nn.GRUCell)) for module in model.modules()
    )


def test_lstm_baseline_hides_truth_and_is_deterministic() -> None:
    values, hidden = _values()
    first = BidirectionalLSTMImputer(3, hidden_size=8, seed=11).fit(
        values, hidden, epochs=2, batch_size=2, patience=2
    )
    changed = values.copy()
    changed[hidden] += 10000.0
    original = first.predict(values, hidden)
    altered = first.predict(changed, hidden)
    assert np.array_equal(original[hidden], altered[hidden])
    assert np.isfinite(original).all()

    second = BidirectionalLSTMImputer(3, hidden_size=8, seed=11).fit(
        values, hidden, epochs=2, batch_size=2, patience=2
    )
    assert np.array_equal(original, second.predict(values, hidden))


def test_lstm_checkpoint_round_trip(tmp_path) -> None:
    values, hidden = _values()
    model = BidirectionalLSTMImputer(3, hidden_size=8, seed=3).fit(
        values, hidden, epochs=1, batch_size=2, patience=1
    )
    checkpoint = model.save_checkpoint(tmp_path / "lstm.pt")
    loaded = BidirectionalLSTMImputer.load_checkpoint(checkpoint)
    assert np.array_equal(model.predict(values, hidden), loaded.predict(values, hidden))


def test_provider_domain_subset_is_metadata_only_and_bounded() -> None:
    candidates = pd.DataFrame(
        {
            "network_id": ["z", "a", "b", "c", "d"],
            "provider": ["p1", "p1", "p1", "p2", "p2"],
            "domain": ["x", "x", "y", "z", "z"],
            "source_panel": [
                "first_confirmation",
                "first_confirmation",
                "second_confirmation",
                "second_confirmation",
                "second_confirmation",
            ],
            "n_eligible_stations": [4, 3, 2, 4, 3],
            "forbidden_loss": [0.0, 99.0, -4.0, 1000.0, -1000.0],
        }
    )
    selected = provider_domain_subset(candidates, per_provider=2)
    assert selected["network_id"].tolist() == ["a", "z", "d", "c"]
    changed = candidates.copy()
    changed["forbidden_loss"] *= -100
    assert (
        provider_domain_subset(changed, per_provider=2)["network_id"].tolist()
        == selected["network_id"].tolist()
    )


def test_lstm_forward_shape() -> None:
    model = BidirectionalLSTMImputer(3, hidden_size=4, seed=0)
    values = torch.zeros((2, 10, 3))
    observed = torch.ones_like(values, dtype=torch.bool)
    components = model.forward_components(values, observed)
    assert components["estimate"].shape == values.shape
    assert components["imputed"].shape == values.shape
