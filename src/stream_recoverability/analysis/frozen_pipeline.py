"""Fail-closed analysis of one frozen, top-level result bundle.

The functions in this module deliberately separate artifact validation from
scientific analysis.  No table is analysed until its content hash, row count,
evidence contract, split, and completion declaration agree with the top-level
manifest.  Inferential helpers then collapse optimisation seeds before using
mask anchors, event episodes, or target-gap years as sampling units.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.stats import wilcoxon

from stream_recoverability.analysis.compensation import (
    INFORMATION_SOURCES,
    build_value_function,
    combination_label,
    compensation_gains,
    information_combinations,
    normalize_combination,
    shapley_table,
)
from stream_recoverability.analysis.inference_safeguards import (
    add_guarded_climatology_skill,
    anchor_year_frontier_bootstrap,
    assess_application_boundary,
    benjamini_hochberg_by_family,
    raw_and_monotone_frontier,
    resolve_climatology_denominator_threshold,
)
from stream_recoverability.analysis.frontiers import estimate_dual_frontiers
from stream_recoverability.analysis.falsification import interpret_falsification
from stream_recoverability.analysis.resilience import (
    RESILIENCE_GROUP_COLUMNS,
    complete_resilience_units,
    node_importance,
    resilience_auc,
    resilience_curve,
)
from stream_recoverability.analysis.uncertainty import (
    interval_calibration_by_gap,
    overall_calibration,
    uncertainty_growth,
)

EVIDENCE_FIELDS = (
    "design_version",
    "data_version",
    "evaluation_split",
    "mask_schema_version",
    "model_schema_version",
    "statistics_schema_version",
)
FRONTIER_GROUPS = (
    "station_id",
    "target",
    "data_version",
    "model",
    "information_combination",
    "window",
    "evaluation_split",
)
FIXED_ARTIFACTS = (
    "best_simple_baseline_lookup.csv",
    "relative_skill_events.parquet",
    "frontier_climatology_curves.csv",
    "frontier_climatology_summary.csv",
    "frontier_best_simple_curves.csv",
    "frontier_best_simple_summary.csv",
    "dual_frontier_comparison.csv",
    "frontier_raw_curves.csv",
    "frontier_monotone_curves.csv",
    "statistical_frontiers.csv",
    "application_frontiers.csv",
    "frontier_breakpoints.csv",
    "frontier_bootstrap_samples.parquet",
    "pairwise_jaccard.csv",
    "unique_date_coverage.csv",
    "effective_replication_summary.csv",
    "overlap_clusters.csv",
    "information_combination_metrics.csv",
    "operational_dropout_gains.csv",
    "retrained_information_upper_bounds.csv",
    "shapley_contributions.csv",
    "information_interactions.csv",
    "resilience_curves.csv",
    "node_importance.csv",
    "failure_set_metrics.csv",
    "resilience_auc.csv",
    "event_episode_metrics.csv",
    "event_vs_matched_control.csv",
    "calibration_by_gap.csv",
    "calibration_overall.csv",
    "uncertainty_growth.csv",
    "uncertainty_by_difficulty.csv",
    "data_version_sensitivity.csv",
    "hypothesis_tests.csv",
    "donor_c_falsification_effects.csv",
    "donor_c_falsification_decision.csv",
)
ANALYSIS_CODE_PATHS = (
    "scripts/09_analyze_results.py",
    "src/stream_recoverability/analysis/frozen_pipeline.py",
    "src/stream_recoverability/analysis/inference_safeguards.py",
    "src/stream_recoverability/analysis/compensation.py",
    "src/stream_recoverability/analysis/resilience.py",
    "src/stream_recoverability/analysis/uncertainty.py",
    "src/stream_recoverability/analysis/frontiers.py",
    "src/stream_recoverability/analysis/falsification.py",
)
ANALYSIS_BUILDER_PATHS = (
    "scripts/09_analyze_results.py",
    "src/stream_recoverability/analysis/frozen_pipeline.py",
)
PRIMARY_REQUIRED_SUITE_ROLES = (
    "core_full",
    "dense_frontier",
    "network_resilience",
    "event_uncertainty",
    "operational_dropout",
    "retrained_upper_bound",
    "donor_c_falsification",
)
LEGACY_PRIMARY_REQUIRED_SUITE_ROLES = tuple(
    role for role in PRIMARY_REQUIRED_SUITE_ROLES if role != "donor_c_falsification"
)
SENSITIVITY_REQUIRED_SUITE_ROLES = (
    "sensitivity_core_T",
    "sensitivity_dense_frontier",
    "sensitivity_operational_dropout",
)
PROPOSED_PRIMARY_ROLES = frozenset(
    {"operational_dropout", "retrained_upper_bound"}
)
PROPOSED_SENSITIVITY_ROLES = frozenset({"sensitivity_operational_dropout"})
FORMAL_REGISTRY_BUILDER_PATHS = (
    "scripts/21_build_formal_suite_registry.py",
    "src/stream_recoverability/analysis/formal_registry.py",
)
REQUIRED_ANALYSIS_DOMAINS = (
    "formal_input_roles",
    "overlap_audit",
    "recoverability_frontier",
    "operational_information",
    "retrained_information",
    "network_resilience",
    "event_uncertainty",
    "uncertainty_calibration",
    "data_version_sensitivity",
    "donor_c_falsification",
    "hypothesis_families",
)
OPERATIONAL_INFORMATION_COMBINATIONS = tuple(information_combinations())
RETRAINED_INFORMATION_COMBINATIONS = (
    frozenset(),
    frozenset({"A"}),
    frozenset({"B"}),
    frozenset({"C"}),
    frozenset({"D"}),
    frozenset({"A", "B"}),
    frozenset({"A", "C"}),
    frozenset({"A", "D"}),
    frozenset(INFORMATION_SOURCES),
)


@dataclass(frozen=True)
class FrozenStatistics:
    """The numerical analysis decisions loaded from the design freeze."""

    bootstrap_replicates: int
    bootstrap_seed: int
    confidence: float
    denominator_guard: Mapping[str, Any]
    hypothesis_families: tuple[str, ...]
    application_criteria: Mapping[str, tuple[str, float]] | None
    dense_t_gaps: tuple[float, ...]
    dense_fl_gaps: tuple[float, ...]
    primary_data_version: str
    sensitivity_data_versions: tuple[str, ...]


@dataclass(frozen=True)
class FrozenInputs:
    """Validated result frames and their immutable top-level declaration."""

    predictions: pd.DataFrame
    events: pd.DataFrame
    manifest: dict[str, Any]
    statistics: FrozenStatistics
    predictions_path: Path
    events_path: Path
    manifest_path: Path
    design_path: Path
    registry: dict[str, Any]
    registry_path: Path
    registry_identity: dict[str, Any]


@dataclass(frozen=True)
class OverlapArtifacts:
    """Sparse audit products and anchor-to-dependence-cluster assignments."""

    pairwise: pd.DataFrame
    dates: pd.DataFrame
    replication: pd.DataFrame
    clusters: pd.DataFrame
    summary: dict[str, Any]


@dataclass(frozen=True)
class FrontierArtifacts:
    raw: pd.DataFrame
    monotone: pd.DataFrame
    statistical: pd.DataFrame
    application: pd.DataFrame
    breakpoints: pd.DataFrame
    bootstrap_samples: pd.DataFrame


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{context} requires columns: {missing}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_analysis_code_identity(
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return clone-stable layered identities and a scoped Git cleanliness audit."""

    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[3]
    )
    identities: list[dict[str, str]] = []
    missing: list[str] = []
    for relative in sorted(ANALYSIS_CODE_PATHS):
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        else:
            identities.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
    try:
        dirty_process = subprocess.run(
            (
                "git",
                "-C",
                str(root),
                "diff",
                "--name-only",
                "--no-ext-diff",
                "HEAD",
                "--",
                *ANALYSIS_CODE_PATHS,
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        untracked_process = subprocess.run(
            (
                "git",
                "-C",
                str(root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                *ANALYSIS_CODE_PATHS,
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        dirty_process = untracked_process = None
    git_available = bool(
        dirty_process is not None
        and untracked_process is not None
        and dirty_process.returncode == 0
        and untracked_process.returncode == 0
    )
    dirty = (
        sorted(filter(None, dirty_process.stdout.splitlines()))
        if git_available and dirty_process is not None
        else []
    )
    untracked = (
        sorted(filter(None, untracked_process.stdout.splitlines()))
        if git_available and untracked_process is not None
        else []
    )
    clean = bool(git_available and not missing and not dirty and not untracked)
    by_path = {item["path"]: item for item in identities}
    builder_sources = [
        by_path[path] for path in ANALYSIS_BUILDER_PATHS if path in by_path
    ]
    builder_identity: dict[str, Any] = {
        "schema_version": "frozen_analysis_builder_identity_v1",
        "sources": builder_sources,
        "identity_hash_scope": "canonical_json_excluding_identity_sha256",
    }
    builder_identity["identity_sha256"] = _canonical_digest(builder_identity)
    return {
        "schema_version": "analysis_code_identity_v1",
        "relevant_source_digest": _canonical_digest({"files": identities}),
        "relevant_source_file_count": len(identities),
        "files": identities,
        "frozen_analysis_builder": builder_identity,
        "tracked_relevant_source_clean": not dirty if git_available else False,
        "dirty_tracked_paths": dirty,
        "relevant_untracked_paths": untracked,
        "missing_paths": missing,
        "git_audit_available": git_available,
        "status": "clean" if clean else "dirty",
    }


def require_clean_analysis_code(identity: Mapping[str, Any]) -> None:
    """Fail before writing outputs when analysis source is not frozen in Git."""

    if identity.get("status") != "clean":
        raise RuntimeError(
            "analysis code identity is not clean: "
            f"dirty={identity.get('dirty_tracked_paths')}, "
            f"untracked={identity.get('relevant_untracked_paths')}, "
            f"missing={identity.get('missing_paths')}"
        )


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".yaml", ".yml"}:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a mapping in {path}")
    return value


def _read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported result table format: {path}")


def load_frozen_statistics(design_path: str | Path) -> FrozenStatistics:
    """Load and verify the exact numerical decisions frozen for this study."""

    design = _read_mapping(Path(design_path))
    statistics = design.get("statistics")
    mask_design = design.get("mask_design")
    if not isinstance(statistics, Mapping) or not isinstance(mask_design, Mapping):
        raise TypeError("design freeze requires statistics and mask_design mappings")

    bootstrap = int(statistics.get("bootstrap_replicates", -1))
    seed = int(statistics.get("bootstrap_seed", -1))
    confidence = float(statistics.get("confidence_level", np.nan))
    if (bootstrap, seed) != (2000, 20260815) or not np.isclose(confidence, 0.95):
        raise ValueError("analysis must use the frozen 2000/20260815/95% bootstrap")
    if statistics.get("monotone_method") != "weighted_PAVA_nonincreasing":
        raise ValueError("analysis requires the frozen weighted non-increasing PAVA")
    if (
        statistics.get("breakpoint_method")
        != "one_internal_hinge_weighted_least_squares"
    ):
        raise ValueError("analysis requires the frozen one-hinge breakpoint method")
    if statistics.get("multiplicity") != (
        "benjamini_hochberg_within_declared_hypothesis_family"
    ):
        raise ValueError("analysis requires BH within named hypothesis families")

    guard = statistics.get("climatology_denominator_guard")
    if not isinstance(guard, Mapping):
        raise TypeError("climatology_denominator_guard must be a mapping")
    expected_thresholds = {"T": 0.05, "F": 0.5, "L": 0.005}
    for target, expected in expected_thresholds.items():
        actual = resolve_climatology_denominator_threshold(guard, target)
        if not np.isclose(actual, expected, rtol=0.0, atol=1e-12):
            raise ValueError(f"unexpected frozen denominator threshold for {target}")

    families = tuple(str(value) for value in statistics.get("hypothesis_families", ()))
    required_families = {
        "frontier_model_vs_climatology",
        "operational_information_dropout",
        "retrained_information_upper_bound",
        "network_failure_set",
        "event_vs_matched_control",
        "data_version_sensitivity",
    }
    if not required_families.issubset(families):
        raise ValueError("design freeze omits a required named hypothesis family")

    application = statistics.get("application_thresholds")
    if not isinstance(application, Mapping):
        raise TypeError("application_thresholds must be a mapping")
    if application.get("status") == "not_declared":
        application_criteria = None
    else:
        raw_criteria = application.get("criteria")
        if not isinstance(raw_criteria, Mapping) or not raw_criteria:
            raise ValueError("declared application thresholds require criteria")
        application_criteria = {}
        for metric, declaration in raw_criteria.items():
            if not isinstance(declaration, Mapping):
                raise TypeError("each application criterion must be a mapping")
            application_criteria[str(metric)] = (
                str(declaration["operator"]),
                float(declaration["value"]),
            )

    primary_data_version = str(design["data_versions"]["primary"])
    sensitivity_data_versions = tuple(
        str(value) for value in design["data_versions"]["required_sensitivity"]
    )
    if not primary_data_version or not sensitivity_data_versions:
        raise ValueError(
            "analysis design requires primary and sensitivity data versions"
        )
    if primary_data_version in sensitivity_data_versions or len(
        set(sensitivity_data_versions)
    ) != len(sensitivity_data_versions):
        raise ValueError("analysis design data-version inventory is inconsistent")

    return FrozenStatistics(
        bootstrap,
        seed,
        confidence,
        guard,
        families,
        application_criteria,
        tuple(float(value) for value in mask_design["dense_T_block_lengths"]),
        tuple(float(value) for value in mask_design["dense_FL_block_lengths"]),
        primary_data_version,
        sensitivity_data_versions,
    )


def _artifact_hash(manifest: Mapping[str, Any], kind: str, path: Path) -> str:
    candidates: list[Any] = [
        manifest.get(f"{kind}_sha256"),
        manifest.get(f"{kind.rstrip('s')}_sha256"),
    ]
    hashes = manifest.get("artifact_hashes")
    if isinstance(hashes, Mapping):
        for key in (kind, path.name, str(path), str(path.resolve())):
            value = hashes.get(key)
            candidates.append(
                value.get("sha256") if isinstance(value, Mapping) else value
            )
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, Mapping):
        for key in (kind, path.name):
            value = artifacts.get(key)
            candidates.append(
                value.get("sha256") if isinstance(value, Mapping) else None
            )
    valid = [str(value).lower() for value in candidates if value is not None]
    if not valid:
        raise ValueError(f"top manifest does not declare a SHA-256 for {kind}")
    if len(set(valid)) != 1 or len(valid[0]) != 64:
        raise ValueError(f"top manifest has inconsistent or malformed {kind} hashes")
    return valid[0]


def _manifest_contracts(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    declared = manifest.get("evidence_contracts")
    if declared is None:
        declared = [manifest]
    if not isinstance(declared, list) or len(declared) != 1:
        raise ValueError("top manifest requires exactly one evidence contract")
    contracts: list[dict[str, Any]] = []
    for raw in declared:
        if not isinstance(raw, Mapping):
            raise TypeError("each evidence contract must be a mapping")
        missing = sorted(set(EVIDENCE_FIELDS).difference(raw))
        if missing:
            raise ValueError(f"evidence contract is missing fields: {missing}")
        canonical = {field: raw[field] for field in EVIDENCE_FIELDS}
        provenance = raw.get("code_provenance")
        if isinstance(provenance, Mapping):
            canonical["code_provenance"] = dict(provenance)
        contracts.append(canonical)
    return contracts


def _lower_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _validate_bundle_roles(manifest: Mapping[str, Any]) -> dict[str, Any]:
    bundle_role = manifest.get("bundle_role")
    if bundle_role == "primary":
        expected_kind = "primary"
        require_donor = manifest.get("design_version") == "design_freeze_v4"
        required_roles = list(
            PRIMARY_REQUIRED_SUITE_ROLES
            if require_donor
            else LEGACY_PRIMARY_REQUIRED_SUITE_ROLES
        )
        proposed_roles = PROPOSED_PRIMARY_ROLES
    elif bundle_role == "sensitivity_compact":
        expected_kind = "sensitivity"
        required_roles = list(SENSITIVITY_REQUIRED_SUITE_ROLES)
        proposed_roles = PROPOSED_SENSITIVITY_ROLES
    else:
        raise ValueError("top manifest has an unknown or missing bundle_role")
    if manifest.get("bundle_kind") != expected_kind:
        raise ValueError("top manifest bundle_kind disagrees with bundle_role")
    if manifest.get("required_suite_roles") != required_roles:
        raise ValueError("top manifest required suite-role inventory is incomplete")
    roster = manifest.get("finalized_model_roster")
    if not isinstance(roster, Mapping):
        raise TypeError("top manifest lacks finalized_model_roster")
    selected = roster.get("selected_models")
    decision = roster.get("proposed_decision")
    if (
        not isinstance(selected, list)
        or not selected
        or len(set(selected)) != len(selected)
        or decision not in {"include_proposed_formally", "framework_only"}
        or ("proposed" in selected) != (decision == "include_proposed_formally")
    ):
        raise ValueError("top manifest finalized roster is inconsistent")
    roster_sha = _lower_sha256(roster.get("sha256"), "finalized roster SHA-256")
    roster_path = roster.get("path")
    if not isinstance(roster_path, str) or not roster_path:
        raise ValueError("top manifest finalized roster lacks a path")

    raw_roles = manifest.get("suite_roles")
    if not isinstance(raw_roles, list) or len(raw_roles) != len(required_roles):
        raise ValueError("top manifest suite_roles does not close required roles")
    if [
        item.get("role") if isinstance(item, Mapping) else None for item in raw_roles
    ] != required_roles:
        raise ValueError(
            "top manifest suite_roles is missing, reordered, or duplicated"
        )
    roles: list[dict[str, Any]] = []
    for raw, role in zip(raw_roles, required_roles, strict=True):
        if not isinstance(raw, Mapping):
            raise TypeError("top manifest suite role rows must be mappings")
        if set(raw) != {
            "role",
            "status",
            "reason",
            "manifest_suites",
            "source_manifest_sha256",
            "expected_models",
        }:
            raise ValueError(f"top manifest role {role} fields are not frozen")
        item = dict(raw)
        should_be_na = decision == "framework_only" and role in proposed_roles
        if should_be_na:
            expected = {
                "role": role,
                "status": "not_applicable",
                "reason": "proposed_decision=framework_only",
                "manifest_suites": [],
                "source_manifest_sha256": [],
                "expected_models": [],
            }
            if item != expected:
                raise ValueError(f"top manifest role {role} must be not_applicable")
        else:
            if item.get("status") != "complete" or item.get("reason") is not None:
                raise ValueError(f"top manifest role {role} is not complete")
            for field in (
                "manifest_suites",
                "source_manifest_sha256",
                "expected_models",
            ):
                values = item.get(field)
                if (
                    not isinstance(values, list)
                    or not values
                    or not all(isinstance(value, str) and value for value in values)
                    or len(values) != len(set(values))
                ):
                    raise ValueError(f"top manifest role {role} has invalid {field}")
            for digest in item["source_manifest_sha256"]:
                _lower_sha256(digest, f"top manifest role {role} source hash")
        roles.append(item)
    return {
        "bundle_kind": expected_kind,
        "bundle_role": bundle_role,
        "required_suite_roles": required_roles,
        "suite_roles": roles,
        "finalized_model_roster": {
            "path": roster_path,
            "sha256": roster_sha,
            "selected_models": list(selected),
            "proposed_decision": decision,
        },
    }


def _validate_completion(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != "formal_aggregate_manifest_v2":
        raise ValueError("analysis requires formal_aggregate_manifest_v2")
    if manifest.get("frozen") is not True:
        raise ValueError("top manifest must declare frozen=true")
    if manifest.get("formal_evidence") is not True:
        raise ValueError("top manifest must declare formal_evidence=true")
    if manifest.get("evidence_role") != "formal_development_evaluation":
        raise ValueError("top manifest is not formal development evidence")
    _validate_bundle_roles(manifest)
    for field in (
        "complete",
        "formal_design_complete",
        "formal_training_seed_complete",
        "formal_mask_seed_complete",
        "run_unit_complete",
        "evidence_complete",
        "finite_predictions",
        "finite_event_metrics",
        "checkpoint_contract_complete",
    ):
        if manifest.get(field) is not True:
            raise ValueError(f"top manifest is not complete: {field} is not true")
    if "status" in manifest and manifest["status"] != "complete":
        raise ValueError("top manifest status is not complete")
    if manifest.get("retryable_run_keys") != []:
        raise ValueError("top manifest must declare retryable_run_keys=[]")
    if manifest.get("retryable_run_unit_count") != 0:
        raise ValueError("top manifest must declare retryable_run_unit_count=0")
    for field, value in manifest.items():
        if field.startswith("duplicate_") and field.endswith("_removed") and value != 0:
            raise ValueError(f"top manifest declares deduplicated evidence in {field}")
    count_pairs = (
        ("expected_run_unit_count", "completed_run_unit_count"),
        ("expected_evidence_run_unit_count", "completed_evidence_run_unit_count"),
        ("expected_contract_units", "completed_contract_units"),
        ("expected_run_count", "completed_status_run_count"),
        ("expected_formal_units", "completed_aggregate_units"),
    )
    for expected, completed in count_pairs:
        if expected in manifest or completed in manifest:
            if not isinstance(manifest.get(expected), int) or not isinstance(
                manifest.get(completed), int
            ):
                raise ValueError(
                    f"top manifest must declare integer {expected}/{completed}"
                )
            if manifest[expected] != manifest[completed]:
                raise ValueError(
                    f"top manifest is incomplete: {expected} != {completed}"
                )
    if (
        isinstance(manifest.get("expected_run_unit_count"), int)
        and isinstance(manifest.get("structural_skip_run_unit_count"), int)
        and isinstance(manifest.get("expected_evidence_run_unit_count"), int)
        and manifest["expected_evidence_run_unit_count"]
        != manifest["expected_run_unit_count"]
        - manifest["structural_skip_run_unit_count"]
    ):
        raise ValueError(
            "top manifest structural-skip/evidence counts are inconsistent"
        )
    expected_hash = manifest.get("expected_run_unit_keys_sha256")
    completed_hash = manifest.get("completed_run_unit_keys_sha256")
    if (
        not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or completed_hash != expected_hash
    ):
        raise ValueError("top manifest expected/completed run-unit hashes differ")


def _validate_table_contract(
    frame: pd.DataFrame,
    contracts: Sequence[Mapping[str, Any]],
    *,
    context: str,
) -> None:
    _require_columns(
        frame,
        (*EVIDENCE_FIELDS, "formal_evidence", "evidence_role"),
        context,
    )
    if frame.empty:
        raise ValueError(f"{context} is empty")
    if frame.loc[:, EVIDENCE_FIELDS].isna().any().any():
        raise ValueError(f"{context} contains null evidence-contract fields")
    if not frame["formal_evidence"].eq(True).all():
        raise ValueError(f"{context} requires formal_evidence=true")
    if not frame["evidence_role"].astype(str).eq("formal_development_evaluation").all():
        raise ValueError(f"{context} is not formal development evidence")
    observed = {
        tuple(str(value) for value in row)
        for row in frame.loc[:, EVIDENCE_FIELDS]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    }
    declared = {
        tuple(str(contract[field]) for field in EVIDENCE_FIELDS)
        for contract in contracts
    }
    if observed != declared:
        raise ValueError(
            f"{context} evidence contracts differ from the top manifest: "
            f"observed={sorted(observed)}, declared={sorted(declared)}"
        )


def _repository_path(value: object, *, declaring_file: Path, label: str) -> Path:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be a normalized non-empty path")
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    repository_candidate = Path(__file__).resolve().parents[3] / candidate
    local_candidate = declaring_file.parent / candidate
    if repository_candidate.exists() or not local_candidate.exists():
        return repository_candidate.resolve()
    return local_candidate.resolve()


def _verified_file_identity(
    value: object,
    *,
    declaring_file: Path,
    label: str,
    allowed_fields: frozenset[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a file identity mapping")
    fields = set(value)
    if allowed_fields is not None and fields != set(allowed_fields):
        raise ValueError(f"{label} fields are not frozen: {sorted(fields)}")
    path = _repository_path(
        value.get("path"), declaring_file=declaring_file, label=f"{label}.path"
    )
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    byte_count = value.get("bytes", value.get("size"))
    digest = value.get("sha256")
    if type(byte_count) is not int or byte_count < 0:
        raise ValueError(f"{label} has an invalid byte count")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} has a malformed SHA-256")
    if byte_count != path.stat().st_size or digest != _file_sha256(path):
        raise ValueError(f"{label} differs from its recorded bytes/SHA-256")
    return path, {"path": str(path), "bytes": byte_count, "sha256": digest}


def _validate_registry_builder_identity(
    value: object, *, registry_path: Path
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("formal registry requires registry_builder_identity")
    if set(value) != {
        "schema_version",
        "sources",
        "identity_hash_scope",
        "identity_sha256",
    }:
        raise ValueError("formal registry builder identity fields are not frozen")
    if value.get("schema_version") != "formal_registry_builder_identity_v1":
        raise ValueError("formal registry builder identity schema is not frozen")
    if value.get("identity_hash_scope") != ("canonical_json_excluding_identity_sha256"):
        raise ValueError("formal registry builder identity hash scope is unknown")
    unsigned = {key: item for key, item in value.items() if key != "identity_sha256"}
    if value.get("identity_sha256") != _canonical_digest(unsigned):
        raise ValueError("formal registry builder identity SHA-256 is inconsistent")
    sources = value.get("sources")
    if not isinstance(sources, list) or len(sources) != len(
        FORMAL_REGISTRY_BUILDER_PATHS
    ):
        raise ValueError("formal registry builder source inventory is incomplete")
    observed_paths: list[str] = []
    for index, source in enumerate(sources):
        path, _ = _verified_file_identity(
            source,
            declaring_file=registry_path,
            label=f"registry_builder_identity.sources[{index}]",
            allowed_fields=frozenset({"path", "bytes", "sha256"}),
        )
        relative = path.resolve().relative_to(Path(__file__).resolve().parents[3])
        observed_paths.append(relative.as_posix())
    if tuple(observed_paths) != FORMAL_REGISTRY_BUILDER_PATHS:
        raise ValueError("formal registry builder sources/order are not frozen")
    return json.loads(json.dumps(dict(value)))


def _load_formal_registry(
    aggregate_manifest: Mapping[str, Any],
    *,
    aggregate_manifest_path: Path,
    contract: Mapping[str, Any],
    primary_data_version: str,
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Reverse-load and close the registry trust chain for one aggregate."""

    raw_identity = aggregate_manifest.get("suite_registry")
    registry_path, registry_file = _verified_file_identity(
        raw_identity,
        declaring_file=aggregate_manifest_path,
        label="aggregate suite_registry",
        allowed_fields=frozenset({"source", "path", "size", "sha256"}),
    )
    if raw_identity.get("source") != "registry_file":
        raise ValueError("analysis requires a persisted registry_file input")
    registry = _read_mapping(registry_path)
    if registry.get("schema_version") != "formal_suite_registry_v1":
        raise ValueError("analysis requires formal_suite_registry_v1")
    if registry.get("finalized") is not True:
        raise ValueError("formal suite registry must declare finalized=true")
    if registry.get("registry_hash_scope") != (
        "canonical_json_excluding_registry_sha256"
    ):
        raise ValueError("formal suite registry hash scope is unknown")
    unsigned = {key: item for key, item in registry.items() if key != "registry_sha256"}
    if registry.get("registry_sha256") != _canonical_digest(unsigned):
        raise ValueError("formal suite registry canonical SHA-256 is inconsistent")

    data_version = str(contract["data_version"])
    expected_primary = data_version == primary_data_version
    expected_roles = (
        (
            PRIMARY_REQUIRED_SUITE_ROLES
            if contract.get("design_version") == "design_freeze_v4"
            else LEGACY_PRIMARY_REQUIRED_SUITE_ROLES
        )
        if expected_primary
        else SENSITIVITY_REQUIRED_SUITE_ROLES
    )
    expected_bundle_role = "primary" if expected_primary else "sensitivity_compact"
    expected_bundle_kind = "primary" if expected_primary else "sensitivity"
    for field, expected in (
        ("data_version", data_version),
        ("evaluation_split", contract["evaluation_split"]),
        ("bundle_role", expected_bundle_role),
        ("bundle_kind", expected_bundle_kind),
        ("required_suite_roles", list(expected_roles)),
    ):
        if registry.get(field) != expected:
            raise ValueError(f"formal suite registry {field} is inconsistent")

    builder_identity = _validate_registry_builder_identity(
        registry.get("registry_builder_identity"), registry_path=registry_path
    )
    _, data_version_manifest_identity = _verified_file_identity(
        registry.get("data_version_manifest"),
        declaring_file=registry_path,
        label="formal registry data_version_manifest",
        allowed_fields=frozenset({"path", "bytes", "sha256"}),
    )
    raw_anchor_catalog = registry.get("frontier_anchor_catalog")
    if not isinstance(raw_anchor_catalog, Mapping) or set(raw_anchor_catalog) != {
        "path",
        "bytes",
        "sha256",
        "count",
        "data_version",
        "evaluation_split",
    }:
        raise ValueError("formal registry frontier anchor identity is not frozen")
    anchor_path, anchor_identity = _verified_file_identity(
        {field: raw_anchor_catalog[field] for field in ("path", "bytes", "sha256")},
        declaring_file=registry_path,
        label="formal registry frontier_anchor_catalog",
        allowed_fields=frozenset({"path", "bytes", "sha256"}),
    )
    anchor_count = raw_anchor_catalog.get("count")
    if (
        type(anchor_count) is not int
        or anchor_count <= 0
        or len(pd.read_csv(anchor_path)) != anchor_count
        or raw_anchor_catalog.get("data_version") != primary_data_version
        or raw_anchor_catalog.get("evaluation_split") != "development_test"
    ):
        raise ValueError("formal registry frontier anchor catalog is inconsistent")
    frontier_anchor_identity = {
        **anchor_identity,
        "count": anchor_count,
        "data_version": raw_anchor_catalog["data_version"],
        "evaluation_split": raw_anchor_catalog["evaluation_split"],
    }
    raw_roster = registry.get("finalized_model_roster")
    if not isinstance(raw_roster, Mapping) or set(raw_roster) != {
        "path",
        "sha256",
        "selected_models",
        "proposed_decision",
    }:
        raise ValueError("formal suite registry roster identity is not frozen")
    roster_path = _repository_path(
        raw_roster.get("path"),
        declaring_file=registry_path,
        label="finalized_model_roster.path",
    )
    if not roster_path.is_file() or _file_sha256(roster_path) != raw_roster.get(
        "sha256"
    ):
        raise ValueError("finalized model roster hash is stale")
    roster_document = _read_mapping(roster_path)
    selected_models = raw_roster.get("selected_models")
    proposed_decision = raw_roster.get("proposed_decision")
    if (
        not isinstance(selected_models, list)
        or not selected_models
        or len(set(selected_models)) != len(selected_models)
        or roster_document.get("selected_models") != selected_models
        or roster_document.get("proposed_decision") != proposed_decision
    ):
        raise ValueError("finalized model roster selection fields are inconsistent")
    if proposed_decision not in {"include_proposed_formally", "framework_only"}:
        raise ValueError("finalized model roster has an unknown proposed decision")

    raw_sources = registry.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("formal suite registry requires source manifests")
    source_by_hash: dict[str, dict[str, Any]] = {}
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, Mapping) or set(raw_source) != {
            "suite",
            "run_directory",
            "manifest",
            "daily_predictions",
            "event_metrics",
            "models",
        }:
            raise ValueError("formal suite registry source fields are not frozen")
        models = raw_source.get("models")
        suite = raw_source.get("suite")
        if (
            not isinstance(suite, str)
            or not suite
            or not isinstance(models, list)
            or not models
            or len(set(models)) != len(models)
        ):
            raise ValueError("formal suite registry source suite/models are invalid")
        source_path, source_identity = _verified_file_identity(
            raw_source.get("manifest"),
            declaring_file=registry_path,
            label=f"formal registry source {index}",
            allowed_fields=frozenset({"path", "bytes", "sha256"}),
        )
        run_directory = _repository_path(
            raw_source.get("run_directory"),
            declaring_file=registry_path,
            label=f"formal registry source {index} run_directory",
        )
        if source_path.parent != run_directory:
            raise ValueError("formal registry source directory/manifest disagree")
        daily_path, daily_identity = _verified_file_identity(
            raw_source.get("daily_predictions"),
            declaring_file=registry_path,
            label=f"formal registry source {index} daily_predictions",
            allowed_fields=frozenset({"path", "bytes", "sha256"}),
        )
        event_path, event_identity = _verified_file_identity(
            raw_source.get("event_metrics"),
            declaring_file=registry_path,
            label=f"formal registry source {index} event_metrics",
            allowed_fields=frozenset({"path", "bytes", "sha256"}),
        )
        if daily_path != run_directory / "daily_predictions.parquet":
            raise ValueError(
                "formal registry source daily_predictions path is not canonical"
            )
        if event_path != run_directory / "event_metrics.parquet":
            raise ValueError(
                "formal registry source event_metrics path is not canonical"
            )
        source_manifest = _read_mapping(source_path)
        if (
            source_manifest.get("suite") != suite
            or source_manifest.get("models") != models
        ):
            raise ValueError("formal registry source manifest suite/models disagree")
        if source_identity["sha256"] in source_by_hash:
            raise ValueError("formal registry source manifests are duplicated")
        source_by_hash[source_identity["sha256"]] = {
            "suite": suite,
            "run_directory": str(run_directory),
            "manifest": source_identity,
            "daily_predictions": daily_identity,
            "event_metrics": event_identity,
            "models": list(models),
        }

    raw_roles = registry.get("suite_roles")
    if not isinstance(raw_roles, list) or len(raw_roles) != len(expected_roles):
        raise ValueError("formal suite registry role inventory is incomplete")
    roles: dict[str, dict[str, Any]] = {}
    for raw_role in raw_roles:
        if not isinstance(raw_role, Mapping) or set(raw_role) != {
            "role",
            "status",
            "reason",
            "manifest_suites",
            "source_manifest_sha256",
            "expected_models",
        }:
            raise ValueError("formal suite registry role fields are not frozen")
        role = raw_role.get("role")
        if not isinstance(role, str) or role in roles:
            raise ValueError("formal suite registry roles are missing or duplicated")
        roles[role] = dict(raw_role)
    if set(roles) != set(expected_roles):
        raise ValueError("formal suite registry roles differ from frozen requirements")
    allowed_not_applicable = (
        PROPOSED_PRIMARY_ROLES if expected_primary else PROPOSED_SENSITIVITY_ROLES
    )
    for role in expected_roles:
        item = roles[role]
        should_be_na = (
            proposed_decision == "framework_only" and role in allowed_not_applicable
        )
        if should_be_na:
            if item != {
                "role": role,
                "status": "not_applicable",
                "reason": "proposed_decision=framework_only",
                "manifest_suites": [],
                "source_manifest_sha256": [],
                "expected_models": [],
            }:
                raise ValueError(f"formal suite role {role} must be not_applicable")
            continue
        if item.get("status") != "complete" or item.get("reason") is not None:
            raise ValueError(f"formal suite role {role} is not complete")
        hashes = item.get("source_manifest_sha256")
        suites = item.get("manifest_suites")
        expected_models = item.get("expected_models")
        if (
            not isinstance(hashes, list)
            or not hashes
            or len(set(hashes)) != len(hashes)
            or not set(hashes).issubset(source_by_hash)
            or not isinstance(suites, list)
            or not suites
            or set(suites) != {source_by_hash[digest]["suite"] for digest in hashes}
            or not isinstance(expected_models, list)
            or not expected_models
            or len(set(expected_models)) != len(expected_models)
            or set(expected_models)
            != {
                model for digest in hashes for model in source_by_hash[digest]["models"]
            }
        ):
            raise ValueError(f"formal suite role {role} source binding is incomplete")

    registry_identity = {
        "schema_version": "analysis_registry_input_v1",
        "registry_file": registry_file,
        "registry_sha256": registry["registry_sha256"],
        "registry_builder_identity": builder_identity,
        "data_version_manifest": data_version_manifest_identity,
        "frontier_anchor_catalog": frontier_anchor_identity,
        "bundle_kind": expected_bundle_kind,
        "bundle_role": expected_bundle_role,
        "data_version": data_version,
        "evaluation_split": contract["evaluation_split"],
        "finalized_model_roster": {
            "path": str(roster_path),
            "sha256": raw_roster["sha256"],
            "selected_models": list(selected_models),
            "proposed_decision": proposed_decision,
        },
        "required_suite_roles": list(expected_roles),
        "suite_roles": [roles[role] for role in expected_roles],
        "source_manifests": [
            source_by_hash[digest] for digest in sorted(source_by_hash)
        ],
    }
    registry_identity["input_identity_sha256"] = _canonical_digest(registry_identity)
    return registry, registry_path, registry_identity


def load_frozen_inputs(
    predictions_path: str | Path,
    events_path: str | Path,
    manifest_path: str | Path,
    design_path: str | Path,
) -> FrozenInputs:
    """Validate hashes and contracts, then load the only analysable bundle."""

    predictions_file = Path(predictions_path).resolve()
    events_file = Path(events_path).resolve()
    manifest_file = Path(manifest_path).resolve()
    design_file = Path(design_path).resolve()
    manifest = _read_mapping(manifest_file)
    _validate_completion(manifest)
    statistics = load_frozen_statistics(design_file)
    contracts = _manifest_contracts(manifest)
    design = _read_mapping(design_file)
    for contract in contracts:
        expected_design_fields = {
            "design_version": str(design["design_version"]),
            "mask_schema_version": str(design["mask_design"]["schema_version"]),
            "model_schema_version": str(design["training"]["schema_version"]),
            "statistics_schema_version": str(design["statistics"]["schema_version"]),
        }
        mismatches = {
            field: (contract[field], expected)
            for field, expected in expected_design_fields.items()
            if contract[field] != expected
        }
        if mismatches:
            raise ValueError(
                f"evidence contract does not match the design freeze: {mismatches}"
            )
        if contract["evaluation_split"] == "test":
            raise ValueError(
                "stored split alias 'test' is not a canonical evidence label"
            )
        if contract["evaluation_split"] not in {
            "validation",
            "development_test",
            "confirmatory",
        }:
            raise ValueError("evidence contract has an unknown evaluation split")
        if contract["evaluation_split"] != "confirmatory":
            allowed_versions = set(design["data_versions"]["definitions"])
            if contract["data_version"] not in allowed_versions:
                raise ValueError("evidence contract uses an undeclared data version")
    registry, registry_path, registry_identity = _load_formal_registry(
        manifest,
        aggregate_manifest_path=manifest_file,
        contract=contracts[0],
        primary_data_version=statistics.primary_data_version,
    )
    for kind, path in (
        ("predictions", predictions_file),
        ("event_metrics", events_file),
    ):
        declared_hash = _artifact_hash(manifest, kind, path)
        if _file_sha256(path) != declared_hash:
            raise ValueError(f"{kind} content hash differs from the top manifest")

    predictions = _read_table(predictions_file)
    events = _read_table(events_file)
    prediction_count = manifest.get("prediction_rows", manifest.get("daily_rows"))
    event_count = manifest.get("event_rows")
    if not isinstance(prediction_count, int) or prediction_count != len(predictions):
        raise ValueError("prediction row count differs from the top manifest")
    if not isinstance(event_count, int) or event_count != len(events):
        raise ValueError("event row count differs from the top manifest")
    _validate_table_contract(predictions, contracts, context="frozen predictions")
    _validate_table_contract(events, contracts, context="frozen event metrics")
    for label, frame in (("predictions", predictions), ("event metrics", events)):
        if "model" in frame:
            legacy = set(frame["model"].dropna().astype(str).str.lower()) & {
                "brits",
                "saits",
            }
            if legacy:
                raise ValueError(
                    f"frozen {label} uses ambiguous legacy model names: {sorted(legacy)}"
                )
    return FrozenInputs(
        predictions,
        events,
        manifest,
        statistics,
        predictions_file,
        events_file,
        manifest_file,
        design_file,
        registry,
        registry_path,
        registry_identity,
    )


def load_frozen_inputs_from_manifest(
    manifest_path: str | Path,
    design_path: str | Path,
) -> FrozenInputs:
    """Resolve a v2 aggregate's prediction/event identities and validate it."""

    manifest_file = Path(manifest_path).resolve()
    manifest = _read_mapping(manifest_file)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise TypeError("top manifest artifacts must be a mapping")

    def artifact_path(name: str) -> Path:
        declaration = artifacts.get(name)
        if not isinstance(declaration, Mapping) or not isinstance(
            declaration.get("path"), str
        ):
            raise TypeError(f"top manifest lacks artifacts.{name}.path")
        path = Path(declaration["path"])
        if not path.is_absolute():
            path = manifest_file.parent / path
        return path.resolve()

    return load_frozen_inputs(
        artifact_path("predictions"),
        artifact_path("event_metrics"),
        manifest_file,
        design_path,
    )


def _strict_boolean(series: pd.Series, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    accepted = {True: True, False: False, "1": True, "0": False}
    mapped = series.map(accepted)
    if mapped.isna().any():
        raise ValueError(f"{name} must contain strict boolean values")
    return mapped.astype(bool)


def _year_column(frame: pd.DataFrame, *, context: str) -> pd.Series:
    for column in ("anchor_year", "year"):
        if column in frame:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            if numeric.notna().all() and np.isclose(numeric, np.round(numeric)).all():
                return numeric.astype(int)
    for column in ("center_date", "window_center_date", "date"):
        if column in frame:
            dates = pd.to_datetime(frame[column], errors="coerce")
            if dates.notna().all():
                return dates.dt.year.astype(int)
    raise ValueError(f"{context} requires an explicit finite anchor/episode year")


def _connected_components(
    nodes: Sequence[str], edges: Sequence[tuple[str, str]]
) -> dict[str, str]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    result: dict[str, str] = {}
    for root in sorted(nodes):
        if root in result:
            continue
        pending = [root]
        component: list[str] = []
        while pending:
            current = pending.pop()
            if current in result or current in component:
                continue
            component.append(current)
            pending.extend(sorted(adjacency[current], reverse=True))
        label = (
            "overlap:"
            + hashlib.sha256("|".join(sorted(component)).encode()).hexdigest()[:16]
        )
        result.update({node: label for node in component})
    return result


def audit_prediction_overlap(predictions: pd.DataFrame) -> OverlapArtifacts:
    """Audit anchor overlap from unique evaluated cells in the frozen daily table."""

    dense = (
        predictions.loc[
            predictions["experiment"].astype(str).str.upper().eq("SCI_DENSE")
        ].copy()
        if "experiment" in predictions
        else pd.DataFrame()
    )
    if dense.empty:
        return OverlapArtifacts(
            pd.DataFrame(
                columns=["left_anchor_id", "right_anchor_id", "temporal_jaccard"]
            ),
            pd.DataFrame(
                columns=["date", "anchors_covering_date", "unique_masked_cells"]
            ),
            pd.DataFrame(columns=["anchor_id", "effective_unique_masked_cells"]),
            pd.DataFrame(columns=["anchor_id", "overlap_cluster_id"]),
            {"status": "unavailable", "reason": "no SCI_DENSE predictions"},
        )
    required = [
        "date",
        "anchor_id",
        "station_id",
        "target",
        "data_version",
        "evaluation_split",
        "quality_approved",
        "artificial_mask",
    ]
    _require_columns(dense, required, "frontier overlap audit")
    usable = _strict_boolean(
        dense["quality_approved"], "quality_approved"
    ) & _strict_boolean(dense["artificial_mask"], "artificial_mask")
    dense = dense.loc[usable, required].copy()
    dense["date"] = pd.to_datetime(dense["date"], errors="coerce").dt.normalize()
    if dense["date"].isna().any() or dense["anchor_id"].isna().any():
        raise ValueError("frontier overlap audit requires finite dates and anchor IDs")
    context = ["data_version", "evaluation_split", "station_id", "target"]
    dense = dense.drop_duplicates([*context, "anchor_id", "date"])
    pair_rows: list[dict[str, Any]] = []
    date_rows: list[dict[str, Any]] = []
    replication_rows: list[dict[str, Any]] = []
    cluster_rows: list[dict[str, Any]] = []
    total_edges = 0
    for group_key, group in dense.groupby(
        context, dropna=False, observed=True, sort=True
    ):
        metadata = dict(zip(context, group_key, strict=True))
        by_anchor = {
            str(anchor): set(values["date"])
            for anchor, values in group.groupby("anchor_id", observed=True, sort=True)
        }
        edges: list[tuple[str, str]] = []
        for left, right in combinations(sorted(by_anchor), 2):
            intersection = by_anchor[left] & by_anchor[right]
            union = by_anchor[left] | by_anchor[right]
            if intersection:
                edges.append((left, right))
            pair_rows.append(
                {
                    **metadata,
                    "left_anchor_id": left,
                    "right_anchor_id": right,
                    "temporal_overlap_days": len(intersection),
                    "temporal_union_days": len(union),
                    "temporal_jaccard": len(intersection) / len(union)
                    if union
                    else 0.0,
                    "has_overlap": bool(intersection),
                }
            )
        total_edges += len(edges)
        assignments = _connected_components(sorted(by_anchor), edges)
        for anchor, cluster in sorted(assignments.items()):
            cluster_rows.append(
                {**metadata, "anchor_id": anchor, "overlap_cluster_id": cluster}
            )
        coverage_by_date: dict[pd.Timestamp, list[str]] = defaultdict(list)
        for anchor, dates in by_anchor.items():
            for date in dates:
                coverage_by_date[date].append(anchor)
        for date, anchors in sorted(coverage_by_date.items()):
            date_rows.append(
                {
                    **metadata,
                    "date": date,
                    "year": date.year,
                    "anchor_ids": json.dumps(sorted(anchors), separators=(",", ":")),
                    "anchors_covering_date": len(anchors),
                    "unique_masked_cells": 1,
                    "masked_cell_instances": len(anchors),
                    "effective_cell_replication": float(len(anchors)),
                    "temporal_overlap_flag": len(anchors) > 1,
                }
            )
        for anchor, dates in sorted(by_anchor.items()):
            effective = sum(1.0 / len(coverage_by_date[date]) for date in dates)
            replication_rows.append(
                {
                    **metadata,
                    "anchor_id": anchor,
                    "overlap_cluster_id": assignments[anchor],
                    "masked_cells": len(dates),
                    "effective_unique_masked_cells": effective,
                    "effective_replication_ratio": len(dates) / effective
                    if effective
                    else np.nan,
                    "overlaps_another_anchor": any(anchor in edge for edge in edges),
                }
            )
    pairwise = pd.DataFrame(pair_rows)
    dates = pd.DataFrame(date_rows)
    replication = pd.DataFrame(replication_rows)
    clusters = pd.DataFrame(cluster_rows)
    summary = {
        "status": "ok",
        "audit_unit": "unique evaluated station-target-date cell per frozen anchor",
        "n_anchors": len(clusters),
        "n_overlap_edges": int(total_edges),
        "n_overlap_clusters": int(clusters["overlap_cluster_id"].nunique()),
        "n_unique_masked_cells": len(dates),
        "anchors_not_assumed_independent": bool(total_edges),
    }
    return OverlapArtifacts(pairwise, dates, replication, clusters, summary)


def guarded_model_skill(
    events: pd.DataFrame,
    denominator_guard: Mapping[str, Any],
    *,
    baseline_model: str = "climatology",
) -> pd.DataFrame:
    """Pair MAE in model/anchor order, then apply the frozen target-unit guard."""

    required = ["experiment", "scenario_id", "station_id", "target", "model", "MAE"]
    _require_columns(events, required, "guarded model skill")
    data = events.copy()
    data["MAE"] = pd.to_numeric(data["MAE"], errors="coerce")
    unit_cols = [
        column
        for column in (
            "design_hash",
            "data_version",
            "evaluation_split",
            "experiment",
            "scenario_id",
            "condition_id",
            "mask_seed",
            "anchor_id",
            "station_id",
            "target",
            "gap_length",
            "target_gap_id",
            "failed_stations",
            "information_combination",
        )
        if column in data
    ]
    baseline = data.loc[
        data["model"].astype(str).eq(baseline_model), [*unit_cols, "MAE"]
    ]
    if baseline.empty:
        raise ValueError(f"guarded skill requires baseline model {baseline_model!r}")
    variability = baseline.groupby(unit_cols, dropna=False, observed=True)["MAE"].agg(
        ["min", "max"]
    )
    if ((variability["max"] - variability["min"]).abs() > 1e-10).any():
        raise ValueError("climatology MAE varies within a model-comparison unit")
    baseline = (
        baseline.groupby(unit_cols, dropna=False, observed=True)["MAE"]
        .mean()
        .rename("climatology_mae")
        .reset_index()
    )
    merged = data.merge(baseline, on=unit_cols, how="left", validate="many_to_one")
    if merged["climatology_mae"].isna().any():
        missing = int(merged["climatology_mae"].isna().sum())
        raise ValueError(f"{missing} model rows have no paired climatology denominator")
    parts: list[pd.DataFrame] = []
    for target, group in merged.groupby(
        "target", dropna=False, observed=True, sort=True
    ):
        threshold = resolve_climatology_denominator_threshold(
            denominator_guard, str(target)
        )
        prepared = group.rename(columns={"MAE": "model_mae"})
        guarded = add_guarded_climatology_skill(
            prepared,
            near_zero_threshold=threshold,
        ).rename(columns={"model_mae": "MAE"})
        parts.append(guarded)
    return pd.concat(parts, ignore_index=True) if parts else merged.assign(skill=np.nan)


def one_hinge_breakpoint(
    gaps: Sequence[float],
    values: Sequence[float],
    weights: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Fit the frozen continuous one-internal-hinge weighted least-squares model."""

    x = np.asarray(gaps, dtype=float)
    y = np.asarray(values, dtype=float)
    w = (
        np.ones(len(x), dtype=float)
        if weights is None
        else np.asarray(weights, dtype=float)
    )
    usable = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[usable], y[usable], w[usable]
    order = np.argsort(x, kind="stable")
    x, y, w = x[order], y[order], w[order]
    if len(np.unique(x)) < 5:
        return {
            "breakpoint_days": np.nan,
            "weighted_sse": np.nan,
            "left_slope": np.nan,
            "right_slope": np.nan,
            "reason": "at least five distinct gap lengths are required",
        }
    candidates = np.unique(x)[1:-1]
    best: tuple[float, float, np.ndarray] | None = None
    root_w = np.sqrt(w)
    for hinge in candidates:
        design = np.column_stack([np.ones(len(x)), x, np.maximum(0.0, x - hinge)])
        coefficients, *_ = np.linalg.lstsq(
            design * root_w[:, None], y * root_w, rcond=None
        )
        residual = y - design @ coefficients
        sse = float(np.sum(w * residual**2))
        candidate = (sse, float(hinge), coefficients)
        if best is None or candidate[0] < best[0] - 1e-15:
            best = candidate
    assert best is not None
    return {
        "breakpoint_days": best[1],
        "weighted_sse": best[0],
        "left_slope": float(best[2][1]),
        "right_slope": float(best[2][1] + best[2][2]),
        "reason": None,
    }


def _wilcoxon_p(values: Sequence[float]) -> float:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    if not len(data):
        return np.nan
    if np.allclose(data, 0.0):
        return 1.0
    try:
        return float(wilcoxon(data, alternative="two-sided", method="auto").pvalue)
    except ValueError:
        return np.nan


def _bootstrap_difference(
    units: pd.DataFrame,
    *,
    value_col: str,
    n_boot: int,
    confidence: float,
    seed: int,
) -> tuple[float, float]:
    if len(units) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    strata = [
        group[value_col].to_numpy(dtype=float)
        for _, group in units.groupby(
            ["station_id", "year"], dropna=False, observed=True, sort=True
        )
    ]
    draws = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        sampled = [
            values[rng.integers(0, len(values), size=len(values))] for values in strata
        ]
        draws[index] = float(np.mean(np.concatenate(sampled)))
    alpha = (1.0 - confidence) / 2.0
    return float(np.quantile(draws, alpha)), float(np.quantile(draws, 1.0 - alpha))


def _frontier_ci(
    samples: pd.DataFrame, column: str, confidence: float
) -> dict[str, Any]:
    if samples.empty or column not in samples:
        return {
            f"{column}_ci_lower": np.nan,
            f"{column}_ci_upper": np.nan,
            f"{column}_finite_bootstrap": 0,
            f"{column}_left_censored_bootstrap": 0,
            f"{column}_right_censored_bootstrap": 0,
        }
    one_per_draw = samples.drop_duplicates("bootstrap_id")
    values = pd.to_numeric(one_per_draw[column], errors="coerce").to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    alpha = (1.0 - confidence) / 2.0
    censor_col = column.replace("_days", "_censoring")
    censor = (
        one_per_draw[censor_col].astype("string")
        if censor_col in one_per_draw
        else pd.Series(dtype="string")
    )
    return {
        f"{column}_ci_lower": float(np.quantile(finite, alpha))
        if len(finite)
        else np.nan,
        f"{column}_ci_upper": float(np.quantile(finite, 1.0 - alpha))
        if len(finite)
        else np.nan,
        f"{column}_finite_bootstrap": len(finite),
        f"{column}_left_censored_bootstrap": int(censor.eq("left").sum()),
        f"{column}_right_censored_bootstrap": int(censor.eq("right").sum()),
    }


def analyze_frontiers(
    events: pd.DataFrame,
    overlap: OverlapArtifacts,
    statistics: FrozenStatistics,
) -> FrontierArtifacts:
    """Build raw, monotone, statistical, and withheld application frontiers."""

    dense = (
        events.loc[events["experiment"].astype(str).str.upper().eq("SCI_DENSE")].copy()
        if "experiment" in events
        else pd.DataFrame()
    )
    if dense.empty:
        empty = pd.DataFrame()
        return FrontierArtifacts(empty, empty, empty, empty, empty, empty)
    _require_columns(
        dense, ["anchor_id", "gap_length", "window_length"], "frontier analysis"
    )
    dense = guarded_model_skill(dense, statistics.denominator_guard)
    dense["year"] = _year_column(dense, context="frontier analysis")
    dense["window"] = pd.to_numeric(dense["window_length"], errors="coerce")
    if "information_combination" not in dense:
        dense["information_combination"] = "full_information"
    else:
        dense["information_combination"] = dense["information_combination"].fillna(
            "full_information"
        )
    cluster_keys = [
        "data_version",
        "evaluation_split",
        "station_id",
        "target",
        "anchor_id",
    ]
    _require_columns(
        overlap.clusters,
        [*cluster_keys, "overlap_cluster_id"],
        "frontier overlap clusters",
    )
    dense = dense.merge(
        overlap.clusters.loc[
            :, [*cluster_keys, "overlap_cluster_id"]
        ].drop_duplicates(),
        on=cluster_keys,
        how="left",
        validate="many_to_one",
    )
    if dense["overlap_cluster_id"].isna().any():
        raise ValueError("frontier rows are missing overlap-cluster assignments")

    results = []
    for target, target_rows in dense.groupby("target", observed=True, sort=True):
        normalized = str(target).upper().split("_")[-1]
        required_gaps = (
            statistics.dense_t_gaps if normalized == "T" else statistics.dense_fl_gaps
        )
        results.append(
            anchor_year_frontier_bootstrap(
                target_rows,
                value_col="skill",
                group_cols=FRONTIER_GROUPS,
                overlap_cluster_col="overlap_cluster_id",
                required_gap_lengths=required_gaps,
                n_boot=statistics.bootstrap_replicates,
                confidence=statistics.confidence,
                seed=statistics.bootstrap_seed,
            )
        )
    curve = pd.concat([result.curve for result in results], ignore_index=True)
    collapsed = pd.concat([result.collapsed for result in results], ignore_index=True)
    samples = pd.concat([result.samples for result in results], ignore_index=True)
    summaries = pd.concat([result.summary for result in results], ignore_index=True)

    if not samples.empty:
        alpha = (1.0 - statistics.confidence) / 2.0
        monotone_intervals = (
            samples.groupby(
                [*FRONTIER_GROUPS, "gap_length"],
                dropna=False,
                observed=True,
                sort=True,
            )["bootstrap_monotone_value"]
            .agg(
                monotone_bootstrap_ci_lower=lambda values: float(
                    np.quantile(values, alpha)
                ),
                monotone_bootstrap_ci_upper=lambda values: float(
                    np.quantile(values, 1.0 - alpha)
                ),
            )
            .reset_index()
        )
        curve = curve.merge(
            monotone_intervals,
            on=[*FRONTIER_GROUPS, "gap_length"],
            how="left",
            validate="one_to_one",
        )
    else:
        curve["monotone_bootstrap_ci_lower"] = np.nan
        curve["monotone_bootstrap_ci_upper"] = np.nan

    raw = curve.copy()
    raw["frontier_value"] = raw["raw_frontier_value"]
    raw["frontier_value_ci_lower"] = raw["bootstrap_ci_lower"]
    raw["frontier_value_ci_upper"] = raw["bootstrap_ci_upper"]
    raw["curve_type"] = "raw"
    monotone = curve.copy()
    monotone["frontier_value"] = monotone["monotone_frontier_value"]
    monotone["frontier_value_ci_lower"] = monotone["monotone_bootstrap_ci_lower"]
    monotone["frontier_value_ci_upper"] = monotone["monotone_bootstrap_ci_upper"]
    monotone["curve_type"] = "weighted_pava_nonincreasing"

    breakpoint_rows: list[dict[str, Any]] = []
    statistical_rows: list[dict[str, Any]] = []
    application_rows: list[dict[str, Any]] = []
    for group_key, group in curve.groupby(
        list(FRONTIER_GROUPS), dropna=False, observed=True, sort=True
    ):
        metadata = dict(zip(FRONTIER_GROUPS, group_key, strict=True))
        summary_match = summaries.copy()
        sample_match = samples.copy()
        collapsed_match = collapsed.copy()
        for column, value in metadata.items():
            summary_match = summary_match.loc[summary_match[column].eq(value)]
            sample_match = sample_match.loc[sample_match[column].eq(value)]
            collapsed_match = collapsed_match.loc[collapsed_match[column].eq(value)]
        weights = pd.to_numeric(group["n_complete_anchor_curves"], errors="coerce")
        for curve_type, value_col in (
            ("raw", "raw_frontier_value"),
            ("weighted_pava_nonincreasing", "monotone_frontier_value"),
        ):
            estimate = one_hinge_breakpoint(
                group["gap_length"], group[value_col], weights
            )
            breakpoint_rows.append(
                {
                    **metadata,
                    "curve_type": curve_type,
                    **estimate,
                    "breakpoint_reason": estimate["reason"],
                }
            )

        summary = summary_match.iloc[0].to_dict() if len(summary_match) else metadata
        lower_curve = group.dropna(subset=["monotone_bootstrap_ci_lower"])
        if lower_curve.empty:
            confidence_frontier = {
                "monotone_frontier_days": np.nan,
                "monotone_frontier_censoring": None,
                "monotone_frontier_status": "bootstrap_confidence_curve_unavailable",
            }
        else:
            lower = raw_and_monotone_frontier(
                lower_curve.rename(
                    columns={"monotone_bootstrap_ci_lower": "lower_skill"}
                ),
                value_col="lower_skill",
                group_cols=(),
                threshold=0.0,
            )
            confidence_frontier = lower.summary.iloc[0].to_dict()
        raw_ci = _frontier_ci(sample_match, "raw_frontier_days", statistics.confidence)
        monotone_ci = _frontier_ci(
            sample_match, "monotone_frontier_days", statistics.confidence
        )
        complete_skill = collapsed_match.loc[
            collapsed_match["frontier_complete_curve"].fillna(False)
        ]
        cluster_skill = complete_skill.groupby(
            "overlap_cluster_id", dropna=False, observed=True
        )["skill"].mean()
        p_value = _wilcoxon_p(cluster_skill)
        breakpoint = next(
            row
            for row in breakpoint_rows
            if row["curve_type"] == "weighted_pava_nonincreasing"
            and all(row[column] == value for column, value in metadata.items())
        )
        statistical_rows.append(
            {
                **summary,
                "statistical_frontier_days": confidence_frontier.get(
                    "monotone_frontier_days"
                ),
                "statistical_frontier_censoring": confidence_frontier.get(
                    "monotone_frontier_censoring"
                ),
                "statistical_frontier_status": confidence_frontier.get(
                    "monotone_frontier_status"
                ),
                **raw_ci,
                **monotone_ci,
                "breakpoint_days": breakpoint["breakpoint_days"],
                "breakpoint_reason": breakpoint["reason"],
                "n_anchors": int(collapsed_match["anchor_id"].nunique()),
                "n_years": int(collapsed_match["year"].nunique()),
                "p_value": p_value,
                "n_hypothesis_clusters": len(cluster_skill),
                "hypothesis_estimand": (
                    "mean_skill_across_predeclared_gaps_per_overlap_cluster"
                ),
                "hypothesis_family": "frontier_model_vs_climatology",
                "training_seeds_collapsed_first": True,
            }
        )
        application_rows.append(
            {
                **metadata,
                **assess_application_boundary(group, statistics.application_criteria),
                "n_anchors": int(collapsed_match["anchor_id"].nunique()),
                "n_years": int(collapsed_match["year"].nunique()),
            }
        )
    statistical = pd.DataFrame(statistical_rows)
    if not statistical.empty:
        statistical = benjamini_hochberg_by_family(statistical)

        common = [*FRONTIER_GROUPS]
        raw_boundaries = statistical.loc[
            :,
            [
                *common,
                "raw_frontier_days",
                "raw_frontier_censoring",
                "raw_frontier_days_ci_lower",
                "raw_frontier_days_ci_upper",
                "n_anchors",
                "n_years",
            ],
        ].rename(
            columns={
                "raw_frontier_days": "boundary_days",
                "raw_frontier_censoring": "boundary_censoring",
                "raw_frontier_days_ci_lower": "boundary_ci_lower",
                "raw_frontier_days_ci_upper": "boundary_ci_upper",
            }
        )
        monotone_boundaries = statistical.loc[
            :,
            [
                *common,
                "monotone_frontier_days",
                "monotone_frontier_censoring",
                "monotone_frontier_days_ci_lower",
                "monotone_frontier_days_ci_upper",
                "n_anchors",
                "n_years",
            ],
        ].rename(
            columns={
                "monotone_frontier_days": "boundary_days",
                "monotone_frontier_censoring": "boundary_censoring",
                "monotone_frontier_days_ci_lower": "boundary_ci_lower",
                "monotone_frontier_days_ci_upper": "boundary_ci_upper",
            }
        )
        breakpoint_frame = pd.DataFrame(breakpoint_rows)
        raw_breakpoints = breakpoint_frame.loc[
            breakpoint_frame["curve_type"].eq("raw"),
            [*common, "breakpoint_days", "breakpoint_reason"],
        ]
        monotone_breakpoints = breakpoint_frame.loc[
            breakpoint_frame["curve_type"].eq("weighted_pava_nonincreasing"),
            [*common, "breakpoint_days", "breakpoint_reason"],
        ]
        raw = raw.merge(raw_boundaries, on=common, validate="many_to_one").merge(
            raw_breakpoints, on=common, validate="many_to_one"
        )
        monotone = monotone.merge(
            monotone_boundaries, on=common, validate="many_to_one"
        ).merge(monotone_breakpoints, on=common, validate="many_to_one")
        application = pd.DataFrame(application_rows).merge(
            statistical.loc[
                :,
                [
                    *common,
                    "statistical_frontier_days",
                    "statistical_frontier_censoring",
                    "monotone_frontier_days_ci_lower",
                    "monotone_frontier_days_ci_upper",
                    "breakpoint_days",
                ],
            ],
            on=common,
            how="left",
            validate="one_to_one",
        )
        breakpoint_frame = breakpoint_frame.merge(
            pd.concat(
                [
                    raw_boundaries.assign(curve_type="raw"),
                    monotone_boundaries.assign(
                        curve_type="weighted_pava_nonincreasing"
                    ),
                ],
                ignore_index=True,
            ),
            on=[*common, "curve_type"],
            how="left",
            validate="one_to_one",
        )
    else:
        application = pd.DataFrame(application_rows)
        breakpoint_frame = pd.DataFrame(breakpoint_rows)
    return FrontierArtifacts(
        raw,
        monotone,
        statistical,
        application,
        breakpoint_frame,
        samples,
    )


def _normalize_information_estimand(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.strip().str.lower()
    aliases = {
        "operational": "operational_dropout",
        "shared_checkpoint": "operational_dropout",
        "operational_dropout": "operational_dropout",
        "retrained": "retrained_upper_bound",
        "retrained_upper_bound": "retrained_upper_bound",
    }
    normalized = result.map(aliases)
    if normalized.isna().any():
        raise ValueError(
            "unknown information estimand; operational and retrained may not be pooled"
        )
    return normalized


def _information_estimand(frame: pd.DataFrame) -> pd.Series:
    declared = [
        column
        for column in ("information_estimand", "component_estimand")
        if column in frame
    ]
    if not declared:
        raise ValueError(
            "information rows require an explicit operational/retrained estimand"
        )
    normalized = _normalize_information_estimand(frame[declared[0]])
    for alias_column in declared[1:]:
        alias = _normalize_information_estimand(frame[alias_column])
        if not alias.equals(normalized):
            raise ValueError(
                "information_estimand and component_estimand mix incompatible estimands"
            )
    return normalized


def _validate_information_coalitions(
    frame: pd.DataFrame,
    *,
    unit_cols: Sequence[str],
) -> None:
    """Require each seed-level estimand unit to have its exact frozen coalition set."""

    _require_columns(
        frame,
        [
            *unit_cols,
            "training_seed",
            "information_estimand",
            "information_combination",
        ],
        "information coalition contract",
    )
    numeric_seed = pd.to_numeric(frame["training_seed"], errors="coerce")
    if (
        numeric_seed.isna().any()
        or not np.isfinite(numeric_seed).all()
        or not np.isclose(numeric_seed, np.round(numeric_seed)).all()
    ):
        raise ValueError(
            "information coalition units require finite integer training seeds"
        )

    mixed_unit_cols = [
        column
        for column in unit_cols
        if column not in {"information_estimand", "information_combination"}
    ]
    mixed = frame.groupby(
        [*mixed_unit_cols, "training_seed"],
        dropna=False,
        observed=True,
        sort=True,
    )["information_estimand"].nunique(dropna=False)
    if mixed.gt(1).any():
        raise ValueError(
            "one information unit mixes operational and retrained estimands"
        )

    contract_unit_cols = [
        column for column in unit_cols if column != "information_combination"
    ]
    for key, group in frame.groupby(
        [*contract_unit_cols, "training_seed"],
        dropna=False,
        observed=True,
        sort=True,
    ):
        key_tuple = key if isinstance(key, tuple) else (key,)
        metadata = dict(
            zip([*contract_unit_cols, "training_seed"], key_tuple, strict=True)
        )
        estimand = str(metadata["information_estimand"])
        expected = (
            set(OPERATIONAL_INFORMATION_COMBINATIONS)
            if estimand == "operational_dropout"
            else set(RETRAINED_INFORMATION_COMBINATIONS)
        )
        observed = group["information_combination"].map(normalize_combination)
        counts = observed.value_counts()
        observed_set = set(observed)
        missing = sorted(
            combination_label(value) for value in expected.difference(observed_set)
        )
        extra = sorted(
            combination_label(value) for value in observed_set.difference(expected)
        )
        duplicates = sorted(
            combination_label(value) for value, count in counts.items() if count != 1
        )
        if missing or extra or duplicates or len(group) != len(expected):
            expected_count = len(expected)
            raise ValueError(
                f"{estimand} requires exactly {expected_count} coalitions per "
                f"training-seed unit; missing={missing}, extra={extra}, "
                f"duplicates={duplicates}"
            )


def _retrained_upper_bound_units(
    collapsed: pd.DataFrame,
    *,
    value_unit_cols: Sequence[str],
) -> pd.DataFrame:
    """Contrast every declared retrained coalition with its retrained S0 fit."""

    if collapsed.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for key, group in collapsed.groupby(
        list(value_unit_cols), dropna=False, observed=True, sort=True
    ):
        metadata = dict(
            zip(
                value_unit_cols,
                key if isinstance(key, tuple) else (key,),
                strict=True,
            )
        )
        mapping = {
            normalize_combination(label): float(mae)
            for label, mae in group[["information_combination", "MAE"]].itertuples(
                index=False, name=None
            )
        }
        if set(mapping) != set(RETRAINED_INFORMATION_COMBINATIONS):
            raise ValueError(
                "retrained upper-bound unit violates its 9-coalition contract"
            )
        baseline = mapping[frozenset()]
        if not np.isfinite(list(mapping.values())).all():
            raise ValueError("retrained upper-bound coalitions require finite MAE")
        for coalition in RETRAINED_INFORMATION_COMBINATIONS[1:]:
            coalition_mae = mapping[coalition]
            gain = baseline - coalition_mae
            rows.append(
                {
                    **metadata,
                    "information_combination": combination_label(coalition),
                    "reference_information_combination": "S0",
                    "source": "+".join(
                        source for source in INFORMATION_SOURCES if source in coalition
                    ),
                    "contrast_type": "declared_retrained_coalition_vs_retrained_S0",
                    "coalition_MAE": coalition_mae,
                    "reference_MAE": baseline,
                    "MAE_gain_vs_S0": gain,
                    "relative_MAE_gain_vs_S0": (
                        gain / abs(baseline) if baseline != 0 else np.nan
                    ),
                    "training_seeds_collapsed_first": True,
                }
            )
    return pd.DataFrame(rows)


def _seed_collapse(
    frame: pd.DataFrame,
    *,
    unit_cols: Sequence[str],
    value_cols: Sequence[str],
) -> pd.DataFrame:
    _require_columns(frame, [*unit_cols, "training_seed", *value_cols], "seed collapse")
    data = frame.copy()
    for column in value_cols:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    within = (
        data.groupby(
            [*unit_cols, "training_seed"], dropna=False, observed=True, sort=True
        )[list(value_cols)]
        .mean()
        .reset_index()
    )
    values = (
        within.groupby(list(unit_cols), dropna=False, observed=True, sort=True)[
            list(value_cols)
        ]
        .mean()
        .reset_index()
    )
    counts = (
        within.groupby(list(unit_cols), dropna=False, observed=True, sort=True)[
            "training_seed"
        ]
        .nunique(dropna=True)
        .rename("n_training_seeds")
        .reset_index()
    )
    result = values.merge(counts, on=list(unit_cols), validate="one_to_one")
    result["training_seeds_collapsed_first"] = True
    return result


def _summarize_unit_values(
    frame: pd.DataFrame,
    *,
    group_cols: Sequence[str],
    value_cols: Sequence[str],
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_cols, *value_cols, "n_units"])
    active = [column for column in group_cols if column in frame]
    summary = (
        frame.groupby(active, dropna=False, observed=True, sort=True)[list(value_cols)]
        .mean()
        .reset_index()
    )
    counts = (
        frame.groupby(active, dropna=False, observed=True)
        .size()
        .rename("n_units")
        .reset_index()
    )
    return summary.merge(counts, on=active, validate="one_to_one")


def analyze_information(
    events: pd.DataFrame,
    statistics: FrozenStatistics,
) -> dict[str, pd.DataFrame]:
    """Analyse the distinct frozen operational-16 and retrained-9 estimands."""

    if "information_combination" not in events:
        return {
            "metrics": pd.DataFrame(),
            "operational": pd.DataFrame(),
            "retrained": pd.DataFrame(),
            "shapley": pd.DataFrame(),
            "interactions": pd.DataFrame(),
            "hypotheses": pd.DataFrame(),
        }
    info = events.loc[events["information_combination"].notna()].copy()
    if info.empty:
        return {
            "metrics": pd.DataFrame(),
            "operational": pd.DataFrame(),
            "retrained": pd.DataFrame(),
            "shapley": pd.DataFrame(),
            "interactions": pd.DataFrame(),
            "hypotheses": pd.DataFrame(),
        }
    _require_columns(
        info, ["scenario_id", "training_seed", "MAE", "model"], "information analysis"
    )
    info["MAE"] = pd.to_numeric(info["MAE"], errors="coerce")
    if info["MAE"].isna().any() or not np.isfinite(info["MAE"]).all():
        raise ValueError("information coalition units require finite MAE")
    info["information_estimand"] = _information_estimand(info)
    info["information_combination"] = info["information_combination"].map(
        combination_label
    )
    info["year"] = _year_column(info, context="information analysis")
    if "window" not in info:
        info["window"] = info.get("window_length", np.nan)
    unit_cols = [
        column
        for column in (
            "design_hash",
            "data_version",
            "evaluation_split",
            "experiment",
            "scenario_id",
            "anchor_id",
            "mask_seed",
            "station_id",
            "target",
            "gap_length",
            "window",
            "model",
            "information_estimand",
            "year",
            "information_combination",
        )
        if column in info
    ]
    _validate_information_coalitions(info, unit_cols=unit_cols)
    collapsed = _seed_collapse(info, unit_cols=unit_cols, value_cols=("MAE",))
    value_unit_cols = [
        column for column in unit_cols if column != "information_combination"
    ]
    collapsed["training_seed"] = "seed_collapsed"
    metric_groups = [
        "station_id",
        "target",
        "data_version",
        "model",
        "information_estimand",
        "information_combination",
        "gap_length",
        "window",
        "evaluation_split",
    ]
    metrics = _summarize_unit_values(
        collapsed,
        group_cols=metric_groups,
        value_cols=("MAE",),
    )
    metrics["training_seeds_collapsed_first"] = True

    operational_collapsed = collapsed.loc[
        collapsed["information_estimand"].eq("operational_dropout")
    ].copy()
    retrained_collapsed = collapsed.loc[
        collapsed["information_estimand"].eq("retrained_upper_bound")
    ].copy()
    operational_values = (
        build_value_function(
            operational_collapsed,
            metric="MAE",
            group_cols=value_unit_cols,
        )
        if not operational_collapsed.empty
        else pd.DataFrame()
    )
    shapley_units = (
        shapley_table(operational_values, group_cols=value_unit_cols)
        if not operational_values.empty
        else pd.DataFrame()
    )
    operational_gain_units = (
        compensation_gains(operational_values, group_cols=value_unit_cols)
        if not operational_values.empty
        else pd.DataFrame()
    )
    summary_groups = [
        "station_id",
        "target",
        "data_version",
        "model",
        "information_estimand",
        "gap_length",
        "window",
        "evaluation_split",
        "source",
    ]
    shapley = _summarize_unit_values(
        shapley_units.loc[~shapley_units["excluded"]]
        if not shapley_units.empty
        else shapley_units,
        group_cols=summary_groups,
        value_cols=(
            "shapley",
            "baseline_value",
            "full_value",
            "total_gain",
            "efficiency_residual",
        ),
    )
    operational = _summarize_unit_values(
        operational_gain_units.loc[~operational_gain_units["excluded"]]
        if not operational_gain_units.empty
        else operational_gain_units,
        group_cols=summary_groups,
        value_cols=(
            "full_removal_gain",
            "mean_marginal_gain",
            "mean_relative_compensation",
        ),
    )
    operational_hypothesis_rows: list[dict[str, Any]] = []
    active_summary_groups = [
        column for column in summary_groups if column in operational_gain_units
    ]
    if not operational_gain_units.empty:
        for key, group in operational_gain_units.loc[
            ~operational_gain_units["excluded"]
        ].groupby(active_summary_groups, dropna=False, observed=True, sort=True):
            metadata = dict(
                zip(
                    active_summary_groups,
                    key if isinstance(key, tuple) else (key,),
                    strict=True,
                )
            )
            operational_hypothesis_rows.append(
                {
                    **metadata,
                    "estimate": float(group["full_removal_gain"].mean()),
                    "p_value": _wilcoxon_p(group["full_removal_gain"]),
                    "n_anchor_units": len(group),
                    "hypothesis_family": "operational_information_dropout",
                }
            )

    retrained_units = _retrained_upper_bound_units(
        retrained_collapsed,
        value_unit_cols=value_unit_cols,
    )
    retrained_groups = [
        "station_id",
        "target",
        "data_version",
        "model",
        "information_estimand",
        "gap_length",
        "window",
        "evaluation_split",
        "information_combination",
        "reference_information_combination",
        "source",
        "contrast_type",
    ]
    retrained = _summarize_unit_values(
        retrained_units,
        group_cols=retrained_groups,
        value_cols=(
            "coalition_MAE",
            "reference_MAE",
            "MAE_gain_vs_S0",
            "relative_MAE_gain_vs_S0",
        ),
    )
    retrained_hypothesis_rows: list[dict[str, Any]] = []
    active_retrained_groups = [
        column for column in retrained_groups if column in retrained_units
    ]
    if not retrained_units.empty:
        for key, group in retrained_units.groupby(
            active_retrained_groups, dropna=False, observed=True, sort=True
        ):
            metadata = dict(
                zip(
                    active_retrained_groups,
                    key if isinstance(key, tuple) else (key,),
                    strict=True,
                )
            )
            retrained_hypothesis_rows.append(
                {
                    **metadata,
                    "estimate": float(group["MAE_gain_vs_S0"].mean()),
                    "p_value": _wilcoxon_p(group["MAE_gain_vs_S0"]),
                    "n_anchor_units": len(group),
                    "hypothesis_family": "retrained_information_upper_bound",
                }
            )
    hypotheses = pd.DataFrame(
        [*operational_hypothesis_rows, *retrained_hypothesis_rows]
    )
    if not hypotheses.empty:
        hypotheses = benjamini_hochberg_by_family(hypotheses)
    if operational_hypothesis_rows:
        merge_cols = [*active_summary_groups]
        operational = operational.merge(
            hypotheses.loc[
                hypotheses["hypothesis_family"].eq("operational_information_dropout"),
                [*merge_cols, "p_value", "p_bh", "bh_reject", "hypothesis_family"],
            ],
            on=merge_cols,
            how="left",
            validate="one_to_one",
        )
    if retrained_hypothesis_rows:
        retrained = retrained.merge(
            hypotheses.loc[
                hypotheses["hypothesis_family"].eq("retrained_information_upper_bound"),
                [
                    *active_retrained_groups,
                    "p_value",
                    "p_bh",
                    "bh_reject",
                    "hypothesis_family",
                ],
            ],
            on=active_retrained_groups,
            how="left",
            validate="one_to_one",
        )

    interaction_rows: list[dict[str, Any]] = []
    operational_groups = (
        operational_values.groupby(
            value_unit_cols, dropna=False, observed=True, sort=True
        )
        if not operational_values.empty
        else ()
    )
    for key, unit in operational_groups:
        metadata = dict(
            zip(value_unit_cols, key if isinstance(key, tuple) else (key,), strict=True)
        )
        if "reason" in unit and unit["reason"].notna().any():
            continue
        mapping = {
            normalize_combination(label): float(value)
            for label, value in unit[["combination", "value"]].itertuples(
                index=False, name=None
            )
        }
        if set(mapping) != set(information_combinations()):
            continue
        for left, right in combinations(INFORMATION_SOURCES, 2):
            interaction_rows.append(
                {
                    **metadata,
                    "source_left": left,
                    "source_right": right,
                    "interaction": mapping[frozenset({left, right})]
                    - mapping[frozenset({left})]
                    - mapping[frozenset({right})]
                    + mapping[frozenset()],
                }
            )
    interactions = _summarize_unit_values(
        pd.DataFrame(interaction_rows),
        group_cols=[
            "station_id",
            "target",
            "data_version",
            "model",
            "information_estimand",
            "gap_length",
            "window",
            "evaluation_split",
            "source_left",
            "source_right",
        ],
        value_cols=("interaction",),
    )
    return {
        "metrics": metrics,
        "operational": operational,
        "retrained": retrained,
        "shapley": shapley,
        "interactions": interactions,
        "hypotheses": hypotheses,
    }


def analyze_resilience_outputs(
    events: pd.DataFrame,
    statistics: FrozenStatistics,
) -> dict[str, pd.DataFrame]:
    """Collapse seeds, require each failure powerset, and estimate network resilience."""

    network = (
        events.loc[events["experiment"].astype(str).str.upper().eq("SCI_NET")].copy()
        if "experiment" in events
        else pd.DataFrame()
    )
    if network.empty:
        return {
            name: pd.DataFrame()
            for name in ("curves", "importance", "failure_sets", "auc", "hypotheses")
        }
    network = guarded_model_skill(network, statistics.denominator_guard)
    network["year"] = _year_column(network, context="network resilience")
    value_cols = ("MAE", "skill")
    unit_cols = [
        column
        for column in (
            *RESILIENCE_GROUP_COLUMNS,
            "design_hash",
            "data_version",
            "target_gap_id",
            "mask_seed",
            "failed_stations",
            "failed_station_ids",
            "failure_count",
            "network_size",
            "year",
        )
        if column in network
    ]
    collapsed = _seed_collapse(network, unit_cols=unit_cols, value_cols=value_cols)
    collapsed["training_seed"] = "seed_collapsed"
    complete, exclusions = complete_resilience_units(
        collapsed,
        value_cols=value_cols,
    )
    if not exclusions.empty:
        reason = (
            exclusions["reason"].iloc[0]
            if "reason" in exclusions and len(exclusions)
            else "incomplete failure powerset"
        )
        raise ValueError(f"frozen SCI_NET suite is incomplete: {reason}")
    if complete.empty:
        raise ValueError("frozen SCI_NET suite is incomplete: no failure powersets")
    if "failure_count" in complete:
        declared_failure_count = pd.to_numeric(
            complete["failure_count"], errors="coerce"
        )
        if (
            declared_failure_count.isna().any()
            or not declared_failure_count.eq(complete["failed_count"]).all()
        ):
            raise ValueError(
                "SCI_NET failure_count disagrees with the parsed failed_stations"
            )
    complete["failure_count"] = complete["failed_count"]
    curves = resilience_curve(complete, skill_col="skill")
    curves["failure_count"] = curves["failed_count"]
    auc = resilience_auc(curves)
    importance = node_importance(complete, value_col="MAE")
    failure_groups = [
        column
        for column in (
            *RESILIENCE_GROUP_COLUMNS,
            "data_version",
            "failed_stations",
            "failure_count",
            "failure_fraction",
        )
        if column in complete
    ]
    failure_sets = _summarize_unit_values(
        complete,
        group_cols=failure_groups,
        value_cols=value_cols,
    )
    hypothesis_rows: list[dict[str, Any]] = []
    outer = [column for column in RESILIENCE_GROUP_COLUMNS if column in complete]
    for key, group in complete.groupby(outer, dropna=False, observed=True, sort=True):
        metadata = dict(
            zip(outer, key if isinstance(key, tuple) else (key,), strict=True)
        )
        reference = group.loc[
            pd.to_numeric(group["failure_count"], errors="coerce").eq(0),
            ["target_gap_id", "MAE"],
        ]
        if reference.empty:
            continue
        reference = reference.groupby("target_gap_id", observed=True)["MAE"].mean()
        for failure_label, failed in group.loc[
            pd.to_numeric(group["failure_count"], errors="coerce").gt(0)
        ].groupby("failed_stations", dropna=False, observed=True, sort=True):
            paired = (
                failed.groupby("target_gap_id", observed=True)["MAE"]
                .mean()
                .to_frame("failed")
                .join(reference.rename("full"), how="inner")
            )
            difference = paired["failed"] - paired["full"]
            hypothesis_rows.append(
                {
                    **metadata,
                    "failed_stations": failure_label,
                    "estimate": float(difference.mean()) if len(difference) else np.nan,
                    "p_value": _wilcoxon_p(difference),
                    "n_anchor_units": len(difference),
                    "hypothesis_family": "network_failure_set",
                }
            )
    hypotheses = pd.DataFrame(hypothesis_rows)
    if not hypotheses.empty:
        hypotheses = benjamini_hochberg_by_family(hypotheses)
    return {
        "curves": curves,
        "importance": importance,
        "failure_sets": failure_sets,
        "auc": auc,
        "hypotheses": hypotheses,
    }


EVENT_VALUE_COLUMNS = (
    "MAE",
    "RMSE",
    "peak_error",
    "timing_error",
    "coverage_90",
    "interval_width_90",
    "event_peak_magnitude_error",
    "event_peak_timing_error_days",
    "event_minimum_magnitude_error",
    "event_minimum_timing_error_days",
)


def analyze_event_pairs(
    events: pd.DataFrame,
    statistics: FrozenStatistics,
) -> dict[str, pd.DataFrame]:
    """Compare seed-collapsed frozen event episodes with their matched controls."""

    if "catalog_role" not in events or "pair_id" not in events:
        return {
            "episodes": pd.DataFrame(),
            "comparisons": pd.DataFrame(),
            "hypotheses": pd.DataFrame(),
        }
    selected = events.loc[
        events["catalog_role"].notna() & events["pair_id"].notna()
    ].copy()
    if selected.empty:
        return {
            "episodes": pd.DataFrame(),
            "comparisons": pd.DataFrame(),
            "hypotheses": pd.DataFrame(),
        }
    selected["year"] = _year_column(selected, context="event-pair analysis")
    metrics = [column for column in EVENT_VALUE_COLUMNS if column in selected]
    _require_columns(
        selected,
        ["training_seed", "model", "station_id", "target", "event_type"],
        "event-pair analysis",
    )
    unit_cols = [
        column
        for column in (
            "design_hash",
            "data_version",
            "evaluation_split",
            "experiment",
            "pair_id",
            "anchor_id",
            "event_id",
            "control_id",
            "catalog_role",
            "station_id",
            "target",
            "event_type",
            "model",
            "window_length",
            "year",
            "station",
            "event_start",
            "event_end",
            "event_peak_date",
            "event_length",
            "matched_control_id",
        )
        if column in selected
    ]
    collapsed = _seed_collapse(selected, unit_cols=unit_cols, value_cols=metrics)
    if "station" not in collapsed:
        collapsed["station"] = collapsed["station_id"]
    if "matched_control_id" not in collapsed:
        collapsed["matched_control_id"] = collapsed["control_id"]
    collapsed["episode_inference_unit"] = collapsed["event_id"].fillna(
        collapsed["pair_id"]
    )
    comparison_rows: list[dict[str, Any]] = []
    group_cols = [
        column
        for column in (
            "data_version",
            "evaluation_split",
            "station_id",
            "target",
            "event_type",
            "model",
            "window_length",
        )
        if column in collapsed
    ]
    role = collapsed["catalog_role"].astype(str).str.lower()
    collapsed["_role"] = np.where(
        role.str.contains("control"),
        "control",
        np.where(role.str.contains("event"), "event", "unknown"),
    )
    if collapsed["_role"].eq("unknown").any():
        raise ValueError("catalog_role must identify event_episode or matched_control")
    for key, group in collapsed.groupby(
        group_cols, dropna=False, observed=True, sort=True
    ):
        metadata = dict(
            zip(group_cols, key if isinstance(key, tuple) else (key,), strict=True)
        )
        for offset, metric in enumerate(metrics):
            pivot = group.pivot_table(
                index="pair_id", columns="_role", values=metric, aggfunc="mean"
            )
            if not {"event", "control"}.issubset(pivot.columns):
                continue
            paired = pivot[["event", "control"]].dropna().copy()
            if paired.empty:
                continue
            context = (
                group.loc[group["_role"].eq("event")]
                .drop_duplicates("pair_id")
                .set_index("pair_id")
            )
            units = paired.join(context[["station_id", "year"]], how="left")
            units["difference"] = units["event"] - units["control"]
            lower, upper = _bootstrap_difference(
                units,
                value_col="difference",
                n_boot=statistics.bootstrap_replicates,
                confidence=statistics.confidence,
                seed=statistics.bootstrap_seed + offset,
            )
            comparison_rows.append(
                {
                    **metadata,
                    "metric": metric,
                    "event_mean": float(paired["event"].mean()),
                    "matched_control_mean": float(paired["control"].mean()),
                    "event_minus_control": float(units["difference"].mean()),
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "p_value": _wilcoxon_p(units["difference"]),
                    "n_event_episodes": len(units),
                    "n_years": int(units["year"].nunique()),
                    "hypothesis_family": "event_vs_matched_control",
                    "training_seeds_collapsed_first": True,
                    "bootstrap_unit": "event_episode_within_station_year_strata",
                }
            )
    comparisons = pd.DataFrame(comparison_rows)
    if not comparisons.empty:
        comparisons = benjamini_hochberg_by_family(comparisons)
    return {
        "episodes": collapsed.drop(columns="_role"),
        "comparisons": comparisons,
        "hypotheses": comparisons.copy(),
    }


def _partially_available_year(frame: pd.DataFrame) -> pd.Series:
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in ("anchor_year", "year"):
        if column not in frame:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        usable = (
            result.isna() & numeric.notna() & np.isclose(numeric, np.round(numeric))
        )
        result.loc[usable] = numeric.loc[usable]
    for column in ("center_date", "window_center_date", "date"):
        if column not in frame:
            continue
        dates = pd.to_datetime(frame[column], errors="coerce")
        usable = result.isna() & dates.notna()
        result.loc[usable] = dates.loc[usable].dt.year
    return result


def analyze_data_version_sensitivity(
    primary_events: pd.DataFrame,
    sensitivity_events: Mapping[str, pd.DataFrame],
    statistics: FrozenStatistics,
) -> pd.DataFrame:
    """Pair separately frozen sensitivity bundles to persistent primary anchors."""

    if "data_version" not in primary_events or "MAE" not in primary_events:
        return pd.DataFrame()
    primary_versions = set(primary_events["data_version"].dropna().astype(str))
    if primary_versions != {statistics.primary_data_version}:
        raise ValueError(
            "primary analysis bundle must contain only the primary data version"
        )
    sensitivity_versions = [
        version
        for version in statistics.sensitivity_data_versions
        if version in sensitivity_events
    ]
    if not sensitivity_versions:
        return pd.DataFrame()
    parts = [primary_events.copy()]
    for version in sensitivity_versions:
        frame = sensitivity_events[version].copy()
        _require_columns(frame, ["data_version", "MAE"], f"{version} sensitivity")
        observed = set(frame["data_version"].dropna().astype(str))
        if observed != {version}:
            raise ValueError(
                f"sensitivity bundle {version!r} contains versions {sorted(observed)}"
            )
        parts.append(frame)
    selected = pd.concat(parts, ignore_index=True, sort=False)
    selected["year"] = _partially_available_year(selected)
    anchor_source = (
        selected["anchor_id"]
        if "anchor_id" in selected
        else selected.get("event_id", pd.Series(np.nan, index=selected.index))
    )
    selected["sensitivity_anchor_id"] = anchor_source
    selected = selected.loc[
        selected["sensitivity_anchor_id"].notna() & selected["year"].notna()
    ].copy()
    if selected.empty:
        return pd.DataFrame()
    selected["year"] = selected["year"].astype(int)
    if "window" not in selected:
        selected["window"] = selected.get("window_length", np.nan)
    if "information_combination" not in selected:
        selected["information_combination"] = "full_information"
    else:
        selected["information_combination"] = selected[
            "information_combination"
        ].fillna("full_information")
    unit_cols = [
        column
        for column in (
            "evaluation_split",
            "experiment",
            "condition_id",
            "scenario_id",
            "sensitivity_anchor_id",
            "mask_seed",
            "station_id",
            "target",
            "model",
            "gap_length",
            "window",
            "information_combination",
            "target_gap_id",
            "failed_stations",
            "pair_id",
            "catalog_role",
            "year",
            "data_version",
        )
        if column in selected
    ]
    collapsed = _seed_collapse(selected, unit_cols=unit_cols, value_cols=("MAE",))
    pairing_cols = [column for column in unit_cols if column != "data_version"]
    primary = collapsed.loc[
        collapsed["data_version"].astype(str).eq(statistics.primary_data_version),
        [*pairing_cols, "MAE"],
    ].rename(columns={"MAE": "primary_MAE"})
    if primary.duplicated(pairing_cols).any():
        raise ValueError("primary data version has duplicate sensitivity units")
    group_cols = [
        column
        for column in (
            "evaluation_split",
            "experiment",
            "station_id",
            "target",
            "model",
            "gap_length",
            "window",
            "information_combination",
        )
        if column in pairing_cols
    ]
    rows: list[dict[str, Any]] = []
    for version_offset, version in enumerate(sensitivity_versions):
        sensitivity = collapsed.loc[
            collapsed["data_version"].astype(str).eq(version),
            [*pairing_cols, "MAE"],
        ].rename(columns={"MAE": "sensitivity_MAE"})
        if sensitivity.duplicated(pairing_cols).any():
            raise ValueError(f"{version} has duplicate sensitivity units")
        paired = sensitivity.merge(
            primary,
            on=pairing_cols,
            how="inner",
            validate="one_to_one",
        )
        paired["MAE_difference"] = paired["sensitivity_MAE"] - paired["primary_MAE"]
        for group_offset, (key, group) in enumerate(
            paired.groupby(group_cols, dropna=False, observed=True, sort=True)
        ):
            metadata = dict(
                zip(
                    group_cols,
                    key if isinstance(key, tuple) else (key,),
                    strict=True,
                )
            )
            lower, upper = _bootstrap_difference(
                group.loc[:, ["station_id", "year", "MAE_difference"]],
                value_col="MAE_difference",
                n_boot=statistics.bootstrap_replicates,
                confidence=statistics.confidence,
                seed=(
                    statistics.bootstrap_seed + version_offset * 10_000 + group_offset
                ),
            )
            rows.append(
                {
                    **metadata,
                    "primary_data_version": statistics.primary_data_version,
                    "sensitivity_data_version": version,
                    "primary_MAE": float(group["primary_MAE"].mean()),
                    "sensitivity_MAE": float(group["sensitivity_MAE"].mean()),
                    "MAE_difference": float(group["MAE_difference"].mean()),
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "p_value": _wilcoxon_p(group["MAE_difference"]),
                    "n_paired_anchors": int(group["sensitivity_anchor_id"].nunique()),
                    "n_years": int(group["year"].nunique()),
                    "hypothesis_family": "data_version_sensitivity",
                    "training_seeds_collapsed_first": True,
                    "bootstrap_unit": ("persistent_anchor_within_station_year_strata"),
                }
            )
    result = pd.DataFrame(rows)
    return benjamini_hochberg_by_family(result) if not result.empty else result


def uncertainty_by_difficulty(calibration: pd.DataFrame) -> pd.DataFrame:
    """Summarise coverage and width over gap, station-loss, and event difficulty."""

    if calibration.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    base_groups = [
        column
        for column in (
            "data_version",
            "evaluation_split",
            "model",
            "target",
            "experiment",
        )
        if column in calibration
    ]
    for axis in ("gap_length", "failure_count", "event_type"):
        if axis not in calibration or calibration[axis].notna().sum() == 0:
            continue
        selected = calibration.loc[calibration[axis].notna()].copy()
        columns = [*base_groups, axis]
        for key, group in selected.groupby(
            columns, dropna=False, observed=True, sort=True
        ):
            metadata = dict(
                zip(columns, key if isinstance(key, tuple) else (key,), strict=True)
            )
            weights = pd.to_numeric(group["n"], errors="coerce").to_numpy(dtype=float)
            coverage = pd.to_numeric(
                group["empirical_coverage"], errors="coerce"
            ).to_numpy(dtype=float)
            width = pd.to_numeric(
                group["mean_interval_width"], errors="coerce"
            ).to_numpy(dtype=float)
            usable = (
                np.isfinite(weights)
                & (weights > 0)
                & np.isfinite(coverage)
                & np.isfinite(width)
            )
            rows.append(
                {
                    **{column: metadata[column] for column in base_groups},
                    "difficulty_axis": axis,
                    "difficulty_level": metadata[axis],
                    "empirical_coverage": float(
                        np.average(coverage[usable], weights=weights[usable])
                    )
                    if usable.any()
                    else np.nan,
                    "mean_interval_width": float(
                        np.average(width[usable], weights=weights[usable])
                    )
                    if usable.any()
                    else np.nan,
                    "n_evaluated_cells": int(weights[usable].sum())
                    if usable.any()
                    else 0,
                    "n_seed_collapsed_units": int(usable.sum()),
                    "training_seeds_collapsed_first": True,
                }
            )
    return pd.DataFrame(rows)


def analyze_calibration(predictions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Produce cell-weighted interval calibration after seed-first collapse."""

    required = {
        "q05",
        "q95",
        "y_true",
        "quality_approved",
        "artificial_mask",
        "gap_length",
    }
    if not required.issubset(predictions.columns):
        return {
            "by_gap": pd.DataFrame(),
            "overall": pd.DataFrame(),
            "growth": pd.DataFrame(),
            "difficulty": pd.DataFrame(),
        }
    finite_interval = np.isfinite(
        pd.to_numeric(predictions["q05"], errors="coerce")
    ) & np.isfinite(pd.to_numeric(predictions["q95"], errors="coerce"))
    probabilistic = predictions.loc[finite_interval].copy()
    if probabilistic.empty:
        return {
            "by_gap": pd.DataFrame(),
            "overall": pd.DataFrame(),
            "growth": pd.DataFrame(),
            "difficulty": pd.DataFrame(),
        }
    units = interval_calibration_by_gap(probabilistic)
    if units.empty:
        return {
            "by_gap": units,
            "overall": pd.DataFrame(),
            "growth": pd.DataFrame(),
            "difficulty": pd.DataFrame(),
        }
    seed_col = "training_seed"
    group_cols = [
        column
        for column in units.columns
        if column
        not in {
            seed_col,
            "empirical_coverage",
            "calibration_error",
            "absolute_calibration_error",
            "mean_interval_width",
            "median_interval_width",
            "quantile_crossing_rate",
            "n",
            "reason",
        }
    ]
    numeric = (
        units.groupby(group_cols, dropna=False, observed=True, sort=True)[
            [
                "empirical_coverage",
                "calibration_error",
                "absolute_calibration_error",
                "mean_interval_width",
                "median_interval_width",
                "quantile_crossing_rate",
                "n",
            ]
        ]
        .mean()
        .reset_index()
    )
    counts = (
        units.groupby(group_cols, dropna=False, observed=True)[seed_col]
        .nunique(dropna=True)
        .rename("n_training_seeds")
        .reset_index()
    )
    by_gap = numeric.merge(counts, on=group_cols, validate="one_to_one")
    by_gap["training_seeds_collapsed_first"] = True
    by_gap["reason"] = None
    overall = overall_calibration(by_gap)
    growth = uncertainty_growth(by_gap)
    difficulty = uncertainty_by_difficulty(by_gap)
    return {
        "by_gap": by_gap,
        "overall": overall,
        "growth": growth,
        "difficulty": difficulty,
    }


EMPTY_SCHEMAS: dict[str, tuple[str, ...]] = {
    "best_simple_baseline_lookup.csv": (
        "condition_family",
        "best_simple_baseline",
        "status",
    ),
    "relative_skill_events.parquet": (
        "scenario_id",
        "model",
        "skill_vs_climatology",
        "skill_vs_best_simple",
        "status",
    ),
    "frontier_climatology_curves.csv": (
        "gap_length",
        "mean_skill",
        "status",
    ),
    "frontier_climatology_summary.csv": (
        "statistical_frontier_days",
        "frontier_denominator",
        "status",
    ),
    "frontier_best_simple_curves.csv": (
        "gap_length",
        "mean_skill",
        "status",
    ),
    "frontier_best_simple_summary.csv": (
        "statistical_frontier_days",
        "frontier_denominator",
        "status",
    ),
    "dual_frontier_comparison.csv": (
        "frontier_denominator",
        "statistical_frontier_days",
        "status",
    ),
    "frontier_raw_curves.csv": (
        *FRONTIER_GROUPS,
        "gap_length",
        "frontier_value",
        "status",
    ),
    "frontier_monotone_curves.csv": (
        *FRONTIER_GROUPS,
        "gap_length",
        "frontier_value",
        "status",
    ),
    "statistical_frontiers.csv": (
        *FRONTIER_GROUPS,
        "statistical_frontier_days",
        "status",
    ),
    "application_frontiers.csv": (
        *FRONTIER_GROUPS,
        "application_threshold_status",
        "operational_boundary_days",
        "status",
    ),
    "frontier_breakpoints.csv": (
        *FRONTIER_GROUPS,
        "curve_type",
        "breakpoint_days",
        "status",
    ),
    "frontier_bootstrap_samples.parquet": (
        *FRONTIER_GROUPS,
        "bootstrap_id",
        "gap_length",
        "status",
    ),
    "pairwise_jaccard.csv": (
        "left_anchor_id",
        "right_anchor_id",
        "temporal_jaccard",
        "status",
    ),
    "unique_date_coverage.csv": ("date", "anchors_covering_date", "status"),
    "effective_replication_summary.csv": (
        "anchor_id",
        "effective_unique_masked_cells",
        "status",
    ),
    "overlap_clusters.csv": ("anchor_id", "overlap_cluster_id", "status"),
    "information_combination_metrics.csv": (
        "information_estimand",
        "information_combination",
        "MAE",
        "status",
    ),
    "operational_dropout_gains.csv": (
        "information_estimand",
        "source",
        "full_removal_gain",
        "status",
    ),
    "retrained_information_upper_bounds.csv": (
        "information_estimand",
        "information_combination",
        "reference_information_combination",
        "source",
        "coalition_MAE",
        "reference_MAE",
        "MAE_gain_vs_S0",
        "status",
    ),
    "shapley_contributions.csv": (
        "information_estimand",
        "source",
        "shapley",
        "status",
    ),
    "information_interactions.csv": (
        "information_estimand",
        "source_left",
        "source_right",
        "interaction",
        "status",
    ),
    "resilience_curves.csv": ("model", "failure_fraction", "relative_skill", "status"),
    "node_importance.csv": ("model", "failed_station_id", "impact", "status"),
    "failure_set_metrics.csv": ("model", "failed_stations", "MAE", "status"),
    "resilience_auc.csv": ("model", "resilience_auc", "status"),
    "event_episode_metrics.csv": ("pair_id", "catalog_role", "model", "MAE", "status"),
    "event_vs_matched_control.csv": (
        "model",
        "event_type",
        "metric",
        "event_minus_control",
        "status",
    ),
    "calibration_by_gap.csv": ("model", "gap_length", "empirical_coverage", "status"),
    "calibration_overall.csv": ("model", "coverage", "status"),
    "uncertainty_growth.csv": ("model", "gap_width_spearman", "status"),
    "uncertainty_by_difficulty.csv": (
        "model",
        "difficulty_axis",
        "difficulty_level",
        "empirical_coverage",
        "mean_interval_width",
        "status",
    ),
    "data_version_sensitivity.csv": (
        "primary_data_version",
        "sensitivity_data_version",
        "model",
        "MAE_difference",
        "status",
    ),
    "hypothesis_tests.csv": ("hypothesis_family", "p_value", "p_bh", "status"),
    "donor_c_falsification_effects.csv": (
        "contrast",
        "skill_gain",
        "ci_lower",
        "ci_upper",
        "status",
    ),
    "donor_c_falsification_decision.csv": (
        "interpretation",
        "claim_language",
        "p_value",
        "status",
    ),
}


def _prepare_output(
    frame: pd.DataFrame,
    name: str,
    reason: str | None = None,
    empty_status: str = "unavailable",
    nonempty_status: str = "ok",
) -> pd.DataFrame:
    if frame.empty:
        result = pd.DataFrame(columns=EMPTY_SCHEMAS[name])
        if empty_status not in {"unavailable", "not_applicable"}:
            raise ValueError(f"unknown empty artifact status: {empty_status}")
        result.attrs["status"] = empty_status
        result.attrs["reason"] = reason or "no eligible frozen rows"
        return result
    if nonempty_status not in {"ok", "not_applicable"}:
        raise ValueError(f"unknown non-empty artifact status: {nonempty_status}")
    result = frame.copy()
    result["status"] = nonempty_status
    result.attrs["status"] = nonempty_status
    result.attrs["reason"] = reason if nonempty_status != "ok" else None
    return result


def _jsonable_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include="object"):
        if (
            result[column]
            .map(lambda value: isinstance(value, (tuple, list, dict, set)))
            .any()
        ):
            result[column] = result[column].map(
                lambda value: (
                    json.dumps(
                        sorted(value) if isinstance(value, set) else value,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    if isinstance(value, (tuple, list, dict, set))
                    else value
                )
            )
    return result


def _atomic_table(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = _jsonable_columns(frame)
    temporary = path.with_name(path.stem + ".tmp" + path.suffix)
    if path.suffix == ".parquet":
        prepared.to_parquet(temporary, index=False)
    else:
        prepared.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json(value: Mapping[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _bundle_input_identity(inputs: FrozenInputs) -> dict[str, Any]:
    contract = _manifest_contracts(inputs.manifest)[0]
    value: dict[str, Any] = {
        "data_version": contract["data_version"],
        "evaluation_split": contract["evaluation_split"],
        "aggregate_manifest": {
            "path": str(inputs.manifest_path),
            "bytes": inputs.manifest_path.stat().st_size,
            "sha256": _file_sha256(inputs.manifest_path),
        },
        "predictions": {
            "path": str(inputs.predictions_path),
            "bytes": inputs.predictions_path.stat().st_size,
            "sha256": _file_sha256(inputs.predictions_path),
        },
        "event_metrics": {
            "path": str(inputs.events_path),
            "bytes": inputs.events_path.stat().st_size,
            "sha256": _file_sha256(inputs.events_path),
        },
        "formal_registry": inputs.registry_identity,
    }
    value["bundle_input_sha256"] = _canonical_digest(value)
    return value


def _close_analysis_inputs(
    inputs: FrozenInputs,
    sensitivity_by_version: Mapping[str, FrozenInputs],
) -> tuple[dict[str, Any], str]:
    """Close four aggregate/registry identities against one frozen roster."""

    required = inputs.statistics.sensitivity_data_versions
    if tuple(sensitivity_by_version) != required:
        raise ValueError("sensitivity inputs are not in frozen data-version order")
    all_inputs = [inputs, *(sensitivity_by_version[version] for version in required)]
    if len({bundle.manifest_path for bundle in all_inputs}) != len(all_inputs):
        raise ValueError("analysis aggregate manifests are duplicated")
    if len({bundle.registry_path for bundle in all_inputs}) != len(all_inputs):
        raise ValueError("analysis formal registries are duplicated")
    for bundle in all_inputs:
        aggregate_roles = _validate_bundle_roles(bundle.manifest)
        registry_roles = bundle.registry_identity
        for field in (
            "bundle_kind",
            "bundle_role",
            "required_suite_roles",
            "suite_roles",
        ):
            if aggregate_roles[field] != registry_roles[field]:
                raise ValueError(f"aggregate and formal registry disagree on {field}")
        aggregate_roster = aggregate_roles["finalized_model_roster"]
        registry_roster = registry_roles["finalized_model_roster"]
        for field in ("sha256", "selected_models", "proposed_decision"):
            if aggregate_roster[field] != registry_roster[field]:
                raise ValueError(
                    f"aggregate and formal registry roster disagree on {field}"
                )
    roster_keys = {
        _canonical_digest(bundle.registry_identity["finalized_model_roster"])
        for bundle in all_inputs
    }
    if len(roster_keys) != 1:
        raise ValueError("formal registries do not bind one finalized model roster")
    roster = inputs.registry_identity["finalized_model_roster"]
    manifest: dict[str, Any] = {
        "schema_version": "frozen_analysis_input_manifest_v1",
        "status": "complete",
        "primary_data_version": inputs.statistics.primary_data_version,
        "required_sensitivity_data_versions": list(required),
        "finalized_model_roster": roster,
        "registry_count": len(all_inputs),
        "aggregate_manifest_count": len(all_inputs),
        "bundles": {
            "primary": _bundle_input_identity(inputs),
            "sensitivity": [
                _bundle_input_identity(sensitivity_by_version[version])
                for version in required
            ],
        },
        "hash_scope": "canonical_json_excluding_input_manifest_sha256",
    }
    manifest["input_manifest_sha256"] = _canonical_digest(manifest)
    return manifest, str(roster["proposed_decision"])


def _domain_record(
    name: str,
    *,
    complete: bool,
    artifacts: Sequence[str],
    reason: str | None = None,
    not_applicable: bool = False,
) -> dict[str, Any]:
    status = (
        "not_applicable"
        if not_applicable
        else ("complete" if complete else "unavailable")
    )
    return {
        "domain": name,
        "status": status,
        "reason": None if status == "complete" else reason,
        "artifacts": list(artifacts),
    }


def _analysis_completion_gate(
    frames: Mapping[str, pd.DataFrame],
    *,
    overlap_summary: Mapping[str, Any],
    statistics: FrozenStatistics,
    proposed_decision: str,
    selected_models: Sequence[str],
) -> dict[str, Any]:
    """Assess protocol-required domains without treating empty output as success."""

    framework_only = proposed_decision == "framework_only"
    donor_falsification_required = (
        "donor_c_falsification" in statistics.hypothesis_families
    )
    probabilistic_model_selected = bool(
        set(selected_models).intersection({"csdi", "proposed"})
    )

    def all_nonempty(names: Sequence[str]) -> bool:
        return all(not frames[name].empty for name in names)

    overlap_artifacts = (
        "pairwise_jaccard.csv",
        "unique_date_coverage.csv",
        "effective_replication_summary.csv",
        "overlap_clusters.csv",
    )
    dual_frontier_artifacts = (
        "frontier_climatology_curves.csv",
        "frontier_climatology_summary.csv",
        "frontier_best_simple_curves.csv",
        "frontier_best_simple_summary.csv",
        "dual_frontier_comparison.csv",
    )
    frontier_artifacts = (
        "frontier_raw_curves.csv",
        "frontier_monotone_curves.csv",
        "statistical_frontiers.csv",
        "frontier_breakpoints.csv",
        "frontier_bootstrap_samples.parquet",
    )
    if statistics.primary_data_version == "published_v2":
        frontier_artifacts = (*dual_frontier_artifacts, *frontier_artifacts)
    operational_artifacts = (
        "information_combination_metrics.csv",
        "operational_dropout_gains.csv",
        "shapley_contributions.csv",
        "information_interactions.csv",
    )
    retrained_artifacts = (
        "information_combination_metrics.csv",
        "retrained_information_upper_bounds.csv",
    )
    resilience_artifacts = (
        "resilience_curves.csv",
        "node_importance.csv",
        "failure_set_metrics.csv",
        "resilience_auc.csv",
    )
    event_artifacts = (
        "event_episode_metrics.csv",
        "event_vs_matched_control.csv",
    )
    calibration_artifacts = (
        "calibration_by_gap.csv",
        "calibration_overall.csv",
        "uncertainty_growth.csv",
        "uncertainty_by_difficulty.csv",
    )
    metrics = frames["information_combination_metrics.csv"]
    estimands = (
        set(metrics["information_estimand"].dropna().astype(str))
        if "information_estimand" in metrics
        else set()
    )
    sensitivity = frames["data_version_sensitivity.csv"]
    sensitivity_versions = (
        set(sensitivity["sensitivity_data_version"].dropna().astype(str))
        if "sensitivity_data_version" in sensitivity
        else set()
    )
    hypotheses = frames["hypothesis_tests.csv"]
    observed_families = (
        set(hypotheses["hypothesis_family"].dropna().astype(str))
        if "hypothesis_family" in hypotheses
        else set()
    )
    expected_families = set(statistics.hypothesis_families)
    if framework_only:
        expected_families.difference_update(
            {
                "operational_information_dropout",
                "retrained_information_upper_bound",
                "donor_c_falsification",
            }
        )
    finite_hypotheses = False
    if not hypotheses.empty and {"p_value", "p_bh"}.issubset(hypotheses):
        p_values = pd.to_numeric(hypotheses["p_value"], errors="coerce")
        adjusted = pd.to_numeric(hypotheses["p_bh"], errors="coerce")
        finite_hypotheses = bool(
            np.isfinite(p_values).all() and np.isfinite(adjusted).all()
        )
    domains = [
        _domain_record("formal_input_roles", complete=True, artifacts=()),
        _domain_record(
            "overlap_audit",
            complete=(
                overlap_summary.get("status") == "ok"
                and all_nonempty(overlap_artifacts)
            ),
            artifacts=overlap_artifacts,
            reason="overlap audit lacks complete dense-anchor evidence",
        ),
        _domain_record(
            "recoverability_frontier",
            complete=all_nonempty(frontier_artifacts),
            artifacts=frontier_artifacts,
            reason="recoverability frontier artifacts are empty or unavailable",
        ),
        _domain_record(
            "operational_information",
            complete=(
                all_nonempty(operational_artifacts)
                and "operational_dropout" in estimands
            ),
            artifacts=operational_artifacts,
            reason=(
                "proposed_decision=framework_only"
                if framework_only
                else "operational information estimand is unavailable"
            ),
            not_applicable=framework_only,
        ),
        _domain_record(
            "retrained_information",
            complete=(
                all_nonempty(retrained_artifacts)
                and "retrained_upper_bound" in estimands
            ),
            artifacts=retrained_artifacts,
            reason=(
                "proposed_decision=framework_only"
                if framework_only
                else "retrained information upper bound is unavailable"
            ),
            not_applicable=framework_only,
        ),
        _domain_record(
            "network_resilience",
            complete=all_nonempty(resilience_artifacts),
            artifacts=resilience_artifacts,
            reason="network resilience artifacts are empty or unavailable",
        ),
        _domain_record(
            "event_uncertainty",
            complete=all_nonempty(event_artifacts),
            artifacts=event_artifacts,
            reason="event/control analysis artifacts are empty or unavailable",
        ),
        _domain_record(
            "uncertainty_calibration",
            complete=all_nonempty(calibration_artifacts),
            artifacts=calibration_artifacts,
            reason=(
                "uncertainty calibration artifacts are empty or unavailable"
                if probabilistic_model_selected
                else "no finalized probabilistic model; uncertainty claim downgraded"
            ),
            not_applicable=not probabilistic_model_selected,
        ),
        _domain_record(
            "data_version_sensitivity",
            complete=(
                not sensitivity.empty
                and sensitivity_versions == set(statistics.sensitivity_data_versions)
            ),
            artifacts=("data_version_sensitivity.csv",),
            reason="all three sensitivity versions lack paired analysis evidence",
        ),
        _domain_record(
            "donor_c_falsification",
            complete=all_nonempty(
                (
                    "donor_c_falsification_effects.csv",
                    "donor_c_falsification_decision.csv",
                )
            ),
            artifacts=(
                "donor_c_falsification_effects.csv",
                "donor_c_falsification_decision.csv",
            ),
            reason=(
                "not declared by the historical design"
                if "donor_c_falsification" not in statistics.hypothesis_families
                else "formal donor-C contrasts are unavailable"
            ),
            not_applicable=not donor_falsification_required,
        ),
        _domain_record(
            "hypothesis_families",
            complete=(observed_families == expected_families and finite_hypotheses),
            artifacts=("hypothesis_tests.csv",),
            reason=(
                "required hypothesis families are missing or have non-finite tests: "
                f"expected={sorted(expected_families)}, "
                f"observed={sorted(observed_families)}"
            ),
        ),
    ]
    if tuple(item["domain"] for item in domains) != REQUIRED_ANALYSIS_DOMAINS:
        raise AssertionError("analysis completion domain inventory drifted")
    complete = all(item["status"] in {"complete", "not_applicable"} for item in domains)
    return {
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        "framework_only": framework_only,
        "required_domains": list(REQUIRED_ANALYSIS_DOMAINS),
        "domains": domains,
        "complete_domain_count": sum(item["status"] == "complete" for item in domains),
        "not_applicable_domain_count": sum(
            item["status"] == "not_applicable" for item in domains
        ),
        "unavailable_domains": [
            item["domain"] for item in domains if item["status"] == "unavailable"
        ],
        "claim_downgrades": (
            []
            if probabilistic_model_selected
            else ["uncertainty_calibration_not_claimed"]
        ),
    }


def _load_best_simple_lookup(inputs: FrozenInputs) -> pd.DataFrame:
    """Load the validation-frozen lookup carried by the finalized v4 roster."""

    raw_roster = inputs.registry.get("finalized_model_roster")
    if not isinstance(raw_roster, Mapping):
        raise TypeError("formal registry lacks finalized_model_roster")
    roster_path = _repository_path(
        raw_roster.get("path"),
        declaring_file=inputs.registry_path,
        label="finalized_model_roster.path",
    )
    roster = _read_mapping(roster_path)
    artifacts = roster.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise TypeError("finalized roster lacks artifacts")
    identity = artifacts.get("best_simple_baseline_lookup")
    if not isinstance(identity, Mapping):
        raise ValueError("v4 finalized roster lacks best-simple baseline lookup")
    lookup_path = _repository_path(
        identity.get("path"),
        declaring_file=roster_path,
        label="best_simple_baseline_lookup.path",
    )
    lookup = _read_table(lookup_path)
    required = {
        "condition_family",
        "best_simple_baseline",
        "station_id",
        "target",
        "mask_geometry",
        "data_version",
    }
    _require_columns(lookup, required, "best-simple baseline lookup")
    if set(lookup["data_version"].astype(str)) != {
        inputs.statistics.primary_data_version
    }:
        raise ValueError("best-simple lookup uses another selection data version")
    if lookup["condition_family"].duplicated().any():
        raise ValueError("best-simple lookup contains duplicate families")
    return lookup


def _analyze_donor_falsification(
    events: pd.DataFrame, statistics: FrozenStatistics
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize an explicitly labelled formal donor-C suite, if present."""

    if "experiment" not in events:
        return pd.DataFrame(), pd.DataFrame()
    data = events.loc[
        events["experiment"].astype(str).eq("SCI_DONOR_FALSIFICATION")
    ].copy()
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()
    required = {"contrast", "skill_gain", "anchor_id"}
    _require_columns(data, required, "donor-C falsification")
    data["skill_gain"] = pd.to_numeric(data["skill_gain"], errors="coerce")
    effects = (
        data.groupby(
            [
                column
                for column in ("station_id", "target", "contrast", "lag_days")
                if column in data
            ],
            dropna=False,
            observed=True,
        )["skill_gain"]
        .agg(["mean", "count", "std"])
        .reset_index()
        .rename(columns={"mean": "skill_gain", "count": "n_anchor_events"})
    )
    effects["standard_error"] = effects["std"] / np.sqrt(effects["n_anchor_events"])
    effects["ci_lower"] = effects["skill_gain"] - 1.96 * effects["standard_error"]
    effects["ci_upper"] = effects["skill_gain"] + 1.96 * effects["standard_error"]
    decision = interpret_falsification(
        effects,
        minimum_meaningful_difference=0.01,
        require_confidence_intervals=True,
    )
    pair_columns = [
        column
        for column in (
            "anchor_id",
            "station_id",
            "target",
            "mask_seed",
            "training_seed",
        )
        if column in data
    ]
    paired = (
        data.groupby([*pair_columns, "contrast"], observed=True)["skill_gain"]
        .mean()
        .unstack("contrast")
    )
    if {"observed_same_day_C", "station_identity_permutation"}.issubset(paired):
        paired_difference = (
            paired["observed_same_day_C"] - paired["station_identity_permutation"]
        ).dropna()
        p_value = _wilcoxon_p(paired_difference)
    else:
        paired_difference = pd.Series(dtype=float)
        p_value = np.nan
    decision_frame = pd.DataFrame(
        [
            {
                **decision,
                "hypothesis_family": "donor_c_falsification",
                "contrast": "observed_same_day_C_vs_station_identity_permutation",
                "estimate": (
                    float(paired_difference.mean())
                    if not paired_difference.empty
                    else np.nan
                ),
                "n_pairs": int(len(paired_difference)),
                "p_value": p_value,
            }
        ]
    )
    return effects, decision_frame


def run_frozen_analysis(
    inputs: FrozenInputs,
    output_dir: str | Path,
    *,
    sensitivity_inputs: Sequence[FrozenInputs] = (),
) -> dict[str, Any]:
    """Run every frozen analysis and always emit the declared artifact set."""

    analysis_code_identity = build_analysis_code_identity()
    require_clean_analysis_code(analysis_code_identity)
    primary_bundle_contract = _validate_bundle_roles(inputs.manifest)
    if primary_bundle_contract["bundle_role"] != "primary":
        raise ValueError("the primary analysis input must have bundle_role=primary")
    primary_versions = set(inputs.events["data_version"].dropna().astype(str))
    if primary_versions != {inputs.statistics.primary_data_version}:
        raise ValueError("the primary frozen bundle has the wrong data version")
    sensitivity_by_version: dict[str, FrozenInputs] = {}
    primary_splits = set(inputs.events["evaluation_split"].dropna().astype(str))
    for bundle in sensitivity_inputs:
        bundle_contract = _validate_bundle_roles(bundle.manifest)
        if bundle_contract["bundle_role"] != "sensitivity_compact":
            raise ValueError(
                "each sensitivity analysis input must be a sensitivity_compact bundle"
            )
        if (
            bundle_contract["finalized_model_roster"]
            != primary_bundle_contract["finalized_model_roster"]
        ):
            raise ValueError("sensitivity and primary bundles use different rosters")
        versions = set(bundle.events["data_version"].dropna().astype(str))
        if len(versions) != 1:
            raise ValueError(
                "each sensitivity bundle must contain exactly one data version"
            )
        version = next(iter(versions))
        if version not in inputs.statistics.sensitivity_data_versions:
            raise ValueError(f"undeclared sensitivity data version: {version}")
        if version in sensitivity_by_version:
            raise ValueError(f"duplicate sensitivity bundle: {version}")
        if (
            set(bundle.events["evaluation_split"].dropna().astype(str))
            != primary_splits
        ):
            raise ValueError(
                "sensitivity and primary bundles use different evaluation splits"
            )
        sensitivity_by_version[version] = bundle

    required_sensitivity_versions = set(inputs.statistics.sensitivity_data_versions)
    if set(sensitivity_by_version) != required_sensitivity_versions:
        missing = sorted(
            required_sensitivity_versions.difference(sensitivity_by_version)
        )
        unexpected = sorted(
            set(sensitivity_by_version).difference(required_sensitivity_versions)
        )
        raise ValueError(
            "frozen analysis requires one independent compact bundle for every "
            f"sensitivity version: missing={missing}, unexpected={unexpected}"
        )
    sensitivity_by_version = {
        version: sensitivity_by_version[version]
        for version in inputs.statistics.sensitivity_data_versions
    }
    analysis_input_manifest, proposed_decision = _close_analysis_inputs(
        inputs, sensitivity_by_version
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    overlap = audit_prediction_overlap(inputs.predictions)
    frontiers = analyze_frontiers(inputs.events, overlap, inputs.statistics)
    if inputs.statistics.primary_data_version == "published_v2":
        best_simple_lookup = _load_best_simple_lookup(inputs)
        dual_frontiers = estimate_dual_frontiers(
            inputs.events,
            best_simple=best_simple_lookup,
            n_boot=inputs.statistics.bootstrap_replicates,
            seed=inputs.statistics.bootstrap_seed,
        )
    else:
        best_simple_lookup = pd.DataFrame()
        dual_frontiers = {
            "scored_events": pd.DataFrame(),
            "climatology_curves": pd.DataFrame(),
            "climatology_frontiers": pd.DataFrame(),
            "best_simple_curves": pd.DataFrame(),
            "best_simple_frontiers": pd.DataFrame(),
            "dual_frontiers": pd.DataFrame(),
        }
    falsification_effects, falsification_decision = _analyze_donor_falsification(
        inputs.events, inputs.statistics
    )
    information = analyze_information(inputs.events, inputs.statistics)
    resilience = analyze_resilience_outputs(inputs.events, inputs.statistics)
    event_pairs = analyze_event_pairs(inputs.events, inputs.statistics)
    calibration = analyze_calibration(inputs.predictions)
    sensitivity = analyze_data_version_sensitivity(
        inputs.events,
        {version: bundle.events for version, bundle in sensitivity_by_version.items()},
        inputs.statistics,
    )
    hypotheses = (
        pd.concat(
            [
                frame
                for frame in (
                    frontiers.statistical,
                    information["hypotheses"],
                    resilience["hypotheses"],
                    event_pairs["hypotheses"],
                    sensitivity,
                    falsification_decision,
                )
                if not frame.empty and "p_value" in frame
            ],
            ignore_index=True,
        )
        if any(
            not frame.empty and "p_value" in frame
            for frame in (
                frontiers.statistical,
                information["hypotheses"],
                resilience["hypotheses"],
                event_pairs["hypotheses"],
                sensitivity,
                falsification_decision,
            )
        )
        else pd.DataFrame()
    )

    frames = {
        "best_simple_baseline_lookup.csv": best_simple_lookup,
        "relative_skill_events.parquet": dual_frontiers["scored_events"],
        "frontier_climatology_curves.csv": dual_frontiers["climatology_curves"],
        "frontier_climatology_summary.csv": dual_frontiers["climatology_frontiers"],
        "frontier_best_simple_curves.csv": dual_frontiers["best_simple_curves"],
        "frontier_best_simple_summary.csv": dual_frontiers["best_simple_frontiers"],
        "dual_frontier_comparison.csv": dual_frontiers["dual_frontiers"],
        "frontier_raw_curves.csv": frontiers.raw,
        "frontier_monotone_curves.csv": frontiers.monotone,
        "statistical_frontiers.csv": frontiers.statistical,
        "application_frontiers.csv": frontiers.application,
        "frontier_breakpoints.csv": frontiers.breakpoints,
        "frontier_bootstrap_samples.parquet": frontiers.bootstrap_samples,
        "pairwise_jaccard.csv": overlap.pairwise,
        "unique_date_coverage.csv": overlap.dates,
        "effective_replication_summary.csv": overlap.replication,
        "overlap_clusters.csv": overlap.clusters,
        "information_combination_metrics.csv": information["metrics"],
        "operational_dropout_gains.csv": information["operational"],
        "retrained_information_upper_bounds.csv": information["retrained"],
        "shapley_contributions.csv": information["shapley"],
        "information_interactions.csv": information["interactions"],
        "resilience_curves.csv": resilience["curves"],
        "node_importance.csv": resilience["importance"],
        "failure_set_metrics.csv": resilience["failure_sets"],
        "resilience_auc.csv": resilience["auc"],
        "event_episode_metrics.csv": event_pairs["episodes"],
        "event_vs_matched_control.csv": event_pairs["comparisons"],
        "calibration_by_gap.csv": calibration["by_gap"],
        "calibration_overall.csv": calibration["overall"],
        "uncertainty_growth.csv": calibration["growth"],
        "uncertainty_by_difficulty.csv": calibration["difficulty"],
        "data_version_sensitivity.csv": sensitivity,
        "hypothesis_tests.csv": hypotheses,
        "donor_c_falsification_effects.csv": falsification_effects,
        "donor_c_falsification_decision.csv": falsification_decision,
    }
    completion_gate = _analysis_completion_gate(
        frames,
        overlap_summary=overlap.summary,
        statistics=inputs.statistics,
        proposed_decision=proposed_decision,
        selected_models=primary_bundle_contract["finalized_model_roster"][
            "selected_models"
        ],
    )
    framework_information_artifacts = {
        "information_combination_metrics.csv",
        "operational_dropout_gains.csv",
        "retrained_information_upper_bounds.csv",
        "shapley_contributions.csv",
        "information_interactions.csv",
    }
    calibration_artifacts = {
        "calibration_by_gap.csv",
        "calibration_overall.csv",
        "uncertainty_growth.csv",
        "uncertainty_by_difficulty.csv",
    }
    probabilistic_model_selected = bool(
        set(
            primary_bundle_contract["finalized_model_roster"]["selected_models"]
        ).intersection({"csdi", "proposed"})
    )
    if proposed_decision == "framework_only" and any(
        not frames[name].empty for name in framework_information_artifacts
    ):
        raise ValueError(
            "framework-only analysis contains proposed information estimands"
        )
    if not probabilistic_model_selected and any(
        not frames[name].empty for name in calibration_artifacts
    ):
        raise ValueError(
            "analysis contains probabilistic outputs without a finalized "
            "probabilistic model"
        )
    unavailability_reasons = {
        "best_simple_baseline_lookup.csv": "validation-frozen target-T lookup is unavailable",
        "relative_skill_events.parquet": "dual-frontier relative skills are unavailable",
        "frontier_climatology_curves.csv": "no complete climatology-relative dense curves",
        "frontier_climatology_summary.csv": "no complete climatology-relative dense frontiers",
        "frontier_best_simple_curves.csv": "no complete best-simple-relative dense curves",
        "frontier_best_simple_summary.csv": "no complete best-simple-relative dense frontiers",
        "dual_frontier_comparison.csv": "dual frontier evidence is unavailable",
        "frontier_raw_curves.csv": "no frozen SCI_DENSE rows",
        "frontier_monotone_curves.csv": "no frozen SCI_DENSE rows",
        "statistical_frontiers.csv": "no complete frozen SCI_DENSE anchor curves",
        "application_frontiers.csv": "no complete frozen SCI_DENSE anchor curves",
        "frontier_breakpoints.csv": "no complete frozen SCI_DENSE anchor curves",
        "frontier_bootstrap_samples.parquet": (
            "no resampleable complete SCI_DENSE anchor curves"
        ),
        "information_combination_metrics.csv": (
            "no frozen information-combination rows"
        ),
        "operational_dropout_gains.csv": "no complete operational 2^4 coalition units",
        "retrained_information_upper_bounds.csv": (
            "no complete retrained-upper-bound exact 9-coalition units"
        ),
        "shapley_contributions.csv": (
            "no complete operational-dropout 2^4 coalition units"
        ),
        "information_interactions.csv": (
            "no complete operational-dropout 2^4 coalition units"
        ),
        "resilience_curves.csv": "no frozen complete SCI_NET failure powersets",
        "node_importance.csv": "no frozen complete SCI_NET failure powersets",
        "failure_set_metrics.csv": "no frozen complete SCI_NET failure powersets",
        "resilience_auc.csv": "no frozen complete SCI_NET failure powersets",
        "event_episode_metrics.csv": "no frozen eligible event/control episodes",
        "event_vs_matched_control.csv": "no complete frozen event/control pairs",
        "calibration_by_gap.csv": "no finite frozen q05/q95 prediction intervals",
        "calibration_overall.csv": "no finite frozen q05/q95 prediction intervals",
        "uncertainty_growth.csv": "no finite multi-gap interval calibration units",
        "uncertainty_by_difficulty.csv": (
            "no finite gap/failure/event interval calibration units"
        ),
        "data_version_sensitivity.csv": (
            "primary and sensitivity versions are not jointly present on persistent anchors"
        ),
        "hypothesis_tests.csv": "no eligible frozen hypothesis families",
        "donor_c_falsification_effects.csv": "no formal donor-C contrast rows",
        "donor_c_falsification_decision.csv": "no formal donor-C decision",
    }
    falsification_artifacts = {
        "donor_c_falsification_effects.csv",
        "donor_c_falsification_decision.csv",
    }
    artifact_manifest: dict[str, Any] = {}
    for name in FIXED_ARTIFACTS:
        framework_not_applicable = (
            proposed_decision == "framework_only"
            and name in framework_information_artifacts
        )
        calibration_not_applicable = (
            not probabilistic_model_selected and name in calibration_artifacts
        )
        application_not_applicable = (
            name == "application_frontiers.csv"
            and inputs.statistics.application_criteria is None
        )
        falsification_not_applicable = (
            "donor_c_falsification" not in inputs.statistics.hypothesis_families
        ) and name in falsification_artifacts
        explicit_not_applicable = (
            framework_not_applicable
            or calibration_not_applicable
            or application_not_applicable
            or falsification_not_applicable
        )
        not_applicable_reason = (
            "proposed_decision=framework_only"
            if framework_not_applicable or falsification_not_applicable
            else (
                "no_finalized_probabilistic_model_claim_downgrade"
                if calibration_not_applicable
                else "withheld_no_predeclared_application_threshold"
            )
        )
        prepared = _prepare_output(
            frames[name],
            name,
            reason=(
                not_applicable_reason
                if explicit_not_applicable
                else unavailability_reasons.get(name)
            ),
            empty_status=(
                "not_applicable" if explicit_not_applicable else "unavailable"
            ),
            nonempty_status=("not_applicable" if explicit_not_applicable else "ok"),
        )
        path = output / name
        _atomic_table(prepared, path)
        artifact_manifest[name] = {
            "status": prepared.attrs.get(
                "status", "ok" if len(prepared) else "unavailable"
            ),
            "reason": prepared.attrs.get("reason"),
            "rows": len(prepared),
            "sha256": _file_sha256(path),
        }
    _atomic_json(overlap.summary, output / "overlap_audit.json")
    analysis_input_path = output / "analysis_input_manifest.json"
    _atomic_json(analysis_input_manifest, analysis_input_path)
    sensitivity_domain = next(
        item
        for item in completion_gate["domains"]
        if item["domain"] == "data_version_sensitivity"
    )
    sensitivity_manifest = {
        "status": sensitivity_domain["status"],
        "reason": (
            None
            if sensitivity_domain["status"] == "complete"
            else "no separately frozen sensitivity bundle shares persistent primary anchors"
        ),
        "primary_data_version": inputs.statistics.primary_data_version,
        "requested_sensitivity_data_versions": list(
            inputs.statistics.sensitivity_data_versions
        ),
        "available_sensitivity_data_versions": sorted(sensitivity_by_version),
        "primary_bundle": {
            "manifest": str(inputs.manifest_path),
            "manifest_sha256": _file_sha256(inputs.manifest_path),
            "bundle_role": primary_bundle_contract["bundle_role"],
            "required_suite_roles": primary_bundle_contract["required_suite_roles"],
            "suite_roles": primary_bundle_contract["suite_roles"],
        },
        "sensitivity_bundles": [
            {
                "data_version": version,
                "manifest": str(bundle.manifest_path),
                "manifest_sha256": _file_sha256(bundle.manifest_path),
                "events_sha256": _file_sha256(bundle.events_path),
                "bundle_role": bundle.manifest["bundle_role"],
                "required_suite_roles": bundle.manifest["required_suite_roles"],
                "suite_roles": bundle.manifest["suite_roles"],
            }
            for version, bundle in sorted(sensitivity_by_version.items())
        ],
        "pairing_unit": "persistent anchor/scenario intersection after seed collapse",
        "rows": len(sensitivity),
        "artifact": artifact_manifest["data_version_sensitivity.csv"],
        "analysis_input_manifest": {
            "path": str(analysis_input_path),
            "bytes": analysis_input_path.stat().st_size,
            "sha256": _file_sha256(analysis_input_path),
        },
    }
    _atomic_json(
        sensitivity_manifest,
        output / "data_version_sensitivity_manifest.json",
    )
    analysis_manifest = {
        "schema_version": "frozen_analysis_manifest_v2",
        "status": completion_gate["status"],
        "complete": completion_gate["complete"],
        "completion_gate": completion_gate,
        "source_manifest": str(inputs.manifest_path),
        "source_manifest_sha256": _file_sha256(inputs.manifest_path),
        "predictions": str(inputs.predictions_path),
        "predictions_sha256": _file_sha256(inputs.predictions_path),
        "event_metrics": str(inputs.events_path),
        "event_metrics_sha256": _file_sha256(inputs.events_path),
        "design_freeze": str(inputs.design_path),
        "design_freeze_sha256": _file_sha256(inputs.design_path),
        "bootstrap_replicates": inputs.statistics.bootstrap_replicates,
        "bootstrap_seed": inputs.statistics.bootstrap_seed,
        "confidence_level": inputs.statistics.confidence,
        "analysis_code_identity": analysis_code_identity,
        "analysis_builder_identity": analysis_code_identity["frozen_analysis_builder"],
        "analysis_input_manifest": {
            "path": str(analysis_input_path),
            "bytes": analysis_input_path.stat().st_size,
            "sha256": _file_sha256(analysis_input_path),
            "input_manifest_sha256": analysis_input_manifest["input_manifest_sha256"],
        },
        "required_analysis_domains": list(REQUIRED_ANALYSIS_DOMAINS),
        "primary_bundle_contract": primary_bundle_contract,
        "sensitivity_bundle_contracts": {
            version: _validate_bundle_roles(bundle.manifest)
            for version, bundle in sorted(sensitivity_by_version.items())
        },
        "aggregation_order": [
            "average_training_seeds_within_model_mask_anchor",
            "cluster_by_anchor_or_event_episode_and_year",
            "compare_models_or_gap_lengths",
        ],
        "application_threshold_status": (
            "not_declared"
            if inputs.statistics.application_criteria is None
            else "declared"
        ),
        "information_estimand_contracts": {
            "operational_dropout": {
                "required_coalitions": [
                    combination_label(value)
                    for value in OPERATIONAL_INFORMATION_COMBINATIONS
                ],
                "required_coalition_count": len(OPERATIONAL_INFORMATION_COMBINATIONS),
                "exact_shapley": True,
                "pairwise_interactions": True,
            },
            "retrained_upper_bound": {
                "required_coalitions": [
                    combination_label(value)
                    for value in RETRAINED_INFORMATION_COMBINATIONS
                ],
                "required_coalition_count": len(RETRAINED_INFORMATION_COMBINATIONS),
                "contrast_reference": "S0",
                "exact_shapley": False,
                "pairwise_interactions": False,
            },
            "pooling_rule": "never_mix_estimands",
        },
        "data_version_inputs": {
            version: {
                "status": (
                    "available"
                    if version == inputs.statistics.primary_data_version
                    or version in sensitivity_by_version
                    else "unavailable"
                ),
                "reason": (
                    None
                    if version == inputs.statistics.primary_data_version
                    or version in sensitivity_by_version
                    else "no separate hash-verified frozen bundle was supplied"
                ),
            }
            for version in (
                inputs.statistics.primary_data_version,
                *inputs.statistics.sensitivity_data_versions,
            )
        },
        "data_version_sensitivity_manifest": str(
            output / "data_version_sensitivity_manifest.json"
        ),
        "artifacts": artifact_manifest,
    }
    _atomic_json(analysis_manifest, output / "analysis_manifest.json")
    return analysis_manifest


__all__ = [
    "EVIDENCE_FIELDS",
    "FIXED_ARTIFACTS",
    "OPERATIONAL_INFORMATION_COMBINATIONS",
    "RETRAINED_INFORMATION_COMBINATIONS",
    "FrontierArtifacts",
    "FrozenInputs",
    "FrozenStatistics",
    "OverlapArtifacts",
    "analyze_calibration",
    "analyze_data_version_sensitivity",
    "analyze_event_pairs",
    "analyze_frontiers",
    "analyze_information",
    "analyze_resilience_outputs",
    "audit_prediction_overlap",
    "build_analysis_code_identity",
    "guarded_model_skill",
    "load_frozen_inputs",
    "load_frozen_inputs_from_manifest",
    "load_frozen_statistics",
    "one_hinge_breakpoint",
    "require_clean_analysis_code",
    "run_frozen_analysis",
    "uncertainty_by_difficulty",
]
