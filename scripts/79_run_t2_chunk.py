#!/usr/bin/env python3
"""Execute one immutable [start,end) chunk of the frozen T2 v9.1 workload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_chunk_executor import execute_t2_chunk

DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=int, help="inclusive global ordinal")
    parser.add_argument("--end", required=True, type=int, help="exclusive global ordinal")
    parser.add_argument("--format", choices=("parquet", "csv"), default="parquet")
    parser.add_argument(
        "--workload-manifest",
        type=Path,
        default=DEFAULT_RUN / "workload_manifest.json",
    )
    parser.add_argument(
        "--design", type=Path, default=ROOT / "configs/design_freeze_v9.yaml"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_RUN / "chunks_v1")
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    manifest = execute_t2_chunk(
        repo_root=ROOT,
        workload_manifest_path=args.workload_manifest,
        design_path=args.design,
        output_dir=args.output,
        start_ordinal=args.start,
        end_ordinal_exclusive=args.end,
        results_format=args.format,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
