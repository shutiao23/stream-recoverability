"""Versioned evidence contracts for masks, checkpoints, and result tables."""

from __future__ import annotations

import hashlib
import json
import subprocess
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
_RELEVANT_CODE_DIRECTORIES = (
    "src/stream_recoverability/evaluation",
    "src/stream_recoverability/experiments",
    "src/stream_recoverability/masks",
    "src/stream_recoverability/models",
)
_RELEVANT_CODE_FILES = (
    "src/stream_recoverability/__init__.py",
    "src/stream_recoverability/analysis/compensation.py",
    "src/stream_recoverability/data/confirmatory.py",
    "scripts/05_train_deep_baselines.py",
    "scripts/08_run_experiments.py",
    "scripts/12_run_science_experiments.py",
    "scripts/13_aggregate_formal_results.py",
    "scripts/15_run_validation_funnel.py",
    "scripts/20_run_confirmatory_evaluation.py",
    "pyproject.toml",
)
_FUTURE_ORCHESTRATION_PATTERNS = (
    "scripts/*ablation*.py",
    "scripts/*retrain*.py",
    "scripts/*upper_bound*.py",
)


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
        or not all(
            isinstance(value, str) and value and value.strip() == value
            for value in sensitivities
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


LEGACY_IDENTITY_FIELDS = frozenset(
    {
        "design_hash",
        "code_identity",
        "input_digests",
        "code_identity_sha256",
        "selection_design_hash",
    }
)


def result_run_root(output_root: str | Path, data_version: str) -> Path:
    """Locate results by data version only. Code edits do not create a new folder."""

    version = str(data_version).strip()
    if not version:
        raise ValueError("data_version is required for a result directory")
    return Path(output_root) / version


def without_legacy_identity(value: Any) -> Any:
    """Drop leftover digest-identity fields so old artifacts stay readable."""

    if isinstance(value, Mapping):
        return {
            key: without_legacy_identity(item)
            for key, item in value.items()
            if key not in LEGACY_IDENTITY_FIELDS
        }
    if isinstance(value, list):
        return [without_legacy_identity(item) for item in value]
    return value


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
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise TypeError("data-version manifest artifacts must be a mapping")
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
        if name not in artifacts:
            raise TypeError(f"data-version manifest lacks {name}")
        if not path.is_file():
            raise FileNotFoundError(f"data-version input is missing: {path}")
        validated[name] = {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
        }
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


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git_output(repository_root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository_root), *arguments),
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("git command unavailable") from error
    if completed.returncode:
        raise RuntimeError("git command failed")
    return completed.stdout


def _repository_root() -> Path:
    source_checkout = Path(__file__).resolve().parents[3]
    root = _git_output(source_checkout, "rev-parse", "--show-toplevel")
    return Path(root.decode("utf-8").strip()).resolve()


def _repo_relative(path: str | Path, repository_root: Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        return candidate.resolve().relative_to(repository_root).as_posix()
    except ValueError:
        return None


def _is_future_orchestration_path(path: str) -> bool:
    candidate = Path(path)
    return any(candidate.match(pattern) for pattern in _FUTURE_ORCHESTRATION_PATTERNS)


def build_code_provenance(
    *,
    repository_root: str | Path | None = None,
    additional_relevant_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Return a clone-stable identity for code that can affect an experiment.

    The clean-worktree check is deliberately scoped to the runner's import
    surface, its entry point, dependency declaration, and the frozen config
    inputs supplied by the caller.  Untracked masks, checkpoints, results, and
    other generated outputs therefore cannot block a formal run, while an
    untracked Python file inside the relevant source roots still does.
    """

    try:
        root = (
            Path(repository_root).resolve()
            if repository_root is not None
            else _repository_root()
        )
        commit = _git_output(root, "rev-parse", "HEAD").decode("ascii").strip()
    except RuntimeError:
        return {
            "schema_version": CODE_PROVENANCE_SCHEMA_VERSION,
            "git_commit": None,
            "tracked_worktree_clean": False,
            "relevant_source_clean": False,
            "relevant_source_digest": None,
            "relevant_source_file_count": 0,
            "dirty_tracked_paths": [],
            "relevant_untracked_paths": [],
            "external_relevant_input_count": len(additional_relevant_paths),
            "status": "git_repository_unavailable",
        }

    explicit_paths = set(_RELEVANT_CODE_FILES)
    external_relevant_inputs = 0
    for path in additional_relevant_paths:
        relative = _repo_relative(path, root)
        if relative is None:
            external_relevant_inputs += 1
        else:
            explicit_paths.add(relative)

    pathspecs = [*_RELEVANT_CODE_DIRECTORIES, "scripts", *sorted(explicit_paths)]
    tracked_output = _git_output(root, "ls-files", "-z", "--", *pathspecs)
    tracked_paths = {
        value.decode("utf-8") for value in tracked_output.split(b"\0") if value
    }
    tracked_paths = {
        path
        for path in tracked_paths
        if path in explicit_paths
        or _is_future_orchestration_path(path)
        or (
            path.endswith(".py")
            and any(
                path.startswith(f"{directory}/")
                for directory in _RELEVANT_CODE_DIRECTORIES
            )
        )
    }

    filesystem_paths = {path for path in explicit_paths if (root / path).is_file()}
    for pattern in _FUTURE_ORCHESTRATION_PATTERNS:
        filesystem_paths.update(
            path.relative_to(root).as_posix()
            for path in root.glob(pattern)
            if path.is_file()
        )
    for directory in _RELEVANT_CODE_DIRECTORIES:
        source_root = root / directory
        if source_root.is_dir():
            filesystem_paths.update(
                path.relative_to(root).as_posix()
                for path in source_root.rglob("*.py")
                if path.is_file()
            )
    relevant_paths = tracked_paths | filesystem_paths
    dirty_output = _git_output(
        root,
        "diff",
        "--name-only",
        "--no-ext-diff",
        "-z",
        "HEAD",
        "--",
        *sorted(relevant_paths),
    )
    dirty_tracked_paths = sorted(
        value.decode("utf-8") for value in dirty_output.split(b"\0") if value
    )
    relevant_untracked_paths = sorted(filesystem_paths.difference(tracked_paths))
    file_identities = [
        {
            "path": path,
            "sha256": file_sha256(root / path) if (root / path).is_file() else None,
        }
        for path in sorted(relevant_paths)
    ]
    tracked_worktree_clean = not dirty_tracked_paths
    relevant_source_clean = bool(
        tracked_worktree_clean
        and not relevant_untracked_paths
        and not external_relevant_inputs
    )
    return {
        "schema_version": CODE_PROVENANCE_SCHEMA_VERSION,
        "git_commit": commit,
        "tracked_worktree_clean": tracked_worktree_clean,
        "relevant_source_clean": relevant_source_clean,
        "relevant_source_digest": _canonical_digest({"files": file_identities}),
        "relevant_source_file_count": len(file_identities),
        "dirty_tracked_paths": dirty_tracked_paths,
        "relevant_untracked_paths": relevant_untracked_paths,
        "external_relevant_input_count": external_relevant_inputs,
        "status": "clean" if relevant_source_clean else "dirty",
    }


def canonical_code_identity(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Select only clone-stable implementation fields for design hashing."""

    identity = {
        "schema_version": provenance.get("schema_version"),
        "relevant_source_digest": provenance.get("relevant_source_digest"),
        "relevant_source_file_count": provenance.get("relevant_source_file_count"),
    }
    if not isinstance(identity["schema_version"], str):
        raise TypeError("code provenance is missing schema_version")
    digest = identity["relevant_source_digest"]
    if not isinstance(digest, str):
        raise TypeError("code provenance source digest must be a string")
    if len(digest) != 64:
        raise ValueError("code provenance is missing a SHA-256 source digest")
    if not isinstance(identity["relevant_source_file_count"], int):
        raise TypeError("code provenance is missing relevant_source_file_count")
    return identity


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

    Result directories are keyed by data version, not by a source digest.
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
    if version_manifest is not None and not version_manifest.exists():
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
            "design freeze requires contract fields that are not implemented: "
            f"{sorted(missing)}"
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
    "canonical_code_identity",
    "canonical_evaluation_split",
    "file_sha256",
    "LEGACY_IDENTITY_FIELDS",
    "load_frozen_data_versions",
    "result_run_root",
    "validate_data_version_inputs",
    "without_legacy_identity",
]
