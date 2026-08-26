#!/usr/bin/env python3
"""Audit or create-once the open-result-bound T2/T7 sealed model freeze."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.sealed_evaluation_readiness import (
    DEFAULT_AGGREGATION,
    DEFAULT_ANALYSIS_CODE,
    DEFAULT_DESIGN,
    DEFAULT_MODEL_FREEZE,
    DEFAULT_MODEL_FREEZE_READINESS,
    DEFAULT_MODEL_ROSTER,
    DEFAULT_OPERATOR_PREDICTOR,
    DEFAULT_POST_T2_INPUT_BINDING,
    DEFAULT_PRE_SCORE_FREEZE,
    DEFAULT_V4_WORKLOAD,
    build_model_freeze_readiness,
    create_model_freeze_manifest,
    write_readiness_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", type=Path, default=DEFAULT_V4_WORKLOAD)
    parser.add_argument(
        "--pre-score-freeze", type=Path, default=DEFAULT_PRE_SCORE_FREEZE
    )
    parser.add_argument(
        "--open-aggregation", type=Path, default=DEFAULT_AGGREGATION
    )
    parser.add_argument(
        "--post-t2-input-binding",
        type=Path,
        default=DEFAULT_POST_T2_INPUT_BINDING,
    )
    parser.add_argument(
        "--predictor-manifest", type=Path, default=DEFAULT_OPERATOR_PREDICTOR
    )
    parser.add_argument("--model-roster", type=Path, default=DEFAULT_MODEL_ROSTER)
    parser.add_argument("--analysis-code", type=Path, default=DEFAULT_ANALYSIS_CODE)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--model-freeze", type=Path, default=DEFAULT_MODEL_FREEZE)
    parser.add_argument(
        "--readiness-output", type=Path, default=DEFAULT_MODEL_FREEZE_READINESS
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Exclusively create the freeze only if the readiness audit is clean.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 2 after writing readiness when any input is blocked.",
    )
    args = parser.parse_args()
    readiness = build_model_freeze_readiness(
        workload_path=args.workload,
        pre_score_freeze_path=args.pre_score_freeze,
        open_aggregation_path=args.open_aggregation,
        post_t2_input_binding_path=args.post_t2_input_binding,
        predictor_manifest_path=args.predictor_manifest,
        model_roster_path=args.model_roster,
        analysis_code_path=args.analysis_code,
        design_path=args.design,
        model_freeze_path=args.model_freeze,
    )
    write_readiness_manifest(readiness, args.readiness_output)
    created = False
    if args.create and readiness["ready_to_create_model_freeze"]:
        create_model_freeze_manifest(readiness, output_path=args.model_freeze)
        created = True
    summary = {
        "status": readiness["status"],
        "ready_to_create_model_freeze": readiness[
            "ready_to_create_model_freeze"
        ],
        "model_freeze_created": created,
        "sealed_outcomes_opened": False,
        "blockers": readiness["blockers"],
        "readiness_output": str(args.readiness_output),
        "model_freeze_output": str(args.model_freeze),
    }
    print(json.dumps(summary, sort_keys=True))
    if args.create and not created:
        raise SystemExit(2)
    if args.require_ready and not readiness["ready_to_create_model_freeze"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
