#!/usr/bin/env python3
"""Orchestrate P0 protocol work that can run without inventing results.

This script never opens confirmatory performance, never freezes a roster from
stale v2 artifacts, and never writes RESULTS_PENDING numbers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from stream_recoverability.governance import (
    evidence_snapshot,
    submission_gate,
    write_json,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_GATE_INPUTS = {
    "roster": PROJECT_ROOT / "results/validation_funnel/published_v2/finalized_model_roster.json",
    "primary_registry": PROJECT_ROOT / "results/frozen/published_v2/suite_registry.json",
    "primary_aggregate_manifest": PROJECT_ROOT / "results/frozen/published_v2/top_manifest.json",
    "analysis_manifest": PROJECT_ROOT / "results/analysis/analysis_manifest.json",
    "confirmatory_data_manifest": PROJECT_ROOT / "data_versions/external_upper_middle_chattahoochee_v1/provenance_manifest.json",
    "confirmatory_run_manifest": PROJECT_ROOT / "results/confirmatory/external_upper_middle_chattahoochee_v1/external_confirmation/completion_manifest.json",
    "once_lock": PROJECT_ROOT / "data_versions/.external_upper_middle_chattahoochee_v1.confirmatory-evaluation-once.lock.json",
    "rights_audit": PROJECT_ROOT / "results/audits/restricted_hosting_audit.json",
    "reproduction_report": PROJECT_ROOT / "results/audits/reproduction_report_acceptance_revision.json",
    "editor_exception_approval": PROJECT_ROOT / "metadata/editor_data_exception_approval.json",
    "author_metadata": PROJECT_ROOT / "metadata/submission_author_metadata.json",
    "reviewer_data_upload": PROJECT_ROOT / "metadata/gems_reviewer_data_upload.json",
}


def _run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    return {"command": command, "returncode": completed.returncode}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-data-versions",
        action="store_true",
        help="Build published_v2 if processed daily_long exists and the directory is absent.",
    )
    parser.add_argument(
        "--with-stage1",
        action="store_true",
        help="Launch v4 Stage 1 only. This is expensive and still model_selection_only.",
    )
    args = parser.parse_args()
    steps = [
        _run([sys.executable, "scripts/25_build_evidence_snapshot.py"]),
        _run([sys.executable, "scripts/26_audit_restricted_hosting.py"]),
        _run(
            [
                sys.executable,
                "scripts/27_submission_gate.py",
                "--allow-no-go",
            ]
        ),
    ]
    long_path = PROJECT_ROOT / "data/processed/daily_long.parquet"
    version_dir = PROJECT_ROOT / "data_versions/published_v2"
    if args.with_data_versions and long_path.is_file() and not version_dir.exists():
        steps.append(
            _run(
                [
                    sys.executable,
                    "scripts/14_build_data_versions.py",
                    "--version",
                    "published_v2",
                    "--version",
                    "no_s2_suspect_v2",
                    "--version",
                    "b1_no_level_v2",
                    "--version",
                    "b1_shift_sensitivity_v2",
                ]
            )
        )
    if args.with_stage1:
        steps.append(
            _run(
                [
                    sys.executable,
                    "scripts/15_run_validation_funnel.py",
                    "run",
                    "--stage",
                    "traditional",
                    "--data-version",
                    "published_v2",
                ]
            )
        )
    report = {
        "steps": steps,
        "evidence_snapshot": evidence_snapshot(PROJECT_ROOT),
        "submission_gate": submission_gate(PROJECT_ROOT, **CANONICAL_GATE_INPUTS),
        "formal_results_generated": False,
        "note": (
            "Stage 2/3, roster freeze, formal suites, and evaluate-once remain "
            "blocked until their artifacts exist. This orchestrator does not "
            "fabricate them."
        ),
    }
    write_json(PROJECT_ROOT / "results/audits/p0_pipeline_report.json", report)
    failed_steps = [step for step in steps if step["returncode"]]
    print(json.dumps({"failed_steps": failed_steps}, indent=2))
    if failed_steps:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
