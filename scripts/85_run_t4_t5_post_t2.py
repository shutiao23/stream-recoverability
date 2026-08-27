#!/usr/bin/env python3
"""Run the fail-closed T4/T5 post-T2 contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t4_t5_post_t2 import run_post_t2_analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workload",
        type=Path,
        default=ROOT
        / "results/framework/t2_recovery_benchmark_v4/workload_manifest_v3.json",
    )
    parser.add_argument(
        "--result-binding",
        type=Path,
        default=ROOT
        / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2"
        / "post_t2_input_binding.json",
    )
    parser.add_argument(
        "--geometry-catalog",
        type=Path,
        default=ROOT / "results/framework/t2_outage_geometry_v1/natural_outage_catalog.csv",
    )
    parser.add_argument(
        "--geometry-manifest",
        type=Path,
        default=ROOT / "results/framework/t2_outage_geometry_v1/geometry_binding_manifest.json",
    )
    parser.add_argument(
        "--pair-plan",
        type=Path,
        default=ROOT / "results/framework/t5_matching_contract_v1/pair_plan.csv",
    )
    parser.add_argument(
        "--pair-manifest",
        type=Path,
        default=ROOT / "results/framework/t5_matching_contract_v1/readiness_manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/framework/t4_t5_post_t2_v1",
    )
    args = parser.parse_args()
    manifest = run_post_t2_analysis(
        workload_path=args.workload,
        result_binding_path=args.result_binding,
        geometry_catalog_path=args.geometry_catalog,
        geometry_manifest_path=args.geometry_manifest,
        pair_plan_path=args.pair_plan,
        pair_manifest_path=args.pair_manifest,
        output_dir=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
