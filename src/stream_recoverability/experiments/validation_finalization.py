"""Fail-closed finalization of the validation-only model-selection funnel.

This module is deliberately separate from the experiment runner.  It consumes
completed validation artifacts, verifies their contracts and file identities,
and is the only implementation allowed to issue a finalized model roster.
Nothing here turns validation output into formal performance evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.analysis.frontiers import select_best_simple_baselines

from .contracts import (
    LEGACY_IDENTITY_FIELDS,
    load_frozen_data_versions,
    validate_data_version_inputs,
)
from .model_registry import load_frozen_model_design
from .selection import assess_proposed_go_no_go, select_stage2_finalists
from .validation import (
    DEEP_CANDIDATES,
    STATION_OUTAGE_STRATUM,
    TRADITIONAL_CANDIDATES,
    VALIDATION_DEEP_SEEDS,
    VALIDATION_MASK_SEEDS,
    VALIDATION_STATIONS,
    rank_validation_models,
    validation_anchor_catalog_identity,
    validation_condition_stratum,
)

FINALIZED_MODEL_ROSTER_SCHEMA_VERSION = "finalized_model_roster_v1"
RANKING_MANIFEST_SCHEMA_VERSION = "validation_model_ranking_manifest_v1"
DIAGNOSTICS_MANIFEST_SCHEMA_VERSION = "validation_stage2_diagnostics_manifest_v1"
STAGE2_SELECTION_MANIFEST_SCHEMA_VERSION = "validation_stage2_selection_manifest_v1"
BRANCH_ABLATION_MANIFEST_SCHEMA_VERSION = "validation_branch_ablation_manifest_v1"
BRANCH_ABLATION_NOT_APPLICABLE_SCHEMA_VERSION = (
    "validation_branch_ablation_not_applicable_v1"
)
GO_NO_GO_SCHEMA_VERSION = "proposed_go_no_go_v1"

STAGE2_SEED = 11
BRANCH_ABLATION_GAPS = (10, 90, 180)
BRANCH_ABLATION_COMBINATIONS = (
    "S0+A+B+C+D",
    "S0+B+C+D",
    "S0+A+C+D",
    "S0+A+B+D",
    "S0+A+B+C",
)
ALL_INFORMATION_COMBINATIONS = (
    "S0",
    "S0+D",
    "S0+C",
    "S0+C+D",
    "S0+B",
    "S0+B+D",
    "S0+B+C",
    "S0+B+C+D",
    "S0+A",
    "S0+A+D",
    "S0+A+C",
    "S0+A+C+D",
    "S0+A+B",
    "S0+A+B+D",
    "S0+A+B+C",
    "S0+A+B+C+D",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_CONTRACT_FIELDS = (
    "design_version",
    "data_version",
    "evaluation_split",
    "mask_schema_version",
    "model_schema_version",
    "statistics_schema_version",
)
_LEGACY_DEEP_NAMES = frozenset({"brits", "saits"})


class _DuplicateJSONKey(ValueError):
    pass


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    try:
        value = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON artifact: {source}") from error
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON mapping in {source}")
    return value


def _read_table(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(source)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(source)
    raise ValueError(f"unsupported table format: {source}")


def _strict_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError(f"{field} must be a strict boolean")


def _canonical_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(set(_CANONICAL_CONTRACT_FIELDS).difference(contract))
    if missing:
        raise ValueError(f"canonical evidence contract is missing fields: {missing}")
    result = {field: contract[field] for field in _CANONICAL_CONTRACT_FIELDS}
    if result["evaluation_split"] != "validation":
        raise ValueError("validation finalization rejects non-validation contracts")
    if not isinstance(result["data_version"], str) or not result["data_version"]:
        raise ValueError("validation finalization requires a data version")
    return json.loads(json.dumps(result))


def _validate_contract(
    value: Mapping[str, Any], expected_contract: Mapping[str, Any], *, context: str
) -> None:
    expected = _canonical_contract(expected_contract)
    mismatches = {
        field: (value.get(field), expected[field])
        for field in _CANONICAL_CONTRACT_FIELDS
        if value.get(field) != expected[field]
    }
    if mismatches:
        raise ValueError(f"{context} evidence contract mismatch: {mismatches}")


def _validate_selection_labels(value: Mapping[str, Any], *, context: str) -> None:
    if value.get("evaluation_split") != "validation":
        raise ValueError(f"{context} must use evaluation_split=validation")
    if value.get("evidence_role") != "model_selection_only":
        raise ValueError(f"{context} must use evidence_role=model_selection_only")
    if value.get("formal_evidence") is not False:
        raise ValueError(f"{context} must declare formal_evidence=false")


def _validate_relevant_source_clean(
    contract: Mapping[str, Any], *, context: str
) -> None:
    provenance = contract.get("code_provenance")
    if not isinstance(provenance, Mapping):
        raise TypeError(f"{context} is missing code_provenance")


def _portable_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_artifact_path(value: str, *, relative_to: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    repository_candidate = REPOSITORY_ROOT / candidate
    local_candidate = relative_to / candidate
    existing = [
        path for path in (repository_candidate, local_candidate) if path.is_file()
    ]
    if len(existing) > 1 and existing[0].resolve() != existing[1].resolve():
        raise ValueError(f"ambiguous artifact path: {value}")
    return existing[0] if existing else repository_candidate


def _file_identity(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    return {
        "path": _portable_path(source),
        "bytes": source.stat().st_size,
    }


def _verify_file_identity(
    value: object, *, relative_to: Path, context: str
) -> tuple[Path, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} file identity must be a mapping")
    path_value = value.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{context} file identity is missing path")
    path = _resolve_artifact_path(path_value, relative_to=relative_to)
    if not path.is_file():
        raise FileNotFoundError(f"{context} artifact does not exist: {path}")
    size = value.get("size", value.get("bytes"))
    if size is not None and int(size) != path.stat().st_size:
        raise ValueError(f"{context} artifact byte count does not match")
    return path, ""


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _immutable_json(value: Mapping[str, Any], path: Path) -> None:
    """Atomically create ``path`` without any overwrite race."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite finalized roster: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FileExistsError(
                f"refusing to overwrite finalized roster: {path}"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _expected_scenario_ids(data_version: str = "published_v1") -> set[str]:
    version_suffix = (
        "" if data_version == "published_v1" else f"-{data_version.upper()}"
    )
    result: set[str] = set()
    for station in VALIDATION_STATIONS:
        condition_ids = (
            f"VAL-PNT-{station}-T-P30",
            f"VAL-BLK1-{station}-T-D010",
            f"VAL-BLK1-{station}-T-D030",
            f"VAL-BLK1-{station}-T-D090",
            f"VAL-BLK1-{station}-T-D180",
            f"VAL-BLK1-{station}-TFL-D090",
            f"VAL-SITE-{station}-HYDROONLY-D090",
        )
        for condition_id in condition_ids:
            for seed in VALIDATION_MASK_SEEDS:
                result.add(f"{condition_id}{version_suffix}-VALIDATION-R{seed:04d}")
    return result


def _expected_branch_scenario_ids(data_version: str = "published_v1") -> set[str]:
    version_suffix = (
        "" if data_version == "published_v1" else f"-{data_version.upper()}"
    )
    return {
        f"VAL-BLK1-{station}-T-D{gap:03d}{version_suffix}-VALIDATION-R{seed:04d}"
        for station in VALIDATION_STATIONS
        for seed in VALIDATION_MASK_SEEDS
        for gap in BRANCH_ABLATION_GAPS
    }


def _training_seed_key(model: str, seed: int) -> str:
    return f"{model}:{seed}"


def _validate_checkpoint_summary(
    summary: Mapping[str, Any],
    *,
    model: str,
    seed: int,
    stage_dir: Path,
) -> dict[str, Any]:
    if summary.get("model") != model or int(summary.get("training_seed", -1)) != seed:
        raise ValueError(f"checkpoint metadata identity mismatch for {model}/{seed}")
    if summary.get("checkpoint_contract_valid") is not True:
        raise ValueError(f"checkpoint contract is invalid for {model}/{seed}")
    checkpoint_path, checkpoint_sha = _verify_file_identity(
        summary.get("checkpoint"),
        relative_to=stage_dir,
        context=f"{model}/{seed} checkpoint",
    )
    if model in {"brits_ref", "saits_ref", "csdi"}:
        _verify_file_identity(
            summary.get("checkpoint_sidecar"),
            relative_to=stage_dir,
            context=f"{model}/{seed} checkpoint sidecar",
        )
    best_epoch = pd.to_numeric(
        pd.Series([summary.get("best_epoch")]), errors="coerce"
    ).iloc[0]
    epochs_run = pd.to_numeric(
        pd.Series([summary.get("epochs_run")]), errors="coerce"
    ).iloc[0]
    if (
        not np.isfinite(best_epoch)
        or not float(best_epoch).is_integer()
        or not np.isfinite(epochs_run)
        or not float(epochs_run).is_integer()
        or not 1 <= int(best_epoch) <= int(epochs_run)
    ):
        raise ValueError(f"checkpoint epoch diagnostics are invalid for {model}/{seed}")
    hit_epoch_limit = _strict_bool(
        summary.get("hit_epoch_limit"), field=f"{model}/{seed} hit_epoch_limit"
    )
    return {
        "model": model,
        "training_seed": seed,
        "best_epoch": int(best_epoch),
        "epochs_run": int(epochs_run),
        "hit_epoch_limit": hit_epoch_limit,
        "checkpoint_path": checkpoint_path,
        "checkpoint_sha256": checkpoint_sha,
    }


def validate_completed_deep_stage(
    stage_dir: str | Path,
    *,
    expected_models: Sequence[str],
    expected_seeds: Sequence[int],
    expected_contract: Mapping[str, Any],
    expected_stage_name: str,
) -> tuple[pd.DataFrame, dict[tuple[str, int], dict[str, Any]], dict[str, Any]]:
    """Verify a complete 105-scenario deep validation stage."""

    directory = Path(stage_dir)
    models = tuple(
        dict.fromkeys(str(model).strip().lower() for model in expected_models)
    )
    seeds = tuple(dict.fromkeys(int(seed) for seed in expected_seeds))
    if not models or not seeds:
        raise ValueError("deep-stage validation requires models and training seeds")
    legacy = sorted(set(models).intersection(_LEGACY_DEEP_NAMES))
    if legacy:
        raise ValueError(f"legacy deep model names are prohibited: {legacy}")
    run_manifest_path = directory / "run_manifest.json"
    stage_manifest_path = directory / "validation_stage_manifest.json"
    events_path = directory / "event_metrics.parquet"
    run_manifest = _read_json(run_manifest_path)
    stage_manifest = _read_json(stage_manifest_path)
    _validate_contract(
        run_manifest, expected_contract, context="deep-stage run manifest"
    )
    _validate_contract(
        stage_manifest, expected_contract, context="validation-stage manifest"
    )
    _validate_selection_labels(stage_manifest, context="validation-stage manifest")
    if stage_manifest.get("stage") != expected_stage_name:
        raise ValueError("validation-stage manifest has the wrong stage name")
    if set(map(str, stage_manifest.get("models", ()))) != set(models):
        raise ValueError("validation-stage manifest model set is not frozen")
    if tuple(map(int, stage_manifest.get("training_seeds", ()))) != seeds:
        raise ValueError("validation-stage manifest training seeds are not frozen")
    if (
        run_manifest.get("evaluation_split") != "validation"
        or run_manifest.get("evidence_role") != "model_selection_only"
    ):
        raise ValueError("deep-stage run manifest is not validation-only")
    if set(map(str, run_manifest.get("models", ()))) != set(models):
        raise ValueError("deep-stage run manifest model set is not frozen")
    if tuple(map(int, run_manifest.get("training_seeds", ()))) != seeds:
        raise ValueError("deep-stage run manifest training seeds are not frozen")

    scenario_ids = _expected_scenario_ids(str(expected_contract["data_version"]))
    run_keys = {_training_seed_key(model, seed) for model in models for seed in seeds}
    expected_units = {
        f"{scenario_id}|{run_key}"
        for scenario_id in scenario_ids
        for run_key in run_keys
    }
    required_flags = (
        "run_unit_complete",
        "evidence_complete",
        "finite_predictions",
        "finite_event_metrics",
        "checkpoint_contract_complete",
    )
    failed_flags = [
        name for name in required_flags if run_manifest.get(name) is not True
    ]
    if failed_flags:
        raise ValueError(f"deep-stage completion flags failed: {failed_flags}")
    if run_manifest.get("grid_scenario_count") != len(scenario_ids):
        raise ValueError("deep-stage run manifest does not cover 105 scenarios")
    if run_manifest.get("selected_scenarios") != len(scenario_ids):
        raise ValueError("deep-stage invocation selected fewer than 105 scenarios")
    unit_fields = (
        "expected_run_unit_keys",
        "completed_run_unit_keys",
        "expected_evidence_run_unit_keys",
        "completed_evidence_run_unit_keys",
        "finite_prediction_run_unit_keys",
        "finite_event_metric_run_unit_keys",
        "checkpoint_required_run_unit_keys",
        "checkpoint_valid_run_unit_keys",
    )
    for field in unit_fields:
        if set(map(str, run_manifest.get(field, ()))) != expected_units:
            raise ValueError(f"deep-stage {field} differs from the frozen run units")
    if run_manifest.get("retryable_run_unit_keys") not in ([], ()):
        raise ValueError("deep-stage contains retryable run units")

    statuses = sorted((directory / "scenarios").glob("*/status.json"))
    if {path.parent.name for path in statuses} != scenario_ids:
        raise ValueError("deep-stage scenario status inventory is incomplete")
    contract_checkpoint_hashes: dict[tuple[str, int], set[str]] = {
        (model, seed): set() for model in models for seed in seeds
    }
    for status_path in statuses:
        status = _read_json(status_path)
        _validate_contract(
            status, expected_contract, context=f"scenario {status_path.parent.name}"
        )
        if status.get("scenario_id") != status_path.parent.name:
            raise ValueError("scenario status path and identity disagree")
        if status.get("status") != "complete":
            raise ValueError(f"scenario is not complete: {status_path.parent.name}")
        if set(map(str, status.get("completed_runs", ()))) != run_keys:
            raise ValueError("scenario completed run keys differ from frozen stage")
        if status.get("retryable_run_keys") not in ([], ()):
            raise ValueError("scenario status contains retryable runs")
        contracts = status.get("run_contracts")
        if not isinstance(contracts, Mapping) or set(contracts) != run_keys:
            raise ValueError("scenario run contracts are incomplete")
        for model in models:
            for seed in seeds:
                run_key = _training_seed_key(model, seed)
                run_contract = contracts[run_key]
                if not isinstance(run_contract, Mapping):
                    raise TypeError("scenario run contract must be a mapping")
                _validate_contract(
                    run_contract,
                    expected_contract,
                    context=f"scenario run contract {status_path.parent.name}/{run_key}",
                )
                if (
                    run_contract.get("model") != model
                    or int(run_contract.get("training_seed", -1)) != seed
                ):
                    raise ValueError("scenario run contract model/seed mismatch")
                checkpoint = run_contract.get("checkpoint")
                _, digest = _verify_file_identity(
                    checkpoint,
                    relative_to=directory,
                    context=f"scenario checkpoint {status_path.parent.name}/{run_key}",
                )
                contract_checkpoint_hashes[(model, seed)].add(digest)

    summaries = run_manifest.get("training_checkpoints")
    if not isinstance(summaries, list):
        raise TypeError("deep-stage run manifest is missing checkpoint metadata")
    by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for summary in summaries:
        if not isinstance(summary, Mapping):
            raise TypeError("checkpoint metadata rows must be mappings")
        key = (str(summary.get("model")), int(summary.get("training_seed", -1)))
        if key in by_key:
            raise ValueError(f"duplicate checkpoint metadata for {key}")
        by_key[key] = summary
    expected_checkpoint_keys = set(contract_checkpoint_hashes)
    if set(by_key) != expected_checkpoint_keys:
        raise ValueError("checkpoint metadata model/seed inventory is incomplete")
    checkpoint_metadata: dict[tuple[str, int], dict[str, Any]] = {}
    for key in sorted(expected_checkpoint_keys):
        metadata = _validate_checkpoint_summary(
            by_key[key], model=key[0], seed=key[1], stage_dir=directory
        )
        if contract_checkpoint_hashes[key] != {metadata["checkpoint_sha256"]}:
            raise ValueError(
                f"checkpoint identity is inconsistent across units for {key}"
            )
        checkpoint_metadata[key] = metadata

    events = _read_table(events_path)
    required_event_columns = {
        "scenario_id",
        "condition_id",
        "model",
        "training_seed",
        "mask_seed",
        "station_id",
        "target",
        "MAE",
        "RMSE",
        "finite_predictions",
        "finite_validation_score",
        "best_epoch",
        "epochs_run",
        "hit_epoch_limit",
        "evaluation_split",
        "evidence_role",
        "data_version",
    }
    missing_columns = sorted(required_event_columns.difference(events.columns))
    if missing_columns:
        raise ValueError(f"deep-stage event metrics omit columns: {missing_columns}")
    if len(events) != len(expected_units):
        raise ValueError("deep-stage event metrics do not contain one row per run unit")
    event_units = {
        f"{row.scenario_id}|{row.model}:{int(row.training_seed)}"
        for row in events[["scenario_id", "model", "training_seed"]].itertuples(
            index=False
        )
    }
    if (
        event_units != expected_units
        or events.duplicated(
            ["scenario_id", "model", "training_seed", "station_id", "target"]
        ).any()
    ):
        raise ValueError(
            "deep-stage event metrics contain missing or duplicate run units"
        )
    if set(events["scenario_id"].astype(str)) != scenario_ids:
        raise ValueError("deep-stage event scenario inventory is not frozen")
    if not events["target"].astype(str).eq("T").all():
        raise ValueError("deep-stage event metrics must target T")
    for field, expected in (
        ("evaluation_split", "validation"),
        ("evidence_role", "model_selection_only"),
        ("data_version", expected_contract["data_version"]),
    ):
        if set(events[field].astype(str)) != {str(expected)}:
            raise ValueError(f"deep-stage event {field} mismatch")
    numeric = events[["MAE", "RMSE"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("deep-stage event metrics contain nonfinite scores")
    for field in ("finite_predictions", "finite_validation_score"):
        if not all(
            _strict_bool(value, field=f"event {field}") for value in events[field]
        ):
            raise ValueError(f"deep-stage event {field} contains false values")
    for (model, seed), group in events.groupby(["model", "training_seed"], sort=True):
        key = (str(model), int(seed))
        metadata = checkpoint_metadata[key]
        for field in ("best_epoch", "epochs_run"):
            values = pd.to_numeric(group[field], errors="coerce")
            if not np.isfinite(values).all() or set(values.astype(int)) != {
                metadata[field]
            }:
                raise ValueError(f"event and checkpoint {field} disagree for {key}")
        hit_values = {
            _strict_bool(value, field=f"event hit_epoch_limit {key}")
            for value in group["hit_epoch_limit"]
        }
        if hit_values != {metadata["hit_epoch_limit"]}:
            raise ValueError(f"event and checkpoint hit_epoch_limit disagree for {key}")
    return (
        events,
        checkpoint_metadata,
        {
            "run_manifest": run_manifest,
            "stage_manifest": stage_manifest,
            "run_manifest_path": run_manifest_path,
            "stage_manifest_path": stage_manifest_path,
            "events_path": events_path,
        },
    )


def extract_stage2_diagnostics(
    stage_dir: str | Path, *, expected_contract: Mapping[str, Any]
) -> pd.DataFrame:
    """Derive exactly one diagnostic row for every frozen deep candidate."""

    events, checkpoints, _ = validate_completed_deep_stage(
        stage_dir,
        expected_models=DEEP_CANDIDATES,
        expected_seeds=(STAGE2_SEED,),
        expected_contract=expected_contract,
        expected_stage_name="deep_single_seed",
    )
    rows: list[dict[str, Any]] = []
    for model in DEEP_CANDIDATES:
        group = events.loc[events["model"].astype(str).eq(model)]
        metadata = checkpoints[(model, STAGE2_SEED)]
        rows.append(
            {
                "model": model,
                "finite_predictions": bool(
                    all(
                        _strict_bool(value, field=f"{model} finite_predictions")
                        for value in group["finite_predictions"]
                    )
                ),
                "finite_validation_score": bool(
                    all(
                        _strict_bool(value, field=f"{model} finite_validation_score")
                        for value in group["finite_validation_score"]
                    )
                ),
                "best_epoch": metadata["best_epoch"],
                "epochs_run": metadata["epochs_run"],
                "hit_epoch_limit": metadata["hit_epoch_limit"],
                "training_seed": STAGE2_SEED,
                "checkpoint_path": _portable_path(metadata["checkpoint_path"]),
                "checkpoint_sha256": metadata["checkpoint_sha256"],
                "event_rows": len(group),
                "evaluation_split": "validation",
                "evidence_role": "model_selection_only",
                "formal_evidence": False,
                "data_version": expected_contract["data_version"],
            }
        )
    result = pd.DataFrame(rows)
    if tuple(result["model"]) != DEEP_CANDIDATES:
        raise AssertionError("diagnostic model ordering changed unexpectedly")
    return result


def write_stage2_diagnostics(
    stage_dir: str | Path,
    output_path: str | Path,
    *,
    expected_contract: Mapping[str, Any],
) -> dict[str, Any]:
    output = Path(output_path)
    diagnostics = extract_stage2_diagnostics(
        stage_dir, expected_contract=expected_contract
    )
    _atomic_csv(diagnostics, output)
    directory = Path(stage_dir)
    manifest = {
        "schema_version": DIAGNOSTICS_MANIFEST_SCHEMA_VERSION,
        "stage": "deep_single_seed",
        "models": list(DEEP_CANDIDATES),
        "training_seed": STAGE2_SEED,
        "run_manifest": _file_identity(directory / "run_manifest.json"),
        "stage_manifest": _file_identity(directory / "validation_stage_manifest.json"),
        "event_metrics": _file_identity(directory / "event_metrics.parquet"),
        "output": _file_identity(output),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **_canonical_contract(expected_contract),
        "code_provenance": json.loads(
            json.dumps(expected_contract.get("code_provenance"))
        ),
    }
    _atomic_json(manifest, output.with_suffix(".manifest.json"))
    return manifest


def read_validation_event_tables(paths: Sequence[str | Path]) -> pd.DataFrame:
    """Read stage tables while rejecting conflicting overlap."""

    frames: list[pd.DataFrame] = []
    for source_order, raw_path in enumerate(paths):
        path = Path(raw_path)
        frame = _read_table(path).copy()
        frame["_source_order"] = source_order
        frame["_source_path"] = str(path)
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("no validation event metric tables were supplied")
    combined = pd.concat(frames, ignore_index=True, sort=False)
    key = [
        "scenario_id",
        "model",
        "training_seed",
        "mask_seed",
        "station_id",
        "target",
    ]
    missing = sorted(set(key).difference(combined.columns))
    if missing:
        raise ValueError(f"validation event tables omit identity keys: {missing}")
    duplicates = combined.duplicated(key, keep=False)
    if duplicates.any():
        comparison_columns = (
            "condition_id",
            "skill",
            "MAE",
            "RMSE",
            "evaluation_split",
            "data_version",
        )
        for _, group in combined.loc[duplicates].groupby(key, dropna=False, sort=False):
            for column in comparison_columns:
                if column not in group or group[column].nunique(dropna=False) != 1:
                    raise ValueError(
                        "overlapping validation event tables disagree for one run unit"
                    )
        combined = combined.sort_values(
            "_source_order", kind="mergesort"
        ).drop_duplicates(key, keep="last")
    return combined.drop(columns=["_source_order", "_source_path"])


def _artifact_from_manifest(
    manifest: Mapping[str, Any],
    field: str,
    *,
    manifest_path: Path,
) -> Path:
    path, _ = _verify_file_identity(
        manifest.get(field),
        relative_to=manifest_path.parent,
        context=f"{manifest_path.name} {field}",
    )
    return path


def validate_ranking_artifact(
    ranking_path: str | Path,
    *,
    expected_contract: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recompute the frozen ranking from hash-bound input event tables."""

    path = Path(ranking_path)
    manifest_path = path.with_suffix(".manifest.json")
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != RANKING_MANIFEST_SCHEMA_VERSION:
        raise ValueError("validation ranking manifest schema is not frozen")
    _validate_contract(manifest, expected_contract, context="ranking manifest")
    _validate_selection_labels(manifest, context="ranking manifest")
    output_path = _artifact_from_manifest(
        manifest, "output", manifest_path=manifest_path
    )
    if output_path.resolve() != path.resolve():
        raise ValueError("ranking manifest points to a different output")
    raw_inputs = manifest.get("event_metrics")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ValueError("ranking manifest requires hash-bound event inputs")
    input_paths = [
        _verify_file_identity(
            identity,
            relative_to=manifest_path.parent,
            context="ranking event input",
        )[0]
        for identity in raw_inputs
    ]
    events = read_validation_event_tables(input_paths)
    expected = rank_validation_models(
        events,
        expected_data_version=str(expected_contract["data_version"]),
    )
    ranking = _read_table(path)

    def _scientific_ranking(frame: pd.DataFrame) -> pd.DataFrame:
        drop = [column for column in frame.columns if column in LEGACY_IDENTITY_FIELDS]
        return frame.drop(columns=drop).reset_index(drop=True)

    try:
        pd.testing.assert_frame_equal(
            _scientific_ranking(ranking),
            _scientific_ranking(expected),
            check_dtype=False,
            check_exact=False,
            atol=1e-12,
            rtol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            "ranking CSV does not equal the deterministic recomputation"
        ) from error
    expected_models = set(TRADITIONAL_CANDIDATES) | set(DEEP_CANDIDATES)
    if set(ranking["model"].astype(str)) != expected_models:
        raise ValueError(
            "ranking does not contain the frozen stage-1/stage-2 candidates"
        )
    traditional = ranking.loc[ranking["model"].astype(str).isin(TRADITIONAL_CANDIDATES)]
    deep = ranking.loc[ranking["model"].astype(str).isin(DEEP_CANDIDATES)]
    if not traditional["validation_stage"].astype(str).eq("traditional").all():
        raise ValueError("traditional ranking rows have the wrong validation stage")
    if not deep["validation_stage"].astype(str).eq("deep_single_seed").all():
        raise ValueError("deep ranking rows are not the seed-11 stage")
    if set(deep["training_seeds"].astype(str)) != {"[11]"}:
        raise ValueError("deep ranking rows are not frozen to seed 11")
    return ranking, manifest


def _selection_settings(design_path: str | Path) -> dict[str, Any]:
    with Path(design_path).open(encoding="utf-8") as handle:
        design = yaml.safe_load(handle)
    if not isinstance(design, Mapping):
        raise TypeError("design freeze must be a mapping")
    try:
        rule = design["model_funnel"]["stage_2_deep_single_seed"]["retention_rule"]
    except (KeyError, TypeError) as error:
        raise ValueError("design freeze omits the stage-2 retention rule") from error
    if not isinstance(rule, Mapping):
        raise TypeError("stage-2 retention rule must be a mapping")
    return {
        "tolerance_from_best": float(rule["retain_if_within_mean_skill_of_best"]),
        "mandatory_diagnostic_candidates": tuple(
            str(value) for value in rule["mandatory_diagnostic_candidates"]
        ),
    }


def _go_no_go_settings(design_path: str | Path) -> dict[str, Any]:
    with Path(design_path).open(encoding="utf-8") as handle:
        design = yaml.safe_load(handle)
    if not isinstance(design, Mapping):
        raise TypeError("design freeze must be a mapping")
    try:
        criteria = design["model_funnel"]["proposed_go_no_go"]["required_criteria"]
        stable = criteria["stable_90_day_gain"]
        difficult = criteria["difficult_case_gain"]
        calibration = criteria["interval_calibration"]
        stations = criteria["station_robustness"]
        ablation = criteria["branch_ablation"]
    except (KeyError, TypeError) as error:
        raise ValueError("design freeze omits proposed go/no-go criteria") from error
    stable_minimum = float(stable["mean_skill_gain_over_best_traditional_minimum"])
    difficult_minimum = float(difficult["mean_skill_gain_minimum"])
    if not abs(stable_minimum - difficult_minimum) <= 1e-12:
        raise ValueError("go/no-go assessor requires identical frozen gain minima")
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


def validate_stage2_selection_artifact(
    selection_path: str | Path,
    *,
    ranking: pd.DataFrame,
    ranking_path: str | Path,
    design_path: str | Path,
    expected_contract: Mapping[str, Any],
) -> tuple[pd.DataFrame, tuple[str, ...], dict[str, Any]]:
    """Verify diagnostics and deterministically reproduce stage-2 selection."""

    path = Path(selection_path)
    manifest_path = path.with_suffix(".manifest.json")
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != STAGE2_SELECTION_MANIFEST_SCHEMA_VERSION:
        raise ValueError("stage-2 selection manifest schema is not frozen")
    _validate_contract(
        manifest, expected_contract, context="stage-2 selection manifest"
    )
    _validate_selection_labels(manifest, context="stage-2 selection manifest")
    selection_output = _artifact_from_manifest(
        manifest, "output", manifest_path=manifest_path
    )
    if selection_output.resolve() != path.resolve():
        raise ValueError("stage-2 manifest points to a different selection output")
    manifest_ranking = _artifact_from_manifest(
        manifest, "ranking", manifest_path=manifest_path
    )
    if manifest_ranking.resolve() != Path(ranking_path).resolve():
        raise ValueError("stage-2 selection is bound to a different ranking")
    diagnostics_path = _artifact_from_manifest(
        manifest, "diagnostics", manifest_path=manifest_path
    )
    diagnostics_manifest_path = diagnostics_path.with_suffix(".manifest.json")
    diagnostics_manifest = _read_json(diagnostics_manifest_path)
    if (
        diagnostics_manifest.get("schema_version")
        != DIAGNOSTICS_MANIFEST_SCHEMA_VERSION
    ):
        raise ValueError("stage-2 diagnostics manifest schema is not frozen")
    _validate_contract(
        diagnostics_manifest,
        expected_contract,
        context="stage-2 diagnostics manifest",
    )
    _validate_selection_labels(
        diagnostics_manifest, context="stage-2 diagnostics manifest"
    )
    diagnostics_output = _artifact_from_manifest(
        diagnostics_manifest,
        "output",
        manifest_path=diagnostics_manifest_path,
    )
    if diagnostics_output.resolve() != diagnostics_path.resolve():
        raise ValueError("diagnostics manifest points to a different output")
    diagnostics_run_manifest = _artifact_from_manifest(
        diagnostics_manifest,
        "run_manifest",
        manifest_path=diagnostics_manifest_path,
    )
    diagnostics_stage_manifest = _artifact_from_manifest(
        diagnostics_manifest,
        "stage_manifest",
        manifest_path=diagnostics_manifest_path,
    )
    diagnostics_events = _artifact_from_manifest(
        diagnostics_manifest,
        "event_metrics",
        manifest_path=diagnostics_manifest_path,
    )
    diagnostic_stage_dir = diagnostics_run_manifest.parent
    if diagnostics_stage_manifest.parent != diagnostic_stage_dir or (
        diagnostics_events.parent != diagnostic_stage_dir
    ):
        raise ValueError("stage-2 diagnostics inputs do not share one stage directory")
    diagnostics = _read_table(diagnostics_path)
    derived_diagnostics = extract_stage2_diagnostics(
        diagnostic_stage_dir, expected_contract=expected_contract
    )
    hash_columns = [
        column
        for column in set(diagnostics.columns).union(derived_diagnostics.columns)
        if "sha256" in str(column).lower() or str(column).endswith("_hash")
    ]
    try:
        pd.testing.assert_frame_equal(
            diagnostics.drop(columns=hash_columns, errors="ignore").reset_index(
                drop=True
            ),
            derived_diagnostics.drop(columns=hash_columns, errors="ignore").reset_index(
                drop=True
            ),
            check_dtype=False,
            check_exact=False,
            atol=1e-12,
            rtol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            "stage-2 diagnostics do not equal the automatic artifact extraction"
        ) from error
    if tuple(diagnostics["model"].astype(str)) != DEEP_CANDIDATES:
        raise ValueError("stage-2 diagnostics do not have exactly four candidate rows")
    if set(pd.to_numeric(diagnostics["training_seed"], errors="coerce")) != {
        STAGE2_SEED
    }:
        raise ValueError("stage-2 diagnostics are not seed-11 evidence")
    for field, expected in (
        ("evaluation_split", "validation"),
        ("evidence_role", "model_selection_only"),
        ("formal_evidence", False),
        ("data_version", expected_contract["data_version"]),
    ):
        if field == "formal_evidence":
            observed = {
                _strict_bool(value, field="diagnostics formal_evidence")
                for value in diagnostics[field]
            }
            if observed != {expected}:
                raise ValueError("stage-2 diagnostics formal_evidence mismatch")
        elif set(diagnostics[field].astype(str)) != {str(expected)}:
            raise ValueError(f"stage-2 diagnostics {field} mismatch")
    recomputed = select_stage2_finalists(
        ranking,
        diagnostics=diagnostics,
        **_selection_settings(design_path),
    )
    recomputed["data_version"] = expected_contract["data_version"]
    selected = _read_table(path)
    hash_columns = [
        column
        for column in set(selected.columns).union(recomputed.columns)
        if "sha256" in str(column).lower() or str(column) in {"design_hash"}
    ]
    try:
        pd.testing.assert_frame_equal(
            selected.drop(columns=hash_columns, errors="ignore").reset_index(drop=True),
            recomputed.drop(columns=hash_columns, errors="ignore").reset_index(
                drop=True
            ),
            check_dtype=False,
            check_exact=False,
            atol=1e-12,
            rtol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            "stage-2 selection does not equal deterministic recomputation"
        ) from error
    finalists = tuple(
        selected.loc[
            selected["selected_for_stability"].map(
                lambda value: _strict_bool(value, field="selected_for_stability")
            ),
            "model",
        ].astype(str)
    )
    if tuple(manifest.get("selected_models", ())) != finalists:
        raise ValueError("stage-2 manifest finalist roster disagrees with its table")
    return selected, finalists, manifest


def _score_cells_sha256(
    dates: Sequence[Any], station_id: str, truth: np.ndarray
) -> str:
    rows = [
        [str(pd.Timestamp(date).date()), station_id, "T", float(value)]
        for date, value in zip(dates, truth)
    ]
    encoded = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_prediction_bundle(
    predictions: object,
    *,
    time_count: int,
    station_count: int,
) -> dict[str, Mapping[str, np.ndarray]]:
    if not isinstance(predictions, Mapping):
        raise TypeError("information-combination predictor must return a mapping")
    labels = set(map(str, predictions))
    expected = set(ALL_INFORMATION_COMBINATIONS)
    if labels != expected:
        missing = sorted(expected.difference(labels))
        extra = sorted(labels.difference(expected))
        if "S0" in missing:
            raise ValueError(
                "branch ablation requires the final 16-combination proposed "
                "checkpoint interface, including empty enabled_groups as S0"
            )
        raise ValueError(
            "branch ablation predictor combination set mismatch: "
            f"missing={missing}, extra={extra}"
        )
    result: dict[str, Mapping[str, np.ndarray]] = {}
    for label in ALL_INFORMATION_COMBINATIONS:
        bundle = predictions[label]
        if not isinstance(bundle, Mapping):
            raise TypeError(f"prediction bundle for {label} must be a mapping")
        required = {"q05", "q25", "q50", "q75", "q95"}
        missing_quantiles = sorted(required.difference(bundle))
        if missing_quantiles:
            raise ValueError(f"prediction bundle for {label} omits {missing_quantiles}")
        for quantile in required:
            array = np.asarray(bundle[quantile], dtype=float)
            if array.shape != (time_count, station_count):
                raise ValueError(
                    f"{label}/{quantile} has shape {array.shape}; expected "
                    f"{(time_count, station_count)}"
                )
        result[label] = bundle
    return result


def _validation_branch_scenarios(funnel: Any) -> tuple[Any, ...]:
    selected = tuple(
        scenario
        for scenario in funnel.grid.scenarios
        if validation_condition_stratum(scenario.condition.condition_id)
        in {f"t_block_{gap}d" for gap in BRANCH_ABLATION_GAPS}
    )
    expected_count = (
        len(VALIDATION_STATIONS)
        * len(VALIDATION_MASK_SEEDS)
        * len(BRANCH_ABLATION_GAPS)
    )
    if len(selected) != expected_count:
        raise AssertionError("branch-ablation scenario inventory is not frozen")
    return selected


def execute_validation_branch_ablation(
    *,
    stage3_dir: str | Path,
    stage3_models: Sequence[str],
    expected_contract: Mapping[str, Any],
    manifest_path: str | Path,
    config_path: str | Path,
    design_path: str | Path,
    data_version_manifest_path: str | Path,
    wide_path: str | Path,
    quality_path: str | Path | None,
    anchor_catalog_path: str | Path,
    output_dir: str | Path,
    mask_dir: str | Path,
    device: str = "cpu",
    predictor: Callable[..., object] | None = None,
) -> dict[str, Any]:
    """Score the five frozen branch contrasts from one checkpoint per seed.

    The injected ``predictor`` exists for focused tests.  Production execution
    uses :func:`predict_proposed_information_combinations` and requires its final
    16-combination interface; there is no climatology fallback for S0.
    """

    from .runner import ExperimentRunner
    from .science import predict_proposed_information_combinations
    from .validation import build_validation_funnel

    contract = _canonical_contract(expected_contract)
    _validate_relevant_source_clean(expected_contract, context="branch ablation")
    models = tuple(dict.fromkeys(str(model) for model in stage3_models))
    if "proposed" not in models:
        raise ValueError("branch ablation requires proposed to complete stage 3")
    _, checkpoint_metadata, _ = validate_completed_deep_stage(
        stage3_dir,
        expected_models=models,
        expected_seeds=VALIDATION_DEEP_SEEDS,
        expected_contract=expected_contract,
        expected_stage_name="deep_stability",
    )
    proposed_checkpoints = {
        seed: checkpoint_metadata[("proposed", seed)] for seed in VALIDATION_DEEP_SEEDS
    }
    output_root = Path(output_dir)
    target_paths = (
        output_root / "branch_ablation_daily_predictions.parquet",
        output_root / "branch_ablation_metrics.parquet",
        output_root / "branch_ablation_manifest.json",
    )
    existing = [path for path in target_paths if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to mix branch-ablation outputs: {existing}")

    funnel = build_validation_funnel(
        manifest_path,
        config_path,
        data_version=str(contract["data_version"]),
        anchor_catalog_path=anchor_catalog_path,
        anchor_data_version=str(contract["data_version"]),
    )
    runner = ExperimentRunner(
        funnel.grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output_root,
        mask_dir=mask_dir,
        config_path=config_path,
        design_path=design_path,
        manifest_path=manifest_path,
        data_version_manifest_path=data_version_manifest_path,
        models=("proposed",),
        training_seeds=VALIDATION_DEEP_SEEDS,
        resume=True,
    )
    if runner.evidence_contract != contract:
        raise RuntimeError("branch runner and validation evidence contracts disagree")
    target_index = runner.data.variable_names.index("T")
    training_climatology = runner._proposed_training_climatology()
    inference = predictor or predict_proposed_information_combinations
    loaded: dict[int, tuple[Any, np.ndarray, np.ndarray]] = {}
    for seed, metadata in proposed_checkpoints.items():
        model, _, mean, scale = runner._load_proposed_model_checkpoint(
            metadata["checkpoint_path"],
            seed,
            funnel.grid.conditions[0].window_length,
            funnel.grid.conditions[0].training_protocol,
        )
        loaded[seed] = (model, mean, scale)

    daily_parts: list[pd.DataFrame] = []
    event_rows: list[dict[str, Any]] = []
    mask_inventory: dict[str, dict[str, Any]] = {}
    for scenario in _validation_branch_scenarios(funnel):
        station_index = runner.data.station_ids.index(scenario.condition.station_ids[0])
        artificial, mask_metadata = runner._generate_mask(scenario)
        truth = runner.data.values[:, station_index, target_index].astype(float)
        quality = runner.data.quality_approved[:, station_index, target_index]
        hidden = artificial[:, station_index, target_index]
        positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
        if not positions.size:
            raise ValueError(
                f"branch scenario has no approved hidden T cells: {scenario.scenario_id}"
            )
        station_id = runner.data.station_ids[station_index]
        mask_path = Path(mask_dir) / "scenarios" / f"{scenario.scenario_id}.npz"
        mask_metadata_path = (
            Path(mask_dir) / "scenarios" / f"{scenario.scenario_id}.json"
        )
        mask_identity = _file_identity(mask_path)
        mask_metadata_identity = _file_identity(mask_metadata_path)
        mask_inventory[scenario.scenario_id] = {
            "scenario_id": scenario.scenario_id,
            "condition_id": scenario.condition.condition_id,
            "station_id": station_id,
            "gap_length": int(scenario.condition.gap_length),
            "mask_seed": int(scenario.mask_seed),
            "anchor_id": str(scenario.condition.anchor_id),
            "score_cell_count": len(positions),
            "mask": mask_identity,
            "mask_metadata": mask_metadata_identity,
        }
        reference = runner._training_reference(station_index, target_index)
        climatology = runner._climatology(station_index, target_index)[1]
        for seed in VALIDATION_DEEP_SEEDS:
            model, mean, scale = loaded[seed]
            raw_predictions = inference(
                model,
                runner.data.values,
                runner.data.natural_observed,
                artificial,
                runner.data.seasonal_features,
                mean,
                scale,
                target_index=target_index,
                training_climatology=training_climatology,
                window_length=scenario.condition.window_length,
                device=device,
            )
            predictions = _validate_prediction_bundle(
                raw_predictions,
                time_count=len(runner.data.values),
                station_count=len(runner.data.station_ids),
            )
            checkpoint = proposed_checkpoints[seed]
            for label in BRANCH_ABLATION_COMBINATIONS:
                quantiles = {
                    name: np.asarray(predictions[label][name], dtype=float)[
                        :, station_index
                    ]
                    for name in ("q05", "q25", "q50", "q75", "q95")
                }
                quantile_matrix = np.column_stack(
                    [quantiles[name][positions] for name in quantiles]
                )
                if not np.isfinite(quantile_matrix).all():
                    raise ValueError(
                        f"nonfinite proposed branch prediction for {scenario.scenario_id}/{seed}/{label}"
                    )
                if not np.all(np.diff(quantile_matrix, axis=1) > 0):
                    raise ValueError(
                        f"unordered proposed quantiles for {scenario.scenario_id}/{seed}/{label}"
                    )
                prediction = quantiles["q50"]
                row_metadata = {
                    **mask_metadata,
                    "scenario_id": scenario.scenario_id,
                    "station_id": station_id,
                    "model": "proposed",
                    "training_seed": seed,
                    "mask_seed": scenario.mask_seed,
                    "target": "T",
                    "gap_length": scenario.condition.gap_length,
                    "pattern": "T",
                    "anchor_id": scenario.condition.anchor_id,
                }
                event = compute_event_metrics(
                    truth,
                    prediction,
                    quality,
                    hidden,
                    target="T",
                    metadata=row_metadata,
                    climatology_pred=climatology,
                    dates=runner.data.dates,
                    quantile_predictions=quantiles,
                    high_threshold=reference.q90,
                    low_threshold=reference.q10,
                    ecological_threshold=None,
                    normalization_iqr=reference.iqr,
                    normalization_std=reference.std,
                )
                event.update(
                    {
                        "condition_id": scenario.condition.condition_id,
                        "information_combination": label,
                        "attribution_estimand": "operational_dropout",
                        "component_estimator": "proposed_checkpoint",
                        "checkpoint_path": _portable_path(
                            checkpoint["checkpoint_path"]
                        ),
                        "mask_path": mask_identity["path"],
                        "mask_metadata_path": mask_metadata_identity["path"],
                        "score_cell_count": len(positions),
                        "fit_split": "train",
                        "tuning_split": "validation_checkpoint",
                        "evaluation_split": "validation",
                        "evidence_role": "model_selection_only",
                        "formal_evidence": False,
                        "data_version": contract["data_version"],
                        "design_version": contract["design_version"],
                        "mask_schema_version": contract["mask_schema_version"],
                        "model_schema_version": contract["model_schema_version"],
                        "statistics_schema_version": contract[
                            "statistics_schema_version"
                        ],
                    }
                )
                if not np.isfinite(float(event["MAE"])) or not np.isfinite(
                    float(event["RMSE"])
                ):
                    raise ValueError("branch event metrics must be finite")
                event_rows.append(event)
                daily_parts.append(
                    pd.DataFrame(
                        {
                            "date": runner.data.dates[positions],
                            "scenario_id": scenario.scenario_id,
                            "condition_id": scenario.condition.condition_id,
                            "station_id": station_id,
                            "target": "T",
                            "model": "proposed",
                            "training_seed": seed,
                            "mask_seed": scenario.mask_seed,
                            "gap_length": scenario.condition.gap_length,
                            "anchor_id": scenario.condition.anchor_id,
                            "information_combination": label,
                            "attribution_estimand": "operational_dropout",
                            "component_estimator": "proposed_checkpoint",
                            "checkpoint_path": _portable_path(
                                checkpoint["checkpoint_path"]
                            ),
                            "mask_path": mask_identity["path"],
                            "y_true": truth[positions],
                            "y_pred": prediction[positions],
                            "q05": quantiles["q05"][positions],
                            "q25": quantiles["q25"][positions],
                            "q50": quantiles["q50"][positions],
                            "q75": quantiles["q75"][positions],
                            "q95": quantiles["q95"][positions],
                            "quality_approved": quality[positions],
                            "artificial_mask": hidden[positions],
                            "evaluation_split": "validation",
                            "evidence_role": "model_selection_only",
                            "formal_evidence": False,
                            "data_version": contract["data_version"],
                        }
                    )
                )
    daily = pd.concat(daily_parts, ignore_index=True)
    events = pd.DataFrame(event_rows)
    events_path = output_root / "branch_ablation_metrics.parquet"
    daily_path = output_root / "branch_ablation_daily_predictions.parquet"
    manifest_path_out = output_root / "branch_ablation_manifest.json"
    _atomic_parquet(daily, daily_path)
    _atomic_parquet(events, events_path)
    manifest = {
        "schema_version": BRANCH_ABLATION_MANIFEST_SCHEMA_VERSION,
        "models": ["proposed"],
        "training_seeds": list(VALIDATION_DEEP_SEEDS),
        "gap_lengths": list(BRANCH_ABLATION_GAPS),
        "information_combinations": list(BRANCH_ABLATION_COMBINATIONS),
        "attribution_estimand": "operational_dropout",
        "component_estimator": "proposed_checkpoint",
        "checkpoint_by_seed": {
            str(seed): _file_identity(proposed_checkpoints[seed]["checkpoint_path"])
            for seed in VALIDATION_DEEP_SEEDS
        },
        "mask_units": list(mask_inventory.values()),
        "mask_unit_count": len(mask_inventory),
        "event_rows": len(events),
        "daily_rows": len(daily),
        "event_metrics": _file_identity(events_path),
        "daily_predictions": _file_identity(daily_path),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **contract,
        "code_provenance": json.loads(
            json.dumps(expected_contract.get("code_provenance"))
        ),
    }
    _atomic_json(manifest, manifest_path_out)
    validate_branch_ablation_artifact(events_path, expected_contract=expected_contract)
    return manifest


def validate_branch_ablation_artifact(
    event_metrics_path: str | Path,
    *,
    expected_contract: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate exact seeds/gaps/contrasts and shared scored-cell identities."""

    path = Path(event_metrics_path)
    manifest_path = path.parent / "branch_ablation_manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != BRANCH_ABLATION_MANIFEST_SCHEMA_VERSION:
        raise ValueError("branch-ablation manifest schema is not frozen")
    _validate_contract(manifest, expected_contract, context="branch-ablation manifest")
    _validate_selection_labels(manifest, context="branch-ablation manifest")
    if (
        manifest.get("attribution_estimand") != "operational_dropout"
        or manifest.get("component_estimator") != "proposed_checkpoint"
    ):
        raise ValueError("branch-ablation manifest mixes attribution estimands")
    bound_events = _artifact_from_manifest(
        manifest, "event_metrics", manifest_path=manifest_path
    )
    if bound_events.resolve() != path.resolve():
        raise ValueError("branch-ablation manifest points to different metrics")
    daily_path = _artifact_from_manifest(
        manifest, "daily_predictions", manifest_path=manifest_path
    )
    events = _read_table(path)
    daily = _read_table(daily_path)
    required = {
        "scenario_id",
        "condition_id",
        "station_id",
        "training_seed",
        "mask_seed",
        "gap_length",
        "information_combination",
        "attribution_estimand",
        "component_estimator",
        "checkpoint_path",
        "anchor_id",
        "score_cell_count",
        "MAE",
        "RMSE",
        "evaluation_split",
        "evidence_role",
        "formal_evidence",
        "data_version",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise ValueError(f"branch-ablation metrics omit columns: {missing}")
    expected_rows = (
        len(VALIDATION_DEEP_SEEDS)
        * len(VALIDATION_STATIONS)
        * len(VALIDATION_MASK_SEEDS)
        * len(BRANCH_ABLATION_GAPS)
        * len(BRANCH_ABLATION_COMBINATIONS)
    )
    if len(events) != expected_rows:
        raise ValueError("branch-ablation metrics do not cover the frozen grid")
    key = [
        "scenario_id",
        "training_seed",
        "information_combination",
        "station_id",
    ]
    if events.duplicated(key).any():
        raise ValueError("branch-ablation metrics contain duplicate contrast units")
    if set(pd.to_numeric(events["training_seed"], errors="coerce")) != set(
        VALIDATION_DEEP_SEEDS
    ):
        raise ValueError("branch-ablation training seeds are not 11/22/33")
    if set(pd.to_numeric(events["gap_length"], errors="coerce")) != set(
        BRANCH_ABLATION_GAPS
    ):
        raise ValueError("branch-ablation gaps are not 10/90/180")
    if set(events["information_combination"].astype(str)) != set(
        BRANCH_ABLATION_COMBINATIONS
    ):
        raise ValueError("branch-ablation combination set is not frozen")
    if set(events["station_id"].astype(str)) != set(VALIDATION_STATIONS):
        raise ValueError("branch-ablation station set is not frozen")
    if set(pd.to_numeric(events["mask_seed"], errors="coerce")) != set(
        VALIDATION_MASK_SEEDS
    ):
        raise ValueError("branch-ablation mask placeholders are not 101..105")
    expected_scenarios = _expected_branch_scenario_ids(
        str(expected_contract["data_version"])
    )
    if set(events["scenario_id"].astype(str)) != expected_scenarios:
        raise ValueError("branch-ablation scenario inventory is not frozen")
    expected_units = {
        (scenario_id, seed)
        for scenario_id in expected_scenarios
        for seed in VALIDATION_DEEP_SEEDS
    }
    observed_units = {
        (str(row.scenario_id), int(row.training_seed))
        for row in events[["scenario_id", "training_seed"]]
        .drop_duplicates()
        .itertuples(index=False)
    }
    if observed_units != expected_units:
        raise ValueError("branch-ablation seed/scenario units are incomplete")
    for field, expected in (
        ("attribution_estimand", "operational_dropout"),
        ("component_estimator", "proposed_checkpoint"),
        ("evaluation_split", "validation"),
        ("evidence_role", "model_selection_only"),
        ("data_version", expected_contract["data_version"]),
    ):
        if set(events[field].astype(str)) != {str(expected)}:
            raise ValueError(f"branch-ablation {field} mismatch")
    if {
        _strict_bool(value, field="branch formal_evidence")
        for value in events["formal_evidence"]
    } != {False}:
        raise ValueError("branch-ablation metrics claim formal evidence")
    if not np.isfinite(
        events[["MAE", "RMSE", "score_cell_count"]]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy()
    ).all():
        raise ValueError("branch-ablation metrics contain nonfinite values")
    unit_columns = ["scenario_id", "training_seed"]
    for _, group in events.groupby(unit_columns, sort=True):
        if set(group["information_combination"].astype(str)) != set(
            BRANCH_ABLATION_COMBINATIONS
        ):
            raise ValueError("one branch unit omits a frozen contrast")
        for field in (
            "station_id",
            "mask_seed",
            "gap_length",
            "anchor_id",
            "score_cell_count",
            "checkpoint_path",
        ):
            if group[field].nunique(dropna=False) != 1:
                raise ValueError(f"branch contrasts do not share {field}")
    daily_required = {
        "scenario_id",
        "training_seed",
        "information_combination",
        "station_id",
        "date",
        "y_true",
        "y_pred",
        "q05",
        "q25",
        "q50",
        "q75",
        "q95",
        "quality_approved",
        "artificial_mask",
    }
    missing_daily = sorted(daily_required.difference(daily.columns))
    if missing_daily:
        raise ValueError(f"branch daily predictions omit columns: {missing_daily}")
    values = daily[["y_true", "y_pred", "q05", "q25", "q50", "q75", "q95"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("branch daily predictions contain nonfinite values")
    if not np.all(np.diff(values[["q05", "q25", "q50", "q75", "q95"]], axis=1) > 0):
        raise ValueError("branch daily predictions contain unordered quantiles")
    if not all(
        _strict_bool(value, field="quality_approved")
        for value in daily["quality_approved"]
    ) or not all(
        _strict_bool(value, field="artificial_mask")
        for value in daily["artificial_mask"]
    ):
        raise ValueError(
            "branch daily predictions include unapproved or unhidden cells"
        )
    daily_cell_keys = ["date", "station_id", "y_true"]
    for (scenario_id, seed), group in daily.groupby(
        ["scenario_id", "training_seed"], sort=True
    ):
        reference = None
        for label, label_group in group.groupby("information_combination", sort=True):
            cells = set(label_group[daily_cell_keys].itertuples(index=False, name=None))
            if reference is None:
                reference = cells
            elif cells != reference:
                raise ValueError(
                    f"branch contrasts score different cells for {scenario_id}/{seed}"
                )
        event_group = events.loc[
            events["scenario_id"].astype(str).eq(str(scenario_id))
            & pd.to_numeric(events["training_seed"], errors="coerce").eq(int(seed))
        ]
        expected_count = int(event_group["score_cell_count"].iloc[0])
        if any(
            len(label_group) != expected_count
            for _, label_group in group.groupby("information_combination", sort=True)
        ):
            raise ValueError("branch daily cell count differs from event metadata")
    if not np.allclose(
        pd.to_numeric(daily["y_pred"], errors="coerce"),
        pd.to_numeric(daily["q50"], errors="coerce"),
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("branch y_pred must equal the proposed q50")

    raw_mask_units = manifest.get("mask_units")
    if not isinstance(raw_mask_units, list) or len(raw_mask_units) != len(
        expected_scenarios
    ):
        raise ValueError("branch manifest mask-unit inventory is incomplete")
    mask_units: dict[str, Mapping[str, Any]] = {}
    for value in raw_mask_units:
        if not isinstance(value, Mapping):
            raise TypeError("branch mask-unit inventory rows must be mappings")
        scenario_id = str(value.get("scenario_id"))
        if scenario_id in mask_units:
            raise ValueError("branch mask-unit inventory contains duplicate scenarios")
        mask_units[scenario_id] = value
    if set(mask_units) != expected_scenarios:
        raise ValueError("branch mask-unit scenario inventory is not frozen")
    for scenario_id, value in mask_units.items():
        _verify_file_identity(
            value.get("mask"),
            relative_to=manifest_path.parent,
            context=f"branch mask {scenario_id}",
        )
        _verify_file_identity(
            value.get("mask_metadata"),
            relative_to=manifest_path.parent,
            context=f"branch mask metadata {scenario_id}",
        )
        rows = events.loc[events["scenario_id"].astype(str).eq(scenario_id)]
        checks = {
            "station_id": str(value.get("station_id")),
            "gap_length": str(value.get("gap_length")),
            "mask_seed": str(value.get("mask_seed")),
            "anchor_id": str(value.get("anchor_id")),
            "score_cell_count": str(value.get("score_cell_count")),
        }
        for field, expected in checks.items():
            if set(rows[field].astype(str)) != {expected}:
                raise ValueError(
                    f"branch mask inventory and event rows disagree for {scenario_id}/{field}"
                )
    raw_checkpoints = manifest.get("checkpoint_by_seed")
    if not isinstance(raw_checkpoints, Mapping) or set(raw_checkpoints) != {
        str(seed) for seed in VALIDATION_DEEP_SEEDS
    }:
        raise ValueError("branch manifest checkpoint seed inventory is incomplete")
    checkpoint_paths = {
        int(seed): _verify_file_identity(
            identity,
            relative_to=manifest_path.parent,
            context=f"branch checkpoint seed {seed}",
        )[0]
        for seed, identity in raw_checkpoints.items()
    }
    for seed, group in events.groupby("training_seed", sort=True):
        expected = _portable_path(checkpoint_paths[int(seed)])
        if "checkpoint_path" in group and set(group["checkpoint_path"].astype(str)) != {
            expected
        }:
            raise ValueError("branch rows and manifest checkpoint paths disagree")
    return events, manifest


def write_early_framework_only_decision(
    *,
    ranking_path: str | Path,
    stage2_selection_path: str | Path,
    output_dir: str | Path,
    design_path: str | Path,
    expected_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist a hash-bound early stop when proposed fails stage 2.

    This path contains no fabricated stage-3 or branch-performance rows.  The
    not-applicable branch document is instead bound to the fully revalidated
    ranking, diagnostics, and deterministic stage-2 selection.
    """

    ranking, _ = validate_ranking_artifact(
        ranking_path, expected_contract=expected_contract
    )
    selection, finalists, _ = validate_stage2_selection_artifact(
        stage2_selection_path,
        ranking=ranking,
        ranking_path=ranking_path,
        design_path=design_path,
        expected_contract=expected_contract,
    )
    if "proposed" in finalists:
        raise ValueError(
            "early framework-only decision is forbidden after proposed enters stage 3"
        )
    proposed_rows = selection.loc[selection["model"].astype(str).eq("proposed")]
    if len(proposed_rows) != 1:
        raise ValueError("stage-2 selection requires exactly one proposed row")
    proposed = proposed_rows.iloc[0]
    if _strict_bool(
        proposed["selected_for_stability"], field="proposed selected_for_stability"
    ):
        raise ValueError("proposed stage-2 row contradicts the finalist roster")

    traditional = ranking.loc[
        ranking["model"].astype(str).isin(TRADITIONAL_CANDIDATES)
    ].sort_values("rank", kind="mergesort")
    if len(traditional) != len(TRADITIONAL_CANDIDATES):
        raise ValueError("ranking omits a frozen traditional T candidate")
    best_traditional = str(traditional.iloc[0]["model"])
    stage2_path = Path(stage2_selection_path)
    stage2_manifest_path = stage2_path.with_suffix(".manifest.json")
    ranking_file = Path(ranking_path)
    output = Path(output_dir)
    branch_path = output / "branch_ablation_not_applicable.json"
    decision_path = output / "proposed_go_no_go_decision.json"
    branch_payload = {
        "schema_version": BRANCH_ABLATION_NOT_APPLICABLE_SCHEMA_VERSION,
        "status": "not_applicable",
        "reason": "proposed_not_selected_for_stability",
        "proposed_decision": "framework_only",
        "stage2_selected_models": list(finalists),
        "stage2_selection": _file_identity(stage2_path),
        "stage2_selection_manifest": _file_identity(stage2_manifest_path),
        "ranking": _file_identity(ranking_file),
        "performance_row_count": 0,
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **_canonical_contract(expected_contract),
        "code_provenance": json.loads(
            json.dumps(expected_contract.get("code_provenance"))
        ),
    }
    _atomic_json(branch_payload, branch_path)
    decision_payload = {
        "schema_version": GO_NO_GO_SCHEMA_VERSION,
        "assessment_mode": "early_framework_only",
        "status": "not_applicable",
        "reason": "proposed_not_selected_for_stability",
        "passed": False,
        "decision": "framework_only",
        "best_traditional_model": best_traditional,
        "criteria_status": "not_applicable",
        "branch_ablation_status": "not_applicable",
        "event_metrics": [],
        "branch_ablations": _file_identity(branch_path),
        "stage2_selection": _file_identity(stage2_path),
        "stage2_selection_manifest": _file_identity(stage2_manifest_path),
        "ranking": _file_identity(ranking_file),
        "stage2_selected_models": list(finalists),
        "evidence": {
            "proposed_selected_for_stability": False,
            "proposed_diagnostic_pass": _strict_bool(
                proposed["diagnostic_pass"], field="proposed diagnostic_pass"
            ),
            "proposed_selection_reason": str(proposed["selection_reason"]),
            "stage3_proposed_required": False,
            "branch_ablation_required": False,
        },
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        **_canonical_contract(expected_contract),
        "code_provenance": json.loads(
            json.dumps(expected_contract.get("code_provenance"))
        ),
    }
    _atomic_json(decision_payload, decision_path)
    return {**decision_payload, "output": _portable_path(decision_path)}


def validate_branch_ablation_not_applicable_artifact(
    artifact_path: str | Path,
    *,
    stage2_selection_path: str | Path,
    ranking_path: str | Path,
    expected_finalists: Sequence[str],
    expected_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate explicit branch non-applicability without accepting empty tables."""

    path = Path(artifact_path)
    document = _read_json(path)
    if document.get("schema_version") != BRANCH_ABLATION_NOT_APPLICABLE_SCHEMA_VERSION:
        raise ValueError("branch not-applicable schema is not frozen")
    _validate_contract(document, expected_contract, context="branch not-applicable")
    _validate_selection_labels(document, context="branch not-applicable")
    expected_values = {
        "status": "not_applicable",
        "reason": "proposed_not_selected_for_stability",
        "proposed_decision": "framework_only",
        "performance_row_count": 0,
    }
    mismatches = {
        field: (document.get(field), expected)
        for field, expected in expected_values.items()
        if document.get(field) != expected
    }
    if mismatches:
        raise ValueError(f"branch not-applicable contract mismatch: {mismatches}")
    finalists = tuple(
        str(value) for value in document.get("stage2_selected_models", ())
    )
    if finalists != tuple(expected_finalists) or "proposed" in finalists:
        raise ValueError("branch not-applicable finalist roster is inconsistent")
    identities = (
        ("stage2_selection", Path(stage2_selection_path)),
        (
            "stage2_selection_manifest",
            Path(stage2_selection_path).with_suffix(".manifest.json"),
        ),
        ("ranking", Path(ranking_path)),
    )
    for field, expected_path in identities:
        observed_path, _ = _verify_file_identity(
            document.get(field),
            relative_to=path.parent,
            context=f"branch not-applicable {field}",
        )
        if observed_path.resolve() != expected_path.resolve():
            raise ValueError(f"branch not-applicable is bound to different {field}")
    return document


def validate_go_no_go_artifact(
    decision_path: str | Path,
    *,
    branch_metrics_path: str | Path,
    design_path: str | Path,
    expected_contract: Mapping[str, Any],
    stage2_selection_path: str | Path | None = None,
    ranking_path: str | Path | None = None,
    stage2_finalists: Sequence[str] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, tuple[Path, ...]]:
    """Recompute the all-criteria decision from hash-bound validation inputs."""

    path = Path(decision_path)
    document = _read_json(path)
    if document.get("schema_version") != GO_NO_GO_SCHEMA_VERSION:
        raise ValueError("go/no-go decision schema is not frozen")
    _validate_contract(document, expected_contract, context="go/no-go decision")
    _validate_selection_labels(document, context="go/no-go decision")
    assessment_mode = document.get("assessment_mode", "full_stage3")
    if assessment_mode == "early_framework_only":
        if (
            stage2_selection_path is None
            or ranking_path is None
            or stage2_finalists is None
        ):
            raise ValueError(
                "early framework-only validation requires ranking and stage-2 inputs"
            )
        finalists = tuple(str(value) for value in stage2_finalists)
        if "proposed" in finalists:
            raise ValueError(
                "early framework-only evidence is invalid after proposed enters stage 3"
            )
        expected_values = {
            "status": "not_applicable",
            "reason": "proposed_not_selected_for_stability",
            "passed": False,
            "decision": "framework_only",
            "criteria_status": "not_applicable",
            "branch_ablation_status": "not_applicable",
        }
        mismatches = {
            field: (document.get(field), expected)
            for field, expected in expected_values.items()
            if document.get(field) != expected
        }
        if mismatches:
            raise ValueError(f"early framework-only decision mismatch: {mismatches}")
        if document.get("event_metrics") != [] or "criteria" in document:
            raise ValueError(
                "early framework-only decision must not contain performance evidence"
            )
        if tuple(document.get("stage2_selected_models", ())) != finalists:
            raise ValueError("early decision finalist roster differs from stage 2")
        for field, expected_path in (
            ("stage2_selection", Path(stage2_selection_path)),
            (
                "stage2_selection_manifest",
                Path(stage2_selection_path).with_suffix(".manifest.json"),
            ),
            ("ranking", Path(ranking_path)),
        ):
            observed_path, _ = _verify_file_identity(
                document.get(field),
                relative_to=path.parent,
                context=f"early go/no-go {field}",
            )
            if observed_path.resolve() != expected_path.resolve():
                raise ValueError(f"early go/no-go is bound to different {field}")
        branch_path, branch_digest = _verify_file_identity(
            document.get("branch_ablations"),
            relative_to=path.parent,
            context="early go/no-go branch status",
        )
        if branch_path.resolve() != Path(branch_metrics_path).resolve():
            raise ValueError("early go/no-go is bound to different branch status")
        validate_branch_ablation_not_applicable_artifact(
            branch_path,
            stage2_selection_path=stage2_selection_path,
            ranking_path=ranking_path,
            expected_finalists=finalists,
            expected_contract=expected_contract,
        )
        stored_branch_digest = document.get("branch_ablations", {}).get("sha256")
        if stored_branch_digest and stored_branch_digest != branch_digest:
            raise ValueError("early go/no-go branch digest is inconsistent")
        evidence = document.get("evidence")
        if not isinstance(evidence, Mapping) or (
            evidence.get("proposed_selected_for_stability") is not False
            or evidence.get("stage3_proposed_required") is not False
            or evidence.get("branch_ablation_required") is not False
        ):
            raise ValueError("early go/no-go evidence summary is inconsistent")
        return document, pd.DataFrame(), ()
    if assessment_mode != "full_stage3":
        raise ValueError(f"unknown go/no-go assessment_mode: {assessment_mode!r}")
    raw_events = document.get("event_metrics")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("go/no-go decision requires hash-bound event inputs")
    event_paths = tuple(
        _verify_file_identity(
            identity,
            relative_to=path.parent,
            context="go/no-go event input",
        )[0]
        for identity in raw_events
    )
    events = read_validation_event_tables(event_paths)
    required_contract_columns = {
        "evaluation_split",
        "evidence_role",
        "data_version",
    }
    missing_contract = sorted(required_contract_columns.difference(events.columns))
    if missing_contract:
        raise ValueError(f"go/no-go events omit contract columns: {missing_contract}")
    for field, expected in (
        ("evaluation_split", "validation"),
        ("evidence_role", "model_selection_only"),
        ("data_version", expected_contract["data_version"]),
    ):
        if set(events[field].astype(str)) != {str(expected)}:
            raise ValueError(f"go/no-go event {field} mismatch")
    if set(events["model"].astype(str)).intersection(_LEGACY_DEEP_NAMES):
        raise ValueError("go/no-go events contain legacy deep model names")
    proposed = events.loc[events["model"].astype(str).eq("proposed")]
    if set(pd.to_numeric(proposed["training_seed"], errors="coerce")) != set(
        VALIDATION_DEEP_SEEDS
    ):
        raise ValueError("go/no-go proposed events require seeds 11/22/33")
    branch_path, branch_digest = _verify_file_identity(
        document.get("branch_ablations"),
        relative_to=path.parent,
        context="go/no-go branch ablations",
    )
    if branch_path.resolve() != Path(branch_metrics_path).resolve():
        raise ValueError("go/no-go decision is bound to different branch metrics")
    branch, _ = validate_branch_ablation_artifact(
        branch_path, expected_contract=expected_contract
    )
    recomputed = assess_proposed_go_no_go(
        events,
        branch,
        best_traditional_model=str(document.get("best_traditional_model")),
        **_go_no_go_settings(design_path),
    )
    expected_label = (
        "include_proposed_formally" if recomputed.passed else "framework_only"
    )
    if document.get("passed") is not recomputed.passed:
        raise ValueError("persisted go/no-go pass flag differs from recomputation")
    if document.get("decision") != expected_label:
        raise ValueError("persisted go/no-go decision differs from recomputation")
    if document.get("best_traditional_model") != recomputed.best_traditional_model:
        raise ValueError("persisted best traditional model differs from recomputation")
    stored_branch_digest = document.get("branch_ablations", {}).get("sha256")
    if stored_branch_digest and stored_branch_digest != branch_digest:
        raise ValueError("go/no-go branch digest is inconsistent")
    criteria_path = _artifact_from_manifest(document, "criteria", manifest_path=path)
    criteria = _read_table(criteria_path)
    expected_criteria = recomputed.criteria.copy()
    expected_criteria["evidence_role"] = "model_selection_only"
    expected_criteria["data_version"] = expected_contract["data_version"]
    try:
        pd.testing.assert_frame_equal(
            criteria.reset_index(drop=True),
            expected_criteria.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            atol=1e-12,
            rtol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            "go/no-go criteria table differs from recomputation"
        ) from error
    persisted_evidence = json.dumps(
        document.get("evidence"), sort_keys=True, separators=(",", ":")
    )
    expected_evidence = json.dumps(
        recomputed.evidence, sort_keys=True, separators=(",", ":")
    )
    if persisted_evidence != expected_evidence:
        raise ValueError("go/no-go evidence summary differs from recomputation")
    return document, events, event_paths


def _require_checkpoint_metadata(
    checkpoint_metadata: Mapping[tuple[str, int], Mapping[str, Any]],
    models: Sequence[str],
    seeds: Sequence[int] = VALIDATION_DEEP_SEEDS,
) -> dict[tuple[str, int], Mapping[str, Any]]:
    required = {(str(model), int(seed)) for model in models for seed in seeds}
    missing = sorted(required.difference(checkpoint_metadata))
    if missing:
        raise ValueError(f"stage-3 checkpoint metadata missing for {missing}")
    return {key: checkpoint_metadata[key] for key in required}


def stage3_budget_unstable_models(
    checkpoint_metadata: Mapping[tuple[str, int], Mapping[str, Any]],
    models: Sequence[str],
    seeds: Sequence[int] = VALIDATION_DEEP_SEEDS,
) -> tuple[str, ...]:
    """Return models that hit the epoch cap on any required seed."""

    metadata = _require_checkpoint_metadata(checkpoint_metadata, models, seeds)
    unstable: list[str] = []
    for model in models:
        if any(
            _strict_bool(
                metadata[(str(model), int(seed))]["hit_epoch_limit"],
                field=f"{model}/{seed} hit_epoch_limit",
            )
            for seed in seeds
        ):
            unstable.append(str(model))
    return tuple(dict.fromkeys(unstable))


def summarize_stage3_stability(
    events: pd.DataFrame,
    checkpoint_metadata: Mapping[tuple[str, int], Mapping[str, Any]],
    *,
    expected_data_version: str | None = None,
) -> pd.DataFrame:
    """One scientific stability row per completed Stage 3 model-seed pair."""

    if events.empty:
        raise ValueError("stage-3 stability requires completed event metrics")
    models = tuple(dict.fromkeys(model for model, _ in checkpoint_metadata))
    if not models:
        raise ValueError("stage-3 stability requires checkpoint metadata")
    metadata = _require_checkpoint_metadata(checkpoint_metadata, models)
    rows: list[dict[str, Any]] = []
    for model in models:
        for seed in VALIDATION_DEEP_SEEDS:
            subset = events.loc[
                events["model"].astype(str).eq(model)
                & pd.to_numeric(events["training_seed"], errors="coerce").eq(seed)
            ].copy()
            ranking = rank_validation_models(
                subset,
                expected_data_version=expected_data_version,
            )
            if len(ranking) != 1:
                raise ValueError(f"stage-3 stability ranking is not unique for {model}/{seed}")
            scored = ranking.iloc[0]
            coverage = np.nan
            if "coverage_90" in subset.columns:
                coverage_values = pd.to_numeric(subset["coverage_90"], errors="coerce")
                if coverage_values.notna().any():
                    coverage = float(coverage_values.mean())
            item = metadata[(model, seed)]
            rows.append(
                {
                    "model": model,
                    "seed": int(seed),
                    "overall_skill": float(scored["mean_skill_across_strata"]),
                    "long_gap_skill": float(scored["long_gap_mean_skill"]),
                    "outage_skill": float(scored["station_outage_mean_skill"]),
                    "worst_station_skill": float(scored["worst_station_mean_skill"]),
                    "coverage_90": coverage,
                    "hit_epoch_limit": bool(item["hit_epoch_limit"]),
                    "best_epoch": int(item["best_epoch"]),
                    "epochs_run": int(item["epochs_run"]),
                    "event_rows": int(len(subset)),
                    "budget_status": (
                        "budget_unstable" if item["hit_epoch_limit"] else "budget_stable"
                    ),
                    "evaluation_split": "validation",
                    "evidence_role": "model_selection_only",
                    "formal_evidence": False,
                    "data_version": str(scored["data_version"]),
                }
            )
    return pd.DataFrame(rows)


PROPOSED_DONOR_KEY_STRATA = (
    "t_block_90d",
    "t_block_180d",
    "tfl_block_90d",
    STATION_OUTAGE_STRATUM,
)
_REPO_ROOT = Path(__file__).resolve().parents[3]
PROPOSED_VERSUS_DONOR_DESIGN_PATH = _REPO_ROOT / "configs/design_freeze_v4.yaml"


def load_proposed_versus_donor_rule(
    design_path: str | Path = PROPOSED_VERSUS_DONOR_DESIGN_PATH,
) -> dict[str, Any]:
    """Return the frozen Stage 3 proposed-versus-donor claim rule."""

    with Path(design_path).open(encoding="utf-8") as handle:
        design = yaml.safe_load(handle)
    if not isinstance(design, Mapping):
        raise TypeError("design freeze must be a mapping")
    try:
        rule = design["model_funnel"]["proposed_versus_donor"]
    except (KeyError, TypeError) as error:
        raise ValueError("design freeze omits proposed_versus_donor") from error
    if not isinstance(rule, Mapping):
        raise TypeError("proposed_versus_donor must be a mapping")
    strata = tuple(str(value) for value in rule["difficult_strata"])
    seeds = tuple(int(value) for value in rule["required_seeds"])
    stations = tuple(str(value) for value in rule["required_stations"])
    if strata != PROPOSED_DONOR_KEY_STRATA:
        raise ValueError("proposed_versus_donor difficult_strata drifted from code")
    if seeds != VALIDATION_DEEP_SEEDS:
        raise ValueError("proposed_versus_donor required_seeds drifted from code")
    if stations != VALIDATION_STATIONS:
        raise ValueError("proposed_versus_donor required_stations drifted from code")
    if str(rule["comparator"]) != "donor_regression":
        raise ValueError("proposed_versus_donor comparator must be donor_regression")
    if str(rule["better_rule"]) != "proposed_mean_skill_strictly_greater_than_donor":
        raise ValueError("proposed_versus_donor better_rule is not the frozen strict inequality")
    if str(rule["tie_rule"]) != "count_as_not_proposed_better":
        raise ValueError("proposed_versus_donor tie_rule must not count ties as wins")
    return {
        "comparator": str(rule["comparator"]),
        "difficult_strata": strata,
        "required_seeds": seeds,
        "required_stations": stations,
        "better_rule": str(rule["better_rule"]),
        "tie_rule": str(rule["tie_rule"]),
        "formal_evidence": bool(rule["formal_evidence"]),
        "evidence_role": str(rule["evidence_role"]),
    }


def assess_proposed_versus_donor(
    events: pd.DataFrame,
    *,
    donor_model: str = "donor_regression",
    key_strata: Sequence[str] = PROPOSED_DONOR_KEY_STRATA,
    design_path: str | Path | None = PROPOSED_VERSUS_DONOR_DESIGN_PATH,
) -> dict[str, Any]:
    """Compare proposed to donor regression on the predeclared hard cases.

    This is a validation-only claim rule.  It does not create formal evidence.
    """

    if design_path is not None:
        rule = load_proposed_versus_donor_rule(design_path)
        donor_model = rule["comparator"]
        key_strata = rule["difficult_strata"]
        required_seeds = rule["required_seeds"]
        required_stations = rule["required_stations"]
    else:
        required_seeds = VALIDATION_DEEP_SEEDS
        required_stations = VALIDATION_STATIONS

    data = events.copy()
    data["condition_stratum"] = data["condition_id"].map(validation_condition_stratum)
    data["skill"] = pd.to_numeric(data["skill"], errors="coerce")
    proposed = data.loc[data["model"].astype(str).eq("proposed")].copy()
    donor = data.loc[data["model"].astype(str).eq(donor_model)].copy()
    if proposed.empty:
        return {
            "claim": "not_in_stage3",
            "donor_model": donor_model,
            "n_compared_cells": 0,
            "n_proposed_better": 0,
            "n_donor_better": 0,
            "cells": [],
            "evaluation_split": "validation",
            "evidence_role": "model_selection_only",
            "formal_evidence": False,
        }
    if donor.empty:
        raise ValueError(f"proposed-versus-donor comparison requires {donor_model}")
    proposed["training_seed"] = pd.to_numeric(
        proposed["training_seed"], errors="coerce"
    ).astype(int)
    keys = ["condition_stratum", "station_id"]
    donor_means = (
        donor.groupby(keys, as_index=False, dropna=False, sort=True)
        .agg(donor_skill=("skill", "mean"))
    )
    proposed_means = (
        proposed.groupby([*keys, "training_seed"], as_index=False, dropna=False, sort=True)
        .agg(proposed_skill=("skill", "mean"))
    )
    paired = proposed_means.merge(donor_means, on=keys, how="inner", validate="many_to_one")
    paired = paired.loc[paired["condition_stratum"].isin(set(key_strata))].copy()
    if paired.empty:
        raise ValueError("proposed-versus-donor comparison has no key-stratum cells")
    paired["proposed_better"] = paired["proposed_skill"] > paired["donor_skill"]
    n_better = int(paired["proposed_better"].sum())
    n_total = int(len(paired))
    seeds = tuple(sorted(int(seed) for seed in paired["training_seed"].unique()))
    stations = tuple(sorted(paired["station_id"].astype(str).unique()))
    all_seeds_all_stations = n_better == n_total
    any_difficult = bool(
        paired.loc[
            paired["condition_stratum"].isin(set(key_strata)),
            "proposed_better",
        ].any()
    )
    if (
        all_seeds_all_stations
        and set(seeds) == set(required_seeds)
        and set(stations) == set(required_stations)
    ):
        claim = "supporting_contribution"
    elif any_difficult:
        claim = "conditional"
    else:
        claim = "no_superiority"
    return {
        "claim": claim,
        "rule": {
            "comparison_unit": "stratum_by_station_mean_skill",
            "better_rule": "proposed_mean_skill_strictly_greater_than_donor",
            "tie_rule": "count_as_not_proposed_better",
            "supporting": "every_stratum_station_seed_cell_strictly_above_donor",
            "conditional": "at_least_one_difficult_cell_strictly_above_donor",
            "no_superiority": "no_difficult_cell_strictly_above_donor",
        },
        "donor_model": donor_model,
        "n_compared_cells": n_total,
        "n_proposed_better": n_better,
        "n_donor_better": n_total - n_better,
        "training_seeds": list(seeds),
        "stations": list(stations),
        "key_strata": list(key_strata),
        "cells": paired.to_dict(orient="records"),
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
    }


def finalize_validation_roster(
    *,
    ranking_path: str | Path,
    stage2_selection_path: str | Path,
    stage3_dir: str | Path,
    branch_metrics_path: str | Path,
    go_no_go_path: str | Path,
    output_path: str | Path,
    design_path: str | Path,
    study_manifest_path: str | Path,
    experiment_config_path: str | Path,
    data_version_manifest_path: str | Path,
    anchor_catalog_path: str | Path,
    expected_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Issue the immutable T/confirmatory model roster after every gate passes.

    ``selected_models`` is intentionally the T-capable internal/external roster:
    the nine frozen traditional T candidates plus completed stage-3 deep
    finalists.  F-only ``rating_curve`` and ``independent_flow`` remain frozen
    internal structural baselines and are not external-execution candidates.
    """

    _validate_relevant_source_clean(expected_contract, context="roster freeze")
    version_manifest = Path(data_version_manifest_path)
    validate_data_version_inputs(
        data_version_manifest_path=version_manifest,
        data_version=str(expected_contract["data_version"]),
        wide_path=version_manifest.parent / "daily_wide.parquet",
        quality_path=version_manifest.parent / "daily_long.parquet",
        require_manifest=True,
        require_quality=True,
    )
    validation_anchor_identity = validation_anchor_catalog_identity(
        anchor_catalog_path,
        require_canonical_path=True,
        expected_data_version=str(expected_contract["data_version"]),
    )
    ranking, ranking_manifest = validate_ranking_artifact(
        ranking_path, expected_contract=expected_contract
    )
    _, finalists, _ = validate_stage2_selection_artifact(
        stage2_selection_path,
        ranking=ranking,
        ranking_path=ranking_path,
        design_path=design_path,
        expected_contract=expected_contract,
    )
    stage3_events, checkpoint_metadata, _ = validate_completed_deep_stage(
        stage3_dir,
        expected_models=finalists,
        expected_seeds=VALIDATION_DEEP_SEEDS,
        expected_contract=expected_contract,
        expected_stage_name="deep_stability",
    )
    budget_unstable = stage3_budget_unstable_models(checkpoint_metadata, finalists)
    decision, _, go_event_paths = validate_go_no_go_artifact(
        go_no_go_path,
        branch_metrics_path=branch_metrics_path,
        design_path=design_path,
        expected_contract=expected_contract,
        stage2_selection_path=stage2_selection_path,
        ranking_path=ranking_path,
        stage2_finalists=finalists,
    )
    stage3_models = set(stage3_events["model"].astype(str))
    if stage3_models != set(finalists):
        raise ValueError("completed stage-3 models differ from stage-2 finalists")
    if "proposed" in finalists:
        branch, _ = validate_branch_ablation_artifact(
            branch_metrics_path, expected_contract=expected_contract
        )
        stage3_event_path = Path(stage3_dir) / "event_metrics.parquet"
        if stage3_event_path.resolve() not in {
            path.resolve() for path in go_event_paths
        }:
            raise ValueError(
                "go/no-go decision is not bound to the completed stage-3 table"
            )
        if set(branch["training_seed"].astype(int)) != set(VALIDATION_DEEP_SEEDS):
            raise ValueError("branch ablation is not complete for stage-3 seeds")
        if decision.get("assessment_mode", "full_stage3") != "full_stage3":
            raise ValueError(
                "proposed stage-3 finalist requires full go/no-go evidence"
            )
    elif decision.get("assessment_mode") != "early_framework_only":
        raise ValueError(
            "proposed stage-2 exclusion requires explicit early framework-only evidence"
        )

    traditional = ranking.loc[
        ranking["model"].astype(str).isin(TRADITIONAL_CANDIDATES)
    ].sort_values("rank", kind="mergesort")
    if len(traditional) != len(TRADITIONAL_CANDIDATES):
        raise ValueError("ranking omits a frozen traditional T candidate")
    best_traditional = str(traditional.iloc[0]["model"])
    if decision.get("best_traditional_model") != best_traditional:
        raise ValueError("go/no-go and ranking best traditional models disagree")
    proposed_decision = str(decision["decision"])
    if "proposed" in budget_unstable:
        proposed_decision = "framework_only"
    selected_deep = [
        model
        for model in finalists
        if model not in budget_unstable
        and (model != "proposed" or proposed_decision == "include_proposed_formally")
    ]
    selected_models = [*TRADITIONAL_CANDIDATES, *selected_deep]
    if set(selected_models).intersection({"rating_curve", "independent_flow"}):
        raise AssertionError("F-only structural baselines leaked into the T roster")
    if ("proposed" in selected_models) != (
        proposed_decision == "include_proposed_formally"
    ):
        raise AssertionError("proposed decision and roster selection disagree")
    frozen_design = load_frozen_model_design(design_path)
    internal_structural = {"rating_curve", "independent_flow"}
    if not internal_structural.issubset(frozen_design.formal_candidates):
        raise ValueError("F-only structural baselines are not frozen internally")

    artifacts = {
        "ranking": _file_identity(ranking_path),
        "stage2_selection": _file_identity(stage2_selection_path),
        "go_no_go": _file_identity(go_no_go_path),
    }
    if str(expected_contract.get("design_version")) == "design_freeze_v4":
        raw_event_inputs = ranking_manifest.get("event_metrics")
        if not isinstance(raw_event_inputs, list) or not raw_event_inputs:
            raise ValueError(
                "v4 roster requires validation event inputs for best-simple lookup"
            )
        ranking_manifest_path = Path(ranking_path).with_suffix(".manifest.json")
        event_paths = [
            _verify_file_identity(
                identity,
                relative_to=ranking_manifest_path.parent,
                context="best-simple validation event input",
            )[0]
            for identity in raw_event_inputs
        ]
        validation_events = read_validation_event_tables(event_paths)
        best_simple = select_best_simple_baselines(validation_events)
        best_simple = best_simple.loc[best_simple["target"].astype(str).eq("T")].copy()
        if best_simple.empty:
            raise ValueError("v4 best-simple lookup contains no target-T families")
        best_simple["data_version"] = str(expected_contract["data_version"])
        lookup_path = Path(output_path).parent / "best_simple_baseline_lookup.csv"
        if lookup_path.exists():
            raise FileExistsError(
                f"refusing to overwrite immutable lookup: {lookup_path}"
            )
        _atomic_csv(best_simple, lookup_path)
        artifacts["best_simple_baseline_lookup"] = _file_identity(lookup_path)
    artifacts = {
        name: {"path": identity["path"]}
        for name, identity in artifacts.items()
    }
    payload = {
        "schema_version": FINALIZED_MODEL_ROSTER_SCHEMA_VERSION,
        "finalized": True,
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        "selected_models": selected_models,
        "best_traditional_model": best_traditional,
        "proposed_decision": proposed_decision,
        "validation_anchor_catalog": validation_anchor_identity,
        "artifacts": artifacts,
        **_canonical_contract(expected_contract),
        "code_provenance": json.loads(
            json.dumps(expected_contract.get("code_provenance"))
        ),
    }
    output = Path(output_path)
    _immutable_json(payload, output)

    # Exercise the exact downstream gate immediately.  This is validation only;
    # the loader performs no network or confirmatory-data access.
    from stream_recoverability.data.confirmatory import load_finalized_model_roster

    try:
        selection_version = load_frozen_data_versions(design_path).primary
        validated = load_finalized_model_roster(
            output,
            design_path=design_path,
            study_manifest_path=study_manifest_path,
            experiment_config_path=experiment_config_path,
            selection_data_version=selection_version,
            selection_data_version_manifest_path=data_version_manifest_path,
        )
    except Exception:
        # A roster that the downstream gate rejects must not remain as apparent
        # authorization.  It was created in this invocation and is safe to remove.
        output.unlink(missing_ok=True)
        raise
    if tuple(validated.selected_models) != tuple(selected_models):
        output.unlink(missing_ok=True)
        raise RuntimeError("downstream roster loader changed the selected model order")
    return payload


__all__ = [
    "ALL_INFORMATION_COMBINATIONS",
    "BRANCH_ABLATION_COMBINATIONS",
    "BRANCH_ABLATION_GAPS",
    "BRANCH_ABLATION_MANIFEST_SCHEMA_VERSION",
    "BRANCH_ABLATION_NOT_APPLICABLE_SCHEMA_VERSION",
    "DIAGNOSTICS_MANIFEST_SCHEMA_VERSION",
    "FINALIZED_MODEL_ROSTER_SCHEMA_VERSION",
    "GO_NO_GO_SCHEMA_VERSION",
    "RANKING_MANIFEST_SCHEMA_VERSION",
    "STAGE2_SELECTION_MANIFEST_SCHEMA_VERSION",
    "PROPOSED_DONOR_KEY_STRATA",
    "load_proposed_versus_donor_rule",
    "assess_proposed_versus_donor",
    "execute_validation_branch_ablation",
    "extract_stage2_diagnostics",
    "finalize_validation_roster",
    "read_validation_event_tables",
    "stage3_budget_unstable_models",
    "summarize_stage3_stability",
    "validate_branch_ablation_artifact",
    "validate_branch_ablation_not_applicable_artifact",
    "validate_completed_deep_stage",
    "validate_go_no_go_artifact",
    "validate_ranking_artifact",
    "validate_stage2_selection_artifact",
    "write_early_framework_only_decision",
    "write_stage2_diagnostics",
]
