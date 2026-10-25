"""Seasonal residual scenarios retaining slow variation and visible-state analogs."""
from __future__ import annotations

import numpy as np
import pandas as pd


def state_conditioned_draws(observed, center, target_dates, residuals, history_dates,
                            *, seed, n_draws=512, block_days=14,
                            history_states=None, target_states=None):
    """No hidden water temperature enters this experimental scenario generator.

    Residual histories must already exclude target/future years. Annual analogs
    supply slow 60-day variation; seasonal blocks supply shorter variation.
    Visible water residuals and available forcing states weight the analogs.
    """
    observed, center, residuals = map(lambda x: np.asarray(x, dtype=float), (observed, center, residuals))
    dates, history = pd.DatetimeIndex(target_dates), pd.DatetimeIndex(history_dates)
    if len(observed) != len(dates) or observed.shape != center.shape or len(residuals) != len(history):
        raise ValueError("Dates and residual dimensions must match")
    if dates.year.nunique() != 1 or np.isfinite(residuals[history.year == dates.year[0]]).any():
        raise ValueError("Target-year residuals must be excluded")
    missing = ~np.isfinite(observed)
    visible = ~missing & np.isfinite(center)
    if not np.isfinite(center[missing]).all():
        raise ValueError("Unavailable reconstruction center")
    current_visible = float(np.mean(observed[visible] - center[visible])) if visible.any() else 0.0
    month_day = dates.strftime("%m-%d")
    slow_paths, analog_features = [], []
    high = np.full(len(history), np.nan)
    state_pairs = []
    if history_states is not None and target_states is not None:
        state_pairs = list(zip(np.asarray(history_states).T, np.asarray(target_states).T))
    target_features = [current_visible]
    for _, values in state_pairs:
        valid = missing & np.isfinite(values)
        target_features.append(float(values[valid].mean()) if valid.any() else np.nan)
    for year in sorted(set(history.year)):
        held = history.year == year
        values = residuals[held]
        if np.isfinite(values).sum() < 180:
            continue
        smooth = pd.Series(values).rolling(60, center=True, min_periods=15).mean().to_numpy()
        high[held] = values - smooth
        mapping = pd.Series(smooth, index=history[held].strftime("%m-%d"))
        mapped = mapping.reindex(month_day).interpolate(limit_direction="both").to_numpy()
        if not np.isfinite(mapped).all():
            continue
        slow_paths.append(mapped)
        analog = [float(mapped[visible].mean()) if visible.any() else float(mapped.mean())]
        for old_values, _ in state_pairs:
            lookup = pd.Series(old_values[held], index=history[held].strftime("%m-%d"))
            value = lookup.reindex(month_day).to_numpy()
            valid = missing & np.isfinite(value)
            analog.append(float(value[valid].mean()) if valid.any() else np.nan)
        analog_features.append(analog)
    if len(slow_paths) < 2:
        raise ValueError("At least two usable residual years are required")
    analog_features = np.asarray(analog_features)
    target_features = np.asarray(target_features)
    distance, dimensions = np.zeros(len(slow_paths)), np.zeros(len(slow_paths))
    for column in range(analog_features.shape[1]):
        values = analog_features[:, column]
        valid = np.isfinite(values) & np.isfinite(target_features[column])
        finite_values = values[np.isfinite(values)]
        scale = max(float(finite_values.std()), 0.25) if len(finite_values) else 1.0
        distance[valid] += ((values[valid] - target_features[column]) / scale) ** 2
        dimensions[valid] += 1
    distance = np.divide(distance, dimensions, out=np.full(len(distance), 4.0), where=dimensions > 0)
    weight = np.exp(-np.minimum(distance, 50) / 2)
    # A small uniform mixture avoids treating a short analog archive as certainty.
    weight = 0.9 * weight / weight.sum() + 0.1 / len(weight)
    rng = np.random.default_rng(seed)
    paths = np.asarray(slow_paths)[rng.choice(len(weight), n_draws, p=weight)]
    valid_blocks = np.flatnonzero(np.convolve(np.isfinite(high).astype(int), np.ones(block_days, dtype=int), mode="valid") == block_days)
    if not len(valid_blocks):
        raise ValueError("No complete short residual block")
    # Never bridge calendar years, including when a target year was omitted.
    valid_blocks = valid_blocks[history.year[valid_blocks] == history.year[valid_blocks + block_days - 1]]
    if not len(valid_blocks):
        raise ValueError("No within-year residual block")
    noise = np.zeros((n_draws, len(dates)))
    for start in range(0, len(dates), block_days):
        length = min(block_days, len(dates) - start)
        distance = np.abs(history.dayofyear.to_numpy()[valid_blocks] - dates.dayofyear[start])
        seasonal = valid_blocks[np.minimum(distance, 366 - distance) <= 30]
        if not len(seasonal):
            seasonal = valid_blocks
        sampled = rng.choice(seasonal, n_draws)
        noise[:, start:start + length] = high[sampled[:, None] + np.arange(length)]
    draws = np.broadcast_to(observed, (n_draws, len(observed))).copy()
    draws[:, missing] = center[missing] + paths[:, missing] + noise[:, missing]
    return draws


def sample_crps(samples, reference):
    """Exact empirical-distribution CRPS without a quadratic pair matrix."""
    ordered = np.sort(np.asarray(samples, dtype=float))
    n = len(ordered)
    pair_term = np.sum((2 * np.arange(1, n + 1) - n - 1) * ordered) / n**2
    return float(np.mean(np.abs(ordered - reference)) - pair_term)
