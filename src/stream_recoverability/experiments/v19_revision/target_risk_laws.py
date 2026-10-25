"""Matched-information H30 laws for an opened-data risk-estimation supplement."""
from __future__ import annotations

import numpy as np

from .state_trajectory import state_conditioned_draws
from .trajectory import conditional_trajectories, historical_location_adjustment, window_means

RESIDUAL_LAWS = ("raw_block14", "visible_adjustment", "seasonal_slow", "seasonal_air_slow", "seasonal_air_flow_slow")
CDF_FEATURES = ("CDF_failure_probability", "CDF_target_abs90", "CDF_h30_sd", "CDF_width90", "CDF_mean_shift_from_point")


def residual_law_draws(law, observed, center, dates, residuals, history_dates, *, history_states, target_states, seed, n_draws=512):
    """Air-only laws never receive the discharge-state column."""
    if law not in RESIDUAL_LAWS:
        raise ValueError("Unknown declared residual law")
    if law in {"raw_block14", "visible_adjustment"}:
        adjustment = historical_location_adjustment(observed, center) if law == "visible_adjustment" else 0.
        return conditional_trajectories(observed, center, residuals, seed=seed, n_draws=n_draws, location_adjustment=adjustment)
    old_state = current_state = None
    if law != "seasonal_slow":
        count = 1 if law == "seasonal_air_slow" else 2
        old, current = np.asarray(history_states, dtype=float), np.asarray(target_states, dtype=float)
        if old.ndim != 2 or current.ndim != 2 or old.shape[1] < count or current.shape[1] < count:
            raise ValueError("Declared forcing-state information is unavailable")
        old_state, current_state = old[:, :count], current[:, :count]
    return state_conditioned_draws(observed, center, dates, residuals, history_dates, seed=seed, n_draws=n_draws,
                                   history_states=old_state, target_states=current_state)


def restore_neural_draws(normalized, observed, mean, scale, expected_h30):
    """Replay cached neural paths, conditioning only on visible observations."""
    normalized = np.asarray(normalized)
    observed = np.asarray(observed, dtype=float)
    if normalized.ndim != 3 or normalized.shape[1] < len(observed) or normalized.shape[2] < 1:
        raise ValueError("Invalid cached neural path shape")
    draws = normalized[:, :len(observed), 0].astype(float) * scale + mean
    visible = np.isfinite(observed)
    draws[:, visible] = observed[visible]
    actual = window_means(draws).max(axis=1)
    expected = np.asarray(expected_h30, dtype=float)
    if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=1e-9):
        raise ValueError("Cached neural paths do not reproduce the existing H30 distribution")
    return draws


def adjust_neural_draws(draws, observed, center):
    """The shared visible adjustment cannot change an observed water value."""
    draws = np.asarray(draws, dtype=float).copy()
    missing = ~np.isfinite(np.asarray(observed, dtype=float))
    draws[:, missing] += historical_location_adjustment(observed, center)
    return draws


def tolerance_features(samples, point, tolerance=.5):
    """Score error of the delivered point, rather than dispersion about a median."""
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all() or not np.isfinite(point):
        return {name: np.nan for name in CDF_FEATURES}
    errors = np.abs(samples - point)
    return dict(zip(CDF_FEATURES, (float((errors > tolerance).mean()), float(np.quantile(errors, .9)),
                                 float(samples.std()), float(np.quantile(samples, .95) - np.quantile(samples, .05)),
                                 float(samples.mean() - point))))
