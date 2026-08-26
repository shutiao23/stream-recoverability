#!/usr/bin/env python3
"""Plan T2 chunks safely; execute only after exact three-part acknowledgement."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_batch_orchestrator import (
    V3_CONTRACT,
    load_contract_spec,
    orchestrate_t2_batch,
)

DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload-manifest",
        type=Path,
        default=DEFAULT_RUN / "workload_manifest.json",
    )
    parser.add_argument(
        "--expect-workload-sha256",
        required=True,
        help="exact SHA-256 of workload-manifest bytes (required even for dry-run)",
    )
    parser.add_argument(
        "--contract-spec",
        type=Path,
        help="parameterized future contract JSON; built-in legacy v3 if omitted",
    )
    parser.add_argument(
        "--design", type=Path, default=ROOT / "configs/design_freeze_v9.yaml"
    )
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument(
        "--end",
        type=int,
        help="exclusive ordinal; omitted means the complete workload",
    )
    parser.add_argument("--chunk-size", type=int, default=5_000)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--format", choices=("parquet", "csv"), default="parquet")
    parser.add_argument(
        "--execution-mode",
        choices=("legacy_item_v1", "network_cache_v1"),
        default="network_cache_v1",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_RUN / "batch_orchestration_v1/batch_state.json",
    )
    parser.add_argument(
        "--chunks-output",
        type=Path,
        default=DEFAULT_RUN / "chunks_cache_v1",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="execute (default is a non-executing readiness/dry-run)",
    )
    parser.add_argument(
        "--allow-full-workload",
        action="store_true",
        help="second explicit gate needed if the plan spans the entire workload",
    )
    parser.add_argument("--ack-item-count", type=int)
    parser.add_argument("--ack-chunk-count", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--print-current-workload-sha256",
        action="store_true",
        help="print the current file SHA before planning; does not waive --expect",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    if args.print_current_workload_sha256:
        print(
            json.dumps(
                {
                    "workload_manifest": str(args.workload_manifest),
                    "current_sha256": hashlib.sha256(
                        args.workload_manifest.read_bytes()
                    ).hexdigest(),
                },
                sort_keys=True,
            )
        )
    contract = load_contract_spec(args.contract_spec) if args.contract_spec else V3_CONTRACT
    state = orchestrate_t2_batch(
        repo_root=ROOT,
        workload_manifest_path=args.workload_manifest,
        design_path=args.design,
        state_path=args.state,
        chunks_output_dir=args.chunks_output,
        expected_workload_sha256=args.expect_workload_sha256,
        contract=contract,
        start_ordinal=args.start,
        end_ordinal_exclusive=args.end,
        chunk_size=args.chunk_size,
        max_workers=args.max_workers,
        execute=args.execute,
        allow_full_workload=args.allow_full_workload,
        acknowledge_item_count=args.ack_item_count,
        acknowledge_chunk_count=args.ack_chunk_count,
        resume=args.resume,
        results_format=args.format,
        execution_mode=args.execution_mode,
    )
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
