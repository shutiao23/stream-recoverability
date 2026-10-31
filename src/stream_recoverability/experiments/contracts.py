"""Versioned evidence contracts for masks, checkpoints, and result tables."""

from __future__ import annotations
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

DEFAULT_DESIGN_PATH = Path("configs/design_freeze_v4.yaml")
SUPPORTED_EXECUTABLE_DESIGN_VERSIONS = frozenset(
    {"design_freeze_v2", "design_freeze_v3", "design_freeze_v4"}
)
EXECUTABLE_DESIGN_VERSION = "design_freeze_v4"
DEFAULT_MANIFEST_PATH = Path("study_manifest.yaml")
SUPPORTED_EVALUATION_SPLITS = frozenset(
    {"validation", "development_test", "test", "confirmatory"}
)
CODE_PROVENANCE_SCHEMA_VERSION = "code_provenance_v1"


@dataclass(frozen=True)
class FrozenDataVersions:
    """The primary and required sensitivity versions declared by a design."""

    primary: str
    sensitivities: tuple[str, ...]

    def manifest_path(
        self, data_root: str | Path, data_version: str | None = None
    ) -> Path:
        version = self.primary if data_version is None else str(data_version)
        if version not in {self.primary, *self.sensitivities}:
            raise ValueError(
                f"data version {version!r} is outside the frozen inventory"
            )
        return Path(data_root) / version / "version_manifest.json"


def load_frozen_data_versions(
    design_path: str | Path = DEFAULT_DESIGN_PATH,
) -> FrozenDataVersions:
    """Load the authoritative data-version inventory from a design freeze."""
    design = _mapping_yaml(Path(design_path))
    raw = design.get("data_versions")
    if not isinstance(raw, Mapping):
        raise TypeError("design freeze data_versions must be a mapping")
    primary = raw.get("primary")
    sensitivities = raw.get("required_sensitivity")
    definitions = raw.get("definitions")
    if not isinstance(primary, str) or not primary or primary.strip() != primary:
        raise ValueError("design freeze requires one normalized primary data version")
    if (
        not isinstance(sensitivities, list)
        or not sensitivities
        or (
            not all(
                (
                    isinstance(value, str) and value and (value.strip() == value)
                    for value in sensitivities
                )
            )
        )
    ):
        raise ValueError("design freeze requires normalized sensitivity data versions")
    frozen_sensitivities = tuple(sensitivities)
    if len(set(frozen_sensitivities)) != len(frozen_sensitivities):
        raise ValueError("design freeze sensitivity data versions must be unique")
    if primary in frozen_sensitivities:
        raise ValueError("primary data version cannot also be a sensitivity")
    if not isinstance(definitions, Mapping) or not {
        primary,
        *frozen_sensitivities,
    }.issubset(definitions):
        raise ValueError("design freeze lacks definitions for executable data versions")
    return FrozenDataVersions(primary=primary, sensitivities=frozen_sensitivities)


def canonical_evaluation_split(value: str) -> str:
    """Return the evidence label, normalising the stored ``test`` alias.

    The processed development table predates the evidence contract and stores
    2018--2020 rows as ``test``.  New artifacts must call that already-visible
    period ``development_test`` so it cannot be mistaken for confirmation.
    """
    label = str(value).strip()
    if label not in SUPPORTED_EVALUATION_SPLITS:
        raise ValueError(
            "evaluation_split must be validation, development_test, test, or confirmatory"
        )
    return "development_test" if label == "test" else label


def result_run_root(output_root: str | Path, data_version: str) -> Path:
    """Locate results by data version only. Code edits do not create a new folder."""
    version = str(data_version).strip()
    if not version:
        raise ValueError("data_version is required for a result directory")
    return Path(output_root) / version


def validate_data_version_inputs(
    *,
    data_version_manifest_path: str | Path | None,
    data_version: str,
    wide_path: str | Path,
    quality_path: str | Path | None,
    require_manifest: bool,
    require_quality: bool,
) -> dict[str, Any] | None:
    """Confirm the named version's wide/long tables exist."""
    if data_version_manifest_path is None:
        if require_manifest:
            raise ValueError("formal execution requires a data-version manifest")
        return None
    manifest_path = Path(data_version_manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"data-version manifest is missing: {manifest_path}")
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("data-version manifest is invalid JSON") from error
    if not isinstance(document, Mapping):
        raise TypeError("data-version manifest must be a JSON mapping")
    if document.get("data_version") != str(data_version):
        raise ValueError(
            "data-version manifest identity differs from the experiment grid"
        )
    required = {
        "daily_wide.parquet": Path(wide_path),
        "daily_long.parquet": Path(quality_path) if quality_path is not None else None,
    }
    if require_quality and required["daily_long.parquet"] is None:
        raise ValueError("formal execution requires quality_path/daily_long.parquet")
    validated: dict[str, dict[str, Any]] = {}
    for name, path in required.items():
        if path is None:
            continue
        if not path.is_file():
            raise FileNotFoundError(f"data-version input is missing: {path}")
        validated[name] = {"path": str(path.resolve()), "bytes": path.stat().st_size}
    return {
        "data_version": str(data_version),
        "manifest": {
            "path": str(manifest_path.resolve()),
            "bytes": manifest_path.stat().st_size,
        },
        "artifacts": validated,
    }


def _mapping_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"expected a YAML mapping in {path}")
    return value


def build_code_provenance(
    *,
    repository_root: str | Path | None = None,
    additional_relevant_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Record where a run reads code and configuration, without a Git scan."""
    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[3]
    )
    return {
        "schema_version": CODE_PROVENANCE_SCHEMA_VERSION,
        "status": "working_tree",
        "code_location": str(root),
        "additional_inputs": [
            str((root / p).resolve()) for p in additional_relevant_paths
        ],
    }


def build_design_contract(
    *,
    design_path: str | Path = DEFAULT_DESIGN_PATH,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    experiment_config_path: str | Path = "configs/experiments.yaml",
    data_version: str,
    evaluation_split: str,
    data_version_manifest_path: str | Path | None = None,
    code_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the scientific labels used to read and write results.

    Result directories are keyed by data version, not by source contents.
    Changing roster, ranking, or checker code does not create a new folder
    and does not invalidate already-trained weights.
    """
    design_file = Path(design_path)
    study_file = Path(manifest_path)
    experiment_file = Path(experiment_config_path)
    design = _mapping_yaml(design_file)
    _mapping_yaml(study_file)
    _mapping_yaml(experiment_file)
    evidence = design.get("evidence_contract", {})
    statistics = design.get("statistics", {})
    mask_design = design.get("mask_design", {})
    training = design.get("training", {})
    if not isinstance(evidence, dict):
        raise TypeError("design freeze evidence_contract must be a mapping")
    version_manifest = (
        Path(data_version_manifest_path)
        if data_version_manifest_path is not None
        else None
    )
    if version_manifest is not None and (not version_manifest.exists()):
        raise FileNotFoundError(version_manifest)
    provenance = dict(
        code_provenance
        if code_provenance is not None
        else build_code_provenance(
            additional_relevant_paths=(design_file, study_file, experiment_file)
        )
    )
    contract = {
        "design_version": str(design["design_version"]),
        "data_version": str(data_version),
        "evaluation_split": canonical_evaluation_split(evaluation_split),
        "mask_schema_version": str(mask_design["schema_version"]),
        "model_schema_version": str(training["schema_version"]),
        "statistics_schema_version": str(statistics["schema_version"]),
        "code_provenance": provenance,
    }
    missing = set(evidence.get("required_fields", ())).difference(contract)
    if missing:
        raise ValueError(
            f"design freeze requires contract fields that are not implemented: {sorted(missing)}"
        )
    return contract


__all__ = [
    "CODE_PROVENANCE_SCHEMA_VERSION",
    "DEFAULT_DESIGN_PATH",
    "DEFAULT_MANIFEST_PATH",
    "EXECUTABLE_DESIGN_VERSION",
    "FrozenDataVersions",
    "SUPPORTED_EXECUTABLE_DESIGN_VERSIONS",
    "SUPPORTED_EVALUATION_SPLITS",
    "build_code_provenance",
    "build_design_contract",
    "canonical_evaluation_split",
    "load_frozen_data_versions",
    "result_run_root",
    "validate_data_version_inputs",
]
