#!/usr/bin/env python3
"""Freeze the outcome-blind T2 v4 primary lattice, or write blockers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stream_recoverability.experiments.t2_primary_aggregation_v2 import (
    create_pre_score_freeze_bundle,
    freeze_v4_analyzable_lattice,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workload",
        type=Path,
        default=ROOT
        / "results/framework/t2_recovery_benchmark_v4/index_draft_manifest.json",
    )
    parser.add_argument(
        "--predictor-manifest",
        type=Path,
        default=ROOT
        / "results/framework/t2_recovery_benchmark_v4/train_only_predictors_v2/predictor_manifest.json",
    )
    parser.add_argument(
        "--eligibility-manifest",
        type=Path,
        default=ROOT
        / "results/framework/t2_recovery_benchmark_v4/pre_score_eligibility/manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT
        / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2",
    )
    args = parser.parse_args()
    manifest = freeze_v4_analyzable_lattice(
        workload_manifest_path=args.workload,
        predictor_manifest_path=args.predictor_manifest,
        eligibility_manifest_path=args.eligibility_manifest,
        output_dir=args.output_dir,
    )
    if manifest.get("manifest_schema") == "t2_v91_v4_analyzable_lattice_freeze_v1":
        bundle = create_pre_score_freeze_bundle(
            index_draft_manifest_path=args.workload,
            eligibility_manifest_path=args.eligibility_manifest,
            lattice_freeze_manifest_path=args.output_dir
            / "lattice_freeze_manifest.json",
            output_path=args.output_dir.parent / "pre_score_freeze_manifest.json",
        )
        manifest = {"lattice": manifest, "pre_score_freeze": bundle}
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
