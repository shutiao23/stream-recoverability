#!/usr/bin/env python3
"""Fail-closed WRR submission gate. Passing requires complete P0 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from stream_recoverability.governance import submission_gate, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_INPUTS = {
    "roster": "results/validation_funnel/published_v2/finalized_model_roster.json",
    "primary-registry": "results/frozen/published_v2/suite_registry.json",
    "primary-aggregate-manifest": "results/frozen/published_v2/top_manifest.json",
    "analysis-manifest": "results/analysis/analysis_manifest.json",
    "confirmatory-data-manifest": "data_versions/external_upper_middle_chattahoochee_v1/provenance_manifest.json",
    "confirmatory-run-manifest": "results/confirmatory/external_upper_middle_chattahoochee_v1/external_confirmation/completion_manifest.json",
    "once-lock": "data_versions/.external_upper_middle_chattahoochee_v1.confirmatory-evaluation-once.lock.json",
    "rights-audit": "results/audits/restricted_hosting_audit.json",
    "reproduction-report": "results/audits/reproduction_report_acceptance_revision.json",
    "editor-exception-approval": "metadata/editor_data_exception_approval.json",
    "author-metadata": "metadata/submission_author_metadata.json",
    "reviewer-data-upload": "metadata/gems_reviewer_data_upload.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/audits/submission_gate.json",
    )
    parser.add_argument(
        "--allow-no-go",
        action="store_true",
        help="Write the report and exit 0 even when the gate is no-go.",
    )
    for option, relative in CANONICAL_INPUTS.items():
        parser.add_argument(
            f"--{option}", type=Path, default=PROJECT_ROOT / relative
        )
    args = parser.parse_args()
    report = submission_gate(
        PROJECT_ROOT,
        roster=args.roster,
        primary_registry=args.primary_registry,
        primary_aggregate_manifest=args.primary_aggregate_manifest,
        analysis_manifest=args.analysis_manifest,
        confirmatory_data_manifest=args.confirmatory_data_manifest,
        confirmatory_run_manifest=args.confirmatory_run_manifest,
        once_lock=args.once_lock,
        rights_audit=args.rights_audit,
        reproduction_report=args.reproduction_report,
        editor_exception_approval=args.editor_exception_approval,
        author_metadata=args.author_metadata,
        reviewer_data_upload=args.reviewer_data_upload,
    )
    write_json(args.output, report)
    print(args.output)
    print(report["decision"])
    if report["blockers"]:
        for item in report["blockers"]:
            print(f"- {item}")
    if not report["passed"] and not args.allow_no_go:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
