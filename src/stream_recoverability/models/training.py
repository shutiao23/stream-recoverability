"""Shared deterministic training utilities for the small PyTorch baselines."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import torch


def set_deterministic(seed: int) -> None:
    """Seed NumPy/PyTorch and request deterministic CPU kernels."""

    if not isinstance(seed, (int, np.integer)) or int(seed) < 0:
        raise ValueError("seed must be a non-negative integer")
    seed = int(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def masked_mae_loss(
    prediction: torch.Tensor, target: torch.Tensor, mask: torch.Tensor
) -> torch.Tensor:
    """MAE evaluated strictly at ``mask=True`` positions."""

    if prediction.shape != target.shape or prediction.shape != mask.shape:
        raise ValueError("prediction, target, and mask must have the same shape")
    selected = mask.bool()
    if not torch.any(selected):
        raise ValueError("masked loss requires at least one selected cell")
    return torch.abs(prediction[selected] - target[selected]).mean()


def masked_mse_loss(
    prediction: torch.Tensor, target: torch.Tensor, mask: torch.Tensor
) -> torch.Tensor:
    """MSE evaluated strictly at ``mask=True`` positions."""

    if prediction.shape != target.shape or prediction.shape != mask.shape:
        raise ValueError("prediction, target, and mask must have the same shape")
    selected = mask.bool()
    if not torch.any(selected):
        raise ValueError("masked loss requires at least one selected cell")
    return torch.square(prediction[selected] - target[selected]).mean()


def compute_time_gaps(observed_mask: torch.Tensor) -> torch.Tensor:
    """Return elapsed unit steps since each feature was last observed."""

    if observed_mask.ndim != 3:
        raise ValueError("observed_mask must have shape (batch, time, feature)")
    observed = observed_mask.bool()
    gaps = torch.zeros_like(observed, dtype=torch.float32)
    for index in range(1, observed.shape[1]):
        gaps[:, index] = 1.0 + (~observed[:, index - 1]).float() * gaps[:, index - 1]
    return gaps


def _as_numpy(values: np.ndarray | torch.Tensor, *, name: str) -> np.ndarray:
    if isinstance(values, torch.Tensor):
        result = values.detach().cpu().numpy()
    else:
        result = np.asarray(values)
    if result.ndim not in {2, 3}:
        raise ValueError(f"{name} must have shape (time, feature) or (batch, time, feature)")
    return result


def as_3d_values(values: np.ndarray | torch.Tensor) -> tuple[np.ndarray, bool]:
    result = _as_numpy(values, name="values").astype(np.float32, copy=False)
    squeeze = result.ndim == 2
    return (result[None, ...] if squeeze else result), squeeze


def as_3d_mask(
    mask: np.ndarray | torch.Tensor,
    expected_shape: tuple[int, ...],
) -> np.ndarray:
    result = _as_numpy(mask, name="artificial_mask")
    if result.dtype != np.bool_:
        raise TypeError("artificial_mask must be boolean")
    if result.ndim == 2:
        result = result[None, ...]
    if result.shape != expected_shape:
        raise ValueError(
            f"artificial_mask has shape {result.shape}, expected {expected_shape}"
        )
    return result


def _validated_pair(
    values: np.ndarray | torch.Tensor,
    artificial_mask: np.ndarray | torch.Tensor,
    n_features: int,
) -> tuple[np.ndarray, np.ndarray, bool]:
    array, squeeze = as_3d_values(values)
    if array.shape[-1] != n_features:
        raise ValueError(f"values has {array.shape[-1]} features, expected {n_features}")
    hidden = as_3d_mask(artificial_mask, array.shape)
    if np.any(hidden & ~np.isfinite(array)):
        raise ValueError("artificial_mask covers a non-finite/ineligible target")
    if not hidden.any():
        raise ValueError("artificial_mask must hide at least one finite target")
    return array, hidden, squeeze


def feature_statistics(values: np.ndarray, artificial_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    observed = np.isfinite(values) & ~artificial_mask
    means = np.empty(values.shape[-1], dtype=np.float32)
    stds = np.empty(values.shape[-1], dtype=np.float32)
    for feature in range(values.shape[-1]):
        selected = values[..., feature][observed[..., feature]]
        if selected.size == 0:
            raise ValueError(f"feature {feature} has no observed training values")
        means[feature] = float(selected.mean())
        standard_deviation = float(selected.std())
        stds[feature] = standard_deviation if standard_deviation >= 1e-6 else 1.0
    return means, stds


def _model_tensors(
    values: np.ndarray,
    artificial_mask: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    finite = np.isfinite(values)
    observed = finite & ~artificial_mask
    normalized = np.zeros_like(values, dtype=np.float32)
    normalized[finite] = (
        (values - mean.reshape(1, 1, -1)) / std.reshape(1, 1, -1)
    )[finite]
    model_input = np.where(observed, normalized, 0.0).astype(np.float32)
    target = np.where(finite, normalized, 0.0).astype(np.float32)
    target_mask = artificial_mask & finite
    return (
        torch.from_numpy(model_input),
        torch.from_numpy(observed),
        torch.from_numpy(target),
        torch.from_numpy(target_mask),
    )


def _loss_for_batches(
    model: Any,
    tensors: tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor],
    batch_size: int,
) -> float:
    model.eval()
    inputs, observed, targets, target_masks = tensors
    losses: list[float] = []
    with torch.no_grad():
        for start in range(0, len(inputs), batch_size):
            selection = slice(start, start + batch_size)
            components = model.forward_components(inputs[selection], observed[selection])
            loss = model.training_loss(
                components, targets[selection], target_masks[selection], observed[selection]
            )
            losses.append(float(loss.detach()))
    return float(np.mean(losses))


def fit_imputer(
    model: Any,
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
) -> dict[str, Any]:
    """Fit one imputer and restore the best fixed-validation checkpoint."""

    if epochs <= 0 or batch_size <= 0 or patience <= 0:
        raise ValueError("epochs, batch_size, and patience must be positive")
    if learning_rate <= 0 or weight_decay < 0 or min_delta < 0:
        raise ValueError("invalid optimizer or early-stopping setting")
    if (validation_values is None) != (validation_mask is None):
        raise ValueError("validation_values and validation_mask must be supplied together")

    set_deterministic(model.seed)
    train_values, train_hidden, _ = _validated_pair(
        values, artificial_mask, model.n_features
    )
    keep = train_hidden.any(axis=(1, 2))
    train_values = train_values[keep]
    train_hidden = train_hidden[keep]
    mean, std = feature_statistics(train_values, train_hidden)
    model.feature_mean.copy_(torch.from_numpy(mean))
    model.feature_std.copy_(torch.from_numpy(std))
    train_tensors = _model_tensors(train_values, train_hidden, mean, std)

    validation_tensors = None
    if validation_values is not None and validation_mask is not None:
        valid_values, valid_hidden, _ = _validated_pair(
            validation_values, validation_mask, model.n_features
        )
        keep = valid_hidden.any(axis=(1, 2))
        validation_tensors = _model_tensors(
            valid_values[keep], valid_hidden[keep], mean, std
        )

    optimizer = torch.optim.Adam(
        model.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay)
    )
    generator = torch.Generator(device="cpu")
    generator.manual_seed(model.seed)
    best_loss = float("inf")
    best_epoch = -1
    best_state: dict[str, torch.Tensor] | None = None
    stale_epochs = 0
    history: dict[str, Any] = {"train_loss": [], "validation_loss": []}

    inputs, observed, targets, target_masks = train_tensors
    for epoch in range(int(epochs)):
        model.train()
        order = torch.randperm(len(inputs), generator=generator)
        batch_losses: list[float] = []
        for start in range(0, len(order), batch_size):
            indices = order[start : start + batch_size]
            optimizer.zero_grad(set_to_none=True)
            components = model.forward_components(inputs[indices], observed[indices])
            loss = model.training_loss(
                components, targets[indices], target_masks[indices], observed[indices]
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            batch_losses.append(float(loss.detach()))
        train_loss = float(np.mean(batch_losses))
        validation_loss = (
            _loss_for_batches(model, validation_tensors, batch_size)
            if validation_tensors is not None
            else train_loss
        )
        history["train_loss"].append(train_loss)
        history["validation_loss"].append(validation_loss)
        if verbose:
            print(
                f"epoch={epoch + 1} train_loss={train_loss:.6f} "
                f"validation_loss={validation_loss:.6f}"
            )

        if validation_loss < best_loss - min_delta:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    if best_state is None:
        raise RuntimeError("training did not produce a finite checkpoint")
    model.load_state_dict(best_state)
    model._is_fitted = True
    history["epochs_ran"] = len(history["train_loss"])
    history["best_epoch"] = best_epoch + 1
    history["best_validation_loss"] = best_loss
    return history


def predict_imputer(
    model: Any,
    values: np.ndarray | torch.Tensor,
    artificial_mask: np.ndarray | torch.Tensor | None = None,
    *,
    batch_size: int = 64,
) -> np.ndarray:
    """Predict without exposing artificial targets to the model input."""

    if not model._is_fitted:
        raise RuntimeError("fit or load_checkpoint must be called before predict")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    array, squeeze = as_3d_values(values)
    if array.shape[-1] != model.n_features:
        raise ValueError(f"values has {array.shape[-1]} features, expected {model.n_features}")
    if artificial_mask is None:
        hidden = np.zeros_like(array, dtype=bool)
    else:
        hidden = as_3d_mask(artificial_mask, array.shape)
        if np.any(hidden & ~np.isfinite(array)):
            raise ValueError("artificial_mask covers a non-finite/ineligible target")

    mean = model.feature_mean.detach().cpu().numpy()
    std = model.feature_std.detach().cpu().numpy()
    inputs, observed, _, _ = _model_tensors(array, hidden, mean, std)
    outputs: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(inputs), batch_size):
            selection = slice(start, start + batch_size)
            normalized = model.forward(inputs[selection], observed[selection])
            outputs.append(normalized.detach().cpu().numpy())
    prediction = np.concatenate(outputs, axis=0)
    prediction = prediction * std.reshape(1, 1, -1) + mean.reshape(1, 1, -1)
    observed_numpy = np.isfinite(array) & ~hidden
    prediction = np.where(observed_numpy, array, prediction)
    if not np.isfinite(prediction).all():
        raise RuntimeError("model produced a non-finite imputation")
    return prediction[0] if squeeze else prediction


def make_windows(
    values: np.ndarray,
    artificial_mask: np.ndarray,
    window_size: int,
    *,
    stride: int | None = None,
    require_masked_target: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Create deterministic windows, including a final right-aligned window."""

    values = np.asarray(values, dtype=np.float32)
    artificial_mask = np.asarray(artificial_mask)
    if values.ndim != 2 or artificial_mask.shape != values.shape:
        raise ValueError("values and artificial_mask must share shape (time, feature)")
    if artificial_mask.dtype != np.bool_:
        raise TypeError("artificial_mask must be boolean")
    if window_size <= 0 or window_size > len(values):
        raise ValueError("window_size must be in 1..len(values)")
    stride = window_size if stride is None else int(stride)
    if stride <= 0:
        raise ValueError("stride must be positive")
    starts = list(range(0, len(values) - window_size + 1, stride))
    final_start = len(values) - window_size
    if not starts or starts[-1] != final_start:
        starts.append(final_start)
    value_windows = np.stack([values[start : start + window_size] for start in starts])
    mask_windows = np.stack(
        [artificial_mask[start : start + window_size] for start in starts]
    )
    if require_masked_target:
        keep = mask_windows.any(axis=(1, 2))
        value_windows = value_windows[keep]
        mask_windows = mask_windows[keep]
    if len(value_windows) == 0:
        raise ValueError("no generated window contains an artificial target")
    return value_windows, mask_windows

