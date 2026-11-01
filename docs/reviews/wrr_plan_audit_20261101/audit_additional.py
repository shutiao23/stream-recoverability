#!/usr/bin/env python3
"""Read-only follow-up checks for the W0-W4 plan and completion report.

Only audit outputs are written. No manuscript, production result, release
receipt, source implementation or GitHub setting is modified.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/wrr_plan_audit_20261101"


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def run_json(command):
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if process.returncode:
        raise RuntimeError(f"Read-only command failed: {command}: {process.stderr[-1000:]}")
    return json.loads(process.stdout)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    previous = json.loads((ROOT / "results/wrr_revision_review_20261101/review_scope.json").read_text())
    input_matches = {name: digest(ROOT / name) == expected
                     for name, expected in previous["inputs_sha256"].items()}
    package = ROOT / "dist/wrr_final_candidate_20261031_r2.zip"

    data = ROOT / "results/wrr_final_revision_20261031"
    summary = pd.read_csv(data / "retention_family_summary.csv")
    scope = json.loads((data / "scope.json").read_text())
    expectations = [
        {"family": row.family,
         "csv_expected_count": float(row.sign_disagreement_count_or_expectation),
         "scope_integer_count": scope["sign_disagreement_counts"][row.family]["uniform_exact"]}
        for row in summary.loc[summary.scheme.eq("uniform_exact")].itertuples()
    ]

    spec = importlib.util.spec_from_file_location(
        "wrr_plan_audit_test", ROOT / "tests/test_stanford_revision.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_read = module.pd.read_csv
    changes = []

    def altered_read(path, *args, **kwargs):
        frame = original_read(path, *args, **kwargs)
        if Path(path).name == "retention_family_summary.csv":
            mask = frame.family.eq("crossed") & frame.scheme.eq("warm90")
            old = float(frame.loc[mask, "estimate_rmse"].iloc[0])
            frame.loc[mask, "estimate_rmse"] += 1e-6
            changes.append({"before": old, "after": float(frame.loc[mask, "estimate_rmse"].iloc[0])})
        return frame

    module.test_summaries_recompute_from_cases()
    with patch.object(module.pd, "read_csv", side_effect=altered_read):
        try:
            module.test_summaries_recompute_from_cases()
            mutation_status = "passed"
        except AssertionError:
            mutation_status = "rejected"

    lint = subprocess.run(
        ["ruff", "check", "--select", "E4,E7,E9,F", "src", "--output-format", "json"],
        cwd=ROOT, text=True, capture_output=True)
    lint_rows = json.loads(lint.stdout)
    (OUT / "ruff_current.json").write_text(json.dumps(lint_rows, indent=2, allow_nan=False) + "\n")

    repo = "repos/shutiao23/stream-recoverability"
    current_runs = run_json(["gh", "api", f"{repo}/actions/runs?head_sha={head}&per_page=30"])
    parent = "2986c0b0a3305adf088ace8c6c5f051a112825e2"
    parent_runs = run_json(["gh", "api", f"{repo}/actions/runs?head_sha={parent}&per_page=30"])
    workflow = run_json(["gh", "api", f"{repo}/actions/workflows/ci.yml"])
    main_ref = run_json(["gh", "api", f"{repo}/git/ref/heads/main"])

    def brief_runs(response):
        return {"total_count": response["total_count"],
                "runs": [{key: value.get(key) for key in
                          ["id", "head_sha", "event", "status", "conclusion", "html_url"]}
                         for value in response["workflow_runs"]]}

    old_acceptance = json.loads((ROOT / "results/final_release_20261031/acceptance.json").read_text())
    current_acceptance = json.loads((ROOT / "results/final_release_20261031_r2/acceptance.json").read_text())
    readme = (ROOT / "README.md").read_text()
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "head": head,
        "reused_evidence_inputs_match": input_matches,
        "candidate_sha256": digest(package),
        "candidate_matches_previous_evidence": digest(package) == previous["version"],
        "sign_expectation_truncation": expectations,
        "arithmetic_test_tolerance_probe": {
            "test": "test_summaries_recompute_from_cases",
            "baseline": "passed", "mutation_status": mutation_status,
            "in_memory_changes": changes,
            "declared_atol": 1e-12,
            "numpy_default_rtol": 1e-5,
            "strict_atol_rejects": not bool(np.isclose(changes[0]["before"], changes[0]["after"], rtol=0, atol=1e-12)),
            "scope": "Single-test in-memory fault injection; not a bypass of the full release pipeline.",
        },
        "source_check": {"command": "ruff check --select E4,E7,E9,F src",
                         "returncode": lint.returncode, "errors": len(lint_rows),
                         "rule_counts": dict(Counter(item["code"] for item in lint_rows)),
                         "ruff_version": subprocess.check_output(["ruff", "--version"], text=True).strip()},
        "ci": {"current_commit": brief_runs(current_runs), "previous_commit": brief_runs(parent_runs),
               "workflow_state": workflow["state"], "main_sha": main_ref["object"]["sha"],
               "writes_performed": False},
        "readme_entrypoint": {
            "labels_old_acceptance_current": "[Current acceptance record](results/final_release_20261031/acceptance.json)" in readme,
            "linked_package_sha256": old_acceptance["package"]["sha256"],
            "r2_package_sha256": current_acceptance["package"]["sha256"],
            "old_article_pages": old_acceptance["manuscripts"]["article"]["pdf_pages"],
            "old_abstract_words": old_acceptance["manuscripts"]["article"]["abstract_words"],
        },
        "production_files_changed": False,
    }
    (OUT / "additional_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"report": str(OUT / "additional_audit.json"),
                      "prior_evidence_identity_matches": all(input_matches.values()),
                      "lint_errors": len(lint_rows), "tolerance_fault_status": mutation_status,
                      "current_ci_runs": current_runs["total_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
