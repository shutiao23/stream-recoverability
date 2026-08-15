"""Versioned evidence contracts for masks, checkpoints, and result tables."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DESIGN_PATH = Path("configs/design_freeze_v1.yaml")
DEFAULT_MANIFEST_PATH = Path("study_manifest.yaml")
SUPPORTED_EVALUATION_SPLITS = frozenset(
    {"validation", "development_test", "test", "confirmatory"}
)


def canonical_evaluation_split(value: str) -> str:
    """Return the evidence label, normalising the stored ``test`` alias.

    The processed development table predates the evidence contract and stores
    2018--2020 rows as ``test``.  New artifacts must call that already-visible
    period ``development_test`` so it cannot be mistaken for confirmation.
    """

    label = str(value).strip()
    if label not in SUPPORTED_EVALUATION_SPLITS:
        raise ValueError(
            "evaluation_split must be validation, development_test, test, or "
            "confirmatory"
        )
    return "development_test" if label == "test" else label


def file_sha256(path: str | Path) -> str:
    """Return a content digest without relying on mutable timestamps."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"expected a YAML mapping in {path}")
    return value


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_design_contract(
    *,
    design_path: str | Path = DEFAULT_DESIGN_PATH,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    experiment_config_path: str | Path = "configs/experiments.yaml",
    data_version: str,
    evaluation_split: str,
    data_version_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the canonical contract whose digest invalidates stale evidence."""

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
    if version_manifest is not None and not version_manifest.exists():
        raise FileNotFoundError(version_manifest)

    # Paths are intentionally excluded: the same frozen inputs must receive the
    # same design hash in a clone, container, or absolute/relative invocation.
    inputs: dict[str, str | None] = {
        "design_freeze": file_sha256(design_file),
        "study_manifest": file_sha256(study_file),
        "experiment_config": file_sha256(experiment_file),
        "data_version_manifest": (
            file_sha256(version_manifest) if version_manifest is not None else None
        ),
    }
    canonical_split = canonical_evaluation_split(evaluation_split)
    contract = {
        "design_version": str(design["design_version"]),
        "data_version": str(data_version),
        "evaluation_split": canonical_split,
        "mask_schema_version": str(mask_design["schema_version"]),
        "model_schema_version": str(training["schema_version"]),
        "statistics_schema_version": str(statistics["schema_version"]),
        "input_digests": inputs,
    }
    contract["design_hash"] = _canonical_digest(contract)
    missing = set(evidence.get("required_fields", ())).difference(contract)
    if missing:
        raise ValueError(
            "design freeze requires contract fields that are not implemented: "
            f"{sorted(missing)}"
        )
    return contract


__all__ = [
    "DEFAULT_DESIGN_PATH",
    "DEFAULT_MANIFEST_PATH",
    "SUPPORTED_EVALUATION_SPLITS",
    "build_design_contract",
    "canonical_evaluation_split",
    "file_sha256",
]
