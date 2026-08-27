#!/usr/bin/env python3
"""Validate global T2 v4 chunk completeness without opening sealed inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stream_recoverability.experiments.t2_result_aggregation_v4 import (
    aggregate_v4_chunk_manifests,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v4"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workload", type=Path, default=DEFAULT_RUN / "workload_manifest.json"
    )
    parser.add_argument(
        "--aggregation-list",
        type=Path,
        default=DEFAULT_RUN / "batch_orchestration_v1/aggregation_chunk_manifests.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RUN / "aggregation/aggregation_manifest.json",
    )
    args = parser.parse_args()
    value = json.loads(args.aggregation_list.read_text(encoding="utf-8"))
    manifest = aggregate_v4_chunk_manifests(
        workload_manifest_path=args.workload,
        chunk_manifest_paths=value.get("chunk_manifest_paths") or [],
        output_manifest_path=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
