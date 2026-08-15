#!/usr/bin/env python3
"""Run dense, resilience, information-compensation, or information studies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.runner import SUPPORTED_MODELS
from stream_recoverability.experiments.science import (
    run_dense_experiments,
    run_information_compensation,
    run_resilience_experiments,
    write_training_information_metrics,
)


def _models(values: list[str]) -> list[str]:
    result = [part.strip().lower() for value in values for part in value.split(",") if part.strip()]
    unknown = sorted(set(result).difference(SUPPORTED_MODELS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unsupported models: {unknown}")
    return list(dict.fromkeys(result))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    dense = subparsers.add_parser("dense", help="run the fixed dense single-gap grid")
    dense.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml")
    dense.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml")
    dense.add_argument("--data", type=Path, default=PROJECT_ROOT / "data/processed/daily_wide.parquet")
    dense.add_argument("--quality-data", type=Path, default=PROJECT_ROOT / "data/processed/daily_long.parquet")
    dense.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results/science_experiments/dense")
    dense.add_argument("--mask-dir", type=Path, default=PROJECT_ROOT / "masks/science_dense")
    dense.add_argument("--models", nargs="+", default=["climatology", "linear"])
    dense.add_argument("--training-seeds", nargs="+", type=int)
    dense.add_argument("--mask-seeds", nargs="+", type=int)
    dense.add_argument("--shard-index", type=int, default=0)
    dense.add_argument("--shard-count", type=int, default=1)
    dense.add_argument("--max-scenarios", type=int)
    dense.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)

    resilience = subparsers.add_parser(
        "resilience", help="run the matched three-station failure powerset"
    )
    resilience.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml")
    resilience.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml")
    resilience.add_argument(
        "--data", type=Path, default=PROJECT_ROOT / "data/processed/daily_wide.parquet"
    )
    resilience.add_argument(
        "--quality-data",
        type=Path,
        default=PROJECT_ROOT / "data/processed/daily_long.parquet",
    )
    resilience.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results/science_experiments/resilience",
    )
    resilience.add_argument(
        "--mask-dir", type=Path, default=PROJECT_ROOT / "masks/science_resilience"
    )
    resilience.add_argument("--models", nargs="+", default=["climatology", "linear"])
    resilience.add_argument("--training-seeds", nargs="+", type=int)
    resilience.add_argument("--mask-seeds", nargs="+", type=int)
    resilience.add_argument("--shard-index", type=int, default=0)
    resilience.add_argument("--shard-count", type=int, default=1)
    resilience.add_argument("--max-scenarios", type=int)
    resilience.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)

    compensation = subparsers.add_parser(
        "compensation", help="evaluate S0 and all 15 checkpoint source subsets"
    )
    compensation.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml")
    compensation.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml")
    compensation.add_argument("--data", type=Path, default=PROJECT_ROOT / "data/processed/daily_wide.parquet")
    compensation.add_argument("--quality-data", type=Path, default=PROJECT_ROOT / "data/processed/daily_long.parquet")
    compensation.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results/science_experiments/compensation",
    )
    compensation.add_argument(
        "--mask-dir", type=Path, default=PROJECT_ROOT / "masks/science_compensation"
    )
    compensation.add_argument("--checkpoint", type=Path)
    compensation.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=PROJECT_ROOT / "results/experiments/checkpoints",
    )
    compensation.add_argument(
        "--checkpoint-template",
        default="proposed-S{seed}-W{window}-{protocol}.pt",
    )
    compensation.add_argument("--training-seed", type=int)
    compensation.add_argument("--training-seeds", nargs="+", type=int)
    compensation.add_argument("--mask-seeds", nargs="+", type=int)
    compensation.add_argument("--max-scenarios", type=int)
    compensation.add_argument("--device", default="cpu")
    compensation.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )

    information = subparsers.add_parser(
        "information", help="compute training-only kNN MI and bidirectional TE"
    )
    information.add_argument("--data", type=Path, default=PROJECT_ROOT / "data/processed/daily_wide.parquet")
    information.add_argument("--quality-data", type=Path, default=PROJECT_ROOT / "data/processed/daily_long.parquet")
    information.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/analysis/information_metrics.csv",
    )
    information.add_argument("--neighbors", type=int, default=5)
    information.add_argument("--lags", nargs="+", type=int, default=[1, 2, 3, 7])
    information.add_argument("--permutations", type=int, default=199)
    information.add_argument("--bins", type=int, default=4)
    information.add_argument("--seed", type=int, default=11)
    information.add_argument(
        "--deseasonalize", action=argparse.BooleanOptionalAction, default=True
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command in {"dense", "resilience"}:
        try:
            models = _models(args.models)
        except argparse.ArgumentTypeError as error:
            raise SystemExit(str(error)) from error
        run_experiments = (
            run_dense_experiments if args.command == "dense" else run_resilience_experiments
        )
        daily, events = run_experiments(
            manifest_path=args.manifest,
            config_path=args.config,
            wide_path=args.data,
            quality_path=args.quality_data,
            output_dir=args.output_dir,
            mask_dir=args.mask_dir,
            models=models,
            training_seeds=args.training_seeds,
            mask_seeds=args.mask_seeds,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            max_scenarios=args.max_scenarios,
            resume=args.resume,
        )
        summary = {
            "command": args.command,
            "models": models,
            "daily_rows": len(daily),
            "event_rows": len(events),
            "output_dir": str(args.output_dir),
        }
    elif args.command == "compensation":
        daily, events, skipped = run_information_compensation(
            checkpoint_path=args.checkpoint,
            checkpoint_dir=args.checkpoint_dir,
            checkpoint_template=args.checkpoint_template,
            manifest_path=args.manifest,
            config_path=args.config,
            wide_path=args.data,
            quality_path=args.quality_data,
            output_dir=args.output_dir,
            mask_dir=args.mask_dir,
            training_seeds=args.training_seeds,
            training_seed=args.training_seed,
            mask_seeds=args.mask_seeds,
            max_scenarios=args.max_scenarios,
            device=args.device,
            resume=args.resume,
        )
        summary = {
            "command": args.command,
            "training_seeds": args.training_seeds,
            "training_seed": args.training_seed,
            "checkpoint": str(args.checkpoint) if args.checkpoint else None,
            "checkpoint_dir": str(args.checkpoint_dir),
            "daily_rows": len(daily),
            "event_rows": len(events),
            "skipped_rows": len(skipped),
            "output_dir": str(args.output_dir),
        }
    else:
        result = write_training_information_metrics(
            args.data,
            args.output,
            quality_long=args.quality_data,
            n_neighbors=args.neighbors,
            lags=args.lags,
            n_permutations=args.permutations,
            n_bins=args.bins,
            seed=args.seed,
            deseasonalize=args.deseasonalize,
        )
        summary = {
            "command": args.command,
            "rows": len(result),
            "mi_rows": int((result["metric"] == "knn_mutual_information").sum()),
            "te_rows": int((result["metric"] == "transfer_entropy").sum()),
            "output": str(args.output),
            "interpretation": "association/directional information only; not causal",
        }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
