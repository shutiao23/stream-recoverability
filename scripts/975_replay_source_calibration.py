#!/usr/bin/env python3
"""Closed frozen-input replay of the source-calibration budget experiment.

Default execution never opens original daily panels, source case caches, model
joblibs, or 968. --freeze-inputs materializes a current-content snapshot once;
it does not backdate provenance or change earlier source receipts. Replays
frozen daily arrays, original role multiplicities and historical references,
then checks existing experiment results without overwriting them.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/wrr_process_experiments_20261029/source_calibration"
LEGACY_TARGET = ROOT / "results/wrr_process_revision_20261029"
OLD_CALIBRATION = ROOT / "results/wrr_review_response_20261027/whole_archive/classical_calibration.json"
LEVELS = np.array([.05, .10, .25, .50, .75, .90, .95])
SEEDS, BUDGETS = (0, 1, 2), (20, 100, 500)
QCOLS = [f"q{int(level * 100):02d}" for level in LEVELS]
ATOL = 1e-10
EXPECTED = ["full/source_nested_quantiles.csv", "full/source_reestimated_offsets.csv",
            "full/target_three_layer_cases.csv", "full/target_historical_reference.csv"]
SAMPLER = Path("src/stream_recoverability/experiments/tr_revision/baselines.py")
SEED_HELPER = Path("src/stream_recoverability/seeds.py")


class ReplayFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReplayFailure(message)


def compare(actual, expected, message, tolerance=ATOL):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    require(a.shape == b.shape, message + ": shape differs")
    require(np.array_equal(np.isfinite(a), np.isfinite(b)), message + ": availability differs")
    finite = np.isfinite(a) & np.isfinite(b)
    maximum = float(abs(a[finite] - b[finite]).max()) if finite.any() else None
    require(maximum is None or maximum <= tolerance, f"{message}: maximum absolute error {maximum}")
    return maximum


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def label(path):
    return str(Path(path).resolve().relative_to(ROOT))


def safe_data_path(relative):
    relative = Path(str(relative))
    require(not relative.is_absolute() and ".." not in relative.parts, "Frozen input path escapes data directory")
    return BASE / relative


def digest_arrays(*values):
    h = hashlib.sha256()
    for value in values:
        array = np.ascontiguousarray(np.asarray(value, dtype="<f8"))
        h.update(str(array.shape).encode())
        h.update(array.tobytes())
    return h.hexdigest()


def direct_module(path, name):
    # File-level import avoids experiments/__init__.py and its model-training
    # registry; these two modules themselves contain no fits or data access.
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_or_check(source, destination):
    if destination.exists():
        require(sha(source) == sha(destination), "Existing frozen copy differs: " + label(destination))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def freeze_inputs():
    """Materialize new snapshots; original results and receipts stay intact."""
    BASE.mkdir(parents=True, exist_ok=True)
    source_path = BASE / "source_union_cases.parquet"
    source = pd.read_parquet(source_path)
    columns = ["case_id", "network_id", "station_key", "year", "design_family", "realization_id", "policy_choice", "mask_runs",
               "region", "independence_group", "training_partition", "local_position", "difficulty", "eval_truth_h30",
               "observed_lower_bound__observed_days", "stochastic_h30_draws"]
    columns += [f"stochastic_h30_q{int(level*100):02d}" for level in LEVELS]
    source_reference = BASE / "frozen_source_reference.parquet"
    if source_reference.exists():
        prior = pd.read_parquet(source_reference)
        require(list(prior.columns) == columns and prior.case_id.tolist() == source.case_id.tolist(), "Frozen source-reference identity changed")
        # Existing frozen values may not be silently refreshed.
        for column in columns:
            if column == "stochastic_h30_draws":
                for a, b in zip(prior[column], source[column]):
                    compare(a, b, "Existing source reference native draws changed", tolerance=0)
            elif pd.api.types.is_numeric_dtype(prior[column]):
                compare(prior[column].to_numpy(), source[column].to_numpy(), "Existing source reference changed", tolerance=0)
            else:
                require(prior[column].tolist() == source[column].tolist(), "Existing source-reference field changed: " + column)
    else:
        source[columns].to_parquet(source_reference, index=False)
    target_path = BASE / "fixed_target_cases.csv"
    target = pd.read_csv(target_path, float_precision="round_trip")
    copies = []
    for position, row in target.iterrows():
        source_input = LEGACY_TARGET / row.input_file
        destination = BASE / "frozen_target_inputs" / Path(row.input_file).name
        copy_or_check(source_input, destination)
        target.loc[position, "input_file"] = str(destination.relative_to(BASE))
        copies.append(dict(copied_from=label(source_input), frozen_copy=label(destination), sha256=sha(destination)))
    target_manifest = BASE / "frozen_target_manifest.csv"
    if target_manifest.exists():
        pd.testing.assert_frame_equal(pd.read_csv(target_manifest, float_precision="round_trip"), target, check_exact=True)
    else:
        target.to_csv(target_manifest, index=False)
    original = json.loads(OLD_CALIBRATION.read_text())["forward"]
    plan = json.loads((BASE / "plan.json").read_text())
    snapshot = {
        "snapshot_scope": "Current-content freeze for the new replay only; not an earlier provenance receipt.",
        "copied_from": label(OLD_CALIBRATION), "copied_content_sha256": sha(OLD_CALIBRATION),
        "source_assignment_seed": 0, "probabilities": LEVELS.tolist(), "minimum_positive_cases_per_cell": 50,
        "historical_offsets": {region: original[region]["offsets"]["stochastic"] for region in ("foen", "gkd_bayern")},
        "roles": {region: {"assigned_interval_groups": plan["source_roles"][region]["assigned_role_groups"]["interval_calibration"],
                           "positive_group_multiplicities": plan["source_roles"][region]["calibration_group_multiplicities"],
                           "held_target_groups": plan["source_roles"][region]["target_groups"]}
                  for region in ("foen", "gkd_bayern")},
    }
    snapshot_path = BASE / "frozen_historical_calibration.json"
    if snapshot_path.exists():
        require(json.loads(snapshot_path.read_text()) == snapshot, "Existing historical content snapshot changed")
    else:
        snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    preparation = dict(scope="Current-content materialization for a closed frozen-input replay; these source locations are not default replay dependencies.",
                       materialization_only_inputs={label(path): sha(path) for path in [source_path, target_path, OLD_CALIBRATION, BASE / "plan.json"]},
                       target_copies=copies)
    preparation_path = BASE / "frozen_replay_preparation.json"
    if preparation_path.exists():
        require(json.loads(preparation_path.read_text()) == preparation, "Existing replay materialization record changed")
    else:
        preparation_path.write_text(json.dumps(preparation, indent=2) + "\n")


def dependency_paths(source_manifest, targets):
    paths = {Path(__file__).resolve(), ROOT / SAMPLER, ROOT / SEED_HELPER,
             BASE / "full/source_frozen_manifest.csv", BASE / "source_role_cases.csv", BASE / "frozen_source_reference.parquet",
             BASE / "frozen_target_manifest.csv", BASE / "frozen_historical_calibration.json"}
    paths.update(safe_data_path(value) for value in source_manifest.input_file.unique())
    paths.update(safe_data_path(value) for value in targets.input_file.unique())
    paths.update(BASE / name for name in EXPECTED)
    return sorted(paths)


def h30(paths):
    cumulative = np.concatenate([np.zeros(paths.shape[:-1] + (1,)), np.cumsum(paths, axis=-1)], axis=-1)
    return ((cumulative[..., 30:] - cumulative[..., :-30]) / 30).max(axis=-1)


def project(q, bounds):
    q = np.asarray(q, float)
    bounds = np.asarray(bounds, float)
    return np.where(np.isfinite(bounds[:, None]), np.maximum(q, bounds[:, None]), q)


def weighted_endpoint(values, weights, probability):
    order = np.argsort(values, kind="stable")
    values, weights = np.asarray(values)[order], np.asarray(weights, int)[order]
    total = int(weights.sum())
    rank = (total - 1) * float(probability)
    rank = math.ceil(rank) if probability >= .5 else math.floor(rank)
    return float(values[np.searchsorted(np.cumsum(weights), rank, side="right")])


def recalibrate(source, q, weights, cells):
    q = project(q, source.observed_lower_bound__observed_days.to_numpy(float))
    valid = np.isfinite(q).all(axis=1) & (weights > 0)
    result, pools = {}, {}
    for cell in cells:
        local = valid & source.difficulty.eq(cell).to_numpy()
        fallback = cell == "__pooled__" or int(local.sum()) < 50
        pool = valid if fallback else local
        require(pool.sum() >= 2, "Frozen source calibration pool is insufficient")
        residuals = source.eval_truth_h30.to_numpy(float)[pool, None] - q[pool]
        result[cell] = [weighted_endpoint(residuals[:, j], weights[pool], probability) for j, probability in enumerate(LEVELS)]
        pools[cell] = dict(positive_valid_cell_cases=int(local.sum()), selected_pool_cases=int(pool.sum()),
                           weighted_pool_rows=int(weights[pool].sum()), fallback=bool(fallback))
    return result, pools


def apply_offsets(q, bound, difficulty, correction):
    first = project(q[None, :], np.array([bound]))[0]
    offset = np.asarray(correction.get(difficulty, correction["__pooled__"]))
    return project(np.sort(first + offset)[None, :], np.array([bound]))[0]


def score(q, truth, bound):
    u = (np.arange(256) + .5) / 256
    samples = np.interp(u, LEVELS, q)
    z, zq = norm.ppf(u), norm.ppf(LEVELS)
    below, above = u < LEVELS[0], u > LEVELS[-1]
    samples[below] = q[0] + (q[1] - q[0]) / (zq[1] - zq[0]) * (z[below] - zq[0])
    samples[above] = q[-1] + (q[-1] - q[-2]) / (zq[-1] - zq[-2]) * (z[above] - zq[-1])
    if np.isfinite(bound):
        samples = np.maximum(samples, bound)
    ordered = np.sort(samples)
    crps = np.mean(abs(ordered - truth)) - np.sum((2 * np.arange(1, 257) - 257) * ordered) / 256 ** 2
    low, median, high = q[0], q[3], q[-1]
    return dict(zip(QCOLS, map(float, q))) | dict(truth=float(truth), bound=float(bound), bias=float(median-truth), mae=float(abs(median-truth)),
                width90=float(high-low), covered90=int(low-1e-8 <= truth <= high+1e-8), crps256_normal=float(crps),
                interval_score90=float(high-low+20*max(low-truth, 0)+20*max(truth-high, 0)))


def source_replay(source, manifest, sampler, seed_function):
    source = source.set_index("case_id")
    require(len(source) == len(manifest) == 2370 and not manifest.case_id.duplicated().any(), "Frozen source denominator differs")
    native_errors, quantile_rows, native_quantiles, streams = [], [], {}, set()
    for filename, part in manifest.groupby("input_file", sort=True):
        with np.load(safe_data_path(filename)) as arrays:
            for row in part.itertuples(index=False):
                case = source.loc[row.case_id]
                observed = arrays["observed"][int(row.case_position)]
                mean = arrays["mean"][int(row.case_position)]
                residual = arrays[f"residual_{int(row.residual_index)}"]
                require(digest_arrays(observed, mean, residual) == row.input_sha256, "Frozen source array identity changed")
                training_years = [int(value) for value in row.training_years.split(";")]
                require(all(year < 2010 and year != row.year for year in training_years), "Frozen source training split contains held/future years")
                native_seed = seed_function(9, 0, row.station_index, row.year, int(case.local_position))
                native = h30(sampler(observed, mean, residual, native_seed, 20))
                error = compare(native, np.asarray(case.stochastic_h30_draws), "Native source draws differ", tolerance=1e-8)
                native_q = np.quantile(native, LEVELS)
                q_error = compare(native_q, case[[f"stochastic_h30_q{int(p*100):02d}" for p in LEVELS]].to_numpy(float), "Native source quantiles differ", tolerance=1e-8)
                native_quantiles[row.case_id] = native_q
                native_errors.append(dict(case_id=row.case_id, available=bool(np.isfinite(native).all()), draw_error=error, quantile_error=q_error))
                for seed in SEEDS:
                    stream = seed_function(9, seed, row.station_index, row.year, int(case.local_position))
                    require(stream not in streams, "Source Monte Carlo stream is duplicated")
                    streams.add(stream)
                    generated = h30(sampler(observed, mean, residual, stream, 500))
                    require(np.isfinite(generated).all() == np.isfinite(native).all(), "Frozen source availability changes with budget/seed")
                    for count in BUDGETS:
                        quantile_rows.append(dict(case_id=row.case_id, seed=seed, count=count, **dict(zip(QCOLS, np.quantile(generated[:count], LEVELS)))))
    return pd.DataFrame(quantile_rows), native_quantiles, native_errors, streams


def replay():
    started = time.monotonic()
    source = pd.read_parquet(BASE / "frozen_source_reference.parquet")
    manifest = pd.read_csv(BASE / "full/source_frozen_manifest.csv", float_precision="round_trip")
    targets = pd.read_csv(BASE / "frozen_target_manifest.csv", float_precision="round_trip")
    roles = pd.read_csv(BASE / "source_role_cases.csv")
    historical = json.loads((BASE / "frozen_historical_calibration.json").read_text())
    paths = dependency_paths(manifest, targets)
    dependencies = {label(path): dict(sha256=sha(path), bytes=path.stat().st_size) for path in paths}
    sampler = direct_module(SAMPLER, "frozen_ar1_sampler").ar1_bridge
    seed_function = direct_module(SEED_HELPER, "frozen_integer_seed").plain_seed
    qsource, native_q, source_checks, source_streams = source_replay(source, manifest, sampler, seed_function)
    key = ["seed", "count", "case_id"]
    expected_q = pd.read_csv(BASE / "full/source_nested_quantiles.csv", float_precision="round_trip").set_index(key).sort_index()
    actual_q = qsource.set_index(key).sort_index()
    require(actual_q.index.equals(expected_q.index), "Frozen source budget/case identities differ")
    source_error = compare(actual_q[QCOLS], expected_q[QCOLS], "Source budget quantiles differ")
    indexed = source.set_index("case_id")
    corrections, offset_rows, original_offset_errors = {}, [], []
    for region, old in historical["historical_offsets"].items():
        role = roles.loc[roles.calibration_region.eq(region)].set_index("case_id")
        local = indexed.loc[role.index]
        weights = role.calibration_weight.to_numpy(int)
        require(local.year.lt(2010).all() and local.training_partition.eq("train").all(), "Source role includes held/future cases")
        group_counts = role.groupby("independence_group").calibration_weight.first().to_dict()
        require(group_counts == historical["roles"][region]["positive_group_multiplicities"], "Frozen source multiplicities changed")
        require(not set(local.independence_group) & set(targets.loc[targets.region.eq(region)].independence_group), "Frozen target and source calibration groups overlap")
        native_matrix = np.stack([native_q[case] for case in local.index])
        original, _ = recalibrate(local, native_matrix, weights, list(old))
        original_offset_errors.extend(compare(original[cell], old[cell], "Historical source offset replay differs") for cell in old)
        for seed in SEEDS:
            for count in BUDGETS:
                matrix = actual_q.loc[(seed, count)].reindex(local.index)[QCOLS].to_numpy(float)
                correction, pools = recalibrate(local, matrix, weights, list(old))
                corrections[region, seed, count] = correction
                for cell, values in correction.items():
                    offset_rows.append(dict(region=region, seed=seed, count=count, cell=cell, **pools[cell],
                                            **{f"offset{int(p*100):02d}": values[j] for j, p in enumerate(LEVELS)}))
    actual_offsets = pd.DataFrame(offset_rows).set_index(["region", "seed", "count", "cell"]).sort_index()
    expected_offsets = pd.read_csv(BASE / "full/source_reestimated_offsets.csv", float_precision="round_trip").set_index(["region", "seed", "count", "cell"]).sort_index()
    require(actual_offsets.index.equals(expected_offsets.index) and len(actual_offsets) == 288, "Source offset replay count/identities differ")
    offset_columns = [f"offset{int(p*100):02d}" for p in LEVELS]
    offset_error = compare(actual_offsets[offset_columns], expected_offsets[offset_columns], "Reestimated source offsets differ")
    for field in ("positive_valid_cell_cases", "selected_pool_cases", "weighted_pool_rows", "fallback"):
        require(actual_offsets[field].equals(expected_offsets[field]), "Source calibration eligibility or fallback changed")
    target_rows, target_checks, baseline_rows, target_streams = [], [], [], set()
    for case in targets.itertuples(index=False):
        common = dict(station_key=case.station_key, year=case.year)
        with np.load(safe_data_path(case.input_file)) as arrays:
            observed, mean, residual = [arrays[name] for name in ("observed", "mean", "residual")]
            require(digest_arrays(observed, mean, residual) == case.input_sha256, "Frozen target arrays changed")
            native = h30(sampler(observed, mean, residual, seed_function(9, 0, case.station_index, case.year, 0), 20))
            native_error = compare(native, np.asarray(json.loads(case.historical_native_draws)), "Native target draws differ", tolerance=1e-8)
            raw_q = np.quantile(native, LEVELS)
            native_q_error = compare(raw_q, [getattr(case, f"stochastic_h30_q{int(p*100):02d}") for p in LEVELS], "Native target quantiles differ", tolerance=1e-8)
            native_cal = apply_offsets(raw_q, case.bound, case.difficulty, historical["historical_offsets"][case.region])
            historical_error = compare(native_cal, [getattr(case, f"stochastic_cal_q{int(p*100):02d}") for p in LEVELS], "Historical target calibrated quantiles differ")
            target_checks.append(dict(**common, draw_error=native_error, quantile_error=native_q_error, historical_calibrated_error=historical_error))
            for method, prefix in [("historical_native20", "stochastic_cal"), ("fixed_D2", "D2")]:
                q = np.array([getattr(case, f"{prefix}_q{int(p*100):02d}") for p in LEVELS])
                baseline_rows.append(common | dict(method=method) | score(q, case.truth, case.bound))
            for seed in SEEDS:
                stream = seed_function(9, seed, case.station_index, case.year, 0)
                require(stream not in target_streams and stream not in source_streams, "Target/source random stream collides")
                target_streams.add(stream)
                values = h30(sampler(observed, mean, residual, stream, 500))
                for count in BUDGETS:
                    raw = np.quantile(values[:count], LEVELS)
                    layers = {"uncalibrated": project(raw[None, :], np.array([case.bound]))[0],
                              "fixed_old_offset": apply_offsets(raw, case.bound, case.difficulty, historical["historical_offsets"][case.region]),
                              "reestimated_source_offset": apply_offsets(raw, case.bound, case.difficulty, corrections[case.region, seed, count])}
                    for layer, q in layers.items():
                        target_rows.append(common | dict(seed=seed, count=count, layer=layer) | score(q, case.truth, case.bound))
    targets_actual = pd.DataFrame(target_rows).set_index(["seed", "count", "layer", "station_key", "year"]).sort_index()
    targets_expected = pd.read_csv(BASE / "full/target_three_layer_cases.csv", float_precision="round_trip").set_index(["seed", "count", "layer", "station_key", "year"]).sort_index()
    metric_columns = QCOLS + ["truth", "bound", "bias", "mae", "width90", "covered90", "crps256_normal", "interval_score90"]
    require(targets_actual.index.equals(targets_expected.index) and len(targets_actual) == 729, "Target three-layer replay case set differs")
    target_error = compare(targets_actual[metric_columns], targets_expected[metric_columns], "Replayed target quantiles/metrics differ")
    baseline_actual = pd.DataFrame(baseline_rows).set_index(["method", "station_key", "year"]).sort_index()
    baseline_expected = pd.read_csv(BASE / "full/target_historical_reference.csv", float_precision="round_trip").set_index(["method", "station_key", "year"]).sort_index()
    baseline_error = compare(baseline_actual[metric_columns], baseline_expected[metric_columns], "Fixed D2/historical reference metrics differ")
    dependency_manifest = BASE / "frozen_replay_dependency_manifest.json"
    manifest_content = dict(scope="Exact files needed by default frozen replay; materialization-only historical sources are not needed.",
                            required_files=dependencies, additionally_package=[label(dependency_manifest)],
                            python_packages=["numpy", "pandas", "pyarrow", "scipy"],
                            command="PYTHONPATH=src python scripts/975_replay_source_calibration.py")
    if dependency_manifest.exists():
        require(json.loads(dependency_manifest.read_text()) == manifest_content, "Frozen replay dependency manifest changed; inspect current inputs before updating it")
    else:
        dependency_manifest.write_text(json.dumps(manifest_content, indent=2) + "\n")
    return dict(status="passed", mode="frozen_input_replay", runtime_seconds=time.monotonic()-started,
                source_cases=2370, source_array_shards=int(manifest.input_file.nunique()), target_cases=27,
                target_array_files=int(targets.input_file.nunique()), seeds=list(SEEDS), budgets=list(BUDGETS),
                source_case_budget_quantiles=len(actual_q), reestimated_offset_cells=288, target_layer_cases=729,
                original_source_unavailable_cases=sum(not row["available"] for row in source_checks),
                native_source_draw_max_abs_error=max(row["draw_error"] for row in source_checks if row["draw_error"] is not None),
                native_source_quantile_max_abs_error=max(row["quantile_error"] for row in source_checks if row["quantile_error"] is not None),
                native_target_draw_max_abs_error=max(row["draw_error"] for row in target_checks),
                native_target_quantile_max_abs_error=max(row["quantile_error"] for row in target_checks),
                historical_source_offset_max_abs_error=max(original_offset_errors),
                historical_target_calibrated_max_abs_error=max(row["historical_calibrated_error"] for row in target_checks),
                source_budget_quantile_max_abs_error=source_error, new_source_offset_max_abs_error=offset_error,
                target_quantile_metric_max_abs_error=target_error, fixed_reference_metric_max_abs_error=baseline_error,
                source_role_offsets_reestimated=True, source_target_random_stream_intersections=0,
                source_only_calibration=True, source_eligibility_and_fallback_unchanged=True,
                daily_model_fit=False, D2_model_fit=False, original_daily_panels_opened=False,
                original_case_caches_opened=False, original_model_joblibs_opened=False,
                audited_results_overwritten=False, absolute_tolerance=ATOL, native_comparison_tolerance=1e-8,
                dependency_manifest=label(dependency_manifest), required_packaged_files=[*dependencies, label(dependency_manifest)],
                environment={"python": sys.version.split()[0], **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pyarrow", "scipy")}},
                limits=["Replays frozen daily model inputs and recorded source roles, not raw-data preparation or fitting",
                        "D2 quantiles are stored fixed references, not independently regenerated model predictions",
                        "Source-calibrated sensitivity is checked on the original two target groups only",
                        "500 paths do not establish infinite-draw convergence or broad method-ranking robustness"])


def isolated_dependency_check(paths):
    with tempfile.TemporaryDirectory(prefix="frozen_source_replay_") as temporary:
        root = Path(temporary)
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        environment = os.environ.copy()
        environment.update(PYTHONPATH="src", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        log = BASE / "frozen_replay_isolated.log"
        with log.open("w") as stream:
            result = subprocess.run([sys.executable, "scripts/975_replay_source_calibration.py"], cwd=root, env=environment,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        require(result.returncode == 0, "Minimal-dependency isolated replay failed; see " + label(log))
        receipt = json.loads((root / BASE.relative_to(ROOT) / "replay_receipt.json").read_text())
        require(receipt["status"] == "passed", "Minimal isolated replay did not pass")
        return dict(status="passed", files_copied=len(paths), source_cases=receipt["source_cases"], target_layer_cases=receipt["target_layer_cases"],
                    source_budget_quantile_max_abs_error=receipt["source_budget_quantile_max_abs_error"],
                    source_offset_max_abs_error=receipt["new_source_offset_max_abs_error"], target_metric_max_abs_error=receipt["target_quantile_metric_max_abs_error"],
                    no_original_daily_panels_case_caches_or_model_files_copied=True, log=label(log))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-inputs", action="store_true", help="Materialize new current-content references and target copies before replay")
    parser.add_argument("--check-isolated", action="store_true", help="Also replay a temporary copy containing only the declared dependencies")
    args = parser.parse_args()
    if args.freeze_inputs:
        freeze_inputs()
    try:
        receipt = replay()
        if args.check_isolated:
            receipt["minimal_dependency_isolated_check"] = isolated_dependency_check(receipt["required_packaged_files"])
    except Exception as error:
        receipt = dict(status="failed", mode="frozen_input_replay", failure=str(error).replace(str(ROOT), "{workspace}"))
        (BASE / "replay_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        raise
    (BASE / "replay_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: receipt[key] for key in ["status", "source_cases", "target_layer_cases", "new_source_offset_max_abs_error", "target_quantile_metric_max_abs_error", "runtime_seconds"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
