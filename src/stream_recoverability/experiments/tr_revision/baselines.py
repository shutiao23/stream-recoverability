"""Variance-preserving completion and Gaussian AR(1) residual bridges."""

from __future__ import annotations

import numpy as np


def move1(train_proxy, train_target, target_proxy):
    x, y, target = map(lambda a: np.asarray(a, float), (train_proxy, train_target, target_proxy))
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 30 or np.std(x[valid], ddof=1) < 1e-8:
        return np.full_like(target, np.nan)
    sign = np.sign(np.corrcoef(x[valid], y[valid])[0, 1])
    return y[valid].mean() + sign * np.std(y[valid], ddof=1) / np.std(x[valid], ddof=1) * (target - x[valid].mean())


def ar1_bridge(observed, mean, residual_history, seed, draws=20):
    observed, mean, residual = map(lambda a: np.asarray(a, float), (observed, mean, residual_history))
    finite = residual[np.isfinite(residual)]
    missing = ~np.isfinite(observed)
    if finite.size < 30 or not np.isfinite(mean[missing]).all():
        return np.full((draws, len(mean)), np.nan)
    mu, sigma = finite.mean(), max(float(finite.std(ddof=1)), 1e-3)
    pairs = np.isfinite(residual[:-1]) & np.isfinite(residual[1:])
    phi = np.corrcoef(residual[:-1][pairs], residual[1:][pairs])[0, 1] if pairs.sum() > 10 else 0.0
    phi = float(np.clip(np.nan_to_num(phi), -0.95, 0.995))
    rng = np.random.default_rng(seed)
    out = np.repeat(observed[None, :], draws, axis=0)
    starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
    ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
    for start, end in zip(starts, ends):
        n = end - start
        left = start > 0 and np.isfinite(observed[start - 1]) and np.isfinite(mean[start - 1])
        right = end < len(mean) and np.isfinite(observed[end]) and np.isfinite(mean[end])
        state = np.full(draws, observed[start - 1] - mean[start - 1] - mu) if left else rng.normal(0, sigma, draws)
        path = np.empty((draws, n + int(right)))
        for j in range(path.shape[1]):
            state = phi * state + rng.normal(0, sigma * np.sqrt(1 - phi**2), draws)
            path[:, j] = state
        if right:
            k = np.arange(1, n + 1)
            covariance = sigma**2 * phi**(n + 1 - k)
            variance = sigma**2
            if left:
                covariance *= 1 - phi**(2 * k)
                variance *= 1 - phi**(2 * (n + 1))
            boundary = observed[end] - mean[end] - mu
            path[:, :n] += (boundary - path[:, -1])[:, None] * covariance / max(variance, 1e-12)
        out[:, start:end] = mean[start:end] + mu + path[:, :n]
    return out
