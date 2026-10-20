"""Information about a thermal decision already identified by observed windows."""

from __future__ import annotations

import numpy as np


def observed_h30_lower_bound(observed: np.ndarray, *, window: int = 30) -> float:
    """Lower bound on complete-record H30 from fully observed consecutive windows."""

    observed = np.asarray(observed, dtype=float)
    if observed.ndim != 1 or window < 1:
        raise ValueError("Require a daily vector and a positive window length")
    if len(observed) < window:
        return -float("inf")
    present = np.isfinite(observed)
    counts = np.convolve(present.astype(int), np.ones(window, dtype=int), mode="valid")
    sums = np.convolve(np.where(present, observed, 0.0), np.ones(window), mode="valid")
    valid = counts == window
    return float((sums[valid] / window).max()) if valid.any() else -float("inf")


def observationally_resolved_hot(lower_bound, threshold, *, measurement_margin_c: float = 0.0) -> np.ndarray:
    """Resolve only hot labels; an unresolved lower bound cannot certify a cool year."""

    lower_bound = np.asarray(lower_bound, dtype=float)
    threshold = np.asarray(threshold, dtype=float)
    if measurement_margin_c < 0:
        raise ValueError("A measurement sensitivity margin cannot be negative")
    return np.isfinite(lower_bound) & (lower_bound - measurement_margin_c > threshold + 1e-9)
