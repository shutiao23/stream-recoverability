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
        help="Launch v3 Stage 1 only. This is expensive and still model_selection_only.",
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
        "submission_gate": submission_gate(PROJECT_ROOT),
        "formal_results_generated": False,
        "note": (
            "Stage 2/3, roster freeze, formal suites, and evaluate-once remain "
            "blocked until their artifacts exist. This orchestrator does not "
            "fabricate them."
        ),
    }
    write_json(PROJECT_ROOT / "results/audits/p0_pipeline_report.json", report)
    print(json.dumps({"failed_steps": [step for step in steps if step["returncode"]]}, indent=2))


if __name__ == "__main__":
    main()
