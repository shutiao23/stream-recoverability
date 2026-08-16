#!/usr/bin/env python3
"""Run the frozen external confirmation exactly once from its finalized roster."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.data.confirmatory import CONFIRMATORY_DATA_VERSION
from stream_recoverability.experiments.contracts import DEFAULT_DESIGN_PATH
from stream_recoverability.experiments.external_confirmation import (
    confirmatory_once_lock_path,
    preflight_confirmatory_evaluation,
    run_confirmatory_evaluation,
    run_confirmatory_feasibility,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=(PROJECT_ROOT / "data_versions" / CONFIRMATORY_DATA_VERSION),
        help="Already-built immutable external data directory; never downloaded here.",
    )
    parser.add_argument(
        "--finalized-model-roster",
        type=Path,
        required=True,
        help="Hash-verified finalized_model_roster_v1 produced from validation only.",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_DESIGN_PATH,
    )
    parser.add_argument(
        "--study-manifest",
        type=Path,
        default=PROJECT_ROOT / "study_manifest.yaml",
    )
    parser.add_argument(
        "--experiment-config",
        type=Path,
        default=PROJECT_ROOT / "configs/experiments.yaml",
    )
    parser.add_argument(
        "--selection-data-version-manifest",
        type=Path,
        default=PROJECT_ROOT / "data_versions/published_v1/version_manifest.json",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=PROJECT_ROOT / "results/confirmatory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional exact output. Default is the canonical version/design path.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate all gates without building masks, fitting models, or locking.",
    )
    mode.add_argument(
        "--feasibility-only",
        action="store_true",
        help=(
            "Preflight plus construct all 60 masks and coverage/truth checks. "
            "Does not train, score, or create a once-lock."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    inputs = preflight_confirmatory_evaluation(
        data_root=args.data_root,
        finalized_model_roster_path=args.finalized_model_roster,
        design_path=args.design,
        study_manifest_path=args.study_manifest,
        experiment_config_path=args.experiment_config,
        selection_data_version_manifest_path=(args.selection_data_version_manifest),
    )
    canonical_root = args.results_root / inputs.evidence_contract["data_version"]
    design_hash = inputs.evidence_contract["design_hash"]
    output = args.output_dir or (
        canonical_root / design_hash / "external_confirmation"
    )
    lock = confirmatory_once_lock_path(inputs.data_root)
    if args.feasibility_only:
        feasibility_output = args.output_dir or (
            canonical_root / design_hash / "feasibility"
        )
        result = run_confirmatory_feasibility(
            data_root=args.data_root,
            finalized_model_roster_path=args.finalized_model_roster,
            output_dir=feasibility_output,
            design_path=args.design,
            study_manifest_path=args.study_manifest,
            experiment_config_path=args.experiment_config,
            selection_data_version_manifest_path=(
                args.selection_data_version_manifest
            ),
        )
        print(
            json.dumps(
                {
                    "status": result.report["status"],
                    "performance_metrics_computed": False,
                    "models_trained": False,
                    "once_lock_created": False,
                    "scenario_count": result.report["scenario_count"],
                    "output_dir": str(result.output_dir),
                    "data_version": result.report["data_version"],
                    "design_hash": result.report["design_hash"],
                    "finalized_model_roster_sha256": result.report["roster_sha256"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight_passed",
                    "performance_metrics_computed": False,
                    "models": list(inputs.selected_models),
                    "training_seeds": list(inputs.training_seeds),
                    "data_version": inputs.evidence_contract["data_version"],
                    "design_hash": inputs.evidence_contract["design_hash"],
                    "evaluation_split": inputs.evidence_contract["evaluation_split"],
                    "finalized_model_roster_sha256": (inputs.roster.manifest_sha256),
                    "data_version_manifest_sha256": (
                        inputs.data_manifest_identity["manifest_sha256"]
                    ),
                    "canonical_output_dir": str(output),
                    "once_lock": str(lock),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    manifest = run_confirmatory_evaluation(
        data_root=args.data_root,
        finalized_model_roster_path=args.finalized_model_roster,
        output_dir=output,
        design_path=args.design,
        study_manifest_path=args.study_manifest,
        experiment_config_path=args.experiment_config,
        selection_data_version_manifest_path=(args.selection_data_version_manifest),
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "complete": manifest["complete"],
                "output_dir": str(output),
                "once_lock": str(lock),
                "data_version": manifest["data_version"],
                "design_hash": manifest["design_hash"],
                "evaluation_split": manifest["evaluation_split"],
                "evidence_role": manifest["evidence_role"],
                "formal_evidence": manifest["formal_evidence"],
                "completed_run_unit_count": manifest["completed_run_unit_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
