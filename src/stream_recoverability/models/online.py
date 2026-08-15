"""Strictly causal online-recovery baselines, separate from offline imputers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn


def _values_3d(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32)
    if result.ndim != 3:
        raise ValueError("values must have shape (time, station, variable)")
    return result


def _boolean_3d(mask: np.ndarray, shape: tuple[int, ...], name: str) -> np.ndarray:
    result = np.asarray(mask)
    if result.dtype != np.bool_ or result.shape != shape:
        raise ValueError(f"{name} must be boolean with shape {shape}")
    return result


def _approved(values: np.ndarray, approved: np.ndarray | None) -> np.ndarray:
    if approved is None:
        return np.isfinite(values)
    return _boolean_3d(approved, values.shape, "approved") & np.isfinite(values)


def _dates(dates: np.ndarray | pd.Series, length: int) -> pd.DatetimeIndex:
    result = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    if len(result) != length or result.isna().any():
        raise ValueError("dates must contain one finite date per time step")
    return result


def _calendar_day(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(
        [pd.Timestamp(2000, value.month, value.day).dayofyear - 1 for value in dates],
        dtype=int,
    )


class TrainingDOYClimatology:
    """Day-of-year climatology fitted exclusively on selected training dates."""

    name = "online_climatology"

    def __init__(self, *, window: int = 7) -> None:
        if not 0 <= int(window) <= 182:
            raise ValueError("window must be between 0 and 182")
        self.window = int(window)
        self._is_fitted = False

    def fit(
        self,
        values: np.ndarray,
        dates: np.ndarray | pd.Series,
        train_selector: np.ndarray,
        *,
        approved: np.ndarray | None = None,
    ) -> "TrainingDOYClimatology":
        values = _values_3d(values)
        parsed_dates = _dates(dates, len(values))
        train = np.asarray(train_selector)
        if train.dtype != np.bool_ or train.shape != (len(values),) or not train.any():
            raise ValueError("train_selector must be a non-empty boolean time mask")
        eligible = _approved(values, approved) & train[:, None, None]
        day = _calendar_day(parsed_dates)
        table = np.empty((366, values.shape[1], values.shape[2]), dtype=np.float32)
        for station in range(values.shape[1]):
            for variable in range(values.shape[2]):
                selected = eligible[:, station, variable]
                channel_values = values[selected, station, variable]
                channel_days = day[selected]
                if len(channel_values) == 0:
                    raise ValueError(
                        f"station {station}, variable {variable} has no approved training values"
                    )
                fallback = float(np.median(channel_values))
                for target_day in range(366):
                    distance = np.abs(channel_days - target_day)
                    distance = np.minimum(distance, 366 - distance)
                    local = channel_values[distance <= self.window]
                    table[target_day, station, variable] = (
                        float(np.median(local)) if len(local) else fallback
                    )
        self.climatology_ = table
        self.shape_ = values.shape[1:]
        self._is_fitted = True
        return self

    def baseline(self, dates: np.ndarray | pd.Series) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("fit must be called before baseline")
        parsed_dates = _dates(dates, len(dates))
        return self.climatology_[_calendar_day(parsed_dates)].copy()

    def predict(
        self,
        values: np.ndarray,
        dates: np.ndarray | pd.Series,
        artificial_mask: np.ndarray,
        *,
        approved: np.ndarray | None = None,
    ) -> np.ndarray:
        values = _values_3d(values)
        if values.shape[1:] != self.shape_:
            raise ValueError("station/variable axes differ from fitted data")
        hidden = _boolean_3d(artificial_mask, values.shape, "artificial_mask")
        observed = _approved(values, approved) & ~hidden
        prediction = self.baseline(dates)
        return np.where(observed, values, prediction).astype(np.float32)


class LastObservationPersistence:
    """Forward-fill each channel; training means handle missing initial history."""

    name = "online_persistence"

    def __init__(self) -> None:
        self._is_fitted = False

    def fit(
        self,
        values: np.ndarray,
        train_selector: np.ndarray,
        *,
        approved: np.ndarray | None = None,
    ) -> "LastObservationPersistence":
        values = _values_3d(values)
        train = np.asarray(train_selector)
        if train.dtype != np.bool_ or train.shape != (len(values),) or not train.any():
            raise ValueError("train_selector must be a non-empty boolean time mask")
        eligible = _approved(values, approved) & train[:, None, None]
        fallback = np.empty(values.shape[1:], dtype=np.float32)
        for station in range(values.shape[1]):
            for variable in range(values.shape[2]):
                selected = values[:, station, variable][eligible[:, station, variable]]
                if len(selected) == 0:
                    raise ValueError(
                        f"station {station}, variable {variable} has no approved training values"
                    )
                fallback[station, variable] = float(np.mean(selected))
        self.fallback_ = fallback
        self.shape_ = values.shape[1:]
        self._is_fitted = True
        return self

    def predict(
        self,
        values: np.ndarray,
        artificial_mask: np.ndarray,
        *,
        approved: np.ndarray | None = None,
    ) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("fit must be called before predict")
        values = _values_3d(values)
        if values.shape[1:] != self.shape_:
            raise ValueError("station/variable axes differ from fitted data")
        hidden = _boolean_3d(artificial_mask, values.shape, "artificial_mask")
        observed = _approved(values, approved) & ~hidden
        result = np.empty_like(values, dtype=np.float32)
        last = self.fallback_.copy()
        for index in range(len(values)):
            result[index] = np.where(observed[index], values[index], last)
            last = np.where(observed[index], values[index], last)
        return result


def _set_seed(seed: int) -> None:
    if not isinstance(seed, (int, np.integer)) or int(seed) < 0:
        raise ValueError("seed must be a non-negative integer")
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    torch.use_deterministic_algorithms(True)


def _time_gaps(observed: np.ndarray) -> np.ndarray:
    gaps = np.zeros(observed.shape, dtype=np.float32)
    for index in range(1, len(observed)):
        gaps[index] = 1.0 + (~observed[index - 1]).astype(np.float32) * gaps[index - 1]
    return gaps


class CausalGRUImputer(nn.Module):
    """Forward-only GRU using current availability masks and elapsed time gaps."""

    name = "causal_gru"

    def __init__(
        self,
        n_stations: int,
        n_variables: int,
        *,
        hidden_size: int = 32,
        input_channel_mask: np.ndarray | None = None,
        seed: int = 0,
    ) -> None:
        _set_seed(seed)
        super().__init__()
        if n_stations <= 0 or n_variables <= 0 or hidden_size <= 0:
            raise ValueError("axis sizes and hidden_size must be positive")
        self.n_stations = int(n_stations)
        self.n_variables = int(n_variables)
        self.n_channels = self.n_stations * self.n_variables
        self.hidden_size = int(hidden_size)
        self.seed = int(seed)
        if input_channel_mask is None:
            channel_mask = np.ones((self.n_stations, self.n_variables), dtype=bool)
        else:
            channel_mask = _boolean_3d(
                np.asarray(input_channel_mask)[None, ...],
                (1, self.n_stations, self.n_variables),
                "input_channel_mask",
            )[0]
        self.register_buffer("input_channel_mask", torch.from_numpy(channel_mask.reshape(-1)))
        self.register_buffer("feature_mean", torch.zeros(self.n_channels))
        self.register_buffer("feature_std", torch.ones(self.n_channels))
        self.cell = nn.GRUCell(self.n_channels * 3, self.hidden_size)
        self.output = nn.Linear(self.hidden_size, self.n_channels)
        self._is_fitted = False
        self.history_: dict[str, Any] = {}

    @property
    def shape(self) -> tuple[int, int]:
        return self.n_stations, self.n_variables

    def _validate_values(self, values: np.ndarray) -> np.ndarray:
        result = _values_3d(values)
        if result.shape[1:] != self.shape:
            raise ValueError(f"values station/variable axes must be {self.shape}")
        return result

    def prepare_inputs(
        self,
        values: np.ndarray,
        artificial_mask: np.ndarray,
        *,
        approved: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return masked normalized values, input mask, gaps, and all-channel mask."""

        values = self._validate_values(values)
        hidden = _boolean_3d(artificial_mask, values.shape, "artificial_mask")
        all_observed = _approved(values, approved) & ~hidden
        selected_channels = self.input_channel_mask.detach().cpu().numpy().reshape(self.shape)
        input_observed = all_observed & selected_channels[None, ...]
        flat_values = values.reshape(len(values), -1)
        flat_input_observed = input_observed.reshape(len(values), -1)
        mean = self.feature_mean.detach().cpu().numpy()
        std = self.feature_std.detach().cpu().numpy()
        normalized = (flat_values - mean[None, :]) / std[None, :]
        clean = np.where(flat_input_observed, normalized, 0.0).astype(np.float32)
        gaps = _time_gaps(flat_input_observed)
        return clean, flat_input_observed, gaps, all_observed.reshape(len(values), -1)

    def _forward_chunk(
        self,
        values: torch.Tensor,
        observed: torch.Tensor,
        gaps: torch.Tensor,
        hidden: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        predictions: list[torch.Tensor] = []
        for index in range(len(values)):
            hidden = self.cell(
                torch.cat(
                    [values[index], observed[index].float(), gaps[index]], dim=-1
                ).unsqueeze(0),
                hidden,
            )
            predictions.append(self.output(hidden).squeeze(0))
        return torch.stack(predictions), hidden

    def _statistics(
        self, values: np.ndarray, artificial_mask: np.ndarray, approved: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        observed = approved & np.isfinite(values) & ~artificial_mask
        mean = np.empty(self.n_channels, dtype=np.float32)
        std = np.empty(self.n_channels, dtype=np.float32)
        flat_values = values.reshape(len(values), -1)
        flat_observed = observed.reshape(len(values), -1)
        for channel in range(self.n_channels):
            selected = flat_values[:, channel][flat_observed[:, channel]]
            if len(selected) == 0:
                raise ValueError(f"channel {channel} has no observed training values")
            mean[channel] = float(selected.mean())
            deviation = float(selected.std())
            std[channel] = deviation if deviation >= 1e-6 else 1.0
        return mean, std

    def _validation_loss(
        self,
        values: np.ndarray,
        artificial_mask: np.ndarray,
        approved: np.ndarray,
        chunk_size: int,
    ) -> float:
        target_mask = artificial_mask & approved & np.isfinite(values)
        clean, observed, gaps, _ = self.prepare_inputs(
            values, artificial_mask, approved=approved
        )
        target = (
            values.reshape(len(values), -1)
            - self.feature_mean.detach().cpu().numpy()[None, :]
        ) / self.feature_std.detach().cpu().numpy()[None, :]
        flat_target_mask = target_mask.reshape(len(values), -1)
        hidden = torch.zeros((1, self.hidden_size))
        absolute_error = 0.0
        count = 0
        self.eval()
        with torch.no_grad():
            for start in range(0, len(values), chunk_size):
                stop = min(start + chunk_size, len(values))
                prediction, hidden = self._forward_chunk(
                    torch.from_numpy(clean[start:stop]),
                    torch.from_numpy(observed[start:stop]),
                    torch.from_numpy(gaps[start:stop]),
                    hidden,
                )
                selected = torch.from_numpy(flat_target_mask[start:stop])
                if selected.any():
                    targets = torch.from_numpy(target[start:stop].astype(np.float32))
                    absolute_error += float(torch.abs(prediction[selected] - targets[selected]).sum())
                    count += int(selected.sum())
        if count == 0:
            raise ValueError("validation mask contains no approved artificial targets")
        return absolute_error / count

    def fit(
        self,
        train_values: np.ndarray,
        train_artificial_mask: np.ndarray,
        *,
        train_approved: np.ndarray | None = None,
        validation_values: np.ndarray | None = None,
        validation_mask: np.ndarray | None = None,
        validation_approved: np.ndarray | None = None,
        epochs: int = 20,
        learning_rate: float = 1e-3,
        weight_decay: float = 0.0,
        chunk_size: int = 64,
        patience: int = 5,
        verbose: bool = False,
    ) -> "CausalGRUImputer":
        if epochs <= 0 or learning_rate <= 0 or chunk_size <= 0 or patience <= 0:
            raise ValueError("epochs, learning_rate, chunk_size, and patience must be positive")
        if weight_decay < 0:
            raise ValueError("weight_decay must be non-negative")
        if (validation_values is None) != (validation_mask is None):
            raise ValueError("validation_values and validation_mask must be supplied together")
        _set_seed(self.seed)
        train_values = self._validate_values(train_values)
        train_hidden = _boolean_3d(
            train_artificial_mask, train_values.shape, "train_artificial_mask"
        )
        train_approved_array = _approved(train_values, train_approved)
        target_mask = train_hidden & train_approved_array
        if not target_mask.any():
            raise ValueError("training mask contains no approved artificial targets")
        mean, std = self._statistics(train_values, train_hidden, train_approved_array)
        self.feature_mean.copy_(torch.from_numpy(mean))
        self.feature_std.copy_(torch.from_numpy(std))
        clean, observed, gaps, _ = self.prepare_inputs(
            train_values, train_hidden, approved=train_approved_array
        )
        targets = (train_values.reshape(len(train_values), -1) - mean[None, :]) / std[None, :]
        flat_target_mask = target_mask.reshape(len(train_values), -1)

        if validation_values is not None and validation_mask is not None:
            validation_values = self._validate_values(validation_values)
            validation_hidden = _boolean_3d(
                validation_mask, validation_values.shape, "validation_mask"
            )
            validation_approved_array = _approved(
                validation_values, validation_approved
            )
        else:
            validation_hidden = None
            validation_approved_array = None

        optimizer = torch.optim.Adam(
            self.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay)
        )
        best_loss = float("inf")
        best_state: dict[str, torch.Tensor] | None = None
        best_epoch = -1
        stale = 0
        train_history: list[float] = []
        validation_history: list[float] = []
        for epoch in range(int(epochs)):
            self.train()
            hidden_state = torch.zeros((1, self.hidden_size))
            epoch_error = 0.0
            epoch_count = 0
            for start in range(0, len(train_values), chunk_size):
                stop = min(start + chunk_size, len(train_values))
                prediction, next_hidden = self._forward_chunk(
                    torch.from_numpy(clean[start:stop]),
                    torch.from_numpy(observed[start:stop]),
                    torch.from_numpy(gaps[start:stop]),
                    hidden_state,
                )
                selected = torch.from_numpy(flat_target_mask[start:stop])
                if selected.any():
                    target_tensor = torch.from_numpy(targets[start:stop].astype(np.float32))
                    loss = torch.abs(prediction[selected] - target_tensor[selected]).mean()
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.parameters(), 5.0)
                    optimizer.step()
                    epoch_error += float(loss.detach()) * int(selected.sum())
                    epoch_count += int(selected.sum())
                hidden_state = next_hidden.detach()
            train_loss = epoch_error / epoch_count
            validation_loss = (
                self._validation_loss(
                    validation_values,
                    validation_hidden,
                    validation_approved_array,
                    chunk_size,
                )
                if validation_values is not None
                else train_loss
            )
            train_history.append(train_loss)
            validation_history.append(validation_loss)
            if verbose:
                print(
                    f"epoch={epoch + 1} train_loss={train_loss:.6f} "
                    f"validation_loss={validation_loss:.6f}"
                )
            if validation_loss < best_loss:
                best_loss = validation_loss
                best_epoch = epoch + 1
                best_state = {
                    name: value.detach().cpu().clone()
                    for name, value in self.state_dict().items()
                }
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    break
        if best_state is None:
            raise RuntimeError("training did not produce a finite checkpoint")
        self.load_state_dict(best_state)
        self._is_fitted = True
        self.history_ = {
            "train_loss": train_history,
            "validation_loss": validation_history,
            "best_epoch": best_epoch,
            "epochs_ran": len(train_history),
            "best_validation_loss": best_loss,
        }
        return self

    def predict(
        self,
        values: np.ndarray,
        artificial_mask: np.ndarray,
        *,
        approved: np.ndarray | None = None,
        chunk_size: int = 256,
    ) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("fit or load_checkpoint must be called before predict")
        values = self._validate_values(values)
        hidden_mask = _boolean_3d(artificial_mask, values.shape, "artificial_mask")
        clean, observed, gaps, all_observed = self.prepare_inputs(
            values, hidden_mask, approved=approved
        )
        hidden_state = torch.zeros((1, self.hidden_size))
        parts: list[np.ndarray] = []
        self.eval()
        with torch.no_grad():
            for start in range(0, len(values), chunk_size):
                stop = min(start + chunk_size, len(values))
                prediction, hidden_state = self._forward_chunk(
                    torch.from_numpy(clean[start:stop]),
                    torch.from_numpy(observed[start:stop]),
                    torch.from_numpy(gaps[start:stop]),
                    hidden_state,
                )
                parts.append(prediction.numpy())
        normalized = np.concatenate(parts)
        physical = (
            normalized * self.feature_std.detach().cpu().numpy()[None, :]
            + self.feature_mean.detach().cpu().numpy()[None, :]
        )
        flat_values = values.reshape(len(values), -1)
        result = np.where(all_observed, flat_values, physical)
        if not np.isfinite(result).all():
            raise RuntimeError("causal GRU produced non-finite predictions")
        return result.reshape(values.shape).astype(np.float32)

    def save_checkpoint(self, path: str | Path) -> Path:
        if not self._is_fitted:
            raise RuntimeError("fit must be called before save_checkpoint")
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "config": {
                    "n_stations": self.n_stations,
                    "n_variables": self.n_variables,
                    "hidden_size": self.hidden_size,
                    "input_channel_mask": self.input_channel_mask.detach()
                    .cpu()
                    .numpy()
                    .reshape(self.shape),
                    "seed": self.seed,
                },
                "state_dict": self.state_dict(),
                "history": self.history_,
            },
            output,
        )
        return output

    @classmethod
    def load_checkpoint(cls, path: str | Path) -> "CausalGRUImputer":
        try:
            payload = torch.load(path, map_location="cpu", weights_only=False)
        except TypeError:
            payload = torch.load(path, map_location="cpu")
        model = cls(**payload["config"])
        model.load_state_dict(payload["state_dict"])
        model.history_ = dict(payload.get("history", {}))
        model._is_fitted = True
        model.eval()
        return model
