#!/usr/bin/env python3
"""Fail-closed aggregation of finalized formal experiment suites.

The aggregator deliberately has no built-in model roster or scenario counts.  A
finalized suite registry names every accepted input directory and model.  Each
runner manifest then supplies its own exact run-unit contract; the tables must
satisfy that contract before any aggregate is replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.contracts import (
    build_design_contract,
    canonical_evaluation_split,
    file_sha256,
)

DAILY_KEY = (
    "scenario_id",
    "model",
    "training_seed",
    "mask_seed",
    "date",
    "station_id",
    "target",
)
EVENT_KEY = (
    "scenario_id",
    "model",
    "training_seed",
    "mask_seed",
    "station_id",
    "target",
)
REQUIRED_EVIDENCE_FIELDS = (
    "design_version",
    "design_hash",
    "data_version",
    "evaluation_split",
    "mask_schema_version",
    "model_schema_version",
    "statistics_schema_version",
)
REQUIRED_MANIFEST_CONTRACT_FIELDS = (
    *REQUIRED_EVIDENCE_FIELDS,
    "input_digests",
    "code_identity",
)
RUN_UNIT_LIST_FIELDS = (
    "expected_run_unit_keys",
    "completed_run_unit_keys",
    "retryable_run_unit_keys",
    "structural_skip_run_unit_keys",
    "expected_evidence_run_unit_keys",
    "completed_evidence_run_unit_keys",
    "finite_prediction_run_unit_keys",
    "finite_event_metric_run_unit_keys",
    "checkpoint_required_run_unit_keys",
    "checkpoint_valid_run_unit_keys",
)
RUN_UNIT_COUNT_FIELDS = {
    **{field: f"{field.removesuffix('_keys')}_count" for field in RUN_UNIT_LIST_FIELDS},
    "checkpoint_required_run_unit_keys": "checkpoint_required_run_count",
    "checkpoint_valid_run_unit_keys": "checkpoint_valid_run_count",
}
RUN_UNIT_BOOLEAN_FIELDS = (
    "run_unit_complete",
    "evidence_complete",
    "finite_predictions",
    "finite_event_metrics",
    "checkpoint_contract_complete",
)
SUMMARY_GROUP_COLUMNS = (
    *REQUIRED_EVIDENCE_FIELDS,
    "evidence_role",
    "experiment",
    "mask_type",
    "layout",
    "outage_mode",
    "overlap_ratio",
    "window_length",
    "training_protocol",
    "fit_split",
    "tuning_split",
    "validation_scope",
    "station_id",
    "target",
    "model",
    "variable_pattern",
    "pattern",
    "gap_length",
    "missing_rate",
    "event_type",
    "target_station_id",
    "failed_station_ids",
    "failed_stations",
    "failure_count",
    "network_size",
    "information_combination",
    "component_estimator",
)
SUMMARY_METRIC_COLUMNS = (
    "MAE",
    "RMSE",
    "bias",
    "NMAE",
    "NRMSE",
    "skill",
    "coverage_90",
    "interval_width_90",
)


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "size": stat.st_size,
        "sha256": file_sha256(resolved),
    }


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON mapping: {path}")
    return value


def _load_registry(
    registry: Mapping[str, Any] | str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(registry, Mapping):
        value = json.loads(json.dumps(dict(registry)))
        identity = {
            "source": "explicit_mapping",
            "sha256": _canonical_sha256(value),
        }
    else:
        path = Path(registry)
        value = _read_mapping(path, "formal suite registry")
        identity = {"source": "registry_file", **_file_identity(path)}
    if value.get("schema_version") != "formal_suite_registry_v1":
        raise ValueError(
            "suite registry schema_version must be formal_suite_registry_v1"
        )
    if value.get("finalized") is not True:
        raise ValueError("suite registry must be explicitly finalized")
    suites = value.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("suite registry must declare at least one suite")
    return value, identity


def _string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(
            f"{label} must be a{' possibly empty' if allow_empty else ' non-empty'} list"
        )
    if not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"{label} must contain non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate values")
    return list(value)


def _count(manifest: Mapping[str, Any], field: str, label: str) -> int:
    value = manifest.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} has invalid {field}: {value!r}")
    return value


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def _seed_label(value: object, label: str) -> str:
    if pd.isna(value):
        return "none"
    numeric = float(value)
    if not np.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{label} has invalid training_seed {value!r}")
    return str(int(numeric))


def _run_unit_keys(frame: pd.DataFrame, label: str) -> set[str]:
    _require_columns(frame, ("scenario_id", "model", "training_seed"), label)
    result: set[str] = set()
    for scenario, model, seed in frame.loc[
        :, ["scenario_id", "model", "training_seed"]
    ].itertuples(index=False, name=None):
        scenario_label = str(scenario)
        model_label = str(model)
        if (
            not scenario_label
            or "|" in scenario_label
            or not model_label
            or ":" in model_label
        ):
            raise ValueError(
                f"{label} has a run-unit identifier that cannot be canonicalized"
            )
        result.add(f"{scenario_label}|{model_label}:{_seed_label(seed, label)}")
    return result


def _parse_run_unit_key(value: str, label: str) -> tuple[str, str, str]:
    try:
        scenario, model_seed = value.split("|", maxsplit=1)
        model, seed = model_seed.rsplit(":", maxsplit=1)
    except ValueError as error:
        raise ValueError(f"{label} has malformed run-unit key {value!r}") from error
    if not scenario or not model or "|" in model_seed or ":" in model:
        raise ValueError(f"{label} has malformed run-unit key {value!r}")
    if seed != "none":
        try:
            numeric_seed = int(seed)
        except ValueError as error:
            raise ValueError(f"{label} has malformed run-unit key {value!r}") from error
        if str(numeric_seed) != seed or numeric_seed < 0:
            raise ValueError(f"{label} has malformed run-unit key {value!r}")
    return scenario, model, seed


def _require_evidence_contract(
    value: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    missing = sorted(set(REQUIRED_MANIFEST_CONTRACT_FIELDS).difference(value))
    if missing:
        raise ValueError(f"{label} is stale or pre-freeze; missing {missing}")
    mismatch = {
        field: (value.get(field), expected.get(field))
        for field in REQUIRED_MANIFEST_CONTRACT_FIELDS
        if value.get(field) != expected.get(field)
    }
    if mismatch:
        raise ValueError(f"{label} evidence contract mismatch: {mismatch}")


def _require_table_contract(
    frame: pd.DataFrame, expected: Mapping[str, Any], label: str
) -> None:
    _require_columns(frame, REQUIRED_EVIDENCE_FIELDS, label)
    for field in REQUIRED_EVIDENCE_FIELDS:
        values = set(frame[field].dropna().astype(str))
        if frame[field].isna().any() or values != {str(expected[field])}:
            raise ValueError(
                f"{label} mixes, omits, or contains stale {field}: {sorted(values)}"
            )


def _require_unique(frame: pd.DataFrame, key: Sequence[str], label: str) -> None:
    _require_columns(frame, key, label)
    if frame.duplicated(list(key), keep=False).any():
        raise ValueError(f"{label} contains duplicate rows for its frozen key")


def _require_finite_tables(
    daily: pd.DataFrame, events: pd.DataFrame, label: str
) -> None:
    _require_columns(daily, ("y_true", "y_pred"), f"{label} daily")
    _require_columns(events, ("MAE", "RMSE"), f"{label} events")
    for frame, columns, table_label in (
        (daily, ("y_true", "y_pred"), "daily predictions"),
        (events, ("MAE", "RMSE"), "event metrics"),
    ):
        for column in columns:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
            if not np.isfinite(values).all():
                raise ValueError(f"{label} {table_label} has nonfinite {column}")


def _manifest_key_sets(manifest: Mapping[str, Any], label: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for field in RUN_UNIT_LIST_FIELDS:
        values = _string_list(manifest.get(field), f"{label}.{field}", allow_empty=True)
        count = _count(manifest, RUN_UNIT_COUNT_FIELDS[field], label)
        if count != len(values):
            raise ValueError(f"{label} {field} disagrees with its count")
        for value in values:
            _parse_run_unit_key(value, f"{label}.{field}")
        result[field] = set(values)
    return result


def _require_checkpoint_identities(manifest: Mapping[str, Any], label: str) -> None:
    required = _count(manifest, "checkpoint_required_run_count", label)
    summaries = manifest.get("training_checkpoints")
    if not isinstance(summaries, list):
        raise TypeError(f"{label}.training_checkpoints must be a list")
    if required and not summaries:
        raise ValueError(
            f"{label} requires checkpoints but declares no checkpoint artifacts"
        )
    for position, summary in enumerate(summaries):
        item_label = f"{label}.training_checkpoints[{position}]"
        if not isinstance(summary, Mapping):
            raise TypeError(f"{item_label} must be a mapping")
        if summary.get("checkpoint_contract_valid") is not True:
            raise ValueError(f"{item_label} has no valid checkpoint contract")
        checkpoint = summary.get("checkpoint")
        if not isinstance(checkpoint, Mapping):
            raise TypeError(f"{item_label}.checkpoint must be a file identity")
        _require_current_file_identity(checkpoint, f"{item_label}.checkpoint")
        sidecar = summary.get("checkpoint_sidecar")
        if sidecar is not None:
            if not isinstance(sidecar, Mapping):
                raise TypeError(
                    f"{item_label}.checkpoint_sidecar must be null or a mapping"
                )
            _require_current_file_identity(sidecar, f"{item_label}.checkpoint_sidecar")


def _require_current_file_identity(identity: Mapping[str, Any], label: str) -> None:
    path_value = identity.get("path")
    expected_sha = identity.get("sha256")
    expected_size = identity.get("size")
    if (
        not isinstance(path_value, str)
        or not path_value
        or not isinstance(expected_sha, str)
    ):
        raise ValueError(f"{label} lacks path/sha256")
    path = Path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    if expected_size != path.stat().st_size or expected_sha != file_sha256(path):
        raise ValueError(f"{label} does not match its recorded size/hash")


def _require_complete_manifest(manifest: Mapping[str, Any], label: str) -> None:
    for field in (
        "complete",
        "formal_design_complete",
        "formal_training_seed_complete",
        "formal_mask_seed_complete",
        *RUN_UNIT_BOOLEAN_FIELDS,
    ):
        if manifest.get(field) is not True:
            raise ValueError(f"{label} requires {field}=true")
    for field, value in manifest.items():
        if (
            field.startswith("formal_")
            and field.endswith("_complete")
            and value is not True
        ):
            raise ValueError(f"{label} has incomplete formal gate {field}")
    if manifest.get("training_profile") != "formal":
        raise ValueError(f"{label} training_profile must be formal")


def _validate_run_directory(
    directory: Path,
    *,
    expected_suite: str,
    expected_models: Sequence[str],
    allowed_table_models: set[str],
    expected_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path = directory / "run_manifest.json"
    daily_path = directory / "daily_predictions.parquet"
    event_path = directory / "event_metrics.parquet"
    manifest = _read_mapping(manifest_path, "runner manifest")
    _require_complete_manifest(manifest, str(manifest_path))
    _require_evidence_contract(manifest, expected_evidence, str(manifest_path))
    if manifest.get("suite") != expected_suite:
        raise ValueError(f"{manifest_path} suite does not match registry")
    models = _string_list(manifest.get("models"), f"{manifest_path}.models")
    if models != list(expected_models):
        raise ValueError(
            f"{manifest_path} model roster does not match finalized registry"
        )
    if manifest.get("retryable_run_keys") != []:
        raise ValueError(f"{manifest_path} retryable_run_keys must be an empty list")

    if not daily_path.is_file() or not event_path.is_file():
        raise FileNotFoundError(f"{directory} is missing frozen daily/event tables")
    daily = pd.read_parquet(daily_path)
    events = pd.read_parquet(event_path)
    _require_table_contract(daily, expected_evidence, str(daily_path))
    _require_table_contract(events, expected_evidence, str(event_path))
    _require_unique(daily, DAILY_KEY, str(daily_path))
    _require_unique(events, EVENT_KEY, str(event_path))
    _require_finite_tables(daily, events, str(directory))
    observed_models = set(daily["model"].astype(str)).union(events["model"].astype(str))
    if not observed_models.issubset(allowed_table_models):
        raise ValueError(f"{directory} has models outside the finalized registry")

    keys = _manifest_key_sets(manifest, str(manifest_path))
    expected = keys["expected_run_unit_keys"]
    completed = keys["completed_run_unit_keys"]
    retryable = keys["retryable_run_unit_keys"]
    structural = keys["structural_skip_run_unit_keys"]
    expected_evidence_keys = keys["expected_evidence_run_unit_keys"]
    completed_evidence = keys["completed_evidence_run_unit_keys"]
    finite_predictions = keys["finite_prediction_run_unit_keys"]
    finite_events = keys["finite_event_metric_run_unit_keys"]
    checkpoint_required = keys["checkpoint_required_run_unit_keys"]
    checkpoint_valid = keys["checkpoint_valid_run_unit_keys"]
    expected_models_in_keys = {
        _parse_run_unit_key(key, str(manifest_path))[1] for key in expected
    }
    if not expected_models_in_keys.issubset(allowed_table_models):
        raise ValueError(f"{manifest_path} run-unit contract contains unlisted models")
    daily_keys = _run_unit_keys(daily, str(daily_path))
    event_keys = _run_unit_keys(events, str(event_path))
    if retryable:
        raise ValueError(f"{manifest_path} has retryable run units")
    if completed != expected:
        raise ValueError(f"{manifest_path} completed run units differ from expected")
    if not structural.issubset(expected):
        raise ValueError(f"{manifest_path} has undeclared structural skips")
    if expected_evidence_keys != expected - structural:
        raise ValueError(
            f"{manifest_path} structural-skip/evidence contract is inconsistent"
        )
    if not (
        completed_evidence
        == expected_evidence_keys
        == finite_predictions
        == finite_events
        == daily_keys
        == event_keys
    ):
        raise ValueError(f"{manifest_path} expected daily/event evidence is incomplete")
    if checkpoint_required != checkpoint_valid or not checkpoint_required.issubset(
        expected
    ):
        raise ValueError(f"{manifest_path} checkpoint run-unit contract is incomplete")

    if _count(manifest, "completed_daily_rows", str(manifest_path)) != len(daily):
        raise ValueError(f"{manifest_path} completed_daily_rows differs from table")
    if _count(manifest, "completed_event_rows", str(manifest_path)) != len(events):
        raise ValueError(f"{manifest_path} completed_event_rows differs from table")
    for legacy_field, observed in (
        ("expected_run_count", len(expected)),
        ("completed_status_run_count", len(completed)),
        ("aggregate_run_count", len(completed_evidence)),
    ):
        if (
            legacy_field in manifest
            and _count(manifest, legacy_field, str(manifest_path)) != observed
        ):
            raise ValueError(
                f"{manifest_path} {legacy_field} contradicts exact run units"
            )
    _require_checkpoint_identities(manifest, str(manifest_path))
    return {
        "directory": str(directory.resolve()),
        "daily": daily,
        "events": events,
        "expected_run_units": expected,
        "completed_run_units": completed,
        "structural_skip_run_units": structural,
        "expected_evidence_run_units": expected_evidence_keys,
        "checkpoint_required_run_units": checkpoint_required,
        "source": {
            "directory": str(directory.resolve()),
            "manifest": _file_identity(manifest_path),
            "daily_predictions": _file_identity(daily_path),
            "event_metrics": _file_identity(event_path),
            "models": models,
            "expected_run_unit_count": len(expected),
            "completed_run_unit_count": len(completed),
            "structural_skip_run_unit_count": len(structural),
            "expected_evidence_run_unit_count": len(expected_evidence_keys),
            "checkpoint_required_run_unit_count": len(checkpoint_required),
        },
    }


def _safe_suite_root(formal_root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label}.path must be a non-empty relative path")
    path = Path(relative)
    if path.is_absolute():
        raise ValueError(f"{label}.path must be relative to formal_root")
    resolved_root = formal_root.resolve()
    resolved = (formal_root / path).resolve()
    if resolved_root not in resolved.parents:
        raise ValueError(f"{label}.path escapes formal_root")
    return resolved


def _validate_registry_suite(
    formal_root: Path,
    entry: object,
    expected_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise TypeError("each suite registry entry must be a mapping")
    name = str(entry.get("name", "")).strip()
    if not name:
        raise ValueError("suite registry entry requires a name")
    if entry.get("finalized") is not True:
        raise ValueError(f"suite {name!r} is not finalized")
    manifest_suite = str(entry.get("manifest_suite", "")).strip()
    if not manifest_suite:
        raise ValueError(f"suite {name!r} requires manifest_suite")
    roster = _string_list(
        entry.get("finalized_models"), f"suite {name}.finalized_models"
    )
    derived = _string_list(
        entry.get("allowed_derived_models", []),
        f"suite {name}.allowed_derived_models",
        allow_empty=True,
    )
    if set(roster).intersection(derived):
        raise ValueError(f"suite {name!r} duplicates finalized and derived models")
    layout = entry.get("layout", "direct")
    suite_root = _safe_suite_root(formal_root, entry.get("path"), f"suite {name}")
    allowed_models = set(roster) | set(derived)
    if layout == "direct":
        runs = [
            _validate_run_directory(
                suite_root,
                expected_suite=manifest_suite,
                expected_models=roster,
                allowed_table_models=allowed_models,
                expected_evidence=expected_evidence,
            )
        ]
    elif layout == "model_children":
        if not suite_root.is_dir():
            raise FileNotFoundError(f"missing declared suite directory: {suite_root}")
        children = sorted(path.name for path in suite_root.iterdir() if path.is_dir())
        if set(children) != set(roster):
            raise ValueError(
                f"suite {name!r} child directories differ from finalized roster: "
                f"observed={children}, expected={sorted(roster)}"
            )
        runs = [
            _validate_run_directory(
                suite_root / model,
                expected_suite=manifest_suite,
                expected_models=[model],
                allowed_table_models={model, *derived},
                expected_evidence=expected_evidence,
            )
            for model in roster
        ]
    else:
        raise ValueError(f"suite {name!r} has unsupported layout {layout!r}")
    return {
        "name": name,
        "manifest_suite": manifest_suite,
        "layout": layout,
        "root": str(suite_root),
        "finalized_models": roster,
        "allowed_derived_models": derived,
        "runs": runs,
    }


def _summary_metrics(events: pd.DataFrame) -> pd.DataFrame:
    _require_columns(events, ("model", "target", "MAE", "RMSE"), "event metrics")
    groups = [column for column in SUMMARY_GROUP_COLUMNS if column in events.columns]
    metrics = [column for column in SUMMARY_METRIC_COLUMNS if column in events.columns]
    data = events.copy()
    for column in metrics:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    grouped = data.groupby(groups, dropna=False, observed=True, sort=True)
    means = grouped[metrics].mean().reset_index()
    counts = grouped.size().rename("n_events").reset_index()
    return means.merge(counts, on=groups, how="left", validate="one_to_one")


def aggregate_formal_results(
    formal_root: str | Path,
    results_root: str | Path,
    *,
    suite_registry: Mapping[str, Any] | str | Path,
    design_path: str | Path = PROJECT_ROOT / "configs/design_freeze_v1.yaml",
    manifest_path: str | Path = PROJECT_ROOT / "study_manifest.yaml",
    config_path: str | Path = PROJECT_ROOT / "configs/experiments.yaml",
    data_version: str = "published_v1",
    evaluation_split: str = "development_test",
    data_version_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate every declared source and atomically write frozen aggregates."""

    canonical_split = canonical_evaluation_split(evaluation_split)
    if canonical_split != "development_test":
        raise ValueError(
            "formal aggregation is restricted to canonical development_test"
        )
    formal = Path(formal_root)
    results = Path(results_root)
    registry, registry_identity = _load_registry(suite_registry)
    if data_version_manifest_path is None:
        candidate = (
            PROJECT_ROOT / "data_versions" / data_version / "version_manifest.json"
        )
        data_version_manifest_path = candidate if candidate.is_file() else None
    evidence = build_design_contract(
        design_path=design_path,
        manifest_path=manifest_path,
        experiment_config_path=config_path,
        data_version=data_version,
        evaluation_split=canonical_split,
        data_version_manifest_path=data_version_manifest_path,
    )
    suites = [
        _validate_registry_suite(formal, entry, evidence)
        for entry in registry["suites"]
    ]
    names = [suite["name"] for suite in suites]
    if len(set(names)) != len(names):
        raise ValueError("suite registry contains duplicate suite names")
    run_directories = [run["directory"] for suite in suites for run in suite["runs"]]
    if len(set(run_directories)) != len(run_directories):
        raise ValueError(
            "suite registry declares the same run directory more than once"
        )

    daily_parts = [run["daily"] for suite in suites for run in suite["runs"]]
    event_parts = [run["events"] for suite in suites for run in suite["runs"]]
    daily = pd.concat(daily_parts, ignore_index=True, sort=False)
    events = pd.concat(event_parts, ignore_index=True, sort=False)
    _require_unique(daily, DAILY_KEY, "combined formal daily predictions")
    _require_unique(events, EVENT_KEY, "combined formal event metrics")
    daily_keys = _run_unit_keys(daily, "combined formal daily predictions")
    event_keys = _run_unit_keys(events, "combined formal event metrics")
    if daily_keys != event_keys:
        raise ValueError("combined formal daily/event evidence run units differ")
    expected_sets = [
        run["expected_run_units"] for suite in suites for run in suite["runs"]
    ]
    if sum(map(len, expected_sets)) != len(set().union(*expected_sets)):
        raise ValueError("formal suites contain duplicate run-unit keys")
    expected = set().union(*expected_sets)
    structural = set().union(
        *(run["structural_skip_run_units"] for suite in suites for run in suite["runs"])
    )
    if daily_keys != expected - structural:
        raise ValueError(
            "combined formal tables do not close the dynamic run-unit contract"
        )
    summary = _summary_metrics(events)

    predictions_path = results / "predictions.parquet"
    event_metrics_path = results / "event_metrics.parquet"
    summary_path = results / "summary_metrics.csv"
    _atomic_parquet(daily, predictions_path)
    _atomic_parquet(events, event_metrics_path)
    _atomic_csv(summary, summary_path)
    sources = [run["source"] for suite in suites for run in suite["runs"]]
    manifest = {
        "schema_version": "formal_aggregate_manifest_v2",
        "frozen": True,
        "complete": True,
        "formal_design_complete": True,
        "formal_training_seed_complete": True,
        "formal_mask_seed_complete": True,
        "training_profile": "formal",
        "run_unit_complete": True,
        "evidence_complete": True,
        "finite_predictions": True,
        "finite_event_metrics": True,
        "checkpoint_contract_complete": True,
        "retryable_run_keys": [],
        "retryable_run_unit_count": 0,
        "suite_registry": registry_identity,
        "suite_count": len(suites),
        "source_run_count": len(sources),
        "suites": [
            {
                "name": suite["name"],
                "manifest_suite": suite["manifest_suite"],
                "layout": suite["layout"],
                "root": suite["root"],
                "finalized_models": suite["finalized_models"],
                "allowed_derived_models": suite["allowed_derived_models"],
                "source_run_count": len(suite["runs"]),
                "expected_run_unit_count": sum(
                    len(run["expected_run_units"]) for run in suite["runs"]
                ),
                "structural_skip_run_unit_count": sum(
                    len(run["structural_skip_run_units"]) for run in suite["runs"]
                ),
                "completed_evidence_run_unit_count": sum(
                    len(run["expected_evidence_run_units"]) for run in suite["runs"]
                ),
            }
            for suite in suites
        ],
        "expected_run_unit_count": len(expected),
        "completed_run_unit_count": len(expected),
        "expected_run_unit_keys_sha256": _canonical_sha256(sorted(expected)),
        "completed_run_unit_keys_sha256": _canonical_sha256(sorted(expected)),
        "structural_skip_run_unit_count": len(structural),
        "structural_skip_run_unit_keys_sha256": _canonical_sha256(sorted(structural)),
        "expected_evidence_run_unit_count": len(expected - structural),
        "completed_evidence_run_unit_count": len(daily_keys),
        "evidence_run_unit_keys_sha256": _canonical_sha256(sorted(daily_keys)),
        "daily_rows": len(daily),
        "event_rows": len(events),
        "summary_rows": len(summary),
        "artifacts": {
            "predictions": _file_identity(predictions_path),
            "event_metrics": _file_identity(event_metrics_path),
            "summary_metrics": _file_identity(summary_path),
        },
        "sources": sources,
        **evidence,
    }
    _atomic_json(manifest, formal / "run_manifest.json")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--suite-registry", type=Path, required=True)
    parser.add_argument(
        "--design", type=Path, default=PROJECT_ROOT / "configs/design_freeze_v1.yaml"
    )
    parser.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "configs/experiments.yaml"
    )
    parser.add_argument("--data-version", default="published_v1")
    parser.add_argument("--evaluation-split", default="development_test")
    parser.add_argument("--data-version-manifest", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = aggregate_formal_results(
        args.formal_root,
        args.results_root,
        suite_registry=args.suite_registry,
        design_path=args.design,
        manifest_path=args.manifest,
        config_path=args.config,
        data_version=args.data_version,
        evaluation_split=args.evaluation_split,
        data_version_manifest_path=args.data_version_manifest,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
