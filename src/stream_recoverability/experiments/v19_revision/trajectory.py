"""Observed-data-conditioned trajectory diagnostics for an annual thermal extreme."""

from __future__ import annotations

import numpy as np


def window_means(values: np.ndarray, window: int = 30) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim not in (1, 2) or array.shape[-1] < window:
        raise ValueError("Require a vector or trajectories with at least one full window")
    cumulative = np.concatenate([np.zeros(array.shape[:-1] + (1,)), np.cumsum(array, axis=-1)], axis=-1)
    return (cumulative[..., window:] - cumulative[..., :-window]) / window


def block_residual_draws(
    residuals: np.ndarray,
    n_days: int,
    *,
    n_draws: int,
    block_days: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample contiguous observed training-residual blocks without crossing missingness."""

    residuals = np.asarray(residuals, dtype=float)
    if residuals.ndim != 1 or block_days < 1 or n_draws < 1 or n_days < 1:
        raise ValueError("Require a residual vector and positive sampling dimensions")
    if len(residuals) < block_days:
        raise ValueError("Training history is shorter than one residual block")
    valid = np.convolve(np.isfinite(residuals).astype(int), np.ones(block_days, dtype=int), mode="valid") == block_days
    starts = np.flatnonzero(valid)
    if not len(starts):
        raise ValueError("No complete contiguous training residual block")
    n_blocks = int(np.ceil(n_days / block_days))
    selected = rng.choice(starts, size=(n_draws, n_blocks))
    positions = selected[..., None] + np.arange(block_days)
    return residuals[positions].reshape(n_draws, -1)[:, :n_days]


def conditional_trajectories(
    observed: np.ndarray,
    center: np.ndarray,
    training_residuals: np.ndarray,
    *,
    seed: int,
    n_draws: int = 128,
    block_days: int = 14,
    location_adjustment: float = 0.0,
) -> np.ndarray:
    """Draw completed years; hidden truth is not an argument or an information source."""

    observed = np.asarray(observed, dtype=float)
    center = np.asarray(center, dtype=float)
    if observed.ndim != 1 or observed.shape != center.shape:
        raise ValueError("Observed values and the model centre must be equal-length vectors")
    missing = ~np.isfinite(observed)
    if not np.isfinite(center[missing]).all():
        raise ValueError("Model centre is unavailable on hidden days")
    if not missing.any():
        return np.broadcast_to(observed, (n_draws, len(observed))).copy()
    try:
        residuals = block_residual_draws(training_residuals, len(center), n_draws=n_draws, block_days=block_days, rng=np.random.default_rng(seed))
    except ValueError:
        starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
        ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
        longest = int((ends - starts).max())
        if longest >= block_days:
            raise
        residuals = block_residual_draws(training_residuals, len(center), n_draws=n_draws, block_days=longest, rng=np.random.default_rng(seed))
    draws = np.broadcast_to(observed, (n_draws, len(observed))).copy()
    draws[:, missing] = center[missing] + location_adjustment + residuals[:, missing]
    return draws


def trajectory_features(
    draws: np.ndarray,
    missing: np.ndarray,
    point_estimate: float,
    *,
    window: int = 30,
) -> dict[str, float]:
    """Summarise peak location and H30 uncertainty; none of these is a guarantee."""

    draws = np.asarray(draws, dtype=float)
    missing = np.asarray(missing, dtype=bool)
    if draws.ndim != 2 or draws.shape[1:] != missing.shape or not np.isfinite(draws).all():
        raise ValueError("Finite trajectory matrix and a matching missing-day vector required")
    rolled = window_means(draws, window)
    starts = np.argmax(rolled, axis=1)
    peaks = rolled[np.arange(len(draws)), starts]
    hidden_by_start = np.convolve(missing.astype(float), np.ones(window) / window, mode="valid")
    hidden = hidden_by_start[starts]
    frequency = np.bincount(starts, minlength=rolled.shape[1]).astype(float) / len(starts)
    positive = frequency[frequency > 0]
    entropy = float(-(positive * np.log(positive)).sum())
    distance = np.abs(np.arange(rolled.shape[1])[None, :] - starts[:, None])
    competitors = np.where(distance >= window, rolled, -np.inf).max(axis=1)
    margins = peaks - competitors
    finite_margins = margins[np.isfinite(margins)]
    lower, upper = np.quantile(peaks, [0.05, 0.95])
    return {
        "probabilistic_hidden_support": float(hidden.mean()),
        "hidden_support_sd": float(hidden.std()),
        "hidden_support_upper90": float(np.quantile(hidden, 0.9)),
        "peak_start_sd_days": float(starts.std()),
        "peak_start_entropy": entropy,
        "peak_competition_margin_C": float(finite_margins.mean()) if len(finite_margins) else 0.0,
        "h30_draw_mean_C": float(peaks.mean()),
        "h30_draw_sd_C": float(peaks.std()),
        "h30_interval_lower_C": float(lower),
        "h30_interval_upper_C": float(upper),
        "h30_interval_width_C": float(upper - lower),
        "direct_h30_uncertainty": float(np.quantile(np.abs(peaks - point_estimate), 0.9)),
        "support_uncertainty_interaction": float(hidden.mean() * peaks.std()),
    }


def historical_location_adjustment(observed: np.ndarray, model_center: np.ndarray, *, shrinkage_days: int = 30) -> float:
    observed = np.asarray(observed, dtype=float)
    model_center = np.asarray(model_center, dtype=float)
    available = np.isfinite(observed) & np.isfinite(model_center)
    count = int(available.sum())
    if not count:
        return 0.0
    residual = observed[available] - model_center[available]
    return float(np.median(residual) * count / (count + shrinkage_days))


def error_channels(truth: np.ndarray, completed: np.ndarray, *, window: int = 30) -> dict[str, float | str]:
    truth = np.asarray(truth, dtype=float)
    completed = np.asarray(completed, dtype=float)
    if truth.shape != completed.shape or not np.isfinite(truth).all() or not np.isfinite(completed).all():
        raise ValueError("Finite matching truth and completed vectors required")
    truth_windows = window_means(truth, window)
    completed_windows = window_means(completed, window)
    true_start = int(np.argmax(truth_windows))
    reconstructed_start = int(np.argmax(completed_windows))
    error = float(completed_windows[reconstructed_start] - truth_windows[true_start])
    hiding = float(np.mean((completed - truth)[true_start : true_start + window]))
    increment = error - hiding
    via_all_windows = float(np.max(window_means(completed - truth, window) - (truth_windows[true_start] - truth_windows)))
    if increment < -1e-9:
        raise RuntimeError("The nonnegative window-switch identity was violated")
    state = "no_switch"
    if reconstructed_start != true_start:
        state = "switch_overestimation" if error > 1e-10 else "switch_without_overestimation"
    return {
        "error_C": error,
        "hidden_channel_C": hiding,
        "window_switch_increment_C": max(0.0, increment),
        "identity_residual_C": error - via_all_windows,
        "true_window_start": true_start,
        "reconstructed_window_start": reconstructed_start,
        "switch_state": state,
    }
