"""D1: a recovery law for the plug-in H30 error built only from training-period quantities.

Write daily water temperature as season plus anomaly a with warm-season
variance sigma_a^2, and the reconstruction residual r = centre - truth with
mean mu_r, variance sigma_r^2 and lag-one correlation phi_r. For a
conditional-mean reconstructor R^2 = 1 - sigma_r^2 / sigma_a^2 and
E[r | a] = -(1 - R^2) a: the reconstruction regresses hidden anomalies towards
the seasonal cycle. If a share h of the true peak window is hidden and the
window anomaly is a_peak, the plug-in error of the window mean is

    e ~ N( h (mu_r - (1 - R^2) a_peak),  h^2 sigma_r^2 R^2 v(30h, phi_r) ),

with v(m, phi) the variance factor of an m-day mean of an AR(1) process (v1).
Because the peak is selected on the 30-day mean, v2 replaces the daily
shrinkage 1 - R^2 by the window-scale slope of the hidden residual mean on the
window anomaly (see component_moments). The
position and the anomaly of the target year's peak are unknown, so the law
mixes over the training years' own (h_y, a_y) pairs. Because the true H30 is
at least the best fully observed window L, e <= P0 - L truncates the upper
tail. No parameter is fitted to reconstruction errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


def variance_factor(m: np.ndarray, phi: float) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    out = np.ones_like(m)
    phi = float(np.clip(phi if np.isfinite(phi) else 0.0, -0.99, 0.999))
    for i, value in enumerate(m):
        n = int(round(value))
        if n <= 1:
            out[i] = 1.0
            continue
        j = np.arange(1, n)
        out[i] = (n + 2 * np.sum((n - j) * phi**j)) / n**2
    return out


def parse(text: str) -> np.ndarray:
    return np.array([float(v) for v in str(text).split(";") if v not in ("", "nan")], dtype=float)


def cross_factor(m: np.ndarray, phi: float, window: int = 30) -> np.ndarray:
    """(1 / (window m)) sum over m hidden days at one end of the window and all window days of phi^|t-s|."""

    phi = float(np.clip(phi if np.isfinite(phi) else 0.0, -0.99, 0.999))
    lags = np.abs(np.arange(window)[:, None] - np.arange(window)[None, :])
    powers = phi**lags
    cumulative = np.cumsum(powers.sum(axis=1))
    out = np.zeros(len(np.atleast_1d(m)))
    for i, value in enumerate(np.atleast_1d(m)):
        n = int(round(value))
        out[i] = cumulative[n - 1] / (window * n) if n >= 1 else 0.0
    return out


def component_moments(shares: np.ndarray, anomalies: np.ndarray, row: pd.Series, version: str, window: int = 30) -> tuple[np.ndarray, np.ndarray, float]:
    """Mean and sd of the plug-in error for each training-year peak configuration.

    v1 shrinks the hidden anomaly at the daily scale, (1 - R^2). v2 conditions
    on the 30-day window mean, the quantity that selects the peak: the hidden
    residual mean regresses on the window anomaly with slope
    sigma_r^2 c(m, phi_r) / (sigma_a^2 v(30, phi_a)). v2p (round 2) replaces the
    warm-season moments by the residual moments inside the training years' own
    peak windows, which captures heteroscedastic and state-dependent residuals.
    """

    sigma_a, sigma_r = float(row.law_sigma_a), float(row.law_sigma_r_warm)
    mu = float(row.law_mu_r_warm) if np.isfinite(row.law_mu_r_warm) else 0.0
    r2 = float(np.clip(1 - sigma_r**2 / sigma_a**2, 0.0, 1.0))
    m = window * shares
    if version == "v2p":
        # Peak-conditional moments: the residual mean and spread inside the training years' own
        # peak windows already contain the regression towards the seasonal cycle at the peak,
        # so no shrinkage term is added. Falls back to v2 when they are unavailable.
        mu_peak, sigma_peak = row.get("law_mu_r_peak", np.nan), row.get("law_sigma_r_peak", np.nan)
        if np.isfinite(mu_peak) and np.isfinite(sigma_peak) and sigma_peak > 0:
            means = shares * float(mu_peak)
            variance = shares**2 * float(sigma_peak) ** 2 * variance_factor(m, row.law_phi_r)
            return means, np.sqrt(variance), r2
        version = "v2"
    if version == "v1":
        means = shares * (mu - (1 - r2) * anomalies)
        variance = shares**2 * sigma_r**2 * max(r2, 0.05) * variance_factor(m, row.law_phi_r)
        return means, np.sqrt(variance), r2
    window_var = sigma_a**2 * variance_factor(np.array([float(window)]), row.law_phi_a)[0]
    covariance = sigma_r**2 * cross_factor(m, row.law_phi_r,window)
    slope = np.clip(covariance / window_var, 0.0, 1.0)
    means = shares * (mu - slope * anomalies)
    residual_var = sigma_r**2 * variance_factor(m, row.law_phi_r) - covariance**2 / window_var
    variance = shares**2 * np.maximum(residual_var, 0.05 * sigma_r**2 * variance_factor(m, row.law_phi_r))
    return means, np.sqrt(variance), r2


def case_law(row: pd.Series, tolerance: float = 0.5, truncate: bool = True, version: str = "v2") -> dict[str, float]:
    shares, anomalies = parse(row.law_hidden_shares), parse(row.law_peak_anomalies)
    sigma_a, sigma_r = float(row.law_sigma_a), float(row.law_sigma_r_warm)
    if not len(shares) or len(shares) != len(anomalies) or not np.isfinite(sigma_a) or not np.isfinite(sigma_r) or sigma_a <= 0:
        return {"law_bias": np.nan, "law_sd": np.nan, "law_pfail": np.nan, "law_r2": np.nan}
    window=int(row.get("primary_window_days",30))
    means, sds, r2 = component_moments(shares, anomalies, row, version,window)
    sds = np.maximum(sds, 1e-3)
    upper = np.inf
    if truncate and np.isfinite(row.get("observed_lower_bound__observed_days", np.nan)):
        upper = max(float(row.h30__policy - row["observed_lower_bound__observed_days"]), 0.0)
    cdf_upper = norm.cdf((upper - means) / sds) if np.isfinite(upper) else np.ones_like(means)
    cdf_upper = np.maximum(cdf_upper, 1e-9)
    low = norm.cdf((-tolerance - means) / sds)
    high = np.clip(cdf_upper - norm.cdf((tolerance - means) / sds), 0, None)
    pfail = np.mean((low + high) / cdf_upper)
    # Mean of each truncated component, then the mixture mean and variance.
    if np.isfinite(upper):
        beta = (upper - means) / sds
        truncated_mean = means - sds * norm.pdf(beta) / cdf_upper
    else:
        truncated_mean = means
    bias = float(np.mean(truncated_mean))
    sd = float(np.sqrt(np.mean(sds**2 + truncated_mean**2) - bias**2))
    return {"law_bias": bias, "law_sd": sd, "law_pfail": float(pfail), "law_r2": r2}


def apply_law(cases: pd.DataFrame, tolerance: float = 0.5, truncate: bool = True, version: str = "v2") -> pd.DataFrame:
    if version == "v3":
        rows = [replay_law(row, tolerance) for _, row in cases.iterrows()]
        return pd.DataFrame(rows, index=cases.index)
    rows = [case_law(row, tolerance, truncate, version) for _, row in cases.iterrows()]
    return pd.DataFrame(rows, index=cases.index)


def replay_law(row: pd.Series, tolerance: float = 0.5) -> dict[str, float]:
    """v3: the empirical error of the same mask replayed on the training years, kernel-smoothed."""

    errors = parse(row.get("law_replay_errors", ""))
    if len(errors) < 2:
        return {"law_bias": np.nan, "law_sd": np.nan, "law_pfail": np.nan, "law_r2": np.nan}
    spread = min(errors.std(ddof=1), (np.quantile(errors, 0.75) - np.quantile(errors, 0.25)) / 1.34) if errors.std(ddof=1) > 0 else 0.0
    bandwidth = max(0.05, 0.9 * spread * len(errors) ** -0.2)
    pfail = np.mean(norm.cdf((-tolerance - errors) / bandwidth) + 1 - norm.cdf((tolerance - errors) / bandwidth))
    return {"law_bias": float(errors.mean()), "law_sd": float(np.sqrt(errors.var(ddof=1) + bandwidth**2)), "law_pfail": float(pfail), "law_r2": np.nan}
