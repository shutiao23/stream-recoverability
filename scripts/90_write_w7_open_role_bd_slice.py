#!/usr/bin/env python3
"""Write the W7 open-role B/D development slice. Not confirmatory T2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_w7_open_role_bd_slice import (
    aggregate_w7_open_role_bd_slice_from_chunks,
    collect_w7_chunk_manifest_paths,
)

DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v1"
DEFAULT_SLICE = DEFAULT_RUN / "w7_open_role_bd_slice"
LOCKED_WORKLOAD_SHA256 = "c08129ad71a96a56a1610a1eacbbb93be9dd5ccd646b21e9ba7dc431f412fa19"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload-manifest",
        type=Path,
        default=DEFAULT_RUN / "workload_manifest.json",
    )
    parser.add_argument(
        "--expect-workload-sha256",
        default=LOCKED_WORKLOAD_SHA256,
    )
    parser.add_argument(
        "--chunk-manifest",
        action="append",
        type=Path,
        default=[],
        help="repeatable t2_v91_result_chunk_v1 manifest; default: batch list",
    )
    parser.add_argument(
        "--aggregation-list",
        action="append",
        type=Path,
        default=[],
        help="repeatable batch aggregation list; default: the 1-network slice list",
    )
    parser.add_argument(
        "--predictor-manifest",
        type=Path,
        default=DEFAULT_RUN / "train_only_predictors/predictor_manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SLICE,
        help=(
            "slice output directory; default is the committed 1-network slice. "
            "Merging expand chunks must pass a different --output so that slice "
            "is not overwritten."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    import hashlib

    actual = hashlib.sha256(args.workload_manifest.read_bytes()).hexdigest()
    if actual != args.expect_workload_sha256:
        raise SystemExit(
            "workload SHA-256 mismatch: "
            f"got {actual}, expected {args.expect_workload_sha256}"
        )
    chunk_paths = collect_w7_chunk_manifest_paths(
        chunk_manifest_paths=args.chunk_manifest,
        aggregation_list_paths=args.aggregation_list,
        default_aggregation_list=DEFAULT_SLICE / "aggregation_chunk_manifests.json",
    )
    if not chunk_paths:
        raise SystemExit("no W7 chunk manifests supplied")
    manifest = aggregate_w7_open_role_bd_slice_from_chunks(
        repo_root=ROOT,
        output_dir=args.output,
        workload_manifest_path=args.workload_manifest,
        chunk_manifest_paths=chunk_paths,
        predictor_manifest_path=args.predictor_manifest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
