#!/usr/bin/env python3
"""Write v4 readiness; freeze a workload only after v2 reaches 67/67."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stream_recoverability.experiments.t2_recovery_benchmark import (
    discover_failure_closure_networks,
    iter_all_work_items,
    load_v91_budget,
)
from stream_recoverability.experiments.t2_workload_v4 import (
    build_v4_readiness_manifest,
    build_v4_workload_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V3 = ROOT / "results/framework/t2_recovery_benchmark_v1/workload_manifest.json"
DEFAULT_OUTPUT = ROOT / "results/framework/t2_recovery_benchmark_v4"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-v3", type=Path, default=DEFAULT_V3)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    networks, _ = discover_failure_closure_networks(ROOT)
    readiness = build_v4_readiness_manifest(
        ROOT, networks, source_v3_workload_path=args.source_v3
    )
    _write(args.output / "readiness_manifest.json", readiness)
    result = {
        "readiness_manifest": str(args.output / "readiness_manifest.json"),
        "status": readiness["status"],
        "formal_workload_written": False,
    }
    if readiness["status"] == "ready_for_formal_v4_freeze":
        budget = load_v91_budget(ROOT)
        workload = build_v4_workload_manifest(
            ROOT,
            networks,
            source_v3_workload_path=args.source_v3,
            source_items=iter_all_work_items(ROOT, networks, budget),
        )
        _write(args.output / "workload_manifest.json", workload)
        result["formal_workload_written"] = True
        result["workload_manifest"] = str(args.output / "workload_manifest.json")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
