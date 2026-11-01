"""Regression tests for the final-release freshness guard.

The test builds a tiny temporary candidate. It does not touch the real archive,
the real PDFs or the real acceptance record.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_release():
    spec = importlib.util.spec_from_file_location("final_release_980_test", ROOT / "scripts/980_final_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_package(module, paths, tex_override=None):
    tex_override = tex_override or {}
    payload = {
        "paper/wrr_tr/article.tex": tex_override.get("article", paths["article_tex"].read_bytes()),
        "paper/wrr_tr/article.pdf": paths["article_pdf"].read_bytes(),
        "paper/wrr_tr/supporting.tex": paths["supporting_tex"].read_bytes(),
        "paper/wrr_tr/supporting.pdf": paths["supporting_pdf"].read_bytes(),
        "key_result.txt": paths["key"].read_bytes(),
    }
    receipt = {
        "abstract_words": 100,
        "key_points": ["point"],
        "manuscripts": {
            "article": {"tex_sha256": hashlib.sha256(payload["paper/wrr_tr/article.tex"]).hexdigest(),
                        "pdf_sha256": sha(paths["article_pdf"]), "pdf_pages": 1},
            "supporting": {"tex_sha256": sha(paths["supporting_tex"]),
                           "pdf_sha256": sha(paths["supporting_pdf"]), "pdf_pages": 1},
        },
    }
    payload["RELEASE_RECEIPT.json"] = json.dumps(receipt).encode()
    manifest_text = "".join(
        hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in sorted(payload.items())
    ).encode()
    payload["CONTENT_MANIFEST.sha256"] = manifest_text
    module.DEST.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(module.DEST, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in payload.items():
            zipped.writestr(name, data)
    manifest = {
        "package": str(module.DEST.relative_to(module.ROOT)),
        "package_sha256": sha(module.DEST),
        "package_bytes": module.DEST.stat().st_size,
        "members": len(payload),
        "scientific_members": len(payload) - 2,
        "content_manifest_sha256": hashlib.sha256(manifest_text).hexdigest(),
        "release_receipt_sha256": hashlib.sha256(payload["RELEASE_RECEIPT.json"]).hexdigest(),
    }
    module.EXTERNAL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest, receipt


def write_verification(module, manifest, receipt):
    verification = {
        "status": "passed",
        "package_sha256": manifest["package_sha256"],
        "external_manifest_sha256": sha(module.EXTERNAL_MANIFEST),
        "member_check": {
            "status": "passed",
            "members": manifest["members"],
            "manifest_sha256": manifest["content_manifest_sha256"],
            "workspace_byte_comparisons": manifest["scientific_members"],
        },
        "manuscripts": {
            label: {
                "tex_sha256": record["tex_sha256"],
                "pdf_sha256": record["pdf_sha256"],
                "pdf_text_matches_rebuild": True,
            }
            for label, record in receipt["manuscripts"].items()
        },
        "extracted_transcription": {"abstract_words": receipt["abstract_words"]},
        "cover_letter": {"title_matches": True, "controlled_gap_scope": True},
        "scientific_text_checks": {
            "si_title_and_1981_2025_row": True,
            "controlled_gap_scope_in_abstract": True,
            "ratio_interpretation_in_article": True,
            "station_group_heterogeneity_recomputed": True,
            "conditional_group_intervals_in_methods": True,
            "central_contribution_stated": True,
            "absolute_endpoint_change_label": True,
            "fixed_reference_year_set_defined": True,
            "si_geometry_derivation": True,
            "si_calendar_extension": True,
        },
        "not_tested": [],
    }
    (module.OUT / "package_verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    return verification


def write_tests(module):
    junit = module.OUT / "targeted_tests.xml"
    junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"></testsuite>')
    summary = {
        "exit_code": 0,
        "passed": 1,
        "tests": 1,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "scope": "test fixture",
        "files": module.TARGETED_TEST_FILES,
        "junit": "targeted_tests.xml",
        "junit_sha256": sha(junit),
        "command": "pytest fixture",
        "interpreter": sys.executable,
        "source_identity": module.release_provenance.source_identity(),
    }
    (module.OUT / "targeted_tests_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def write_local_ci(module):
    ruff = module.OUT / "ruff_current.json"
    ruff.write_text("[]\n")
    full = module.OUT / "full_pytest.xml"
    full.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"></testsuite>')
    evidence_names = [
        "evidence_snapshot_inventory.json",
        "restricted_hosting_audit_inventory.json",
        "submission_gate_inventory_only.json",
    ]
    for name in evidence_names:
        (module.OUT / name).write_text(json.dumps({"decision": "inventory_only"}) + "\n")
    identity = module.release_provenance.source_identity()
    full_summary = {
        "exit_code": 0, "tests": 1, "passed": 1, "failures": 0, "errors": 0, "skipped": 0,
        "junit": "full_pytest.xml", "junit_sha256": sha(full),
        "command": "pytest --junitxml full_pytest.xml", "interpreter": sys.executable,
        "source_identity": identity,
    }
    summary = {
        "status": "passed",
        "source_check": {
            "command": "ruff check --select E4,E7,E9,F src", "exit_code": 0, "findings": 0,
            "report": "ruff_current.json", "report_sha256": sha(ruff),
        },
        "full_pytest": full_summary,
        "evidence_gates": {
            "decision": "inventory_only",
            "outputs": {name: sha(module.OUT / name) for name in evidence_names},
        },
    }
    (module.OUT / "ci_local_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def write_delivery(module, manifest):
    delivery = {
        "status": "passed",
        "archive_sha256": manifest["package_sha256"],
        "scope": "test fixture",
        "extracted_package_checks": {
            "transcription_and_pdf_compile": True,
            "source_calibration_frozen_replay": True,
            "time_support_frozen_replay": True,
            "current_observation_replay": True,
        },
    }
    (module.OUT / "package_delivery_check.json").write_text(json.dumps(delivery, indent=2) + "\n")
    return delivery


@pytest.fixture()
def fixture(tmp_path, monkeypatch):
    module = load_release()
    module.ROOT = tmp_path
    module.DEST = tmp_path / "dist/candidate.zip"
    module.EXTERNAL_MANIFEST = tmp_path / "dist/candidate.manifest.json"
    module.OUT = tmp_path / "results/release"
    module.REVIEW = tmp_path / "review"
    module.TARGETED_TEST_FILES = ["tests/test_fixture.py"]
    module.MANUSCRIPTS = {
        "article": {"tex": "paper/wrr_tr/article.tex", "pdf": "paper/wrr_tr/article.pdf"},
        "supporting": {"tex": "paper/wrr_tr/supporting.tex", "pdf": "paper/wrr_tr/supporting.pdf"},
    }
    module.OUT.mkdir(parents=True, exist_ok=True)
    module.REVIEW.mkdir(parents=True, exist_ok=True)
    (module.ROOT / "paper/wrr_tr").mkdir(parents=True, exist_ok=True)
    paths = {
        "article_tex": module.ROOT / "paper/wrr_tr/article.tex",
        "article_pdf": module.ROOT / "paper/wrr_tr/article.pdf",
        "supporting_tex": module.ROOT / "paper/wrr_tr/supporting.tex",
        "supporting_pdf": module.ROOT / "paper/wrr_tr/supporting.pdf",
        "key": module.ROOT / "key_result.txt",
    }
    paths["article_tex"].write_text("article v1\n")
    paths["article_pdf"].write_bytes(b"article pdf v1")
    paths["supporting_tex"].write_text("supporting v1\n")
    paths["supporting_pdf"].write_bytes(b"supporting pdf v1")
    paths["key"].write_text("key v1\n")
    (module.REVIEW / "REVISION_COMPLETION_20261101_R3_ZH.md").write_text("completion\n")
    monkeypatch.setattr(module, "pdf_pages", lambda path: 1)
    monkeypatch.setattr(module, "abstract_words", lambda: 100)
    monkeypatch.setattr(module, "key_points", lambda: ["point"])
    monkeypatch.setattr(module, "git_state", lambda: {"head": "fixture", "worktree": {}})
    manifest, receipt = build_package(module, paths)
    write_verification(module, manifest, receipt)
    write_tests(module)
    write_delivery(module, manifest)
    (module.OUT / "extension_replay.json").write_text(json.dumps({
        "status": "passed",
        "archive_sha256": manifest["package_sha256"],
        "archives": 1623,
        "geometry_rows": 8115,
        "max_numeric_difference": 0.0,
        "tolerance": 1e-12,
    }, indent=2) + "\n")
    write_local_ci(module)
    return module, paths


def test_accepts_matching_fixture(fixture):
    module, _ = fixture
    module.accept(None)
    acceptance = json.loads((module.OUT / "acceptance.json").read_text())
    assert acceptance["status"] == "complete"
    assert acceptance["package"]["sha256"] == sha(module.DEST)


def test_tex_edit_after_verification_is_rejected(fixture):
    module, paths = fixture
    paths["article_tex"].write_text("article v2\n")
    with pytest.raises(module.ReleaseFailure, match="Packaged/workspace bytes differ"):
        module.accept(None)


def test_pdf_edit_after_verification_is_rejected(fixture):
    module, paths = fixture
    paths["article_pdf"].write_bytes(b"article pdf v2")
    with pytest.raises(module.ReleaseFailure, match="Packaged/workspace bytes differ"):
        module.accept(None)


def test_key_result_edit_after_verification_is_rejected(fixture):
    module, paths = fixture
    paths["key"].write_text("key v2\n")
    with pytest.raises(module.ReleaseFailure, match="Packaged/workspace bytes differ"):
        module.accept(None)


def test_stale_verification_package_hash_is_rejected(fixture):
    module, _ = fixture
    path = module.OUT / "package_verification.json"
    verification = json.loads(path.read_text())
    verification["package_sha256"] = "0" * 64
    path.write_text(json.dumps(verification, indent=2) + "\n")
    with pytest.raises(module.ReleaseFailure, match="Verification package hash differs"):
        module.accept(None)


def test_stale_verification_tex_hash_is_rejected(fixture):
    module, _ = fixture
    path = module.OUT / "package_verification.json"
    verification = json.loads(path.read_text())
    verification["manuscripts"]["article"]["tex_sha256"] = "0" * 64
    path.write_text(json.dumps(verification, indent=2) + "\n")
    with pytest.raises(module.ReleaseFailure, match="TeX changed after verification"):
        module.accept(None)


def test_rebuilt_package_with_old_verification_is_rejected(fixture):
    module, paths = fixture
    paths["article_tex"].write_text("article v2\n")
    manifest, _ = build_package(module, paths)
    # The verification report still names the old package hash.
    with pytest.raises(module.ReleaseFailure, match="Verification package hash differs"):
        module.accept(None)


def mutate_ci(module, mutator):
    path = module.OUT / "ci_local_summary.json"
    data = json.loads(path.read_text())
    mutator(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def test_zero_tests_and_nonzero_ci_exit_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"].update(tests=0, passed=0, exit_code=5)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="exit code"):
        module.accept(None)


def test_all_skipped_ci_summary_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"].update(tests=1, passed=0, skipped=1)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="no executed passing tests"):
        module.accept(None)


def test_contradictory_ci_counts_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"].update(tests=10, passed=100)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="counts are inconsistent"):
        module.accept(None)


def test_ci_junit_hash_mismatch_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"]["junit_sha256"] = "0" * 64
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="JUnit hash differs"):
        module.accept(None)


def test_ci_source_tree_mismatch_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"]["source_identity"]["src_tree_sha256"] = "0" * 64
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="not run on the current source tree"):
        module.accept(None)


def test_targeted_counts_inconsistent_rejected(fixture):
    module, _ = fixture
    path = module.OUT / "targeted_tests_summary.json"
    data = json.loads(path.read_text())
    data.update(tests=10, passed=100)
    path.write_text(json.dumps(data, indent=2) + "\n")
    with pytest.raises(module.ReleaseFailure, match="counts are inconsistent"):
        module.accept(None)


def test_full_pytest_failure_count_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"].update(tests=2, passed=1, failures=1, errors=0, skipped=0)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="reports test failures"):
        module.accept(None)


def test_full_pytest_error_count_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"].update(tests=2, passed=1, failures=0, errors=1, skipped=0)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="reports test errors"):
        module.accept(None)


def test_full_pytest_junit_count_mismatch_rejected(fixture):
    module, _ = fixture
    def mutate(data):
        data["full_pytest"].update(tests=999, passed=999, failures=0, errors=0, skipped=0)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="JUnit counts differ"):
        module.accept(None)


def test_full_pytest_failure_xml_with_normal_summary_rejected(fixture):
    module, _ = fixture
    full = module.OUT / "full_pytest.xml"
    full.write_text('<testsuite tests="1" failures="1" errors="0" skipped="0"></testsuite>')
    def mutate(data):
        data["full_pytest"]["junit_sha256"] = sha(full)
    mutate_ci(module, mutate)
    with pytest.raises(module.ReleaseFailure, match="JUnit counts differ"):
        module.accept(None)


def test_targeted_failure_count_rejected(fixture):
    module, _ = fixture
    path = module.OUT / "targeted_tests_summary.json"
    data = json.loads(path.read_text())
    data.update(tests=2, passed=1, failures=1, errors=0, skipped=0)
    path.write_text(json.dumps(data, indent=2) + "\n")
    with pytest.raises(module.ReleaseFailure, match="reports test failures"):
        module.accept(None)
