#!/usr/bin/env python3
"""Run or rank the frozen validation-only model-selection funnel.

Nothing produced by this script is formal, development-test, or confirmatory
evidence.  Its sole role is selecting models on the validation split.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    build_design_contract,
    load_frozen_data_versions,
    result_run_root,
)
from stream_recoverability.experiments.runner import (
    SUPPORTED_MODELS,
    TRAINABLE_MODELS,
    ExperimentRunner,
)
from stream_recoverability.experiments.selection import (
    assess_proposed_go_no_go,
    select_stage2_finalists,
)
from stream_recoverability.experiments.validation import (
    DEEP_CANDIDATES,
    TRADITIONAL_CANDIDATES,
    VALIDATION_DEEP_SEEDS,
    VALIDATION_STAGES,
    build_validation_funnel,
    select_validation_stage,
    write_validation_model_ranking,
)
from stream_recoverability.experiments.validation_finalization import (
    GO_NO_GO_SCHEMA_VERSION,
    RANKING_MANIFEST_SCHEMA_VERSION,
    STAGE2_SELECTION_MANIFEST_SCHEMA_VERSION,
    assess_proposed_versus_donor,
    execute_validation_branch_ablation,
    finalize_validation_roster,
    read_validation_event_tables,
    summarize_stage3_stability,
    validate_completed_deep_stage,
    validate_ranking_artifact,
    validate_stage2_selection_artifact,
    write_early_framework_only_decision,
    write_stage2_diagnostics,
)


def _model_list(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    models = tuple(
        dict.fromkeys(
            part.strip().lower()
            for value in values
            for part in value.split(",")
            if part.strip()
        )
    )
    return models


def _atomic_json(value: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _add_contract_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-version", default="published_v2")
    parser.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/experiments.yaml",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_DESIGN_PATH,
    )
    parser.add_argument(
        "--data-root", type=Path, default=PROJECT_ROOT / "data_versions"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "results/validation_funnel",
    )
    parser.add_argument(
        "--anchor-catalog",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "validation_anchors_v2.csv",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one frozen validation stage")
    _add_contract_arguments(run)
    run.add_argument(
        "--stage",
        choices=tuple(stage.name for stage in VALIDATION_STAGES),
        required=True,
    )
    run.add_argument(
        "--models",
        nargs="+",
        help="optional stage candidate subset; required for deep_stability finalists",
    )
    run.add_argument("--data", type=Path)
    run.add_argument("--quality-data", type=Path)
    run.add_argument(
        "--mask-root",
        type=Path,
        default=PROJECT_ROOT / "masks/validation_funnel",
    )
    run.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--shard-index", type=int, default=0)
    run.add_argument("--shard-count", type=int, default=1)
    run.add_argument("--max-scenarios", type=int)

    rank = commands.add_parser(
        "rank", help="write validation_model_ranking.csv from completed stages"
    )
    _add_contract_arguments(rank)
    rank.add_argument(
        "--event-metrics",
        type=Path,
        nargs="+",
        help=(
            "initial-stage event tables; defaults exactly to traditional and "
            "deep_single_seed"
        ),
    )
    rank.add_argument("--output", type=Path)

    select = commands.add_parser(
        "select-finalists",
        help="apply the frozen stage-2 finalist rule to validation-only artifacts",
    )
    _add_contract_arguments(select)
    select.add_argument(
        "--ranking",
        type=Path,
        help="defaults to validation_model_ranking.csv under the versioned run root",
    )
    select.add_argument(
        "--diagnostics",
        type=Path,
        required=True,
        help="one strict convergence/finite-value diagnostic row per deep candidate",
    )
    select.add_argument("--output", type=Path)

    go_no_go = commands.add_parser(
        "go-no-go",
        help="apply every frozen proposed-model continuation criterion",
    )
    _add_contract_arguments(go_no_go)
    go_no_go.add_argument(
        "--event-metrics",
        type=Path,
        nargs="+",
        help=(
            "complete validation event tables containing traditional and proposed "
            "rows; required only when proposed entered stage 3"
        ),
    )
    go_no_go.add_argument(
        "--branch-ablations",
        type=Path,
        help=(
            "validation-only one-checkpoint operational-dropout table; required "
            "only when proposed entered stage 3"
        ),
    )
    go_no_go.add_argument("--ranking", type=Path)
    go_no_go.add_argument("--stage2-selection", type=Path)
    go_no_go.add_argument("--best-traditional-model")
    go_no_go.add_argument("--output-dir", type=Path)

    diagnostics = commands.add_parser(
        "extract-diagnostics",
        help="derive strict seed-11 diagnostics from completed runner artifacts",
    )
    _add_contract_arguments(diagnostics)
    diagnostics.add_argument("--stage-dir", type=Path)
    diagnostics.add_argument("--output", type=Path)

    branch = commands.add_parser(
        "run-branch-ablation",
        help="run validation-only same-checkpoint proposed branch ablations",
    )
    _add_contract_arguments(branch)
    branch.add_argument("--stage3-dir", type=Path)
    branch.add_argument("--data", type=Path)
    branch.add_argument("--quality-data", type=Path)
    branch.add_argument(
        "--mask-root",
        type=Path,
        default=PROJECT_ROOT / "masks/validation_branch_ablation",
    )
    branch.add_argument("--output-dir", type=Path)
    branch.add_argument("--device", default="cpu")

    freeze = commands.add_parser(
        "freeze-roster",
        help="atomically issue finalized_model_roster_v1 after every gate passes",
    )
    _add_contract_arguments(freeze)
    freeze.add_argument("--ranking", type=Path)
    freeze.add_argument("--stage2-selection", type=Path)
    freeze.add_argument("--stage3-dir", type=Path)
    freeze.add_argument("--branch-ablations", type=Path)
    freeze.add_argument("--go-no-go", type=Path)
    freeze.add_argument("--output", type=Path)

    summarize = commands.add_parser(
        "summarize-stage3",
        help="write the Stage 3 stability table and proposed-versus-donor claim",
    )
    _add_contract_arguments(summarize)
    summarize.add_argument("--stage3-dir", type=Path)
    summarize.add_argument(
        "--event-metrics",
        type=Path,
        nargs="+",
        help="traditional plus Stage 3 event tables for the proposed-versus-donor claim",
    )
    summarize.add_argument("--output-dir", type=Path)
    return parser


def _contract(
    args: argparse.Namespace, *, require_version_manifest: bool
) -> tuple[dict[str, Any], Path]:
    frozen_versions = load_frozen_data_versions(args.design)
    if args.data_version != frozen_versions.primary:
        raise ValueError(
            "validation selection must use the design primary data version: "
            f"{frozen_versions.primary}"
        )
    version_root = args.data_root / args.data_version
    version_manifest = version_root / "version_manifest.json"
    if require_version_manifest and not version_manifest.is_file():
        raise FileNotFoundError(
            f"versioned data manifest is required before validation: {version_manifest}"
        )
    contract = build_design_contract(
        design_path=args.design,
        manifest_path=args.manifest,
        experiment_config_path=args.config,
        data_version=args.data_version,
        evaluation_split="validation",
        data_version_manifest_path=(
            version_manifest if version_manifest.is_file() else None
        ),
    )
    run_root = result_run_root(args.output_root, args.data_version)
    return contract, run_root


def _write_funnel_registry(
    funnel: Any, contract: dict[str, Any], run_root: Path
) -> None:
    units = funnel.mask_unit_frame()
    for key, value in contract.items():
        units[key] = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list, tuple))
            else value
        )
    _atomic_csv(units, run_root / "validation_mask_units.csv")
    _atomic_json(
        {
            "suite": "validation_funnel",
            "evaluation_split": "validation",
            "evidence_role": "model_selection_only",
            "formal_evidence": False,
            "condition_count": len(funnel.grid.conditions),
            "mask_unit_count": len(funnel.mask_units),
            "mask_units_per_condition": 5,
            "mask_seed_placeholders": list(funnel.grid.mask_seeds),
            "anchor_integration_status": "bound_centered_anchor_v1",
            "anchor_catalog_path": funnel.grid.validation_anchor_catalog_path,
            "anchor_catalog_rows": funnel.grid.validation_anchor_count,
            "anchor_ids": list(funnel.grid.validation_anchor_ids),
            "anchor_season_counts": (
                units.drop_duplicates("anchor_id")["season"]
                .value_counts()
                .sort_index()
                .to_dict()
            ),
            "stages": [stage.as_dict() for stage in funnel.stages],
            **contract,
        },
        run_root / "validation_funnel_manifest.json",
    )


def _run(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=True)
    funnel = build_validation_funnel(
        args.manifest,
        args.config,
        data_version=args.data_version,
        anchor_catalog_path=args.anchor_catalog,
        anchor_data_version=args.data_version,
    )
    stage, models = select_validation_stage(
        funnel,
        args.stage,
        models=_model_list(args.models),
    )
    unsupported = sorted(set(models).difference(SUPPORTED_MODELS))
    if unsupported:
        raise ValueError(
            "validation stage cannot run until these frozen candidates are "
            f"registered in the runner: {unsupported}"
        )

    version_root = args.data_root / args.data_version
    wide_path = args.data or version_root / "daily_wide.parquet"
    quality_path = args.quality_data or version_root / "daily_long.parquet"
    for path in (wide_path, quality_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    stage_output = run_root / args.stage
    mask_dir = result_run_root(args.mask_root, args.data_version)
    if int(args.shard_index) == 0:
        _write_funnel_registry(funnel, contract, run_root)

    selected_trainable = set(models).intersection(TRAINABLE_MODELS)
    training_seeds: tuple[int, ...] = stage.training_seeds if selected_trainable else ()
    runner = ExperimentRunner(
        funnel.grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=stage_output,
        mask_dir=mask_dir,
        config_path=args.config,
        design_path=args.design,
        manifest_path=args.manifest,
        data_version_manifest_path=version_root / "version_manifest.json",
        models=models,
        training_seeds=training_seeds,
        resume=args.resume,
    )
    canonical_contract = {
        key: value for key, value in contract.items() if key != "code_provenance"
    }
    if runner.evidence_contract != canonical_contract:
        raise RuntimeError("runner and validation funnel design contracts disagree")
    daily, events = runner.run(
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        max_scenarios=args.max_scenarios,
    )
    summary = {
        "command": "run",
        "suite": "validation_funnel",
        "stage": stage.name,
        "models": list(models),
        "training_seeds": list(training_seeds),
        "condition_count": len(funnel.grid.conditions),
        "mask_unit_count": len(funnel.mask_units),
        "anchor_catalog": str(args.anchor_catalog),
        "anchor_catalog_rows": funnel.grid.validation_anchor_count,
        "anchor_ids": list(funnel.grid.validation_anchor_ids),
        "daily_rows": len(daily),
        "event_rows": len(events),
        "output_dir": str(stage_output),
        "mask_dir": str(mask_dir),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    _atomic_json(summary, stage_output / "validation_stage_manifest.json")
    return summary


def _read_ranking_inputs(paths: Sequence[Path]) -> pd.DataFrame:
    frames = []
    for source_order, path in enumerate(paths):
        if not path.is_file():
            raise FileNotFoundError(path)
        frame = pd.read_parquet(path)
        frame["_source_order"] = source_order
        frame["_source_path"] = str(path)
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("no validation event_metrics.parquet files found")
    combined = pd.concat(frames, ignore_index=True, sort=False)
    duplicate_key = [
        "scenario_id",
        "model",
        "training_seed",
        "mask_seed",
        "station_id",
        "target",
    ]
    missing = sorted(set(duplicate_key).difference(combined.columns))
    if missing:
        raise ValueError(f"validation event tables are missing keys: {missing}")
    duplicates = combined.duplicated(duplicate_key, keep=False)
    if duplicates.any():
        comparison_columns = [
            "condition_id",
            "skill",
            "evaluation_split",
            "data_version",
        ]
        for _, group in combined.loc[duplicates].groupby(
            duplicate_key, dropna=False, sort=False
        ):
            for column in comparison_columns:
                if group[column].nunique(dropna=False) != 1:
                    raise ValueError(
                        "overlapping validation stages disagree for one model-seed unit"
                    )
        combined = combined.sort_values(
            "_source_order", kind="mergesort"
        ).drop_duplicates(duplicate_key, keep="last")
    return combined.drop(columns=["_source_order", "_source_path"])


def _validate_initial_ranking_inventory(events: pd.DataFrame) -> None:
    expected_models = set(TRADITIONAL_CANDIDATES) | set(DEEP_CANDIDATES)
    observed_models = set(events["model"].astype(str))
    if observed_models != expected_models:
        raise ValueError(
            "initial validation ranking must contain exactly traditional plus "
            "deep_single_seed candidates"
        )
    deep = events.loc[events["model"].astype(str).isin(DEEP_CANDIDATES)]
    deep_seeds = set(pd.to_numeric(deep["training_seed"], errors="coerce").dropna())
    if deep_seeds != {VALIDATION_DEEP_SEEDS[0]}:
        raise ValueError(
            "initial validation ranking rejects deep_stability seed 22/33 rows"
        )
    traditional = events.loc[events["model"].astype(str).isin(TRADITIONAL_CANDIDATES)]
    if pd.to_numeric(traditional["training_seed"], errors="coerce").notna().any():
        raise ValueError("traditional validation ranking rows must be seedless")


def _initial_ranking_paths(run_root: Path) -> tuple[Path, Path]:
    return (
        run_root / "traditional" / "event_metrics.parquet",
        run_root / "deep_single_seed" / "event_metrics.parquet",
    )


def _read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported table format for {path}; expected CSV or Parquet")


def _load_design(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        design = yaml.safe_load(handle)
    if not isinstance(design, dict):
        raise TypeError(f"expected a YAML mapping in {path}")
    return design


def _validate_validation_artifact(
    frame: pd.DataFrame,
    *,
    contract: dict[str, Any],
    artifact_name: str,
) -> None:
    required = {"evaluation_split", "data_version"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{artifact_name} is missing contract columns: {missing}")
    if frame.empty:
        raise ValueError(f"{artifact_name} is empty")
    expected = {
        "evaluation_split": "validation",
        "data_version": str(contract["data_version"]),
    }
    for column, value in expected.items():
        observed = set(frame[column].astype(str))
        if observed != {value}:
            raise ValueError(
                f"{artifact_name} {column} mismatch: observed={sorted(observed)} "
                f"expected={value!r}"
            )


def _selection_settings(design: dict[str, Any]) -> dict[str, Any]:
    try:
        rule = design["model_funnel"]["stage_2_deep_single_seed"]["retention_rule"]
    except (KeyError, TypeError) as exc:
        raise ValueError("design freeze omits the stage-2 retention rule") from exc
    if not isinstance(rule, dict):
        raise TypeError("stage-2 retention rule must be a mapping")
    return {
        "tolerance_from_best": float(rule["retain_if_within_mean_skill_of_best"]),
        "mandatory_diagnostic_candidates": tuple(
            str(value) for value in rule["mandatory_diagnostic_candidates"]
        ),
    }


def _go_no_go_settings(design: dict[str, Any]) -> dict[str, Any]:
    try:
        criteria = design["model_funnel"]["proposed_go_no_go"]["required_criteria"]
        stable = criteria["stable_90_day_gain"]
        difficult = criteria["difficult_case_gain"]
        calibration = criteria["interval_calibration"]
        stations = criteria["station_robustness"]
        ablation = criteria["branch_ablation"]
    except (KeyError, TypeError) as exc:
        raise ValueError("design freeze omits proposed go/no-go criteria") from exc
    stable_minimum = float(stable["mean_skill_gain_over_best_traditional_minimum"])
    difficult_minimum = float(difficult["mean_skill_gain_minimum"])
    if not abs(stable_minimum - difficult_minimum) <= 1e-12:
        raise ValueError(
            "current assessor requires identical frozen stable/difficult skill minima"
        )
    return {
        "skill_gain_minimum": stable_minimum,
        "coverage_bounds": tuple(
            float(value) for value in calibration["acceptable_mean_coverage"]
        ),
        "minimum_positive_stations": int(
            stations["minimum_stations_with_positive_gain"]
        ),
        "maximum_station_share": float(
            stations["maximum_single_station_share_of_positive_gain"]
        ),
        "ablation_tolerance_mae": float(ablation["numerical_tolerance_MAE"]),
    }


def _rank(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=False)
    if args.event_metrics:
        paths = tuple(args.event_metrics)
    else:
        paths = _initial_ranking_paths(run_root)
    events = _read_ranking_inputs(paths)
    _validate_initial_ranking_inventory(events)
    output = args.output or run_root / "validation_model_ranking.csv"
    ranking = write_validation_model_ranking(
        events,
        output,
        expected_data_version=args.data_version,
    )
    manifest = {
        "schema_version": RANKING_MANIFEST_SCHEMA_VERSION,
        "command": "rank",
        "models_ranked": len(ranking),
        "event_metrics": [_artifact_identity(path) for path in paths],
        "output": _artifact_identity(output),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    _atomic_json(manifest, output.with_suffix(".manifest.json"))
    return manifest


def _select_finalists(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=False)
    ranking_path = args.ranking or run_root / "validation_model_ranking.csv"
    ranking = _read_table(ranking_path)
    diagnostics = _read_table(args.diagnostics)
    _validate_validation_artifact(
        ranking,
        contract=contract,
        artifact_name="validation ranking",
    )
    _validate_validation_artifact(
        diagnostics,
        contract=contract,
        artifact_name="stage-2 diagnostics",
    )
    selected = select_stage2_finalists(
        ranking,
        diagnostics=diagnostics,
        **_selection_settings(_load_design(args.design)),
    )
    selected["data_version"] = contract["data_version"]
    output = args.output or run_root / "stage2_finalist_selection.csv"
    _atomic_csv(selected, output)
    finalists = (
        selected.loc[selected["selected_for_stability"].astype(bool), "model"]
        .astype(str)
        .tolist()
    )
    manifest = {
        "schema_version": STAGE2_SELECTION_MANIFEST_SCHEMA_VERSION,
        "command": "select-finalists",
        "selected_models": finalists,
        "ranking": _artifact_identity(ranking_path),
        "diagnostics": _artifact_identity(args.diagnostics),
        "output": _artifact_identity(output),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    _atomic_json(manifest, output.with_suffix(".manifest.json"))
    return manifest


def _go_no_go(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=False)
    ranking_path = args.ranking or run_root / "validation_model_ranking.csv"
    stage2_path = args.stage2_selection or run_root / "stage2_finalist_selection.csv"
    ranking, _ = validate_ranking_artifact(ranking_path, expected_contract=contract)
    _, finalists, _ = validate_stage2_selection_artifact(
        stage2_path,
        ranking=ranking,
        ranking_path=ranking_path,
        design_path=args.design,
        expected_contract=contract,
    )
    output_dir = args.output_dir or run_root / "proposed_go_no_go"
    if "proposed" not in finalists:
        if args.event_metrics or args.branch_ablations is not None:
            raise ValueError(
                "proposed did not enter stage 3; performance and branch tables "
                "must not be supplied to the early framework-only path"
            )
        return write_early_framework_only_decision(
            ranking_path=ranking_path,
            stage2_selection_path=stage2_path,
            output_dir=output_dir,
            design_path=args.design,
            expected_contract=contract,
        )
    if not args.event_metrics or args.branch_ablations is None:
        raise ValueError(
            "proposed entered stage 3; --event-metrics and --branch-ablations "
            "are both required"
        )
    events = _read_ranking_inputs(tuple(args.event_metrics))
    _validate_validation_artifact(
        events,
        contract=contract,
        artifact_name="go/no-go event metrics",
    )
    ablations = _read_table(args.branch_ablations)
    _validate_validation_artifact(
        ablations,
        contract=contract,
        artifact_name="branch ablations",
    )
    decision = assess_proposed_go_no_go(
        events,
        ablations,
        best_traditional_model=args.best_traditional_model,
        **_go_no_go_settings(_load_design(args.design)),
    )
    criteria_path = output_dir / "proposed_go_no_go_criteria.csv"
    decision_path = output_dir / "proposed_go_no_go_decision.json"
    criteria = decision.criteria.copy()
    criteria["evidence_role"] = "model_selection_only"
    criteria["data_version"] = contract["data_version"]
    _atomic_csv(criteria, criteria_path)
    payload = {
        "schema_version": GO_NO_GO_SCHEMA_VERSION,
        "command": "go-no-go",
        "assessment_mode": "full_stage3",
        "status": "complete",
        "passed": decision.passed,
        "decision": "include_proposed_formally"
        if decision.passed
        else "framework_only",
        "best_traditional_model": decision.best_traditional_model,
        "evidence": decision.evidence,
        "criteria": _artifact_identity(criteria_path),
        "event_metrics": [_artifact_identity(path) for path in args.event_metrics],
        "branch_ablations": _artifact_identity(args.branch_ablations),
        "stage2_selection": _artifact_identity(stage2_path),
        "stage2_selection_manifest": _artifact_identity(
            stage2_path.with_suffix(".manifest.json")
        ),
        "ranking": _artifact_identity(ranking_path),
        "stage2_selected_models": list(finalists),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
    }
    _atomic_json(payload, decision_path)
    return {**payload, "output": str(decision_path)}


def _artifact_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
    }


def _extract_diagnostics(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=True)
    stage_dir = args.stage_dir or run_root / "deep_single_seed"
    output = args.output or run_root / "stage2_diagnostics.csv"
    return write_stage2_diagnostics(stage_dir, output, expected_contract=contract)


def _run_branch_ablation(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=True)
    stage3_dir = args.stage3_dir or run_root / "deep_stability"
    stage3_manifest_path = stage3_dir / "run_manifest.json"
    if not stage3_manifest_path.is_file():
        raise FileNotFoundError(stage3_manifest_path)
    stage3_manifest = json.loads(stage3_manifest_path.read_text(encoding="utf-8"))
    models = tuple(str(model) for model in stage3_manifest.get("models", ()))
    version_root = args.data_root / args.data_version
    wide_path = args.data or version_root / "daily_wide.parquet"
    quality_path = args.quality_data or version_root / "daily_long.parquet"
    output_dir = args.output_dir or run_root / "branch_ablation"
    mask_dir = result_run_root(args.mask_root, args.data_version)
    return execute_validation_branch_ablation(
        stage3_dir=stage3_dir,
        stage3_models=models,
        expected_contract=contract,
        manifest_path=args.manifest,
        config_path=args.config,
        design_path=args.design,
        data_version_manifest_path=version_root / "version_manifest.json",
        wide_path=wide_path,
        quality_path=quality_path,
        anchor_catalog_path=args.anchor_catalog,
        output_dir=output_dir,
        mask_dir=mask_dir,
        device=args.device,
    )


def _freeze_roster(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=True)
    ranking = args.ranking or run_root / "validation_model_ranking.csv"
    stage2 = args.stage2_selection or run_root / "stage2_finalist_selection.csv"
    stage3 = args.stage3_dir or run_root / "deep_stability"
    branch = args.branch_ablations or (
        run_root / "proposed_go_no_go" / "branch_ablation_not_applicable.json"
        if (
            run_root / "proposed_go_no_go" / "branch_ablation_not_applicable.json"
        ).is_file()
        else run_root / "branch_ablation" / "branch_ablation_metrics.parquet"
    )
    go_no_go = (
        args.go_no_go
        or run_root / "proposed_go_no_go" / "proposed_go_no_go_decision.json"
    )
    output = args.output or run_root / "finalized_model_roster.json"
    return finalize_validation_roster(
        ranking_path=ranking,
        stage2_selection_path=stage2,
        stage3_dir=stage3,
        branch_metrics_path=branch,
        go_no_go_path=go_no_go,
        output_path=output,
        design_path=args.design,
        study_manifest_path=args.manifest,
        experiment_config_path=args.config,
        data_version_manifest_path=(
            args.data_root / args.data_version / "version_manifest.json"
        ),
        anchor_catalog_path=args.anchor_catalog,
        expected_contract=contract,
    )


def _summarize_stage3(args: argparse.Namespace) -> dict[str, Any]:
    contract, run_root = _contract(args, require_version_manifest=True)
    stage3 = args.stage3_dir or run_root / "deep_stability"
    stage_manifest = json.loads(
        (stage3 / "validation_stage_manifest.json").read_text(encoding="utf-8")
    )
    models = tuple(str(model) for model in stage_manifest.get("models", ()))
    events, checkpoints, _ = validate_completed_deep_stage(
        stage3,
        expected_models=models,
        expected_seeds=VALIDATION_DEEP_SEEDS,
        expected_contract=contract,
        expected_stage_name="deep_stability",
    )
    output_dir = args.output_dir or run_root
    stability = summarize_stage3_stability(
        events,
        checkpoints,
        expected_data_version=str(contract["data_version"]),
    )
    stability_path = output_dir / "stage3_stability.csv"
    _atomic_csv(stability, stability_path)
    event_paths = args.event_metrics or [
        run_root / "traditional" / "event_metrics.parquet",
        stage3 / "event_metrics.parquet",
    ]
    comparison = assess_proposed_versus_donor(read_validation_event_tables(event_paths))
    comparison_path = output_dir / "proposed_versus_donor.json"
    _atomic_json(
        {key: value for key, value in comparison.items() if key != "cells"},
        comparison_path,
    )
    cells_path = output_dir / "proposed_versus_donor_cells.csv"
    _atomic_csv(pd.DataFrame(comparison["cells"]), cells_path)
    return {
        "stability": str(stability_path),
        "proposed_versus_donor": str(comparison_path),
        "claim": comparison["claim"],
        "budget_unstable_models": sorted(
            set(stability.loc[stability["hit_epoch_limit"], "model"].astype(str))
        ),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        summary = _run(args)
    elif args.command == "rank":
        summary = _rank(args)
    elif args.command == "select-finalists":
        summary = _select_finalists(args)
    elif args.command == "go-no-go":
        summary = _go_no_go(args)
    elif args.command == "extract-diagnostics":
        summary = _extract_diagnostics(args)
    elif args.command == "run-branch-ablation":
        summary = _run_branch_ablation(args)
    elif args.command == "summarize-stage3":
        summary = _summarize_stage3(args)
    else:
        summary = _freeze_roster(args)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
