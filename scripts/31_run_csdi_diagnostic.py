#!/usr/bin/env python3
"""Run the v5 reduced CSDI diagnostic outside the formal frontier roster."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.science import run_dense_experiments


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roster",
        type=Path,
        default=PROJECT_ROOT
        / "results/validation_funnel/published_v2/finalized_model_roster.json",
    )
    parser.add_argument("--mask-seeds", nargs="+", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--max-scenarios", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    roster = json.loads(args.roster.read_text(encoding="utf-8"))
    protocol = roster["diagnostic_protocols"]["csdi"]
    if "csdi" not in roster["diagnostic_models"]:
        raise ValueError("the finalized roster does not authorize the CSDI diagnostic")
    output = PROJECT_ROOT / "results/diagnostics/csdi_reduced_v1"
    daily, events = run_dense_experiments(
        manifest_path=PROJECT_ROOT / "study_manifest.yaml",
        config_path=PROJECT_ROOT / "configs/experiments.yaml",
        design_path=PROJECT_ROOT / "configs/design_freeze_v4.yaml",
        data_version_manifest_path=PROJECT_ROOT
        / "data_versions/published_v2/version_manifest.json",
        wide_path=PROJECT_ROOT / "data_versions/published_v2/daily_wide.parquet",
        quality_path=PROJECT_ROOT / "data_versions/published_v2/daily_long.parquet",
        output_dir=output,
        checkpoint_dir=PROJECT_ROOT
        / "results/science_experiments/published_v2/development_test/dense/checkpoints",
        mask_dir=PROJECT_ROOT / "masks/science_dense/published_v2/development_test",
        models=("csdi",),
        training_seeds=(int(protocol["seed"]),),
        mask_seeds=args.mask_seeds,
        data_version="published_v2",
        evaluation_split="development_test",
        frontier_anchor_path=PROJECT_ROOT / "metadata/frontier_anchors_v2.csv",
        variables=("T",),
        gap_lengths=tuple(int(value) for value in protocol["gap_lengths_days"]),
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        max_scenarios=args.max_scenarios,
        resume=True,
    )
    print(
        json.dumps(
            {
                "status": "diagnostic_only",
                "formal_frontier_evidence": False,
                "daily_rows": len(daily),
                "event_rows": len(events),
                "output_dir": str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
