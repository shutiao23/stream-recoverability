#!/usr/bin/env python3
"""Freeze saved annual inputs and replay the bounded B numerical comparison.

Default execution reads only the new annual-input table and listed 969 result
tables. It imports the pure Fraction/np.polyfit geometry and score functions
from 974 without invoking that script's raw-input audit or main workflow.
--freeze-inputs records a current derived snapshot, not historical provenance.
Same-day missingness and paired-cluster intervals remain in the scope of 974.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import itertools
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

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "results/wrr_process_experiments_20261029"
OUT = EXPERIMENT / "time_frozen_replay"
ARCHIVE = ROOT / "results/wrr_review_response_20261027/whole_archive"
REFERENCE = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
PURE_HELPER = ROOT / "scripts/974_independent_time_gap_audit.py"
KEY = ["station_key", "replicate", "independence_group"]
FIELDS = ["estimate_mse", "year_set_mse", "reconstruction_mse", "cross_term", "cdf_distance", "sxx", "span", "mean_year", "end_abs_weight", "max_abs_weight"]
EXPECTED = ["time_archive_accounting.parquet", "time_all_feasible_subsets.parquet", "time_fixed_geometry_selections.parquet",
            "time_exact_random_expectations.parquet", "time_sensitivity_summary.csv"]
ATOL = 1e-9


class ReplayFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReplayFailure(message)


def compare(a, b, message):
    a, b = np.asarray(a, float), np.asarray(b, float)
    require(a.shape == b.shape and np.array_equal(np.isfinite(a), np.isfinite(b)), message + ": shape/availability differs")
    mask = np.isfinite(a)
    maximum = float(abs(a[mask] - b[mask]).max()) if mask.any() else 0.0
    require(maximum <= ATOL, f"{message}: maximum absolute error {maximum}")
    return maximum


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def label(path):
    return str(Path(path).resolve().relative_to(ROOT))


def parse_years(value):
    if value is None or pd.isna(value) or str(value) == "":
        return tuple()
    return tuple(map(int, str(value).split(";")))


def freeze_inputs():
    """Read original saved inputs once and create a new, explicit derived table."""
    OUT.mkdir(parents=True, exist_ok=True)
    reference = pd.read_parquet(REFERENCE, columns=["station_key", "year", "design_family", "eval_truth_h30"])
    reference = reference.loc[reference.design_family.eq("crossed") & reference.year.ge(2010)]
    require(reference.groupby(["station_key", "year"]).eval_truth_h30.nunique().max() == 1, "Complete-reference station-year truth is inconsistent")
    references = {station: part.drop_duplicates("year").set_index("year").eval_truth_h30.sort_index()
                  for station, part in reference.groupby("station_key")}
    trends_path = ARCHIVE / "trends.csv"
    trends = pd.read_csv(trends_path)
    trends = trends.loc[trends.family.eq("crossed") & trends["mode"].eq("forward") & trends.estimator.eq("D2") & trends.dependence.eq("point")]
    original_paths = {REFERENCE, trends_path}
    rows = []
    for (station, replicate), block in trends.groupby(["station_key", "replicate"], sort=True):
        folder = ARCHIVE / "crossed/forward" / f"replicate_{replicate:02d}" / station.replace("|", "_")
        design_path, prediction_path = folder / "design.json", folder / "annual_predictions.parquet"
        original_paths.update([design_path, prediction_path])
        design = json.loads(design_path.read_text())
        masks = set(map(int, design["masks"]))
        saved = block.set_index("retention")
        predictions = pd.read_parquet(prediction_path).set_index("year") if masks else None
        for year, truth in references[station].items():
            missing = int(year) in masks
            d2 = float(predictions.loc[year].D2) if missing else np.nan
            warm = not missing or float(predictions.loc[year].warm_observed_fraction) >= .9
            rows.append(dict(station_key=station, replicate=int(replicate), independence_group=design["independence_group"], region=design["region"],
                             year=int(year), truth_h30=float(truth), d2_point_h30=d2, point_h30=d2 if missing else float(truth),
                             missing=missing, warm_keep=bool(warm), original_all_evaluable=bool(saved.loc["all"].available),
                             original_warm_evaluable=bool(saved.loc["warm90"].available)))
    inputs = pd.DataFrame(rows).sort_values(KEY + ["year"]).reset_index(drop=True)
    require(not inputs.duplicated(KEY + ["year"]).any(), "Frozen archive/year rows are duplicated")
    data_path = OUT / "annual_inputs.parquet"
    if data_path.exists():
        pd.testing.assert_frame_equal(pd.read_parquet(data_path), inputs, check_exact=True)
    else:
        inputs.to_parquet(data_path, index=False)
    frozen = dict(
        scope="Current-content derived freeze of saved predictions, masks and complete-reference outcomes. It does not establish original measurement provenance or an earlier historical identity.",
        materialization_only_input_sha256={label(path): sha(path) for path in sorted(original_paths)},
        derived_file=label(data_path), derived_sha256=sha(data_path), annual_rows=len(inputs), archives=int(inputs[KEY].drop_duplicates().shape[0]),
        fields={"truth_h30": "Unique complete-reference H30 used only to evaluate finite-record slopes",
                "d2_point_h30": "Saved D2 point on a masked year; missing on fully observed reference years",
                "point_h30": "The point used in the experiment: D2 on masked years, observed reference on unmasked years",
                "missing": "Year belongs to the original whole-archive mask design",
                "warm_keep": "Complete reference years plus masked years meeting the stored warm-season 90% criterion",
                "original_all_evaluable": "Original saved all-year availability flag (at least five retained years and supported points)",
                "original_warm_evaluable": "Original saved warm-season availability flag; the thirteen exclusions retain only three or four years"},
        limits="Annual numeric replay only; original daily preprocessing, fitting, daily gap overlap and group uncertainty are not rerun by this entry point.")
    manifest_path = OUT / "freeze_manifest.json"
    if manifest_path.exists():
        require(json.loads(manifest_path.read_text()) == frozen, "Existing current-content annual freeze changed")
    else:
        manifest_path.write_text(json.dumps(frozen, indent=2) + "\n")


def pure_functions():
    spec = importlib.util.spec_from_file_location("pure_time_geometry_974", PURE_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.score


def replay():
    started = time.monotonic()
    inputs = pd.read_parquet(OUT / "annual_inputs.parquet")
    freeze = json.loads((OUT / "freeze_manifest.json").read_text())
    require(sha(OUT / "annual_inputs.parquet") == freeze["derived_sha256"], "Frozen annual input file changed")
    require(not inputs.duplicated(KEY + ["year"]).any(), "Annual input identity is duplicated")
    score_set = pure_functions()
    accounting = pd.read_parquet(EXPERIMENT / "time_archive_accounting.parquet").set_index(KEY)
    saved_subsets = pd.read_parquet(EXPERIMENT / "time_all_feasible_subsets.parquet").set_index(KEY + ["subset_id"])
    saved_fixed = pd.read_parquet(EXPERIMENT / "time_fixed_geometry_selections.parquet").set_index(KEY + ["scheme"])
    saved_expected = pd.read_parquet(EXPERIMENT / "time_exact_random_expectations.parquet").set_index(KEY)
    saved_summary = pd.read_csv(EXPERIMENT / "time_sensitivity_summary.csv", float_precision="round_trip").set_index(["scope", "weighting", "scheme"])
    raw_rows, scored, expected, errors = [], [], [], []
    feasible_count = 0
    for key, block in inputs.groupby(KEY, sort=True):
        block = block.sort_values("year")
        require(block.original_all_evaluable.nunique() == block.original_warm_evaluable.nunique() == 1, "Original availability changes within an archive")
        years = block.year.to_numpy(int)
        truth, point = block.truth_h30.to_numpy(float), block.point_h30.to_numpy(float)
        missing = block.missing.to_numpy(bool)
        warm = block.warm_keep.to_numpy(bool)
        require(np.isfinite(truth).all() and np.isfinite(point).all(), "Annual score inputs are unsupported")
        require(warm[~missing].all(), "Fixed complete years were removed")
        compare(point[~missing], truth[~missing], "Complete-year point differs from its observed reference")
        compare(point[missing], block.loc[missing, "d2_point_h30"].to_numpy(float), "Masked-year D2 point changed")
        require(bool(block.original_all_evaluable.iloc[0]) == (len(years) >= 5), "All-year five-year availability flag differs")
        require(bool(block.original_warm_evaluable.iloc[0]) == (warm.sum() >= 5), "Warm-season five-year availability flag differs")
        common = bool(block.original_all_evaluable.iloc[0] and block.original_warm_evaluable.iloc[0])
        k = int((warm & missing).sum())
        identity = dict(zip(KEY, key)) | dict(region=block.region.iloc[0])
        flags = dict(original_common=common, primary=common and bool(missing.any()), nontrivial_choice=common and 0 < k < int(missing.sum()))
        raw_rows.append(identity | flags)
        original = accounting.loc[key]
        require(all(bool(original[name]) == value for name, value in flags.items()), "Frozen cohort flags differ from 969")
        if not common:
            continue
        complete = tuple(years[~missing])
        incomplete = tuple(years[missing])
        options = []
        for index, chosen in enumerate(itertools.combinations(incomplete, k)):
            selected = tuple(sorted(complete + chosen))
            metrics = score_set(years, truth, point, selected)
            saved = saved_subsets.loc[key + (index,)]
            require(parse_years(saved.retained_years) == selected and parse_years(saved.chosen_incomplete_years) == chosen, "Frozen feasible subset identity differs")
            errors.append(compare([metrics[field] for field in FIELDS], saved[FIELDS].to_numpy(float), "Frozen subset score/geometry differs"))
            options.append(dict(subset_id=index, chosen=chosen, selected=selected, **metrics))
        require(len(options) == math.comb(int(missing.sum()), k), "Frozen subset enumeration is not exhaustive")
        feasible_count += len(options)
        compare(saved_subsets.loc[key].uniform_subset_probability.to_numpy(float), np.full(len(options), 1/len(options)), "Feasible subset uniform probabilities differ")
        cdf = min(options, key=lambda row: (round(row["cdf_distance"], 14), -round(row["sxx"], 14), row["chosen"]))
        sxx = min(options, key=lambda row: (-round(row["sxx"], 14), round(row["cdf_distance"], 14), row["chosen"]))
        by_years = {row["selected"]: row for row in options}
        selected = {"warm90": by_years[tuple(years[warm])], "cdf_all_years": cdf, "sxx_all_years": sxx}
        # The two historical controls are declared fixed year-set inputs. Their
        # scores are recomputed; they are not relabelled new optimization rules.
        for legacy in ("legacy_random", "legacy_time_balanced"):
            selected[legacy] = by_years[parse_years(saved_fixed.loc[key + (legacy,)].retained_years)]
        for scheme, row in selected.items():
            saved = saved_fixed.loc[key + (scheme,)]
            require(parse_years(saved.retained_years) == row["selected"], "Frozen calendar selection or tie-break differs")
            scored.append(identity | dict(scheme=scheme) | {field: row[field] for field in FIELDS})
        full = score_set(years, truth, point, tuple(years))
        scored.append(identity | dict(scheme="all") | {field: full[field] for field in FIELDS})
        mean = {field: float(np.mean([row[field] for row in options])) for field in FIELDS}
        errors.append(compare([mean[field] for field in FIELDS], saved_expected.loc[key, FIELDS].to_numpy(float), "Frozen conditional random expectation differs"))
        expected.append(identity | dict(scheme="uniform_random_expected") | mean)
    archive = pd.DataFrame(raw_rows).set_index(KEY)
    require((len(archive), int(archive.original_common.sum()), int(archive.primary.sum()), int(archive.nontrivial_choice.sum()), feasible_count) == (820, 807, 805, 468, 5758), "Frozen denominator or feasible-set count differs")
    require(len(saved_subsets) == feasible_count and len(expected) == 807, "Frozen exact expectation denominator differs")
    score_rows = pd.DataFrame(scored + expected)
    checks, primary = 0, []
    for scope, selector in [("actual_mask_common", archive.primary), ("original_common", archive.original_common), ("choice_only", archive.nontrivial_choice)]:
        roster = archive.loc[selector]
        for weighting in ("equal_archive", "equal_station", "equal_group"):
            if weighting == "equal_archive":
                weights = np.ones(len(roster))
            else:
                labels = roster.index.get_level_values("station_key" if weighting == "equal_station" else "independence_group")
                counts = pd.Series(labels).value_counts()
                weights = np.array([1/counts[value] for value in labels])
            for scheme, block in score_rows.groupby("scheme"):
                block = block.set_index(KEY).reindex(roster.index)
                actual = {field: float(np.average(block[field], weights=weights)) for field in FIELDS}
                saved = saved_summary.loc[(scope, weighting, scheme)]
                fields = [field for field in FIELDS if field != "mean_year"]
                errors.append(compare([actual[field] for field in fields], saved[fields].to_numpy(float), "Frozen weighted summary differs"))
                rmses = [float(np.sqrt(actual[field])) for field in FIELDS[:3]]
                errors.append(compare(rmses, saved[["estimate_rmse", "year_set_rmse", "reconstruction_rmse"]].to_numpy(float), "Frozen root-of-expected-MSE summary differs"))
                require(abs(actual["estimate_mse"]-actual["year_set_mse"]-actual["reconstruction_mse"]-actual["cross_term"]) < 1e-10, "Frozen signed MSE identity fails")
                checks += 1
                if scope == "actual_mask_common" and weighting == "equal_archive":
                    primary.append(dict(scheme=scheme, estimate_rmse=rmses[0], year_set_rmse=rmses[1], reconstruction_rmse=rmses[2]))
    paths = [Path(__file__).resolve(), PURE_HELPER, OUT / "annual_inputs.parquet", OUT / "freeze_manifest.json"] + [EXPERIMENT / name for name in EXPECTED]
    dependencies = {label(path): dict(sha256=sha(path), bytes=path.stat().st_size) for path in sorted(paths)}
    dependency_path = OUT / "required_files.json"
    manifest = dict(scope="Closed annual numerical replay; original saved-reference and prediction caches are not required by default execution.",
                    required_files=dependencies, additionally_package=[label(dependency_path)], python_packages=["numpy", "pandas", "pyarrow"],
                    command="PYTHONPATH=src python scripts/977_replay_time_support.py")
    if dependency_path.exists():
        require(json.loads(dependency_path.read_text()) == manifest, "Existing annual replay dependency manifest changed")
    else:
        dependency_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return dict(status="passed", mode="frozen_saved_annual_input_replay", scope="Annual feasible-set enumeration, calendar-only optimization, conditional expected MSE and 805/807/468 weighted summaries from frozen saved inputs", runtime_seconds=time.monotonic()-started,
                frozen_annual_rows=len(inputs), raw_archives=820, original_common=807, actual_mask_common=805, choice_only=468,
                all_feasible_subsets=5758, exact_conditional_random_expectations=807, weighted_summary_checks=checks,
                maximum_abs_numeric_error=max(errors), absolute_tolerance=ATOL, primary_equal_archive_summaries=primary,
                legacy_controls="Saved legacy year sets are fixed inputs; their slopes are recomputed from the frozen annual rows.",
                exact_random_estimand="First average MSE uniformly over feasible subsets within archive, then aggregate archives and take the root. This is not mean realized RMSE across random seeds.",
                original_case_caches_opened=False, original_daily_panels_opened=False, models_fit=False,
                audited_results_overwritten=False, required_files=[*dependencies, label(dependency_path)], dependency_manifest=label(dependency_path),
                daily_gap_scope="Actual same-day gaps are not replayed here. scripts/974_independent_time_gap_audit.py and time_gap_independent_audit.json independently re-read original daily data and exclude group-years without an evaluable peer.",
                not_replayed=["Original data preparation or historical measurement provenance", "200 realized random-seed summaries and paired-group bootstrap intervals", "Actual same-day co-missingness"],
                environment={"python": sys.version.split()[0], **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pyarrow")}})


def isolated_check(paths):
    with tempfile.TemporaryDirectory(prefix="frozen_time_replay_") as temporary:
        root = Path(temporary)
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        environment = os.environ.copy()
        environment.update(PYTHONPATH="src", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        log_path = OUT / "isolated_replay.log"
        with log_path.open("w") as stream:
            result = subprocess.run([sys.executable, "scripts/977_replay_time_support.py"], cwd=root, env=environment,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=300)
        require(result.returncode == 0, "Minimal annual-input replay failed; see " + label(log_path))
        receipt = json.loads((root / OUT.relative_to(ROOT) / "replay_receipt.json").read_text())
        require(receipt["status"] == "passed", "Isolated annual replay did not pass")
        return dict(status="passed", files_copied=len(paths), annual_rows=receipt["frozen_annual_rows"],
                    feasible_sets=receipt["all_feasible_subsets"], weighted_summary_checks=receipt["weighted_summary_checks"],
                    maximum_abs_numeric_error=receipt["maximum_abs_numeric_error"],
                    no_original_case_caches_or_daily_data_copied=True, log=label(log_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-inputs", action="store_true")
    parser.add_argument("--check-isolated", action="store_true")
    parser.add_argument("--output", type=Path, help="Receipt destination; default is time_frozen_replay/replay_receipt.json")
    args = parser.parse_args()
    receipt_path = args.output if args.output is not None else OUT / "replay_receipt.json"
    if not receipt_path.is_absolute():
        receipt_path = ROOT / receipt_path
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if args.freeze_inputs:
        freeze_inputs()
    try:
        receipt = replay()
        if args.check_isolated:
            receipt["minimal_dependency_isolated_check"] = isolated_check(receipt["required_files"])
    except Exception as error:
        receipt = dict(status="failed", mode="frozen_saved_annual_input_replay", failure=str(error).replace(str(ROOT), "{workspace}"))
        OUT.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        raise
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({name: receipt[name] for name in ["status", "frozen_annual_rows", "all_feasible_subsets", "weighted_summary_checks", "maximum_abs_numeric_error", "runtime_seconds"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
