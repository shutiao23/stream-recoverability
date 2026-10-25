#!/usr/bin/env python3
"""TR-E2: mechanism and deployment case populations for every target and estimator.

For every complete station-year (leave-one-year-out training) two families of
masks are applied:

* crossed: one contiguous 30/60/90-day gap with no, partial or full overlap of
  the training-time climatological peak window (P-mech);
* calendar: a real incomplete warm-season calendar of the same provider, each
  run jittered by up to 15 days (P-deploy). Exact importance weights for
  state-dependent onsets (P-MNAR) are stored with each calendar case.

Each case stores the seven targets of the truth, of every plug-in completion
(including Air2stream-3), of the observed-days practice, and of two conditional
H30 laws (raw residual blocks and the seasonal air-state law), plus the
decision-time inputs of the recovery law. Columns prefixed ``eval_`` use the
hidden truth and are for evaluation only.

Round 2 (the default configuration) works on per-station hot years: Southern
Hemisphere records are shifted by 184 days so that calendar years become
July-June years, the warm season is the station's five climatologically hottest
consecutive months (from the training years of each case), degree-days use its
four hottest months, and the climatological peak centre is stored so that
peak-season rules can be anchored to it. Australia is an opened development
roster in round 2; the test roster is new USGS stations (``usgs_new``).

Random draws are seeded with plain integers: the station's position in the
sorted roster, the year and, for trajectory draws, the design's position in the
station-year. Each station's cases are cached under a readable name; a run
recomputes them unless ``--resume`` is given.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
from stream_recoverability.experiments import air2stream_equivalent as physics
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.cases import deseasonalized_correlations
from stream_recoverability.experiments.v17_fitness.estimators import StationModels, observed_days_metric, usable_donors
from stream_recoverability.experiments.v17_fitness.outages import climatological_peak_window
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.design import contiguous_starts, overlap_class
from stream_recoverability.experiments.v19_revision.process import enable_compiled_reference, simulate_three
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps, state_conditioned_draws
from sklearn.linear_model import LinearRegression

from stream_recoverability.experiments.v19_revision.trajectory import conditional_trajectories, trajectory_features
from stream_recoverability.seeds import plain_seed, position_index
from stream_recoverability.experiments.tr_revision.baselines import move1, ar1_bridge
from stream_recoverability.experiments.tr_revision.simulation import prepare_states, prepared_draws, prepare_replay, replay_from_prepared
from stream_recoverability.experiments.tr_revision.simulation import visible_air_exposure
from stream_recoverability.experiments.v17_fitness.estimators import linear_interp_fill

CORE = T.load_script("tr_core351", T.ROOT / "scripts/351_wrr_representative_recovery.py")
PROCESS = T.load_script("tr_process362", T.ROOT / "scripts/362_wrr_process_reference.py")
CACHE = T.SCRATCH / "case_cache"
AU_ROSTER = T.AU_ROUND1 / "au_roster.csv"
AU_AIR = T.ROOT / "data/external/wrr_target_recovery_20261021/au_sealed/air_forcing.parquet"
NEW_ROSTER = T.OUT / "e10_sealed_usgs" / "sealed_roster.csv"
NEW_AIR = T.ROOT / "data/external/wrr_target_recovery_20261022/usgs_new/air_forcing.parquet"
METHODS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge", "air2stream3", "air_ols")
NUMERIC_TARGETS = ("h30", "h7", "annual_mean", "c30", T.DEGREE_DAYS, "days_above_20")
QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
JITTER_DAYS = 15
# Seed streams: the first part of every seed names what it draws.
CROSSED_SEED, CALENDAR_SEED, RAW_DRAW_SEED, STATE_DRAW_SEED = 0, 1, 2, 3


def air_state(air: pd.Series | None, index: pd.DatetimeIndex, reference: pd.Series | None = None) -> pd.Series:
    """Standardised 7-day air anomaly; decision-time information.

    The scale is the anomaly's standard deviation over the five warmest months of
    the station's air climatology (round 1: May-September).
    """

    if air is None or not np.isfinite(air.to_numpy(dtype=float)).any():
        return pd.Series(np.nan, index=index)
    values = air.dropna() if reference is None else air.loc[reference].dropna()
    climate = values.groupby(values.index.dayofyear).mean().reindex(range(1, 367)).interpolate(limit_direction="both").to_numpy()
    smooth = np.convolve(np.r_[climate[-15:], climate, climate[:15]], np.ones(31) / 31, mode="valid")
    anomaly = air - smooth[air.index.dayofyear.to_numpy() - 1]
    week = anomaly.rolling(7, min_periods=4).mean()
    months = T.hottest_months(smooth[:365], np.arange(1, 366), 5) if T.SEASON_MODE == "hot_year" else (5, 6, 7, 8, 9)
    warm = week.loc[week.index.month.isin(months)]
    if reference is not None:
        warm=warm.loc[reference.reindex(warm.index).fillna(False)]
    return week / warm.std(ddof=1)


def crossed_designs(support: np.ndarray, seed: int, lengths: list[int], replicates: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    designs = []
    for length in lengths:
        for name, starts in contiguous_starts(len(support), int(length), support).items():
            if not len(starts):
                continue
            for replicate, start in enumerate(rng.choice(starts, size=replicates, replace=len(starts) < replicates)):
                mask = np.zeros(len(support), dtype=bool)
                mask[start : start + length] = True
                designs.append({"family": "crossed", "key": f"cross_{length}_{name}_{replicate}", "length": int(length), "overlap_class": name, "mask": mask, "source": ""})
    return designs


def calendar_designs(pool: list[dict], index: pd.DatetimeIndex, z: np.ndarray, betas: dict[str, float], seed: int, n: int) -> list[dict]:
    """Real calendars, each run jittered; exact importance weights for state-dependent onsets."""

    rng = np.random.default_rng(seed)
    n_days = len(index)
    designs = []
    if not pool:
        return designs
    for draw in rng.choice(len(pool), size=min(n, len(pool)), replace=False):
        source = pool[int(draw)]
        mask = np.zeros(n_days, dtype=bool)
        logw = {name: 0.0 for name in betas}
        onsets = []
        for start_doy, length in source["runs"]:
            start = int(min(start_doy - 1, n_days - 1))
            length = int(min(length, n_days - start))
            low, high = max(0, start - JITTER_DAYS), min(n_days - length, start + JITTER_DAYS)
            window = np.arange(low, high + 1)
            if start == 0 or start + length >= n_days:
                window = np.array([start])
            onset = int(rng.choice(window))
            mask[onset : onset + length] = True
            onsets.append(onset)
            state = z[window]
            for name, beta in betas.items():
                if np.isfinite(state).all() and np.isfinite(z[onset]):
                    logw[name] += beta * z[onset] - float(np.log(np.mean(np.exp(beta * state))))
        if mask.all() or (~mask).sum() < 30:
            continue
        designs.append({
            "family": "calendar", "key": f"calendar_{len(designs)}", "length": int(mask.sum()), "overlap_class": "observed", "mask": mask,
            "source": source["key"], "logw": logw, "onset_z_mean": float(np.nanmean(z[onsets])) if onsets else np.nan,
        })
    return designs


def air2stream_fill(fitted, index: pd.DatetimeIndex, air: np.ndarray, observed: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(len(index), np.nan)
    if fitted is None or not np.isfinite(air).all():
        return out
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
    for start, end in zip(starts, ends):
        if start < 1 or not np.isfinite(observed[start - 1]):
            return np.full(len(index), np.nan)
        segment = slice(start - 1, end)
        simulated = simulate_three(index[segment], air[segment], fitted.parameters, initial_water_temperature_c=float(observed[start - 1]))
        out[start:end] = simulated[1:]
    return out


def replay_errors(target: pd.Series, residual: np.ndarray, years: list[int], mask_days: tuple[int, ...], window: int = 30) -> list[float]:
    """The same hidden days on each training year, completed with that year's out-of-fold residuals."""

    errors = []
    for year in years:
        selected = target.index.year == year
        truth = target.loc[selected].to_numpy(dtype=float)
        hidden = np.isin(target.index[selected].dayofyear.to_numpy(), mask_days)
        noise = residual[selected]
        if not hidden.any() or not np.isfinite(truth).all() or not np.isfinite(noise[hidden]).all():
            continue
        completed = truth.copy()
        completed[hidden] -= noise[hidden]
        errors.append(float(T.window_means(completed, window).max() - T.window_means(truth, window).max()))
    return errors


def air_ols_fill(model: StationModels, index: pd.DatetimeIndex) -> np.ndarray:
    """Ablation: the air regression without ridge shrinkage."""

    out = np.full(len(index), np.nan)
    if model.air is None:
        return out
    train_index = model.target.index[model.train_mask.to_numpy()]
    X = model._air_design(train_index)
    y = model.target.loc[model.train_mask].to_numpy(dtype=float)
    good = np.isfinite(X).all(axis=1) & np.isfinite(y)
    if good.sum() < 120:
        return out
    fitted = LinearRegression().fit(X[good], y[good])
    design = model._air_design(index)
    valid = np.isfinite(design).all(axis=1)
    if valid.any():
        out[valid] = fitted.predict(design[valid])
    return out


def observed_targets(observed: np.ndarray, index: pd.DatetimeIndex, threshold: float, degree_day_months: tuple[int, ...] = (6, 7, 8, 9), primary_window: int = 30) -> dict[str, float]:
    """The practice of computing each target from recorded days only."""

    jjas = np.isin(index.month.to_numpy(), list(degree_day_months))
    seen = np.isfinite(observed)
    rolled = pd.Series(observed).rolling(primary_window, min_periods=primary_window).mean().to_numpy()
    jjas_fraction = float(seen[jjas].mean())
    return {
        "h30": observed_days_metric(observed),
        "h7": observed_days_metric(observed, window=7, min_coverage=6 / 7),
        "annual_mean": float(np.nanmean(observed)),
        "c30": float(pd.Series(observed).rolling(30, min_periods=24).mean().min()),
        T.DEGREE_DAYS: float(np.nansum(np.clip(observed[jjas], 0, None)) / jjas_fraction) if jjas_fraction > 0 else np.nan,
        "days_above_20": float(np.nansum(observed[jjas] > threshold) / jjas_fraction + np.nansum(observed[~jjas] > threshold)) if jjas_fraction > 0 else np.nan,
        "observed_lower_bound": float(np.nanmax(rolled)) if np.isfinite(rolled).any() else np.nan,
    }


def residual_moments(residual: np.ndarray, index: pd.DatetimeIndex, warm_months: tuple[int, ...] = (5, 6, 7, 8, 9)) -> dict[str, float]:
    """Reconstruction residual r = centre - truth on training warm-season days."""

    r = -np.asarray(residual, dtype=float)
    warm = np.isin(np.asarray(index.month), list(warm_months))
    values = np.where(warm, r, np.nan)
    finite = values[np.isfinite(values)]
    pairs = np.isfinite(values[:-1]) & np.isfinite(values[1:])
    phi = float(np.corrcoef(values[:-1][pairs], values[1:][pairs])[0, 1]) if pairs.sum() > 10 else np.nan
    return {
        "law_mu_r_warm": float(finite.mean()) if len(finite) else np.nan,
        "law_sigma_r_warm": float(finite.std()) if len(finite) else np.nan,
        "law_phi_r": phi,
    }


def peak_residual_moments(residual: np.ndarray, target_index: pd.DatetimeIndex, years: list[int], peak_starts: list[int], window: int = 30) -> dict[str, float]:
    """Residual r = centre - truth inside each training year's true 30-day peak window (round 2, S2)."""

    values = []
    r = -np.asarray(residual, dtype=float)
    for year, start in zip(years, peak_starts):
        positions = np.flatnonzero(target_index.year == year)[start : start + window]
        values.append(r[positions])
    values = np.concatenate(values) if values else np.array([])
    values = values[np.isfinite(values)]
    return {"law_mu_r_peak": float(values.mean()) if len(values) else np.nan, "law_sigma_r_peak": float(values.std()) if len(values) > 1 else np.nan}


def draw_summary(prefix: str, draws: np.ndarray, index: pd.DatetimeIndex, truth: dict[str, float], point: float, targets: tuple[str, ...], threshold: float, degree_day_months: tuple[int, ...] = (6, 7, 8, 9), primary: str = "h30") -> dict:
    stats = {primary:T.window_means(draws,int(primary[1:])).max(axis=1)} if targets == (primary,) else T.target_statistics(draws, index, threshold, degree_day_months)
    row = {}
    for target in targets:
        values = np.asarray(stats[target], dtype=float)
        quantiles = np.quantile(values, QUANTILES)
        if target == primary:
            row.update({f"{prefix}_{primary}_q{int(q * 100):02d}": float(v) for q, v in zip(QUANTILES, quantiles)})
            row[f"{prefix}_{primary}_mean"] = float(values.mean())
            row[f"{prefix}_{primary}_sd"] = float(values.std())
            for delta in (0.25, 0.5, 1.0):
                row[f"{prefix}_pfail_point_{int(delta * 100):03d}"] = float((np.abs(values - point) > delta).mean()) if np.isfinite(point) else np.nan
                row[f"{prefix}_pfail_median_{int(delta * 100):03d}"] = float((np.abs(values - quantiles[3]) > delta).mean())
            row[f"eval_{prefix}_{primary}_pit"] = float((values < truth[primary]).mean() + 0.5 * (values == truth[primary]).mean()) if np.isfinite(truth[primary]) else np.nan
        else:
            row[f"{prefix}_{target}_q05"], row[f"{prefix}_{target}_q50"], row[f"{prefix}_{target}_q95"] = (float(quantiles[0]), float(quantiles[3]), float(quantiles[-1]))
        row[f"eval_{prefix}_{target}_crps"] = sample_crps(values, truth[target])
    return row


def cache_path(job: dict, settings: dict) -> Path:
    return CACHE / settings["version"] / job["roster"] / f"{job['network_id']}__{job['station_id']}.parquet"


def station_cases(job: dict, settings: dict, generator: dict, pool: list[dict], resume: bool = False) -> dict:
    window=int(settings.get("primary_window_days",30));primary=f"h{window}"
    if window not in [7,30]:raise ValueError("Source target must be H7 or H30")
    if window!=30 and "replication_seeds" not in settings:raise ValueError("Alternative-window generation requires the grouped replication workflow")
    cache = cache_path(job, settings)
    if resume and cache.exists():
        return {"cache": str(cache), "cached": True}
    enable_compiled_reference()
    panel = read_temperature_panel(job["input_path"])
    panel.columns = panel.columns.astype(str)
    panel = panel.asfreq("D")
    if job["station_id"] not in panel:
        return {"cache": None, "reason": "station_missing"}
    # Southern Hemisphere: shift dates so that each calendar year of the analysis is a July-June hot year.
    shift = 0 if settings.get("calendar_year_only",False) else T.hemisphere_shift_days(job.get("latitude"))
    real_index = panel.index
    if shift:
        panel.index = panel.index + pd.Timedelta(days=shift)
    if settings.get("synthetic_water_trend_c_decade",0):
        # Change the complete daily water record (including visible donors),
        # then refit every upstream stage. Air forcing remains unperturbed.
        offset=float(settings["synthetic_water_trend_c_decade"])*(panel.index.year.to_numpy()-2000)/10
        panel=panel.add(offset,axis=0)
    target = pd.to_numeric(panel[job["station_id"]], errors="coerce")
    donor_panel = panel.drop(columns=job["station_id"])
    years = CORE.complete_years(target)
    if len(years) < 4:
        return {"cache": None, "reason": "fewer_than_four_complete_years"}
    air = station_air_series(Path(job["air_input_path"]), job["network_id"], job["station_id"], real_index)
    if air is not None:
        air.index = target.index
    air_values = air.to_numpy(dtype=float) if air is not None else np.full(len(target), np.nan)
    z_all = air_state(air, target.index)
    water = target.to_numpy(dtype=float)
    threshold = settings["exceedance_threshold_c"]
    betas = {"k1": generator["onset_log_odds_per_sd_air_week"], "k2": 2 * generator["onset_log_odds_per_sd_air_week"], "upper": generator["onset_log_odds_upper95"]}
    rows = []
    plan = [(year, "complete") for year in years]
    if job["roster"] == "real":
        # Real incomplete years inside the active span; the truth is unknown.
        observed_years = target.dropna().index.year
        first, last = int(observed_years.min()), int(observed_years.max())
        plan = []
        # A nationally fixed metadata roster can explicitly identify fully
        # supported analysis years despite an artificially padded input window.
        # The default historical workflow keeps its original edge-year rule.
        for year in job.get("real_years",range(first + 1, last)):
            values = water[target.index.year == year]
            if np.isfinite(values).all() or np.isfinite(values).sum() < 30:
                continue
            plan.append((year, "real"))
    for year, kind in plan:
        held = target.index.year == year
        allowed = pd.Series(~held, index=target.index)
        # Optional differential split: held-out hot/future years are excluded
        # from every upstream fit, climatology and residual replay.
        split = settings.get("training_split", "leave_one_year_out")
        if split == "cold_to_hot":
            annual = {y: float(T.window_means(water[target.index.year == y], window).max()) for y in years}
            cutoff = float(np.quantile(list(annual.values()), 0.8))
            excluded = [y for y, value in annual.items() if value >= cutoff]
            allowed &= ~target.index.year.isin(excluded)
        elif split == "before_2010":
            allowed &= target.index.year < 2010
        elif split not in ["leave_one_year_out","non_air_refit"]:
            raise ValueError(f"Unknown training split: {split}")
        train_years = [value for value in years if value != year]
        train_years = [value for value in train_years if bool(allowed[target.index.year == value].any())]
        if len(train_years) < 3:
            continue
        if split in ["cold_to_hot","before_2010"]:
            z_all=air_state(air,target.index,allowed)
        index = target.index[held]
        truth = water[held]
        model = StationModels(target=target, donors=donor_panel, air=air, train_mask=allowed)
        climate = model.smooth_climatology(index)
        support_days = climatological_peak_window(target.loc[allowed],window=window)
        support = np.isin(index.dayofyear.to_numpy(), support_days)
        if T.SEASON_MODE == "hot_year":
            # Seasons from the training climatology of this case: no hidden value enters.
            warm_months = T.hottest_months(climate, index.dayofyear.to_numpy(), settings["warm_season_months"])
            dd_months = T.hottest_months(climate, index.dayofyear.to_numpy(), settings["degree_day_months"])
        else:
            warm_months, dd_months = tuple(settings["warm_months"]), (6, 7, 8, 9)
        warm = np.isin(index.month.to_numpy(), list(warm_months))
        truth_targets = T.target_statistics(truth, index, threshold, dd_months) if kind == "complete" else {name: np.nan for name in T.TARGETS}
        # Recovery-law inputs from training years only.
        train_index = target.index[allowed.to_numpy()]
        anomaly = target.loc[allowed] - model.smooth_climatology(train_index)
        warm_anomaly = anomaly.where(anomaly.index.month.isin(list(warm_months)))
        a = warm_anomaly.to_numpy(dtype=float)
        pairs = np.isfinite(a[:-1]) & np.isfinite(a[1:])
        sigma_a = float(np.nanstd(a))
        phi_a = float(np.corrcoef(a[:-1][pairs], a[1:][pairs])[0, 1]) if pairs.sum() > 10 else np.nan
        peak_starts, peak_anomalies, train_h30 = [], [], []
        for value in train_years:
            block = water[target.index.year == value]
            means = T.window_means(block, window)
            start = int(np.argmax(means))
            clim_block = model.smooth_climatology(target.index[target.index.year == value])
            peak_starts.append(start)
            peak_anomalies.append(float(means[start] - clim_block[start : start + window].mean()))
            train_h30.append(float(means[start]))
        air2 = None
        if np.isfinite(air_values).any():
            try:
                fit_water=water.copy() if split in ["cold_to_hot","before_2010"] else water
                if split in ["cold_to_hot","before_2010"]:
                    fit_water[~allowed.to_numpy()]=np.nan
                start, end = PROCESS.calibration_segment(target.index, fit_water, air_values, None, int(year), False)
                air2 = physics.fit_air2stream3(target.index[start:end], fit_water[start:end], air_values[start:end], max_nfev=200)
            except (ValueError, RuntimeError):
                air2 = None
        z = z_all.to_numpy(dtype=float)[held]
        if kind == "complete":
            designs = []
            for replication_seed in settings.get("replication_seeds", [None]):
                parts = () if replication_seed is None else (int(replication_seed),)
                generated = crossed_designs(support, plain_seed(*parts, CROSSED_SEED, job["station_index"], year), settings["gap_lengths_days"], settings["realizations_per_cell"])
                generated += calendar_designs(pool, index, z, betas, plain_seed(*parts, CALENDAR_SEED, job["station_index"], year), settings["n_mnar_geometries"] + 2)
                for local_position, design in enumerate(generated):
                    design["replication_seed"] = replication_seed
                    design["local_position"] = local_position
                designs.extend(generated)
        else:
            real_mask = ~np.isfinite(truth)
            designs = [{"family": "real", "key": "real", "length": int(real_mask.sum()), "overlap_class": "observed", "mask": real_mask, "source": ""}]
        with np.errstate(invalid="ignore", divide="ignore"):
            correlations = deseasonalized_correlations(target, donor_panel, allowed)
        residual_cache = {}
        baseline_cache = {}
        deterministic_cache = {}
        fills_cache = {}
        air_year = air_values[held]
        air_h30 = float(T.window_means(air_year, window).max()) if np.isfinite(air_year).all() else np.nan
        for position, design in enumerate(designs):
            mask = design["mask"]
            starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
            ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
            longest_run = int((ends - starts).max())
            observed = truth.copy()
            observed[mask] = np.nan
            exposure=np.zeros(len(observed),dtype=bool)
            if settings.get("visible_air_exposure_days",0):
                observed,exposure=visible_air_exposure(observed,air_year,warm,
                    days=int(settings["visible_air_exposure_days"]),
                    top_fraction=float(settings.get("visible_air_exposure_top_fraction",.1)),
                    seed=plain_seed(8,int(design.get("replication_seed") or 0),job["station_index"],year,int(design.get("local_position",position))))
            visible = usable_donors(donor_panel, index, mask)
            if "replication_seeds" in settings:
                if tuple(visible) not in fills_cache:
                    fills_cache[tuple(visible)] = CORE.predictions(model, observed, index, visible)
                fills = dict(fills_cache[tuple(visible)])
                fills["linear_interp"] = linear_interp_fill(observed)
            else:
                fills = CORE.predictions(model, observed, index, visible)
            fills["air2stream3"] = air2stream_fill(air2, index, air_year, observed, mask)
            fills["air_ols"] = air_ols_fill(model, index)
            choice = CORE.select_policy({name: fills[name] for name in METHODS if name not in ("air2stream3", "air_ols")}, mask, longest_run)
            completed = {}
            for name in METHODS:
                values = observed.copy()
                values[mask] = fills[name][mask]
                if np.isfinite(values).all():
                    completed[name] = values
            row = {
                "network_id": job["network_id"], "station_id": job["station_id"], "station_key": job["station_key"], "provider": job["provider"],
                "region": job["region"], "independence_group": job["independence_group"], "statistic_class": job["statistic_class"],
                "regulation_status": job["regulation_status"], "roster": job["roster"], "year": int(year),
                "design_family": design["family"], "realization_id": design["key"], "gap_length": design["length"], "overlap_class": design["overlap_class"],
                "calendar_source": design["source"], "mask_runs": ";".join(f"{s}:{e - s}" for s, e in zip(starts, ends)),
                "total_missing": int(mask.sum()), "missing_fraction": float(mask.mean()), "n_runs": len(starts), "longest_run": longest_run,
                "warm_observed_fraction": float((~mask & warm).sum() / warm.sum()), "peak_overlap": float(mask[support].mean()),
                "n_visible_donors": len(visible), "donor_corr_mean": float(correlations.reindex(list(visible)).mean()) if visible else np.nan,
                "air_available": bool(np.isfinite(air_year).all()), "policy_choice": choice or "unavailable",
                "n_complete_years": len(train_years), "clim_peak": float(T.window_means(climate, window).max()),
                f"train_{primary}_mean": float(np.mean(train_h30)), f"train_{primary}_sd": float(np.std(train_h30, ddof=1)),
                "law_sigma_a": sigma_a, "law_phi_a": phi_a, "law_peak_anomaly_mean": float(np.mean(peak_anomalies)), "law_peak_anomaly_sd": float(np.std(peak_anomalies, ddof=1)),
                "law_hidden_shares": ";".join(f"{mask[s : s + window].mean():.4f}" for s in peak_starts), "law_peak_anomalies": ";".join(f"{v:.4f}" for v in peak_anomalies),
                f"air_{primary}_target_year": air_h30, "air_gap_z_mean": float(np.nanmean(z[mask])) if np.isfinite(z[mask]).any() else np.nan,
                "air_warm_z_mean": float(np.nanmean(z[warm])) if np.isfinite(z[warm]).any() else np.nan,
                "mnar_logw_k1": design.get("logw", {}).get("k1", np.nan), "mnar_logw_k2": design.get("logw", {}).get("k2", np.nan),
                "mnar_logw_upper": design.get("logw", {}).get("upper", np.nan), "onset_z_mean": design.get("onset_z_mean", np.nan),
                "eval_true_peak_hidden_fraction": float(mask[int(np.argmax(T.window_means(truth, window))) :][:window].mean()) if kind == "complete" else np.nan,
                "eval_truth_local_hot": bool(truth_targets[primary] > np.quantile(train_h30, 0.9)) if kind == "complete" else np.nan,
                f"train_{primary}_q90": float(np.quantile(train_h30, 0.9)),
                "hemisphere_shift_days": int(shift), "hot_year_start": str((index[0] - pd.Timedelta(days=shift)).date()),
                "missingness_stratum": job.get("missingness_stratum", ""),
                "warm_months": ";".join(map(str, warm_months)), "dd_months": ";".join(map(str, dd_months)),
                "peak_center_doy": int(support_days[window//2]),
                "eval_truth_window_at_year_edge": bool(kind == "complete" and (int(np.argmax(T.window_means(truth, window))) in (0, len(truth) - window))),
            }
            if window!=30:row["primary_window_days"]=window;row["primary_target"]=primary
            if settings.get("visible_air_exposure_days",0):
                row["eval_air_exposure_days"]=int(exposure.sum())
                row["eval_air_exposure_daily_shift"]=float(np.mean(observed[exposure]-truth[exposure])) if exposure.any() else np.nan
            if "replication_seeds" in settings:
                row["replication_seed"] = design.get("replication_seed", settings["replication_seeds"][0])
                row["training_split"] = split
                if split == "cold_to_hot":
                    row["training_partition"] = "test" if year in excluded else "train"
                elif split == "before_2010":
                    row["training_partition"] = "test" if year >= 2010 else "train"
            edge = np.zeros(len(mask), dtype=bool)
            for s, e in zip(starts, ends):
                edge[max(0, s - 10) : s] = True
                edge[e : min(len(mask), e + 10)] = True
            edge &= ~mask
            row["visible_edge_anomaly"] = float(np.mean(observed[edge] - climate[edge])) if edge.any() else np.nan
            for name, value in truth_targets.items():
                row[f"eval_truth_{name}"] = value
            for name, values in completed.items():
                for target_name, value in T.target_statistics(values, index, threshold, dd_months).items():
                    row[f"{target_name}__{name}"] = value
            for target_name, value in observed_targets(observed, index, threshold, dd_months,primary_window=window).items():
                row[f"{target_name}__observed_days"] = value
            h30_values = [row[f"{primary}__{name}"] for name in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge") if f"{primary}__{name}" in row]
            row["estimator_disagreement"] = float(max(h30_values) - min(h30_values)) if h30_values else np.nan
            stack = np.array([fills[name][mask] for name in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge") if np.isfinite(fills[name][mask]).all()])
            row["daily_estimator_disagreement"] = float(np.mean(stack.max(axis=0) - stack.min(axis=0))) if len(stack) else np.nan
            if choice:
                point = row[f"{primary}__{choice}"]
                row[f"{primary}__policy"] = point
                for target_name in T.TARGETS:
                    row[f"{target_name}__policy"] = row.get(f"{target_name}__{choice}", np.nan)
                missing_doy = tuple(index.dayofyear.to_numpy()[mask]) if choice == "linear_interp" else ()
                residual_key = (choice, tuple(visible) if choice == "donor_ridge" else (), missing_doy)
                if residual_key not in residual_cache:
                    residual_cache[residual_key] = CORE.residual_history(target, donor_panel, air, allowed, train_years, choice, tuple(visible), missing_doy)
                residual = residual_cache[residual_key]
                cached = deterministic_cache.get(residual_key)
                if "replication_seeds" in settings and cached is None:
                    finite=residual[np.isfinite(residual)]
                    adjacent=np.isfinite(residual[:-1])&np.isfinite(residual[1:])
                    correlation=np.nan
                    if adjacent.sum()>=3 and residual[:-1][adjacent].std()>0 and residual[1:][adjacent].std()>0:
                        correlation=float(np.corrcoef(residual[:-1][adjacent],residual[1:][adjacent])[0,1])
                    cached={"moments":residual_moments(residual,target.index,warm_months),"peak_moments":peak_residual_moments(residual,target.index,train_years,peak_starts,window),"sd":float(np.nanstd(residual)),"daily_diagnostics":{"reconstructor_oof_daily_bias":-float(finite.mean()) if len(finite) else np.nan,"reconstructor_oof_daily_abs90":float(np.quantile(np.abs(finite),.9)) if len(finite) else np.nan,"reconstructor_oof_lag1":correlation},"replay":prepare_replay(target,residual,train_years,window)}
                    states=z_all.to_numpy(dtype=float)[:,None] if np.isfinite(z).all() else None
                    try:
                        cached["state_prepared"]=prepare_states(index,residual,target.index,states)
                    except ValueError:
                        cached["state_prepared"]=None
                    deterministic_cache[residual_key]=cached
                if settings.get("classical_baselines", False):
                    key = (choice, tuple(visible) if choice == "donor_ridge" else ())
                    if key not in baseline_cache:
                        if choice == "air_ridge":
                            proxy_train = model.air_predict(train_index)
                        elif choice == "donor_ridge":
                            proxy_train = model.donor_predict(model.donor_ridge(visible), train_index)
                        else:
                            proxy_train = model.smooth_climatology(train_index)
                        proxy_test = fills[choice]
                        y_train = target.loc[allowed].to_numpy(dtype=float)
                        is_warm = train_index.month.isin(warm_months)
                        baseline_cache[key] = {
                            "move1_annual": move1(proxy_train, y_train, proxy_test),
                            "move1_warm": move1(proxy_train[is_warm], y_train[is_warm], proxy_test),
                        }
                        # Annual augmentation uses training-year proxy H30 only.
                        proxy_h30, water_h30 = [], []
                        for train_year in train_years:
                            selected_year = train_index.year == train_year
                            proxy_block, water_block = proxy_train[selected_year], y_train[selected_year]
                            if np.isfinite(proxy_block).all() and np.isfinite(water_block).all():
                                proxy_h30.append(T.window_means(proxy_block, window).max())
                                water_h30.append(T.window_means(water_block, window).max())
                        baseline_cache[key]["annual_pairs"] = (proxy_h30, water_h30)
                    for name in ("move1_annual", "move1_warm"):
                        fill = observed.copy()
                        fill[mask] = baseline_cache[key][name][mask]
                        row[f"{primary}__{name}"] = float(T.window_means(fill, window).max()) if np.isfinite(fill).all() else np.nan
                    px, py = map(np.asarray, baseline_cache[key]["annual_pairs"])
                    if len(px) >= 3 and np.std(px, ddof=1) > 1e-8:
                        row[f"{primary}__move1_{primary}"] = float(py.mean() + np.sign(np.corrcoef(px, py)[0, 1]) * np.std(py, ddof=1) / np.std(px, ddof=1) * (point - px.mean()))
                    if choice not in ["air_ridge","donor_ridge"]:
                        for name in ["move1_annual","move1_warm",f"move1_{primary}"]:
                            row[f"{primary}__{name}"]=np.nan
                    bridge_seed = plain_seed(9, int(design.get("replication_seed") or 0), job["station_index"], year, design.get("local_position", position))
                    bridge = ar1_bridge(observed, fills[choice], residual, bridge_seed, settings.get("multiple_imputations", 20))
                    h30_bridge = T.window_means(bridge, window).max(axis=1)
                    row[f"{primary}__stochastic_regression"] = float(np.median(h30_bridge))
                    row[f"stochastic_{primary}_draws"] = h30_bridge.tolist()
                    for level, value in zip(QUANTILES, np.quantile(h30_bridge, QUANTILES)):
                        row[f"stochastic_{primary}_q{int(level * 100):02d}"] = float(value)
                if cached is not None:
                    row.update(cached["moments"]);row.update(cached["peak_moments"]);row["reconstructor_oof_daily_sd"]=cached["sd"]
                    replay=replay_from_prepared(cached["replay"],tuple(index.dayofyear.to_numpy()[mask]),window)
                    diagnostics=cached["daily_diagnostics"]|{f"historical_mask_{primary}_abs90":float(np.quantile(np.abs(replay),.9)) if replay else np.nan,f"historical_mask_{primary}_bias":float(np.mean(replay)) if replay else np.nan,"n_historical_mask_errors":len(replay)}
                    row.update({f"hist_{k}":v for k,v in diagnostics.items()})
                    row["law_replay_errors"]=";".join(f"{v:.4f}" for v in replay)
                else:
                    row.update(residual_moments(residual, target.index, warm_months))
                    row.update(peak_residual_moments(residual, target.index, train_years, peak_starts,window))
                    row["reconstructor_oof_daily_sd"] = float(np.nanstd(residual))
                    row.update({f"hist_{k}": v for k, v in CORE.historical_error_diagnostics(target, residual, train_years, tuple(index.dayofyear.to_numpy()[mask])).items()})
                    row["law_replay_errors"] = ";".join(f"{v:.4f}" for v in replay_errors(target, residual, train_years, tuple(index.dayofyear.to_numpy()[mask]),window))
                try:
                    parts = () if design.get("replication_seed") is None else (int(design["replication_seed"]),)
                    local_position = design.get("local_position", position)
                    raw = conditional_trajectories(observed, fills[choice], residual, seed=plain_seed(*parts, RAW_DRAW_SEED, job["station_index"], year, local_position), n_draws=settings["trajectory_draws"], block_days=14)
                    row.update(draw_summary("raw", raw, index, truth_targets, point, (primary,), threshold, dd_months,primary))
                    row.update({f"win_{k.replace('h30',primary)}": v for k, v in trajectory_features(raw, mask, point,window=window).items()})
                except ValueError:
                    pass
                try:
                    states = z_all.to_numpy(dtype=float)[:, None] if np.isfinite(z).all() else None
                    if cached is not None and cached.get("state_prepared") is not None:
                        draws=prepared_draws(observed,fills[choice],cached["state_prepared"],seed=plain_seed(*parts,STATE_DRAW_SEED,job["station_index"],year,local_position),n_draws=settings["trajectory_draws"],target_states=z[:,None] if states is not None else None)
                    else:
                        draws = state_conditioned_draws(
                            observed, fills[choice], index, residual, target.index, seed=plain_seed(*parts, STATE_DRAW_SEED, job["station_index"], year, local_position), n_draws=settings["trajectory_draws"],
                            history_states=states, target_states=z[:, None] if states is not None else None,
                        )
                    row.update(draw_summary("state", draws, index, truth_targets, point, tuple(settings.get("trajectory_targets", NUMERIC_TARGETS)), threshold, dd_months,primary))
                    row["state_law"] = "seasonal_air_slow" if states is not None else "seasonal_slow"
                except ValueError as error:
                    row["state_law"] = f"unavailable: {error}"
            rows.append(row)
    cache.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(cache, index=False)
    return {"cache": str(cache), "cached": False, "n_cases": len(frame)}


def run_station(job: dict, settings: dict, generator: dict, pool: list[dict], resume: bool) -> dict:
    """Worker entry point: the script is re-imported so module helpers resolve in the worker."""

    module = T.load_script("tr_cases_worker", Path(__file__))
    return module.station_cases(job, settings, generator, pool, resume)


def calendar_pool(roster: str, jobs: list[dict]) -> dict[str, list[dict]]:
    """Real incomplete calendars per provider: (start day-of-year, length) runs."""

    if roster == "source":
        years = pd.read_parquet(T.E1 / "station_years.parquet")
        gaps = pd.read_parquet(T.E1 / "gaps.parquet")
        core = years.loc[~years.edge_year & years.fully_active & ~years.complete_year, ["station_key", "year", "provider"]]
        gaps = gaps.merge(core, on=["station_key", "year", "provider"], how="inner")
    else:
        # Real calendars of the roster's own stations, on the same (shifted) calendar as the cases.
        rows = []
        if roster=="independent":
            providers={job["provider"] for job in jobs}
            if len(providers)!=1:raise ValueError("Independent calendar construction requires one registered provider")
            provider=next(iter(providers))
        else:provider = {"au": "bom", "usgs_new": "usgs_new"}[roster]
        shifts = {job["input_path"]: T.hemisphere_shift_days(job.get("latitude")) for job in jobs}
        networks = {job["input_path"]: job["network_id"] for job in jobs}
        for path in sorted(shifts):
            panel = read_temperature_panel(path)
            if shifts[path]:
                panel.index = panel.index + pd.Timedelta(days=shifts[path])
            for column in panel:
                series = panel[column]
                observed = series.dropna()
                if observed.empty:
                    continue
                first, last = observed.index.min(), observed.index.max()
                for year in range(first.year + 1, last.year):
                    block = series.loc[str(year)]
                    missing = block.isna().to_numpy()
                    if not missing.any() or missing.all():
                        continue
                    starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
                    ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
                    for s, e in zip(starts, ends):
                        rows.append({"station_key": f"{provider}|{column}", "network_id": networks[path], "year": year, "provider": provider, "start_doy": int(s + 1), "length": int(e - s)})
        gaps = pd.DataFrame(rows)
    pools: dict[str, list[dict]] = {}
    if gaps.empty:return pools
    for (provider, station, year), block in gaps.groupby(["provider", "station_key", "year"]):
        calendar = {"key": f"{station}:{year}", "runs": list(zip(block.start_doy.astype(int), block.length.astype(int)))}
        pools.setdefault(provider, []).append(calendar)
        if roster in ["usgs_new","independent"]:
            pools.setdefault(station, []).append(calendar)
            pools.setdefault(f"network:{block.network_id.iloc[0]}", []).append(calendar)
    return pools


def pool_for(job: dict, pools: dict[str, list[dict]]) -> list[dict]:
    """Sealed USGS stations use their own calendars, then their network's, then the roster's pool."""

    if job["roster"] in ["usgs_new","independent"]:
        for key in (job["station_key"], f"network:{job['network_id']}"):
            if pools.get(key):
                return pools[key]
    return pools.get(job["provider"], [])


def jobs_for(roster: str) -> list[dict]:
    """The roster's station-network records, each with its position in the sorted roster (for seeds)."""

    jobs = roster_jobs(roster)
    positions = position_index(f"{job['network_id']}|{job['station_id']}" for job in jobs)
    for job in jobs:
        job["station_index"] = positions[f"{job['network_id']}|{job['station_id']}"]
    return jobs


def roster_jobs(roster: str) -> list[dict]:
    sites = pd.read_csv(T.E1 / "usgs_site_metadata.csv", dtype={"site_no": str, "huc2": str}).set_index("site_no").huc2
    if roster in ("source", "real"):
        latitudes = T.station_latitudes()
        jobs, _ = CORE.source_jobs("leave_one_year_out", False)
        for job in jobs:
            job["air_input_path"] = str(T.AIR)
            job["station_key"] = f"{job['provider']}|{job['station_id']}"
            job["region"] = T.region_of(job["provider"], job["network_id"], sites.get(job["station_id"]) if job["provider"] == "usgs" else None)
            job["roster"] = roster
            job["latitude"] = latitudes.get(job["station_key"])
        return jobs
    if roster == "au":
        # Round 2: Australia was the round-1 test region and is a development roster.
        frame = pd.read_csv(AU_ROSTER, dtype=str)
        frame = frame.loc[pd.to_numeric(frame.n_complete_years) >= 4]
        jobs = []
        for row in frame.itertuples(index=False):
            path = Path(row.input_path)
            path = path if path.is_absolute() else T.ROOT / path
            jobs.append({
                "network_id": row.network_id, "station_id": str(row.station_id), "provider": "bom", "independence_group": row.network_id,
                "input_path": str(path), "statistic_class": "daily_mean", "regulation_status": "unknown",
                "air_input_path": str(AU_AIR), "station_key": f"bom|{row.station_id}", "region": "bom", "roster": "au", "latitude": float(row.lat),
            })
        return jobs
    frame = pd.read_csv(NEW_ROSTER, dtype=str)
    jobs = []
    for row in frame.itertuples(index=False):
        path = Path(row.input_path)
        path = path if path.is_absolute() else T.ROOT / path
        jobs.append({
            "network_id": row.network_id, "station_id": str(row.station_id), "provider": "usgs_new", "independence_group": row.independence_group,
            "input_path": str(path), "statistic_class": "daily_mean", "regulation_status": "unknown",
            "air_input_path": str(NEW_AIR), "station_key": f"usgs_new|{row.station_id}", "region": f"usgs_new_huc{row.huc2}", "roster": "usgs_new",
            "latitude": float(row.latitude), "missingness_stratum": row.missingness_stratum,
        })
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roster", choices=["source", "au", "real", "usgs_new"], default="source")
    parser.add_argument("--workers", type=int, default=96)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="reuse station caches left by an interrupted run of the same configuration")
    args = parser.parse_args()
    settings = T.settings()
    generator = json.loads((T.E1_MISSINGNESS / "mnar_generator.json").read_text())
    jobs = jobs_for(args.roster)
    if args.limit:
        jobs = jobs[: args.limit]
    pools = calendar_pool("source" if args.roster == "real" else args.roster, jobs)
    print(f"[431] {args.roster}: {len(jobs)} station-network records; calendar pools {[(k, len(v)) for k, v in pools.items() if '|' not in k and not k.startswith('network:')]}", flush=True)
    started = time.monotonic()
    results = Parallel(n_jobs=args.workers, verbose=5)(delayed(run_station)(job, settings, generator, pool_for(job, pools), args.resume) for job in jobs)
    frames = [pd.read_parquet(result["cache"]) for result in results if result.get("cache")]
    cases = pd.concat([frame for frame in frames if len(frame)], ignore_index=True)
    # Australia is the test region of round 1 (e7_sealed) and a development roster in round 2.
    australia = T.OUT / ("e7_au_development" if settings.get("round", 1) == 2 else "e7_sealed")
    folder = {"source": T.OUT / "e2_cases", "au": australia, "real": T.OUT / "e9_application", "usgs_new": T.OUT / "e10_sealed_usgs"}[args.roster]
    output = folder / ("cases.parquet" if not args.limit else "cases_smoke.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)
    cases.to_parquet(output, index=False)
    summary = {
        "roster": args.roster, "n_cases": len(cases), "n_station_years": int(cases[["station_key", "year"]].drop_duplicates().shape[0]),
        "n_stations": int(cases.station_key.nunique()), "n_groups": int(cases.independence_group.nunique()), "n_regions": int(cases.region.nunique()),
        "families": cases.design_family.value_counts().to_dict(), "policy": cases.policy_choice.value_counts().to_dict(),
        "excluded": [result for result in results if not result.get("cache")], "elapsed_seconds": time.monotonic() - started,
    }
    T.write_json(output.with_name(output.stem + "_summary.json"), summary)
    print({key: value for key, value in summary.items() if key != "excluded"}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
