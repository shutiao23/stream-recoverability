"""Variance-preserving completion and Gaussian AR(1) residual bridges.

``ar1_bridge`` is the legacy sampler used by the frozen r4 trajectories. All
paths share one ``Generator`` and innovations are drawn in day-major order, so
the random stream consumed by a path depends on the total number of paths. A
20-path call is therefore not a prefix of a 500-path call.

``ar1_bridge_pathwise`` gives every path an independent child stream from
``SeedSequence(seed).spawn(draws)``. Path ``i`` is identical for every total
draw count greater than ``i``, so a pilot ensemble can be extended without
regenerating earlier paths. ``ar1_bridge`` is intentionally unchanged for
historical reproducibility.
"""

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


def ar1_bridge_pathwise(observed, mean, residual_history, seed, draws=20):
    """Gaussian AR(1) bridge with one independent random stream per path.

    Same AR(1), boundary-conditioning, and output semantics as
    :func:`ar1_bridge`, but path ``i`` always consumes the same stream from
    the ``i``-th child of ``SeedSequence(seed)``. Consequently the first ``N``
    paths are identical for any ``draws >= N``.
    """
    observed, mean, residual = map(lambda a: np.asarray(a, float), (observed, mean, residual_history))
    finite = residual[np.isfinite(residual)]
    missing = ~np.isfinite(observed)
    if finite.size < 30 or not np.isfinite(mean[missing]).all():
        return np.full((draws, len(mean)), np.nan)
    if draws <= 0:
        return np.empty((0, len(mean)))
    mu, sigma = finite.mean(), max(float(finite.std(ddof=1)), 1e-3)
    pairs = np.isfinite(residual[:-1]) & np.isfinite(residual[1:])
    phi = np.corrcoef(residual[:-1][pairs], residual[1:][pairs])[0, 1] if pairs.sum() > 10 else 0.0
    phi = float(np.clip(np.nan_to_num(phi), -0.95, 0.995))
    scale = sigma * np.sqrt(1 - phi**2)
    children = np.random.SeedSequence(seed).spawn(draws)
    rngs = [np.random.default_rng(child) for child in children]
    out = np.repeat(observed[None, :], draws, axis=0)
    starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
    ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
    for start, end in zip(starts, ends):
        n = end - start
        left = start > 0 and np.isfinite(observed[start - 1]) and np.isfinite(mean[start - 1])
        right = end < len(mean) and np.isfinite(observed[end]) and np.isfinite(mean[end])
        steps = n + int(right)
        state = np.empty(draws)
        innovations = np.empty((draws, steps))
        for i, rng in enumerate(rngs):
            state[i] = observed[start - 1] - mean[start - 1] - mu if left else rng.normal(0, sigma)
            innovations[i] = rng.normal(0, scale, steps)
        path = np.empty((draws, steps))
        for j in range(steps):
            state = phi * state + innovations[:, j]
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
