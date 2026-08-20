"""Build immutable registries from completed, explicitly named formal runs.

This module is deliberately fail closed.  It does not discover historical result
trees and it does not train, repair, or rewrite an experiment.  Its sole output
is the dynamic ``formal_suite_registry_v1`` consumed by
``scripts/13_aggregate_formal_results.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from stream_recoverability.experiments.contracts import (
    build_design_contract,
    canonical_code_identity,
    canonical_evaluation_split,
    file_sha256,
    validate_data_version_inputs,
)
from stream_recoverability.masks.anchors import (
    FRONTIER_MASK_SEEDS,
    load_frontier_anchor_catalog,
)
from stream_recoverability.masks.event_catalog import (
    event_catalog_sha256,
    load_event_episode_catalog,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LEGACY_FORMAL_ROOT = (REPOSITORY_ROOT / "results/formal").resolve()
REGISTRY_SCHEMA_VERSION = "formal_suite_registry_v1"
REGISTRY_BUILDER_IDENTITY_SCHEMA_VERSION = "formal_registry_builder_identity_v1"
ROSTER_SCHEMA_VERSION = "finalized_model_roster_v1"
DEFAULT_FRONTIER_ANCHOR_PATH = REPOSITORY_ROOT / "metadata/frontier_anchors.csv"
REGISTRY_BUILDER_SOURCE_PATHS = (
    REPOSITORY_ROOT / "scripts/21_build_formal_suite_registry.py",
    Path(__file__).resolve(),
)
F_ONLY_STRUCTURAL_BASELINES = frozenset({"rating_curve", "independent_flow"})
LEGACY_MODEL_NAMES = frozenset({"brits", "saits"})
FORMAL_TRAINABLE_MODELS = frozenset({"brits_ref", "saits_ref", "csdi", "proposed"})
FORMAL_TRAINING_SEEDS = (11, 22, 33, 44, 55)
DERIVED_SUITE_MODELS = {
    "science_compensation": frozenset({"information_compensation"}),
    "retrained_information_upper_bounds": frozenset(
        {"retrained_information_upper_bound"}
    ),
}
PROPOSED_ONLY_SUITES = frozenset(DERIVED_SUITE_MODELS)
FRONTIER_ANCHORED_MASK_TYPES = frozenset(
    {"async", "block", "station_outage", "matched_network"}
)
FRONTIER_BINDING_FIELDS = (
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
)
PRIMARY_SUITE_ROLES = (
    "core_full",
    "dense_frontier",
    "network_resilience",
    "event_uncertainty",
    "operational_dropout",
    "retrained_upper_bound",
)
PRIMARY_SUITE_ROLE_EQUIVALENTS = {
    "full": ("core_full", "event_uncertainty"),
    "science_dense": ("dense_frontier",),
    "science_resilience": ("network_resilience",),
    "science_compensation": ("operational_dropout",),
    "retrained_information_upper_bounds": ("retrained_upper_bound",),
}
SENSITIVITY_SUITE_ROLES = (
    "sensitivity_core_T",
    "sensitivity_dense_frontier",
    "sensitivity_operational_dropout",
)
SENSITIVITY_SUITE_ROLE_EQUIVALENTS = {
    "core": ("sensitivity_core_T",),
    "science_dense": ("sensitivity_dense_frontier",),
    "science_compensation": ("sensitivity_operational_dropout",),
}


def _load_finalized_model_roster(*args: Any, **kwargs: Any) -> Any:
    # Lazy import avoids a data.confirmatory -> experiments package -> runner ->
    # formal_authorization -> data.confirmatory cycle for standalone CLI use.
    from stream_recoverability.data.confirmatory import load_finalized_model_roster

    return load_finalized_model_roster(*args, **kwargs)


def _validate_formal_execution_authorization(*args: Any, **kwargs: Any) -> Any:
    # Keep the import lazy for the same data.confirmatory package cycle described
    # above.  The registry is a second trust boundary after runner construction.
    from stream_recoverability.experiments.formal_authorization import (
        validate_formal_authorization,
    )

    return validate_formal_authorization(*args, **kwargs)


CONTRACT_FIELDS = (
    "design_version",
    "design_hash",
    "data_version",
    "evaluation_split",
    "mask_schema_version",
    "model_schema_version",
    "statistics_schema_version",
    "input_digests",
    "code_identity",
)
TABLE_CONTRACT_FIELDS = CONTRACT_FIELDS[:7]
RUN_UNIT_FIELDS = (
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
    **{field: f"{field.removesuffix('_keys')}_count" for field in RUN_UNIT_FIELDS},
    "checkpoint_required_run_unit_keys": "checkpoint_required_run_count",
    "checkpoint_valid_run_unit_keys": "checkpoint_valid_run_count",
}
REQUIRED_COMPLETE_FLAGS = (
    "complete",
    "formal_design_complete",
    "formal_training_seed_complete",
    "formal_mask_seed_complete",
    "run_unit_complete",
    "evidence_complete",
    "finite_predictions",
    "finite_event_metrics",
    "checkpoint_contract_complete",
    "formal_grid_contract_complete",
)


@dataclass(frozen=True)
class _ValidatedRun:
    manifest_path: Path
    run_directory: Path
    suite: str
    models: tuple[str, ...]
    contract: dict[str, Any]
    expected_run_units: frozenset[str]
    manifest_sha256: str
    manifest_bytes: int
    daily_predictions_identity: dict[str, Any]
    event_metrics_identity: dict[str, Any]


@dataclass(frozen=True)
class _FrontierAnchorReference:
    path: Path
    sha256: str
    bytes: int
    count: int
    catalog: pd.DataFrame


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON mapping: {path}")
    return value


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _repository_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be a normalized non-empty path")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPOSITORY_ROOT / candidate


def _require_builder_sources_tracked_clean() -> None:
    relative_paths: list[str] = []
    for source in REGISTRY_BUILDER_SOURCE_PATHS:
        try:
            relative_paths.append(
                source.resolve().relative_to(REPOSITORY_ROOT).as_posix()
            )
        except ValueError as error:
            raise ValueError(
                f"registry builder source is outside the repository: {source}"
            ) from error
    tracked = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY_ROOT),
            "ls-files",
            "--error-unmatch",
            "--",
            *relative_paths,
        ),
        check=False,
        capture_output=True,
        timeout=15,
    )
    if tracked.returncode:
        raise ValueError("registry builder sources must be tracked by git")
    status = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *relative_paths,
        ),
        check=False,
        capture_output=True,
        timeout=15,
    )
    if status.returncode:
        raise RuntimeError("git status failed for registry builder sources")
    if status.stdout:
        raise ValueError("registry builder sources must be tracked and clean")


def build_registry_builder_identity() -> dict[str, Any]:
    """Return a separate identity for registry construction code.

    Registry automation is deliberately not folded into the model design hash:
    changing this validator must not invalidate already completed model runs.
    Its exact bytes are instead covered by the registry's own canonical hash.
    """

    _require_builder_sources_tracked_clean()
    sources: list[dict[str, Any]] = []
    for source in REGISTRY_BUILDER_SOURCE_PATHS:
        resolved = source.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"missing formal registry builder source: {resolved}")
        sources.append(
            {
                "path": _portable_path(resolved),
                "bytes": resolved.stat().st_size,
                "sha256": file_sha256(resolved),
            }
        )
    identity: dict[str, Any] = {
        "schema_version": REGISTRY_BUILDER_IDENTITY_SCHEMA_VERSION,
        "sources": sources,
        "identity_hash_scope": "canonical_json_excluding_identity_sha256",
    }
    identity["identity_sha256"] = _canonical_sha256(identity)
    return identity


def validate_registry_builder_identity(value: object) -> dict[str, Any]:
    """Validate a persisted builder identity against the current source bytes."""

    _require_builder_sources_tracked_clean()
    if not isinstance(value, Mapping):
        raise TypeError("registry_builder_identity must be a mapping")
    identity = json.loads(json.dumps(dict(value)))
    if set(identity) != {
        "schema_version",
        "sources",
        "identity_hash_scope",
        "identity_sha256",
    }:
        raise ValueError("registry builder identity fields are not frozen")
    if identity.get("schema_version") != REGISTRY_BUILDER_IDENTITY_SCHEMA_VERSION:
        raise ValueError("registry builder identity schema is not frozen")
    if (
        identity.get("identity_hash_scope")
        != "canonical_json_excluding_identity_sha256"
    ):
        raise ValueError("registry builder identity has an unknown hash scope")
    sources = identity.get("sources")
    if not isinstance(sources, list) or len(sources) != len(
        REGISTRY_BUILDER_SOURCE_PATHS
    ):
        raise ValueError("registry builder identity source inventory is incomplete")
    expected_paths = [_portable_path(path) for path in REGISTRY_BUILDER_SOURCE_PATHS]
    observed_paths: list[str] = []
    for index, source in enumerate(sources):
        label = f"registry_builder_identity.sources[{index}]"
        if not isinstance(source, Mapping) or set(source) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise ValueError(f"{label} is not an exact file identity")
        path_value = source.get("path")
        observed_paths.append(str(path_value))
        if path_value != expected_paths[index]:
            raise ValueError("registry builder source paths/order are not frozen")
        path = _repository_path(path_value, f"{label}.path")
        if not path.is_file():
            raise FileNotFoundError(f"missing registry builder source: {path}")
        if (
            source.get("bytes") != path.stat().st_size
            or source.get("sha256") != file_sha256(path)
        ):
            raise ValueError(f"{label} does not match current source bytes/SHA-256")
    if len(set(observed_paths)) != len(observed_paths):
        raise ValueError("registry builder source paths are duplicated")
    unsigned = {
        key: item for key, item in identity.items() if key != "identity_sha256"
    }
    if identity.get("identity_sha256") != _canonical_sha256(unsigned):
        raise ValueError("registry builder canonical identity SHA-256 does not match")
    return identity


def _path_within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _load_frontier_anchor_reference(
    path: str | Path, study_manifest_path: str | Path
) -> _FrontierAnchorReference:
    catalog_path = Path(path).resolve()
    if not catalog_path.is_file():
        raise FileNotFoundError(
            f"frozen frontier anchor catalog does not exist: {catalog_path}"
        )
    study_path = Path(study_manifest_path)
    study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
    if not isinstance(study, Mapping):
        raise TypeError(f"study manifest must be a YAML mapping: {study_path}")
    try:
        stations = tuple(
            str(value) for value in study["data_panels"]["core"]["stations"]
        )
        targets = (
            str(study["study"]["primary_target"]),
            *(str(value) for value in study["study"]["secondary_targets"]),
        )
    except (KeyError, TypeError) as error:
        raise ValueError(
            "study manifest lacks the frozen core station/target inventory"
        ) from error
    if (
        not stations
        or not targets
        or len(set(stations)) != len(stations)
        or len(set(targets)) != len(targets)
    ):
        raise ValueError("study manifest core station/target inventory is invalid")
    catalog = load_frontier_anchor_catalog(
        catalog_path,
        expected_data_version="published_v1",
        expected_evaluation_split="development_test",
        required_stations=stations,
        required_targets=targets,
    )
    expected_count = len(stations) * len(targets) * len(FRONTIER_MASK_SEEDS)
    if len(catalog) != expected_count:
        raise ValueError(
            "frozen frontier anchor catalog does not close the exact "
            f"station/target/seed inventory: {len(catalog)} != {expected_count}"
        )
    return _FrontierAnchorReference(
        path=catalog_path,
        sha256=file_sha256(catalog_path),
        bytes=catalog_path.stat().st_size,
        count=len(catalog),
        catalog=catalog,
    )


def _load_m7a_condition_targets(
    study_manifest_path: str | Path, experiment_config_path: str | Path
) -> dict[str, str]:
    study = yaml.safe_load(Path(study_manifest_path).read_text(encoding="utf-8"))
    config = yaml.safe_load(Path(experiment_config_path).read_text(encoding="utf-8"))
    if not isinstance(study, Mapping) or not isinstance(config, Mapping):
        raise TypeError("study and experiment configuration must be YAML mappings")
    try:
        stations = tuple(
            str(value) for value in study["data_panels"]["core"]["stations"]
        )
        raw_events = config["M7"]["events"]
    except (KeyError, TypeError) as error:
        raise ValueError("frozen M7a station/event inventory is unavailable") from error
    if (
        len(stations) != 3
        or len(set(stations)) != len(stations)
        or not isinstance(raw_events, Mapping)
        or len(raw_events) != 4
    ):
        raise ValueError(
            "frozen M7a inventory must contain three stations and four events"
        )
    events = {
        str(event): str(target) for event, target in raw_events.items()
    }
    if (
        any(not event or event.strip() != event for event in events)
        or any(target not in {"T", "F", "L"} for target in events.values())
        or len(events) != len(raw_events)
    ):
        raise ValueError("frozen M7a event/target definitions are invalid")
    condition_targets = {
        f"M7A-STRESS-{station}-{event.upper()}": target
        for station in stations
        for event, target in events.items()
    }
    if len(condition_targets) != 12:
        raise ValueError("frozen M7a inventory must contain exactly twelve conditions")
    return condition_targets


def _data_version_bundle_kind(
    design_path: str | Path, data_version: str
) -> str:
    design = yaml.safe_load(Path(design_path).read_text(encoding="utf-8"))
    if not isinstance(design, Mapping):
        raise TypeError("design freeze must be a YAML mapping")
    versions = design.get("data_versions")
    if not isinstance(versions, Mapping):
        raise TypeError("design freeze lacks data_versions")
    primary = versions.get("primary")
    sensitivities = versions.get("required_sensitivity")
    definitions = versions.get("definitions")
    if (
        not isinstance(primary, str)
        or not primary
        or not isinstance(sensitivities, list)
        or not sensitivities
        or not all(isinstance(value, str) and value for value in sensitivities)
        or len(set(sensitivities)) != len(sensitivities)
        or primary in sensitivities
        or not isinstance(definitions, Mapping)
        or not {primary, *sensitivities}.issubset(set(definitions))
    ):
        raise ValueError("design freeze data-version inventory is invalid")
    if data_version == primary:
        return "primary"
    if data_version in sensitivities:
        return "sensitivity"
    raise ValueError(
        f"data_version {data_version!r} is not a frozen primary/sensitivity version"
    )


def _normalized_strings(value: object, label: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not empty):
        raise ValueError(
            f"{label} must be a {'possibly empty' if empty else 'non-empty'} list"
        )
    if not all(
        isinstance(item, str) and item and item.strip() == item for item in value
    ):
        raise TypeError(f"{label} must contain normalized non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicates")
    return list(value)


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _parse_run_unit(value: str, label: str) -> tuple[str, str, str]:
    try:
        scenario, model_seed = value.split("|", maxsplit=1)
        model, seed = model_seed.rsplit(":", maxsplit=1)
    except ValueError as error:
        raise ValueError(f"{label} has malformed run-unit key {value!r}") from error
    if not scenario or not model or "|" in model_seed or ":" in model:
        raise ValueError(f"{label} has malformed run-unit key {value!r}")
    if seed != "none":
        try:
            numeric = int(seed)
        except ValueError as error:
            raise ValueError(f"{label} has malformed run-unit key {value!r}") from error
        if numeric < 0 or str(numeric) != seed:
            raise ValueError(f"{label} has malformed run-unit key {value!r}")
    return scenario, model, seed


def _seed_label(value: object, label: str) -> str:
    if pd.isna(value):
        return "none"
    numeric = float(value)
    if not np.isfinite(numeric) or not numeric.is_integer() or numeric < 0:
        raise ValueError(f"{label} contains an invalid training seed")
    return str(int(numeric))


def _integer_scalar(value: object, label: str) -> int:
    if pd.isna(value):
        raise ValueError(f"{label} must not be missing")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be an integer") from error
    if not np.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{label} must be a finite integer")
    return int(numeric)


def _text_scalar(value: object, label: str) -> str:
    if pd.isna(value):
        raise ValueError(f"{label} must not be missing")
    result = str(value)
    if not result or result.strip() != result:
        raise ValueError(f"{label} must be a normalized non-empty string")
    return result


def _table_run_units(frame: pd.DataFrame, label: str) -> set[str]:
    required = {"scenario_id", "model", "training_seed"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing run-unit columns: {missing}")
    result: set[str] = set()
    for scenario, model, seed in frame.loc[
        :, ["scenario_id", "model", "training_seed"]
    ].itertuples(index=False, name=None):
        scenario_name = str(scenario)
        model_name = str(model)
        key = f"{scenario_name}|{model_name}:{_seed_label(seed, label)}"
        _parse_run_unit(key, label)
        result.add(key)
    return result


def _run_unit_sets(manifest: Mapping[str, Any], label: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for field in RUN_UNIT_FIELDS:
        values = _normalized_strings(
            manifest.get(field), f"{label}.{field}", empty=True
        )
        count_field = RUN_UNIT_COUNT_FIELDS[field]
        count = _nonnegative_int(manifest.get(count_field), f"{label}.{count_field}")
        if count != len(values):
            raise ValueError(f"{label}.{field} disagrees with {count_field}")
        for value in values:
            _parse_run_unit(value, f"{label}.{field}")
        result[field] = set(values)
    return result


def _resolve_artifact_path(value: str, run_directory: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    local = run_directory / candidate
    repository = REPOSITORY_ROOT / candidate
    existing = [path for path in (local, repository) if path.is_file()]
    if len(existing) > 1 and existing[0].resolve() != existing[1].resolve():
        raise ValueError(f"ambiguous checkpoint artifact path: {value}")
    return existing[0] if existing else local


def _validate_file_identity(identity: object, label: str, run_directory: Path) -> None:
    if not isinstance(identity, Mapping):
        raise TypeError(f"{label} must be a file identity")
    path_value = identity.get("path")
    expected_size = identity.get("size")
    expected_sha256 = identity.get("sha256")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{label} lacks path")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError(f"{label} lacks SHA-256")
    path = _resolve_artifact_path(path_value, run_directory)
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    if expected_size != path.stat().st_size or expected_sha256 != file_sha256(path):
        raise ValueError(f"{label} does not match its size/hash")


def _validate_checkpoints(
    manifest: Mapping[str, Any], label: str, run_directory: Path
) -> None:
    summaries = manifest.get("training_checkpoints")
    if not isinstance(summaries, list):
        raise TypeError(f"{label}.training_checkpoints must be a list")
    required = _nonnegative_int(
        manifest.get("checkpoint_required_run_count"),
        f"{label}.checkpoint_required_run_count",
    )
    if required and not summaries:
        raise ValueError(f"{label} requires checkpoints but records none")
    for index, summary in enumerate(summaries):
        item = f"{label}.training_checkpoints[{index}]"
        if not isinstance(summary, Mapping):
            raise TypeError(f"{item} must be a mapping")
        if summary.get("checkpoint_contract_valid") is not True:
            raise ValueError(f"{item} does not have a valid checkpoint contract")
        _validate_file_identity(
            summary.get("checkpoint"), f"{item}.checkpoint", run_directory
        )
        sidecar = summary.get("checkpoint_sidecar")
        if sidecar is not None:
            _validate_file_identity(
                sidecar, f"{item}.checkpoint_sidecar", run_directory
            )


def _validate_table_contract(
    frame: pd.DataFrame, contract: Mapping[str, Any], label: str
) -> None:
    missing = sorted(set(TABLE_CONTRACT_FIELDS).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing evidence fields: {missing}")
    for field in TABLE_CONTRACT_FIELDS:
        values = set(frame[field].dropna().astype(str))
        if frame[field].isna().any() or values != {str(contract[field])}:
            raise ValueError(f"{label} mixes or mismatches {field}: {sorted(values)}")
    if (
        "evidence_role" not in frame
        or not frame["evidence_role"]
        .astype(str)
        .eq("formal_development_evaluation")
        .all()
    ):
        raise ValueError(f"{label} is not formal development evidence")
    if "formal_evidence" not in frame or not frame["formal_evidence"].eq(True).all():
        raise ValueError(f"{label} requires formal_evidence=true")


def _validate_unique_table(frame: pd.DataFrame, *, daily: bool, label: str) -> None:
    key = [
        "scenario_id",
        "model",
        "training_seed",
        "mask_seed",
        *(["date"] if daily else []),
        "station_id",
        "target",
    ]
    if (
        "information_combination" in frame
        and frame["information_combination"].notna().any()
    ):
        key.append("information_combination")
    missing = sorted(set(key).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing frozen-key columns: {missing}")
    if frame.duplicated(key, keep=False).any():
        raise ValueError(f"{label} contains duplicate frozen-key rows")


def _frontier_table_bindings(
    frame: pd.DataFrame,
    *,
    label: str,
    reference: _FrontierAnchorReference,
) -> dict[str, dict[str, Any]]:
    required = {
        "scenario_id",
        "mask_type",
        "mask_seed",
        "station_ids",
        *FRONTIER_BINDING_FIELDS,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing frontier-binding columns: {missing}")
    anchored = frame.loc[
        frame["mask_type"].astype(str).isin(FRONTIER_ANCHORED_MASK_TYPES)
    ]
    if anchored.empty:
        raise ValueError(f"{label} contains no frozen frontier-anchored scenarios")
    catalog_by_id = reference.catalog.set_index("anchor_id", drop=False)
    bindings: dict[str, dict[str, Any]] = {}
    for scenario_id, group in anchored.groupby("scenario_id", sort=False, dropna=False):
        scenario = _text_scalar(scenario_id, f"{label}.scenario_id")
        records: list[dict[str, Any]] = []
        for row in group.loc[
            :,
            ["mask_type", "mask_seed", "station_ids", *FRONTIER_BINDING_FIELDS],
        ].itertuples(index=False, name=None):
            values = dict(
                zip(
                    ("mask_type", "mask_seed", "station_ids", *FRONTIER_BINDING_FIELDS),
                    row,
                    strict=True,
                )
            )
            raw_stations = values["station_ids"]
            if not isinstance(raw_stations, str):
                raise TypeError(f"{label} scenario {scenario} station_ids must be JSON")
            try:
                stations = json.loads(raw_stations)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{label} scenario {scenario} station_ids is invalid JSON"
                ) from error
            if (
                not isinstance(stations, list)
                or not stations
                or not all(isinstance(item, str) and item for item in stations)
            ):
                raise ValueError(
                    f"{label} scenario {scenario} station_ids must be non-empty strings"
                )
            record = {
                "mask_type": _text_scalar(
                    values["mask_type"], f"{label} scenario {scenario}.mask_type"
                ),
                "mask_seed": _integer_scalar(
                    values["mask_seed"], f"{label} scenario {scenario}.mask_seed"
                ),
                "anchor_station_id": stations[0],
                "anchor_id": _text_scalar(
                    values["anchor_id"], f"{label} scenario {scenario}.anchor_id"
                ),
                "anchor_target": _text_scalar(
                    values["anchor_target"],
                    f"{label} scenario {scenario}.anchor_target",
                ),
                "anchor_mask_seed": _integer_scalar(
                    values["anchor_mask_seed"],
                    f"{label} scenario {scenario}.anchor_mask_seed",
                ),
                "center_date": pd.Timestamp(values["center_date"]).strftime(
                    "%Y-%m-%d"
                ),
                "center_index": _integer_scalar(
                    values["center_index"],
                    f"{label} scenario {scenario}.center_index",
                ),
                "anchor_data_version": _text_scalar(
                    values["anchor_data_version"],
                    f"{label} scenario {scenario}.anchor_data_version",
                ),
                "anchor_evaluation_split": _text_scalar(
                    values["anchor_evaluation_split"],
                    f"{label} scenario {scenario}.anchor_evaluation_split",
                ),
                "anchor_source_split": _text_scalar(
                    values["anchor_source_split"],
                    f"{label} scenario {scenario}.anchor_source_split",
                ),
                "anchor_max_supported_length": _integer_scalar(
                    values["anchor_max_supported_length"],
                    f"{label} scenario {scenario}.anchor_max_supported_length",
                ),
                "anchor_start_month": _integer_scalar(
                    values["anchor_start_month"],
                    f"{label} scenario {scenario}.anchor_start_month",
                ),
                "anchor_season": _text_scalar(
                    values["anchor_season"],
                    f"{label} scenario {scenario}.anchor_season",
                ),
                "anchor_year": _integer_scalar(
                    values["anchor_year"],
                    f"{label} scenario {scenario}.anchor_year",
                ),
                "anchor_hydrologic_state": _text_scalar(
                    values["anchor_hydrologic_state"],
                    f"{label} scenario {scenario}.anchor_hydrologic_state",
                ),
            }
            records.append(record)
        unique_records = {
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for record in records
        }
        if len(unique_records) != 1:
            raise ValueError(
                f"{label} scenario {scenario} mixes frontier anchor bindings"
            )
        binding = records[0]
        if binding["mask_type"] not in FRONTIER_ANCHORED_MASK_TYPES:
            raise AssertionError("frontier mask selection changed during validation")
        if binding["mask_seed"] != binding["anchor_mask_seed"] or not scenario.endswith(
            f"-R{binding['mask_seed']:04d}"
        ):
            raise ValueError(
                f"{label} scenario {scenario} mask seed differs from its fixed anchor"
            )
        anchor_id = binding["anchor_id"]
        if anchor_id not in catalog_by_id.index:
            raise ValueError(
                f"{label} scenario {scenario} references unknown frontier anchor {anchor_id}"
            )
        catalog_row = catalog_by_id.loc[anchor_id]
        if isinstance(catalog_row, pd.DataFrame):
            raise TypeError(f"frontier catalog duplicates anchor_id {anchor_id}")
        expected = {
            "anchor_station_id": str(catalog_row["station_id"]),
            "anchor_id": str(catalog_row["anchor_id"]),
            "anchor_target": str(catalog_row["target"]),
            "anchor_mask_seed": int(catalog_row["mask_seed"]),
            "center_date": str(catalog_row["center_date"]),
            "center_index": int(catalog_row["center_index"]),
            "anchor_data_version": str(catalog_row["data_version"]),
            "anchor_evaluation_split": str(catalog_row["evaluation_split"]),
            "anchor_source_split": str(catalog_row["source_split"]),
            "anchor_max_supported_length": int(catalog_row["max_supported_length"]),
            "anchor_start_month": int(catalog_row["start_month"]),
            "anchor_season": str(catalog_row["season"]),
            "anchor_year": int(catalog_row["year"]),
            "anchor_hydrologic_state": str(catalog_row["hydrologic_state"]),
        }
        observed = {field: binding[field] for field in expected}
        if observed != expected:
            raise ValueError(
                f"{label} scenario {scenario} frontier anchor binding mismatch: "
                f"observed={observed}, expected={expected}"
            )
        bindings[scenario] = binding
    return bindings


def _validate_frontier_anchor_source(
    *,
    run_directory: Path,
    manifest: Mapping[str, Any],
    daily: pd.DataFrame,
    events: pd.DataFrame,
    reference: _FrontierAnchorReference,
) -> None:
    label = str(run_directory / "run_manifest.json")
    raw_path = manifest.get("frontier_anchor_catalog_path")
    expected_sha256 = manifest.get("frontier_anchor_catalog_sha256")
    expected_count = manifest.get("frontier_anchor_count")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"{label} requires frontier_anchor_catalog_path")
    path = _resolve_artifact_path(raw_path, run_directory).resolve()
    if path != reference.path:
        raise ValueError(f"{label} does not use the canonical frontier anchor path")
    if expected_sha256 != reference.sha256 or file_sha256(path) != reference.sha256:
        raise ValueError(f"{label} frontier anchor catalog SHA-256 does not match")
    if _nonnegative_int(expected_count, f"{label}.frontier_anchor_count") != reference.count:
        raise ValueError(f"{label} frontier anchor catalog count does not match")
    daily_bindings = _frontier_table_bindings(
        daily,
        label=str(run_directory / "daily_predictions.parquet"),
        reference=reference,
    )
    event_bindings = _frontier_table_bindings(
        events,
        label=str(run_directory / "event_metrics.parquet"),
        reference=reference,
    )
    if daily_bindings != event_bindings:
        raise ValueError(
            f"{run_directory} daily/event frontier anchor inventories differ"
        )
    grid_contract = manifest.get("formal_grid_contract")
    if not isinstance(grid_contract, Mapping):
        raise TypeError(f"{label} lacks a formal_grid_contract")
    for field, expected in (
        ("suite", manifest.get("suite")),
        ("frontier_anchor_required", True),
        ("frontier_anchor_catalog_path", raw_path),
        ("frontier_anchor_catalog_sha256", reference.sha256),
        ("frontier_anchor_count", reference.count),
    ):
        if grid_contract.get(field) != expected:
            raise ValueError(f"{label} formal_grid_contract has stale {field}")
    grid_scenario_count = _nonnegative_int(
        grid_contract.get("frontier_anchor_scenario_count"),
        f"{label}.formal_grid_contract.frontier_anchor_scenario_count",
    )
    binding_sha256 = grid_contract.get("frontier_anchor_bindings_sha256")
    if (
        grid_scenario_count < len(daily_bindings)
        or grid_scenario_count < 1
        or not isinstance(binding_sha256, str)
        or len(binding_sha256) != 64
        or any(character not in "0123456789abcdef" for character in binding_sha256)
    ):
        raise ValueError(f"{label} formal grid frontier inventory is incomplete")


def _validate_tables(
    run_directory: Path,
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    key_sets: Mapping[str, set[str]],
    frontier_anchor_reference: _FrontierAnchorReference,
) -> tuple[set[str], set[str], dict[str, Any], dict[str, Any]]:
    daily_path = run_directory / "daily_predictions.parquet"
    event_path = run_directory / "event_metrics.parquet"
    if not daily_path.is_file() or not event_path.is_file():
        raise FileNotFoundError(f"{run_directory} lacks frozen daily/event tables")
    initial_stats = {
        path: (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        for path in (daily_path, event_path)
    }
    daily = pd.read_parquet(daily_path)
    events = pd.read_parquet(event_path)
    if daily.empty or events.empty:
        raise ValueError(f"{run_directory} has empty formal evidence tables")
    _validate_table_contract(daily, contract, str(daily_path))
    _validate_table_contract(events, contract, str(event_path))
    _validate_unique_table(daily, daily=True, label=str(daily_path))
    _validate_unique_table(events, daily=False, label=str(event_path))
    for frame, columns, label in (
        (daily, ("y_true", "y_pred"), str(daily_path)),
        (events, ("MAE", "RMSE"), str(event_path)),
    ):
        missing = sorted(set(columns).difference(frame.columns))
        if missing:
            raise ValueError(f"{label} lacks finite-evidence columns: {missing}")
        for column in columns:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
            if not np.isfinite(values).all():
                raise ValueError(f"{label} has non-finite {column}")
    daily_keys = _table_run_units(daily, str(daily_path))
    event_keys = _table_run_units(events, str(event_path))
    expected_evidence = key_sets["expected_evidence_run_unit_keys"]
    if daily_keys != expected_evidence or event_keys != expected_evidence:
        raise ValueError(f"{run_directory} tables do not close expected evidence units")
    if _nonnegative_int(
        manifest.get("completed_daily_rows"), "completed_daily_rows"
    ) != len(daily):
        raise ValueError("completed_daily_rows differs from daily table")
    if _nonnegative_int(
        manifest.get("completed_event_rows"), "completed_event_rows"
    ) != len(events):
        raise ValueError("completed_event_rows differs from event table")
    _validate_frontier_anchor_source(
        run_directory=run_directory,
        manifest=manifest,
        daily=daily,
        events=events,
        reference=frontier_anchor_reference,
    )
    for model in F_ONLY_STRUCTURAL_BASELINES.intersection(
        set(daily["model"].astype(str)) | set(events["model"].astype(str))
    ):
        for frame, table_path in ((daily, daily_path), (events, event_path)):
            targets = set(
                frame.loc[frame["model"].astype(str).eq(model), "target"].astype(str)
            )
            if targets and targets != {"F"}:
                raise ValueError(
                    f"{table_path} violates F-only semantics for {model}"
                )
    final_stats = {
        path: (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        for path in (daily_path, event_path)
    }
    if final_stats != initial_stats:
        raise RuntimeError(f"{run_directory} evidence tables changed during validation")
    daily_identity = {
        "path": _portable_path(daily_path),
        "bytes": daily_path.stat().st_size,
        "sha256": file_sha256(daily_path),
    }
    event_identity = {
        "path": _portable_path(event_path),
        "bytes": event_path.stat().st_size,
        "sha256": file_sha256(event_path),
    }
    hashed_stats = {
        path: (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
        for path in (daily_path, event_path)
    }
    if hashed_stats != initial_stats:
        raise RuntimeError(f"{run_directory} evidence tables changed while hashing")
    return (
        set(daily["model"].astype(str)),
        set(events["model"].astype(str)),
        daily_identity,
        event_identity,
    )


def _validate_manifest(
    manifest_path: Path,
    *,
    formal_root: Path,
    data_version: str,
    evaluation_split: str,
    design_hash: str,
    frontier_anchor_reference: _FrontierAnchorReference,
    data_version_input_identity: Mapping[str, Any],
) -> _ValidatedRun:
    path = manifest_path.resolve()
    root = formal_root.resolve()
    if path.name != "run_manifest.json":
        raise ValueError(f"formal input must be an explicit run_manifest.json: {path}")
    if root not in path.parents:
        raise ValueError(f"formal manifest is outside the declared formal root: {path}")
    if _path_within(path, LEGACY_FORMAL_ROOT):
        raise ValueError("legacy results/formal is forbidden as registry input")
    initial_manifest_sha256 = file_sha256(path)
    initial_manifest_bytes = path.stat().st_size
    manifest = _read_mapping(path, "formal run manifest")
    label = str(path)
    for flag in REQUIRED_COMPLETE_FLAGS:
        if manifest.get(flag) is not True:
            raise ValueError(f"{label} requires {flag}=true")
    for field, value in manifest.items():
        if (
            field.startswith("formal_")
            and field.endswith("_complete")
            and value is not True
        ):
            raise ValueError(f"{label} has incomplete formal gate {field}")
    if manifest.get("training_profile") != "formal":
        raise ValueError(f"{label} rejects smoke/non-formal training profiles")
    for limited_field in ("max_scenarios", "max_scenario", "scenario_limit"):
        if manifest.get(limited_field) not in (None, False):
            raise ValueError(f"{label} declares forbidden {limited_field}")
    if manifest.get("retryable_run_keys") not in ([], ()):  # legacy mirror gate
        raise ValueError(f"{label}.retryable_run_keys must be empty")
    missing_contract = sorted(set(CONTRACT_FIELDS).difference(manifest))
    if missing_contract:
        raise ValueError(
            f"{label} is stale; missing contract fields {missing_contract}"
        )
    if manifest.get("data_version") != data_version:
        raise ValueError(f"{label} data_version does not match the requested bundle")
    if (
        canonical_evaluation_split(str(manifest.get("evaluation_split")))
        != evaluation_split
    ):
        raise ValueError(
            f"{label} evaluation_split does not match the requested bundle"
        )
    if manifest.get("design_hash") != design_hash:
        raise ValueError(f"{label} design_hash does not match the requested bundle")
    if manifest.get("data_version_input_identity") != data_version_input_identity:
        raise ValueError(f"{label} data-version input identity is stale")
    if manifest.get("evidence_role") != "formal_development_evaluation":
        raise ValueError(f"{label} is validation/confirmatory or not formal evidence")
    if manifest.get("formal_evidence") is not True:
        raise ValueError(f"{label} requires formal_evidence=true")
    code_provenance = manifest.get("code_provenance")
    if not isinstance(code_provenance, Mapping):
        raise TypeError(f"{label}.code_provenance must be a mapping")
    if (
        code_provenance.get("relevant_source_clean") is not True
        or code_provenance.get("tracked_worktree_clean") is not True
        or code_provenance.get("status") != "clean"
    ):
        raise ValueError(f"{label} was not produced from clean relevant source")
    if canonical_code_identity(code_provenance) != manifest.get("code_identity"):
        raise ValueError(f"{label} code provenance/identity is inconsistent")
    suite = manifest.get("suite")
    if not isinstance(suite, str) or not suite or suite.strip() != suite:
        raise ValueError(f"{label} requires a normalized suite name")
    models = _normalized_strings(manifest.get("models"), f"{label}.models")
    if set(models).intersection(LEGACY_MODEL_NAMES):
        raise ValueError(f"{label} contains forbidden legacy brits/saits names")

    key_sets = _run_unit_sets(manifest, label)
    expected = key_sets["expected_run_unit_keys"]
    completed = key_sets["completed_run_unit_keys"]
    retryable = key_sets["retryable_run_unit_keys"]
    structural = key_sets["structural_skip_run_unit_keys"]
    evidence = key_sets["expected_evidence_run_unit_keys"]
    if not expected or completed != expected or retryable:
        raise ValueError(f"{label} has incomplete/retryable formal run units")
    if not structural.issubset(expected) or evidence != expected - structural:
        raise ValueError(f"{label} has an invalid structural-skip contract")
    for field in (
        "completed_evidence_run_unit_keys",
        "finite_prediction_run_unit_keys",
        "finite_event_metric_run_unit_keys",
    ):
        if key_sets[field] != evidence:
            raise ValueError(f"{label}.{field} does not close the evidence contract")
    required_checkpoints = key_sets["checkpoint_required_run_unit_keys"]
    if key_sets[
        "checkpoint_valid_run_unit_keys"
    ] != required_checkpoints or not required_checkpoints.issubset(expected):
        raise ValueError(f"{label} has an incomplete checkpoint run-unit contract")
    expected_models = {_parse_run_unit(key, label)[1] for key in expected}
    if expected_models != set(models):
        raise ValueError(f"{label} manifest models differ from exact run units")
    daily_models, event_models, daily_identity, event_identity = _validate_tables(
        path.parent,
        manifest,
        manifest,
        key_sets,
        frontier_anchor_reference,
    )
    evidence_models = {_parse_run_unit(key, label)[1] for key in evidence}
    if daily_models != evidence_models or event_models != evidence_models:
        raise ValueError(f"{label} actual table models differ from evidence run units")
    _validate_checkpoints(manifest, label, path.parent)
    contract = {field: manifest[field] for field in CONTRACT_FIELDS}
    final_manifest_sha256 = file_sha256(path)
    final_manifest_bytes = path.stat().st_size
    if (
        final_manifest_sha256 != initial_manifest_sha256
        or final_manifest_bytes != initial_manifest_bytes
    ):
        raise RuntimeError(f"{path} changed during registry validation")
    return _ValidatedRun(
        manifest_path=path,
        run_directory=path.parent,
        suite=suite,
        models=tuple(models),
        contract=json.loads(json.dumps(contract)),
        expected_run_units=frozenset(expected),
        manifest_sha256=final_manifest_sha256,
        manifest_bytes=final_manifest_bytes,
        daily_predictions_identity=daily_identity,
        event_metrics_identity=event_identity,
    )


def _validate_model_authorization(
    runs: Sequence[_ValidatedRun], selected: set[str], proposed_decision: str
) -> None:
    if selected.intersection(LEGACY_MODEL_NAMES):
        raise ValueError("finalized roster contains forbidden legacy brits/saits names")
    if selected.intersection(F_ONLY_STRUCTURAL_BASELINES):
        raise ValueError(
            "F-only structural baselines must not appear in the finalized T roster"
        )
    for run in runs:
        derived = DERIVED_SUITE_MODELS.get(run.suite, frozenset())
        if run.suite in PROPOSED_ONLY_SUITES and proposed_decision == "framework_only":
            raise ValueError(
                f"{run.suite} is not_applicable when proposed_decision=framework_only"
            )
        if proposed_decision == "framework_only" and (
            "proposed" in run.models or set(run.models).intersection(derived)
        ):
            raise ValueError("framework_only registry cannot contain proposed evidence")
        allowed = selected | F_ONLY_STRUCTURAL_BASELINES
        if proposed_decision == "include_proposed_formally":
            allowed |= set(derived)
        unauthorized = sorted(set(run.models).difference(allowed))
        if unauthorized:
            raise ValueError(
                f"suite {run.suite!r} contains models outside the finalized roster: "
                f"{unauthorized}"
            )
        derived_elsewhere = (
            set(run.models)
            .intersection(set().union(*DERIVED_SUITE_MODELS.values()))
            .difference(derived)
        )
        if derived_elsewhere:
            raise ValueError(
                f"suite {run.suite!r} uses derived models with the wrong estimand: "
                f"{sorted(derived_elsewhere)}"
            )


def _validate_run_authorizations(
    runs: Sequence[_ValidatedRun],
    *,
    roster: Any,
    roster_path: Path,
    design_path: str | Path,
    study_manifest_path: str | Path,
    experiment_config_path: str | Path,
) -> None:
    expected_roster = {
        "sha256": roster.manifest_sha256,
        "selected_models": list(roster.selected_models),
        "proposed_decision": roster.proposed_decision,
    }
    for run in runs:
        manifest = _read_mapping(run.manifest_path, "formal run manifest")
        if manifest.get("expected_formal_models") != list(run.models):
            raise ValueError(
                f"{run.manifest_path} expected_formal_models differs from models"
            )
        raw_authorization = manifest.get("formal_execution_authorization")
        if not isinstance(raw_authorization, Mapping):
            raise TypeError(
                f"{run.manifest_path} lacks formal_execution_authorization"
            )
        execution_models: Sequence[str] = (
            ("proposed",) if run.suite in DERIVED_SUITE_MODELS else run.models
        )
        authorization = _validate_formal_execution_authorization(
            raw_authorization,
            expected_suite=run.suite,
            expected_models=execution_models,
            design_path=design_path,
            study_manifest_path=study_manifest_path,
            experiment_config_path=experiment_config_path,
        )
        raw_authorized_roster = authorization.get("finalized_model_roster")
        if not isinstance(raw_authorized_roster, Mapping):
            raise TypeError(
                f"{run.manifest_path} authorization lacks finalized_model_roster"
            )
        mismatches = {
            field: (raw_authorized_roster.get(field), expected)
            for field, expected in expected_roster.items()
            if raw_authorized_roster.get(field) != expected
        }
        raw_authorized_path = raw_authorized_roster.get("path")
        if (
            not isinstance(raw_authorized_path, str)
            or not raw_authorized_path
            or _repository_path(
                raw_authorized_path,
                f"{run.manifest_path}.authorization.finalized_model_roster.path",
            ).resolve()
            != roster_path.resolve()
        ):
            mismatches["path"] = (raw_authorized_path, str(roster_path))
        if mismatches:
            raise ValueError(
                f"{run.manifest_path} authorization is bound to another finalized "
                f"roster: {mismatches}"
            )
        manifest_roster = manifest.get("finalized_model_roster")
        if not isinstance(manifest_roster, Mapping):
            raise TypeError(f"{run.manifest_path} lacks finalized_model_roster")
        top_level_mismatches = {
            field: (manifest_roster.get(field), expected)
            for field, expected in expected_roster.items()
            if manifest_roster.get(field) != expected
        }
        top_level_path = manifest_roster.get("path")
        if (
            not isinstance(top_level_path, str)
            or not top_level_path
            or _repository_path(
                top_level_path,
                f"{run.manifest_path}.finalized_model_roster.path",
            ).resolve()
            != roster_path.resolve()
        ):
            top_level_mismatches["path"] = (top_level_path, str(roster_path))
        if top_level_mismatches:
            raise ValueError(
                f"{run.manifest_path} finalized roster mirror is stale: "
                f"{top_level_mismatches}"
            )


def _expected_models_for_role(
    role: str, selected_models: Sequence[str]
) -> tuple[str, ...]:
    selected = tuple(selected_models)
    if role in {"core_full", "dense_frontier", "event_uncertainty"}:
        return (*selected, *sorted(F_ONLY_STRUCTURAL_BASELINES))
    if role == "network_resilience":
        return selected
    if role == "operational_dropout":
        return ("information_compensation",)
    if role == "retrained_upper_bound":
        return ("retrained_information_upper_bound",)
    if role in {"sensitivity_core_T", "sensitivity_dense_frontier"}:
        return selected
    if role == "sensitivity_operational_dropout":
        return ("information_compensation",)
    raise ValueError(f"unknown formal suite role {role!r}")


def _validate_event_uncertainty_source(
    run: _ValidatedRun, m7a_condition_targets: Mapping[str, str]
) -> None:
    manifest = _read_mapping(run.manifest_path, "full-suite run manifest")
    raw_path = manifest.get("event_catalog_path")
    expected_hash = manifest.get("event_catalog_sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("full event_uncertainty role requires event_catalog_path")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("full event_uncertainty role requires event_catalog_sha256")
    catalog_path = _resolve_artifact_path(raw_path, run.run_directory)
    catalog = load_event_episode_catalog(
        catalog_path,
        expected_data_version=str(run.contract["data_version"]),
        expected_evaluation_split=str(run.contract["evaluation_split"]),
    )
    observed_hash = event_catalog_sha256(catalog)
    if expected_hash != observed_hash:
        raise ValueError("full event catalog logical SHA-256 does not match")
    episode_count = _nonnegative_int(
        manifest.get("event_catalog_episode_count"),
        "event_catalog_episode_count",
    )
    analysis_count = _nonnegative_int(
        manifest.get("event_catalog_analysis_count"),
        "event_catalog_analysis_count",
    )
    eligible = catalog.loc[catalog["analysis_eligible"].astype(bool)]
    if episode_count != len(catalog) or analysis_count != len(eligible):
        raise ValueError("full event catalog counts differ from the frozen catalog")
    if analysis_count < 1:
        raise ValueError("event_uncertainty role requires eligible event/control pairs")
    scenario_details = [
        value.upper()
        for value, baseline in (
            (str(run.contract["data_version"]), "published_v1"),
            (str(run.contract["evaluation_split"]), "test"),
        )
        if value != baseline
    ]
    scenario_suffix = "" if not scenario_details else "-" + "-".join(scenario_details)
    expected_m7a_targets = {
        f"{condition_id}{scenario_suffix}-R0000": target
        for condition_id, target in m7a_condition_targets.items()
    }
    expected_m7a_scenarios = set(expected_m7a_targets)
    expected_m7b_scenarios = {
        *(
            f"M7B-EVENT-{event_id}{scenario_suffix}-R0000"
            for event_id in eligible["event_id"].astype(str)
        ),
        *(
            f"M7B-CONTROL-{control_id}{scenario_suffix}-R0000"
            for control_id in eligible["control_id"].astype(str)
        ),
    }
    expected_scenarios = expected_m7a_scenarios | expected_m7b_scenarios
    all_run_scenarios = {
        _parse_run_unit(key, str(run.manifest_path))[0]
        for key in run.expected_run_units
    }
    observed_scenarios = {
        scenario
        for scenario in all_run_scenarios
        if scenario.startswith(("M7A-", "M7B-"))
    }
    if len(expected_m7b_scenarios) != 2 * analysis_count:
        raise ValueError("event catalog event/control identifiers are not one-to-one")
    if observed_scenarios != expected_scenarios:
        raise ValueError(
            "full event inventory must equal twelve M7a stresses plus two M7b "
            "seed-0 scenarios per eligible pair"
        )
    for table_name in ("daily_predictions.parquet", "event_metrics.parquet"):
        table = pd.read_parquet(
            run.run_directory / table_name,
            columns=["scenario_id", "experiment", "target"],
        )
        if table[["scenario_id", "experiment", "target"]].isna().any().any():
            raise ValueError(f"full {table_name} has missing event identity fields")
        scenario_values = table["scenario_id"].astype(str)
        experiment_values = table["experiment"].astype(str)
        m7a_rows = scenario_values.isin(expected_m7a_scenarios)
        m7b_rows = scenario_values.isin(expected_m7b_scenarios)
        if (
            (m7a_rows & ~experiment_values.eq("M7a")).any()
            or (m7b_rows & ~experiment_values.eq("M7b")).any()
        ):
            raise ValueError(
                f"full {table_name} mixes event experiment labels within scenarios"
            )
        observed_m7a_targets = table.loc[m7a_rows, ["scenario_id", "target"]]
        if any(
            str(target) != expected_m7a_targets[str(scenario)]
            for scenario, target in observed_m7a_targets.itertuples(
                index=False, name=None
            )
        ):
            raise ValueError(
                f"full {table_name} M7a targets differ from the frozen event design"
            )
        table_m7a = set(
            table.loc[
                experiment_values.eq("M7a"), "scenario_id"
            ].astype(str)
        )
        table_m7b = set(
            table.loc[
                experiment_values.eq("M7b"), "scenario_id"
            ].astype(str)
        )
        prefixed = set(
            table.loc[
                table["scenario_id"]
                .astype(str)
                .str.startswith(("M7A-", "M7B-")),
                "scenario_id",
            ].astype(str)
        )
        if (
            table_m7a != expected_m7a_scenarios
            or table_m7b != expected_m7b_scenarios
            or prefixed != expected_scenarios
        ):
            raise ValueError(
                f"full {table_name} event rows do not equal the exact frozen inventory"
            )
    expected_run_units = {
        f"{scenario}|{model}:{seed}"
        for scenario in expected_scenarios
        for model in run.models
        for seed in (
            FORMAL_TRAINING_SEEDS if model in FORMAL_TRAINABLE_MODELS else ("none",)
        )
    }
    observed_run_units = {
        key
        for key in run.expected_run_units
        if _parse_run_unit(key, str(run.manifest_path))[0] in expected_scenarios
    }
    if observed_run_units != expected_run_units:
        raise ValueError(
            "full M7a/M7b run units do not close the formal model/training-seed "
            "inventory"
        )
    grid_contract = manifest.get("formal_grid_contract")
    if not isinstance(grid_contract, Mapping):
        raise TypeError("full event role lacks formal_grid_contract")
    for field, expected in (
        ("event_uncertainty_required", True),
        ("event_catalog_path", raw_path),
        ("event_catalog_sha256", observed_hash),
        ("event_catalog_episode_count", len(catalog)),
        ("event_catalog_analysis_count", len(eligible)),
        ("m7a_scenario_count", len(expected_m7a_scenarios)),
        ("m7b_scenario_count", len(expected_m7b_scenarios)),
    ):
        if grid_contract.get(field) != expected:
            raise ValueError(f"full formal_grid_contract has stale {field}")


def _validate_suite_roles(
    runs: Sequence[_ValidatedRun],
    *,
    bundle_kind: str,
    selected_models: Sequence[str],
    proposed_decision: str,
    m7a_condition_targets: Mapping[str, str],
) -> tuple[str, list[str], list[dict[str, Any]]]:
    if bundle_kind == "primary":
        bundle_role = "primary"
        required_roles = list(PRIMARY_SUITE_ROLES)
        role_sources: dict[str, list[_ValidatedRun]] = {
            role: [] for role in required_roles
        }
        for run in runs:
            roles = PRIMARY_SUITE_ROLE_EQUIVALENTS.get(run.suite)
            if roles is None:
                raise ValueError(
                    f"primary registry has no frozen role for suite {run.suite!r}"
                )
            for role in roles:
                role_sources[role].append(run)
        role_contracts: list[dict[str, Any]] = []
        for role in required_roles:
            sources = role_sources[role]
            expected_models = _expected_models_for_role(role, selected_models)
            if (
                role in {"operational_dropout", "retrained_upper_bound"}
                and proposed_decision == "framework_only"
            ):
                if sources:
                    raise ValueError(
                        f"role {role} must be not_applicable in framework_only mode"
                    )
                role_contracts.append(
                    {
                        "role": role,
                        "status": "not_applicable",
                        "reason": "proposed_decision=framework_only",
                        "manifest_suites": [],
                        "source_manifest_sha256": [],
                        "expected_models": [],
                    }
                )
                continue
            if not sources:
                raise ValueError(f"primary registry is missing required role {role}")
            if role == "event_uncertainty":
                for source in sources:
                    _validate_event_uncertainty_source(
                        source, m7a_condition_targets
                    )
            observed_models = {model for source in sources for model in source.models}
            if observed_models != set(expected_models):
                raise ValueError(
                    f"role {role} model roster differs from finalized expectations: "
                    f"observed={sorted(observed_models)}, "
                    f"expected={sorted(expected_models)}"
                )
            role_contracts.append(
                {
                    "role": role,
                    "status": "complete",
                    "reason": None,
                    "manifest_suites": sorted({source.suite for source in sources}),
                    "source_manifest_sha256": sorted(
                        source.manifest_sha256 for source in sources
                    ),
                    "expected_models": list(expected_models),
                }
            )
        return bundle_role, required_roles, role_contracts

    if bundle_kind != "sensitivity":
        raise ValueError(f"unknown formal bundle kind {bundle_kind!r}")
    bundle_role = "sensitivity_compact"
    required_roles = list(SENSITIVITY_SUITE_ROLES)
    role_sources: dict[str, list[_ValidatedRun]] = {role: [] for role in required_roles}
    for run in runs:
        roles = SENSITIVITY_SUITE_ROLE_EQUIVALENTS.get(run.suite)
        if roles is None:
            raise ValueError(
                "sensitivity registry accepts only independently frozen compact "
                f"roles; unsupported suite {run.suite!r}"
            )
        for role in roles:
            role_sources[role].append(run)
    role_contracts: list[dict[str, Any]] = []
    for role in required_roles:
        sources = role_sources[role]
        expected_models = _expected_models_for_role(role, selected_models)
        if (
            role == "sensitivity_operational_dropout"
            and proposed_decision == "framework_only"
        ):
            if sources:
                raise ValueError(
                    "sensitivity_operational_dropout must be not_applicable in "
                    "framework_only mode"
                )
            role_contracts.append(
                {
                    "role": role,
                    "status": "not_applicable",
                    "reason": "proposed_decision=framework_only",
                    "manifest_suites": [],
                    "source_manifest_sha256": [],
                    "expected_models": [],
                }
            )
            continue
        if not sources:
            raise ValueError(f"sensitivity registry is missing required role {role}")
        observed_models = {model for source in sources for model in source.models}
        if observed_models != set(expected_models):
            raise ValueError(
                f"role {role} model roster differs from finalized expectations: "
                f"observed={sorted(observed_models)}, "
                f"expected={sorted(expected_models)}"
            )
        role_contracts.append(
            {
                "role": role,
                "status": "complete",
                "reason": None,
                "manifest_suites": sorted({source.suite for source in sources}),
                "source_manifest_sha256": sorted(
                    source.manifest_sha256 for source in sources
                ),
                "expected_models": list(expected_models),
            }
        )
    return bundle_role, required_roles, role_contracts


def _suite_entries(
    runs: Sequence[_ValidatedRun], formal_root: Path
) -> list[dict[str, Any]]:
    grouped: dict[str, list[_ValidatedRun]] = {}
    for run in runs:
        grouped.setdefault(run.suite, []).append(run)
    entries: list[dict[str, Any]] = []
    for suite in sorted(grouped):
        members = sorted(grouped[suite], key=lambda item: str(item.run_directory))
        if len(members) == 1:
            member = members[0]
            relative = member.run_directory.relative_to(
                formal_root.resolve()
            ).as_posix()
            entries.append(
                {
                    "name": suite,
                    "path": relative,
                    "layout": "direct",
                    "manifest_suite": suite,
                    "finalized": True,
                    "finalized_models": list(member.models),
                    "allowed_derived_models": [],
                }
            )
            continue
        parents = {member.run_directory.parent for member in members}
        if len(parents) != 1 or any(len(member.models) != 1 for member in members):
            raise ValueError(
                f"duplicate suite {suite!r} must be one-model sibling directories"
            )
        parent = next(iter(parents))
        declared = {member.run_directory.name for member in members}
        models = {member.models[0] for member in members}
        if declared != models:
            raise ValueError(f"suite {suite!r} model child names differ from models")
        observed = {path.name for path in parent.iterdir() if path.is_dir()}
        if observed != declared:
            raise ValueError(
                f"suite {suite!r} has unlisted model child directories: "
                f"observed={sorted(observed)}, declared={sorted(declared)}"
            )
        entries.append(
            {
                "name": suite,
                "path": parent.relative_to(formal_root.resolve()).as_posix(),
                "layout": "model_children",
                "manifest_suite": suite,
                "finalized": True,
                "finalized_models": sorted(models),
                "allowed_derived_models": [],
            }
        )
    return entries


def _revalidate_run_artifact_identities(runs: Sequence[_ValidatedRun]) -> None:
    for run in runs:
        for label, path, expected_bytes, expected_sha256 in (
            (
                "manifest",
                run.manifest_path,
                run.manifest_bytes,
                run.manifest_sha256,
            ),
            (
                "daily_predictions",
                run.run_directory / "daily_predictions.parquet",
                run.daily_predictions_identity["bytes"],
                run.daily_predictions_identity["sha256"],
            ),
            (
                "event_metrics",
                run.run_directory / "event_metrics.parquet",
                run.event_metrics_identity["bytes"],
                run.event_metrics_identity["sha256"],
            ),
        ):
            if (
                not path.is_file()
                or path.stat().st_size != expected_bytes
                or file_sha256(path) != expected_sha256
            ):
                raise RuntimeError(
                    f"formal source {label} changed during registry construction: {path}"
                )


def _immutable_atomic_json(value: Mapping[str, Any], path: Path) -> None:
    output = path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"formal suite registry is immutable: {output}")
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix=f".{output.name}.", delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # A hard link is an atomic create that fails rather than replacing an
        # output written by a concurrent registry builder.
        os.link(temporary_name, output)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def build_formal_suite_registry(
    *,
    manifest_paths: Sequence[str | Path],
    finalized_model_roster_path: str | Path,
    formal_root: str | Path,
    output_path: str | Path,
    data_version: str,
    evaluation_split: str,
    design_hash: str,
    design_path: str | Path = REPOSITORY_ROOT / "configs/design_freeze_v3.yaml",
    study_manifest_path: str | Path = REPOSITORY_ROOT / "study_manifest.yaml",
    experiment_config_path: str | Path = REPOSITORY_ROOT / "configs/experiments.yaml",
    data_version_manifest_path: str | Path | None = None,
    selection_data_version_manifest_path: str | Path | None = None,
    frontier_anchor_catalog_path: str | Path = DEFAULT_FRONTIER_ANCHOR_PATH,
) -> dict[str, Any]:
    """Validate explicit completed suites and atomically create one registry."""

    if not manifest_paths:
        raise ValueError("at least one explicit --manifest is required")
    canonical_split = canonical_evaluation_split(evaluation_split)
    if canonical_split != "development_test":
        raise ValueError("formal registries reject validation/confirmatory splits")
    if not isinstance(data_version, str) or not data_version.strip():
        raise ValueError("data_version must be a non-empty string")
    bundle_kind = _data_version_bundle_kind(design_path, data_version)
    if (
        not isinstance(design_hash, str)
        or len(design_hash) != 64
        or any(character not in "0123456789abcdef" for character in design_hash)
    ):
        raise ValueError("design_hash must be a lowercase SHA-256")
    version_manifest = (
        Path(data_version_manifest_path)
        if data_version_manifest_path is not None
        else REPOSITORY_ROOT / "data_versions" / data_version / "version_manifest.json"
    )
    if not version_manifest.is_file():
        raise FileNotFoundError(
            f"target data-version manifest does not exist: {version_manifest}"
        )
    expected_contract = build_design_contract(
        design_path=design_path,
        manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        data_version=data_version,
        evaluation_split=canonical_split,
        data_version_manifest_path=version_manifest,
    )
    data_version_input_identity = validate_data_version_inputs(
        data_version_manifest_path=version_manifest,
        data_version=data_version,
        wide_path=version_manifest.parent / "daily_wide.parquet",
        quality_path=version_manifest.parent / "daily_long.parquet",
        require_manifest=True,
        require_quality=True,
    )
    if data_version_input_identity is None:
        raise AssertionError("formal data-version input identity is unavailable")
    if design_hash != expected_contract["design_hash"]:
        raise ValueError(
            "requested design_hash does not match the current frozen data/config/code "
            "contract"
        )
    frontier_anchor_reference = _load_frontier_anchor_reference(
        frontier_anchor_catalog_path, study_manifest_path
    )
    m7a_condition_targets = _load_m7a_condition_targets(
        study_manifest_path, experiment_config_path
    )
    root = Path(formal_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"formal root does not exist: {root}")
    if _path_within(root, LEGACY_FORMAL_ROOT):
        raise ValueError("legacy results/formal is forbidden as registry input")

    roster_path = Path(finalized_model_roster_path)
    roster_document = _read_mapping(roster_path, "finalized model roster")
    if roster_document.get("schema_version") != ROSTER_SCHEMA_VERSION:
        raise ValueError("model roster must use finalized_model_roster_v1")
    roster = _load_finalized_model_roster(
        roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    resolved_manifests = [Path(path).resolve() for path in manifest_paths]
    if len(set(resolved_manifests)) != len(resolved_manifests):
        raise ValueError("the same run manifest was listed more than once")
    if len({path.parent for path in resolved_manifests}) != len(resolved_manifests):
        raise ValueError("formal run directories must be unique")
    runs = [
        _validate_manifest(
            path,
            formal_root=root,
            data_version=data_version,
            evaluation_split=canonical_split,
            design_hash=design_hash,
            frontier_anchor_reference=frontier_anchor_reference,
            data_version_input_identity=data_version_input_identity,
        )
        for path in resolved_manifests
    ]
    first_contract = runs[0].contract
    expected_canonical_contract = {
        field: expected_contract[field] for field in CONTRACT_FIELDS
    }
    if first_contract != expected_canonical_contract:
        raise ValueError(
            "formal manifests do not match the current frozen data/config/code contract"
        )
    for run in runs[1:]:
        if run.contract != first_contract:
            raise ValueError(
                "formal manifests mix evidence contracts or code identities"
            )
    expected_unit_count = sum(len(run.expected_run_units) for run in runs)
    unique_expected_units = set().union(*(run.expected_run_units for run in runs))
    if len(unique_expected_units) != expected_unit_count:
        raise ValueError("formal suite manifests contain duplicate run-unit keys")
    _validate_model_authorization(
        runs, set(roster.selected_models), roster.proposed_decision
    )
    _validate_run_authorizations(
        runs,
        roster=roster,
        roster_path=roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
    )
    suites = _suite_entries(runs, root)
    bundle_role, required_roles, suite_roles = _validate_suite_roles(
        runs,
        bundle_kind=bundle_kind,
        selected_models=roster.selected_models,
        proposed_decision=roster.proposed_decision,
        m7a_condition_targets=m7a_condition_targets,
    )
    _revalidate_run_artifact_identities(runs)
    sources = [
        {
            "suite": run.suite,
            "run_directory": _portable_path(run.run_directory),
            "manifest": {
                "path": _portable_path(run.manifest_path),
                "bytes": run.manifest_bytes,
                "sha256": run.manifest_sha256,
            },
            "daily_predictions": run.daily_predictions_identity,
            "event_metrics": run.event_metrics_identity,
            "models": list(run.models),
        }
        for run in sorted(runs, key=lambda item: (item.suite, str(item.run_directory)))
    ]
    not_applicable_suite_names = (
        PROPOSED_ONLY_SUITES
        if bundle_kind == "primary"
        else frozenset({"science_compensation"})
    )
    not_applicable = (
        [
            {
                "manifest_suite": suite,
                "status": "not_applicable",
                "reason": "proposed_decision=framework_only",
            }
            for suite in sorted(not_applicable_suite_names)
        ]
        if roster.proposed_decision == "framework_only"
        else []
    )
    registry_builder_identity = validate_registry_builder_identity(
        build_registry_builder_identity()
    )
    registry: dict[str, Any] = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "finalized": True,
        "bundle_kind": bundle_kind,
        "bundle_role": bundle_role,
        "data_version": data_version,
        "evaluation_split": canonical_split,
        "design_hash": design_hash,
        "code_identity": first_contract["code_identity"],
        "registry_builder_identity": registry_builder_identity,
        "data_version_manifest": {
            "path": _portable_path(version_manifest),
            "bytes": version_manifest.stat().st_size,
            "sha256": file_sha256(version_manifest),
        },
        "data_version_input_identity": data_version_input_identity,
        "frontier_anchor_catalog": {
            "path": _portable_path(frontier_anchor_reference.path),
            "bytes": frontier_anchor_reference.bytes,
            "sha256": frontier_anchor_reference.sha256,
            "count": frontier_anchor_reference.count,
            "data_version": "published_v1",
            "evaluation_split": "development_test",
        },
        "formal_root": _portable_path(root),
        "finalized_model_roster": {
            "path": _portable_path(roster_path),
            "sha256": roster.manifest_sha256,
            "selected_models": list(roster.selected_models),
            "proposed_decision": roster.proposed_decision,
        },
        "not_applicable_suites": not_applicable,
        "required_suite_roles": required_roles,
        "suite_roles": suite_roles,
        "sources": sources,
        "suites": suites,
        "registry_hash_scope": "canonical_json_excluding_registry_sha256",
    }
    registry["registry_sha256"] = _canonical_sha256(registry)
    _immutable_atomic_json(registry, Path(output_path))
    return registry


__all__ = [
    "DEFAULT_FRONTIER_ANCHOR_PATH",
    "F_ONLY_STRUCTURAL_BASELINES",
    "REGISTRY_BUILDER_IDENTITY_SCHEMA_VERSION",
    "REGISTRY_SCHEMA_VERSION",
    "build_formal_suite_registry",
    "build_registry_builder_identity",
    "validate_registry_builder_identity",
]
