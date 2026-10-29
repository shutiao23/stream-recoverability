#!/usr/bin/env python3
"""Validate the current candidate ZIP and replay its frozen trajectory diagnostic.

Checks CRCs, extraction paths, and exact packaged/workspace file bytes before
executing packaged code. In a temporary extracted copy, runs manuscript
transcription checks and compiles the article/SI, then repeats 962 without
--replay or --refresh-frozen. This tests the included saved-input path in the
currently installed environment, not full raw-data rebuilding or retraining.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_revision_20261029"
RESULT = PurePosixPath("results/wrr_process_revision_20261029")
CSV_OUTPUTS = (
    "trajectory_revision_nested_cases.csv", "trajectory_revision_case_deltas.csv",
    "trajectory_revision_stratum_tails.csv", "trajectory_revision_seed_ranges.csv",
    "trajectory_revision_stratum_scores.csv", "trajectory_revision_overall_scores.csv",
    "trajectory_revision_group_scope.csv", "trajectory_revision_frozen_manifest.csv",
)
SOURCE_FLAGS = (
    "source_role_offsets_reestimated", "source_role_calibration_sensitivity_executed",
    "target_subset_even_odd_calibration_executed", "trajectory_count_convergence_established",
    "fine_method_ranking_robustness_established",
)
GENERATED_PACKAGE_FILES = {"REVIEW_PACKAGE_README.txt", "dependency_inventory.json"}
EXCLUDED_VALIDATION_BASENAMES = {"validation.json", "delivery_check.json"}


class DeliveryFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DeliveryFailure(message)


def relative_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_member_path(name: str) -> PurePosixPath:
    require(bool(name) and "\x00" not in name and "\\" not in name, "ZIP member has an invalid path encoding")
    require(not name.startswith("/") and not name.startswith("~"), "ZIP member is absolute or home-relative")
    parts = name.rstrip("/").split("/")
    require(all(part not in {"", ".", ".."} and ":" not in part for part in parts), "ZIP member has an unsafe path component")
    path = PurePosixPath(*parts)
    require(not path.is_absolute(), "ZIP member path is absolute")
    return path


def same_stream_bytes(left, right) -> bool:
    while True:
        a, b = left.read(1024 * 1024), right.read(1024 * 1024)
        if a != b:
            return False
        if not a:
            return True


def validate_members(zipped: zipfile.ZipFile) -> dict:
    names, files, directories = set(), set(), set()
    compared, skipped, compared_bytes = 0, [], 0
    for info in zipped.infolist():
        path = safe_member_path(info.filename)
        label = path.as_posix()
        require(label not in names, "ZIP has duplicate or colliding normalized member paths: " + label)
        names.add(label)
        kind = stat.S_IFMT(info.external_attr >> 16)
        require(kind in {0, stat.S_IFREG, stat.S_IFDIR}, "ZIP contains a symlink or special file: " + label)
        require(not info.flag_bits & 1, "ZIP member is encrypted: " + label)
        if info.is_dir():
            directories.add(label)
            continue
        files.add(label)
        if label in GENERATED_PACKAGE_FILES or path.name in EXCLUDED_VALIDATION_BASENAMES:
            skipped.append(label)
            continue
        current = ROOT / label
        require(current.is_file(), "Packaged file is absent from workspace: " + label)
        require(current.stat().st_size == info.file_size, "Packaged/workspace file sizes differ: " + label)
        with zipped.open(info) as packed, current.open("rb") as workspace:
            require(same_stream_bytes(packed, workspace), "Packaged/workspace bytes differ: " + label)
        compared += 1
        compared_bytes += info.file_size
    for label in names:
        for parent in PurePosixPath(label).parents:
            require(parent.as_posix() not in files, "ZIP file masks a parent directory: " + label)
    bad_crc = zipped.testzip()
    require(bad_crc is None, "ZIP CRC failure: " + str(bad_crc))
    return {
        "crc": "passed", "safe_paths": "passed", "members": len(names), "files": len(files),
        "workspace_byte_comparisons": compared, "workspace_bytes_compared": compared_bytes,
        "skipped_generated_or_validation_members": sorted(skipped),
        "exclusions": "Only root package README/dependency inventory and validation.json/delivery_check.json basenames are excluded. Repository README.md files are compared.",
    }


def installed_environment() -> dict:
    packages = {}
    for name in ("numpy", "pandas", "pyarrow", "scipy", "matplotlib", "scikit-learn", "torch"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "platform": platform.system(), "machine": platform.machine(), "packages": packages,
        "python_environment": "Current interpreter and installed libraries; no dependency installation or clean-environment portability test.",
        "subprocess_overrides": {"PYTHONPATH": "src", "TR_CONFIG": "configs/wrr_target_recovery_20261022.json",
                                 "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
    }


def execute(command: list[str], folder: Path, environment: dict, log: Path, timeout: int) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as stream:
        process = subprocess.run(command, cwd=folder, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                 text=True, timeout=timeout)
    require(process.returncode == 0, "Isolated subprocess failed; see " + relative_label(log))


def check_frozen_manifest(root: Path) -> dict:
    manifest = pd.read_csv(root / RESULT / "trajectory_revision_frozen_manifest.csv", float_precision="round_trip")
    require(len(manifest) == 27 and not manifest.duplicated(["station_key", "year"]).any(), "Frozen manifest is not 27 unique station-years")
    require(manifest.station_key.nunique() == 6 and manifest.independence_group.nunique() == 2, "Frozen diagnostic does not have six stations and two groups")
    input_hashes = {}
    for row in manifest.itertuples(index=False):
        relative = safe_member_path(str(row.input_file))
        path = root / RESULT / relative
        require(path.is_file() and path.suffix == ".npz", "Frozen daily-model input is absent: " + relative.as_posix())
        input_hashes[str(RESULT / relative)] = sha256(path)
    require(len(input_hashes) == 27, "Frozen input paths are not unique")
    return input_hashes


def calibration_flags(report: dict) -> dict:
    flags = report["source_calibration"]
    for name in SOURCE_FLAGS:
        require(flags.get(name) is False, "Unexecuted calibration or convergence is claimed: " + name)
    return {name: flags[name] for name in SOURCE_FLAGS}


def isolated_validation(archive: Path, log_directory: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="wrr_process_delivery_") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as zipped:
            # Every member has already passed the path/symlink/CRC checks.
            zipped.extractall(root)
            baseline_csv = {name: pd.read_csv(io.BytesIO(zipped.read(str(RESULT / name))), float_precision="round_trip")
                            for name in CSV_OUTPUTS}
            baseline_draws = pd.read_parquet(io.BytesIO(zipped.read(str(RESULT / "trajectory_revision_h30_draws.parquet"))))
            original_report = json.loads(zipped.read(str(RESULT / "trajectory_revision_report.json")))
        original_flags = calibration_flags(original_report)
        require(original_report["seeds"] == [0, 1, 2] and original_report["counts"] == [20, 100, 500], "Packaged trajectory seed/budget list differs")
        frozen_before = check_frozen_manifest(root)
        environment = os.environ.copy()
        environment.update(installed_environment()["subprocess_overrides"])
        environment["MPLCONFIGDIR"] = str(root / ".delivery_cache/matplotlib")
        # Run 930 in a separate interpreter to avoid resolving any previously
        # imported workspace modules when checking the extracted copy.
        worker = r'''
import importlib.util,json
from pathlib import Path
root=Path.cwd()
spec=importlib.util.spec_from_file_location("isolated_delivery_consistency", root/"scripts/930_delivery_consistency.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result={"transcription":module.check_tree(root),"compile":module.compile_pdfs(root)}
(root/"isolated_transcription_compile.json").write_text(json.dumps(result,indent=2)+"\n")
'''
        execute([sys.executable, "-c", worker], root, environment, log_directory / "transcription_compile.log", timeout=1800)
        transcription = json.loads((root / "isolated_transcription_compile.json").read_text())
        # Use the explicitly current content manifests. Historical manifests
        # remain untouched and are not retroactively authenticated by this run.
        execute([sys.executable, "scripts/967_current_observation_replay.py", "replay"], root, environment,
                log_directory / "observation_replay.log", timeout=1200)
        observations = json.loads((root / RESULT / "replay_integrity/replay_report.json").read_text())
        require(observations["status"] == "passed", "Isolated current observation replay did not pass")
        require(observations["historical_provenance_authenticated"] is False,
                "Current content replay must not authenticate historical provenance")
        observation_counts = {name: check["actual_report_counts"] for name, check in observations["checks"].items()}
        # Explicitly omit --replay: this path needs only the packaged frozen
        # arrays and does not reopen missing original observation archives.
        execute([sys.executable, "scripts/962_process_trajectory_budget.py"], root, environment,
                log_directory / "trajectory_replay.log", timeout=600)
        comparisons = []
        for name, original in baseline_csv.items():
            regenerated = pd.read_csv(root / RESULT / name, float_precision="round_trip")
            try:
                pd.testing.assert_frame_equal(original, regenerated, check_exact=True, check_dtype=True)
            except AssertionError as error:
                raise DeliveryFailure("Isolated regenerated CSV differs exactly: " + name + "; " + str(error)[:500]) from error
            comparisons.append({"file": str(RESULT / name), "rows": len(original), "columns": len(original.columns), "comparison": "Exact values, dtypes, column order and row order"})
        generated_draws = pd.read_parquet(root / RESULT / "trajectory_revision_h30_draws.parquet")
        require(list(baseline_draws.columns) == list(generated_draws.columns) and len(baseline_draws) == len(generated_draws), "Regenerated H30-draw table shape differs")
        non_draw = [column for column in baseline_draws if column != "h30_draws"]
        pd.testing.assert_frame_equal(baseline_draws[non_draw], generated_draws[non_draw], check_exact=True)
        for before, after in zip(baseline_draws.h30_draws, generated_draws.h30_draws):
            require(np.array_equal(before, after), "Regenerated 500-path H30 sample differs")
        frozen_after = check_frozen_manifest(root)
        require(frozen_before == frozen_after, "Isolated replay changed frozen daily-model inputs")
        regenerated_report = json.loads((root / RESULT / "trajectory_revision_report.json").read_text())
        require(calibration_flags(regenerated_report) == original_flags, "Calibration scope changed during isolated replay")
        require(regenerated_report["daily_inputs_refreshed_this_run"] is False, "Isolated replay refreshed daily models")
        # Generated manuscript text must also remain the packaged text. PDF
        # metadata timestamps are intentionally not a byte-comparison target.
        with zipfile.ZipFile(archive) as zipped:
            for name in ("process_trajectory_revision_values.tex", "process_trajectory_revision_table.tex", "process_trajectory_revision_supporting.tex"):
                relative = "paper/wrr_tr/" + name
                require((root / relative).read_bytes() == zipped.read(relative), "Isolated replay changed packaged manuscript input: " + relative)
        return {
            "transcription_and_compile": transcription, "csv_exact_comparisons": comparisons,
            "current_observation_replay": observation_counts, "historical_provenance_authenticated": False,
            "h30_sample_rows_exact": len(generated_draws), "h30_draws_per_row": 500,
            "frozen_inputs_unchanged": len(frozen_after), "source_calibration": original_flags,
            "trajectory_command": "PYTHONPATH=src python scripts/962_process_trajectory_budget.py",
            "daily_models_refit": False, "source_role_calibration_executed": False,
            "compile_order": "Transcription and both PDFs checked on the exact extracted package before trajectory regeneration.",
            "logs": [relative_label(log_directory / name) for name in ("transcription_compile.log", "observation_replay.log", "trajectory_replay.log")],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("dist/wrr_review_response_candidate.zip"))
    args = parser.parse_args()
    archive = args.archive if args.archive.is_absolute() else ROOT / args.archive
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "delivery_check.json"
    report = {
        "status": "running", "archive": relative_label(archive), "environment": installed_environment(),
        "scope": "Current candidate/workspace byte identity, ZIP safety and CRC, current observation arithmetic/rule replay, exact saved-input trajectory replay, manuscript transcription and isolated article/SI compilation.",
        "not_tested": ["Full original raw-data reconstruction", "Daily-model or D2 retraining",
                       "962 frozen-input replay does not re-estimate source-role offsets; that experiment is scripts/968 and 978",
                       "Strict independent external confirmation", "Clean-environment dependency installation", "Public data-rights clearance or permanent archival deposit"],
    }
    try:
        require(archive.is_file(), "Candidate archive does not exist: " + relative_label(archive))
        report["archive_sha256"] = sha256(archive)
        with zipfile.ZipFile(archive) as zipped:
            report["archive_integrity_and_workspace_match"] = validate_members(zipped)
        log_directory = OUT / "delivery_check_logs" / report["archive_sha256"][:16]
        report["isolated"] = isolated_validation(archive, log_directory)
        require(sha256(archive) == report["archive_sha256"], "Candidate ZIP changed during delivery verification")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = str(error).replace(str(ROOT), "{workspace}")
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": "failed", "report": relative_label(report_path), "failure": report["failure"]}), file=sys.stderr)
        return 1
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "passed", "report": relative_label(report_path), "archive_sha256": report["archive_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
