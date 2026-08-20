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

from stream_recoverability.data.confirmatory import load_finalized_model_roster
from stream_recoverability.experiments.contracts import (
    build_design_contract,
    canonical_evaluation_split,
    file_sha256,
    validate_data_version_inputs,
)
from stream_recoverability.experiments.formal_authorization import (
    FRONTIER_ANCHORED_MASK_TYPES,
    validate_formal_authorization,
)
from stream_recoverability.masks.anchors import load_frontier_anchor_catalog
from stream_recoverability.masks.event_catalog import (
    event_catalog_sha256,
    load_event_episode_catalog,
)

PRIMARY_SUITE_ROLES = (
    "core_full",
    "dense_frontier",
    "network_resilience",
    "event_uncertainty",
    "operational_dropout",
    "retrained_upper_bound",
)
SENSITIVITY_SUITE_ROLES = (
    "sensitivity_core_T",
    "sensitivity_dense_frontier",
    "sensitivity_operational_dropout",
)
STRUCTURAL_BASELINES = ("independent_flow", "rating_curve")
CANONICAL_FRONTIER_ANCHOR_PATH = PROJECT_ROOT / "metadata/frontier_anchors.csv"
DERIVED_FORMAL_MODELS = {
    "science_compensation": "information_compensation",
    "retrained_information_upper_bounds": "retrained_information_upper_bound",
}
PRIMARY_SUITE_ROLE_EQUIVALENTS = {
    "full": ("core_full", "event_uncertainty"),
    "science_dense": ("dense_frontier",),
    "science_resilience": ("network_resilience",),
    "science_compensation": ("operational_dropout",),
    "retrained_information_upper_bounds": ("retrained_upper_bound",),
}
SENSITIVITY_SUITE_ROLE_EQUIVALENTS = {
    "core": ("sensitivity_core_T",),
    "science_dense": ("sensitivity_dense_frontier",),
    "science_compensation": ("sensitivity_operational_dropout",),
}

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
    "attribution_estimand",
    "information_estimand",
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
    if (
        value.get("registry_hash_scope")
        != "canonical_json_excluding_registry_sha256"
    ):
        raise ValueError("suite registry has an unknown canonical hash scope")
    persisted_hash = value.get("registry_sha256")
    unsigned = {key: item for key, item in value.items() if key != "registry_sha256"}
    if persisted_hash != _canonical_sha256(unsigned):
        raise ValueError("suite registry canonical SHA-256 does not match its content")
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


def _repository_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _registry_file_identity(
    value: object, *, label: str, required_path: Path | None = None
) -> Path:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a file identity")
    path = _repository_path(value.get("path"), f"{label}.path")
    if required_path is not None and path.resolve() != required_path.resolve():
        raise ValueError(f"{label} points to a different artifact")
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    expected_sha = value.get("sha256")
    expected_bytes = value.get("bytes", value.get("size"))
    if expected_sha != file_sha256(path) or expected_bytes != path.stat().st_size:
        raise ValueError(f"{label} does not match its recorded bytes/SHA-256")
    return path


def _expected_role_models(
    role: str, selected_models: Sequence[str]
) -> list[str]:
    selected = list(selected_models)
    if role in {"core_full", "dense_frontier", "event_uncertainty"}:
        return [*selected, *STRUCTURAL_BASELINES]
    if role == "network_resilience":
        return selected
    if role in {"operational_dropout", "sensitivity_operational_dropout"}:
        return ["information_compensation"]
    if role == "retrained_upper_bound":
        return ["retrained_information_upper_bound"]
    if role in {"sensitivity_core_T", "sensitivity_dense_frontier"}:
        return selected
    raise ValueError(f"unknown registry suite role {role!r}")


def _validate_registry_contract(
    registry: Mapping[str, Any],
    *,
    formal_root: Path,
    expected_evidence: Mapping[str, Any],
    data_version: str,
    evaluation_split: str,
    data_version_manifest_path: Path,
    design_path: str | Path,
    study_manifest_path: str | Path,
    config_path: str | Path,
) -> dict[str, Any]:
    """Revalidate every trust-bearing field emitted by the registry builder."""

    expected_bundle_role = (
        "primary" if data_version == "published_v1" else "sensitivity_compact"
    )
    expected_bundle_kind = (
        "primary" if data_version == "published_v1" else "sensitivity"
    )
    for field, expected in (
        ("bundle_role", expected_bundle_role),
        ("bundle_kind", expected_bundle_kind),
        ("data_version", data_version),
        ("evaluation_split", evaluation_split),
        ("design_hash", expected_evidence["design_hash"]),
        ("code_identity", expected_evidence["code_identity"]),
    ):
        if registry.get(field) != expected:
            raise ValueError(f"suite registry {field} does not match frozen execution")
    registry_root = _repository_path(registry.get("formal_root"), "formal_root")
    if registry_root.resolve() != formal_root.resolve():
        raise ValueError("suite registry formal_root differs from aggregation root")
    _registry_file_identity(
        registry.get("data_version_manifest"),
        label="registry data-version manifest",
        required_path=data_version_manifest_path,
    )

    raw_roster = registry.get("finalized_model_roster")
    if not isinstance(raw_roster, Mapping):
        raise TypeError("suite registry lacks finalized_model_roster")
    if set(raw_roster) != {"path", "sha256", "selected_models", "proposed_decision"}:
        raise ValueError("suite registry finalized roster fields are not frozen")
    roster_path = _repository_path(raw_roster.get("path"), "finalized roster path")
    roster = load_finalized_model_roster(
        roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=config_path,
        selection_data_version="published_v1",
        selection_data_version_manifest_path=(
            PROJECT_ROOT / "data_versions/published_v1/version_manifest.json"
        ),
    )
    expected_roster = {
        "path": raw_roster["path"],
        "sha256": roster.manifest_sha256,
        "selected_models": list(roster.selected_models),
        "proposed_decision": roster.proposed_decision,
    }
    if dict(raw_roster) != expected_roster:
        raise ValueError("suite registry finalized roster metadata is stale or tampered")

    required_roles = (
        list(PRIMARY_SUITE_ROLES)
        if expected_bundle_role == "primary"
        else list(SENSITIVITY_SUITE_ROLES)
    )
    if registry.get("required_suite_roles") != required_roles:
        raise ValueError("suite registry required role inventory is incomplete")
    raw_roles = registry.get("suite_roles")
    if not isinstance(raw_roles, list) or len(raw_roles) != len(required_roles):
        raise ValueError("suite registry suite_roles do not close required roles")
    roles_by_name: dict[str, dict[str, Any]] = {}
    for item in raw_roles:
        if not isinstance(item, Mapping):
            raise TypeError("suite registry role rows must be mappings")
        role = item.get("role")
        if not isinstance(role, str) or role in roles_by_name:
            raise ValueError("suite registry roles are missing or duplicated")
        roles_by_name[role] = dict(item)
    if set(roles_by_name) != set(required_roles):
        raise ValueError("suite registry role names differ from required roles")

    source_rows = registry.get("sources")
    if not isinstance(source_rows, list) or not source_rows:
        raise ValueError("suite registry requires non-empty hash-bound sources")
    role_equivalents = (
        PRIMARY_SUITE_ROLE_EQUIVALENTS
        if expected_bundle_role == "primary"
        else SENSITIVITY_SUITE_ROLE_EQUIVALENTS
    )
    source_by_hash: dict[str, dict[str, Any]] = {}
    for position, source in enumerate(source_rows):
        if not isinstance(source, Mapping):
            raise TypeError("suite registry source rows must be mappings")
        if set(source) != {
            "suite",
            "run_directory",
            "manifest",
            "daily_predictions",
            "event_metrics",
            "models",
        }:
            raise ValueError("suite registry source fields are not frozen")
        suite = source.get("suite")
        models = _string_list(
            source.get("models"), f"registry.sources[{position}].models"
        )
        if not isinstance(suite, str) or suite not in role_equivalents:
            raise ValueError("suite registry source has no role in this bundle")
        source_path = _registry_file_identity(
            source.get("manifest"), label=f"registry source {position} manifest"
        )
        run_directory = _repository_path(
            source.get("run_directory"), f"registry source {position} run_directory"
        )
        if source_path.parent.resolve() != run_directory.resolve():
            raise ValueError("registry source run directory and manifest disagree")
        daily_path = _registry_file_identity(
            source.get("daily_predictions"),
            label=f"registry source {position} daily predictions",
            required_path=run_directory / "daily_predictions.parquet",
        )
        event_path = _registry_file_identity(
            source.get("event_metrics"),
            label=f"registry source {position} event metrics",
            required_path=run_directory / "event_metrics.parquet",
        )
        digest = file_sha256(source_path)
        if digest in source_by_hash:
            raise ValueError("suite registry contains duplicate source manifests")
        source_manifest = _read_mapping(source_path, "registry source manifest")
        if source_manifest.get("suite") != suite or source_manifest.get("models") != models:
            raise ValueError("registry source suite/models differ from its manifest")
        source_by_hash[digest] = {
            "manifest_sha256": digest,
            "suite": suite,
            "models": models,
            "manifest_path": source_path.resolve(),
            "run_directory": run_directory.resolve(),
            "daily_predictions_path": daily_path.resolve(),
            "daily_predictions_sha256": file_sha256(daily_path),
            "event_metrics_path": event_path.resolve(),
            "event_metrics_sha256": file_sha256(event_path),
        }

    expected_not_applicable = (
        [
            {
                "manifest_suite": suite,
                "status": "not_applicable",
                "reason": "proposed_decision=framework_only",
            }
            for suite in sorted(DERIVED_FORMAL_MODELS)
        ]
        if roster.proposed_decision == "framework_only"
        else []
    )
    if registry.get("not_applicable_suites") != expected_not_applicable:
        raise ValueError("suite registry not_applicable_suites is incomplete")

    proposed_not_applicable = (
        {"operational_dropout", "retrained_upper_bound"}
        if expected_bundle_role == "primary"
        else {"sensitivity_operational_dropout"}
    )
    for role in required_roles:
        item = roles_by_name[role]
        if set(item) != {
            "role",
            "status",
            "reason",
            "manifest_suites",
            "source_manifest_sha256",
            "expected_models",
        }:
            raise ValueError(f"registry role {role} fields are not frozen")
        expected_na = (
            roster.proposed_decision == "framework_only"
            and role in proposed_not_applicable
        )
        if expected_na:
            if item != {
                "role": role,
                "status": "not_applicable",
                "reason": "proposed_decision=framework_only",
                "manifest_suites": [],
                "source_manifest_sha256": [],
                "expected_models": [],
            }:
                raise ValueError(f"registry role {role} must be explicitly not_applicable")
            continue
        if item.get("status") != "complete" or item.get("reason") is not None:
            raise ValueError(f"registry role {role} is not complete")
        suites = _string_list(
            item.get("manifest_suites"), f"registry role {role} manifest_suites"
        )
        hashes = _string_list(
            item.get("source_manifest_sha256"),
            f"registry role {role} source hashes",
        )
        expected_sources = {
            digest: source
            for digest, source in source_by_hash.items()
            if role in role_equivalents[source["suite"]]
        }
        expected_suites = sorted(
            {source["suite"] for source in expected_sources.values()}
        )
        if suites != expected_suites or hashes != sorted(expected_sources):
            raise ValueError(f"registry role {role} source bindings are stale")
        expected_models = _expected_role_models(role, roster.selected_models)
        if item.get("expected_models") != expected_models:
            raise ValueError(f"registry role {role} model contract is stale")
        observed_models = {
            model
            for source in expected_sources.values()
            for model in source["models"]
        }
        if observed_models != set(expected_models):
            raise ValueError(f"registry role {role} source models are incomplete")
    return {
        "bundle_kind": expected_bundle_kind,
        "bundle_role": expected_bundle_role,
        "required_suite_roles": required_roles,
        "suite_roles": [roles_by_name[role] for role in required_roles],
        "finalized_model_roster": {
            "path": raw_roster["path"],
            "sha256": roster.manifest_sha256,
            "selected_models": list(roster.selected_models),
            "proposed_decision": roster.proposed_decision,
        },
        "sources": list(source_by_hash.values()),
    }


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
    _require_columns(
        frame,
        (*REQUIRED_EVIDENCE_FIELDS, "formal_evidence", "evidence_role"),
        label,
    )
    for field in REQUIRED_EVIDENCE_FIELDS:
        values = set(frame[field].dropna().astype(str))
        if frame[field].isna().any() or values != {str(expected[field])}:
            raise ValueError(
                f"{label} mixes, omits, or contains stale {field}: {sorted(values)}"
            )
    if not frame["formal_evidence"].eq(True).all():
        raise ValueError(f"{label} requires formal_evidence=true")
    if not frame["evidence_role"].astype(str).eq(
        "formal_development_evaluation"
    ).all():
        raise ValueError(f"{label} is not formal development evidence")


def _require_unique(frame: pd.DataFrame, key: Sequence[str], label: str) -> None:
    effective_key = list(key)
    if (
        "information_combination" in frame
        and frame["information_combination"].notna().any()
    ):
        effective_key.append("information_combination")
    _require_columns(frame, effective_key, label)
    if frame.duplicated(effective_key, keep=False).any():
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


def _resolve_run_artifact(
    value: object, *, run_directory: Path, label: str
) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty path")
    raw = Path(value)
    candidates = (
        (raw,)
        if raw.is_absolute()
        else (run_directory / raw, PROJECT_ROOT / raw)
    )
    existing = {candidate.resolve() for candidate in candidates if candidate.is_file()}
    if not existing:
        raise FileNotFoundError(f"{label} is missing: {value}")
    if len(existing) != 1:
        raise ValueError(f"{label} resolves ambiguously: {value}")
    return next(iter(existing))


def _manifest_roster_matches(
    value: object, expected: Mapping[str, Any], *, label: str
) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a finalized roster mapping")
    for field in ("sha256", "selected_models", "proposed_decision"):
        if value.get(field) != expected.get(field):
            raise ValueError(f"{label}.{field} differs from the registry roster")
    path = _repository_path(value.get("path"), f"{label}.path")
    expected_path = _repository_path(expected.get("path"), "registry roster path")
    if path.resolve() != expected_path.resolve():
        raise ValueError(f"{label}.path differs from the registry roster")


def _formal_authorization_models(
    suite: str, manifest_models: Sequence[str]
) -> list[str]:
    return ["proposed"] if suite in DERIVED_FORMAL_MODELS else list(manifest_models)


def _validate_frontier_anchor_tables(
    manifest: Mapping[str, Any],
    daily: pd.DataFrame,
    events: pd.DataFrame,
    *,
    run_directory: Path,
    label: str,
) -> dict[str, Any]:
    catalog_path = _resolve_run_artifact(
        manifest.get("frontier_anchor_catalog_path"),
        run_directory=run_directory,
        label=f"{label}.frontier_anchor_catalog_path",
    )
    if catalog_path != CANONICAL_FRONTIER_ANCHOR_PATH.resolve():
        raise ValueError(f"{label} does not use the canonical frontier catalog")
    observed_sha = file_sha256(catalog_path)
    if manifest.get("frontier_anchor_catalog_sha256") != observed_sha:
        raise ValueError(f"{label} frontier anchor catalog SHA-256 mismatch")
    catalog = load_frontier_anchor_catalog(
        catalog_path,
        expected_data_version="published_v1",
        expected_evaluation_split="development_test",
    )
    if manifest.get("frontier_anchor_count") != len(catalog):
        raise ValueError(f"{label} frontier anchor catalog count mismatch")
    grid_contract = manifest.get("formal_grid_contract")
    if (
        manifest.get("formal_grid_contract_complete") is not True
        or not isinstance(grid_contract, Mapping)
    ):
        raise ValueError(f"{label} lacks a completed formal grid contract")
    for field, expected in (
        ("suite", manifest.get("suite")),
        ("frontier_anchor_required", True),
        ("frontier_anchor_catalog_path", manifest.get("frontier_anchor_catalog_path")),
        ("frontier_anchor_catalog_sha256", observed_sha),
        ("frontier_anchor_count", len(catalog)),
    ):
        if grid_contract.get(field) != expected:
            raise ValueError(f"{label} formal grid contract has stale {field}")
    scenario_count = grid_contract.get("frontier_anchor_scenario_count")
    binding_hash = grid_contract.get("frontier_anchor_bindings_sha256")
    if (
        isinstance(scenario_count, bool)
        or not isinstance(scenario_count, int)
        or scenario_count < 1
        or not isinstance(binding_hash, str)
        or len(binding_hash) != 64
    ):
        raise ValueError(f"{label} formal grid contract lacks anchor inventory")

    catalog_by_id = catalog.set_index("anchor_id", drop=False)
    inventories: list[set[tuple[str, str, int]]] = []
    required_columns = (
        "scenario_id",
        "mask_type",
        "anchor_id",
        "anchor_target",
        "anchor_mask_seed",
        "center_date",
        "center_index",
        "anchor_data_version",
        "anchor_evaluation_split",
        "anchor_source_split",
        "anchor_max_supported_length",
        "anchor_start_month",
        "anchor_season",
        "anchor_year",
        "anchor_hydrologic_state",
        "station_ids",
    )
    for frame, table_label in ((daily, "daily"), (events, "events")):
        _require_columns(frame, required_columns, f"{label} {table_label}")
        anchored = frame.loc[
            frame["mask_type"].astype(str).isin(FRONTIER_ANCHORED_MASK_TYPES)
        ].copy()
        if anchored.empty or anchored.loc[:, required_columns].isna().any().any():
            raise ValueError(f"{label} {table_label} lacks frontier anchor bindings")
        inventory: set[tuple[str, str, int]] = set()
        for row in anchored.loc[:, required_columns].drop_duplicates().itertuples(
            index=False
        ):
            anchor_id = str(row.anchor_id)
            if anchor_id not in catalog_by_id.index:
                raise ValueError(f"{label} contains an unknown frontier anchor")
            catalog_row = catalog_by_id.loc[anchor_id]
            try:
                stations = json.loads(str(row.station_ids))
            except json.JSONDecodeError as error:
                raise ValueError(f"{label} has malformed station_ids") from error
            if not isinstance(stations, list) or not stations:
                raise ValueError(f"{label} has empty station_ids")
            observed = {
                "station_id": str(stations[0]),
                "target": str(row.anchor_target),
                "mask_seed": int(row.anchor_mask_seed),
                "center_date": str(row.center_date),
                "center_index": int(row.center_index),
                "data_version": str(row.anchor_data_version),
                "evaluation_split": str(row.anchor_evaluation_split),
                "source_split": str(row.anchor_source_split),
                "max_supported_length": int(row.anchor_max_supported_length),
                "start_month": int(row.anchor_start_month),
                "season": str(row.anchor_season),
                "year": int(row.anchor_year),
                "hydrologic_state": str(row.anchor_hydrologic_state),
            }
            expected = {
                "station_id": str(catalog_row["station_id"]),
                "target": str(catalog_row["target"]),
                "mask_seed": int(catalog_row["mask_seed"]),
                "center_date": str(catalog_row["center_date"]),
                "center_index": int(catalog_row["center_index"]),
                "data_version": str(catalog_row["data_version"]),
                "evaluation_split": str(catalog_row["evaluation_split"]),
                "source_split": str(catalog_row["source_split"]),
                "max_supported_length": int(catalog_row["max_supported_length"]),
                "start_month": int(catalog_row["start_month"]),
                "season": str(catalog_row["season"]),
                "year": int(catalog_row["year"]),
                "hydrologic_state": str(catalog_row["hydrologic_state"]),
            }
            if observed != expected:
                raise ValueError(f"{label} contains a stale frontier anchor binding")
            inventory.add((str(row.scenario_id), anchor_id, int(row.anchor_mask_seed)))
        inventories.append(inventory)
    if inventories[0] != inventories[1]:
        raise ValueError(f"{label} daily/event frontier anchor inventories differ")
    if len(inventories[0]) > scenario_count:
        raise ValueError(f"{label} table anchor inventory exceeds its grid contract")
    return {
        "path": str(catalog_path),
        "sha256": observed_sha,
        "count": len(catalog),
        "observed_evidence_scenario_count": len(inventories[0]),
    }


def _validate_full_event_contract(
    manifest: Mapping[str, Any],
    expected_run_units: set[str],
    *,
    run_directory: Path,
    label: str,
) -> dict[str, Any] | None:
    if manifest.get("suite") != "full":
        return None
    catalog_path = _resolve_run_artifact(
        manifest.get("event_catalog_path"),
        run_directory=run_directory,
        label=f"{label}.event_catalog_path",
    )
    catalog = load_event_episode_catalog(
        catalog_path,
        expected_data_version=str(manifest["data_version"]),
        expected_evaluation_split=str(manifest["evaluation_split"]),
    )
    digest = event_catalog_sha256(catalog)
    eligible = catalog.loc[catalog["analysis_eligible"].astype(bool)]
    if (
        manifest.get("event_catalog_sha256") != digest
        or manifest.get("event_catalog_episode_count") != len(catalog)
        or manifest.get("event_catalog_analysis_count") != len(eligible)
        or len(eligible) < 1
    ):
        raise ValueError(f"{label} event catalog identity/count mismatch")
    suffixes: list[str] = []
    if str(manifest["data_version"]) != "published_v1":
        suffixes.append(str(manifest["data_version"]).upper())
    if str(manifest["evaluation_split"]) != "test":
        suffixes.append(str(manifest["evaluation_split"]).upper())
    detail = "" if not suffixes else "-" + "-".join(suffixes)
    expected_m7b = {
        *(
            f"M7B-EVENT-{value}{detail}-R0000"
            for value in eligible["event_id"].astype(str)
        ),
        *(
            f"M7B-CONTROL-{value}{detail}-R0000"
            for value in eligible["control_id"].astype(str)
        ),
    }
    observed_scenarios = {
        _parse_run_unit_key(key, label)[0] for key in expected_run_units
    }
    observed_m7a = {
        scenario for scenario in observed_scenarios if scenario.startswith("M7A-")
    }
    observed_m7b = {
        scenario
        for scenario in observed_scenarios
        if scenario.startswith(("M7B-EVENT-", "M7B-CONTROL-"))
    }
    if len(observed_m7a) != 12 or any(
        not scenario.endswith("-R0000") for scenario in observed_m7a
    ):
        raise ValueError(f"{label} must contain exactly twelve seed-0 M7a scenarios")
    if len(expected_m7b) != 2 * len(eligible) or observed_m7b != expected_m7b:
        raise ValueError(
            f"{label} M7b inventory must be two seed-0 scenarios per eligible pair"
        )
    grid_contract = manifest.get("formal_grid_contract")
    if not isinstance(grid_contract, Mapping):
        raise TypeError(f"{label} lacks a formal full-grid contract")
    for field, expected in (
        ("event_uncertainty_required", True),
        ("event_catalog_path", manifest.get("event_catalog_path")),
        ("event_catalog_sha256", digest),
        ("event_catalog_episode_count", len(catalog)),
        ("event_catalog_analysis_count", len(eligible)),
        ("m7a_scenario_count", 12),
        ("m7b_scenario_count", len(expected_m7b)),
    ):
        if grid_contract.get(field) != expected:
            raise ValueError(f"{label} formal full-grid contract has stale {field}")
    return {
        "path": str(catalog_path),
        "sha256": digest,
        "episode_count": len(catalog),
        "analysis_count": len(eligible),
        "m7a_scenario_count": len(observed_m7a),
        "m7b_scenario_count": len(observed_m7b),
    }


def _validate_run_directory(
    directory: Path,
    *,
    expected_suite: str,
    expected_models: Sequence[str],
    allowed_table_models: set[str],
    expected_evidence: Mapping[str, Any],
    expected_roster: Mapping[str, Any],
    design_path: str | Path,
    study_manifest_path: str | Path,
    config_path: str | Path,
    data_version_manifest_path: str | Path,
) -> dict[str, Any]:
    manifest_path = directory / "run_manifest.json"
    daily_path = directory / "daily_predictions.parquet"
    event_path = directory / "event_metrics.parquet"
    manifest = _read_mapping(manifest_path, "runner manifest")
    _require_complete_manifest(manifest, str(manifest_path))
    _require_evidence_contract(manifest, expected_evidence, str(manifest_path))
    version_manifest = Path(data_version_manifest_path)
    expected_version_identity = validate_data_version_inputs(
        data_version_manifest_path=version_manifest,
        data_version=str(manifest.get("data_version")),
        wide_path=version_manifest.parent / "daily_wide.parquet",
        quality_path=version_manifest.parent / "daily_long.parquet",
        require_manifest=True,
        require_quality=True,
    )
    if manifest.get("data_version_input_identity") != expected_version_identity:
        raise ValueError(f"{manifest_path} data-version input identity is stale")
    if manifest.get("formal_evidence") is not True:
        raise ValueError(f"{manifest_path} requires formal_evidence=true")
    if manifest.get("evidence_role") != "formal_development_evaluation":
        raise ValueError(f"{manifest_path} is not formal development evidence")
    if manifest.get("suite") != expected_suite:
        raise ValueError(f"{manifest_path} suite does not match registry")
    models = _string_list(manifest.get("models"), f"{manifest_path}.models")
    if models != list(expected_models):
        raise ValueError(
            f"{manifest_path} model roster does not match finalized registry"
        )
    if manifest.get("expected_formal_models") != models:
        raise ValueError(f"{manifest_path} expected_formal_models is stale")
    _manifest_roster_matches(
        manifest.get("finalized_model_roster"),
        expected_roster,
        label=f"{manifest_path}.finalized_model_roster",
    )
    authorization = manifest.get("formal_execution_authorization")
    if not isinstance(authorization, Mapping):
        raise TypeError(f"{manifest_path} lacks formal execution authorization")
    validated_authorization = validate_formal_authorization(
        authorization,
        expected_suite=expected_suite,
        expected_models=_formal_authorization_models(expected_suite, models),
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=config_path,
    )
    _manifest_roster_matches(
        validated_authorization.get("finalized_model_roster"),
        expected_roster,
        label=f"{manifest_path}.authorization.finalized_model_roster",
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
    frontier_contract = _validate_frontier_anchor_tables(
        manifest,
        daily,
        events,
        run_directory=directory,
        label=str(manifest_path),
    )
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
    event_contract = _validate_full_event_contract(
        manifest,
        expected,
        run_directory=directory,
        label=str(manifest_path),
    )
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
            "formal_execution_authorization": validated_authorization,
            "frontier_anchor_catalog": frontier_contract,
            "event_catalog": event_contract,
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
    *,
    expected_roster: Mapping[str, Any],
    design_path: str | Path,
    study_manifest_path: str | Path,
    config_path: str | Path,
    data_version_manifest_path: str | Path,
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
                expected_roster=expected_roster,
                design_path=design_path,
                study_manifest_path=study_manifest_path,
                config_path=config_path,
                data_version_manifest_path=data_version_manifest_path,
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
                expected_roster=expected_roster,
                design_path=design_path,
                study_manifest_path=study_manifest_path,
                config_path=config_path,
                data_version_manifest_path=data_version_manifest_path,
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
    design_path: str | Path = PROJECT_ROOT / "configs/design_freeze_v3.yaml",
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
    if data_version_manifest_path is None:
        raise FileNotFoundError(
            f"formal aggregation requires a data-version manifest for {data_version}"
        )
    version_manifest_path = Path(data_version_manifest_path)
    if not version_manifest_path.is_file():
        raise FileNotFoundError(
            f"formal aggregation data-version manifest is missing: {version_manifest_path}"
        )
    evidence = build_design_contract(
        design_path=design_path,
        manifest_path=manifest_path,
        experiment_config_path=config_path,
        data_version=data_version,
        evaluation_split=canonical_split,
        data_version_manifest_path=version_manifest_path,
    )
    registry_contract = _validate_registry_contract(
        registry,
        formal_root=formal,
        expected_evidence=evidence,
        data_version=data_version,
        evaluation_split=canonical_split,
        data_version_manifest_path=version_manifest_path,
        design_path=design_path,
        study_manifest_path=manifest_path,
        config_path=config_path,
    )
    suites = [
        _validate_registry_suite(
            formal,
            entry,
            evidence,
            expected_roster=registry_contract["finalized_model_roster"],
            design_path=design_path,
            study_manifest_path=manifest_path,
            config_path=config_path,
            data_version_manifest_path=version_manifest_path,
        )
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
    expected_sources = {
        str(source["manifest_path"]): source
        for source in registry_contract["sources"]
    }
    actual_sources = {
        str(Path(run["source"]["manifest"]["path"]).resolve()): {
            "suite": suite["manifest_suite"],
            "models": run["source"]["models"],
            "run_directory": Path(run["directory"]).resolve(),
            "manifest_sha256": run["source"]["manifest"]["sha256"],
            "daily_predictions_path": Path(
                run["source"]["daily_predictions"]["path"]
            ).resolve(),
            "daily_predictions_sha256": run["source"]["daily_predictions"][
                "sha256"
            ],
            "event_metrics_path": Path(
                run["source"]["event_metrics"]["path"]
            ).resolve(),
            "event_metrics_sha256": run["source"]["event_metrics"]["sha256"],
        }
        for suite in suites
        for run in suite["runs"]
    }
    if set(actual_sources) != set(expected_sources):
        raise ValueError("validated suite manifests differ from registry sources")
    for path, actual in actual_sources.items():
        expected = expected_sources[path]
        for field in (
            "suite",
            "models",
            "manifest_sha256",
            "daily_predictions_path",
            "daily_predictions_sha256",
            "event_metrics_path",
            "event_metrics_sha256",
        ):
            if actual[field] != expected[field]:
                raise ValueError(f"registry source {path} has stale {field}")
        if actual["run_directory"] != expected["run_directory"]:
            raise ValueError(f"registry source {path} has a stale run directory")

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
    sources = [run["source"] for suite in suites for run in suite["runs"]]
    frontier_catalogs = {
        (
            source["frontier_anchor_catalog"]["path"],
            source["frontier_anchor_catalog"]["sha256"],
            source["frontier_anchor_catalog"]["count"],
        )
        for source in sources
    }
    if len(frontier_catalogs) != 1:
        raise ValueError("formal sources do not share one frozen frontier catalog")
    frontier_path, frontier_sha, frontier_count = next(iter(frontier_catalogs))
    _atomic_parquet(daily, predictions_path)
    _atomic_parquet(events, event_metrics_path)
    _atomic_csv(summary, summary_path)
    manifest = {
        "schema_version": "formal_aggregate_manifest_v2",
        "frozen": True,
        "complete": True,
        "formal_design_complete": True,
        "formal_training_seed_complete": True,
        "formal_mask_seed_complete": True,
        "training_profile": "formal",
        "formal_evidence": True,
        "evidence_role": "formal_development_evaluation",
        "run_unit_complete": True,
        "evidence_complete": True,
        "finite_predictions": True,
        "finite_event_metrics": True,
        "checkpoint_contract_complete": True,
        "retryable_run_keys": [],
        "retryable_run_unit_count": 0,
        "suite_registry": registry_identity,
        "suite_registry_sha256": registry["registry_sha256"],
        "bundle_kind": registry_contract["bundle_kind"],
        "bundle_role": registry_contract["bundle_role"],
        "required_suite_roles": registry_contract["required_suite_roles"],
        "suite_roles": registry_contract["suite_roles"],
        "finalized_model_roster": registry_contract["finalized_model_roster"],
        "frontier_anchor_catalog": {
            "path": frontier_path,
            "sha256": frontier_sha,
            "count": frontier_count,
        },
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
        "--design", type=Path, default=PROJECT_ROOT / "configs/design_freeze_v3.yaml"
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
