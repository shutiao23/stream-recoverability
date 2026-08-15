#!/usr/bin/env python3
"""Run a resumable smoke/core/full experiment suite or one deterministic shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments import ExperimentRunner, build_experiment_grid  # noqa: E402
from stream_recoverability.experiments.runner import SUPPORTED_MODELS  # noqa: E402


def _model_list(values: list[str]) -> list[str]:
    models = [part.strip().lower() for value in values for part in value.split(",") if part.strip()]
    unknown = sorted(set(models).difference(SUPPORTED_MODELS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unsupported models: {unknown}")
    return list(dict.fromkeys(models))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("smoke", "core", "full"), default="smoke")
    parser.add_argument("--models", nargs="+", default=["climatology", "linear"])
    parser.add_argument("--training-seeds", nargs="+", type=int)
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "data/processed/daily_wide.parquet")
    parser.add_argument("--quality-data", type=Path, default=PROJECT_ROOT / "data/processed/daily_long.parquet")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results/experiments")
    parser.add_argument("--mask-dir", type=Path, default=PROJECT_ROOT / "masks/full")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--max-scenarios", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        models = _model_list(args.models)
    except argparse.ArgumentTypeError as error:
        raise SystemExit(str(error)) from error
    grid = build_experiment_grid(args.manifest, args.config, suite=args.suite)
    runner = ExperimentRunner(
        grid,
        wide_path=args.data,
        quality_path=args.quality_data,
        output_dir=args.output_dir,
        mask_dir=args.mask_dir,
        config_path=args.config,
        models=models,
        training_seeds=args.training_seeds,
        resume=args.resume,
    )
    daily, events = runner.run(
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        max_scenarios=args.max_scenarios,
    )
    print(
        json.dumps(
            {
                "suite": args.suite,
                "models": models,
                "daily_rows": len(daily),
                "event_rows": len(events),
                "output_dir": str(args.output_dir),
                "external_validation_status": grid.external_validation_status,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
