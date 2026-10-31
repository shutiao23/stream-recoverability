"""Whole-archive masking, fixed-marginal joint draws and trend evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .ridge_history import YearExcludedRidge
from .statistics import interval_score


LEVELS = np.array([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])


def group_error_quantile(frame, level=0.95):
    """Give every calibration group equal total weight across repeated masks."""
    weights = 1 / frame.groupby("independence_group").error.transform("size").to_numpy(
        float
    )
    order = np.argsort(frame.error.abs().to_numpy())
    cumulative = np.cumsum(weights[order]) / weights.sum()
    return float(
        frame.error.abs().to_numpy()[order][np.searchsorted(cumulative, level)]
    )


def task_calibration_support(frame, min_source_groups=3, epsilon=1e-8):
    """Reject unsupported relative slope calibration before target scoring.

    A group is counted only if it contains a nondegenerate source interval.
    The empirical support check does not imply exchangeability or a guarantee.
    """
    pool = frame.loc[frame.reference_half_width.gt(epsilon) & frame.error.notna()].copy()
    groups = pool.independence_group.nunique()
    result = {"n_source_groups": groups,
              "n_source_station_repetitions": len(pool),
              "n_degenerate_source_repetitions": len(frame) - len(pool)}
    if groups < min_source_groups:
        return result | {"status": "insufficient_source_groups"}, pool
    radius = group_error_quantile(pool)
    if not np.isfinite(radius) or radius <= epsilon:
        return result | {"scale_factor": radius, "status": "degenerate_source_errors"}, pool
    low, high = np.quantile(pool.reference_half_width, [0.01, 0.99])
    return result | {"scale_factor": radius, "minimum_supported_half_width": float(low),
                     "maximum_supported_half_width": float(high), "status": "supported"}, pool


def mask_archive(panel, station, masks):
    """Hide all selected years before passing the archive to a fitting routine."""
    visible = panel.copy()
    for year, runs in masks.items():
        positions = np.flatnonzero(visible.index.year == year)
        for run in str(runs).split(";"):
            if run:
                start, length = map(int, run.split(":"))
                visible.iloc[
                    positions[start : start + length], visible.columns.get_loc(station)
                ] = np.nan
    return visible


def apply_observed_lower_bound(quantiles, lower_bounds):
    """Project values onto the support implied by finite observed windows.

    Rows with no fully observed window have no known bound; missing predictions
    remain missing.  This operation applies equally to both annual estimators.
    """
    values = np.asarray(quantiles, dtype=float)
    bounds = np.asarray(lower_bounds, dtype=float)
    if values.ndim != 2 or bounds.shape != (values.shape[0],):
        raise ValueError("Expected one lower bound per quantile row")
    return np.where(np.isfinite(bounds[:, None]), np.maximum(values, bounds[:, None]), values)


def marginal_draws(quantiles, draws=256, tails="normal", lower_bounds=None):
    """Fixed stratified samples, with explicit outer-tail and support assumptions.

    The seven stored quantiles do not identify their outer 5% tails.  The
    default extends the two tails using the neighboring normal-quantile
    spacings; this is a modeling assumption, not a coverage guarantee.  The
    original endpoint extension is retained as ``tails='constant'`` for a
    paired sensitivity.  Finite observed-window bounds constrain both tails.
    """
    if tails not in {"constant", "normal"}:
        raise ValueError(f"Unknown tail model: {tails}")
    quantiles = np.asarray(quantiles, dtype=float)
    if lower_bounds is not None:
        quantiles = apply_observed_lower_bound(quantiles, lower_bounds)
    u = (np.arange(draws) + 0.5) / draws
    result = np.column_stack([np.interp(u, LEVELS, q) for q in quantiles])
    if tails == "normal":
        z = norm.ppf(u)
        z_levels = norm.ppf(LEVELS)
        low = u < LEVELS[0]
        high = u > LEVELS[-1]
        for j, q in enumerate(quantiles):
            scale_low = (q[1] - q[0]) / (z_levels[1] - z_levels[0])
            scale_high = (q[-1] - q[-2]) / (z_levels[-1] - z_levels[-2])
            result[low, j] = q[0] + scale_low * (z[low] - z_levels[0])
            result[high, j] = q[-1] + scale_high * (z[high] - z_levels[-1])
    if lower_bounds is not None:
        bounds = np.asarray(lower_bounds, dtype=float)
        result = np.where(np.isfinite(bounds)[None, :], np.maximum(result, bounds[None, :]), result)
    return result


def reorder_marginals(samples, ranks):
    """Change only the joint ranks, preserving every sampled annual marginal."""
    out = np.empty_like(samples)
    for j in range(samples.shape[1]):
        order = np.argsort(ranks[:, j], kind="stable")
        out[order, j] = np.sort(samples[:, j])
    return out


def history_ranks(
    target, air, masks, years, *, draws=256, seed=0, block=1, fit_before=None
):
    """Shared year-bootstrap regression states and visible residual histories.

    Only the already-masked target enters this function. Whole-year bootstrap
    weights provide one common fitted state per draw. Ordered annual OOF mean
    residuals supply either independent or contiguous three-year innovations.
    These ranks are an empirical dependence sensitivity, not a coverage theorem.
    """
    index = target.index
    doy = index.dayofyear.to_numpy()
    columns = [
        np.ones(len(index)),
        np.sin(2 * np.pi * doy / 365.25),
        np.cos(2 * np.pi * doy / 365.25),
    ]
    if air is not None:
        columns.append(air.reindex(index).to_numpy(float))
    x = np.column_stack(columns)
    training_target = target.to_numpy(float).copy()
    if fit_before is not None:
        training_target[index.year >= fit_before] = np.nan
    model = YearExcludedRidge(x[:, 1:], training_target, index.year)
    history_years = np.unique(index.year[model.valid])
    residual = model.residual_history(-1, history_years)
    annual = pd.Series(residual, index=index).groupby(index.year).agg(["mean", "count"])
    annual = annual.loc[annual["count"] >= 180, "mean"].dropna()
    # Gaps in the historical calendar cannot become artificial adjacent years.
    starts = [
        i
        for i in range(len(annual) - block + 1)
        if annual.index[i + block - 1] - annual.index[i] == block - 1
    ]
    if not starts:
        return None
    gap_x = []
    for year in years:
        held = index.year == year
        hidden = np.zeros(len(index), bool)
        positions = np.flatnonzero(held)
        for run in str(masks.get(year, "")).split(";"):
            if run:
                start, length = map(int, run.split(":"))
                hidden[positions[start : start + length]] = True
        good = hidden & np.isfinite(x).all(axis=1)
        gap_x.append(x[good].mean(axis=0) if good.any() else np.zeros(x.shape[1]))
    gap_x = np.asarray(gap_x)
    stats = []
    for year in history_years:
        selected = model.valid & (index.year == year)
        stats.append(
            (x[selected].T @ x[selected], x[selected].T @ training_target[selected])
        )
    rng = np.random.default_rng(seed)
    ranks = np.empty((draws, len(years)))
    penalty = np.eye(x.shape[1])
    penalty[0, 0] = 0
    # Blocks advance by actual calendar distance, including skipped reference years.
    offsets = np.asarray(years) - min(years)
    span = int(offsets.max()) + 1
    history = annual.to_numpy()
    for draw in range(draws):
        weights = rng.multinomial(len(stats), np.full(len(stats), 1 / len(stats)))
        xx = sum(w * s[0] for w, s in zip(weights, stats))
        xy = sum(w * s[1] for w, s in zip(weights, stats))
        coefficients = np.linalg.solve(xx + penalty, xy)
        sequence = np.concatenate(
            [
                history[i : i + block]
                for i in rng.choice(starts, int(np.ceil(span / block)))
            ]
        )[:span]
        ranks[draw] = gap_x @ coefficients + sequence[offsets]
    return ranks


def slope(years, values):
    x = (np.asarray(years, float) - np.mean(years)) / 10
    return np.asarray(values) @ x / (x @ x)


def trend_result(years, truth, point, samples=None):
    """Target the finite complete record; exclude climate regression noise."""
    reference = float(slope(years, truth))
    estimate = float(slope(years, point))
    row = {
        "truth_slope": reference,
        "slope": estimate,
        "error": estimate - reference,
        "squared_error": (estimate - reference) ** 2,
    }
    if samples is not None:
        slopes = slope(years, samples)
        low, high = np.quantile(slopes, [0.025, 0.975])
        row.update(
            lower95=float(low),
            upper95=float(high),
            width95=float(high - low),
            missing_coverage95=bool(low - 1e-12 <= reference <= high + 1e-12),
            interval_score95=float(interval_score(low, high, reference, alpha=0.05)),
        )
    return row


def factorial_contrasts(table):
    """Paired retention effects, estimator effects and symmetric MSE decomposition."""
    keys = (["family"] if "family" in table else []) + [
        "mode",
        "station_key",
        "replicate",
    ]
    pivot = table.pivot(
        index=keys, columns=["retention", "estimator"], values="squared_error"
    )
    rows = []
    for index, row in pivot.iterrows():
        a = row.get(("warm90", "plug_in"), np.nan)
        b = row.get(("all", "plug_in"), np.nan)
        for estimator in ["stochastic_calibrated", "D2"]:
            c = row.get(("warm90", estimator), np.nan)
            d = row.get(("all", estimator), np.nan)
            rows.append(
                dict(
                    zip(keys, index),
                    estimator=estimator,
                    retention_at_plugin=a - b,
                    retention_at_estimator=c - d,
                    estimator_at_warm90=a - c,
                    estimator_at_all=b - d,
                    interaction=(a - b) - (c - d),
                    symmetric_retention=((a - b) + (c - d)) / 2,
                    symmetric_estimator=((a - c) + (b - d)) / 2,
                    total_gain=a - d,
                )
            )
    return pd.DataFrame(rows)
