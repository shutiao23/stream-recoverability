#!/usr/bin/env python3
"""Execute evaluation-label contamination controls against 968.analyse_full.

Only module OUT and load_targets are patched. Existing source draws, masks,
role multiplicities, bounds, reference quantiles and all native20 safeguards
remain in place. Each execution writes into its own temporary copy. This tests
the calibration/scoring interface, not raw hidden-day perturbation and refitting.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/wrr_process_experiments_20261029/source_calibration"
QCOLS = [f"q{probability:02d}" for probability in (5, 10, 25, 50, 75, 90, 95)]
OFFSET_COLUMNS = [f"offset{probability:02d}" for probability in (5, 10, 25, 50, 75, 90, 95)]
OFFSET_KEYS = ["region", "seed", "count", "cell"]
TARGET_KEYS = ["seed", "count", "layer", "station_key", "year"]
# The 15 scientific output tables plus four core source/target/plan files.
PROTECTED = [
    "plan.json", "source_union_cases.parquet", "source_role_cases.csv", "fixed_target_cases.csv",
    "full/source_frozen_manifest.csv", "full/source_native20_checks.csv", "full/source_nested_draws.parquet",
    "full/source_nested_quantiles.csv", "full/source_pool_availability.csv", "full/source_unavailable_cases.csv",
    "full/source_reestimated_offsets.csv", "full/target_native20_checks.csv", "full/target_nested_draws.parquet",
    "full/target_historical_reference.csv", "full/target_three_layer_cases.csv", "full/target_three_layer_summary.csv",
    "full/target_budget_case_deltas.csv", "full/target_budget_tail_summary.csv", "full/target_source_offset_stage_contrasts.csv",
]


class ProbeFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeFailure(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def table(folder, name, keys):
    return pd.read_csv(folder / "full" / name, float_precision="round_trip").set_index(keys).sort_index()


def hash_protected():
    require(len(PROTECTED) == 19 and len(set(PROTECTED)) == 19, "Protected result list must contain 19 unique files")
    return {name: sha(BASE / name) for name in PROTECTED}


def exact_frame(a, b, message):
    try:
        pd.testing.assert_frame_equal(a, b, check_exact=True, check_dtype=True)
    except AssertionError as error:
        raise ProbeFailure(message + ": " + str(error)[:600]) from error


def main():
    started = time.monotonic()
    before = hash_protected()
    report_path = BASE / "calibration_leakage_probe.json"
    log_path = BASE / "calibration_leakage_probe.log"
    module_path = ROOT / "scripts/968_process_source_calibration.py"
    report = dict(
        status="running", probe="Executed evaluation-label contamination controls",
        tested_module="scripts/968_process_source_calibration.py", tested_module_sha256=sha(module_path),
        invoked_function="analyse_full(source_union)", patches=["module.OUT", "module.load_targets"],
        input_hashes_before=before,
        scope="Evaluation/reference truth labels entering the annual calibration and scoring stage; fixed daily-model inputs and source trajectory draws remain unchanged.",
        not_tested="Not a perturbation of original hidden water-temperature days followed by daily-model refitting; no claim about leakage in upstream daily fitting or feature construction.",
    )
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("executed_calibration_probe_968", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = pd.read_parquet(BASE / "source_union_cases.parquet")
        original_targets = module.load_targets()
        original_out, original_loader = module.OUT, module.load_targets
        with tempfile.TemporaryDirectory(prefix="calibration_label_probe_") as temporary, log_path.open("w") as log:
            temporary = Path(temporary)
            outputs = {}
            executions = {}
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                for scenario in ("baseline", "target_truth_permuted", "target_truth_plus_one", "source_truth_plus_one"):
                    folder = temporary / scenario
                    shutil.copytree(BASE / "full/station_parts", folder / "full/station_parts")
                    shutil.copyfile(BASE / "source_role_cases.csv", folder / "source_role_cases.csv")
                    targets = original_targets.copy(deep=True)
                    union = source.copy(deep=True)
                    if scenario == "target_truth_permuted":
                        values = original_targets.truth.to_numpy(float)
                        targets["truth"] = np.random.default_rng(2026102976).permutation(values)
                        require(not np.array_equal(targets.truth, values), "Target permutation did not change truth labels")
                    elif scenario == "target_truth_plus_one":
                        targets["truth"] = original_targets.truth + 1.0
                    elif scenario == "source_truth_plus_one":
                        union["eval_truth_h30"] = source.eval_truth_h30 + 1.0
                    exact_frame(targets.drop(columns="truth"), original_targets.drop(columns="truth"), "Target draw/reference/bound inputs changed outside truth")
                    exact_frame(union.drop(columns="eval_truth_h30"), source.drop(columns="eval_truth_h30"), "Source draws, bounds or roles changed outside truth")
                    module.OUT = folder
                    module.load_targets = lambda selected=targets: selected.copy(deep=True)
                    print("EXECUTE", scenario, flush=True)
                    try:
                        execution = module.analyse_full(union)
                    except Exception as error:
                        # Preserve every existing safety guard. A failed positive
                        # control is reported, never bypassed to manufacture a pass.
                        report["guard_failure"] = dict(scenario=scenario, error=str(error))
                        raise ProbeFailure(f"analyse_full rejected {scenario}: {error}") from error
                    outputs[scenario] = folder
                    executions[scenario] = {key: execution[key] for key in ["status", "source_cases_regenerated", "target_cases", "source_role_offsets_reestimated"]}
                baseline = outputs["baseline"]
                offsets = table(baseline, "source_reestimated_offsets.csv", OFFSET_KEYS)
                targets = table(baseline, "target_three_layer_cases.csv", TARGET_KEYS)
                source_q = table(baseline, "source_nested_quantiles.csv", ["case_id", "seed", "count"])
                require(len(offsets) == 288 and len(targets) == 729 and len(source_q) == 21330, "Baseline full-case dimensions changed")
                exact_frame(offsets, table(BASE, "source_reestimated_offsets.csv", OFFSET_KEYS), "Temporary baseline offsets differ from official results")
                exact_frame(targets, table(BASE, "target_three_layer_cases.csv", TARGET_KEYS), "Temporary baseline target scores differ from official results")
                negative = []
                for scenario in ("target_truth_permuted", "target_truth_plus_one"):
                    offset_other = table(outputs[scenario], "source_reestimated_offsets.csv", OFFSET_KEYS)
                    target_other = table(outputs[scenario], "target_three_layer_cases.csv", TARGET_KEYS)
                    source_other = table(outputs[scenario], "source_nested_quantiles.csv", ["case_id", "seed", "count"])
                    exact_frame(offsets, offset_other, "Target evaluation truth changed a source offset")
                    exact_frame(source_q, source_other, "Target evaluation truth changed a source trajectory quantile")
                    exact_frame(targets[QCOLS + ["bound"]], target_other[QCOLS + ["bound"]], "Target evaluation truth changed target distribution/bound")
                    changed_mae = int((targets.mae != target_other.mae).sum())
                    changed_crps = int((targets.crps256_normal != target_other.crps256_normal).sum())
                    changed_bias = int((targets.bias != target_other.bias).sum())
                    require(changed_mae > 0 and changed_crps > 0 and changed_bias > 0, "Target scoring failed to react to changed evaluation truth")
                    if scenario == "target_truth_plus_one":
                        require(np.allclose(target_other.bias.to_numpy() - targets.bias.to_numpy(), -1.0, rtol=0, atol=1e-12), "Target +1 truth did not shift bias by -1")
                    negative.append(dict(scenario=scenario, executed=True, offset_cells_unchanged_exactly=288,
                                         offset_scalar_values_unchanged_exactly=288*7,
                                         offset_csv_bytes_unchanged=sha(baseline / "full/source_reestimated_offsets.csv") == sha(outputs[scenario] / "full/source_reestimated_offsets.csv"),
                                         source_quantile_rows_unchanged_exactly=len(source_q), target_quantile_rows_unchanged_exactly=729,
                                         changed_target_bias_rows=changed_bias, changed_target_mae_rows=changed_mae, changed_target_crps_rows=changed_crps))
                positive_folder = outputs["source_truth_plus_one"]
                positive_offsets = table(positive_folder, "source_reestimated_offsets.csv", OFFSET_KEYS)
                positive_source_q = table(positive_folder, "source_nested_quantiles.csv", ["case_id", "seed", "count"])
                exact_frame(source_q, positive_source_q, "Source-label control changed the fixed source trajectories")
                metadata = [column for column in offsets if column not in OFFSET_COLUMNS and not column.startswith("change_vs_native")]
                exact_frame(offsets[metadata], positive_offsets[metadata], "Source-label control changed source weights, eligibility or fallback")
                shift = positive_offsets[OFFSET_COLUMNS].to_numpy() - offsets[OFFSET_COLUMNS].to_numpy()
                maximum_error = float(abs(shift - 1.0).max())
                require(maximum_error < 1e-12, "Source truth +1 failed to increase every pre-target-projection calibration offset by +1")
                positive_targets = table(positive_folder, "target_three_layer_cases.csv", TARGET_KEYS)
                reestimated = targets.index.get_level_values("layer") == "reestimated_source_offset"
                changed_target_q = int(np.any(targets.loc[reestimated, QCOLS].to_numpy() != positive_targets.loc[reestimated, QCOLS].to_numpy(), axis=1).sum())
                require(changed_target_q > 0, "Source-label positive control did not affect reestimated target distributions")
                for layer in ("uncalibrated", "fixed_old_offset"):
                    selected = targets.index.get_level_values("layer") == layer
                    exact_frame(targets.loc[selected], positive_targets.loc[selected], "Source truth changed a target layer that keeps source offsets fixed")
                report.update(status="passed", executions=executions, target_label_negative_controls=negative,
                              source_label_positive_control=dict(executed=True, source_truth_delta=1.0, offset_cells_checked=288,
                                offset_scalar_values_checked=2016, expected_pre_target_projection_offset_shift=1.0,
                                maximum_abs_error_from_plus_one=maximum_error,
                                fixed_source_quantile_rows_unchanged_exactly=len(source_q), source_pool_and_fallback_unchanged=True,
                                changed_reestimated_target_distribution_rows=changed_target_q,
                                target_uncalibrated_and_fixed_old_offset_layers_unchanged=True),
                              no_calibration_guard_disabled=True, temporary_outputs_only=True)
        module.OUT, module.load_targets = original_out, original_loader
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = str(error).replace(str(ROOT), "{workspace}")
    finally:
        after = hash_protected()
        report["input_hashes_after"] = after
        report["formal_result_files_checked"] = len(PROTECTED)
        report["formal_results_unchanged"] = before == after
        if before != after:
            report["status"] = "failed"
            report["failure"] = "Formal scientific result hashes changed during the probe"
        report["runtime_seconds"] = time.monotonic() - started
        report["log"] = str(log_path.relative_to(ROOT))
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(status=report["status"], report=str(report_path.relative_to(ROOT)),
                          formal_result_files_unchanged=report["formal_results_unchanged"], runtime_seconds=report["runtime_seconds"])))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
