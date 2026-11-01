#!/usr/bin/env python3
"""Audit the corrected candidate without modifying production artifacts."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/wrr_postfix_review_20261101"
DATA = ROOT / "results/wrr_final_revision_20261031"
PACKAGE = ROOT / "dist/wrr_final_candidate_20261101.zip"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(name, record):
    (OUT / name).write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def comparator_checks():
    module = load_module("review_current_comparator", ROOT / "scripts/983_verify_extension_replay.py")
    name = "retention_geometry_cases.csv"
    frame = pd.read_csv(DATA / name)
    spec = json.loads((DATA / "table_spec.json").read_text())["tables"][name]
    rows = frame.iloc[:10].copy()
    finite_index = rows.index[rows.estimate_error.notna()][0]
    nan_index = rows.index[rows.estimate_error.isna()][0]
    probes = {}
    mutations = {
        "unchanged": lambda x: x,
        "row_order_only": lambda x: x.iloc[::-1],
        "finite_mse_plus_one": lambda x: x.assign(estimate_mse=x.estimate_mse + (x.index == finite_index)),
        "label_change": lambda x: x.assign(region=x.region.mask(x.index == finite_index, "reviewer_wrong_region")),
        "finite_to_nan": lambda x: x.assign(estimate_error=x.estimate_error.mask(x.index == finite_index, np.nan)),
        "structural_nan_to_finite": lambda x: x.assign(estimate_error=x.estimate_error.mask(x.index == nan_index, 1.0)),
        "infinity": lambda x: x.assign(estimate_mse=x.estimate_mse.mask(x.index == finite_index, np.inf)),
        "duplicate_key": lambda x: pd.concat([x, x.iloc[[0]]], ignore_index=True),
        "missing_key": lambda x: x.iloc[1:],
    }
    with tempfile.TemporaryDirectory(prefix="wrr_current_comparator_") as folder:
        folder = Path(folder)
        before = folder / "before.csv"
        after = folder / "after.csv"
        rows.to_csv(before, index=False)
        for label, mutate in mutations.items():
            mutate(rows.copy()).to_csv(after, index=False)
            try:
                result = module.compare_table(before, after, spec)
                probes[label] = {"status": "passed", "result": result}
            except module.ReplayComparisonError as error:
                probes[label] = {"status": "rejected", "reason": str(error)}
    expected = {name: ("passed" if name in {"unchanged", "row_order_only"} else "rejected") for name in mutations}
    record = {"probes": probes, "all_expected_outcomes": all(probes[k]["status"] == v for k, v in expected.items()),
              "scope": "Actual new compare_table on temporary copies of real current rows; package and production files unchanged."}
    save("comparator_probes.json", record)
    return record["all_expected_outcomes"]


def output_portability():
    members = [
        "scripts/981_stanford_revision.py", "scripts/980_final_release.py", "scripts/revision_table_spec.py",
        "results/wrr_process_revision_20261029/time_support_cases.csv",
        "results/wrr_review_response_20261027/whole_archive/trends.csv",
    ]
    inputs = ["reference_truths.csv", "case_designs.csv", "annual_predictions_compact.csv"]
    runs = []
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    with tempfile.TemporaryDirectory(prefix="wrr_output_portability_") as temporary:
        temporary = Path(temporary)
        code = temporary / "package_code"
        inside = code / "custom_outputs"
        outside = temporary / "outside_outputs"
        with zipfile.ZipFile(PACKAGE) as zipped:
            for name in members:
                target = code / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(name))
            for dest in [inside, outside]:
                dest.mkdir(parents=True, exist_ok=True)
                for name in inputs:
                    (dest / name).write_bytes(zipped.read("results/wrr_final_revision_20261031/" + name))
        for label, destination in [("inside_root_first", inside), ("inside_root_second", inside), ("outside_root", outside)]:
            paper = temporary / ("paper_" + label)
            command = [sys.executable, str(code / "scripts/981_stanford_revision.py"),
                       "--out", str(destination), "--paper", str(paper)]
            process = subprocess.run(command, cwd=code, text=True, capture_output=True, env=env)
            record = {"case": label, "exit_code": process.returncode,
                      "stdout_tail": process.stdout[-1200:], "stderr_tail": process.stderr[-2200:]}
            if process.returncode == 0:
                manifest = json.loads((destination / "data_manifest.json").read_text())
                matches = {}
                for name, expected in manifest["outputs"].items():
                    target = Path(name)
                    if not target.is_absolute():
                        target = destination / name if (destination / name).is_file() else code / name
                    matches[name] = hashlib.sha256(target.read_bytes()).hexdigest() == expected
                record["manifest_outputs"] = len(matches)
                record["all_output_hashes_match"] = all(matches.values())
                record["requested_paper_directory_used"] = all((paper / name).is_file() for name in
                    ["stanford_revision_values.tex", "stanford_calendar_table.tex", "stanford_geometry_table.tex"])
            runs.append(record)
    save("output_portability.json", {"runs": runs,
         "scope": "Packaged code and compact inputs only; original raw/cache inputs absent; all runs in a temporary directory."})
    return {record["case"]: record["exit_code"] for record in runs}


def ci_summary_guard():
    tests = load_module("review_freshness_fixture", ROOT / "tests/test_final_release_freshness.py")
    results = []
    variants = {
        "valid_nonzero_run": {"tests": 10, "passed": 9, "skipped": 1, "failures": 0, "errors": 0, "exit_code": 0},
        "exit_five_no_tests": {"tests": 0, "passed": 0, "skipped": 0, "failures": 0, "errors": 0, "exit_code": 5},
        "all_skipped": {"tests": 10, "passed": 0, "skipped": 10, "failures": 0, "errors": 0, "exit_code": 0},
        "inconsistent_pass_count": {"tests": 10, "passed": 100, "skipped": 0, "failures": 0, "errors": 0, "exit_code": 0},
    }
    for label, counts in variants.items():
        with tempfile.TemporaryDirectory(prefix="wrr_ci_guard_") as directory:
            monkeypatch = pytest.MonkeyPatch()
            try:
                module, _ = tests.fixture.__wrapped__(Path(directory), monkeypatch)
                path = module.OUT / "ci_local_summary.json"
                record = json.loads(path.read_text())
                record["full_pytest"] = counts
                path.write_text(json.dumps(record))
                # Bind the CI summary to this tiny package too, so acceptance
                # still has to pass its normal package/workspace byte check.
                with zipfile.ZipFile(module.DEST) as zipped:
                    payload = {name: zipped.read(name) for name in zipped.namelist()
                               if name != "CONTENT_MANIFEST.sha256"}
                payload[str(path.relative_to(module.ROOT))] = path.read_bytes()
                content = "".join(hashlib.sha256(value).hexdigest() + "  " + name + "\n"
                                  for name, value in sorted(payload.items())).encode()
                payload["CONTENT_MANIFEST.sha256"] = content
                with zipfile.ZipFile(module.DEST, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
                    for name, value in payload.items():
                        zipped.writestr(name, value)
                manifest = json.loads(module.EXTERNAL_MANIFEST.read_text())
                manifest.update(package_sha256=tests.sha(module.DEST),
                                package_bytes=module.DEST.stat().st_size,
                                members=len(payload), scientific_members=len(payload) - 2,
                                content_manifest_sha256=hashlib.sha256(content).hexdigest())
                module.EXTERNAL_MANIFEST.write_text(json.dumps(manifest))
                receipt = json.loads(payload["RELEASE_RECEIPT.json"])
                tests.write_verification(module, manifest, receipt)
                tests.write_delivery(module, manifest)
                replay_path = module.OUT / "extension_replay.json"
                replay = json.loads(replay_path.read_text())
                replay["archive_sha256"] = manifest["package_sha256"]
                replay_path.write_text(json.dumps(replay))
                try:
                    with redirect_stdout(io.StringIO()):
                        module.accept(None)
                    result = {"case": label, "status": "accepted", "full_pytest": counts}
                except module.ReleaseFailure as error:
                    result = {"case": label, "status": "rejected", "reason": str(error), "full_pytest": counts}
                results.append(result)
            finally:
                monkeypatch.undo()
    save("ci_summary_guard.json", {"probes": results,
         "scope": "Uses the repository's tiny temporary release fixture, with the CI summary additionally included in its ZIP and all package/verification identities synchronized. Evaluates full-pytest summary validation only; does not alter the real candidate or establish that the current real test run failed."})
    return {record["case"]: record["status"] for record in results}


def table_metadata():
    specs = json.loads((DATA / "table_spec.json").read_text())["tables"]
    designs = pd.read_csv(DATA / "case_designs.csv")
    parsed = [json.loads(value) for value in designs.masks]
    result = {"mask_json_types": sorted({type(value).__name__ for value in parsed}),
              "mask_rows": len(parsed), "example": parsed[0],
              "declared_masks_grain": specs["case_designs.csv"]["grain"],
              "declared_masks_unit": specs["case_designs.csv"]["unit"],
              "declared_geometry_unit": specs["retention_geometry_cases.csv"]["unit"],
              "column_coverage": {name: set(spec["numeric"]) | set(spec["labels"]) == set(spec["columns"])
                                  for name, spec in specs.items()}}
    save("table_metadata.json", result)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"comparator_expected_outcomes": comparator_checks()}), flush=True)
    print(json.dumps({"output_portability_exit_codes": output_portability()}), flush=True)
    print(json.dumps({"ci_summary_guard": ci_summary_guard()}), flush=True)
    table_metadata()
