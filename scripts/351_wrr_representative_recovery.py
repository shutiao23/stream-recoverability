#!/usr/bin/env python3
"""Rebuild repeated controlled recovery and uncertainty diagnostics from daily records."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["STREAM_AIR_FORCING"] = str(ROOT / "data/interim/v18_air_forcing.parquet")

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.cases import deseasonalized_correlations, station_geometry_pool
from stream_recoverability.experiments.v17_fitness.estimators import StationModels, donor_coverage, linear_interp_fill, observed_days_metric, usable_donors
from stream_recoverability.experiments.v17_fitness.independence import independence_table
from stream_recoverability.experiments.v17_fitness.outages import climatological_peak_window, design_for_year
from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.design import GapDesign, event_relative_designs, overlap_class, paired_gap_designs
from stream_recoverability.experiments.v19_revision.trajectory import (
    conditional_trajectories,
    error_channels,
    historical_location_adjustment,
    trajectory_features,
    window_means,
)

OUT = C.RUN / "r3_03_representative_recovery"
CACHE = C.ROOT / "scratch/wrr_revision_20261020c/station_recovery"
COVERAGE = C.READY / "major_revision_20261014/p0_06_coverage_recompute/final_coverage_table.csv"
WAVE2_MANIFEST = C.READY / "p0_07_wave2_ingest/wave2_inputs_manifest.csv"
METHODS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")


def complete_years(target: pd.Series) -> list[int]:
    years = []
    for year, block in target.groupby(target.index.year):
        expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
        if len(block) == expected and np.isfinite(block.to_numpy(dtype=float)).all():
            years.append(int(year))
    return years


def source_jobs(protocol_name: str, smoke: bool) -> tuple[list[dict], pd.DataFrame]:
    coverage = pd.read_csv(COVERAGE, dtype={"station_id": str, "network_id": str})
    manifest = pd.read_csv(WAVE2_MANIFEST, dtype=str).set_index("network_id")
    for network, source in manifest.iterrows():
        match = coverage.network_id.eq(network) & coverage.panel.eq("wave2_confirmation")
        coverage.loc[match, "manifest_input_path"] = source.input_path
        coverage.loc[match, "manifest_sha256"] = source.sha256
    selected = coverage.loc[coverage.in_final_analysis_panel.eq(True)].copy()
    selected = selected.loc[pd.to_numeric(selected.n_complete_years, errors="coerce") >= 4]
    selected = selected.drop_duplicates(["network_id", "station_id"])
    selected["canonical_station_id"] = selected.provider.astype(str) + "|" + selected.station_id.astype(str)
    membership = selected[["network_id", "canonical_station_id"]].rename(columns={"canonical_station_id": "station_id"})
    groups = independence_table(membership).set_index("network_id").independence_group
    selected["independence_group"] = selected.network_id.map(groups)
    if smoke:
        selected = selected.sort_values(["provider", "network_id", "station_id"]).groupby("provider", group_keys=False).head(1)
    jobs = []
    for row in selected.itertuples(index=False):
        path = Path(str(row.manifest_input_path))
        if not path.is_absolute():
            path = C.ROOT / path
        jobs.append(
            {
                "network_id": str(row.network_id),
                "station_id": str(row.station_id),
                "provider": str(row.provider),
                "independence_group": str(row.independence_group),
                "input_path": str(path),
                "source_sha256": str(row.manifest_sha256),
                "statistic_class": str(row.statistic_class),
                "regulation_status": str(row.regulation_status),
                "split_role": str(row.split_role),
                "fit_protocol": protocol_name,
                "smoke": smoke,
            }
        )
    return jobs, selected


def predictions(models: StationModels, observed: np.ndarray, index: pd.DatetimeIndex, donors: tuple[str, ...]) -> dict[str, np.ndarray]:
    fit = models.donor_ridge(donors) if donors else None
    return {
        "doy_climatology": models.doy_climatology(index),
        "smooth_climatology": models.smooth_climatology(index),
        "linear_interp": linear_interp_fill(observed),
        "donor_ridge": models.donor_predict(fit, index) if fit is not None else np.full(len(index), np.nan),
        "air_ridge": models.air_predict(index),
    }


def residual_history(
    target: pd.Series,
    donor_panel: pd.DataFrame,
    air: pd.Series | None,
    allowed: pd.Series,
    years: list[int],
    method: str,
    donor_names: tuple[str, ...],
    missing_dayofyear: tuple[int, ...] = (),
) -> np.ndarray:
    residual = np.full(len(target), np.nan)
    for year in years:
        held = (target.index.year == year) & allowed.to_numpy()
        if not held.any():
            continue
        train = allowed & (target.index.year != year)
        if target.loc[train].notna().sum() < 365:
            continue
        model = StationModels(target=target, donors=donor_panel, air=air, train_mask=train)
        index = target.index[held]
        if method == "linear_interp":
            observed = target.loc[held].to_numpy(dtype=float).copy()
            hidden = np.isin(index.dayofyear.to_numpy(), missing_dayofyear)
            observed[hidden] = np.nan
            center = linear_interp_fill(observed)
        elif method == "donor_ridge":
            fitted = model.donor_ridge(donor_names)
            center = model.donor_predict(fitted, index) if fitted is not None else np.full(len(index), np.nan)
        elif method == "air_ridge":
            center = model.air_predict(index)
        else:
            center = model.smooth_climatology(index)
        errors = target.loc[held].to_numpy(dtype=float) - center
        if method == "linear_interp":
            errors[~hidden] = np.nan
        residual[held] = errors
    return residual


def seasonal_threshold(target: pd.Series, allowed: pd.Series, index: pd.DatetimeIndex, quantile: float) -> np.ndarray:
    history = target.loc[allowed].dropna()
    days = history.index.dayofyear.to_numpy()
    values = history.to_numpy(dtype=float)
    threshold = np.full(367, np.nan)
    for day in np.unique(index.dayofyear):
        distance = np.minimum(np.abs(days - day), 366 - np.abs(days - day))
        nearby = values[distance <= 15]
        if len(nearby):
            threshold[day] = np.quantile(nearby, quantile)
    return threshold[index.dayofyear.to_numpy()]


def historical_error_diagnostics(target: pd.Series, residuals: np.ndarray, years: list[int], mask_days: tuple[int, ...]) -> dict:
    finite = residuals[np.isfinite(residuals)]
    adjacent = np.isfinite(residuals[:-1]) & np.isfinite(residuals[1:])
    correlation = np.nan
    if adjacent.sum() >= 3:
        previous, following = residuals[:-1][adjacent], residuals[1:][adjacent]
        if previous.std() > 0 and following.std() > 0:
            correlation = float(np.corrcoef(previous, following)[0, 1])
    errors = []
    for historical_year in years:
        selected = target.index.year == historical_year
        truth = target.loc[selected].to_numpy(dtype=float)
        hidden = np.isin(target.index[selected].dayofyear.to_numpy(), mask_days)
        noise = residuals[selected]
        if not hidden.any() or not np.isfinite(truth).all() or not np.isfinite(noise[hidden]).all():
            continue
        completed = truth.copy()
        completed[hidden] -= noise[hidden]
        errors.append(float(window_means(completed).max() - window_means(truth).max()))
    return {
        "reconstructor_oof_daily_bias": -float(finite.mean()) if len(finite) else np.nan,
        "reconstructor_oof_daily_abs90": float(np.quantile(np.abs(finite), 0.9)) if len(finite) else np.nan,
        "reconstructor_oof_lag1": correlation,
        "historical_mask_h30_abs90": float(np.quantile(np.abs(errors), 0.9)) if errors else np.nan,
        "historical_mask_h30_bias": float(np.mean(errors)) if errors else np.nan,
        "n_historical_mask_errors": len(errors),
    }


def event_days(values: np.ndarray, threshold: np.ndarray, minimum: int) -> np.ndarray:
    above = np.asarray(values > threshold, dtype=bool)
    starts = np.flatnonzero(above & ~np.r_[False, above[:-1]])
    ends = np.flatnonzero(above & ~np.r_[above[1:], False]) + 1
    events = np.zeros(len(values), dtype=bool)
    for start, end in zip(starts, ends):
        if end - start >= minimum:
            events[start:end] = True
    return events


def calendar_designs(target: pd.Series, index: pd.DatetimeIndex, support: np.ndarray, *, prospective: bool) -> tuple[list[GapDesign], list[dict]]:
    designs = []
    for source_year, block in target.groupby(target.index.year):
        if prospective and int(source_year) >= int(index[0].year):
            continue
        expected = 366 if pd.Timestamp(int(source_year), 12, 31).is_leap_year else 365
        if len(block) != expected or block.isna().all() or block.notna().all():
            continue
        missing_days = set(zip(block.index[block.isna()].month, block.index[block.isna()].day))
        mask = np.array([(month, day) in missing_days for month, day in zip(index.month, index.day)])
        if not mask.any() or mask.all():
            continue
        share = float(mask[support].mean())
        designs.append(GapDesign(f"calendar_{source_year}", "real_calendar", int(mask.sum()), overlap_class(share), 0, mask))
    empty = [] if designs else [{"family": "real_calendar", "reason": "no_eligible_incomplete_calendar_in_allowed_history"}]
    return designs, empty


def select_policy(fills: dict[str, np.ndarray], mask: np.ndarray, gap_length: int) -> str | None:
    order = ("donor_ridge", "air_ridge", "linear_interp", "smooth_climatology", "doy_climatology")
    for method in order:
        if method == "linear_interp" and gap_length > 30:
            continue
        if np.isfinite(fills[method][mask]).all():
            return method
    return None


def intervention_rows(truth: np.ndarray, completed: np.ndarray, mask: np.ndarray, seed: int, n_permutations: int) -> dict:
    residuals = completed[mask] - truth[mask]
    mean = float(residuals.mean())
    centered = residuals - mean
    rng = np.random.default_rng(seed)
    variants = {"raw": [], "permuted": [], "demeaned": [], "demeaned_permuted": []}
    for repeat in range(n_permutations):
        shuffled = rng.permutation(centered)
        for name, errors in (("raw", residuals), ("permuted", shuffled + mean), ("demeaned", centered), ("demeaned_permuted", shuffled)):
            if repeat and name in ("raw", "demeaned"):
                continue
            alternate = truth.copy()
            alternate[mask] += errors
            variants[name].append(abs(float(window_means(alternate).max() - window_means(truth).max())))
    result = {f"oracle_{name}_mae_C": float(np.mean(values)) for name, values in variants.items()}
    result["oracle_interaction_C"] = result["oracle_raw_mae_C"] - result["oracle_permuted_mae_C"] - result["oracle_demeaned_mae_C"] + result["oracle_demeaned_permuted_mae_C"]
    return result


def build_station(job: dict, settings: dict, cache_salt: str) -> dict:
    key = stable_seed(job["network_id"], job["station_id"], job["fit_protocol"], cache_salt, job["smoke"], job.get("air_input_path", "legacy"), job.get("cofailure_fraction", 0), job.get("design_mode", "crossed"), job["source_sha256"])
    cache = CACHE / f"{key}.parquet"
    excluded = CACHE / f"{key}_excluded.json"
    if cache.exists() and excluded.exists():
        return {"cache": str(cache), "exclusions": json.loads(excluded.read_text()), "cached": True}
    path = Path(job["input_path"])
    if not path.exists():
        return {"cache": None, "exclusions": [{**job, "reason": "input_missing"}]}
    if C.digest(path) != job["source_sha256"]:
        raise RuntimeError(f"Daily input drift: {path}")
    panel = read_temperature_panel(str(path))
    panel.columns = panel.columns.astype(str)
    panel = panel.asfreq("D")
    if job["station_id"] not in panel:
        return {"cache": None, "exclusions": [{**job, "reason": "station_missing"}]}
    target = pd.to_numeric(panel[job["station_id"]], errors="coerce")
    donor_panel = panel.drop(columns=job["station_id"])
    years = complete_years(target)
    if len(years) < 4:
        return {"cache": None, "exclusions": [{**job, "reason": "fewer_than_four_strict_complete_years", "n_years": len(years)}]}
    if job["smoke"]:
        years = years[-1:]
    all_years = complete_years(target)
    air_path = Path(job.get("air_input_path", ROOT / "data/interim/v18_air_forcing.parquet"))
    air = station_air_series(air_path, job["network_id"], job["station_id"], panel.index)
    rows, exclusions = [], []
    for year in years:
        held = target.index.year == year
        allowed = pd.Series(target.index.year < year if job["fit_protocol"] == "strictly_prior_years" else ~held, index=target.index)
        train_years = [value for value in all_years if (value < year if job["fit_protocol"] == "strictly_prior_years" else value != year)]
        if len(train_years) < 3:
            exclusions.append({"year": year, "reason": "fewer_than_three_allowed_complete_training_years"})
            continue
        index = target.index[held]
        truth = target.loc[held].to_numpy(dtype=float)
        model = StationModels(target=target, donors=donor_panel, air=air, train_mask=allowed)
        climate = model.smooth_climatology(index)
        support_days = climatological_peak_window(target.loc[allowed])
        support = np.isin(index.dayofyear.to_numpy(), support_days)
        warm = np.isin(index.month.to_numpy(), [5, 6, 7, 8, 9])
        designs, empty = paired_gap_designs(
            support,
            warm,
            seed=stable_seed("r3-design", job["network_id"], job["station_id"], year),
            lengths=tuple(settings["gap_lengths_days"]),
            replicates=settings["realizations_per_cell"],
        )
        exclusions.extend({"year": year, **item} for item in empty)
        train_values = target.loc[allowed].dropna()
        residual = train_values - train_values.groupby(train_values.index.dayofyear).transform("mean")
        training_metrics = np.array([window_means(target.loc[target.index.year == value].to_numpy(dtype=float)).max() for value in train_years])
        local_threshold = float(np.quantile(training_metrics, settings["local_hot_quantile"]))
        event_threshold = seasonal_threshold(target, allowed, index, settings["event_quantile"])
        events = event_days(truth, event_threshold, settings["event_min_duration_days"])
        if job.get("design_mode") == "events":
            designs, empty = event_relative_designs(events, support, lengths=tuple(settings["gap_lengths_days"]))
            exclusions.extend({"year": year, **item} for item in empty)
        elif job.get("design_mode") == "real_calendars":
            designs, empty = calendar_designs(target, index, support, prospective=job["fit_protocol"] == "strictly_prior_years")
            exclusions.extend({"year": year, **item} for item in empty)
        elif job.get("design_mode") == "admission":
            geometry_panel = panel.loc[allowed] if job["fit_protocol"] == "strictly_prior_years" else panel
            pool = station_geometry_pool(geometry_panel)
            realizations = design_for_year(index, support_days, pool, rng=np.random.default_rng(stable_seed(job["network_id"], job["station_id"], year, job["fit_protocol"])), n_empirical=5, cross_overlap=False)
            designs = [GapDesign(real.realization_id, real.arm, real.total_missing, real.overlap_class, 0, real.mask(len(index))) for real in realizations]
        truth_metric = float(window_means(truth).max())
        true_start = int(np.argmax(window_means(truth)))
        with np.errstate(invalid="ignore", divide="ignore"):
            correlations = deseasonalized_correlations(target, donor_panel, allowed)
        historical_residual_cache = {}
        for design in designs:
            mask = design.mask
            starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
            ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
            longest_run = int((ends - starts).max())
            longest_start = int(starts[np.argmax(ends - starts)])
            observed = truth.copy()
            observed[mask] = np.nan
            visible = usable_donors(donor_panel, index, mask)
            cofailure = float(job.get("cofailure_fraction", 0))
            removed = ()
            if cofailure and visible:
                removal_order = np.random.default_rng(stable_seed("r3-cofailure", job["network_id"], job["station_id"], year, design.key)).permutation(visible)
                removed = tuple(removal_order[: int(np.ceil(cofailure * len(visible)))])
                visible = tuple(station for station in visible if station not in removed)
            fills = predictions(model, observed, index, visible)
            choice = select_policy(fills, mask, longest_run)
            month = int(index[longest_start].month)
            selected_correlations = correlations.reindex(list(visible)).dropna()
            coverage = donor_coverage(donor_panel, index, mask)
            if removed:
                coverage.loc[list(removed)] = 0
            completed_methods, metrics = {}, {}
            for name, prediction in fills.items():
                completed = observed.copy()
                completed[mask] = prediction[mask]
                if np.isfinite(completed).all():
                    completed_methods[name] = completed
                    metrics[name] = float(window_means(completed).max())
            policy_metric = metrics[choice] if choice else np.nan
            observed_peak = observed_days_metric(observed)
            row = {
                "network_id": job["network_id"], "station_id": job["station_id"], "provider": job["provider"],
                "independence_group": job["independence_group"], "statistic_class": job["statistic_class"],
                "regulation_status": job["regulation_status"], "split_role": job["split_role"],
                "fit_protocol": job["fit_protocol"], "year": year, "realization_id": design.key,
                "training_complete_years": ";".join(map(str, train_years)),
                "maximum_training_calendar_year": int(target.loc[allowed].index.year.max()),
                "mask_runs": ";".join(f"{start}:{end-start}" for start, end in zip(starts, ends)),
                "visible_donor_ids": ";".join(visible),
                "design_family": design.family, "overlap_class": design.overlap_class, "replicate": design.replicate,
                "longest_run": longest_run,
                "total_missing": int(mask.sum()), "missing_fraction": float(mask.mean()),
                "n_runs": int((mask & ~np.r_[False, mask[:-1]]).sum()),
                "warm_observed_fraction": float((~mask & warm).sum() / warm.sum()),
                "peak_overlap": float(mask[support].mean()),
                "true_peak_hidden_fraction": float(mask[true_start : true_start + 30].mean()),
                "month_sin": float(np.sin(2 * np.pi * month / 12)), "month_cos": float(np.cos(2 * np.pi * month / 12)),
                "longest_run_month": month,
                "left_flank": bool(not mask[0]), "right_flank": bool(not mask[-1]),
                "n_visible_donors": len(visible),
                "donor_corr_mean": float(selected_correlations.mean()) if len(selected_correlations) else np.nan,
                "donor_corr_min": float(selected_correlations.min()) if len(selected_correlations) else np.nan,
                "donor_corr_max": float(selected_correlations.max()) if len(selected_correlations) else np.nan,
                "donor_coverage_mean": float(coverage.mean()) if len(coverage) else np.nan,
                "air_available": "air_ridge" in metrics,
                "train_resid_sd": float(residual.std()), "seasonal_amplitude": float(np.nanmax(climate) - np.nanmin(climate)),
                "train_metric_sd": float(training_metrics.std(ddof=1)), "n_complete_years": len(train_years),
                "record_years": int(target.loc[allowed].index.year.nunique()),
                "truth_hottest30": truth_metric, "clim_peak": float(window_means(climate).max()),
                "truth_annual_mean": float(truth.mean()),
                "truth_hottest7": float(window_means(truth, 7).max()),
                "truth_coldest30": float(window_means(truth).min()),
                "observed_peak": observed_peak,
                "observed_peak_margin": observed_peak - float(window_means(climate).max()),
                "has_complete_window": bool((np.convolve((~mask).astype(int), np.ones(30, dtype=int), mode="valid") == 30).any()),
                "local_hot_threshold_C": local_threshold, "truth_local_hot": truth_metric > local_threshold,
                "warm_anomaly": truth_metric - float(window_means(climate).max()) >= settings["warm_anomaly_c"],
                "n_truth_event_days": int(events.sum()), "n_hidden_event_days": int((events & mask).sum()),
                "policy_choice": choice or "unavailable", "policy_metric": policy_metric,
                "abserr_policy": abs(policy_metric - truth_metric), "policy_bad": not np.isfinite(policy_metric) or abs(policy_metric - truth_metric) > settings["tolerance_c"],
                "estimator_disagreement": max(metrics.values()) - min(metrics.values()) if metrics else np.nan,
            }
            if "cofailure_fraction" in job:
                row["cofailure_fraction"] = cofailure
                row["event_phase"] = design.key.split("_")[1] if design.family == "event_relative" else "not_targeted"
            prediction_stack = np.array([fills[name][mask] for name in metrics])
            row["daily_estimator_disagreement"] = float(np.mean(prediction_stack.max(axis=0) - prediction_stack.min(axis=0))) if len(prediction_stack) else np.nan
            for name in METHODS:
                row[f"hottest30_{name}"] = metrics.get(name, np.nan)
                row[f"abserr_{name}"] = abs(metrics[name] - truth_metric) if name in metrics else np.nan
                if name in completed_methods:
                    completed = completed_methods[name]
                    row[f"annual_mean_error_C__{name}"] = float(completed.mean() - truth.mean())
                    row[f"hottest7_error_C__{name}"] = float(window_means(completed, 7).max() - row["truth_hottest7"])
                    row[f"coldest30_error_C__{name}"] = float(window_means(completed).min() - row["truth_coldest30"])
                    row[f"gap_mean_error_C__{name}"] = float((completed[mask] - truth[mask]).mean())
                    channels = error_channels(truth, completed_methods[name])
                    row.update({f"{key}__{name}": value for key, value in channels.items()})
                    if design.replicate == 0 and design.family == "crossed_contiguous":
                        oracle = intervention_rows(truth, completed_methods[name], mask, stable_seed("r3-intervention", job["network_id"], job["station_id"], year, design.key, name), settings["residual_intervention_permutations"])
                        row.update({f"{key}__{name}": value for key, value in oracle.items()})
            if choice:
                missing_dayofyear = tuple(index.dayofyear.to_numpy()[mask]) if choice == "linear_interp" else ()
                residual_key = (choice, tuple(visible) if choice == "donor_ridge" else (), missing_dayofyear)
                if residual_key not in historical_residual_cache:
                    historical_residual_cache[residual_key] = residual_history(target, donor_panel, air, allowed, train_years, choice, tuple(visible), missing_dayofyear)
                training_residuals = historical_residual_cache[residual_key]
                finite_training_residuals = training_residuals[np.isfinite(training_residuals)]
                row["reconstructor_oof_daily_sd"] = float(finite_training_residuals.std()) if len(finite_training_residuals) else np.nan
                if job.get("design_mode") in {"admission", "events", "real_calendars", "crossed"}:
                    row.update(historical_error_diagnostics(target, training_residuals, train_years, tuple(index.dayofyear.to_numpy()[mask])))
                    row["scaled_support_uncertainty"] = row["peak_overlap"] * row["reconstructor_oof_daily_sd"]
                adjustment = historical_location_adjustment(observed, fills[choice])
                adjusted = completed_methods[choice].copy()
                adjusted[mask] += adjustment
                row["deployable_adjustment_C"] = adjustment
                row["adjusted_h30"] = float(window_means(adjusted).max())
                row["adjusted_abserr"] = abs(row["adjusted_h30"] - truth_metric)
                try:
                    draws = conditional_trajectories(observed, fills[choice], training_residuals, seed=stable_seed("r3-draw", job["network_id"], job["station_id"], year, design.key), n_draws=settings["trajectory_draws"], block_days=settings["residual_block_days"])
                    row.update(trajectory_features(draws, mask, policy_metric))
                    row["uncertainty_status"] = "available"
                except ValueError as error:
                    row["uncertainty_status"] = str(error)
            else:
                row["uncertainty_status"] = "point_reconstruction_unavailable"
            rows.append(row)
    result = pd.DataFrame(rows)
    result.to_parquet(cache, index=False)
    C.write_json(excluded, {"records": exclusions})
    return {"cache": str(cache), "exclusions": {"records": exclusions}, "cached": False, "n_cases": len(result)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    settings = C.protocol()
    output = (C.ROOT / "scratch/wrr_revision_20261020c/smoke" if args.smoke else OUT) / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    jobs, roster = source_jobs(args.protocol, args.smoke)
    roster.to_csv(output / "eligible_roster_before_scoring.csv", index=False)
    salt = C.digest(Path(__file__)) + C.digest(C.CONFIG)
    C.write_json(output / "jobs.json", {"jobs": jobs, "script_hash": C.digest(Path(__file__))})
    print(f"[351] {args.protocol}: {len(jobs)} station-network records from {roster.network_id.nunique()} networks", flush=True)
    started = time.monotonic()
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(build_station)(job, settings, salt) for job in jobs)
    frames = [pd.read_parquet(result["cache"]) for result in results if result["cache"]]
    frames = [frame for frame in frames if len(frame)]
    if not frames:
        raise RuntimeError("No station contributed a valid recovery case")
    cases = pd.concat(frames, ignore_index=True)
    cases.to_parquet(output / "cases.parquet", index=False)
    case_keys = cases[["network_id", "station_id", "year"]].drop_duplicates()
    summary = {
        "fit_protocol": args.protocol, "smoke": args.smoke, "n_cases": len(cases),
        "n_networks": cases.network_id.nunique(), "n_stations": cases.station_id.nunique(),
        "n_station_network_years": len(case_keys), "n_providers": cases.provider.nunique(),
        "n_uncertainty_available": int(cases.uncertainty_status.eq("available").sum()),
        "elapsed_seconds": time.monotonic() - started,
        "evidence_role": "opened existing archive, broader controlled retrospective experiment",
    }
    C.write_json(output / "summary.json", summary)
    C.write_json(output / "exclusions.json", {"stations": results})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"coverage": COVERAGE, "external_manifest": WAVE2_MANIFEST}))
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
