#!/usr/bin/env python3
"""Replay original source-role classical calibration at larger bridge budgets.

All work is exploratory and saved in a new experiment directory. Source-role
assignments, bootstrap multiplicities, masks, daily reconstruction and AR(1)
residual inputs remain fixed. Native historical 20-path generation is audited
separately from the first 20 paths of a nested 500-path generation. D2 is never
refit. Larger-budget endpoint checks are not proofs of infinite-draw convergence.
"""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import hashlib
import importlib.metadata
import platform
import sys
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels, usable_donors, linear_interp_fill
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.tr_revision.baselines import ar1_bridge
from stream_recoverability.experiments.tr_revision.archive import apply_observed_lower_bound, marginal_draws
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps
from stream_recoverability.seeds import plain_seed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_experiments_20261029/source_calibration"
SOURCE = ROOT / "results/wrr_review_completion_20261024"
ARCHIVE = ROOT / "results/wrr_review_response_20261027/whole_archive"
TARGET_FROZEN = ROOT / "results/wrr_process_revision_20261029"
SOURCE_CASES = SOURCE / "cases/before_2010/seed_00.parquet"
SOURCE_REPAIR = SOURCE / "repairs/before_2010/seed_00.parquet"
OLD_CALIBRATION = ARCHIVE / "classical_calibration.json"
KEYS = ["network_id", "station_key", "year", "design_family", "realization_id", "policy_choice", "mask_runs"]
LEVELS = np.array([.05, .10, .25, .50, .75, .90, .95])
COUNTS = (20, 100, 500)
SEEDS = (0, 1, 2)
REGIONS = ("foen", "gkd_bayern")
DAILY_CODE_FILES = (
    "scripts/968_process_source_calibration.py", "scripts/431_tr_cases.py",
    "scripts/351_wrr_representative_recovery.py", "scripts/wrr_tr_common.py", "scripts/wrr_r3_common.py",
    "src/stream_recoverability/experiments/development_recovery.py",
    "src/stream_recoverability/experiments/v17_fitness/estimators.py",
    "src/stream_recoverability/experiments/v17_fitness/paths.py",
    "src/stream_recoverability/experiments/v19_revision/data.py",
    "src/stream_recoverability/experiments/tr_revision/baselines.py", "src/stream_recoverability/seeds.py",
)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def path_label(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()



def daily_reconstruction_versions():
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "system": platform.system(), "machine": platform.machine(), "byteorder": sys.byteorder,
            **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn", "pyarrow", "joblib")}}


def daily_reconstruction_shared_signature():
    """Bind all common daily-fit/sampler inputs, not just original case tables."""
    files = {"air_forcing": Path(T.AIR), "source_config": Path(T.CONFIG),
             "source_generation_settings": SOURCE / "cases/before_2010/generation_settings.json",
             "source_cases": SOURCE_CASES, "source_repair": SOURCE_REPAIR}
    code = {path: sha(ROOT / path) for path in DAILY_CODE_FILES}
    return {"schema": 1, "files": {name: {"path": path_label(path), "sha256": sha(path)} for name, path in files.items()},
            "code_sha256": code, "versions": daily_reconstruction_versions(),
            "loaded_configuration": getattr(T, "_CONFIG", {}), "season_mode": T.SEASON_MODE,
            "algorithm": {"training_split": "before_2010", "window_days": 30, "native_paths": 20,
                          "nested_paths": 500, "mc_seeds": list(SEEDS),
                          "bridge_seed_rule": "plain_seed(9, mc_seed, station_index, year, original_local_position)"}}


def daily_reconstruction_signature(job, shared):
    latitude = job.get("latitude")
    latitude = float(latitude) if latitude is not None and np.isfinite(latitude) else None
    identity = {name: str(job.get(name, "")) for name in
                ("station_key", "station_id", "network_id", "provider", "region", "independence_group", "roster")}
    identity.update(station_index=int(job["station_index"]), latitude=latitude,
                    hemisphere_shift_days=int(T.hemisphere_shift_days(latitude)),
                    input_panel=path_label(job["input_path"]), input_panel_sha256=sha(job["input_path"]),
                    declared_air_input=path_label(job["air_input_path"]) if job.get("air_input_path") else None)
    payload = {"schema": 1, "shared": shared, "job": identity}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return payload | {"sha256": hashlib.sha256(encoded).hexdigest()}


def signature_differences(a, b, prefix=""):
    if isinstance(a, dict) and isinstance(b, dict):
        paths = []
        for key in sorted(set(a) | set(b)):
            if key == "sha256" and not prefix:
                continue
            path = prefix + "." + key if prefix else key
            if key not in a or key not in b:
                paths.append(path)
            else:
                paths.extend(signature_differences(a[key], b[key], path))
        return paths
    return [] if a == b else [prefix]


def resume_station(job, cases, stage, shared):
    """Reject old/unbound caches; only a fresh reconstruction may write a signature."""
    folder = OUT / stage / "station_parts"
    stem = job["station_key"].replace("|", "_")
    metadata = folder / f"{stem}_metadata.json"
    check(metadata.exists(), "Resume station metadata is missing; rerun without --resume to rebuild")
    saved = json.loads(metadata.read_text())
    check(isinstance(saved.get("daily_reconstruction_signature"), dict),
          "Resume cache lacks a daily-reconstruction signature; rerun without --resume to rebuild. Existing caches are never backfilled with current signatures.")
    current = daily_reconstruction_signature(job, shared)
    old = saved["daily_reconstruction_signature"]
    changed = signature_differences(old, current)
    check(old == current, "Resume daily-reconstruction signature changed (" + ", ".join(changed[:8]) + "); rerun without --resume to rebuild")
    check(all((folder / f"{stem}_{kind}").is_file() for kind in ("draws.parquet", "manifest.csv", "native20_checks.csv")),
          "Resume station cache is incomplete; rerun without --resume to rebuild")
    cached = pd.read_parquet(folder / f"{stem}_draws.parquet", columns=["case_id", "seed"])
    check(set(cached.case_id) == set(cases.case_id) and len(cached) == len(cases) * len(SEEDS), "Resume source cache identity differs; rerun without --resume to rebuild")
    return saved


def digest_arrays(*values):
    h = hashlib.sha256()
    for value in values:
        value = np.ascontiguousarray(np.asarray(value, dtype="<f8"))
        h.update(str(value.shape).encode())
        h.update(value.tobytes())
    return h.hexdigest()


def case_id(row):
    return hashlib.sha256(json.dumps([str(row[k]) for k in KEYS], separators=(",", ":")).encode()).hexdigest()[:24]


def difficulty(c):
    overlap = c.peak_overlap.to_numpy(float)
    bins = np.where(overlap <= 0, 0, np.searchsorted([0, .25, .5, .75, 1], overlap, side="left"))
    layer = c.policy_choice.where(c.policy_choice.isin(["air_ridge", "donor_ridge"]), "other")
    return pd.Series([f"{bin_}|{kind}" for bin_, kind in zip(bins, layer)], index=c.index)


def load_source():
    """Apply the documented historical repair, leaving all source files intact."""
    c = pd.read_parquet(SOURCE_CASES)
    check(not c.duplicated(KEYS).any(), "Original source identity is not unique")
    # This is the row position used by the original bridge-repair replay.
    c["local_position"] = c.groupby(["network_id", "station_key", "year", "replication_seed"], sort=False).cumcount()
    repair = pd.read_parquet(SOURCE_REPAIR).set_index(KEYS)
    positions = repair.index.get_indexer(pd.MultiIndex.from_frame(c[KEYS]))
    present = positions >= 0
    for column in ["h30__stochastic_regression", "stochastic_h30_draws"] + [f"stochastic_h30_q{int(q*100):02d}" for q in LEVELS]:
        if column in repair:
            c.loc[present, column] = repair.iloc[positions[present]][column].to_numpy()
    c = c.loc[c.policy_choice.ne("unavailable") & c.eval_truth_h30.notna()].reset_index(drop=True)
    c["difficulty"] = difficulty(c)
    c["case_id"] = [case_id(row) for _, row in c.iterrows()]
    return c


def offsets(cases, quantiles, weights, cells):
    """Original case-count fallback, group multiplicity and empirical endpoints."""
    q = apply_observed_lower_bound(quantiles, cases.observed_lower_bound__observed_days.to_numpy(float))
    valid = np.isfinite(q).all(axis=1)
    positive = np.asarray(weights) > 0
    result, counts = {}, []
    for cell in ["__pooled__", *cells]:
        in_cell = positive & valid & cases.difficulty.eq(cell).to_numpy()
        local = cell != "__pooled__" and int(in_cell.sum()) >= 50
        pool = in_cell if local else positive & valid
        check(pool.sum() >= 2, "Insufficient original calibration-role data")
        residual = np.repeat(cases.eval_truth_h30.to_numpy(float)[pool, None] - q[pool], np.asarray(weights)[pool].astype(int), axis=0)
        result[cell] = [float(np.quantile(residual[:, j], level, method="higher" if level >= .5 else "lower")) for j, level in enumerate(LEVELS)]
        counts.append(dict(cell=cell, positive_valid_cell_cases=int(in_cell.sum()), selected_pool_cases=int(pool.sum()),
                           weighted_pool_rows=len(residual), fallback=not local))
    return result, counts


def load_targets():
    frozen = pd.read_csv(TARGET_FROZEN / "trajectory_revision_frozen_manifest.csv", float_precision="round_trip")
    rows = []
    for station, cases in frozen.groupby("station_key", sort=False):
        folder = ARCHIVE / "crossed/forward/replicate_00" / station.replace("|", "_")
        original = pd.read_parquet(folder / "annual_predictions.parquet").set_index("year")
        for row in cases.itertuples(index=False):
            r = original.loc[row.year]
            record = row._asdict() | {"peak_overlap": float(r.peak_overlap), "policy_choice": str(r.policy_choice),
                                     "original_mask_runs": str(r.mask_runs),
                                     "historical_native_draws": json.dumps(np.asarray(r.stochastic_h30_draws, float).tolist())}
            check(str(r.mask_runs) == row.mask_runs and str(r.policy_choice) == row.reconstructor,
                  "Frozen target mask or daily policy differs from original")
            for prefix in ("D2", "stochastic_cal"):
                for level in LEVELS:
                    col = f"{prefix}_q{int(level*100):02d}"
                    record[col] = float(r[col])
            for level in LEVELS:
                col = f"stochastic_h30_q{int(level*100):02d}"
                record[col] = float(r[col])
            rows.append(record)
    targets = pd.DataFrame(rows)
    targets["difficulty"] = difficulty(targets)
    check(len(targets) == 27 and targets.independence_group.nunique() == 2, "Target case set changed")
    return targets


def calibrated(q, bounds, cells, corrections):
    q = apply_observed_lower_bound(q, bounds)
    adjustment = np.asarray([corrections.get(cell, corrections["__pooled__"]) for cell in cells])
    return apply_observed_lower_bound(np.sort(q + adjustment, axis=1), bounds)


def plan():
    OUT.mkdir(parents=True, exist_ok=True)
    source = load_source()
    targets = load_targets()
    refit = T.load_script("sensitivity_original_roles", ROOT / "scripts/466_review_completion_refit.py")
    saved = json.loads(OLD_CALIBRATION.read_text())["forward"]
    cells = sorted(source.difficulty.unique())
    reports, selected, fallbacks = {}, [], []
    for region in REGIONS:
        seed = plain_seed(7, 0, sorted(set(source.region) | {region}).index(region))
        held, groups, weights = refit.roles(source, region, seed)
        bundle = joblib.load(SOURCE / "refits/before_2010/seed_00" / f"{region}.joblib")
        role_json = json.loads((SOURCE / "refits/before_2010/seed_00" / f"{region}.json").read_text())
        check(groups == bundle["roles"] == role_json["roles"], "Original role assignment differs from saved D2 model")
        w = weights["interval_calibration"]
        pick = w > 0
        local = source.loc[pick].copy()
        local["calibration_region"] = region
        local["calibration_weight"] = w[pick].astype(int)
        check(local.year.lt(2010).all() and local.training_partition.eq("train").all(), "Calibration includes post-cutoff or test cases")
        held_groups = set(targets.loc[targets.region.eq(region), "independence_group"])
        check(not held_groups & set(local.independence_group), "Target and source calibration groups overlap")
        check(set(local.independence_group).issubset(set(groups["interval_calibration"])), "Positive case outside original interval-calibration role")
        q = source[[f"stochastic_h30_q{int(q*100):02d}" for q in LEVELS]].to_numpy(float)
        recreated, counts = offsets(source, q, w, cells)
        old = saved[region]["offsets"]["stochastic"]
        check(set(recreated) == set(old), "Historical source calibration cells differ")
        max_error = max(float(np.max(abs(np.asarray(recreated[cell]) - old[cell]))) for cell in recreated)
        check(max_error < 1e-10, "Historical offsets do not reproduce")
        target = targets.loc[targets.region.eq(region)]
        target_q = target[[f"stochastic_h30_q{int(q*100):02d}" for q in LEVELS]].to_numpy(float)
        original_calibrated = target[[f"stochastic_cal_q{int(q*100):02d}" for q in LEVELS]].to_numpy(float)
        qcal = calibrated(target_q, target.bound.to_numpy(float), target.difficulty, old)
        target_error = float(np.max(abs(qcal - original_calibrated)))
        check(target_error < 1e-10, "Original target calibrated quantiles do not reproduce")
        for count in counts:
            fallbacks.append(dict(calibration_region=region, **count))
        reports[region] = dict(role_seed=int(seed), assigned_role_groups=groups,
                               calibration_group_multiplicities=local.groupby("independence_group").calibration_weight.first().to_dict(),
                               positive_cases=len(local), effective_weight=int(local.calibration_weight.sum()),
                               stations=local.station_key.nunique(), groups=local.independence_group.nunique(),
                               first_year=int(local.year.min()), last_year=int(local.year.max()),
                               target_groups=sorted(held_groups), source_target_groups_disjoint=True,
                               historical_offset_max_abs_error=max_error, historical_target_calibrated_max_abs_error=target_error)
        selected.append(local)
    role_cases = pd.concat(selected, ignore_index=True)
    union = role_cases.drop_duplicates(KEYS).sort_values(["station_key", "year", "local_position"]).reset_index(drop=True)
    role_cases[["calibration_region", "calibration_weight", "case_id", *KEYS, "independence_group", "region", "training_partition", "local_position", "difficulty"]].to_csv(OUT / "source_role_cases.csv", index=False)
    union.to_parquet(OUT / "source_union_cases.parquet", index=False)
    targets.to_csv(OUT / "fixed_target_cases.csv", index=False)
    pd.DataFrame(fallbacks).to_csv(OUT / "historical_source_fallbacks.csv", index=False)
    paths = [SOURCE_CASES, SOURCE_REPAIR, OLD_CALIBRATION, TARGET_FROZEN / "trajectory_revision_frozen_manifest.csv"]
    paths += [SOURCE / "refits/before_2010/seed_00" / f"{region}.{extension}" for region in REGIONS for extension in ("json", "joblib")]
    report = dict(status="planned_and_historical_calibration_reproduced", exploratory=True,
                  hash_scope="Hashes collected for this new experiment; no earlier receipt or provenance timestamp is rewritten.",
                  input_sha256={path_label(path): sha(path) for path in paths},
                  source_roles=reports, union_source_cases=len(union), union_source_stations=union.station_key.nunique(),
                  union_source_station_years=len(union[["station_key", "year"]].drop_duplicates()),
                  targets=27, target_stations=6, target_groups=2, nested_seeds=list(SEEDS), nested_counts=list(COUNTS),
                  native_vs_nested="Native20 is regenerated with draws=20 to reproduce historical repaired source draws. Nested20 is a prefix of a draws=500 call and need not match native20 because random arrays are generated per day.",
                  three_layers=["uncalibrated", "fixed_old_offset", "reestimated_source_offset"],
                  calibration_order="source seven raw quantiles -> observed-bound projection -> weighted source-role residual quantiles -> add offsets to projected target quantiles -> sort -> observed-bound projection -> common normal-spacing 256 annual samples with bound projection",
                  fallback="Per cell use >=50 finite positive-weight source cases, counted before multiplicity; otherwise all finite positive-weight source cases. Group bootstrap multiplicities unchanged.",
                  native_checks_required="Native20 source draws and quantiles must reproduce repaired historical values before nested sensitivity is accepted. Original calibration offsets and original target calibrated quantities are already checked.",
                  source_daily_inputs="Reconstitute once from the original pre-2010 held-year daily split and saved original source masks; native20 reproduction audits the daily means/residual histories, then freeze arrays across all budgets/seeds.",
                  d2="Original 27 target D2 quantiles remain fixed; no D2 weights, features or offsets are refit.",
                  limits=["Only the original six stations / two connected target groups", "500 paths do not prove infinite-draw convergence", "No target residual or target truth determines a calibration offset", "Named regions, daily reconstructor and target group remain confounded", "Full-archive trend ranking is outside this same-target annual diagnostic"])
    (OUT / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    return union, reports


def reconstruct_station(job, cases, stage, shared_signature=None):
    """Exact saved-mask/native-seed reconstruction, using the original repair path."""
    shared_signature = shared_signature if shared_signature is not None else daily_reconstruction_shared_signature()
    check(daily_reconstruction_shared_signature() == shared_signature, "Daily reconstruction dependencies changed before fitting; rebuild without --resume")
    reconstruction_signature = daily_reconstruction_signature(job, shared_signature)
    destination = OUT / stage / "station_parts"
    destination.mkdir(parents=True, exist_ok=True)
    metadata_path = destination / f"{job['station_key'].replace('|', '_')}_metadata.json"
    # An interrupted explicit rebuild must not leave an old success stamp over
    # partially regenerated arrays. Never create/upgrade this stamp on resume.
    metadata_path.unlink(missing_ok=True)
    core = T.load_script("sensitivity_source_daily", ROOT / "scripts/431_tr_cases.py")
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    real_index = panel.index
    shift = T.hemisphere_shift_days(job.get("latitude"))
    if shift:
        panel.index += pd.Timedelta(days=shift)
    target, donors = panel[job["station_id"]], panel.drop(columns=job["station_id"])
    years = core.CORE.complete_years(target)
    air = station_air_series(T.AIR, job["network_id"], job["station_id"], real_index)
    if air is not None:
        air.index = target.index
    arrays, draw_records, manifests, checks = {}, [], [], []
    for year, block in cases.groupby("year", sort=True):
        held = target.index.year == year
        allowed = pd.Series(~held & (target.index.year < 2010), index=target.index)
        train_years = [y for y in years if y != year and allowed.loc[target.index.year == y].any()]
        check(all(y < 2010 and y != year for y in train_years), "Invalid source daily training years")
        index, truth = target.index[held], target.loc[held].to_numpy(float)
        model = StationModels(target, donors, air, allowed)
        residual_cache, means, observed_rows, residual_indices = {}, [], [], []
        case_rows = []
        for row in block.itertuples(index=False):
            mask = T.mask_from_runs(row.mask_runs, len(index))
            observed = truth.copy()
            observed[mask] = np.nan
            visible = usable_donors(donors, index, mask)
            choice = row.policy_choice
            if choice == "air_ridge":
                mean = model.air_predict(index)
            elif choice == "donor_ridge":
                fit = model.donor_ridge(visible)
                mean = model.donor_predict(fit, index) if fit is not None else np.full(len(index), np.nan)
            elif choice == "linear_interp":
                mean = linear_interp_fill(observed)
            elif choice == "doy_climatology":
                mean = model.doy_climatology(index)
            else:
                mean = model.smooth_climatology(index)
            missing_doy = tuple(index.dayofyear.to_numpy()[mask]) if choice == "linear_interp" else ()
            key = (choice, tuple(visible) if choice == "donor_ridge" else (), missing_doy)
            if key not in residual_cache:
                residual_cache[key] = core.CORE.residual_history(target, donors, air, allowed, train_years, choice, tuple(visible), missing_doy)
            residual = residual_cache[key]
            native_seed = plain_seed(9, 0, job["station_index"], int(year), int(row.local_position))
            native = T.window_means(ar1_bridge(observed, mean, residual, native_seed, 20), 30).max(axis=1)
            original = np.asarray(row.stochastic_h30_draws, float)
            check(np.isfinite(native).all() == np.isfinite(original).all(), "Native20 availability differs from historical source repair")
            delta = float(np.max(abs(native - original))) if np.isfinite(native).all() else np.nan
            check(not np.isfinite(native).all() or delta < 1e-8, f"Native20 does not reproduce source repaired draws: {row.station_key}/{year}/{row.local_position}; delta={delta}")
            input_hash = digest_arrays(observed, mean, residual)
            checks.append(dict(case_id=row.case_id, station_key=row.station_key, year=int(year), local_position=int(row.local_position),
                               native20_max_abs_draw_error=delta, finite=bool(np.isfinite(native).all()),
                               comparison_status="matched_finite" if np.isfinite(native).all() else "matched_unavailable",
                               finite_residual_days=int(np.isfinite(residual).sum()), input_sha256=input_hash))
            position = len(observed_rows)
            residual_position = list(residual_cache).index(key)
            observed_rows.append(observed)
            means.append(mean)
            residual_indices.append(residual_position)
            case_rows.append(row)
            for seed in SEEDS:
                seed_value = plain_seed(9, seed, job["station_index"], int(year), int(row.local_position))
                nested = T.window_means(ar1_bridge(observed, mean, residual, seed_value, 500), 30).max(axis=1)
                draw_records.append(dict(case_id=row.case_id, station_key=row.station_key, year=int(year), seed=seed,
                                         bridge_seed=int(seed_value), draws=nested.tolist(), native20=native.tolist() if seed == 0 else None))
        arrays = {"observed": np.vstack(observed_rows), "mean": np.vstack(means), "residual_index": np.asarray(residual_indices)}
        arrays.update({f"residual_{i}": value for i, value in enumerate(residual_cache.values())})
        folder = OUT / stage / "source_frozen_inputs"
        folder.mkdir(parents=True, exist_ok=True)
        filename = folder / f"{job['station_key'].replace('|', '_')}_{year}.npz"
        np.savez_compressed(filename, **arrays)
        for position, row in enumerate(case_rows):
            manifests.append(dict(case_id=row.case_id, station_key=row.station_key, year=int(year), case_position=position,
                                  residual_index=int(residual_indices[position]), input_file=str(filename.relative_to(OUT)),
                                  training_years=";".join(map(str, train_years)), station_index=int(job["station_index"])))
    destination = OUT / stage / "station_parts"
    destination.mkdir(parents=True, exist_ok=True)
    stem = job["station_key"].replace("|", "_")
    pd.DataFrame(draw_records).to_parquet(destination / f"{stem}_draws.parquet", index=False)
    pd.DataFrame(manifests).to_csv(destination / f"{stem}_manifest.csv", index=False)
    pd.DataFrame(checks).to_csv(destination / f"{stem}_native20_checks.csv", index=False)
    ending_shared_signature = daily_reconstruction_shared_signature()
    check(ending_shared_signature == shared_signature and daily_reconstruction_signature(job, ending_shared_signature) == reconstruction_signature,
          "Daily reconstruction inputs changed during fitting; cache has no success signature, rerun without --resume")
    metadata = dict(station_key=job["station_key"], cases=len(cases), station_years=cases.year.nunique(),
                    native20_max_abs_draw_error=max(row["native20_max_abs_draw_error"] for row in checks),
                    input_panel=path_label(job["input_path"]), input_panel_sha256=sha(job["input_path"]),
                    station_index=int(job["station_index"]),
                    source_cases_sha256=sha(SOURCE_CASES), source_repair_sha256=sha(SOURCE_REPAIR),
                    daily_reconstruction_signature=reconstruction_signature)
    (destination / f"{stem}_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def metric_row(q, truth, bound):
    q = np.asarray(q, float)
    low, median, high = q[0], q[3], q[-1]
    annual = marginal_draws(q[None, :], draws=256, tails="normal", lower_bounds=np.array([bound]))[:, 0]
    return {**{f"q{int(level * 100):02d}": float(q[j]) for j, level in enumerate(LEVELS)},
            "truth": float(truth), "bound": float(bound), "bias": float(median - truth),
            "mae": float(abs(median - truth)), "width90": float(high - low),
            "covered90": int(low - 1e-8 <= truth <= high + 1e-8),
            "crps256_normal": float(sample_crps(annual, truth)),
            "interval_score90": float(high - low + 20 * max(low - truth, 0) + 20 * max(truth - high, 0))}


def target_draws(targets):
    rows, checks = [], []
    for case in targets.itertuples(index=False):
        with np.load(TARGET_FROZEN / case.input_file) as data:
            observed, mean, residual = [data[key] for key in ("observed", "mean", "residual")]
            check(digest_arrays(observed, mean, residual) == case.input_sha256, "Frozen target inputs changed")
            native_seed = plain_seed(9, 0, case.station_index, case.year, 0)
            native = T.window_means(ar1_bridge(observed, mean, residual, native_seed, 20), 30).max(axis=1)
            original = np.array([getattr(case, f"stochastic_h30_q{int(level*100):02d}") for level in LEVELS])
            original_draws = np.asarray(json.loads(case.historical_native_draws), float)
            check(np.isfinite(native).all() and np.isfinite(original_draws).all(), "Native target draws must remain finite")
            draw_delta = float(np.max(abs(native - original_draws)))
            check(draw_delta < 1e-8, "Native target draws do not reproduce original archive")
            delta = float(np.max(abs(np.quantile(native, LEVELS) - original)))
            check(delta < 1e-8, "Native target 20-path quantiles do not reproduce original archive")
            checks.append(dict(station_key=case.station_key, year=case.year, native20_max_abs_quantile_error=delta, native20_max_abs_draw_error=draw_delta, input_sha256=case.input_sha256))
            for seed in SEEDS:
                bridge_seed = plain_seed(9, seed, case.station_index, case.year, 0)
                nested = T.window_means(ar1_bridge(observed, mean, residual, bridge_seed, 500), 30).max(axis=1)
                rows.append(dict(station_key=case.station_key, year=case.year, seed=seed, bridge_seed=int(bridge_seed),
                                 input_sha256=case.input_sha256, draws=nested.tolist()))
    pd.DataFrame(checks).to_csv(OUT / "full/target_native20_checks.csv", index=False)
    result = pd.DataFrame(rows)
    result.to_parquet(OUT / "full/target_nested_draws.parquet", index=False)
    return result


def analyse_full(union):
    """Source-only offset updates and three distinct same-target score layers."""
    folder = OUT / "full"
    pieces = [pd.read_parquet(path) for path in sorted((folder / "station_parts").glob("*_draws.parquet"))]
    samples = pd.concat(pieces, ignore_index=True)
    check(len(samples) == len(union) * len(SEEDS) and not samples.duplicated(["case_id", "seed"]).any(), "Full source draw collection is incomplete")
    native_saved = samples.loc[samples.seed.eq(0)].set_index("case_id").reindex(union.case_id)
    for regenerated, expected in zip(native_saved.native20, union.stochastic_h30_draws):
        check(np.array_equal(np.asarray(regenerated, float), np.asarray(expected, float), equal_nan=True), "Cached source native20 differs from current historical source")
    samples.to_parquet(folder / "source_nested_draws.parquet", index=False)
    manifests = pd.concat([pd.read_csv(path) for path in sorted((folder / "station_parts").glob("*_manifest.csv"))], ignore_index=True)
    native_checks = pd.concat([pd.read_csv(path) for path in sorted((folder / "station_parts").glob("*_native20_checks.csv"))], ignore_index=True)
    check(set(manifests.case_id) == set(union.case_id) == set(native_checks.case_id), "Full frozen source cases differ")
    manifests = manifests.merge(native_checks[["case_id", "input_sha256"]], on="case_id", validate="one_to_one")
    manifests.to_csv(folder / "source_frozen_manifest.csv", index=False)
    historical_quantiles = union[[f"stochastic_h30_q{int(level*100):02d}" for level in LEVELS]].to_numpy(float)
    regenerated_native_quantiles = np.quantile(np.stack(native_saved.native20.to_numpy()), LEVELS, axis=1).T
    native_valid = np.isfinite(historical_quantiles).all(axis=1)
    check(np.array_equal(np.isfinite(regenerated_native_quantiles).all(axis=1), native_valid), "Native20 source quantile availability differs")
    quantile_errors = np.full(len(union), np.nan)
    quantile_errors[native_valid] = abs(regenerated_native_quantiles[native_valid] - historical_quantiles[native_valid]).max(axis=1)
    check((quantile_errors[native_valid] < 1e-8).all(), "Native20 source quantiles differ from historical repair")
    error_by_id = pd.Series(quantile_errors, index=union.case_id)
    native_checks["native20_max_abs_quantile_error"] = native_checks.case_id.map(error_by_id)
    native_checks.to_csv(folder / "source_native20_checks.csv", index=False)
    role_cases = pd.read_csv(OUT / "source_role_cases.csv")
    old = json.loads(OLD_CALIBRATION.read_text())["forward"]
    # Every historical difficulty cell is kept, including empty cells whose
    # original fallback is the global positive-weight calibration pool.
    all_cells = sorted(key for key in old[REGIONS[0]]["offsets"]["stochastic"] if key != "__pooled__")
    offsets_by_key, offset_rows, raw_source_rows, availability_rows = {}, [], [], []
    indexed_union = union.set_index("case_id")
    for seed in SEEDS:
        local_samples = samples.loc[samples.seed.eq(seed)].set_index("case_id").reindex(union.case_id)
        values = np.stack(local_samples.draws.to_numpy())
        expected_available = np.isfinite(np.stack(union.stochastic_h30_draws.to_numpy())).all(axis=1)
        check(np.array_equal(np.isfinite(values).all(axis=1), expected_available), "Source availability changed under nested regeneration")
        for case, expected, actual in zip(union.itertuples(index=False), expected_available, np.isfinite(values).all(axis=1)):
            availability_rows.append(dict(case_id=case.case_id, station_key=case.station_key, year=case.year, seed=seed,
                                          original_native20_available=bool(expected), nested500_available=bool(actual),
                                          availability_unchanged=bool(expected == actual)))
        for count in COUNTS:
            q = np.quantile(values[:, :count], LEVELS, axis=1).T
            for i, case in enumerate(union.itertuples(index=False)):
                raw_source_rows.append(dict(case_id=case.case_id, seed=seed, count=count,
                                            **{f"q{int(level*100):02d}": float(q[i, j]) for j, level in enumerate(LEVELS)}))
            q_frame = pd.DataFrame(q, index=union.case_id)
            for region in REGIONS:
                role = role_cases.loc[role_cases.calibration_region.eq(region)].set_index("case_id")
                cases = indexed_union.loc[role.index]
                qs = q_frame.loc[role.index].to_numpy(float)
                correction, fallback_rows = offsets(cases, qs, role.calibration_weight.to_numpy(float), all_cells)
                offsets_by_key[region, seed, count] = correction
                for fallback in fallback_rows:
                    cell = fallback["cell"]
                    offset_rows.append(dict(region=region, seed=seed, count=count, **fallback,
                                            **{f"offset{int(level*100):02d}": float(correction[cell][j]) for j, level in enumerate(LEVELS)},
                                            **{f"change_vs_native{int(level*100):02d}": float(correction[cell][j] - old[region]["offsets"]["stochastic"][cell][j]) for j, level in enumerate(LEVELS)}))
    availability = pd.DataFrame(availability_rows)
    availability.to_csv(folder / "source_pool_availability.csv", index=False)
    availability.loc[~availability.original_native20_available | ~availability.nested500_available].to_csv(folder / "source_unavailable_cases.csv", index=False)
    pd.DataFrame(raw_source_rows).to_csv(folder / "source_nested_quantiles.csv", index=False)
    pd.DataFrame(offset_rows).to_csv(folder / "source_reestimated_offsets.csv", index=False)
    targets = load_targets()
    nested = target_draws(targets)
    baseline, scored = [], []
    for case in targets.itertuples(index=False):
        common = dict(station_key=case.station_key, year=case.year, region=case.region, reconstructor=case.reconstructor,
                      independence_group=case.independence_group, difficulty=case.difficulty, input_sha256=case.input_sha256)
        for method, prefix in [("historical_native20", "stochastic_cal"), ("fixed_D2", "D2")]:
            q = np.array([getattr(case, f"{prefix}_q{int(level*100):02d}") for level in LEVELS])
            baseline.append(common | dict(method=method) | metric_row(q, case.truth, case.bound))
        for seed in SEEDS:
            values = np.asarray(nested.loc[nested.station_key.eq(case.station_key) & nested.year.eq(case.year) & nested.seed.eq(seed), "draws"].iloc[0], float)
            for count in COUNTS:
                raw_q = np.quantile(values[:count], LEVELS)[None, :]
                projected = apply_observed_lower_bound(raw_q, np.array([case.bound]))[0]
                fixed = calibrated(raw_q, np.array([case.bound]), [case.difficulty], old[case.region]["offsets"]["stochastic"])[0]
                updated = calibrated(raw_q, np.array([case.bound]), [case.difficulty], offsets_by_key[case.region, seed, count])[0]
                for layer, q in [("uncalibrated", projected), ("fixed_old_offset", fixed), ("reestimated_source_offset", updated)]:
                    scored.append(common | dict(seed=seed, count=count, layer=layer) | metric_row(q, case.truth, case.bound))
    baseline = pd.DataFrame(baseline)
    scored = pd.DataFrame(scored)
    check(len(scored) == 27 * len(SEEDS) * len(COUNTS) * 3, "Target three-layer pairing incomplete")
    historical = baseline.loc[baseline.method.eq("historical_native20")].set_index(["station_key", "year"])
    d2 = baseline.loc[baseline.method.eq("fixed_D2")].set_index(["station_key", "year"])
    for metric in ["q05", "q50", "q95", "mae", "covered90", "width90", "crps256_normal"]:
        key = pd.MultiIndex.from_frame(scored[["station_key", "year"]])
        scored[f"delta_{metric}_vs_native20"] = scored[metric].to_numpy() - historical[metric].reindex(key).to_numpy()
        scored[f"delta_{metric}_vs_D2"] = scored[metric].to_numpy() - d2[metric].reindex(key).to_numpy()
    baseline.to_csv(folder / "target_historical_reference.csv", index=False)
    scored.to_csv(folder / "target_three_layer_cases.csv", index=False)
    summaries = []
    for keys, block in scored.groupby(["seed", "count", "layer", "region", "reconstructor"]):
        row = dict(zip(["seed", "count", "layer", "region", "reconstructor"], keys))
        row.update(n=len(block), stations=block.station_key.nunique(), groups=block.independence_group.nunique(),
                   n_covered=int(block.covered90.sum()), coverage90=float(block.covered90.mean()),
                   mae=float(block.mae.mean()), bias=float(block.bias.mean()), width90=float(block.width90.mean()),
                   crps256_normal=float(block.crps256_normal.mean()),
                   mean_mae_minus_D2=float(block.delta_mae_vs_D2.mean()),
                   mean_crps_minus_D2=float(block.delta_crps256_normal_vs_D2.mean()),
                   n_lower_crps_than_D2=int(block.delta_crps256_normal_vs_D2.lt(0).sum()),
                   n_q95_shift_gt005_vs_native=int(block.delta_q95_vs_native20.abs().gt(.05).sum()),
                   median_abs_q95_shift_vs_native=float(block.delta_q95_vs_native20.abs().median()))
        summaries.append(row)
    pd.DataFrame(summaries).to_csv(folder / "target_three_layer_summary.csv", index=False)
    # Pair budgets within one random stream and one calibration layer.
    keys = ["seed", "layer", "station_key", "year", "region", "reconstructor", "independence_group"]
    a = scored.loc[scored["count"].eq(20)].set_index(keys)
    delta_rows = []
    for count in (100, 500):
        b = scored.loc[scored["count"].eq(count)].set_index(keys)
        pair = a[["q05", "q50", "q95", "width90", "covered90", "crps256_normal"]].join(b[["q05", "q50", "q95", "width90", "covered90", "crps256_normal"]], lsuffix="_20", rsuffix="_other", validate="one_to_one").reset_index()
        pair["comparison"] = f"nested20_to_{count}"
        for tail in ("q05", "q50", "q95"):
            pair[f"delta_{tail}"] = pair[f"{tail}_other"] - pair[f"{tail}_20"]
            pair[f"abs_delta_{tail}"] = pair[f"delta_{tail}"].abs()
        pair["either_tail_gt005"] = pair.abs_delta_q05.gt(.05) | pair.abs_delta_q95.gt(.05)
        delta_rows.append(pair)
    deltas = pd.concat(delta_rows, ignore_index=True)
    deltas.to_csv(folder / "target_budget_case_deltas.csv", index=False)
    tail_rows = []
    for keys, block in deltas.groupby(["seed", "layer", "comparison", "region", "reconstructor"]):
        row = dict(zip(["seed", "layer", "comparison", "region", "reconstructor"], keys))
        row.update(n=len(block), n_either_tail_gt005=int(block.either_tail_gt005.sum()),
                   n_covered20=int(block.covered90_20.sum()), n_covered_other=int(block.covered90_other.sum()),
                   mean_width20=float(block.width90_20.mean()), mean_width_other=float(block.width90_other.mean()))
        for tail in ("q05", "q50", "q95"):
            row[f"median_abs_delta_{tail}"] = float(block[f"abs_delta_{tail}"].median())
            row[f"max_abs_delta_{tail}"] = float(block[f"abs_delta_{tail}"].max())
            row[f"n_{tail}_gt005"] = int(block[f"abs_delta_{tail}"].gt(.05).sum())
        tail_rows.append(row)
    pd.DataFrame(tail_rows).to_csv(folder / "target_budget_tail_summary.csv", index=False)
    # Offset updates are compared at identical target random samples, so this
    # stage contrast isolates the actual calibration change without inventing
    # orthogonal or causal variance components.
    keys = ["seed", "count", "station_key", "year", "region", "reconstructor", "independence_group"]
    old_target = scored.loc[scored.layer.eq("fixed_old_offset")].set_index(keys)
    new_target = scored.loc[scored.layer.eq("reestimated_source_offset")].set_index(keys)
    contrasts = []
    for metric in ["q05", "q50", "q95", "mae", "width90", "covered90", "crps256_normal"]:
        delta = (new_target[metric] - old_target[metric]).rename("source_offset_change").reset_index()
        delta["metric"] = metric
        contrasts.append(delta)
    pd.concat(contrasts, ignore_index=True).to_csv(folder / "target_source_offset_stage_contrasts.csv", index=False)
    return dict(status="source_calibration_reestimated_and_same_targets_scored", complete_source_calibration_reestimated=True, target_calibrated_scores_generated=True,
                source_role_offsets_reestimated=True, source_calibration_targets_used=False,
                source_cases_regenerated=len(union), source_seeds=list(SEEDS), target_cases=27,
                target_native20_max_abs_quantile_error=float(pd.read_csv(folder / "target_native20_checks.csv").native20_max_abs_quantile_error.max()),
                target_native20_max_abs_draw_error=float(pd.read_csv(folder / "target_native20_checks.csv").native20_max_abs_draw_error.max()),
                original_positive_source_unavailable_cases=int((~availability.loc[availability.seed.eq(0)].original_native20_available).sum()),
                source_availability_unchanged_across_budgets_and_seeds=True,
                source_native20_max_abs_draw_error=float(native_checks.native20_max_abs_draw_error.max()),
                source_native20_max_abs_quantile_error=float(native_checks.native20_max_abs_quantile_error.max()),
                fixed_d2_reference=True, score_distribution="Common seven-quantile normal-spacing 256-point annual samples with observed bound; no trend scoring",
                convergence_established=False, broad_method_ranking_robustness_established=False)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["plan", "pilot", "full"], default="plan")
    parser.add_argument("--pilot-station", default="nve_hydapi|16.207.0")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    union, roles = plan()
    if args.stage == "plan":
        print(json.dumps(dict(stage="plan", cases=len(union), stations=union.station_key.nunique(), station_years=len(union[["station_key", "year"]].drop_duplicates()))), flush=True)
        return 0
    core = T.load_script("sensitivity_jobs", ROOT / "scripts/431_tr_cases.py")
    jobs = {job["station_key"]: job for job in core.jobs_for("source")}
    selected = union.loc[union.station_key.eq(args.pilot_station)] if args.stage == "pilot" else union
    check(len(selected) > 0, "No selected source cases")
    shared_signature = daily_reconstruction_shared_signature()
    records, pending = [], []
    for station, cases in selected.groupby("station_key", sort=True):
        if args.resume:
            records.append(resume_station(jobs[station], cases, args.stage, shared_signature))
        else:
            pending.append((jobs[station], cases, args.stage, shared_signature))
    if pending:
        records.extend(Parallel(n_jobs=args.workers, verbose=5)(delayed(reconstruct_station)(*arguments) for arguments in pending))
    check(daily_reconstruction_shared_signature() == shared_signature, "Shared inputs changed before analysis; rebuild without --resume")
    check(all(record.get("daily_reconstruction_signature", {}).get("shared") == shared_signature for record in records), "Station signatures disagree with this execution")
    report = dict(daily_reconstruction_shared_signature=shared_signature,
                  stage=args.stage, status="native20_source_reproduced_and_nested_draws_generated", stations=records,
                  source_cases=len(selected), elapsed_seconds=time.monotonic() - started,
                  source_stations_reconstructed_this_run=len(pending), source_stations_reused_this_run=len(records)-len(pending),
                  complete_source_calibration_reestimated=False, target_calibrated_scores_generated=False,
                  full_source_cases_required=len(union), d2_refit=False)
    if args.stage == "full":
        report.update(analyse_full(union))
    (OUT / args.stage / "daily_reconstruction_shared_signature.json").write_text(json.dumps(shared_signature, indent=2) + "\n")
    report["elapsed_seconds"] = time.monotonic() - started
    (OUT / args.stage / "execution.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.stage == "full" and len(pending) == len(records):
        (OUT / args.stage / "full_reconstruction_execution.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ["stage", "status", "source_cases", "elapsed_seconds", "complete_source_calibration_reestimated", "target_calibrated_scores_generated"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
