#!/usr/bin/env python3
"""Read-only checks of the second 2026-11-01 release; mutate tiny fixtures only."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/wrr_r2_review_20261101"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def junit(path, status):
    failure, error = int(status == "failure"), int(status == "error")
    suite = ET.Element("testsuite", tests="2", failures=str(failure), errors=str(error), skipped="0")
    ET.SubElement(suite, "testcase", classname="tests.test_fixture", name="test_one", time="0.001")
    case = ET.SubElement(suite, "testcase", classname="tests.test_fixture", name="test_two", time="0.001")
    if failure or error:
        ET.SubElement(case, status, message="reviewer injected outcome")
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return {"tests": 2, "passed": 2 - failure - error, "failures": failure, "errors": error, "skipped": 0}


def bind_package(module, tests):
    with zipfile.ZipFile(module.DEST) as zipped:
        payload = {name: zipped.read(name) for name in zipped.namelist() if name != "CONTENT_MANIFEST.sha256"}
    names = ["targeted_tests_summary.json", "targeted_tests.xml", "ci_local_summary.json", "full_pytest.xml",
             "ruff_current.json", "evidence_snapshot_inventory.json", "restricted_hosting_audit_inventory.json",
             "submission_gate_inventory_only.json"]
    for name in names:
        path = module.OUT / name
        payload[str(path.relative_to(module.ROOT))] = path.read_bytes()
    content = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n"
                      for name, data in sorted(payload.items())).encode()
    payload["CONTENT_MANIFEST.sha256"] = content
    with zipfile.ZipFile(module.DEST, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in payload.items():
            zipped.writestr(name, data)
    manifest = json.loads(module.EXTERNAL_MANIFEST.read_text())
    manifest.update(package_sha256=tests.sha(module.DEST), package_bytes=module.DEST.stat().st_size,
                    members=len(payload), scientific_members=len(payload) - 2,
                    content_manifest_sha256=hashlib.sha256(content).hexdigest())
    module.EXTERNAL_MANIFEST.write_text(json.dumps(manifest))
    tests.write_verification(module, manifest, json.loads(payload["RELEASE_RECEIPT.json"]))
    tests.write_delivery(module, manifest)
    path = module.OUT / "extension_replay.json"
    report = json.loads(path.read_text())
    report["archive_sha256"] = manifest["package_sha256"]
    path.write_text(json.dumps(report))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tests = load_module("r2_freshness_test_fixture", ROOT / "tests/test_final_release_freshness.py")
    modes = ["baseline", "full_positive_failure", "full_positive_error", "full_summary_xml_count_mismatch",
             "full_failed_xml_clean_summary", "targeted_positive_failure", "targeted_failed_xml_clean_summary",
             "old_zero_execution", "old_all_skipped", "old_inconsistent_counts", "old_wrong_junit_hash",
             "old_wrong_source_tree"]
    results = []
    for mode in modes:
        with tempfile.TemporaryDirectory(prefix="wrr_r2_gate_") as folder:
            monkeypatch = pytest.MonkeyPatch()
            try:
                module, _ = tests.fixture.__wrapped__(Path(folder), monkeypatch)
                full_path = module.OUT / "full_pytest.xml"
                targeted_path = module.OUT / "targeted_tests.xml"
                full_outcome = "failure" if mode in {"full_positive_failure", "full_failed_xml_clean_summary"} else (
                    "error" if mode == "full_positive_error" else "passed")
                targeted_outcome = "failure" if mode in {"targeted_positive_failure", "targeted_failed_xml_clean_summary"} else "passed"
                full_counts = junit(full_path, full_outcome)
                targeted_counts = junit(targeted_path, targeted_outcome)
                ci_path = module.OUT / "ci_local_summary.json"
                ci = json.loads(ci_path.read_text())
                ci["full_pytest"].update(full_counts, exit_code=0, junit_sha256=tests.sha(full_path))
                target_summary_path = module.OUT / "targeted_tests_summary.json"
                target = json.loads(target_summary_path.read_text())
                target.update(targeted_counts, exit_code=0, junit_sha256=tests.sha(targeted_path))
                if mode == "full_summary_xml_count_mismatch":
                    ci["full_pytest"].update(tests=999, passed=999)
                elif mode == "full_failed_xml_clean_summary":
                    ci["full_pytest"].update(passed=2, failures=0)
                elif mode == "targeted_failed_xml_clean_summary":
                    target.update(passed=2, failures=0)
                elif mode == "old_zero_execution":
                    ci["full_pytest"].update(tests=0, passed=0, exit_code=5)
                elif mode == "old_all_skipped":
                    ci["full_pytest"].update(passed=0, skipped=2)
                elif mode == "old_inconsistent_counts":
                    ci["full_pytest"].update(tests=10, passed=100)
                elif mode == "old_wrong_junit_hash":
                    ci["full_pytest"]["junit_sha256"] = "0" * 64
                elif mode == "old_wrong_source_tree":
                    ci["full_pytest"]["source_identity"]["src_tree_sha256"] = "0" * 64
                ci_path.write_text(json.dumps(ci))
                target_summary_path.write_text(json.dumps(target))
                bind_package(module, tests)
                try:
                    with redirect_stdout(io.StringIO()):
                        module.accept(None)
                    status, reason = "accepted", None
                except module.ReleaseFailure as error:
                    status, reason = "rejected", str(error)
                fields = ["exit_code", "tests", "passed", "failures", "errors", "skipped"]
                results.append({"case": mode, "status": status, "reason": reason,
                                "full_junit_counts": full_counts,
                                "full_summary_counts": {key: ci["full_pytest"][key] for key in fields},
                                "targeted_junit_counts": targeted_counts,
                                "targeted_summary_counts": {key: target[key] for key in fields}})
            finally:
                monkeypatch.undo()
    record = {"probes": results,
              "scope": "Actual 980.accept on tiny temporary fixtures; summaries and JUnit are members of the fixture ZIP and package/verification hashes are synchronized. This tests field/content validation; the real candidate and receipts are unchanged, and no current scientific/test result is alleged to be false."}
    (OUT / "acceptance_probes.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({item["case"]: item["status"] for item in results}))


if __name__ == "__main__":
    main()
