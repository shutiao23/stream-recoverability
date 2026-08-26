#!/usr/bin/env python3
"""Build a fail-closed T2 aggregation readiness or mixed-model input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_result_aggregation import (
    aggregate_t2_results,
)

DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v1"
DEFAULT_OUTPUT = DEFAULT_RUN / "aggregation"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload-manifest",
        type=Path,
        default=DEFAULT_RUN / "workload_manifest.json",
    )
    parser.add_argument(
        "--design", type=Path, default=ROOT / "configs/design_freeze_v9.yaml"
    )
    parser.add_argument(
        "--checkpoint-dir", type=Path, default=DEFAULT_RUN / "checkpoints_v3"
    )
    parser.add_argument(
        "--checkpoint-binding",
        type=Path,
        help="required SHA binding before checkpoint_v2 can be aggregated",
    )
    parser.add_argument(
        "--chunk-manifest",
        action="append",
        type=Path,
        default=[],
        help="repeatable future t2_v91_result_chunk_v1 manifest",
    )
    parser.add_argument(
        "--predictor-manifest",
        type=Path,
        help="train-only operator plus four-univariate prediction contract",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    manifest = aggregate_t2_results(
        workload_manifest_path=args.workload_manifest,
        design_path=args.design,
        output_dir=args.output,
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_binding_path=args.checkpoint_binding,
        chunk_manifest_paths=args.chunk_manifest,
        predictor_manifest_path=args.predictor_manifest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
