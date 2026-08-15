"""Small, CPU-friendly BRITS- and SAITS-style imputation baselines."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .training import (
    compute_time_gaps,
    fit_imputer,
    masked_mae_loss,
    predict_imputer,
    set_deterministic,
)


class BaseDeepImputer(nn.Module):
    """Common fit/predict/checkpoint interface for both deep baselines."""

    model_name = "deep_imputer"

    def __init__(self, n_features: int, *, seed: int = 0) -> None:
        super().__init__()
        if not isinstance(n_features, (int, np.integer)) or int(n_features) <= 0:
            raise ValueError("n_features must be a positive integer")
        if not isinstance(seed, (int, np.integer)) or int(seed) < 0:
            raise ValueError("seed must be a non-negative integer")
        self.n_features = int(n_features)
        self.seed = int(seed)
        self.register_buffer("feature_mean", torch.zeros(self.n_features))
        self.register_buffer("feature_std", torch.ones(self.n_features))
        self._is_fitted = False
        self.history_: dict[str, Any] = {}
        self._config: dict[str, Any] = {"n_features": self.n_features, "seed": self.seed}

    def fit(
        self,
        values: np.ndarray | torch.Tensor,
        artificial_mask: np.ndarray | torch.Tensor,
        *,
        validation_values: np.ndarray | torch.Tensor | None = None,
        validation_mask: np.ndarray | torch.Tensor | None = None,
        epochs: int = 100,
        batch_size: int = 16,
        learning_rate: float = 1e-3,
        weight_decay: float = 0.0,
        patience: int = 10,
        min_delta: float = 0.0,
        verbose: bool = False,
    ) -> "BaseDeepImputer":
        self.history_ = fit_imputer(
            self,
            values,
            artificial_mask,
            validation_values=validation_values,
            validation_mask=validation_mask,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            weight_decay=weight_decay,
            patience=patience,
            min_delta=min_delta,
            verbose=verbose,
        )
        return self

    def predict(
        self,
        values: np.ndarray | torch.Tensor,
        artificial_mask: np.ndarray | torch.Tensor | None = None,
        *,
        batch_size: int = 64,
    ) -> np.ndarray:
        return predict_imputer(self, values, artificial_mask, batch_size=batch_size)

    def save_checkpoint(self, path: str | Path) -> Path:
        if not self._is_fitted:
            raise RuntimeError("fit must be called before save_checkpoint")
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "class_name": type(self).__name__,
                "config": self._config,
                "state_dict": self.state_dict(),
                "history": self.history_,
            },
            output,
        )
        return output

    @classmethod
    def load_checkpoint(cls, path: str | Path) -> "BaseDeepImputer":
        try:
            payload = torch.load(Path(path), map_location="cpu", weights_only=False)
        except TypeError:  # PyTorch 2.0 compatibility
            payload = torch.load(Path(path), map_location="cpu")
        if payload.get("class_name") != cls.__name__:
            raise ValueError(
                f"checkpoint contains {payload.get('class_name')}, not {cls.__name__}"
            )
        model = cls(**payload["config"])
        model.load_state_dict(payload["state_dict"])
        model.history_ = dict(payload.get("history", {}))
        model._is_fitted = True
        model.eval()
        return model


class _TemporalDecay(nn.Module):
    def __init__(self, n_features: int, hidden_size: int) -> None:
        super().__init__()
        self.linear = nn.Linear(n_features, hidden_size)

    def forward(self, gaps: torch.Tensor) -> torch.Tensor:
        return torch.exp(-torch.relu(self.linear(gaps)))


class BRITSImputer(BaseDeepImputer):
    """Bidirectional recurrent imputer with time-gap decay and consistency."""

    model_name = "brits"

    def __init__(
        self,
        n_features: int,
        *,
        hidden_size: int = 64,
        consistency_weight: float = 0.1,
        seed: int = 0,
    ) -> None:
        set_deterministic(seed)
        super().__init__(n_features, seed=seed)
        if hidden_size <= 0:
            raise ValueError("hidden_size must be positive")
        if consistency_weight < 0:
            raise ValueError("consistency_weight must be non-negative")
        self.hidden_size = int(hidden_size)
        self.consistency_weight = float(consistency_weight)
        self.forward_decay = _TemporalDecay(self.n_features, self.hidden_size)
        self.backward_decay = _TemporalDecay(self.n_features, self.hidden_size)
        self.forward_cell = nn.GRUCell(self.n_features * 2, self.hidden_size)
        self.backward_cell = nn.GRUCell(self.n_features * 2, self.hidden_size)
        self.forward_history = nn.Linear(self.hidden_size, self.n_features)
        self.backward_history = nn.Linear(self.hidden_size, self.n_features)
        self._config.update(
            {
                "hidden_size": self.hidden_size,
                "consistency_weight": self.consistency_weight,
            }
        )

    def _run_direction(
        self,
        values: torch.Tensor,
        observed_mask: torch.Tensor,
        cell: nn.GRUCell,
        decay: _TemporalDecay,
        history_layer: nn.Linear,
    ) -> torch.Tensor:
        batch_size, steps, _ = values.shape
        gaps = compute_time_gaps(observed_mask)
        hidden = values.new_zeros((batch_size, self.hidden_size))
        estimates: list[torch.Tensor] = []
        for index in range(steps):
            hidden = hidden * decay(gaps[:, index])
            estimate = history_layer(hidden)
            observed = observed_mask[:, index]
            current = torch.where(observed, values[:, index], estimate)
            hidden = cell(
                torch.cat([current, observed.float()], dim=-1),
                hidden,
            )
            estimates.append(estimate)
        return torch.stack(estimates, dim=1)

    def forward_components(
        self, values: torch.Tensor, observed_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        if values.ndim != 3 or observed_mask.shape != values.shape:
            raise ValueError("values and observed_mask must share (batch, time, feature)")
        observed = observed_mask.bool()
        clean_values = torch.where(observed, values, torch.zeros_like(values))
        forward_estimate = self._run_direction(
            clean_values,
            observed,
            self.forward_cell,
            self.forward_decay,
            self.forward_history,
        )
        backward_estimate = torch.flip(
            self._run_direction(
                torch.flip(clean_values, dims=[1]),
                torch.flip(observed, dims=[1]),
                self.backward_cell,
                self.backward_decay,
                self.backward_history,
            ),
            dims=[1],
        )
        combined = 0.5 * (forward_estimate + backward_estimate)
        imputed = torch.where(observed, clean_values, combined)
        return {
            "forward": forward_estimate,
            "backward": backward_estimate,
            "combined": combined,
            "imputed": imputed,
        }

    def forward(self, values: torch.Tensor, observed_mask: torch.Tensor) -> torch.Tensor:
        return self.forward_components(values, observed_mask)["imputed"]

    def training_loss(
        self,
        components: dict[str, torch.Tensor],
        target: torch.Tensor,
        target_mask: torch.Tensor,
        observed_mask: torch.Tensor,
    ) -> torch.Tensor:
        del observed_mask
        forward_loss = masked_mae_loss(components["forward"], target, target_mask)
        backward_loss = masked_mae_loss(components["backward"], target, target_mask)
        combined_loss = masked_mae_loss(components["combined"], target, target_mask)
        consistency = masked_mae_loss(
            components["forward"], components["backward"], target_mask
        )
        return (
            forward_loss + backward_loss + combined_loss
        ) / 3.0 + self.consistency_weight * consistency


def _sinusoidal_positions(
    length: int, width: int, *, device: torch.device, dtype: torch.dtype
) -> torch.Tensor:
    position = torch.arange(length, device=device, dtype=dtype).unsqueeze(1)
    divisor = torch.exp(
        torch.arange(0, width, 2, device=device, dtype=dtype)
        * (-math.log(10000.0) / width)
    )
    encoding = torch.zeros((length, width), device=device, dtype=dtype)
    encoding[:, 0::2] = torch.sin(position * divisor)
    if width > 1:
        encoding[:, 1::2] = torch.cos(position * divisor[: encoding[:, 1::2].shape[1]])
    return encoding.unsqueeze(0)


class SAITSImputer(BaseDeepImputer):
    """Two-stage, mask-aware self-attention imputer."""

    model_name = "saits"

    def __init__(
        self,
        n_features: int,
        *,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 1,
        d_ff: int = 128,
        dropout: float = 0.0,
        seed: int = 0,
    ) -> None:
        set_deterministic(seed)
        super().__init__(n_features, seed=seed)
        if d_model <= 0 or n_heads <= 0 or d_model % n_heads:
            raise ValueError("d_model must be positive and divisible by n_heads")
        if n_layers <= 0 or d_ff <= 0:
            raise ValueError("n_layers and d_ff must be positive")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.n_layers = int(n_layers)
        self.d_ff = int(d_ff)
        self.dropout = float(dropout)
        self.first_input = nn.Linear(self.n_features * 2, self.d_model)
        self.second_input = nn.Linear(self.n_features * 2, self.d_model)
        self.first_attention = self._encoder()
        self.second_attention = self._encoder()
        self.first_output = nn.Linear(self.d_model, self.n_features)
        self.second_output = nn.Linear(self.d_model, self.n_features)
        self.fusion_gate = nn.Linear(self.d_model * 2 + self.n_features, self.n_features)
        self._config.update(
            {
                "d_model": self.d_model,
                "n_heads": self.n_heads,
                "n_layers": self.n_layers,
                "d_ff": self.d_ff,
                "dropout": self.dropout,
            }
        )

    def _encoder(self) -> nn.TransformerEncoder:
        layer = nn.TransformerEncoderLayer(
            d_model=self.d_model,
            nhead=self.n_heads,
            dim_feedforward=self.d_ff,
            dropout=self.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=False,
        )
        return nn.TransformerEncoder(layer, num_layers=self.n_layers)

    def forward_components(
        self, values: torch.Tensor, observed_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        if values.ndim != 3 or observed_mask.shape != values.shape:
            raise ValueError("values and observed_mask must share (batch, time, feature)")
        observed = observed_mask.bool()
        mask_values = observed.float()
        clean_values = torch.where(observed, values, torch.zeros_like(values))
        positions = _sinusoidal_positions(
            values.shape[1], self.d_model, device=values.device, dtype=values.dtype
        )

        first_hidden = self.first_attention(
            self.first_input(torch.cat([clean_values, mask_values], dim=-1)) + positions
        )
        first_estimate = self.first_output(first_hidden)
        first_filled = torch.where(observed, clean_values, first_estimate)

        second_hidden = self.second_attention(
            self.second_input(torch.cat([first_filled, mask_values], dim=-1)) + positions
        )
        second_estimate = self.second_output(second_hidden)
        gate = torch.sigmoid(
            self.fusion_gate(
                torch.cat([first_hidden, second_hidden, mask_values], dim=-1)
            )
        )
        combined = gate * first_estimate + (1.0 - gate) * second_estimate
        imputed = torch.where(observed, clean_values, combined)
        return {
            "first": first_estimate,
            "second": second_estimate,
            "combined": combined,
            "imputed": imputed,
        }

    def forward(self, values: torch.Tensor, observed_mask: torch.Tensor) -> torch.Tensor:
        return self.forward_components(values, observed_mask)["imputed"]

    def training_loss(
        self,
        components: dict[str, torch.Tensor],
        target: torch.Tensor,
        target_mask: torch.Tensor,
        observed_mask: torch.Tensor,
    ) -> torch.Tensor:
        del observed_mask
        return (
            masked_mae_loss(components["first"], target, target_mask)
            + masked_mae_loss(components["second"], target, target_mask)
            + masked_mae_loss(components["combined"], target, target_mask)
        ) / 3.0


BRITS = BRITSImputer
SAITS = SAITSImputer
