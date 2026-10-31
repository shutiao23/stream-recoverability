"""Separate numerical estimates, observed-window bounds and unknown values."""

from __future__ import annotations

import numpy as np


def water_air_agreement(observed, air, window=7):
    """Smallest observed-window mean absolute water/air difference, in Celsius."""
    difference = np.abs(np.asarray(observed, float) - np.asarray(air, float))
    windows = np.lib.stride_tricks.sliding_window_view(difference, window)
    valid = np.isfinite(windows).all(axis=1)
    return float(windows[valid].mean(axis=1).min()) if valid.any() else np.nan


def release_states(frame, limits, quality_flag):
    """Use visible inputs only; callers attach truth after making decisions."""
    supported = frame.D2.notna().to_numpy() & frame.risk_score.le(0.1).to_numpy()
    supported &= frame.n_complete_years.ge(4).to_numpy()
    for column, threshold in limits.items():
        value = frame[column].to_numpy(float)
        supported &= np.isfinite(value) & (np.abs(value) <= threshold)
    quality_flag = np.asarray(quality_flag, bool)
    lower = frame.observed_lower_bound__observed_days.notna().to_numpy()
    state = np.full(len(frame), "unknown", dtype=object)
    state[lower & ~quality_flag] = "observed_bound"
    state[supported & ~quality_flag] = "estimate"
    return state
