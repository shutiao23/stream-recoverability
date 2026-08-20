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

from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    build_design_contract,
    canonical_evaluation_split,
    load_frozen_data_versions,
)
from stream_recoverability.experiments.donor_falsification import (
    run_donor_falsification,
)
from stream_recoverability.experiments.formal_authorization import (
    authorize_roster_suite,
)
from stream_recoverability.experiments.retrained_information import (
    run_retrained_information_upper_bounds,
)
from stream_recoverability.experiments.runner import SUPPORTED_MODELS
from stream_recoverability.experiments.science import (
    run_dense_experiments,
    run_information_compensation,
    run_resilience_experiments,
    write_training_information_metrics,
)


def _models(values: list[str]) -> list[str]:
    result = [
        part.strip().lower()
        for value in values
        for part in value.split(",")
        if part.strip()
    ]
    unknown = sorted(set(result).difference(SUPPORTED_MODELS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unsupported models: {unknown}")
    return list(dict.fromkeys(result))


def _add_anchor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-version", default="published_v2")
    parser.add_argument(
        "--evaluation-split",
        choices=("development_test", "test"),
        default="development_test",
    )
    parser.add_argument(
        "--frontier-anchors",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "frontier_anchors_v2.csv",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_DESIGN_PATH,
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=PROJECT_ROOT / "data_versions",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    dense = subparsers.add_parser("dense", help="run the fixed dense single-gap grid")
    dense.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    dense.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    dense.add_argument("--data", type=Path)
    dense.add_argument("--quality-data", type=Path)
    dense.add_argument("--output-dir", type=Path)
    dense.add_argument("--mask-dir", type=Path)
    dense.add_argument("--models", nargs="+")
    dense.add_argument("--finalized-model-roster", type=Path, required=True)
    dense.add_argument("--training-seeds", nargs="+", type=int)
    dense.add_argument("--mask-seeds", nargs="+", type=int)
    dense.add_argument("--shard-index", type=int, default=0)
    dense.add_argument("--shard-count", type=int, default=1)
    dense.add_argument("--max-scenarios", type=int)
    dense.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    _add_anchor_arguments(dense)

    resilience = subparsers.add_parser(
        "resilience", help="run the matched three-station failure powerset"
    )
    resilience.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    resilience.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    resilience.add_argument("--data", type=Path)
    resilience.add_argument("--quality-data", type=Path)
    resilience.add_argument("--output-dir", type=Path)
    resilience.add_argument("--mask-dir", type=Path)
    resilience.add_argument("--models", nargs="+")
    resilience.add_argument("--finalized-model-roster", type=Path, required=True)
    resilience.add_argument("--training-seeds", nargs="+", type=int)
    resilience.add_argument("--mask-seeds", nargs="+", type=int)
    resilience.add_argument("--shard-index", type=int, default=0)
    resilience.add_argument("--shard-count", type=int, default=1)
    resilience.add_argument("--max-scenarios", type=int)
    resilience.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )
    _add_anchor_arguments(resilience)

    compensation = subparsers.add_parser(
        "compensation", help="evaluate S0 and all 15 checkpoint source subsets"
    )
    compensation.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    compensation.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    compensation.add_argument("--data", type=Path)
    compensation.add_argument("--quality-data", type=Path)
    compensation.add_argument("--output-dir", type=Path)
    compensation.add_argument("--mask-dir", type=Path)
    compensation.add_argument("--checkpoint", type=Path)
    compensation.add_argument(
        "--checkpoint-dir",
        type=Path,
    )
    compensation.add_argument(
        "--checkpoint-template",
        default="proposed-S{seed}-W{window}-{protocol}.pt",
    )
    compensation.add_argument("--training-seed", type=int)
    compensation.add_argument("--training-seeds", nargs="+", type=int)
    compensation.add_argument("--finalized-model-roster", type=Path, required=True)
    compensation.add_argument("--mask-seeds", nargs="+", type=int)
    compensation.add_argument("--max-scenarios", type=int)
    compensation.add_argument("--device", default="cpu")
    compensation.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )
    _add_anchor_arguments(compensation)

    donor = subparsers.add_parser(
        "donor-falsification",
        help="run the frozen same-checkpoint target-donor lag/permutation suite",
    )
    donor.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    donor.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    donor.add_argument("--data", type=Path)
    donor.add_argument("--quality-data", type=Path)
    donor.add_argument("--output-dir", type=Path)
    donor.add_argument("--mask-dir", type=Path)
    donor.add_argument("--checkpoint-dir", type=Path)
    donor.add_argument("--training-seeds", nargs="+", type=int)
    donor.add_argument("--finalized-model-roster", type=Path, required=True)
    donor.add_argument("--mask-seeds", nargs="+", type=int)
    donor.add_argument("--max-scenarios", type=int)
    donor.add_argument("--device", default="cpu")
    donor.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    _add_anchor_arguments(donor)

    retrained = subparsers.add_parser(
        "retrained-information",
        help="train and evaluate the frozen nine-coalition information upper bound",
    )
    retrained.add_argument(
        "--finalized-model-roster",
        type=Path,
        required=True,
        help="hash-verified validation-only finalized_model_roster_v1 JSON",
    )
    retrained.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    retrained.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    retrained.add_argument("--data", type=Path)
    retrained.add_argument("--quality-data", type=Path)
    retrained.add_argument("--output-dir", type=Path)
    retrained.add_argument("--mask-dir", type=Path)
    retrained.add_argument("--training-seeds", nargs="+", type=int)
    retrained.add_argument("--mask-seeds", nargs="+", type=int)
    retrained.add_argument(
        "--coalitions",
        nargs="+",
        help=(
            "optional subset of the frozen labels, e.g. S0 S0+A S0+A+B+C+D; "
            "a formal completion still requires all nine"
        ),
    )
    retrained.add_argument("--max-scenarios", type=int)
    retrained.add_argument("--device", default="cpu")
    retrained.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )
    _add_anchor_arguments(retrained)

    information = subparsers.add_parser(
        "information", help="compute training-only kNN MI and bidirectional TE"
    )
    information.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    information.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    information.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_DESIGN_PATH,
    )
    information.add_argument("--data-version", default="published_v2")
    information.add_argument(
        "--evaluation-split",
        choices=("development_test", "test"),
        default="development_test",
        help="design context only; the information estimates still use train rows",
    )
    information.add_argument(
        "--data-root", type=Path, default=PROJECT_ROOT / "data_versions"
    )
    information.add_argument("--data", type=Path)
    information.add_argument(
        "--quality-data",
        type=Path,
    )
    information.add_argument(
        "--output",
        type=Path,
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
    frozen_versions = load_frozen_data_versions(args.design)
    if args.data_version not in {
        frozen_versions.primary,
        *frozen_versions.sensitivities,
    }:
        raise ValueError("--data-version is outside the design's frozen inventory")
    if args.command in {"dense", "resilience"}:
        canonical_split = canonical_evaluation_split(args.evaluation_split)
        version_root = args.data_root / args.data_version
        version_manifest = version_root / "version_manifest.json"
        selection_version_manifest = frozen_versions.manifest_path(args.data_root)
        if not version_manifest.is_file() or not selection_version_manifest.is_file():
            raise FileNotFoundError(
                "versioned data manifests are required: "
                f"{version_manifest}, {selection_version_manifest}"
            )
        contract = build_design_contract(
            design_path=args.design,
            manifest_path=args.manifest,
            experiment_config_path=args.config,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            data_version_manifest_path=version_manifest,
        )
        data = args.data or version_root / "daily_wide.parquet"
        quality_data = args.quality_data or version_root / "daily_long.parquet"
        output_dir = args.output_dir or (
            PROJECT_ROOT
            / "results"
            / "science_experiments"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
            / args.command
        )
        mask_dir = args.mask_dir or (
            PROJECT_ROOT
            / "masks"
            / f"science_{args.command}"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
        )
        models, formal_authorization = authorize_roster_suite(
            args.finalized_model_roster,
            suite="science_dense" if args.command == "dense" else "science_resilience",
            target_scope=("T", "F", "L") if args.command == "dense" else ("T",),
            design_path=args.design,
            study_manifest_path=args.manifest,
            experiment_config_path=args.config,
            selection_data_version_manifest_path=selection_version_manifest,
        )
        if args.models is not None:
            try:
                requested_models = tuple(_models(args.models))
            except argparse.ArgumentTypeError as error:
                raise SystemExit(str(error)) from error
            if requested_models != models:
                raise ValueError(
                    "--models cannot override the finalized formal roster: "
                    f"expected={list(models)}, observed={list(requested_models)}"
                )
        run_experiments = (
            run_dense_experiments
            if args.command == "dense"
            else run_resilience_experiments
        )
        daily, events = run_experiments(
            manifest_path=args.manifest,
            config_path=args.config,
            design_path=args.design,
            data_version_manifest_path=version_manifest,
            wide_path=data,
            quality_path=quality_data,
            output_dir=output_dir,
            mask_dir=mask_dir,
            models=models,
            training_seeds=args.training_seeds,
            formal_authorization=formal_authorization,
            mask_seeds=args.mask_seeds,
            data_version=args.data_version,
            evaluation_split=args.evaluation_split,
            frontier_anchor_path=args.frontier_anchors,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            max_scenarios=args.max_scenarios,
            resume=args.resume,
        )
        summary = {
            "command": args.command,
            "models": list(models),
            "daily_rows": len(daily),
            "event_rows": len(events),
            "output_dir": str(output_dir),
            "data_version": args.data_version,
            "evaluation_split": canonical_split,
            "design_hash": contract["design_hash"],
            "formal_evidence": True,
            "finalized_model_roster": formal_authorization["finalized_model_roster"],
            "expected_formal_models": list(models),
        }
    elif args.command == "compensation":
        canonical_split = canonical_evaluation_split(args.evaluation_split)
        version_root = args.data_root / args.data_version
        version_manifest = version_root / "version_manifest.json"
        selection_version_manifest = frozen_versions.manifest_path(args.data_root)
        if not version_manifest.is_file() or not selection_version_manifest.is_file():
            raise FileNotFoundError(
                "versioned data manifests are required: "
                f"{version_manifest}, {selection_version_manifest}"
            )
        contract = build_design_contract(
            design_path=args.design,
            manifest_path=args.manifest,
            experiment_config_path=args.config,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            data_version_manifest_path=version_manifest,
        )
        data = args.data or version_root / "daily_wide.parquet"
        quality_data = args.quality_data or version_root / "daily_long.parquet"
        output_dir = args.output_dir or (
            PROJECT_ROOT
            / "results"
            / "science_experiments"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
            / "compensation"
        )
        mask_dir = args.mask_dir or (
            PROJECT_ROOT
            / "masks"
            / "science_compensation"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
        )
        checkpoint_dir = args.checkpoint_dir or (
            PROJECT_ROOT
            / "results"
            / "experiments_v2"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
            / "full"
            / "checkpoints"
        )
        daily, events, skipped = run_information_compensation(
            finalized_model_roster_path=args.finalized_model_roster,
            selection_data_version_manifest_path=selection_version_manifest,
            checkpoint_path=args.checkpoint,
            checkpoint_dir=checkpoint_dir,
            checkpoint_template=args.checkpoint_template,
            manifest_path=args.manifest,
            config_path=args.config,
            design_path=args.design,
            data_version_manifest_path=version_manifest,
            wide_path=data,
            quality_path=quality_data,
            output_dir=output_dir,
            mask_dir=mask_dir,
            training_seeds=args.training_seeds,
            training_seed=args.training_seed,
            mask_seeds=args.mask_seeds,
            data_version=args.data_version,
            evaluation_split=args.evaluation_split,
            frontier_anchor_path=args.frontier_anchors,
            max_scenarios=args.max_scenarios,
            device=args.device,
            resume=args.resume,
        )
        compensation_manifest = json.loads(
            (output_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
        summary = {
            "command": args.command,
            "training_seeds": args.training_seeds,
            "training_seed": args.training_seed,
            "checkpoint": str(args.checkpoint) if args.checkpoint else None,
            "checkpoint_dir": str(checkpoint_dir),
            "daily_rows": len(daily),
            "event_rows": len(events),
            "skipped_rows": len(skipped),
            "output_dir": str(output_dir),
            "data_version": args.data_version,
            "evaluation_split": canonical_split,
            "design_hash": contract["design_hash"],
            "status": compensation_manifest["status"],
            "formal_evidence": compensation_manifest["formal_evidence"],
            "finalized_model_roster": compensation_manifest["finalized_model_roster"],
            "expected_formal_models": compensation_manifest["expected_formal_models"],
        }
    elif args.command == "donor-falsification":
        canonical_split = canonical_evaluation_split(args.evaluation_split)
        version_root = args.data_root / args.data_version
        version_manifest = version_root / "version_manifest.json"
        selection_version_manifest = frozen_versions.manifest_path(args.data_root)
        for required in (version_manifest, selection_version_manifest):
            if not required.is_file():
                raise FileNotFoundError(
                    f"versioned data manifest is required: {required}"
                )
        contract = build_design_contract(
            design_path=args.design,
            manifest_path=args.manifest,
            experiment_config_path=args.config,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            data_version_manifest_path=version_manifest,
        )
        run_root = (
            PROJECT_ROOT
            / "results/science_experiments"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
        )
        output_dir = args.output_dir or run_root / "donor_falsification"
        mask_dir = args.mask_dir or (
            PROJECT_ROOT
            / "masks/science_donor_falsification"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
        )
        checkpoint_dir = args.checkpoint_dir or (
            PROJECT_ROOT
            / "results/experiments_v2"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
            / "full/checkpoints"
        )
        daily, events, skipped = run_donor_falsification(
            finalized_model_roster_path=args.finalized_model_roster,
            selection_data_version_manifest_path=selection_version_manifest,
            checkpoint_dir=checkpoint_dir,
            manifest_path=args.manifest,
            config_path=args.config,
            design_path=args.design,
            data_version_manifest_path=version_manifest,
            wide_path=args.data or version_root / "daily_wide.parquet",
            quality_path=args.quality_data or version_root / "daily_long.parquet",
            output_dir=output_dir,
            mask_dir=mask_dir,
            training_seeds=args.training_seeds,
            mask_seeds=args.mask_seeds,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            frontier_anchor_path=args.frontier_anchors,
            max_scenarios=args.max_scenarios,
            device=args.device,
            resume=args.resume,
        )
        run_manifest = json.loads(
            (output_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
        summary = {
            "command": args.command,
            "status": run_manifest["status"],
            "complete": run_manifest["complete"],
            "daily_rows": len(daily),
            "event_rows": len(events),
            "skipped_rows": len(skipped),
            "output_dir": str(output_dir),
            "data_version": args.data_version,
            "design_hash": contract["design_hash"],
        }
    elif args.command == "retrained-information":
        canonical_split = canonical_evaluation_split(args.evaluation_split)
        version_root = args.data_root / args.data_version
        version_manifest = version_root / "version_manifest.json"
        selection_version_manifest = frozen_versions.manifest_path(args.data_root)
        for required in (version_manifest, selection_version_manifest):
            if not required.is_file():
                raise FileNotFoundError(
                    f"versioned data manifest is required: {required}"
                )
        contract = build_design_contract(
            design_path=args.design,
            manifest_path=args.manifest,
            experiment_config_path=args.config,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            data_version_manifest_path=version_manifest,
        )
        data = args.data or version_root / "daily_wide.parquet"
        quality_data = args.quality_data or version_root / "daily_long.parquet"
        output_dir = args.output_dir or (
            PROJECT_ROOT
            / "results"
            / "science_experiments"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
            / "retrained_information_upper_bounds"
        )
        mask_dir = args.mask_dir or (
            PROJECT_ROOT
            / "masks"
            / "science_retrained_information"
            / args.data_version
            / contract["design_hash"]
            / canonical_split
        )
        daily, events, run_manifest = run_retrained_information_upper_bounds(
            finalized_model_roster_path=args.finalized_model_roster,
            manifest_path=args.manifest,
            config_path=args.config,
            design_path=args.design,
            data_version_manifest_path=version_manifest,
            selection_data_version_manifest_path=selection_version_manifest,
            wide_path=data,
            quality_path=quality_data,
            output_dir=output_dir,
            mask_dir=mask_dir,
            training_seeds=args.training_seeds,
            mask_seeds=args.mask_seeds,
            coalitions=args.coalitions,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            frontier_anchor_path=args.frontier_anchors,
            max_scenarios=args.max_scenarios,
            device=args.device,
            resume=args.resume,
        )
        summary = {
            "command": args.command,
            "status": run_manifest["status"],
            "complete": run_manifest["complete"],
            "daily_rows": len(daily),
            "event_rows": len(events),
            "output_dir": str(output_dir),
            "data_version": args.data_version,
            "evaluation_split": canonical_split,
            "design_hash": contract["design_hash"],
            "attribution_estimand": "retrained_upper_bound",
        }
    else:
        canonical_split = canonical_evaluation_split(args.evaluation_split)
        version_root = args.data_root / args.data_version
        version_manifest = version_root / "version_manifest.json"
        if not version_manifest.is_file():
            raise FileNotFoundError(
                f"versioned data manifest is required: {version_manifest}"
            )
        contract = build_design_contract(
            design_path=args.design,
            manifest_path=args.manifest,
            experiment_config_path=args.config,
            data_version=args.data_version,
            evaluation_split=canonical_split,
            data_version_manifest_path=version_manifest,
        )
        data = args.data or version_root / "daily_wide.parquet"
        quality_data = args.quality_data or version_root / "daily_long.parquet"
        output = args.output or (
            PROJECT_ROOT
            / "results"
            / "analysis"
            / args.data_version
            / contract["design_hash"]
            / "training_information_metrics.csv"
        )
        result = write_training_information_metrics(
            data,
            output,
            quality_long=quality_data,
            n_neighbors=args.neighbors,
            lags=args.lags,
            n_permutations=args.permutations,
            n_bins=args.bins,
            seed=args.seed,
            deseasonalize=args.deseasonalize,
            evidence_contract=contract,
        )
        summary = {
            "command": args.command,
            "rows": len(result),
            "mi_rows": int((result["metric"] == "knn_mutual_information").sum()),
            "te_rows": int((result["metric"] == "transfer_entropy").sum()),
            "output": str(output),
            "data_version": args.data_version,
            "design_hash": contract["design_hash"],
            "fit_split": "train",
            "formal_evidence": False,
            "interpretation": "association/directional information only; not causal",
        }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
