"""A previous successful build must not certify a changed manuscript or ZIP."""
import importlib.util
import json
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("completion_audit", ROOT / "scripts/538_completion_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def candidate(tmp_path):
    paths = audit.package_evidence(tmp_path)["compared_paths"]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name + " original").encode())
    archive = tmp_path / "dist/wrr_review_response_candidate.zip"
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as z:
        for name in paths:
            z.write(tmp_path / name, name)
    reports = tmp_path / "results/wrr_review_response_20261027/audit"
    reports.mkdir(parents=True)
    for i, numpy in enumerate(["1.26.4", "2.2.6"]):
        (reports / f"env_{i}_package_check.json").write_text(json.dumps({
            "status": "passed", "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "environment": {"numpy": numpy}, "checks": {"build": "passed"},
        }))
    return archive

def test_checks_match_current_named_files_and_archive(tmp_path):
    candidate(tmp_path)
    result = audit.package_evidence(tmp_path)
    assert result["status"] == "current_candidate_checked"
    assert result["workspace_mismatches"] == []
    assert result["distinct_environments"] == 2

def test_changed_manuscript_invalidates_previous_success(tmp_path):
    candidate(tmp_path)
    (tmp_path / "paper/wrr_tr/review_completion_supporting.tex").write_text("changed")
    result = audit.package_evidence(tmp_path)
    assert result["status"] == "stale_or_unchecked_candidate"
    assert result["workspace_mismatches"] == ["paper/wrr_tr/review_completion_supporting.tex"]
    assert result["distinct_environments"] == 2

def test_changed_archive_cannot_reuse_old_reports(tmp_path):
    archive = candidate(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("new_summary.txt", "additional result")
    result = audit.package_evidence(tmp_path)
    assert result["status"] == "stale_or_unchecked_candidate"
    assert result["matching_reports"] == []
