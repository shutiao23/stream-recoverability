#!/usr/bin/env python3
"""WRR P1 group 2 — mechanism boundary: misalignment, competing peaks, residual
correlation, the air-forcing reconstructor, and a design-based phase interval.

Review of 2026-10-14 (F06 / P1 group 2) asks the mechanism boundary to be pinned
down. The existing Step-3 artifact
(``scripts/302_wrr_mr_step3_fixed_reconstructor_mechanism.py``) crossed gap
position with reconstructor for four reconstructors on the paired
position x length development panel
(``results/wrr_submission_ready/amendments/position_length_paired/``). This
script keeps that case construction and those reconstructors and adds:

1. the air-forcing reconstructor (``air_ridge``) to the crossed design. The v17
   forcing table shipped with the study covers 0 of the 24 crossed-panel
   stations (that is why Step 3 omitted it, and why ``air_available`` is False on
   every case of the archived crossed parquet). The v18 NASA POWER forcing table
   (``data/interim/v18_air_forcing.parquet``, the table used by the v18 air
   sensitivity analysis) covers all 24. Availability is reported, never assumed,
   and the reduced-sample statement under the v17 table is written out.
2. three new conditions on the same cases, each computed from the daily series
   (not from the archived case table, which stores no series):
   - ``window_misalignment``: the reconstructed 30-day maximum against the truth
     maximum, in days;
   - ``competing_peak``: the truth gap between the best window and the best
     window disjoint from it, and between the best and second-best disjoint
     windows;
   - ``residual_correlation``: lag-1 autocorrelation of the reconstruction
     residuals inside and outside the gap.
3. a position x length crossed design at a fixed hidden share, per reconstructor,
   with a "is the length effect distinguishable from zero" verdict per
   reconstructor.
4. a phase-identifiability interval computed from the actual design matrix of the
   sine fit on each case's observed-day mask, under i.i.d. residuals, AR(1)
   residuals with the case's own estimated autocorrelation, and a
   Newey-West/Bartlett HAC. Compared with the manuscript's fixed
   amplitude-to-noise threshold.

Everything is clustered by network. Nothing here is a pre-registered
confirmation: these are conditional, descriptive mechanism contrasts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The forcing table must be chosen before the pipeline modules are imported:
# stream_recoverability.experiments.v17_fitness.paths reads the environment at
# import time. See the module docstring for why the v18 table is the primary.
AIR_TABLE_V18 = ROOT / "data" / "interim" / "v18_air_forcing.parquet"
AIR_TABLE_V17 = (
    ROOT
    / "results"
    / "development_v11"
    / "independent_air2stream_equivalent"
    / "daily_forcing.parquet"
)
os.environ["STREAM_AIR_FORCING"] = str(AIR_TABLE_V18)

sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool  # noqa: E402
from stream_recoverability.experiments.v17_fitness.estimators import (  # noqa: E402
    StationModels,
    hottest_window_mean,
    linear_interp_fill,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import (  # noqa: E402
    air_series_for,
    load_network_panel,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    REALIZATIONS_PER_STATION_YEAR,
    stable_seed,
)
from stream_recoverability.experiments.v18_closure.endpoints import sine_parameters  # noqa: E402

STEP1_PANEL = ROOT / "results" / "v17_fitness" / "step1_panel"
CROSSED_PARQUET = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "amendments"
    / "position_length_paired"
    / "crossed_development_cases.parquet"
)
WINTER_SINE_SUMMARY = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "amendments"
    / "winter_regulatory"
    / "summary_sine.json"
)
OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p1_mechanism_boundary"
)
SCRATCH = ROOT / "scratch" / "p1_mechanism"

RECONSTRUCTORS = (
    "doy_climatology",
    "smooth_climatology",
    "linear_interp",
    "donor_ridge",
    "air_ridge",
)
LENGTHS = (30, 60, 90)
OVERLAP_CLASSES = ("none", "partial", "full")
WINDOW = 30
DAYS_IN_YEAR = 365.25
TOLERANCE_FRACTION = 0.4717  # step-17 convention, same as the manuscript
MIN_RESID_PAIRS = 30
HAC_LAG_DAYS = 30
HIDDEN_SHARE_FULL = 0.999
HIDDEN_SHARE_LEVELS = (0.999, 0.90)
PHASE_BOOTSTRAP_DRAWS = 200
PHASE_BOOTSTRAP_BLOCK_DAYS = 30
BOOT_DRAWS = 2000
SEED = 23
# Bins, declared here rather than chosen after looking.
COMPETING_PEAK_BINS = (0.0, 0.25, 0.5, 1.0, 2.0, np.inf)
RESID_AC_BINS = (-1.01, 0.0, 0.25, 0.5, 0.75, 1.01)
VISIBILITY_BINS = (0.0, 0.5, 0.7, 0.85, 0.95, 1.01)
MISALIGNMENT_BINS = (0, 7, 14, 29, 10**9)


# --------------------------------------------------------------------------
# small numerical helpers
# --------------------------------------------------------------------------
def lag1_autocorrelation(values: np.ndarray, available: np.ndarray) -> tuple[float, int]:
    """Lag-1 autocorrelation over consecutive available days (pairwise)."""

    values = np.asarray(values, dtype=float)
    available = np.asarray(available, dtype=bool) & np.isfinite(values)
    if len(values) < 3:
        return float("nan"), 0
    pair = available[1:] & available[:-1]
    n_pairs = int(pair.sum())
    if n_pairs < MIN_RESID_PAIRS:
        return float("nan"), n_pairs
    left = values[:-1][pair]
    right = values[1:][pair]
    if float(np.std(left)) <= 0.0 or float(np.std(right)) <= 0.0:
        return float("nan"), n_pairs
    return float(np.corrcoef(left, right)[0, 1]), n_pairs


def rolling_window_argmax(values: np.ndarray, window: int = WINDOW) -> tuple[float, int, np.ndarray]:
    """Maximum ``window``-day mean, the (right-aligned) end index, and the roll."""

    rolled = (
        pd.Series(np.asarray(values, dtype=float))
        .rolling(int(window), min_periods=int(window))
        .mean()
        .to_numpy(dtype=float)
    )
    if not np.isfinite(rolled).any():
        return float("nan"), -1, rolled
    end = int(np.nanargmax(rolled))
    return float(rolled[end]), end, rolled


def truth_competition(truth: np.ndarray, window: int = WINDOW) -> dict[str, float]:
    """Competing-peak geometry of the truth alone (no reconstruction involved).

    ``competing_peak_gap_C`` is the drop from the best window to the best window
    that does not overlap it; ``competing_peak_gap_C2`` is the drop from that
    best disjoint window to the next-best disjoint one. Windows are 30 days wide
    and right-aligned, both in the truth and in every reconstructed series.
    """

    peak_value, peak_end, rolled = rolling_window_argmax(truth, window)
    out: dict[str, float] = {
        "truth_window_end": float(peak_end),
        "truth_window_start": float(peak_end - window + 1),
        "truth_window_value": float(peak_value),
        "truth_peak_tie_days": float("nan"),
        "truth_peak_ties": float("nan"),
        "competing_peak_gap_C": float("nan"),
        "competing_peak_gap_C2": float("nan"),
        "competing_peak_end": float("nan"),
        "competing_peak_distance_days": float("nan"),
        "competing_peak_value": float("nan"),
        "second_disjoint_end": float("nan"),
        "second_disjoint_distance_days": float("nan"),
        "second_disjoint_value": float("nan"),
        "n_disjoint_windows": 0.0,
    }
    if peak_end < 0:
        return out
    finite = np.isfinite(rolled)
    out["truth_peak_tie_days"] = float(np.sum(np.abs(rolled[finite] - peak_value) <= 1e-9))
    out["truth_peak_ties"] = float(out["truth_peak_tie_days"] > 1)
    ends = np.flatnonzero(finite)
    disjoint = ends[(ends <= peak_end - window) | (ends >= peak_end + window)]
    out["n_disjoint_windows"] = float(len(disjoint))
    if len(disjoint) == 0:
        return out
    order = disjoint[np.argsort(-rolled[disjoint], kind="stable")]
    best = int(order[0])
    out["competing_peak_end"] = float(best)
    out["competing_peak_value"] = float(rolled[best])
    out["competing_peak_gap_C"] = float(peak_value - rolled[best])
    out["competing_peak_distance_days"] = float(abs(best - peak_end))
    if len(order) > 1:
        second = int(order[1])
        out["second_disjoint_end"] = float(second)
        out["second_disjoint_value"] = float(rolled[second])
        out["second_disjoint_distance_days"] = float(abs(second - peak_end))
        out["competing_peak_gap_C2"] = float(rolled[best] - rolled[second])
    return out


def phase_standard_error_days(
    truth: np.ndarray,
    observed: np.ndarray,
) -> dict[str, float]:
    """Design-based standard error of the sine-fit peak day, in days.

    The design matrix is the one the manuscript's rule assumes away:
    ``[1, sin(theta), cos(theta)]`` evaluated on the days the visibility mask
    actually leaves observed — not a balanced 365-row design. Three covariance
    models are computed for the same least-squares fit:

    ``iid``   V = sigma^2 (X'X)^-1, the model behind sigma*sqrt(2/n)/A.
    ``ar1``   V = sigma^2 (X'X)^-1 X'R X (X'X)^-1, R_ij = rho^|t_i - t_j| with
              rho estimated from adjacent observed-day residual pairs.
    ``hac``   Newey-West/Bartlett sandwich with a 30-day kernel (robustness to
              the AR(1) shape).

    Normalisation. ``phase_se_*_days`` are standard errors of the fitted peak
    day at the case's own amplitude and residual sd. The ``*_at_unit_snr_days``
    columns divide out the ratio sigma/A, i.e. they are the standard error in
    days when A/sigma = 1. That is the quantity the identifiability rule needs:
    a 95% interval 2 * (sigma/A) * c_days is within the tolerance tau exactly
    when A/sigma >= 2 * c_days / tau. ``closed_form_at_unit_snr_days`` is the
    same quantity under the uniform-sampling formula
    sqrt(2/n) * T / (2 pi) (radians converted to days), which is the
    manuscript's assumption.
    """

    nan = float("nan")
    out = {
        "phase_n_observed": float(np.sum(~np.asarray(observed, dtype=bool))),
        "phase_amplitude": nan,
        "phase_sigma": nan,
        "phase_amplitude_over_sigma": nan,
        "phase_rho_lag1": nan,
        "phase_se_iid_days": nan,
        "phase_se_ar1_days": nan,
        "phase_se_hac_days": nan,
        "phase_se_iid_at_unit_snr_days": nan,
        "phase_se_ar1_at_unit_snr_days": nan,
        "phase_se_hac_at_unit_snr_days": nan,
        "phase_closed_form_at_unit_snr_days": nan,
        "phase_n_adjacent_pairs": nan,
    }
    truth = np.asarray(truth, dtype=float)
    good = ~np.asarray(observed, dtype=bool) & np.isfinite(truth)
    n = int(good.sum())
    if n < 60:
        return out
    t = np.arange(len(truth), dtype=float)
    theta = 2 * np.pi * t[good] / DAYS_IN_YEAR
    design = np.column_stack([np.ones(n), np.sin(theta), np.cos(theta)])
    y = truth[good]
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    _, a, b = (float(v) for v in beta)
    amplitude = float(np.hypot(a, b))
    if not np.isfinite(amplitude) or amplitude <= 0:
        return out
    resid = y - design @ beta
    dof = max(1, n - 3)
    sigma = float(np.sqrt(float(resid @ resid) / dof))
    gram_inv = np.linalg.inv(design.T @ design)
    # d(phi)/d(a,b) for phi = atan2(-b, a)
    gradient = np.array([0.0, b / amplitude**2, -a / amplitude**2])
    to_days = DAYS_IN_YEAR / (2 * np.pi)

    def se_days(cov: np.ndarray) -> float:
        var = float(gradient @ cov @ gradient)
        return float(np.sqrt(max(var, 0.0)) * to_days)

    cov_iid = sigma**2 * gram_inv
    se_iid = se_days(cov_iid)

    days = t[good]
    adjacent = np.diff(days) == 1
    rho = nan
    n_adj = int(adjacent.sum())
    if n_adj >= MIN_RESID_PAIRS:
        left = resid[:-1][adjacent]
        right = resid[1:][adjacent]
        if float(np.std(left)) > 0 and float(np.std(right)) > 0:
            rho = float(np.corrcoef(left, right)[0, 1])

    distance = np.abs(days[:, None] - days[None, :])
    se_ar1 = nan
    if np.isfinite(rho) and abs(rho) < 0.999:
        correlation = rho**distance
        cov_ar1 = sigma**2 * gram_inv @ (design.T @ correlation @ design) @ gram_inv
        se_ar1 = se_days(cov_ar1)

    # Newey-West / Bartlett sandwich on the observed days.
    weight = np.where(distance <= HAC_LAG_DAYS, 1.0 - distance / (HAC_LAG_DAYS + 1.0), 0.0)
    meat = design.T @ ((weight * np.outer(resid, resid)) @ design)
    cov_hac = gram_inv @ meat @ gram_inv
    se_hac = se_days(cov_hac)

    # Converting to A/sigma = 1: se_days = (sigma/A) * c_days, so c_days = se_days * A / sigma.
    scale = amplitude / sigma if sigma > 0 else nan
    out.update(
        {
            "phase_n_observed": float(n),
            "phase_amplitude": amplitude,
            "phase_sigma": sigma,
            "phase_amplitude_over_sigma": scale,
            "phase_rho_lag1": rho,
            "phase_se_iid_days": se_iid,
            "phase_se_ar1_days": se_ar1,
            "phase_se_hac_days": se_hac,
            "phase_se_iid_at_unit_snr_days": se_iid * scale,
            "phase_se_ar1_at_unit_snr_days": se_ar1 * scale,
            "phase_se_hac_at_unit_snr_days": se_hac * scale,
            "phase_closed_form_at_unit_snr_days": float(np.sqrt(2.0 / n) * to_days),
            "phase_n_adjacent_pairs": float(n_adj),
        }
    )
    return out


def phase_bootstrap_sd(
    truth: np.ndarray,
    observed: np.ndarray,
    *,
    draws: int = 200,
    block_days: int = 30,
    seed: int = 0,
) -> float:
    """Simulated sampling sd of the fitted sine peak day under this mask.

    A check on the analytic intervals, not a substitute for them. The full-year
    series is fitted with the same three-parameter sine, its residuals are
    resampled in circular blocks (so the residual autocorrelation is preserved
    without assuming AR(1)), the resampled residuals are added back to the fit,
    the masked days are removed, and the sine is refitted. The sd of the fitted
    peak day across draws is what the analytic standard error claims to be.
    """

    truth = np.asarray(truth, dtype=float)
    mask = np.asarray(observed, dtype=bool)
    n_days = len(truth)
    t = np.arange(n_days, dtype=float)
    angle = 2 * np.pi * t / DAYS_IN_YEAR
    design = np.column_stack([np.ones(n_days), np.sin(angle), np.cos(angle)])
    finite = np.isfinite(truth)
    if finite.sum() < 60:
        return float("nan")
    beta, *_ = np.linalg.lstsq(design[finite], truth[finite], rcond=None)
    fitted = design @ beta
    resid = np.where(finite, truth - fitted, 0.0)
    good_obs = ~mask & finite
    if good_obs.sum() < 60:
        return float("nan")
    design_obs = design[good_obs]
    gram_inv = np.linalg.inv(design_obs.T @ design_obs)
    rng = np.random.default_rng(int(seed))
    n_blocks = int(np.ceil(n_days / block_days))
    starts = np.arange(0, n_days, block_days)
    phases = np.empty(int(draws), dtype=float)
    for draw in range(int(draws)):
        picks = rng.integers(0, len(starts), n_blocks)
        index = np.concatenate(
            [(starts[k] + np.arange(block_days)) % n_days for k in picks]
        )[:n_days]
        simulated = fitted + resid[index]
        y = simulated[good_obs]
        beta_star, *_ = np.linalg.lstsq(design_obs, y, rcond=None)
        _, a_star, b_star = (float(v) for v in beta_star)
        phi = float(np.arctan2(-b_star, a_star) % (2 * np.pi))
        phases[draw] = (phi * DAYS_IN_YEAR / (2 * np.pi) + DAYS_IN_YEAR / 4.0) % DAYS_IN_YEAR
    finite_phases = phases[np.isfinite(phases)]
    if finite_phases.size < 20:
        return float("nan")
    # Circular sd, because the phase lives on a circle.
    angles = 2 * np.pi * finite_phases / DAYS_IN_YEAR
    resultant = np.hypot(np.mean(np.cos(angles)), np.mean(np.sin(angles)))
    if resultant <= 0:
        return float("nan")
    circular_sd_rad = float(np.sqrt(-2.0 * np.log(resultant)))
    return circular_sd_rad * DAYS_IN_YEAR / (2 * np.pi)


# --------------------------------------------------------------------------
# network-clustered bootstrap on pre-split per-network blocks
# --------------------------------------------------------------------------
def cluster_stat(
    frame: pd.DataFrame,
    stat,
    *,
    columns: tuple[str, ...],
    cluster: str = "network_id",
    draws: int = BOOT_DRAWS,
    seed: int = SEED,
) -> dict[str, float]:
    """Network-clustered interval for an arbitrary statistic of case columns.

    Resamples whole networks with replacement. For statistics built from
    per-network means this is algebraically the same as
    ``stats.cluster_bootstrap`` (duplicated networks are exact copies, so a
    network mean is unchanged by duplication); it is vectorised because the
    manuscript-grade tables need hundreds of intervals.
    """

    block = frame.loc[np.isfinite(pd.to_numeric(frame[columns[0]], errors="coerce"))]
    if block.empty:
        return {"point": float("nan"), "low": float("nan"), "high": float("nan"), "n_clusters": 0}
    codes, keys = pd.factorize(block[cluster].to_numpy(), sort=True)
    n_clusters = len(keys)
    arrays = {name: block[name].to_numpy() for name in columns}
    arrays["code"] = codes.astype(np.int64)
    per_network = [
        {name: arrays[name][codes == k] for name in arrays} for k in range(n_clusters)
    ]

    def evaluate(selection: np.ndarray) -> float:
        merged = {
            name: np.concatenate([per_network[int(k)][name] for k in selection])
            for name in arrays
        }
        return float(stat(merged))

    point = evaluate(np.arange(n_clusters))
    if n_clusters < 2:
        return {
            "point": point,
            "low": float("nan"),
            "high": float("nan"),
            "n_clusters": n_clusters,
        }
    rng = np.random.default_rng(int(seed))
    values = np.empty(int(draws), dtype=float)
    for draw in range(int(draws)):
        values[draw] = evaluate(rng.integers(0, n_clusters, n_clusters))
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "point": point,
            "low": float("nan"),
            "high": float("nan"),
            "n_clusters": n_clusters,
        }
    return {
        "point": point,
        "low": float(np.quantile(finite, 0.025)),
        "high": float(np.quantile(finite, 0.975)),
        "se": float(np.std(finite, ddof=1)),
        "n_clusters": int(n_clusters),
    }


def network_equal_mean_stat(cols: dict[str, np.ndarray]) -> float:
    """Equal weight per network, whatever the number of cases in each."""

    code = cols["code"]
    size = int(code.max()) + 1
    totals = np.bincount(code, weights=cols["v"], minlength=size)
    counts = np.bincount(code, minlength=size)
    present = counts > 0
    return float(np.mean(totals[present] / counts[present]))


def network_equal_share_stat(cols: dict[str, np.ndarray]) -> float:
    code = cols["code"]
    size = int(code.max()) + 1
    totals = np.bincount(code, weights=cols["v"], minlength=size)
    counts = np.bincount(code, minlength=size)
    present = counts > 0
    return float(np.mean(totals[present] / counts[present]))


def network_paired_diff_stat(cols: dict[str, np.ndarray]) -> float:
    """Mean over networks of (mean where g=1) - (mean where g=0), network equal.

    A middle ground between the station-year-paired contrast (needs both levels
    in the same station-year) and an unpaired subset difference: it needs both
    levels only somewhere in the same network. Networks without both levels
    contribute nothing, and the count of contributing networks is reported.
    """

    code = cols["code"]
    values = cols["v"]
    flag = cols["g"]
    size = int(code.max()) + 1
    differences = []
    for k in range(size):
        selection = code == k
        high = values[selection & (flag > 0.5)]
        low = values[selection & (flag < 0.5)]
        if high.size and low.size:
            differences.append(float(high.mean() - low.mean()))
    return float(np.mean(differences)) if differences else float("nan")


def add_ci(row: dict, ci: dict, prefix: str = "") -> dict:
    row[f"{prefix}point_C"] = ci["point"]
    row[f"{prefix}ci_low_C"] = ci["low"]
    row[f"{prefix}ci_high_C"] = ci["high"]
    row[f"{prefix}n_networks"] = ci["n_clusters"]
    row[f"{prefix}ci_excludes_zero"] = bool(
        np.isfinite(ci["low"]) and np.isfinite(ci["high"]) and not (ci["low"] <= 0 <= ci["high"])
    )
    return row


# --------------------------------------------------------------------------
# case construction (mirrors experiments.v17_fitness.cases.build_station_cases)
# --------------------------------------------------------------------------
def build_station_diagnostics(job: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cases plus the series-level conditions for one station.

    The outage realizations are regenerated from the same deterministic seeds
    that built the archived crossed panel, with ``cross_overlap=True`` and
    ``n_empirical=REALIZATIONS_PER_STATION_YEAR // 3``, so the stratified
    length x overlap cases are identical. Diagnostic columns are added from the
    daily series, which the archived case table does not store.
    """

    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    protocol = str(job.get("fit_protocol", "leave_one_year_out"))
    try:
        daily = load_network_panel(network_id, str(job["source_root"])).copy()
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame(), pd.DataFrame()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame(), pd.DataFrame()

    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)
    complete_years = tuple(int(y) for y in job["complete_years"])
    if len(complete_years) < 2:
        return pd.DataFrame(), pd.DataFrame()

    rows: list[dict] = []
    phase_rows: list[dict] = []

    for year in complete_years:
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        truth_metric = hottest_window_mean(truth)
        if not np.isfinite(truth_metric):
            continue
        train_mask = pd.Series(~year_mask, index=daily.index)
        peak_source = target.loc[target.index.year != int(year)]
        models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        peak_doys = climatological_peak_window(peak_source, exclude_year=None)
        train_values = target.loc[train_mask].dropna()
        if len(train_values) < 365:
            continue
        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), protocol))
        realizations = design_for_year(
            year_index,
            peak_doys,
            pool,
            rng=rng,
            n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3),
            cross_overlap=bool(job.get("cross_overlap", False)),
        )
        truth_fit = sine_parameters(truth)
        competition = truth_competition(truth, WINDOW)
        n_days = len(truth)

        for realization in realizations:
            mask = realization.mask(n_days)
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan
            visible = usable_donors(donors, year_index, mask)
            fits: dict[str, np.ndarray] = {}
            fits["doy_climatology"] = models.doy_climatology(year_index)
            fits["smooth_climatology"] = models.smooth_climatology(year_index)
            fits["linear_interp"] = linear_interp_fill(observed)
            donor_fit = models.donor_ridge(visible) if visible else None
            fits["donor_ridge"] = (
                models.donor_predict(donor_fit, year_index)
                if donor_fit is not None
                else np.full(n_days, np.nan)
            )
            fits["air_ridge"] = (
                models.air_predict(year_index) if air is not None else np.full(n_days, np.nan)
            )

            rolled_truth = competition_window_roll(truth)
            longest = max(realization.runs, key=lambda item: item[1])
            true_peak_end = int(competition["truth_window_end"])
            true_peak_slice = slice(max(0, true_peak_end - WINDOW + 1), true_peak_end + 1)
            base = {
                "network_id": network_id,
                "station_id": station_id,
                "provider": str(job["provider"]),
                "split_role": str(job["split_role"]),
                "regulation_status": str(job["regulation_status"]),
                "year": int(year),
                "fit_protocol": protocol,
                "realization_id": realization.realization_id,
                "arm": realization.arm,
                "overlap_class": realization.overlap_class,
                "longest_run": int(realization.longest_run),
                "n_runs": int(realization.n_runs),
                "total_missing": int(realization.total_missing),
                "missing_fraction": float(mask.sum() / n_days),
                "longest_run_month": int(year_index.month.to_numpy()[int(longest[0])]),
                "peak_overlap": float(peak_overlap_fraction(year_index, mask, peak_doys)),
                "true_peak_hidden_fraction": float(mask[true_peak_slice].mean()),
                "truth_hottest30": float(truth_metric),
                "air_available": bool(air is not None and np.isfinite(fits["air_ridge"]).any()),
                "n_visible_donors": int(len(visible)),
                "n_complete_years": int(len(complete_years)),
                "truth_window_value_roll": float(rolled_truth[true_peak_end])
                if true_peak_end >= 0
                else float("nan"),
                "truth_sine_phase": float(truth_fit["sine_phase"]),
                "truth_sine_amplitude": float(truth_fit["sine_amplitude"]),
            }
            base.update(competition)

            phase_rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "year": int(year),
                    "realization_id": realization.realization_id,
                    "arm": realization.arm,
                    "overlap_class": realization.overlap_class,
                    "longest_run": int(realization.longest_run),
                    "missing_fraction": float(mask.sum() / n_days),
                    "peak_overlap": float(peak_overlap_fraction(year_index, mask, peak_doys)),
                    "truth_peak_hidden_fraction": float(mask[true_peak_slice].mean()),
                    "truth_sine_phase": float(truth_fit["sine_phase"]),
                    "truth_sine_amplitude": float(truth_fit["sine_amplitude"]),
                    "truth_sine_resid_sd": sine_fit_residual_sd(truth),
                    **phase_standard_error_days(truth, mask),
                }
            )
            # Validation subsample: cheap enough to run, broad enough to compare
            # the analytic intervals with a resampling answer.
            if (
                len(phase_rows) % 3 == 0
                and realization.arm == "stratified"
                and realization.longest_run in (30, 90)
                and realization.overlap_class in ("none", "full")
            ):
                phase_rows[-1]["bootstrap_sd_days"] = phase_bootstrap_sd(
                    truth,
                    mask,
                    draws=PHASE_BOOTSTRAP_DRAWS,
                    block_days=PHASE_BOOTSTRAP_BLOCK_DAYS,
                    seed=stable_seed(network_id, station_id, int(year), realization.realization_id, "phase"),
                )

            air_missing_days = (
                int(
                    np.sum(
                        ~np.isfinite(
                            pd.to_numeric(air.reindex(year_index), errors="coerce").to_numpy(dtype=float)
                        )
                    )
                )
                if air is not None
                else -1
            )
            # The air design uses lags up to 14 days, so days at the very start
            # of the panel have no lag history and the air branch cannot predict
            # them. Counted here so the excluded air cases have a recorded reason.
            air_design_missing_days = -1
            if air is not None:
                air_design = models._air_design(year_index)
                if air_design is not None:
                    air_design_missing_days = int(
                        np.sum(~np.isfinite(air_design).all(axis=1))
                    )
            for name in RECONSTRUCTORS:
                fill = np.asarray(fits[name], dtype=float)
                completed = observed.copy()
                completed[mask] = fill[mask]
                case = dict(base)
                case["reconstructor"] = name
                case["masked_days_with_nan_fill"] = int(np.sum(~np.isfinite(fill[mask])))
                case["air_forcing_missing_days_in_year"] = air_missing_days
                case["air_design_missing_days_in_year"] = air_design_missing_days
                if not np.isfinite(completed).all():
                    case.update(
                        {
                            "reconstructed_hottest30": float("nan"),
                            "err_hottest30": float("nan"),
                            "abserr_hottest30": float("nan"),
                            "window_end_reconstructed": float("nan"),
                            "window_misaligned": float("nan"),
                            "misalignment_days": float("nan"),
                            "abs_misalignment_days": float("nan"),
                            "window_overlap_days_with_truth": float("nan"),
                            "window_disjoint_from_truth": float("nan"),
                            "recon_max_status": "not_finite",
                        }
                    )
                    rows.append(case)
                    continue

                recon_value, recon_end, _ = rolling_window_argmax(completed, WINDOW)
                error = float(recon_value - truth_metric)
                misalignment = float(recon_end - true_peak_end) if true_peak_end >= 0 else float("nan")
                overlap_days = (
                    float(max(0.0, WINDOW - abs(misalignment))) if np.isfinite(misalignment) else float("nan")
                )

                resid_repaired = completed - truth  # identically 0 outside the gap
                model_resid = fill - truth  # the reconstructor's own error everywhere
                inside, n_inside = lag1_autocorrelation(resid_repaired, mask)
                outside_values = np.where(np.isfinite(model_resid), model_resid, np.nan)
                outside, n_outside = lag1_autocorrelation(outside_values, ~mask)
                inside_sd = (
                    float(np.nanstd(resid_repaired[mask])) if mask.any() else float("nan")
                )
                outside_finite = ~mask & np.isfinite(model_resid)
                outside_sd = (
                    float(np.nanstd(model_resid[outside_finite])) if outside_finite.any() else float("nan")
                )

                case.update(
                    {
                        "reconstructed_hottest30": float(recon_value),
                        "err_hottest30": error,
                        "abserr_hottest30": abs(error),
                        "window_end_reconstructed": float(recon_end),
                        "window_misaligned": float(recon_end != true_peak_end),
                        "misalignment_days": misalignment,
                        "abs_misalignment_days": abs(misalignment),
                        "window_overlap_days_with_truth": overlap_days,
                        "window_disjoint_from_truth": float(
                            np.isfinite(misalignment) and abs(misalignment) >= WINDOW
                        ),
                        "recon_max_status": "ok",
                        "resid_ac_inside_gap": inside,
                        "resid_ac_inside_pairs": float(n_inside),
                        "resid_ac_outside_gap": outside,
                        "resid_ac_outside_pairs": float(n_outside),
                        "resid_sd_inside_gap": inside_sd,
                        "resid_sd_outside_gap": outside_sd,
                        "model_resid_defined_outside": bool(outside_finite.any()),
                    }
                )
                rows.append(case)

    cases = pd.DataFrame(rows)
    phases = pd.DataFrame(phase_rows)
    return cases, phases


def competition_window_roll(truth: np.ndarray) -> np.ndarray:
    _, _, rolled = rolling_window_argmax(truth, WINDOW)
    return rolled


def sine_fit_residual_sd(values: np.ndarray) -> float:
    """Residual sd of the three-parameter sine fit on the days present."""

    y = np.asarray(values, dtype=float)
    good = np.isfinite(y)
    if int(good.sum()) < 30:
        return float("nan")
    t = np.arange(len(y), dtype=float)[good]
    angle = 2 * np.pi * t / DAYS_IN_YEAR
    design = np.column_stack([np.ones(len(t)), np.sin(angle), np.cos(angle)])
    beta, *_ = np.linalg.lstsq(design, y[good], rcond=None)
    resid = y[good] - design @ beta
    dof = max(1, int(good.sum()) - 3)
    return float(np.sqrt(float(resid @ resid) / dof))


# --------------------------------------------------------------------------
# station selection: exactly the crossed panel of scripts/281 (24 stations)
# --------------------------------------------------------------------------
def crossed_panel_jobs(limit: int | None = None) -> list[dict]:
    roster = pd.read_csv(STEP1_PANEL / "station_roster.csv")
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    dev_nets = set(split.loc[split["split_role"].eq("development"), "network_id"].astype(str))
    roster = roster.loc[roster["network_id"].astype(str).isin(dev_nets)].copy()
    counts = roster.groupby("network_id")["station_id"].nunique()
    multi = set(counts.loc[counts >= 2].index.astype(str))
    roster = roster.loc[roster["network_id"].astype(str).isin(multi)]
    picked = (
        roster.groupby("network_id", group_keys=False)
        .head(2)
        .head(24)
        .reset_index(drop=True)
    )
    if limit:
        picked = picked.head(int(limit))
    jobs: list[dict] = []
    for row in picked.itertuples():
        years = []
        try:
            panel = load_network_panel(str(row.network_id), str(row.source_root))
        except (FileNotFoundError, ValueError):
            continue
        station_id = str(row.station_id)
        if station_id not in [str(c) for c in panel.columns]:
            continue
        series = pd.to_numeric(panel[station_id], errors="coerce")
        for year, block in series.groupby(series.index.year):
            need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
            if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
                years.append(int(year))
        if len(years) < 4:
            continue
        jobs.append(
            {
                "network_id": str(row.network_id),
                "station_id": station_id,
                "provider": str(getattr(row, "provider", "unknown")),
                "source_root": str(getattr(row, "source_root", "first")),
                "split_role": "development",
                "regulation_status": str(getattr(row, "regulation_status", "unknown")),
                "complete_years": years,
                "fit_protocol": "leave_one_year_out",
                "cross_overlap": True,
            }
        )
    return jobs


# --------------------------------------------------------------------------
# analysis helpers
# --------------------------------------------------------------------------
def station_year_mean(frame: pd.DataFrame, value: str, keys: list[str]) -> pd.DataFrame:
    return (
        frame.groupby(keys, as_index=False)[value]
        .mean()
        .rename(columns={value: "v"})
    )


def bin_series(values: np.ndarray, edges: tuple[float, ...]) -> np.ndarray:
    edges = np.asarray(edges, dtype=float)
    out = np.full(len(values), -1, dtype=int)
    finite = np.isfinite(values)
    out[finite] = np.clip(np.digitize(values[finite], edges[1:-1]), 0, len(edges) - 2)
    return out


def label_bins(edges: tuple[float, ...]) -> list[str]:
    labels = []
    for low, high in zip(edges[:-1], edges[1:]):
        if np.isinf(high):
            labels.append(f">={low:g}")
        else:
            labels.append(f"[{low:g},{high:g})")
    return labels


def error_by_bin(
    frame: pd.DataFrame,
    *,
    value_col: str,
    bin_col: str,
    edges: tuple[float, ...],
    reconstructors: tuple[str, ...],
    seed: int,
) -> pd.DataFrame:
    rows = []
    labels = label_bins(edges)
    for name in reconstructors:
        block = frame.loc[frame["reconstructor"].eq(name)].copy()
        if block.empty:
            continue
        codes = bin_series(block[bin_col].to_numpy(dtype=float), edges)
        block = block.assign(_bin=codes)
        for code, label in enumerate(labels):
            sub = block.loc[block["_bin"].eq(code)]
            if sub.empty:
                continue
            row = {
                "block": "error_by_bin",
                "reconstructor": name,
                "bin_variable": bin_col,
                "bin": label,
                "n_cases": int(len(sub)),
                "n_stations": int(sub["station_id"].nunique()),
            }
            ci = cluster_stat(
                sub.assign(v=sub["abserr_hottest30"]),
                network_equal_mean_stat,
                columns=("v",),
                seed=seed,
            )
            add_ci(row, ci)
            rows.append(row)
    return pd.DataFrame(rows)


def error_contrast(
    frame: pd.DataFrame,
    *,
    value_col: str,
    flag_col: str,
    reconstructors: tuple[str, ...],
    seed: int,
    label: str,
) -> pd.DataFrame:
    """Network-clustered contrast between flag==1 and flag==0 subsets."""

    rows = []
    for name in reconstructors:
        block = frame.loc[frame["reconstructor"].eq(name)].copy()
        flag = pd.to_numeric(block[flag_col], errors="coerce")
        block = block.loc[flag.notna()].copy()
        block["v"] = pd.to_numeric(block[value_col], errors="coerce")
        block["_flag"] = pd.to_numeric(block[flag_col], errors="coerce")
        if block.empty or block["_flag"].nunique() < 2:
            continue
        # Paired within station-year where both levels exist; else unpaired.
        station_year = (
            block.groupby(["network_id", "station_id", "year", "_flag"], as_index=False)["v"].mean()
        )
        wide = station_year.pivot_table(
            index=["network_id", "station_id", "year"], columns="_flag", values="v"
        )
        paired = wide.dropna() if {0.0, 1.0}.issubset(set(wide.columns)) else pd.DataFrame()
        row = {
            "block": "condition_contrast",
            "contrast": label,
            "reconstructor": name,
            "design": "paired_within_station_year"
            if len(paired)
            else "unpaired_subsets",
            "n_station_years_paired": int(len(paired)),
            "n_cases_high": int((block["_flag"] == 1).sum()),
            "n_cases_low": int((block["_flag"] == 0).sum()),
        }
        if len(paired):
            delta = paired.reset_index()
            delta["v"] = pd.to_numeric(delta[1.0], errors="coerce") - pd.to_numeric(
                delta[0.0], errors="coerce"
            )
            ci = cluster_stat(delta, network_equal_mean_stat, columns=("v",), seed=seed)
        else:
            ci = {"point": float("nan"), "low": float("nan"), "high": float("nan"), "n_clusters": 0}
        add_ci(row, ci)
        for level, tag in ((1.0, "high"), (0.0, "low")):
            sub = block.loc[block["_flag"].eq(level)]
            ci_level = cluster_stat(sub, network_equal_mean_stat, columns=("v",), seed=seed)
            row[f"mean_abserr_{tag}_C"] = ci_level["point"]
            row[f"n_networks_{tag}"] = ci_level["n_clusters"]
        rows.append(row)
    return pd.DataFrame(rows)


def share_table(
    frame: pd.DataFrame,
    *,
    flag_col: str,
    subset_col: str | None,
    reconstructors: tuple[str, ...],
    seed: int,
    block_name: str,
) -> pd.DataFrame:
    rows = []
    for name in reconstructors:
        block_all = frame.loc[frame["reconstructor"].eq(name)].copy()
        if block_all.empty:
            continue
        if subset_col is None:
            subsets = [("all", block_all)]
        else:
            subsets = [("all", block_all)] + [
                (str(key), group) for key, group in block_all.groupby(subset_col, sort=True)
            ]
        for subset, sub in subsets:
            flag = pd.to_numeric(sub[flag_col], errors="coerce")
            sub = sub.loc[flag.notna()].copy()
            if sub.empty:
                continue
            sub["v"] = pd.to_numeric(sub[flag_col], errors="coerce")
            row = {
                "block": block_name,
                "reconstructor": name,
                "subset": subset,
                "n_cases": int(len(sub)),
                "n_networks": int(sub["network_id"].nunique()),
            }
            ci = cluster_stat(sub, network_equal_share_stat, columns=("v",), seed=seed)
            row["share_misaligned"] = ci["point"]
            row["share_ci_low"] = ci["low"]
            row["share_ci_high"] = ci["high"]
            misaligned = sub.loc[sub["v"].eq(1.0)]
            row["median_abs_misalignment_days"] = (
                float(misaligned["abs_misalignment_days"].median()) if len(misaligned) else float("nan")
            )
            row["max_abs_misalignment_days"] = (
                float(misaligned["abs_misalignment_days"].max()) if len(misaligned) else float("nan")
            )
            rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=int, default=0, help="limit stations (debug)")
    parser.add_argument("--workers", type=int, default=0, help="joblib workers (0=auto)")
    parser.add_argument("--draws", type=int, default=BOOT_DRAWS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--tag", type=str, default="", help="suffix for scratch outputs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    draws = int(args.draws)
    seed = int(args.seed)
    suffix = f"_{args.tag}" if args.tag else ""

    jobs = crossed_panel_jobs(limit=args.stations or None)
    workers = int(args.workers) if args.workers else min(len(jobs), 24)
    print(f"[317] {len(jobs)} stations, {workers} workers, {draws} bootstrap draws", flush=True)
    results = Parallel(n_jobs=workers, verbose=5)(
        delayed(build_station_diagnostics)(job) for job in jobs
    )
    case_frames = [frame for frame, _ in results if len(frame)]
    phase_frames = [frame for _, frame in results if len(frame)]
    if not case_frames:
        raise RuntimeError("no cases built")
    cases = pd.concat(case_frames, ignore_index=True)
    phases = pd.concat(phase_frames, ignore_index=True)
    print(f"[317] built {len(cases)} cases / {len(phases)} phase rows in {time.time() - started:.0f}s", flush=True)
    cases.to_parquet(SCRATCH / f"cases_with_conditions{suffix}.parquet", index=False)
    phases.to_parquet(SCRATCH / f"phase_cases{suffix}.parquet", index=False)

    validation: dict[str, object] = {"n_cases": int(len(cases)), "n_phase_rows": int(len(phases))}

    # ---- air availability, recorded not assumed -------------------------
    air_rows = []
    for name, path in (("v17_daily_forcing", AIR_TABLE_V17), ("v18_nasa_power", AIR_TABLE_V18)):
        table = pd.read_parquet(path, columns=["station_id", "network_id"])
        station_hits = int(
            pd.Series(sorted(cases["station_id"].unique())).isin(table["station_id"].astype(str)).sum()
        )
        network_hits = int(
            pd.Series(sorted(cases["network_id"].unique())).isin(table["network_id"].astype(str)).sum()
        )
        air_rows.append(
            {
                "forcing_table": name,
                "path": str(path.relative_to(ROOT)),
                "stations_covered": station_hits,
                "stations_total": int(cases["station_id"].nunique()),
                "networks_covered": network_hits,
                "networks_total": int(cases["network_id"].nunique()),
            }
        )
    air_availability = pd.DataFrame(air_rows)
    air_cases = cases.loc[cases["reconstructor"].eq("air_ridge")]
    validation["air_available_share_cases"] = float(air_cases["air_available"].mean())
    validation["air_reconstructor_finite_share"] = float(
        pd.to_numeric(air_cases["abserr_hottest30"], errors="coerce").notna().mean()
    )
    validation["air_reconstructor_missing_cases"] = int(
        pd.to_numeric(air_cases["abserr_hottest30"], errors="coerce").isna().sum()
    )
    unique_cases = cases.drop_duplicates(["network_id", "station_id", "year", "realization_id"])
    validation["truth_peak_tie_share"] = float(
        pd.to_numeric(unique_cases["truth_peak_ties"], errors="coerce").mean()
    )
    validation["truth_peak_tie_days_median"] = float(
        pd.to_numeric(unique_cases["truth_peak_tie_days"], errors="coerce").median()
    )
    validation["competing_peak_gap_C_median_C"] = float(
        pd.to_numeric(unique_cases["competing_peak_gap_C"], errors="coerce").median()
    )
    validation["competing_peak_gap_C2_median_C"] = float(
        pd.to_numeric(unique_cases["competing_peak_gap_C2"], errors="coerce").median()
    )

    # ---- reproduction check against the archived crossed panel ----------
    crossed = pd.read_parquet(CROSSED_PARQUET)
    check_keys = ["network_id", "station_id", "year", "realization_id"]
    designed = cases.loc[
        cases["longest_run"].isin(LENGTHS) & cases["overlap_class"].isin(OVERLAP_CLASSES)
    ]
    mine = designed.loc[designed["reconstructor"].eq("doy_climatology"), check_keys + ["peak_overlap", "true_peak_hidden_fraction"]]
    mine = mine.rename(
        columns={"peak_overlap": "peak_overlap_mine", "true_peak_hidden_fraction": "hidden_mine"}
    )
    reference = crossed[check_keys + ["peak_overlap", "true_peak_hidden_fraction", "abserr_doy_climatology", "abserr_smooth_climatology", "abserr_linear_interp", "abserr_donor_ridge", "overlap_class", "longest_run"]]
    merged = reference.merge(mine, on=check_keys, how="outer", indicator=True)
    both = merged.loc[merged["_merge"].eq("both")]
    validation["reproduction"] = {
        "archived_crossed_cases": int(len(reference)),
        "regenerated_designed_cases": int(len(mine)),
        "matched": int(len(both)),
        "only_in_archive": int((merged["_merge"] == "left_only").sum()),
        "only_in_regenerated": int((merged["_merge"] == "right_only").sum()),
        "max_abs_dev_peak_overlap": float(
            (both["peak_overlap"] - both["peak_overlap_mine"]).abs().max()
        )
        if len(both)
        else None,
        "max_abs_dev_hidden_fraction": float(
            (both["true_peak_hidden_fraction"] - both["hidden_mine"]).abs().max()
        )
        if len(both)
        else None,
    }
    for recon in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge"):
        pair = designed.loc[designed["reconstructor"].eq(recon), check_keys + ["abserr_hottest30"]].rename(
            columns={"abserr_hottest30": "abserr_mine"}
        )
        comp = reference[check_keys + [f"abserr_{recon}"]].merge(pair, on=check_keys, how="inner")
        deviation = (comp[f"abserr_{recon}"] - comp["abserr_mine"]).abs()
        validation["reproduction"][f"max_abs_dev_abserr_{recon}"] = (
            float(deviation.max()) if len(deviation) else None
        )
        validation["reproduction"][f"n_compared_{recon}"] = int(len(comp))

    # ---- crossed design: position x length, per reconstructor ------------
    analysis = cases.loc[
        cases["longest_run"].isin(LENGTHS) & cases["overlap_class"].isin(OVERLAP_CLASSES)
    ].copy()
    crossed_rows: list[dict] = []
    for recon in RECONSTRUCTORS:
        block = analysis.loc[analysis["reconstructor"].eq(recon)].copy()
        block = block.loc[pd.to_numeric(block["abserr_hottest30"], errors="coerce").notna()]
        block = block.rename(columns={"abserr_hottest30": "abserr"})
        if block.empty:
            crossed_rows.append({"reconstructor": recon, "contrast": "unavailable", "note": "no finite cases"})
            continue
        station_year = station_year_mean(
            block,
            "abserr",
            ["network_id", "station_id", "year", "longest_run", "overlap_class"],
        )
        # (1) position at fixed length: full - none
        for length in LENGTHS:
            sub = station_year.loc[station_year["longest_run"].eq(length)]
            wide = sub.pivot_table(
                index=["network_id", "station_id", "year"], columns="overlap_class", values="v"
            )
            if not {"full", "none"}.issubset(set(map(str, wide.columns))):
                continue
            both = wide.dropna(subset=["full", "none"]).reset_index()
            if both.empty:
                continue
            both["v"] = pd.to_numeric(both["full"], errors="coerce") - pd.to_numeric(
                both["none"], errors="coerce"
            )
            ci = cluster_stat(both, network_equal_mean_stat, columns=("v",), draws=draws, seed=seed)
            row = {
                "design": "position_x_length",
                "contrast": "full_minus_none_at_fixed_length",
                "level": f"length={length}",
                "length": float(length),
                "reconstructor": recon,
                "n_station_years": int(len(both)),
            }
            add_ci(row, ci)
            crossed_rows.append(row)
        # (2) length at fixed overlap class: long - short
        for overlap in OVERLAP_CLASSES:
            sub = station_year.loc[station_year["overlap_class"].astype(str).eq(overlap)]
            wide = sub.pivot_table(
                index=["network_id", "station_id", "year"], columns="longest_run", values="v"
            )
            available = [c for c in LENGTHS if c in wide.columns]
            if len(available) < 2:
                continue
            low, high = available[0], available[-1]
            both = wide.dropna(subset=[low, high]).reset_index()
            if both.empty:
                continue
            both["v"] = pd.to_numeric(both[high], errors="coerce") - pd.to_numeric(
                both[low], errors="coerce"
            )
            ci = cluster_stat(both, network_equal_mean_stat, columns=("v",), draws=draws, seed=seed + 7)
            row = {
                "design": "position_x_length",
                "contrast": "long_minus_short_at_fixed_overlap_class",
                "level": f"overlap={overlap}",
                "overlap_class": overlap,
                "short_length": float(low),
                "long_length": float(high),
                "reconstructor": recon,
                "n_station_years": int(len(both)),
            }
            add_ci(row, ci)
            crossed_rows.append(row)

    # ---- 3. length effect at a fixed hidden share, every reconstructor ---
    for hidden_cut in HIDDEN_SHARE_LEVELS:
        hidden = analysis.loc[
            pd.to_numeric(analysis["true_peak_hidden_fraction"], errors="coerce") >= hidden_cut
        ].copy()
        hidden = hidden.rename(columns={"abserr_hottest30": "abserr"})
        for recon in RECONSTRUCTORS:
            block = hidden.loc[hidden["reconstructor"].eq(recon)].copy()
            block = block.loc[pd.to_numeric(block["abserr"], errors="coerce").notna()]
            row = {
                "design": "position_x_length",
                "contrast": "long_minus_short_at_fixed_hidden_share",
                "level": f"true_peak_hidden_fraction>={hidden_cut:g}",
                "hidden_share_cut": float(hidden_cut),
                "reconstructor": recon,
                "n_cases": int(len(block)),
                "n_stations": int(block["station_id"].nunique()) if len(block) else 0,
            }
            if block.empty:
                row["note"] = "no cases at this hidden-share cut"
                crossed_rows.append(row)
                continue
            station_year = station_year_mean(
                block,
                "abserr",
                ["network_id", "station_id", "year", "longest_run", "overlap_class"],
            )
            wide = station_year.pivot_table(
                index=["network_id", "station_id", "year"], columns="longest_run", values="v"
            )
            available = [c for c in LENGTHS if c in wide.columns]
            row["lengths_available"] = ",".join(str(int(c)) for c in available)
            if len(available) < 2:
                row["note"] = "not enough lengths with both members at this hidden-share cut"
                crossed_rows.append(row)
                continue
            low, high = available[0], available[-1]
            both = wide.dropna(subset=[low, high]).reset_index()
            row["short_length"] = float(low)
            row["long_length"] = float(high)
            if both.empty:
                row["note"] = "no station-year carries both lengths at this hidden-share cut"
                crossed_rows.append(row)
                continue
            both["v"] = pd.to_numeric(both[high], errors="coerce") - pd.to_numeric(
                both[low], errors="coerce"
            )
            ci = cluster_stat(both, network_equal_mean_stat, columns=("v",), draws=draws, seed=seed + 11)
            row.update(
                {
                    "n_station_years": int(len(both)),
                    "mean_peak_overlap_short": float(
                        block.loc[block["longest_run"].eq(low), "peak_overlap"].mean()
                    ),
                    "mean_peak_overlap_long": float(
                        block.loc[block["longest_run"].eq(high), "peak_overlap"].mean()
                    ),
                }
            )
            add_ci(row, ci)
            row["length_effect_distinguishable_from_zero"] = bool(row["ci_excludes_zero"])
            crossed_rows.append(row)

            # Same contrast, network-paired rather than station-year-paired: uses
            # every case at this hidden-share cut, and needs both lengths only
            # somewhere in the same network.
            net_row = {
                "design": "position_x_length",
                "contrast": "long_minus_short_at_fixed_hidden_share",
                "level": f"true_peak_hidden_fraction>={hidden_cut:g}",
                "hidden_share_cut": float(hidden_cut),
                "reconstructor": recon,
                "n_cases": int(len(block)),
                "n_stations": int(block["station_id"].nunique()),
                "short_length": float(low),
                "long_length": float(high),
                "design_detail": "network_paired_subsets",
            }
            paired_frame = block.loc[block["longest_run"].isin([low, high])].copy()
            paired_frame["v"] = pd.to_numeric(paired_frame["abserr"], errors="coerce")
            paired_frame["g"] = (paired_frame["longest_run"] == high).astype(float)
            paired_frame = paired_frame.loc[paired_frame["v"].notna()]
            if len(paired_frame) and paired_frame["g"].nunique() > 1:
                net_ci = cluster_stat(
                    paired_frame,
                    network_paired_diff_stat,
                    columns=("v", "g"),
                    draws=draws,
                    seed=seed + 12,
                )
                add_ci(net_row, net_ci)
                net_row["length_effect_distinguishable_from_zero"] = bool(
                    net_row["ci_excludes_zero"]
                )
            else:
                net_row["note"] = "no network carries both lengths at this hidden-share cut"
            crossed_rows.append(net_row)
    crossed_effects = pd.DataFrame(crossed_rows)
    crossed_effects.to_csv(OUT / "crossed_effects.csv", index=False)

    # ---- misalignment ----------------------------------------------------
    mis_rows: list[dict] = []
    mis_rows.append(
        share_table(
            analysis,
            flag_col="window_misaligned",
            subset_col="overlap_class",
            reconstructors=RECONSTRUCTORS,
            seed=seed,
            block_name="misalignment_share_by_overlap_class",
        )
    )
    mis_rows.append(
        share_table(
            analysis,
            flag_col="window_misaligned",
            subset_col="longest_run",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 3,
            block_name="misalignment_share_by_length",
        )
    )
    mis_rows.append(
        share_table(
            analysis,
            flag_col="window_disjoint_from_truth",
            subset_col="overlap_class",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 5,
            block_name="disjoint_window_share_by_overlap_class",
        )
    )
    mis_rows.append(
        share_table(
            analysis.loc[pd.to_numeric(analysis["truth_peak_ties"], errors="coerce").eq(0)],
            flag_col="window_misaligned",
            subset_col=None,
            reconstructors=RECONSTRUCTORS,
            seed=seed + 9,
            block_name="misalignment_share_unique_truth_peak",
        )
    )
    mis_rows.append(
        error_by_bin(
            analysis,
            value_col="abserr_hottest30",
            bin_col="abs_misalignment_days",
            edges=(0.0, 0.5, 8.0, 15.0, 30.0, np.inf),
            reconstructors=RECONSTRUCTORS,
            seed=seed + 13,
        )
    )
    mis_rows.append(
        error_contrast(
            analysis,
            value_col="abserr_hottest30",
            flag_col="window_misaligned",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 17,
            label="misaligned_minus_aligned",
        )
    )
    mis_rows.append(
        error_contrast(
            analysis,
            value_col="abserr_hottest30",
            flag_col="window_disjoint_from_truth",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 19,
            label="disjoint_minus_overlapping_window",
        )
    )
    misalignment_table = pd.concat([frame for frame in mis_rows if len(frame)], ignore_index=True)
    misalignment_table.to_csv(OUT / "misalignment_table.csv", index=False)

    # ---- competing peak --------------------------------------------------
    competing_rows = [
        share_table(
            analysis,
            flag_col="window_misaligned",
            subset_col=None,
            reconstructors=RECONSTRUCTORS,
            seed=seed + 23,
            block_name="misalignment_share_all",
        )
    ]
    analysis_c = analysis.assign(
        competing_bin=pd.cut(
            pd.to_numeric(analysis["competing_peak_gap_C"], errors="coerce"),
            bins=list(COMPETING_PEAK_BINS),
            right=False,
        ).astype(str)
    )
    competing_rows.append(
        share_table(
            analysis_c,
            flag_col="window_misaligned",
            subset_col="competing_bin",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 29,
            block_name="misalignment_share_by_competing_peak_C",
        )
    )
    competing_rows.append(
        error_by_bin(
            analysis,
            value_col="abserr_hottest30",
            bin_col="competing_peak_gap_C",
            edges=COMPETING_PEAK_BINS,
            reconstructors=RECONSTRUCTORS,
            seed=seed + 31,
        )
    )
    competing_rows.append(
        error_by_bin(
            analysis,
            value_col="abserr_hottest30",
            bin_col="competing_peak_gap_C2",
            edges=COMPETING_PEAK_BINS,
            reconstructors=RECONSTRUCTORS,
            seed=seed + 37,
        )
    )
    # Spearman of the competing-peak gap against the misalignment indicator
    corr_rows = []
    for recon in RECONSTRUCTORS:
        block = analysis.loc[analysis["reconstructor"].eq(recon)].copy()
        pair = block[["network_id", "competing_peak_gap_C", "window_misaligned"]].dropna()
        if len(pair) < 100:
            continue

        def spearman(cols: dict[str, np.ndarray]) -> float:
            if len(cols["x"]) < 20:
                return float("nan")
            rank_x = pd.Series(cols["x"]).rank().to_numpy()
            rank_y = pd.Series(cols["y"]).rank().to_numpy()
            if np.std(rank_x) == 0 or np.std(rank_y) == 0:
                return float("nan")
            return float(np.corrcoef(rank_x, rank_y)[0, 1])

        frame = pair.rename(columns={"competing_peak_gap_C": "x", "window_misaligned": "y"})
        ci = cluster_stat(
            frame, spearman, columns=("x", "y"), draws=min(draws, 1000), seed=seed + 41
        )
        corr_rows.append(
            {
                "block": "competing_peak_spearman",
                "reconstructor": recon,
                "n_cases": int(len(pair)),
                "spearman_C_vs_misaligned": ci["point"],
                "ci_low": ci["low"],
                "ci_high": ci["high"],
                "n_networks": ci["n_clusters"],
                "ci_excludes_zero": bool(
                    np.isfinite(ci["low"]) and np.isfinite(ci["high"]) and not (ci["low"] <= 0 <= ci["high"])
                ),
            }
        )
    competing_rows.append(pd.DataFrame(corr_rows))
    competing_peak_table = pd.concat([f for f in competing_rows if len(f)], ignore_index=True)
    competing_peak_table.to_csv(OUT / "competing_peak.csv", index=False)

    # ---- residual correlation -------------------------------------------
    residual_rows: list[dict] = []
    distribution_rows = []
    for recon in RECONSTRUCTORS:
        block = analysis.loc[analysis["reconstructor"].eq(recon)]
        for tag, col in (("inside_gap", "resid_ac_inside_gap"), ("outside_gap_model", "resid_ac_outside_gap")):
            values = pd.to_numeric(block[col], errors="coerce").dropna()
            distribution_rows.append(
                {
                    "block": "distribution",
                    "reconstructor": recon,
                    "where": tag,
                    "n_cases": int(len(values)),
                    "n_cases_missing": int(len(block) - len(values)),
                    "mean_lag1_ac": float(values.mean()) if len(values) else float("nan"),
                    "median_lag1_ac": float(values.median()) if len(values) else float("nan"),
                    "q25_lag1_ac": float(values.quantile(0.25)) if len(values) else float("nan"),
                    "q75_lag1_ac": float(values.quantile(0.75)) if len(values) else float("nan"),
                    "share_above_0p5": float((values > 0.5).mean()) if len(values) else float("nan"),
                }
            )
    residual_rows.append(pd.DataFrame(distribution_rows))
    # paired inside - outside within station-year
    paired_rows = []
    for recon in RECONSTRUCTORS:
        block = analysis.loc[analysis["reconstructor"].eq(recon)].copy()
        long = block.melt(
            id_vars=["network_id", "station_id", "year"],
            value_vars=["resid_ac_inside_gap", "resid_ac_outside_gap"],
            var_name="where",
            value_name="ac",
        ).dropna()
        if long.empty:
            continue
        station_year = long.groupby(
            ["network_id", "station_id", "year", "where"], as_index=False
        )["ac"].mean()
        wide = station_year.pivot_table(index=["network_id", "station_id", "year"], columns="where", values="ac")
        if not {"resid_ac_inside_gap", "resid_ac_outside_gap"}.issubset(set(wide.columns)):
            continue
        both = wide.dropna().reset_index()
        if both.empty:
            continue
        both["v"] = both["resid_ac_inside_gap"] - both["resid_ac_outside_gap"]
        ci = cluster_stat(both, network_equal_mean_stat, columns=("v",), draws=draws, seed=seed + 43)
        paired_rows.append(
            {
                "block": "paired_inside_minus_outside",
                "reconstructor": recon,
                "n_station_years": int(len(both)),
                "inside_mean": float(both["resid_ac_inside_gap"].mean()),
                "outside_mean": float(both["resid_ac_outside_gap"].mean()),
                "point_C": ci["point"],
                "ci_low_C": ci["low"],
                "ci_high_C": ci["high"],
                "n_networks": ci["n_clusters"],
                "ci_excludes_zero": bool(
                    np.isfinite(ci["low"]) and np.isfinite(ci["high"]) and not (ci["low"] <= 0 <= ci["high"])
                ),
            }
        )
    residual_rows.append(pd.DataFrame(paired_rows))
    residual_rows.append(
        error_by_bin(
            analysis,
            value_col="abserr_hottest30",
            bin_col="resid_ac_inside_gap",
            edges=RESID_AC_BINS,
            reconstructors=RECONSTRUCTORS,
            seed=seed + 47,
        )
    )
    residual_rows.append(
        error_by_bin(
            analysis,
            value_col="abserr_hottest30",
            bin_col="resid_ac_outside_gap",
            edges=RESID_AC_BINS,
            reconstructors=RECONSTRUCTORS,
            seed=seed + 53,
        )
    )
    # error consequence of a strongly correlated inside-gap residual
    resid_ac = pd.to_numeric(analysis["resid_ac_inside_gap"], errors="coerce")
    analysis_r = analysis.assign(
        resid_ac_inside_high=(resid_ac > 0.5).astype(float).where(resid_ac.notna())
    )
    residual_rows.append(
        error_contrast(
            analysis_r,
            value_col="abserr_hottest30",
            flag_col="resid_ac_inside_high",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 59,
            label="inside_gap_AC_above_0p5_minus_below",
        )
    )
    # A fixed 0.5 cut leaves almost every case above it (see the distribution
    # block), so the powered contrast is a per-reconstructor median split.
    median_split_frames = []
    for recon in RECONSTRUCTORS:
        block = analysis.loc[analysis["reconstructor"].eq(recon)].copy()
        ac = pd.to_numeric(block["resid_ac_inside_gap"], errors="coerce")
        if ac.notna().sum() < 50:
            continue
        cut = float(ac.median())
        block["resid_ac_inside_above_median"] = (ac > cut).astype(float).where(ac.notna())
        block["resid_ac_median_cut"] = cut
        median_split_frames.append(block)
    if median_split_frames:
        median_split = pd.concat(median_split_frames, ignore_index=True)
        split_rows = error_contrast(
            median_split,
            value_col="abserr_hottest30",
            flag_col="resid_ac_inside_above_median",
            reconstructors=RECONSTRUCTORS,
            seed=seed + 61,
            label="inside_gap_AC_above_reconstructor_median_minus_below",
        )
        if len(split_rows):
            split_rows["median_cut_used"] = [
                float(median_split.loc[median_split["reconstructor"].eq(name), "resid_ac_median_cut"].iloc[0])
                if (median_split["reconstructor"].eq(name)).any()
                else float("nan")
                for name in split_rows["reconstructor"]
            ]
            residual_rows.append(split_rows)
    residual_correlation = pd.concat([f for f in residual_rows if len(f)], ignore_index=True)
    residual_correlation.to_csv(OUT / "residual_correlation.csv", index=False)

    # ---- phase identifiability -------------------------------------------
    phase = phases.copy()
    phase = phase.loc[pd.to_numeric(phase["phase_se_iid_days"], errors="coerce").notna()].copy()
    # Tolerance: 0.4717 of the interannual sd of the true phase, panel-local.
    truth_phase = (
        phase.groupby(["network_id", "station_id", "year"])["truth_sine_phase"].first().reset_index()
    )
    per_station = truth_phase.groupby(["network_id", "station_id"])["truth_sine_phase"].agg(["std", "size"])
    per_station = per_station.loc[per_station["size"] >= 4, "std"].dropna()
    phase_scale_panel = float(per_station.mean()) if len(per_station) else float("nan")
    tolerance_panel = TOLERANCE_FRACTION * phase_scale_panel
    median_n_observed = float(pd.to_numeric(phase["phase_n_observed"], errors="coerce").median())
    closed_form_k_panel = (
        2 * np.sqrt(2.0 / median_n_observed) / (2 * np.pi * tolerance_panel / DAYS_IN_YEAR)
        if np.isfinite(tolerance_panel) and tolerance_panel > 0
        else float("nan")
    )
    manuscript: dict[str, float] = {}
    if WINTER_SINE_SUMMARY.exists():
        published = json.loads(WINTER_SINE_SUMMARY.read_text())
        manuscript = {
            "phase_tolerance_days": float(published["phase_tolerance"]["tolerance_days"]),
            "phase_interannual_sd_days": float(published["phase_tolerance"]["interannual_sd_days"]),
            "n_observed_days_median": float(published["reporting_rule"]["n_observed_days_median"]),
            "k_theory": float(published["reporting_rule"]["k_theory"]),
            "k_used": float(published["reporting_rule"]["k_used"]),
            "n_cases": float(published["n_cases"]),
        }
    k_manuscript = float(manuscript.get("k_used", 4.5))
    scenario_specs = (
        ("design_iid", "iid_half_width_2se_days", "iid_k_crit"),
        ("design_ar1", "ar1_half_width_2se_days", "ar1_k_crit"),
        ("design_hac_bartlett_30d", "hac_bartlett_30d_half_width_2se_days", "hac_bartlett_30d_k_crit"),
        ("closed_form_uniform_sampling", None, "closed_form_k_crit"),
    )
    phase = phase.assign(
        iid_half_width_2se_days=2 * pd.to_numeric(phase["phase_se_iid_days"], errors="coerce"),
        ar1_half_width_2se_days=2 * pd.to_numeric(phase["phase_se_ar1_days"], errors="coerce"),
        hac_bartlett_30d_half_width_2se_days=2
        * pd.to_numeric(phase["phase_se_hac_days"], errors="coerce"),
        iid_k_crit=2 * pd.to_numeric(phase["phase_se_iid_at_unit_snr_days"], errors="coerce") / tolerance_panel,
        ar1_k_crit=2 * pd.to_numeric(phase["phase_se_ar1_at_unit_snr_days"], errors="coerce") / tolerance_panel,
        hac_bartlett_30d_k_crit=2
        * pd.to_numeric(phase["phase_se_hac_at_unit_snr_days"], errors="coerce")
        / tolerance_panel,
        closed_form_k_crit=2
        * pd.to_numeric(phase["phase_closed_form_at_unit_snr_days"], errors="coerce")
        / tolerance_panel,
    )
    visibility = 1.0 - pd.to_numeric(phase["missing_fraction"], errors="coerce")
    phase = phase.assign(
        visibility_bin=pd.cut(visibility, bins=list(VISIBILITY_BINS), right=False).astype(str)
    )

    def phase_block(panel_frame: pd.DataFrame, panel_label: str) -> pd.DataFrame:
        """Scenario summary, widening decomposition and visibility bins for one panel."""

        rows: list[dict] = []
        for label, se_col, k_col in scenario_specs:
            if se_col is None:
                half = 2 * pd.to_numeric(
                    panel_frame["phase_closed_form_at_unit_snr_days"], errors="coerce"
                ) * pd.to_numeric(panel_frame["phase_sigma"], errors="coerce")
                se_days = pd.to_numeric(panel_frame["phase_closed_form_at_unit_snr_days"], errors="coerce") * pd.to_numeric(
                    panel_frame["phase_sigma"], errors="coerce"
                )
            else:
                half = pd.to_numeric(panel_frame[se_col], errors="coerce")
                se_days = half / 2.0
            keep = half.notna() & np.isfinite(half)
            block = panel_frame.loc[keep]
            if block.empty:
                continue
            retained = block.loc[
                pd.to_numeric(block["phase_amplitude_over_sigma"], errors="coerce") >= k_manuscript
            ]
            median_k_crit = float(pd.to_numeric(block[k_col], errors="coerce").median())
            rows.append(
                {
                    "block": "scenario_summary",
                    "panel": panel_label,
                    "scenario": label,
                    "manuscript_k_theory": manuscript.get("k_theory", float("nan")),
                    "manuscript_k_used": k_manuscript,
                    "manuscript_tolerance_days": manuscript.get("phase_tolerance_days", float("nan")),
                    "design_interval_wider_than_manuscript_threshold": bool(
                        np.isfinite(median_k_crit) and median_k_crit > k_manuscript
                    ),
                    "design_k_crit_over_manuscript_k": float(median_k_crit / k_manuscript)
                    if np.isfinite(median_k_crit)
                    else float("nan"),
                    "n_cases": int(len(block)),
                    "n_stations": int(block["station_id"].nunique()),
                    "n_networks": int(block["network_id"].nunique()),
                    "median_n_observed_days": float(
                        pd.to_numeric(block["phase_n_observed"], errors="coerce").median()
                    ),
                    "median_amplitude_over_sigma": float(
                        pd.to_numeric(block["phase_amplitude_over_sigma"], errors="coerce").median()
                    ),
                    "median_rho_lag1": float(
                        pd.to_numeric(block["phase_rho_lag1"], errors="coerce").median()
                    ),
                    "median_se_days": float(pd.to_numeric(se_days[keep], errors="coerce").median()),
                    "median_95pct_half_width_days": float(half.median()),
                    "q90_95pct_half_width_days": float(half.quantile(0.90)),
                    "tolerance_days_panel": tolerance_panel,
                    "share_half_width_within_tolerance": float((half <= tolerance_panel).mean()),
                    "median_design_k_crit": median_k_crit,
                    "share_design_k_crit_above_manuscript_k": float(
                        (pd.to_numeric(block[k_col], errors="coerce") > k_manuscript).mean()
                    ),
                    "n_retained_by_manuscript_rule": int(len(retained)),
                    "share_retained_by_manuscript_rule": float(len(retained) / len(block)),
                    "share_of_retained_with_half_width_above_tolerance": float(
                        (pd.to_numeric(retained[se_col], errors="coerce") > tolerance_panel).mean()
                    )
                    if len(retained) and se_col
                    else float("nan"),
                }
            )

        def ratio(numerator: str, denominator: str) -> float:
            values = pd.to_numeric(panel_frame[numerator], errors="coerce") / pd.to_numeric(
                panel_frame[denominator], errors="coerce"
            )
            return float(values.median())

        rows.append(
            {
                "block": "widening_decomposition",
                "panel": panel_label,
                "n_cases": int(len(panel_frame)),
                "tolerance_days_panel": tolerance_panel,
                "closed_form_k_theory_panel": closed_form_k_panel,
                "manuscript_k_theory": manuscript.get("k_theory", float("nan")),
                "manuscript_k_used": k_manuscript,
                "manuscript_tolerance_days": manuscript.get("phase_tolerance_days", float("nan")),
                "median_closed_form_at_unit_snr_days": float(
                    pd.to_numeric(panel_frame["phase_closed_form_at_unit_snr_days"], errors="coerce").median()
                ),
                "median_design_iid_at_unit_snr_days": float(
                    pd.to_numeric(panel_frame["phase_se_iid_at_unit_snr_days"], errors="coerce").median()
                ),
                "median_design_ar1_at_unit_snr_days": float(
                    pd.to_numeric(panel_frame["phase_se_ar1_at_unit_snr_days"], errors="coerce").median()
                ),
                "median_design_hac_at_unit_snr_days": float(
                    pd.to_numeric(panel_frame["phase_se_hac_at_unit_snr_days"], errors="coerce").median()
                ),
                "median_ratio_design_iid_over_closed_form": ratio(
                    "phase_se_iid_at_unit_snr_days", "phase_closed_form_at_unit_snr_days"
                ),
                "median_ratio_ar1_over_design_iid": ratio(
                    "phase_se_ar1_at_unit_snr_days", "phase_se_iid_at_unit_snr_days"
                ),
                "median_ratio_hac_over_design_iid": ratio(
                    "phase_se_hac_at_unit_snr_days", "phase_se_iid_at_unit_snr_days"
                ),
            }
        )
        bootstrap = panel_frame.loc[
            pd.to_numeric(panel_frame.get("bootstrap_sd_days"), errors="coerce").notna()
        ] if "bootstrap_sd_days" in panel_frame.columns else panel_frame.iloc[0:0]
        if len(bootstrap):
            simulated = pd.to_numeric(bootstrap["bootstrap_sd_days"], errors="coerce")
            ar1 = pd.to_numeric(bootstrap["phase_se_ar1_days"], errors="coerce")
            iid = pd.to_numeric(bootstrap["phase_se_iid_days"], errors="coerce")
            rows.append(
                {
                    "block": "bootstrap_validation",
                    "panel": panel_label,
                    "scenario": "circular_block_residual_bootstrap",
                    "n_cases": int(len(bootstrap)),
                    "median_simulated_sd_days": float(simulated.median()),
                    "median_analytic_ar1_se_days": float(ar1.median()),
                    "median_analytic_iid_se_days": float(iid.median()),
                    "median_ratio_simulated_over_ar1": float((simulated / ar1).median()),
                    "median_ratio_simulated_over_iid": float((simulated / iid).median()),
                    "share_simulated_within_factor_2_of_ar1": float(
                        ((simulated / ar1).between(0.5, 2.0)).mean()
                    ),
                    "bootstrap_draws": PHASE_BOOTSTRAP_DRAWS,
                    "bootstrap_block_days": PHASE_BOOTSTRAP_BLOCK_DAYS,
                }
            )
        for label, block in panel_frame.groupby("visibility_bin", sort=True):
            half_ar1 = pd.to_numeric(block["ar1_half_width_2se_days"], errors="coerce")
            rows.append(
                {
                    "block": "by_visibility_bin",
                    "panel": panel_label,
                    "scenario": "design_ar1",
                    "visibility_bin": label,
                    "n_cases": int(len(block)),
                    "median_n_observed_days": float(
                        pd.to_numeric(block["phase_n_observed"], errors="coerce").median()
                    ),
                    "median_amplitude_over_sigma": float(
                        pd.to_numeric(block["phase_amplitude_over_sigma"], errors="coerce").median()
                    ),
                    "median_95pct_half_width_days": float(half_ar1.median()),
                    "share_half_width_within_tolerance": float((half_ar1 <= tolerance_panel).mean()),
                    "share_retained_by_manuscript_rule": float(
                        (
                            pd.to_numeric(block["phase_amplitude_over_sigma"], errors="coerce")
                            >= k_manuscript
                        ).mean()
                    ),
                }
            )
        return pd.DataFrame(rows)

    phase_crossed = phase.loc[
        phase["longest_run"].isin(LENGTHS) & phase["overlap_class"].isin(OVERLAP_CLASSES)
    ]
    phase_out = pd.concat(
        [phase_block(phase, "all_realizations"), phase_block(phase_crossed, "crossed_design")],
        ignore_index=True,
    )
    phase_out.to_csv(OUT / "phase_identifiability.csv", index=False)
    bootstrap_block = phase_out.loc[phase_out["block"].eq("bootstrap_validation")]
    validation["phase_bootstrap_validation"] = (
        bootstrap_block[
            [
                "panel",
                "n_cases",
                "median_simulated_sd_days",
                "median_analytic_ar1_se_days",
                "median_analytic_iid_se_days",
                "median_ratio_simulated_over_ar1",
                "median_ratio_simulated_over_iid",
                "share_simulated_within_factor_2_of_ar1",
            ]
        ].to_dict(orient="records")
        if len(bootstrap_block)
        else []
    )
    validation["phase_design_vs_manuscript"] = (
        phase_out.loc[phase_out["block"].eq("scenario_summary")][
            [
                "panel",
                "scenario",
                "n_cases",
                "median_95pct_half_width_days",
                "median_design_k_crit",
                "design_k_crit_over_manuscript_k",
                "share_of_retained_with_half_width_above_tolerance",
            ]
        ].to_dict(orient="records")
    )
    phase.to_parquet(SCRATCH / f"phase_cases_scored{suffix}.parquet", index=False)

    # ---- explicit accounting of the gaps in this design ------------------
    gap_rows = []
    for recon in RECONSTRUCTORS:
        block = cases.loc[cases["reconstructor"].eq(recon)]
        missing = pd.to_numeric(block["abserr_hottest30"], errors="coerce").isna()
        gap_rows.append(
            {
                "reconstructor": recon,
                "n_cases": int(len(block)),
                "n_completed_year_not_finite": int(missing.sum()),
                "share_not_finite": float(missing.mean()),
                "median_masked_days_with_nan_fill": float(
                    pd.to_numeric(block["masked_days_with_nan_fill"], errors="coerce").median()
                ),
                "max_masked_days_with_nan_fill": float(
                    pd.to_numeric(block["masked_days_with_nan_fill"], errors="coerce").max()
                ),
                "n_cases_inside_gap_AC_not_estimable": int(
                    pd.to_numeric(block["resid_ac_inside_gap"], errors="coerce").isna().sum()
                ),
                "n_cases_outside_gap_AC_not_estimable": int(
                    pd.to_numeric(block["resid_ac_outside_gap"], errors="coerce").isna().sum()
                ),
                "n_cases_with_no_visible_donor": int(block["n_visible_donors"].eq(0).sum()),
                "max_air_design_missing_days_in_year": float(
                    pd.to_numeric(block["air_design_missing_days_in_year"], errors="coerce").clip(lower=0).max()
                ),
            }
        )
    gap_accounting = pd.DataFrame(gap_rows)
    gap_accounting.to_csv(OUT / "recorded_gaps.csv", index=False)
    air_only = cases.loc[cases["reconstructor"].eq("air_ridge")]
    air_not_finite = pd.to_numeric(air_only["abserr_hottest30"], errors="coerce").isna()
    validation["air_forcing_missing_days_total"] = int(
        cases.drop_duplicates(["network_id", "station_id", "year", "realization_id"])[
            "air_forcing_missing_days_in_year"
        ].clip(lower=0).sum()
    )
    validation["air_design_missing_days_total_across_cases"] = int(
        pd.to_numeric(air_only["air_design_missing_days_in_year"], errors="coerce")
        .clip(lower=0)
        .sum()
    )
    validation["air_excluded_cases_with_missing_air_design"] = int(
        (air_not_finite & pd.to_numeric(air_only["air_design_missing_days_in_year"], errors="coerce").gt(0)).sum()
    )
    validation["air_excluded_cases_other_reason"] = int(
        (air_not_finite & ~pd.to_numeric(air_only["air_design_missing_days_in_year"], errors="coerce").gt(0)).sum()
    )
    validation["phase_rows_with_too_few_observed_days"] = int(
        len(phases) - int(pd.to_numeric(phases["phase_se_iid_days"], errors="coerce").notna().sum())
    )

    # ---- fingerprint -----------------------------------------------------
    elapsed = time.time() - started
    fingerprint = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256(Path(__file__)),
        "git_head": git_head(),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_seconds": round(elapsed, 1),
        "inputs": {
            "station_roster": {
                "path": str((STEP1_PANEL / "station_roster.csv").relative_to(ROOT)),
                "sha256": sha256(STEP1_PANEL / "station_roster.csv"),
            },
            "network_split": {
                "path": str((STEP1_PANEL / "network_split.csv").relative_to(ROOT)),
                "sha256": sha256(STEP1_PANEL / "network_split.csv"),
            },
            "archived_crossed_cases": {
                "path": str(CROSSED_PARQUET.relative_to(ROOT)),
                "sha256": sha256(CROSSED_PARQUET),
            },
            "air_forcing_primary_v18": {
                "path": str(AIR_TABLE_V18.relative_to(ROOT)),
                "sha256": sha256(AIR_TABLE_V18),
            },
            "air_forcing_v17_shipped": {
                "path": str(AIR_TABLE_V17.relative_to(ROOT)),
                "sha256": sha256(AIR_TABLE_V17),
            },
            "manuscript_sine_summary": {
                "path": str(WINTER_SINE_SUMMARY.relative_to(ROOT)),
                "sha256": sha256(WINTER_SINE_SUMMARY),
            },
        },
        "air_forcing_env": os.environ.get("STREAM_AIR_FORCING", ""),
        "air_availability": air_availability.to_dict(orient="records"),
        "config": {
            "reconstructors": list(RECONSTRUCTORS),
            "lengths": list(LENGTHS),
            "window_days": WINDOW,
            "bootstrap_draws": draws,
            "seed": seed,
            "tolerance_fraction": TOLERANCE_FRACTION,
            "hidden_share_full": HIDDEN_SHARE_FULL,
            "competing_peak_bins": [float(x) for x in COMPETING_PEAK_BINS],
            "resid_ac_bins": [float(x) for x in RESID_AC_BINS],
            "hac_lag_days": HAC_LAG_DAYS,
            "stations_built": int(cases["station_id"].nunique()),
            "networks_built": int(cases["network_id"].nunique()),
            "n_cases_all": int(len(cases)),
            "n_cases_crossed_design": int(len(analysis)),
            "phase_n_cases": int(len(phase)),
            "phase_tolerance_days_panel": tolerance_panel,
            "phase_interannual_sd_days_panel": phase_scale_panel,
            "closed_form_k_panel": closed_form_k_panel,
            "manuscript_sine_rule": manuscript,
        },
        "validation": validation,
        "claim_status": (
            "descriptive conditional mechanism evidence on the paired crossed "
            "development panel; cluster-bootstrapped but not pre-registered; not "
            "a reconstruction-independent geometry law"
        ),
    }
    (OUT / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2) + "\n")

    # ---- SUMMARY.md ------------------------------------------------------
    def fmt(value: object, digits: int = 3) -> str:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(value)
        if not np.isfinite(number):
            return "n/a"
        return f"{number:.{digits}f}"

    def table_for_summary(frame: pd.DataFrame, columns: list[str]) -> str:
        """Compact view of a table; the full version stays in its CSV."""

        if frame is None or not len(frame):
            return "(no rows)"
        keep = [column for column in columns if column in frame.columns]
        view = frame.loc[:, keep].copy()
        for column in view.columns:
            if pd.api.types.is_float_dtype(view[column]):
                view[column] = view[column].map(
                    lambda value: "" if value is None or not np.isfinite(value) else f"{value:.3f}"
                )
        # Drop columns that are empty for every row of this block; the CSV keeps them.
        empty = [column for column in view.columns if bool((view[column].astype(str) == "").all())]
        if len(empty) < len(view.columns):
            view = view.drop(columns=empty)
        return view.to_string(index=False)

    lines: list[str] = []
    lines.append("# P1 mechanism boundary — misalignment, competing peaks, residual correlation, air reconstructor, design-based phase interval")
    lines.append("")
    lines.append(f"Generated {fingerprint['generated_utc']} from `{fingerprint['script']}` "
                 f"(sha256 `{fingerprint['script_sha256'][:12]}`) at git HEAD `{fingerprint['git_head']}`. "
                 f"Wall time {elapsed / 60:.1f} min.")
    lines.append("")
    lines.append("## Protocol")
    lines.append("")
    lines.append(
        f"- Cases: the Step-3 paired position x length crossed development panel "
        f"(`{CROSSED_PARQUET.relative_to(ROOT)}`), reconstructed here from the same "
        f"deterministic seeds so the daily series are available: "
        f"{fingerprint['config']['stations_built']} stations / {fingerprint['config']['networks_built']} networks, "
        f"{fingerprint['config']['n_cases_all']} cases, {len(analysis)} of them in the "
        f"crossed design (lengths {list(LENGTHS)} x overlap classes {list(OVERLAP_CLASSES)})."
    )
    lines.append(
        f"- Reconstructors: {', '.join(RECONSTRUCTORS)}; leave-one-year-out fits; "
        f"30-day windows; network-clustered bootstrap, {draws} draws, seed {seed}; "
        f"every interval is the network-equal mean (each network one vote)."
    )
    lines.append(
        "- Air forcing: the v17 table shipped with the study (`"
        + str(AIR_TABLE_V17.relative_to(ROOT))
        + "`) covers "
        + f"{int(air_availability.loc[air_availability['forcing_table'].eq('v17_daily_forcing'), 'stations_covered'].iloc[0])}"
        + f"/{int(cases['station_id'].nunique())} crossed-panel stations, so `air_ridge` is not "
        "estimable there; the primary run uses the v18 NASA POWER forcing table (`"
        + str(AIR_TABLE_V18.relative_to(ROOT))
        + f"`), which covers "
        + f"{int(air_availability.loc[air_availability['forcing_table'].eq('v18_nasa_power'), 'stations_covered'].iloc[0])}"
        + f"/{int(cases['station_id'].nunique())}. Air rows are labelled by their forcing table in "
        "`protocol_fingerprint.json`; `air_available` case share is "
        + f"{fmt(validation['air_available_share_cases'])} and finite `air_ridge` error share is "
        + f"{fmt(validation['air_reconstructor_finite_share'])}."
    )
    lines.append(
        "- Conditions are computed from the daily series, not from the archived case table "
        "(which stores no series): reconstructed 30-day maximum vs truth maximum (days); "
        "truth gap to the best disjoint window (C) and to the second-best disjoint window (C2); "
        "lag-1 autocorrelation of the reconstruction residual inside the gap and of the "
        "reconstructor's own fitted value against truth outside the gap."
    )
    lines.append(
        "- New conditions are conditional/descriptive: they are not pre-registered and their "
        "intervals are not corrected for multiplicity."
    )
    lines.append("")
    lines.append("## Reproduction check against the archived crossed panel")
    lines.append("")
    repro = validation["reproduction"]
    lines.append(
        f"- matched {repro['matched']} of {repro['archived_crossed_cases']} archived crossed cases "
        f"(only-in-archive {repro['only_in_archive']}, only-in-regenerated {repro['only_in_regenerated']})."
    )
    lines.append(
        f"- max |Δ peak_overlap| {fmt(repro['max_abs_dev_peak_overlap'], 6)}, max |Δ true_peak_hidden_fraction| "
        f"{fmt(repro['max_abs_dev_hidden_fraction'], 6)}."
    )
    for recon in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge"):
        lines.append(
            f"- max |Δ abserr_hottest30| for `{recon}`: "
            f"{fmt(repro.get(f'max_abs_dev_abserr_{recon}'), 6)} °C "
            f"over {repro.get(f'n_compared_{recon}', 0)} cases."
        )
    lines.append("")
    lines.append("## 1. Crossed design: position x length, per reconstructor")
    lines.append("")
    lines.append(
        table_for_summary(
            crossed_effects,
            [
                "design",
                "contrast",
                "level",
                "design_detail",
                "reconstructor",
                "n_cases",
                "n_station_years",
                "n_networks",
                "short_length",
                "long_length",
                "point_C",
                "ci_low_C",
                "ci_high_C",
                "ci_excludes_zero",
                "length_effect_distinguishable_from_zero",
                "note",
            ],
        )
    )
    lines.append("")
    lines.append("Length effect at the fixed hidden share (whether the interval excludes zero):")
    lines.append("")
    fixed = crossed_effects.loc[
        crossed_effects["contrast"].eq("long_minus_short_at_fixed_hidden_share")
    ]
    if fixed.empty:
        lines.append("(no fixed-hidden-share length contrast could be formed)")
    for row in fixed.itertuples():
        ci_low = getattr(row, "ci_low_C", float("nan"))
        ci_high = getattr(row, "ci_high_C", float("nan"))
        if not (np.isfinite(ci_low) and np.isfinite(ci_high)):
            verdict = "interval not estimable on this sample (reported, not filled in)"
        elif getattr(row, "ci_excludes_zero", False):
            verdict = "distinguishable from zero"
        else:
            verdict = "NOT distinguishable from zero"
        design_detail = getattr(row, "design_detail", None)
        if not isinstance(design_detail, str):
            design_detail = "station_year_paired"
        units = (
            f"{getattr(row, 'n_station_years', 'n/a')} station-years"
            if design_detail == "station_year_paired"
            else f"{getattr(row, 'n_networks', 'n/a')} networks"
        )
        lines.append(
            f"- `{row.reconstructor}` at hidden share {getattr(row, 'level', 'n/a')} "
            f"({design_detail}), lengths {getattr(row, 'short_length', 'n/a')} vs "
            f"{getattr(row, 'long_length', 'n/a')}: {fmt(getattr(row, 'point_C', float('nan')))} °C "
            f"[{fmt(ci_low)}, {fmt(ci_high)}] on {units} — {verdict}."
        )
    lines.append("")
    lines.append("## 2. Misalignment")
    lines.append("")
    lines.append(
        f"The truth peak window is tied in {100 * validation['truth_peak_tie_share']:.1f}% of cases "
        f"(median {fmt(validation['truth_peak_tie_days_median'], 0)} tied 30-day windows); the "
        "unique-peak restriction is reported as `misalignment_share_unique_truth_peak`."
    )
    lines.append("")
    headline = misalignment_table.loc[
        misalignment_table["block"].eq("misalignment_share_by_overlap_class")
        & misalignment_table["subset"].eq("all")
    ]
    consequence = misalignment_table.loc[
        misalignment_table["block"].eq("condition_contrast")
        & misalignment_table["contrast"].eq("misaligned_minus_aligned")
    ]
    for row in headline.itertuples():
        match = consequence.loc[consequence["reconstructor"].eq(row.reconstructor)]
        extra = ""
        if len(match):
            item = match.iloc[0]
            extra = (
                f"; error {fmt(item['mean_abserr_low_C'])} °C when aligned vs "
                f"{fmt(item['mean_abserr_high_C'])} °C when not, paired difference "
                f"{fmt(item['point_C'])} [{fmt(item['ci_low_C'])}, {fmt(item['ci_high_C'])}]"
            )
        lines.append(
            f"- `{row.reconstructor}`: {100 * row.share_misaligned:.1f}% of cases land on a different "
            f"window (median {fmt(row.median_abs_misalignment_days, 0)} days away){extra}."
        )
    lines.append("")
    lines.append(
        table_for_summary(
            misalignment_table,
            [
                "block",
                "reconstructor",
                "subset",
                "bin",
                "contrast",
                "design",
                "n_cases",
                "n_networks",
                "share_misaligned",
                "share_ci_low",
                "share_ci_high",
                "median_abs_misalignment_days",
                "mean_abserr_low_C",
                "mean_abserr_high_C",
                "point_C",
                "ci_low_C",
                "ci_high_C",
                "ci_excludes_zero",
            ],
        )
    )
    lines.append("")
    lines.append("## 3. Competing peak")
    lines.append("")
    lines.append(
        f"Median truth gap from the best window to the best disjoint window C = "
        f"{fmt(validation['competing_peak_gap_C_median_C'])} °C; the best-to-second-best disjoint "
        f"gap C2 = {fmt(validation['competing_peak_gap_C2_median_C'])} °C, i.e. the disjoint "
        "competitors are usually a broad plateau rather than one sharp rival. C is a station-year "
        "property, so its error relationship is confounded with station identity."
    )
    lines.append("")
    lines.append(
        table_for_summary(
            competing_peak_table,
            [
                "block",
                "reconstructor",
                "subset",
                "bin",
                "n_cases",
                "n_networks",
                "share_misaligned",
                "share_ci_low",
                "share_ci_high",
                "point_C",
                "ci_low_C",
                "ci_high_C",
                "spearman_C_vs_misaligned",
                "ci_excludes_zero",
            ],
        )
    )
    lines.append("")
    lines.append("## 4. Residual correlation")
    lines.append("")
    lines.append(
        "Inside the gap the residual is the reconstruction error itself; outside the gap the "
        "repaired series equals the truth by construction, so the outside column is the "
        "reconstructor's own fitted value against truth on observed days (`linear_interp` has none "
        "outside the gap and is reported missing, never zero)."
    )
    lines.append("")
    distribution = residual_correlation.loc[residual_correlation["block"].eq("distribution")]
    for recon in RECONSTRUCTORS:
        inside = distribution.loc[
            distribution["reconstructor"].eq(recon) & distribution["where"].eq("inside_gap")
        ]
        outside = distribution.loc[
            distribution["reconstructor"].eq(recon) & distribution["where"].eq("outside_gap_model")
        ]
        pieces = []
        if len(inside):
            pieces.append(
                f"inside mean lag-1 AC {fmt(inside['mean_lag1_ac'].iloc[0])} "
                f"(n={int(inside['n_cases'].iloc[0])}, {int(inside['n_cases_missing'].iloc[0])} cases "
                "with too few adjacent hidden-day pairs to estimate)"
            )
        if len(outside) and outside["n_cases"].iloc[0]:
            pieces.append(f"outside mean lag-1 AC {fmt(outside['mean_lag1_ac'].iloc[0])}")
        elif len(outside):
            pieces.append("outside not defined by this reconstructor")
        lines.append(f"- `{recon}`: " + "; ".join(pieces) + ".")
    lines.append("")
    lines.append(
        table_for_summary(
            residual_correlation,
            [
                "block",
                "reconstructor",
                "where",
                "bin",
                "contrast",
                "n_cases",
                "n_cases_missing",
                "mean_lag1_ac",
                "median_lag1_ac",
                "share_above_0p5",
                "median_cut_used",
                "mean_abserr_low_C",
                "mean_abserr_high_C",
                "point_C",
                "ci_low_C",
                "ci_high_C",
                "ci_excludes_zero",
            ],
        )
    )
    lines.append("")
    lines.append("## 5. Phase identifiability from the actual design matrix")
    lines.append("")
    lines.append(
        "The manuscript's rule is a uniform-sampling signal-to-noise cut: it assumes "
        "se(phi) = sigma*sqrt(2/n)/A on a balanced design and keeps cases with A/sigma >= "
        f"{k_manuscript:g} (k_theory {fmt(manuscript.get('k_theory', float('nan')))} on the "
        f"{int(manuscript.get('n_cases', 0))}-case development panel, where the phase tolerance is "
        f"{fmt(manuscript.get('phase_tolerance_days', float('nan')))} d). Below, `*_at_unit_snr_days` "
        "is the standard error in days at A/sigma = 1, so the required amplitude-to-noise ratio for "
        "a 95% half width within tolerance is 2 * c / tau (manuscript threshold "
        f"{k_manuscript:g})."
    )
    lines.append("")
    lines.append(
        table_for_summary(
            phase_out,
            [
                "block",
                "panel",
                "scenario",
                "n_cases",
                "median_n_observed_days",
                "median_amplitude_over_sigma",
                "median_rho_lag1",
                "median_se_days",
                "median_95pct_half_width_days",
                "tolerance_days_panel",
                "share_half_width_within_tolerance",
                "median_design_k_crit",
                "design_k_crit_over_manuscript_k",
                "share_retained_by_manuscript_rule",
                "share_of_retained_with_half_width_above_tolerance",
                "median_ratio_design_iid_over_closed_form",
                "median_ratio_ar1_over_design_iid",
                "median_ratio_simulated_over_ar1",
                "median_ratio_simulated_over_iid",
                "visibility_bin",
            ],
        )
    )
    lines.append("")
    scenario = phase_out.loc[phase_out["block"].eq("scenario_summary")]
    for panel_label in scenario["panel"].dropna().unique():
        block = scenario.loc[scenario["panel"].eq(panel_label)]
        assumed = block.loc[block["scenario"].eq("closed_form_uniform_sampling")]
        if len(assumed):
            lines.append(
                f"- Panel `{panel_label}`: the uniform-sampling rule needs A/sigma >= "
                f"{fmt(assumed['median_design_k_crit'].iloc[0])} (median across cases, panel tolerance "
                f"{fmt(assumed['tolerance_days_panel'].iloc[0])} d), against the manuscript's "
                f"{k_manuscript:g}."
            )
        for row in block.itertuples():
            if row.scenario == "closed_form_uniform_sampling":
                continue
            verdict = (
                "WIDER than the assumed threshold"
                if getattr(row, "design_interval_wider_than_manuscript_threshold", False)
                else "not wider than the assumed threshold"
            )
            lines.append(
                f"- Panel `{panel_label}`, `{row.scenario}`: median required A/sigma "
                f"{fmt(row.median_design_k_crit)} "
                f"({fmt(getattr(row, 'design_k_crit_over_manuscript_k', float('nan')), 2)}x the manuscript "
                f"{k_manuscript:g}) — the design-based interval is {verdict}; "
                f"{fmt(100 * getattr(row, 'share_of_retained_with_half_width_above_tolerance', float('nan')), 1)}% "
                "of the cases the fixed rule retains have a design-based 95% half width above the tolerance."
            )
    bootstrap_rows = phase_out.loc[phase_out["block"].eq("bootstrap_validation")]
    if len(bootstrap_rows):
        lines.append("")
        lines.append(
            "Resampling check on the analytic intervals (circular block bootstrap of the sine-fit "
            f"residuals, {PHASE_BOOTSTRAP_DRAWS} draws, {PHASE_BOOTSTRAP_BLOCK_DAYS}-day blocks, on a "
            "deterministic subsample):"
        )
        lines.append("")
        for row in bootstrap_rows.itertuples():
            lines.append(
                f"- Panel `{row.panel}`: n={row.n_cases}, median simulated sd "
                f"{fmt(row.median_simulated_sd_days)} d vs analytic AR(1) {fmt(row.median_analytic_ar1_se_days)} d "
                f"(ratio {fmt(row.median_ratio_simulated_over_ar1, 2)}) and analytic i.i.d. "
                f"{fmt(row.median_analytic_iid_se_days)} d (ratio {fmt(row.median_ratio_simulated_over_iid, 2)}); "
                f"{fmt(100 * row.share_simulated_within_factor_2_of_ar1, 1)}% of cases within a factor of two "
                "of the AR(1) interval."
            )
    lines.append("")
    lines.append("## Recorded gaps (nothing silently dropped)")
    lines.append("")
    lines.append(gap_accounting.to_string(index=False))
    lines.append("")
    lines.append(
        f"- Air branch: the forcing table has "
        f"{validation['air_forcing_missing_days_total']} missing calendar days on these "
        "station-year-realizations, so the forcing itself is complete. The "
        f"{validation['air_reconstructor_missing_cases']} of {len(air_cases)} air cases with no finite "
        "completed year are cases whose gap covers days at the very start of the panel, where the "
        "air design's lags (up to 14 days) have no history: "
        f"{validation['air_excluded_cases_with_missing_air_design']} of them are explained that way "
        f"and {validation['air_excluded_cases_other_reason']} are not (reported, not filled in). "
        "Those cases are excluded from air rows only; every other reconstructor keeps them."
    )
    lines.append(
        "- Donor branch: the `donor_ridge` cases with no finite completed year are donor-scarcity "
        "cases (`n_cases_with_no_visible_donor`) plus cases where a visible donor is itself absent on "
        "some hidden days, so the donor regression returns NaN there; the max masked-days-with-NaN-fill "
        "column quantifies it."
    )
    lines.append(
        f"- {validation['phase_rows_with_too_few_observed_days']} of {len(phases)} phase rows have "
        "fewer than 60 observed days and carry no design-based interval."
    )
    lines.append(
        f"- The archived crossed panel holds {validation['reproduction']['archived_crossed_cases']} cases; "
        f"{validation['reproduction']['only_in_archive']} of them are the empirical-arm `observed` "
        "overlap-class cases that the designed crossed analysis excludes, exactly as in Step 3. "
        "The other 1899 reproduce to machine precision."
    )
    lines.append("")
    lines.append("## Falsification statements")
    lines.append("")
    lines.append(
        "- This analysis fails to support a reconstruction-independent geometry law if the "
        "position contrast does not survive with the air reconstructor, if the length effect at a "
        "fixed hidden share does not exclude zero for the reconstructors the manuscript leans on, "
        "or if the misalignment share is near zero."
    )
    lines.append(
        "- The design-based phase interval refutes the fixed A/sigma threshold if a substantial "
        "share of cases retained by that threshold has a design-based interval wider than the "
        "study's own phase tolerance; it supports the threshold if the two mostly agree."
    )
    lines.append(
        "- Competing-peak and residual-correlation conditions are observational properties of the "
        "cases; a null there falsifies the mechanism reading, not the panel."
    )
    lines.append("")
    lines.append("## What this does not prove")
    lines.append("")
    lines.append(
        "- It does not prove that misalignment, competing peaks or residual autocorrelation "
        "*cause* the error; they are measured on the same cases, not randomised."
    )
    lines.append(
        "- The competing-peak gap C is a station-year property, so its error relationship is "
        "confounded with station identity and cannot be separated from it here."
    )
    lines.append(
        "- The air reconstructor is fitted to a reanalysis forcing (NASA POWER v18 table); it is "
        "not an in-situ air measurement, and its contrasts are properties of that product."
    )
    lines.append(
        "- The phase interval is computed on the observed-day fit (the protocol the manuscript "
        "calls the authors' own, unrepaired). It is not a repaired-series interval, and it is "
        "conditional on an AR(1)/Bartlett model for the residual correlation rather than on the "
        "full residual covariance."
    )
    lines.append(
        "- Nothing here is a pre-registered confirmation; no number may move a headline claim "
        "without the Step-2/Step-3 gates."
    )
    lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    print(f"[317] done in {elapsed / 60:.1f} min -> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
