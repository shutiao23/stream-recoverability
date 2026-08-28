"""A genuine mask-aware bidirectional LSTM imputer for offline gaps."""

from __future__ import annotations

import torch
from torch import nn

from stream_recoverability.models.deep_baselines import BaseDeepImputer
from stream_recoverability.models.training import masked_mae_loss, set_deterministic


class BidirectionalLSTMImputer(BaseDeepImputer):
    """Offline gap imputer backed by ``torch.nn.LSTM`` in both directions.

    This compact sensitivity baseline is not a reimplementation of a published
    stream-temperature LSTM. Values hidden for training or evaluation are
    zeroed by the shared imputer interface; an observed-value mask is supplied
    as a separate input channel.
    """

    model_name = "bidirectional_lstm"

    def __init__(
        self,
        n_features: int,
        *,
        hidden_size: int = 32,
        n_layers: int = 1,
        dropout: float = 0.0,
        seed: int = 0,
    ) -> None:
        set_deterministic(seed)
        super().__init__(n_features, seed=seed)
        if hidden_size <= 0 or n_layers <= 0:
            raise ValueError("hidden_size and n_layers must be positive")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        self.hidden_size = int(hidden_size)
        self.n_layers = int(n_layers)
        self.dropout = float(dropout)
        self.lstm = nn.LSTM(
            input_size=self.n_features * 2,
            hidden_size=self.hidden_size,
            num_layers=self.n_layers,
            batch_first=True,
            bidirectional=True,
            dropout=self.dropout if self.n_layers > 1 else 0.0,
        )
        self.output = nn.Linear(self.hidden_size * 2, self.n_features)
        self._config.update(
            {
                "hidden_size": self.hidden_size,
                "n_layers": self.n_layers,
                "dropout": self.dropout,
            }
        )

    def forward_components(
        self, values: torch.Tensor, observed_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        if values.ndim != 3 or observed_mask.shape != values.shape:
            raise ValueError(
                "values and observed_mask must share (batch, time, feature)"
            )
        observed = observed_mask.bool()
        clean = torch.where(observed, values, torch.zeros_like(values))
        hidden, _ = self.lstm(torch.cat([clean, observed.float()], dim=-1))
        estimate = self.output(hidden)
        imputed = torch.where(observed, clean, estimate)
        return {"estimate": estimate, "imputed": imputed}

    def forward(
        self, values: torch.Tensor, observed_mask: torch.Tensor
    ) -> torch.Tensor:
        return self.forward_components(values, observed_mask)["imputed"]

    def training_loss(
        self,
        components: dict[str, torch.Tensor],
        target: torch.Tensor,
        target_mask: torch.Tensor,
        observed_mask: torch.Tensor,
    ) -> torch.Tensor:
        del observed_mask
        return masked_mae_loss(components["estimate"], target, target_mask)


__all__ = ["BidirectionalLSTMImputer"]
