#!/usr/bin/env python3
"""Whole-archive stress with a matched-count heat-associated scenario.

Donor stations remain observed in this experiment. Every selected year of the
target station is hidden before any local fitting. Annual models and offsets
use source roles disjoint from held test groups. In the original forward role
assignment, other training-only groups from the named region can remain. The
forward experiment uses source models/calibration trained before 2010 and evaluates
2010 onward; its local daily models also use observations before 2010 only.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.tr_revision.archive import (
    LEVELS,
    apply_observed_lower_bound,
    factorial_contrasts,
    history_ranks,
    marginal_draws,
    mask_archive,
    reorder_marginals,
    slope,
    trend_result,
)
from stream_recoverability.seeds import plain_seed

SOURCE = T.ROOT / "results/wrr_review_completion_20261024"
OUT = T.ROOT / "results/whole_archive"


def matched_heat_years(baseline_uniform, selection_uniform, eligible, hot):
    """Use baseline count with weighted, label-free sampling of hot years."""
    uniform = np.asarray(baseline_uniform, dtype=float)
    selection = np.asarray(selection_uniform, dtype=float)
    eligible = np.asarray(eligible, dtype=bool)
    hot = np.asarray(hot, dtype=bool)
    if uniform.ndim != 1 or uniform.shape != eligible.shape or uniform.shape != hot.shape or uniform.shape != selection.shape:
        raise ValueError("Uniforms, eligibility and heat flags must align")
    if not np.isfinite(uniform).all() or ((uniform < 0) | (uniform >= 1)).any() or not np.isfinite(selection).all() or ((selection < 0) | (selection >= 1)).any():
        raise ValueError("Uniform draws must lie in [0, 1)")
    count = int(((uniform < .35) & eligible).sum())
    weights = np.where(hot, 5.0, 1.0)
    ids = np.flatnonzero(eligible)
    keys = -np.log(np.maximum(selection[ids], np.finfo(float).tiny)) / weights[ids]
    missing = np.zeros(len(uniform), dtype=bool)
    missing[ids[np.argsort(keys, kind="stable")[:count]]] = True
    return missing


def classical_calibration(source, region, refit):
    """The same source interval-calibration groups used by the annual model."""
    source = source.loc[
        source.policy_choice.ne("unavailable") & source.eval_truth_h30.notna()
    ].reset_index(drop=True)
    _, _, weights = refit.roles(
        source, region, plain_seed(7, 0, sorted(set(source.region.unique()) | {region}).index(region))
    )
    difficulty = refit.difficulty(source)
    result = {"offsets": {}}
    for prefix in ["stochastic", "state"]:
        q = source[
            [f"{prefix}_h30_q{int(100 * level):02d}" for level in LEVELS]
        ].to_numpy(float)
        q = apply_observed_lower_bound(q, source.observed_lower_bound__observed_days)
        valid = np.isfinite(q).all(axis=1)
        offsets = {}
        for cell in ["__pooled__", *sorted(difficulty.unique())]:
            pool = (weights["interval_calibration"] > 0) & valid
            if (
                cell != "__pooled__"
                and (pool & difficulty.eq(cell).to_numpy()).sum() >= 50
            ):
                pool &= difficulty.eq(cell).to_numpy()
            residual = np.repeat(
                source.loc[pool, "eval_truth_h30"].to_numpy()[:, None] - q[pool],
                weights["interval_calibration"][pool].astype(int),
                axis=0,
            )
            offsets[cell] = [
                float(
                    np.quantile(
                        residual[:, j],
                        level,
                        method="higher" if level >= 0.5 else "lower",
                    )
                )
                for j, level in enumerate(LEVELS)
            ]
        result["offsets"][prefix] = offsets
    return result


def recalibrate_d2(source, region, refit, bundle):
    """Re-estimate quantile offsets on the original independent calibration role.

    Projection is applied before and after offset correction for both methods.
    Original quantile-model weights stay fixed; target-region data never enter
    the recalibration role.
    """
    import wrr_tr_features as F

    source = source.loc[
        source.policy_choice.ne("unavailable") & source.eval_truth_h30.notna()
    ].reset_index(drop=True)
    _, roles, weights = refit.roles(
        source, region, plain_seed(7, 0, sorted(set(source.region.unique()) | {region}).index(region))
    )
    if roles != bundle["roles"]:
        raise RuntimeError("Recalibration roles do not match the original fitted model")
    selected = weights["interval_calibration"] > 0
    calibration = source.loc[selected].copy()
    x = F.design_matrix(calibration, simulation=True).reindex(columns=bundle["features"])
    raw = np.sort(
        np.column_stack([model.predict(x) for model in bundle["quantile_models"]])
        + calibration.h30__policy.to_numpy(float)[:, None], axis=1
    )
    raw = apply_observed_lower_bound(raw, calibration.observed_lower_bound__observed_days)
    difficulty = refit.difficulty(calibration)
    all_difficulty = refit.difficulty(source)
    multiplicity = weights["interval_calibration"][selected].astype(int)
    offsets = {}
    for cell in sorted(all_difficulty.unique()):
        pool = difficulty.eq(cell).to_numpy()
        if pool.sum() < 50:
            pool = np.ones(len(calibration), dtype=bool)
        residual = np.repeat(
            calibration.eval_truth_h30.to_numpy(float)[pool, None] - raw[pool],
            multiplicity[pool], axis=0
        )
        offsets[cell] = [float(np.quantile(residual[:, j], level,
                           method="higher" if level >= 0.5 else "lower"))
                         for j, level in enumerate(LEVELS)]
    return offsets, roles["interval_calibration"]


def one(
    job,
    reference,
    replicate,
    mode,
    family,
    calibration,
    output,
    draws,
    resume,
    reanalyze=False,
    scenario="baseline",
):
    folder = (
        output
        / family
        / mode
        / f"replicate_{replicate:02d}"
        / job["station_key"].replace("|", "_")
    )
    folder.mkdir(parents=True, exist_ok=True)
    completed = folder / (
        "annual_predictions.parquet" if mode == "calibration" else "trends.csv"
    )
    if resume and not reanalyze and completed.exists():
        return str(folder)
    core = T.load_script("whole_archive_cases", T.ROOT / "scripts/431_tr_cases.py")
    inference = T.load_script(
        "whole_archive_inference",
        T.ROOT / "scripts/495_review_completion_independent_analysis.py",
    )
    rng = np.random.default_rng(plain_seed(521, job["station_index"], replicate))
    all_years = np.array(sorted(reference.year.unique()))
    selected = pd.DataFrame(
        [
            g.iloc[int(rng.integers(len(g)))]
            for _, g in reference.groupby("year", sort=True)
        ]
    )
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    shift = T.hemisphere_shift_days(job.get("latitude"))
    real_index = panel.index
    analysis = panel.copy()
    analysis.index += pd.Timedelta(days=shift)
    # Seven fully observed years precede the jointly degraded archive.
    probabilities = np.full(len(all_years), 0.35)
    if scenario in {"heat_associated", "heat_associated_matched"}:
        air = station_air_series(Path(job["air_input_path"]), job["network_id"], job["station_id"], real_index)
        if air is None:
            T.write_json(folder / "unavailable.json", {"reason": "no air forcing for heat-associated masking"})
            return str(folder)
        air.index = analysis.index
        annual_air = []
        for year in all_years:
            values = air.loc[air.index.year == year].to_numpy(float)
            annual_air.append(float(np.max(T.window_means(values, 30))) if len(values) >= 30 and np.isfinite(values).all() else np.nan)
        annual_air = np.asarray(annual_air)
        baseline = annual_air[:7]
        if np.isfinite(baseline).sum() < 4 or not np.isfinite(annual_air).all():
            T.write_json(folder / "unavailable.json", {"reason": "insufficient air data for prespecified heat-associated masking"})
            return str(folder)
        cutoff = np.nanquantile(baseline, 0.8)
        probabilities = np.where(annual_air >= cutoff, 0.90, 0.18)
    uniform = rng.random(len(all_years))
    eligible = np.arange(len(all_years)) >= 7
    if mode == "forward":
        eligible &= all_years >= 2010
    if scenario == "heat_associated_matched":
        # Preserve the baseline number of missing years for this exact archive.
        # Exponential-race sampling gives heat-associated years five times the
        # sampling weight, conditional on that fixed count. A separate seeded
        # stream selects years so the baseline count and subsequent random
        # draws remain paired with the original calculation.
        heat_rng = np.random.default_rng(plain_seed(689, job["station_index"], replicate))
        missing = matched_heat_years(uniform, heat_rng.random(len(all_years)), eligible, annual_air >= cutoff)
    else:
        missing = (uniform < probabilities) & eligible
    masks = dict(zip(all_years[missing], selected.loc[missing, "mask_runs"]))
    visible = mask_archive(analysis, job["station_id"], masks)
    if scenario == "synchronized_donors":
        for donor in visible.columns.difference([job["station_id"]]):
            visible = mask_archive(visible, donor, masks)
    years = all_years[all_years >= 2010] if mode == "forward" else all_years
    if len(years) < 5:
        T.write_json(
            folder / "unavailable.json",
            {"reason": "fewer than five evaluation years", "n_years": len(years)},
        )
        return str(folder)
    split = "leave_one_year_out" if mode == "offline" else "before_2010"
    settings = T.settings() | {
        "version": f"whole_archive_{scenario}/{family}/{mode}/replicate_{replicate:02d}",
        "replication_seeds": [replicate],
        "training_split": split,
        "classical_baselines": True,
        "trajectory_targets": ["h30"],
    }
    generator = json.loads((T.E1_MISSINGNESS / "mnar_generator.json").read_text())
    if reanalyze and (folder / "annual_predictions.parquet").exists():
        cases = pd.read_parquet(folder / "annual_predictions.parquet")
    else:
        with TemporaryDirectory(dir=folder) as temporary:
            path = Path(temporary) / "visible.csv"
            water = visible.copy()
            water.index = real_index
            water.index.name = "date"
            water.to_csv(path)
            local = job | {
                "input_path": str(path),
                "roster": "real",
                "real_years": sorted(masks),
            }
            result = (
                core.station_cases(local, settings, generator, [], False)
                if masks
                else {}
            )
        cases = (
            pd.read_parquet(result["cache"]) if result.get("cache") else pd.DataFrame()
        )
    if mode == "calibration":
        cases.to_parquet(folder / "annual_predictions.parquet", index=False)
        T.write_json(
            folder / "design.json",
            {
                "role": "pre-2010 task calibration features only",
                "station_key": job["station_key"],
                "years": list(map(int, years)),
                "masks": {str(y): m for y, m in masks.items()},
                "daily_training_years": "before 2010 only",
            },
        )
        return str(folder)
    if len(cases):
        bundle = joblib.load(
            SOURCE / "refits" / split / "seed_00" / f"{job['region']}.joblib"
        )
        if "D2_offsets" in calibration:
            bundle["offsets"] = calibration["D2_offsets"]
        cases = inference.classical_predictions(
            inference.predict(cases, bundle), calibration
        )
    cases.to_parquet(folder / "annual_predictions.parquet", index=False)
    reference_indexed = selected.set_index("year")
    truth = reference_indexed.loc[years, "eval_truth_h30"].to_numpy(float)
    incomplete = np.isin(years, list(masks))
    filled = (
        cases.set_index("year").reindex(years)
        if len(cases)
        else pd.DataFrame(index=years)
    )
    warm90 = (
        ~incomplete
        | filled.get("warm_observed_fraction", pd.Series(np.nan, index=years))
        .ge(0.9)
        .to_numpy()
    )
    air = station_air_series(
        Path(job["air_input_path"]), job["network_id"], job["station_id"], real_index
    )
    if air is not None:
        air.index = visible.index
    history_target = visible[job["station_id"]].copy()
    ranks = {"independent": rng.normal(size=(draws, len(years)))}
    for name, block in [("shared_parameters", 1), ("residual_blocks", 3)]:
        ranks[name] = history_ranks(
            history_target,
            air,
            masks,
            years,
            draws=draws,
            seed=plain_seed(522, job["station_index"], replicate),
            block=block,
            fit_before=2010 if mode == "forward" else None,
        )
    common = {
        "station_key": job["station_key"],
        "independence_group": job["independence_group"],
        "region": job["region"],
        "replicate": replicate,
        "mode": mode,
        "family": family,
        "scenario": scenario,
        "n_years": len(years),
        "n_incomplete": int(incomplete.sum()),
    }
    trends, annual = [], []
    for estimator, column, prefix in [
        ("plug_in", "h30__policy", None),
        ("stochastic_calibrated", "stochastic_cal_q50", "stochastic_cal"),
        ("D2", "D2", "D2"),
    ]:
        point = truth.copy()
        predicted = filled.get(column, pd.Series(np.nan, index=years)).to_numpy(float)
        point[incomplete] = predicted[incomplete]
        for retention, keep in [("warm90", warm90), ("all", np.ones(len(years), bool))]:
            available = keep.sum() >= 5 and np.isfinite(point[keep]).all()
            row = common | {
                "estimator": estimator,
                "retention": retention,
                "dependence": "point",
                "available": bool(available),
                "n_retained": int(keep.sum()),
            }
            if available:
                estimate = float(slope(years[keep], point[keep]))
                expected = float(slope(years, truth))
                row.update(
                    truth_slope=expected,
                    slope=estimate,
                    error=estimate - expected,
                    squared_error=(estimate - expected) ** 2,
                )
            trends.append(row)
        valid = incomplete & np.isfinite(predicted)
        annual.append(
            common
            | {
                "estimator": estimator,
                "n_eligible": int(incomplete.sum()),
                "n_available": int(valid.sum()),
                "mae": float(np.mean(abs(point[valid] - truth[valid])))
                if valid.any()
                else np.nan,
            }
        )
        if prefix is None:
            continue
        quantiles = filled.reindex(
            columns=[f"{prefix}_q{int(100 * q):02d}" for q in LEVELS]
        ).to_numpy(float)
        quantiles[~incomplete] = truth[~incomplete, None]
        if not np.isfinite(quantiles).all():
            for dependence in ranks:
                trends.append(
                    common
                    | {
                        "estimator": estimator,
                        "retention": "all",
                        "dependence": dependence,
                        "available": False,
                    }
                )
            continue
        low, high = quantiles[incomplete, 0], quantiles[incomplete, -1]
        annual[-1].update(
            coverage90=float(
                np.mean((truth[incomplete] >= low - 1e-8) & (truth[incomplete] <= high + 1e-8))
            )
            if incomplete.any()
            else np.nan,
            width90=float(np.mean(high - low)) if incomplete.any() else np.nan,
        )
        bounds = filled.get(
            "observed_lower_bound__observed_days", pd.Series(np.nan, index=years)
        ).to_numpy(float)
        bounds[~incomplete] = truth[~incomplete]
        base = marginal_draws(quantiles, draws, lower_bounds=bounds)
        for dependence, rank in ranks.items():
            row = common | {
                "estimator": estimator,
                "retention": "all",
                "dependence": dependence,
                "available": rank is not None,
            }
            if rank is not None:
                samples = reorder_marginals(base, rank)
                row.update(trend_result(years, truth, point, samples))
            trends.append(row)
    # Exact same selected masks and years from the old, separately fitted cases.
    if mode == "offline":
        old_point = truth.copy()
        old_point[incomplete] = reference_indexed.loc[years[incomplete], "h30__policy"]
        trends.append(
            common
            | {
                "estimator": "precomputed_plugin",
                "retention": "all",
                "dependence": "point",
                "available": bool(np.isfinite(old_point).all()),
                **trend_result(years, truth, old_point),
            }
        )
    pd.DataFrame(trends).to_csv(folder / "trends.csv", index=False)
    pd.DataFrame(annual).to_csv(folder / "annual.csv", index=False)
    hidden_remaining = 0
    donor_hidden_remaining = 0
    for year, runs in masks.items():
        values = visible.loc[visible.index.year == year, job["station_id"]].to_numpy(
            float
        )
        for run in str(runs).split(";"):
            start, length = map(int, run.split(":"))
            hidden_remaining += int(np.isfinite(values[start : start + length]).sum())
            if scenario == "synchronized_donors":
                donor_values = visible.loc[visible.index.year == year].drop(columns=job["station_id"]).iloc[start:start + length].to_numpy(float)
                donor_hidden_remaining += int(np.isfinite(donor_values).sum())
    T.write_json(
        folder / "design.json",
        common
        | {
            "masks": {str(y): m for y, m in masks.items()},
            "all_masks_applied_before_fitting": True,
            "hidden_values_present_in_visible_archive": hidden_remaining,
            "hidden_donor_values_present": donor_hidden_remaining if scenario == "synchronized_donors" else None,
            "donors": "same gaps simultaneously hidden" if scenario == "synchronized_donors" else "other physical stations remain observed",
            "source_model_split": split,
            "annual_model": "held test connected groups excluded; full named-region exclusion depends on the source model roles; inspect the source-role audit",
            "marginals": "identical annual samples for all three dependence modes; normal-spacing tail extrapolation, constrained by observed-window support",
        },
    )
    return str(folder)


def summarize(output):
    paths = sorted(
        p
        for family in ["calendar", "crossed"]
        for p in (output / family).glob("*/replicate_*/*/trends.csv")
    )
    trends = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    annual = pd.concat(
        [pd.read_csv(p.parent / "annual.csv") for p in paths], ignore_index=True
    )
    trends.to_csv(output / "trends.csv", index=False)
    annual.to_csv(output / "annual.csv", index=False)
    groups = ["family", "mode", "estimator", "retention", "dependence"]
    summary = []
    for key, g in trends.groupby(groups):
        valid = g.loc[g.available]
        row = dict(
            zip(groups, key),
            n_eligible=len(g),
            n_available=len(valid),
            availability=len(valid) / len(g),
        )
        if len(valid):
            row.update(
                rmse=float(np.sqrt(valid.squared_error.mean())),
                bias=float(valid.error.mean()),
            )
            for column in ["missing_coverage95", "width95", "interval_score95"]:
                if column in valid:
                    row[column] = float(valid[column].mean())
        summary.append(row)
    pd.DataFrame(summary).to_csv(output / "trend_summary.csv", index=False)
    annual.groupby(["family", "mode", "estimator"]).agg(
        n_eligible=("n_eligible", "sum"),
        n_available=("n_available", "sum"),
        mean_station_mae=("mae", "mean"),
        mean_station_coverage90=("coverage90", "mean"),
        mean_station_width90=("width90", "mean"),
    ).reset_index().to_csv(output / "annual_summary.csv", index=False)
    points = trends.loc[
        trends.dependence.eq("point")
        & trends.estimator.isin(["plug_in", "stochastic_calibrated", "D2"])
    ]
    contrasts = factorial_contrasts(points)
    contrasts.to_csv(output / "factorial_contrasts.csv", index=False)
    contrasts.groupby(["family", "mode", "estimator"]).mean(
        numeric_only=True
    ).reset_index().to_csv(output / "factorial_summary.csv", index=False)
    T.write_json(
        output / "status.json",
        {
            "completed_station_repetitions": len(paths),
            "n_stations": trends.station_key.nunique(),
            "n_regions": trends.region.nunique(),
            "replicates": sorted(map(int, trends.replicate.unique())),
            "modes": sorted(trends["mode"].unique()),
            "interpretation": "exploratory paired experiments on opened source archives; repeated masks are not independent climates",
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--replicates", type=int, default=20)
    p.add_argument("--limit-stations", type=int)
    p.add_argument("--draws", type=int, default=256)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--summarize-only", action="store_true")
    p.add_argument(
        "--reanalyze",
        action="store_true",
        help="reuse daily refits and refresh annual calibration and trend summaries",
    )
    p.add_argument("--output", type=Path, default=OUT)
    p.add_argument("--scenario", default="baseline", choices=["baseline", "heat_associated", "heat_associated_matched", "synchronized_donors"])
    p.add_argument(
        "--modes",
        nargs="+",
        default=["offline", "forward"],
        choices=["offline", "forward", "calibration"],
    )
    p.add_argument(
        "--families",
        nargs="+",
        default=["calendar", "crossed"],
        choices=["calendar", "crossed"],
    )
    args = p.parse_args()
    output = args.output
    if args.limit_stations:
        output = output / f"pilot_{args.limit_stations}"
    output.mkdir(parents=True, exist_ok=True)
    if args.summarize_only:
        summarize(output)
        return 0
    core = T.load_script("whole_archive_parent", T.ROOT / "scripts/431_tr_cases.py")
    refit = T.load_script(
        "whole_archive_roles", T.ROOT / "scripts/466_review_completion_refit.py"
    )
    cols = [
        "station_key",
        "region",
        "independence_group",
        "year",
        "design_family",
        "mask_runs",
        "h30__policy",
        "eval_truth_h30",
    ]
    reference = pd.read_parquet(
        SOURCE / "cases/leave_one_year_out/seed_00.parquet", columns=cols
    )
    counts = reference.groupby("station_key").year.nunique()
    eligible = counts[counts >= 20].index
    jobs = [j for j in core.jobs_for("source") if j["station_key"] in eligible]
    # Round-robin regions for small pilots, without selecting by prediction errors.
    grouped = {}
    for job in sorted(jobs, key=lambda j: j["station_key"]):
        grouped.setdefault(job["region"], []).append(job)
    jobs = [
        group[i]
        for i in range(max(map(len, grouped.values())))
        for group in grouped.values()
        if i < len(group)
    ]
    if args.limit_stations:
        jobs = jobs[: args.limit_stations]
    T.write_json(
        output
        / (
            "calibration_design.json"
            if args.modes == ["calibration"]
            else "design.json"
        ),
        {
            "station_keys": [j["station_key"] for j in jobs],
            "replicates": args.replicates,
            "draws": args.draws,
            "modes": args.modes,
            "families": args.families,
            "eligible_complete_years_minimum": 20,
            "scenario": args.scenario,
            "year_missing_probability": "0.90 for air-hot years and 0.18 otherwise, relative to first-seven-year air H30 80th percentile" if args.scenario == "heat_associated" else ("matched baseline year count; exponential-race weight 5 for air-hot years and 1 otherwise" if args.scenario == "heat_associated_matched" else 0.35),
            "first_seven_years": "observed burn-in",
            "forward_source_cutoff": 2010,
            "donor_availability": "same target masks applied to donors" if args.scenario == "synchronized_donors" else "observed neighboring stations, same for every method",
        },
    )
    columns = [
        "region",
        "independence_group",
        "policy_choice",
        "eval_truth_h30",
        "peak_overlap",
        "training_partition",
        "network_id",
        "station_key",
        "year",
        "design_family",
        "realization_id",
        "mask_runs",
    ]
    columns += [
        f"{prefix}_h30_q{int(100 * q):02d}"
        for prefix in ["stochastic", "state"]
        for q in LEVELS
    ]
    calibrations = {}
    for mode in args.modes:
        if mode == "calibration":
            continue
        split = "before_2010" if mode == "forward" else "leave_one_year_out"
        path = SOURCE / "cases" / split / "seed_00.parquet"
        source = pd.read_parquet(path)
        analysis = T.load_script(
            "whole_archive_classical_repairs",
            T.ROOT / "scripts/467_review_completion_analysis.py",
        )
        source = analysis.apply_bridge_repairs(source, 0, split)
        for region in sorted({j["region"] for j in jobs}):
            if (SOURCE / "refits" / split / "seed_00" / f"{region}.joblib").exists():
                calibrations[mode, region] = classical_calibration(
                    source, region, refit
                )
                bundle = joblib.load(SOURCE / "refits" / split / "seed_00" / f"{region}.joblib")
                offsets, calibration_groups = recalibrate_d2(source, region, refit, bundle)
                calibrations[mode, region]["D2_offsets"] = offsets
                calibrations[mode, region]["D2_calibration_groups"] = calibration_groups
    path = output / "classical_calibration.json"
    saved_calibrations = json.loads(path.read_text()) if path.exists() else {}
    saved_calibrations.update(
        {
            mode: {
                region: value
                for (m, region), value in calibrations.items()
                if m == mode
            }
            for mode in args.modes
            if mode != "calibration"
        }
    )
    T.write_json(path, saved_calibrations)
    todo, unavailable = [], []
    for job in jobs:
        for family in args.families:
            ref = reference.loc[
                reference.station_key.eq(job["station_key"])
                & reference.design_family.eq(family)
            ]
            for mode in args.modes:
                current = ref.loc[ref.year.lt(2010)] if mode == "calibration" else ref
                if current.year.nunique() < (10 if mode == "calibration" else 20):
                    continue
                if mode != "calibration" and (mode, job["region"]) not in calibrations:
                    unavailable.append(
                        {
                            "station_key": job["station_key"],
                            "region": job["region"],
                            "mode": mode,
                            "family": family,
                            "reason": "no complete reference years from 2010 onward"
                            if not ref.year.ge(2010).any()
                            else "no existing source model for this region and time split",
                        }
                    )
                    continue
                for rep in range(args.replicates):
                    todo.append(
                        (
                            job,
                            current,
                            rep,
                            mode,
                            family,
                            calibrations.get((mode, job["region"])),
                        )
                    )
    if args.modes != ["calibration"]:
        T.write_json(output / "unavailable.json", unavailable)
    start = time.monotonic()
    Parallel(n_jobs=args.workers, verbose=10)(
        delayed(one)(
            job,
            ref,
            rep,
            mode,
            family,
            cal,
            output,
            args.draws,
            args.resume,
            args.reanalyze,
            args.scenario,
        )
        for job, ref, rep, mode, family, cal in todo
    )
    summarize(output)
    print(
        f"Completed {len(todo)} station repetitions in {time.monotonic() - start:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
