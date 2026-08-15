#!/usr/bin/env python3
"""Run a resumable smoke/core/full experiment suite or one deterministic shard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments import (
    ExperimentRunner,
    build_experiment_grid,
)
from stream_recoverability.experiments.contracts import (
    build_design_contract,
    canonical_evaluation_split,
    file_sha256,
)
from stream_recoverability.experiments.formal_authorization import (
    authorize_roster_suite,
)
from stream_recoverability.experiments.runner import (
    LEGACY_MODEL_ALIASES,
    SUPPORTED_MODELS,
)


def _model_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    models = [
        part.strip().lower()
        for value in values
        for part in value.split(",")
        if part.strip()
    ]
    accepted = {*SUPPORTED_MODELS, *LEGACY_MODEL_ALIASES}
    unknown = sorted(set(models).difference(accepted))
    if unknown:
        raise argparse.ArgumentTypeError(f"unsupported models: {unknown}")
    return list(dict.fromkeys(models))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("smoke", "core", "full"), default="smoke")
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--training-seeds", nargs="+", type=int)
    parser.add_argument(
        "--finalized-model-roster",
        type=Path,
        help=(
            "hash-verified validation-only finalized_model_roster_v1; required "
            "for development_test core/full formal evidence"
        ),
    )
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml")
    parser.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / "configs/design_freeze_v1.yaml",
    )
    parser.add_argument("--data-version", default="published_v1")
    parser.add_argument(
        "--evaluation-split",
        choices=("validation", "test", "development_test", "confirmatory"),
        default="development_test",
    )
    parser.add_argument(
        "--frontier-anchors",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "frontier_anchors.csv",
    )
    parser.add_argument(
        "--event-catalog",
        type=Path,
        help="Frozen M7b event/control catalog; required for the full suite.",
    )
    parser.add_argument("--data", type=Path)
    parser.add_argument("--quality-data", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mask-dir", type=Path)
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
    canonical_split = canonical_evaluation_split(args.evaluation_split)
    version_root = PROJECT_ROOT / "data_versions" / args.data_version
    version_manifest = version_root / "version_manifest.json"
    if not version_root.is_dir():
        raise FileNotFoundError(
            f"declared data version directory does not exist: {version_root}"
        )
    if not version_manifest.is_file():
        raise FileNotFoundError(
            f"data version manifest is required: {version_manifest}"
        )
    manifest_value = json.loads(version_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest_value, dict):
        raise TypeError("data version manifest must be a JSON object")
    if manifest_value.get("data_version") != args.data_version:
        raise ValueError(
            "data version manifest identity mismatch: "
            f"expected {args.data_version!r}, got "
            f"{manifest_value.get('data_version')!r}"
        )
    data = args.data or version_root / "daily_wide.parquet"
    quality_data = args.quality_data or version_root / "daily_long.parquet"
    artifacts = manifest_value.get("artifacts")
    if not isinstance(artifacts, dict):
        raise TypeError("data version manifest artifacts must be a JSON object")
    for logical_name, path in (
        ("daily_wide.parquet", data),
        ("daily_long.parquet", quality_data),
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
        artifact = artifacts.get(logical_name)
        if not isinstance(artifact, dict) or not isinstance(
            artifact.get("sha256"), str
        ):
            raise TypeError(
                f"data version manifest lacks a SHA-256 for {logical_name}"
            )
        actual_digest = file_sha256(path)
        if actual_digest != artifact["sha256"]:
            raise ValueError(
                f"{logical_name} does not match data version manifest: "
                f"expected {artifact['sha256']}, got {actual_digest}"
            )
    if args.suite == "full" and args.event_catalog is None:
        raise SystemExit("--event-catalog is required for the full suite")
    if args.event_catalog is not None and not args.event_catalog.is_file():
        raise FileNotFoundError(args.event_catalog)
    if args.suite != "full" and args.event_catalog is not None:
        raise SystemExit("--event-catalog is only valid for the full suite")
    resolved_contract = build_design_contract(
        design_path=args.design,
        manifest_path=args.manifest,
        experiment_config_path=args.config,
        data_version=args.data_version,
        evaluation_split=canonical_split,
        data_version_manifest_path=version_manifest,
    )
    canonical_contract = {
        key: value
        for key, value in resolved_contract.items()
        if key != "code_provenance"
    }
    run_token = (
        Path(args.data_version)
        / resolved_contract["design_hash"]
        / canonical_split
        / args.suite
    )
    output_dir = args.output_dir or PROJECT_ROOT / "results/experiments_v2" / run_token
    mask_dir = args.mask_dir or PROJECT_ROOT / "masks/v2" / run_token
    grid = build_experiment_grid(
        args.manifest,
        args.config,
        suite=args.suite,
        data_version=args.data_version,
        evaluation_split=canonical_split,
        event_catalog_path=args.event_catalog,
        frontier_anchor_path=args.frontier_anchors,
    )
    formal_authorization = None
    is_formal_evidence_suite = (
        canonical_split == "development_test" and args.suite in {"core", "full"}
    )
    if is_formal_evidence_suite:
        if args.finalized_model_roster is None:
            raise SystemExit(
                "--finalized-model-roster is required for development_test "
                "core/full formal evidence"
            )
        selection_manifest = (
            PROJECT_ROOT / "data_versions/published_v1/version_manifest.json"
        )
        expected_models, formal_authorization = authorize_roster_suite(
            args.finalized_model_roster,
            suite=grid.suite,
            target_scope=tuple(
                dict.fromkeys(
                    target
                    for condition in grid.conditions
                    for target in condition.evaluation_variables
                )
            ),
            design_path=args.design,
            study_manifest_path=args.manifest,
            experiment_config_path=args.config,
            selection_data_version_manifest_path=selection_manifest,
        )
        if models is not None and tuple(models) != expected_models:
            raise ValueError(
                "--models cannot override the finalized formal roster: "
                f"expected={list(expected_models)}, observed={models}"
            )
        models = list(expected_models)
    elif args.finalized_model_roster is not None:
        raise ValueError(
            "--finalized-model-roster is only valid for development_test "
            "core/full formal suites"
        )
    runner = ExperimentRunner(
        grid,
        wide_path=data,
        quality_path=quality_data,
        output_dir=output_dir,
        mask_dir=mask_dir,
        config_path=args.config,
        design_path=args.design,
        manifest_path=args.manifest,
        data_version_manifest_path=version_manifest,
        models=models,
        training_seeds=args.training_seeds,
        formal_authorization=formal_authorization,
        resume=args.resume,
    )
    if runner.evidence_contract != canonical_contract:
        raise RuntimeError("preflight and runner design contracts disagree")
    daily, events = runner.run(
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        max_scenarios=args.max_scenarios,
    )
    print(
        json.dumps(
            {
                "suite": args.suite,
                "models": list(runner.models),
                "daily_rows": len(daily),
                "event_rows": len(events),
                "output_dir": str(output_dir),
                "data_version": args.data_version,
                "evaluation_split": canonical_split,
                "design_hash": runner.evidence_contract["design_hash"],
                "mask_dir": str(mask_dir),
                "data_version_manifest": str(version_manifest),
                "event_catalog": (
                    str(args.event_catalog) if args.event_catalog is not None else None
                ),
                "external_validation_status": grid.external_validation_status,
                "formal_evidence": runner.formal_evidence,
                "finalized_model_roster": (
                    runner.formal_authorization["finalized_model_roster"]
                    if runner.formal_authorization is not None
                    else None
                ),
                "expected_formal_models": (
                    list(runner.models) if runner.formal_evidence else []
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
