#!/usr/bin/env python3
"""Execute one immutable T2 v4 chunk after the 67/67 formal freeze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stream_recoverability.experiments.t2_chunk_executor_v4 import (
    execute_t2_v4_chunk,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v4"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--format", choices=("parquet", "csv"), default="parquet")
    parser.add_argument("--workload", type=Path, default=DEFAULT_RUN / "workload_manifest.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_RUN / "chunks_v1")
    args = parser.parse_args()
    manifest = execute_t2_v4_chunk(
        repo_root=ROOT,
        workload_manifest_path=args.workload,
        output_dir=args.output,
        start_ordinal=args.start,
        end_ordinal_exclusive=args.end,
        results_format=args.format,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
