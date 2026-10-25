"""Scores and inference with explicit units, censoring direction and empty sets."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import log_ndtr
from scipy.stats import norm, t


def ensemble_crps(samples, truth, threshold=None):
    """Empirical CRPS; threshold chaining gives upper-tail weighted CRPS.

    For weight 1{z >= threshold}, use v(x)=max(x, threshold) on *all* cases.
    No selection by the realized outcome is made.
    """
    x = np.asarray(samples, dtype=float)
    y = np.asarray(truth, dtype=float)
    if x.ndim != 2 or x.shape[0] != y.size:
        raise ValueError("samples must be cases x draws, aligned with truth")
    if threshold is not None:
        boundary = np.broadcast_to(np.asarray(threshold), y.shape)
        x, y = np.maximum(x, boundary[:, None]), np.maximum(y, boundary)
    x = np.sort(x, axis=1)
    n = x.shape[1]
    coefficient = 2 * np.arange(1, n + 1) - n - 1
    return np.mean(np.abs(x - y[:, None]), axis=1) - x @ coefficient / n**2


def interval_score(lower, upper, truth, alpha=0.1):
    lower, upper, truth = np.broadcast_arrays(lower, upper, truth)
    if np.any(lower > upper):
        raise ValueError("interval lower bound exceeds upper bound")
    return upper - lower + 2 / alpha * (np.maximum(lower - truth, 0) + np.maximum(truth - upper, 0))


def quantile_samples(quantiles, levels, draws=128):
    """Midpoint integration of piecewise-linear quantiles, constant outer tails.

    The tail convention is explicit, shared across arms, and not an exact CRPS
    for the unstored original predictive distribution.
    """
    levels = np.asarray(levels)
    q = np.asarray(quantiles)
    u = (np.arange(draws) + 0.5) / draws
    j = np.clip(np.searchsorted(levels, u) - 1, 0, len(levels) - 2)
    w = np.clip((u - levels[j]) / (levels[j + 1] - levels[j]), 0, 1)
    return q[:, j] * (1 - w) + q[:, j + 1] * w


def lower_bound_trend(years, observed, lower, *, minimum=5):
    """Gaussian trend likelihood with exact observations and Y >= L bounds.

    A fully observed window gives a LOWER bound on the annual maximum. Thus
    this is right censoring of the response and uses log survival, not log CDF.
    This is inspired by interval-data methods; it is not Bulletin 17C EMA.
    Returns NaNs if the trend is not identified or the optimizer fails.
    """
    years, observed, lower = map(lambda a: np.asarray(a, float), (years, observed, lower))
    exact = np.isfinite(observed)
    censored = ~exact & np.isfinite(lower)
    if exact.sum() < minimum or np.ptp(years[exact]) == 0:
        return dict(slope=np.nan, se=np.nan, converged=False, n_exact=int(exact.sum()), n_censored=int(censored.sum()))
    x = (years - np.mean(years)) / 10
    slope, intercept = np.polyfit(x[exact], observed[exact], 1)
    initial_sd = max(np.std(observed[exact] - intercept - slope * x[exact]), 0.05)

    def nll(theta):
        mu, sd = theta[0] + theta[1] * x, np.exp(theta[2])
        z = (observed[exact] - mu[exact]) / sd
        return float(np.sum(0.5 * z**2 + theta[2] + 0.5 * np.log(2 * np.pi)) - np.sum(log_ndtr((mu[censored] - lower[censored]) / sd)))

    result = minimize(nll, [intercept, slope, np.log(initial_sd)], method="BFGS", options={"gtol": 1e-6})
    # BFGS may report precision loss at an already stationary finite solution.
    converged = bool(np.isfinite(result.fun) and (result.success or np.linalg.norm(result.jac) < 1e-3))
    se = np.sqrt(max(float(result.hess_inv[1, 1]), 0)) if converged else np.nan
    return dict(slope=float(result.x[1]) if converged else np.nan, se=float(se), converged=converged, n_exact=int(exact.sum()), n_censored=int(censored.sum()))


def random_effects_ratio(observed, predicted, variance=None):
    """REML normal random effects for log(O/E), with t prediction interval.

    Inputs are group/region-level totals. Jeffreys half-event correction avoids
    log zero. Supplied sampling variances should reflect independent groups;
    absent that information, the Poisson approximation is only descriptive.
    """
    o, e = np.asarray(observed, float), np.asarray(predicted, float)
    valid = np.isfinite(o) & np.isfinite(e) & (e > 0)
    z = np.log((o[valid] + 0.5) / (e[valid] + 0.5))
    v = 1 / (o[valid] + 0.5) if variance is None else np.maximum(np.asarray(variance, float)[valid], 1e-8)
    k = len(z)
    if k < 3:
        return dict(n=k, ratio=np.nan, lower=np.nan, upper=np.nan, tau2=np.nan, probability_ratio_above_1p4=np.nan)

    def reml(tau2):
        w = 1 / (v + tau2)
        mu = np.sum(w * z) / w.sum()
        return 0.5 * (np.log(v + tau2).sum() + np.log(w.sum()) + np.sum(w * (z - mu)**2))

    fit = minimize_scalar(reml, bounds=(0, max(float(np.var(z) * 10), 1)), method="bounded")
    tau2 = float(fit.x) if reml(float(fit.x)) < reml(0) else 0.0
    w = 1 / (v + tau2)
    mu = float(np.average(z, weights=w))
    # Hartung-Knapp variance, conservatively no smaller than inverse information.
    var_mu = max(float(np.sum(w * (z - mu)**2) / (k - 1) / w.sum()), float(1 / w.sum()))
    scale = np.sqrt(tau2 + var_mu)
    critical = t.ppf(0.975, k - 2)
    return dict(n=k, ratio=float(np.exp(mu)), lower=float(np.exp(mu - critical * scale)), upper=float(np.exp(mu + critical * scale)), tau2=tau2, log_mean=mu, prediction_scale=float(scale), prediction_df=k - 2, probability_ratio_above_1p4=float(t.sf((np.log(1.4) - mu) / max(scale, 1e-12), k - 2)))


def removal_count(reference_sq, candidate_sq, reduction=0.0):
    """Exact minimum deletions until 1-sqrt(sum C / sum A) < reduction."""
    a, c = np.asarray(reference_sq), np.asarray(candidate_sq)
    delta = c - (1 - reduction)**2 * a
    if delta.sum() > 0:
        return 0
    remain = delta.sum() - np.cumsum(np.sort(delta))
    ids = np.flatnonzero(remain[:-1] > 1e-12)
    return int(ids[0] + 1) if len(ids) else None


def event_metrics(truth, prediction):
    truth, prediction = np.asarray(truth, bool), np.asarray(prediction, bool)
    hits, misses = np.sum(truth & prediction), np.sum(truth & ~prediction)
    false, correct = np.sum(~truth & prediction), np.sum(~truth & ~prediction)
    h = hits / (hits + misses) if hits + misses else np.nan
    f = false / (false + correct) if false + correct else np.nan
    # Half-count continuity correction, reported alongside the uncorrected rates.
    hc, fc = (hits + 0.5) / (hits + misses + 1), (false + 0.5) / (false + correct + 1)
    numerator = np.log(fc) - np.log(hc) - np.log1p(-fc) + np.log1p(-hc)
    denominator = np.log(fc) + np.log(hc) + np.log1p(-fc) + np.log1p(-hc)
    sedi=float(numerator/denominator) if hits+misses and false+correct else np.nan
    return dict(hits=int(hits), misses=int(misses), false_alarms=int(false), correct_negatives=int(correct), hit_rate=float(h), false_alarm_rate=float(f), sedi=sedi)
