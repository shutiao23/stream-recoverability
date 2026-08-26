"""Fail-closed readiness gate for the first T2/T7 sealed evaluation.

This module deliberately has no unseal, vault-read, outcome-parser, or scoring
function.  It reads only public lock files, result/model manifests, Git
metadata, and the strict byte-registry JSON sidecars written during custody.
The registry is the sole source used to inventory sealed availability before
the evaluate-once lock is claimed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from stream_recoverability.data.foen_sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_FOEN_REGISTRY,
)
from stream_recoverability.data.foen_sealed_corpus import LockedFoenCatalog
from stream_recoverability.data.sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_HUC8_REGISTRY,
)
from stream_recoverability.data.sealed_corpus import LockedV3Catalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
READINESS_SCHEMA = "t2_t7_sealed_preunseal_readiness_v1"
MODEL_FREEZE_SCHEMA = "t2_t7_sealed_model_freeze_v1"
MODEL_FREEZE_READINESS_SCHEMA = "t2_t7_sealed_model_freeze_readiness_v1"
ONCE_LOCK_SCHEMA = "t2_t7_sealed_evaluate_once_lock_v1"
CLAIM_ACKNOWLEDGEMENT = "claim-once-before-any-sealed-read"
DEFAULT_DESIGN = REPOSITORY_ROOT / "configs/design_freeze_v9.yaml"
DEFAULT_AGGREGATION = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/aggregation/aggregation_manifest.json"
)
DEFAULT_V4_WORKLOAD = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/workload_manifest.json"
)
DEFAULT_PRE_SCORE_FREEZE = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/pre_score_freeze_manifest.json"
)
DEFAULT_POST_T2_INPUT_BINDING = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2/post_t2_input_binding.json"
)
DEFAULT_OPERATOR_PREDICTOR = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2/operator_predictor_manifest.json"
)
DEFAULT_MODEL_ROSTER = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2/model_roster.json"
)
DEFAULT_ANALYSIS_CODE = (
    REPOSITORY_ROOT
    / "src/stream_recoverability/experiments/sealed_evaluator_scaffold.py"
)
DEFAULT_MODEL_FREEZE = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/model_freeze_manifest.json"
)
DEFAULT_ONCE_LOCK = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/evaluate_once_lock.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/preunseal_readiness_manifest.json"
)
DEFAULT_MODEL_FREEZE_READINESS = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/model_freeze_readiness_manifest.json"
)
PROTECTED_IMPLEMENTATION_PATHS = (
    "src/stream_recoverability/experiments/sealed_evaluation_readiness.py",
    "scripts/80_audit_sealed_evaluation_readiness.py",
    "scripts/91_build_sealed_model_freeze.py",
    "tests/test_sealed_evaluation_readiness.py",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SealedReadinessError(RuntimeError):
    """Raised when an evaluate-once claim is not exactly authorized."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required metadata is not a regular file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON mapping: {path}")
    return value


def _valid_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _registry_files(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"registry root is not a regular directory: {root}")
    files = sorted(root.glob("*/*.json"))
    unexpected = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix != ".json"
    )
    if unexpected:
        raise ValueError("registry contains non-JSON files")
    if any(path.is_symlink() for path in files):
        raise ValueError("registry JSON cannot be a symlink")
    return files


def _recorded_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_recorded_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise SealedReadinessError("registry inventory lacks its audited root")
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def _audit_huc8_registry(root: Path) -> dict[str, Any]:
    catalog = LockedV3Catalog.load()
    expected_requests = catalog.requests("sealed")
    expected = {
        (request.network_id, request.site_id): request for request in expected_requests
    }
    rows: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for path in _registry_files(root):
        row = _load_json(path)
        identity = (str(row.get("network_id")), str(row.get("site_id")))
        request = expected.get(identity)
        if request is None or identity in identities:
            raise ValueError(f"unexpected or duplicate HUC8 registry identity: {identity}")
        identities.add(identity)
        required = {
            "registry_schema": "huc8_corpus_byte_registry_v1",
            "network_id": request.network_id,
            "role": "sealed",
            "site_id": request.site_id,
            "request_start": request.start,
            "request_end": request.end,
            "split_sha256": catalog.split_sha256,
            "storage_class": "sealed_write_only_vault",
            "content_parsed": False,
            "sealed_outcomes_opened": False,
            "qc_permitted": False,
            "reused_registry": False,
        }
        drift = {key for key, value in required.items() if row.get(key) != value}
        if drift or set(row) != {
            *required,
            "sha256",
            "byte_count",
        }:
            raise ValueError(f"HUC8 registry schema/metadata drift: {path}")
        if not isinstance(row.get("sha256"), str) or not _SHA256.fullmatch(
            str(row["sha256"])
        ):
            raise ValueError(f"invalid HUC8 registry SHA-256: {path}")
        if not _valid_positive_int(row.get("byte_count")):
            raise ValueError(f"invalid HUC8 registry byte count: {path}")
        rows.append(row)
    missing = sorted(set(expected).difference(identities))
    if missing:
        raise ValueError(f"HUC8 registry is incomplete: {len(missing)} requests missing")
    network_ids = sorted({network_id for network_id, _ in identities})
    if len(network_ids) != 44:
        raise ValueError(f"HUC8 sealed network count is {len(network_ids)}, expected 44")
    return {
        "provider": "usgs_nwis",
        "registry_root": _recorded_path(root),
        "eligibility_basis": "locked_catalog_v3_huc8_metadata_only",
        "availability_basis": "strict_registry_metadata_only_vault_not_opened_or_statted",
        "n_networks": len(network_ids),
        "n_objects": len(rows),
        "network_ids": network_ids,
        "registry_records_sha256": _canonical_sha256(rows),
        "complete": len(rows) == len(expected_requests),
    }


def _audit_foen_registry(root: Path) -> dict[str, Any]:
    catalog = LockedFoenCatalog.load()
    expected_requests = catalog.requests()
    expected = {
        (request.network_id, request.site_id, request.year): request
        for request in expected_requests
    }
    rows: list[dict[str, Any]] = []
    identities: set[tuple[str, str, int]] = set()
    for path in _registry_files(root):
        row = _load_json(path)
        year = row.get("request_year")
        if isinstance(year, bool) or not isinstance(year, int):
            raise TypeError(f"invalid FOEN request year: {path}")
        identity = (str(row.get("network_id")), str(row.get("site_id")), year)
        request = expected.get(identity)
        if request is None or identity in identities:
            raise ValueError(f"unexpected or duplicate FOEN registry identity: {identity}")
        identities.add(identity)
        required = {
            "registry_schema": "foen_sealed_byte_registry_v2",
            "provider": "foen",
            "network_id": request.network_id,
            "role": "sealed",
            "site_id": request.site_id,
            "request_year": request.year,
            "request_start": request.start,
            "request_end_exclusive": request.end_exclusive,
            "split_sha256": catalog.split_sha256,
            "catalog_sha256": catalog.catalog_sha256,
            "query_template_sha256": catalog.query_template_sha256,
            "storage_class": "foen_sealed_write_only_provider_vault",
            "content_parsed": False,
            "json_decoded": False,
            "value_fields_inspected": False,
            "sealed_outcomes_opened": False,
            "qc_permitted": False,
            "reused_registry": False,
        }
        if set(row) != {*required, "response_sha256", "byte_count"} or any(
            row.get(key) != value for key, value in required.items()
        ):
            raise ValueError(f"FOEN registry schema/metadata drift: {path}")
        if not isinstance(row.get("response_sha256"), str) or not _SHA256.fullmatch(
            str(row["response_sha256"])
        ):
            raise ValueError(f"invalid FOEN registry SHA-256: {path}")
        if not _valid_positive_int(row.get("byte_count")):
            raise ValueError(f"invalid FOEN registry byte count: {path}")
        rows.append(row)
    missing = sorted(set(expected).difference(identities))
    if missing:
        raise ValueError(f"FOEN registry is incomplete: {len(missing)} requests missing")
    network_ids = sorted({network_id for network_id, _, _ in identities})
    if len(network_ids) != 10:
        raise ValueError(f"FOEN sealed network count is {len(network_ids)}, expected 10")
    return {
        "provider": "foen",
        "registry_root": _recorded_path(root),
        "eligibility_basis": "prospective_station_membership_metadata_only_daily_eligibility_unknown",
        "availability_basis": "strict_registry_metadata_only_vault_not_opened_or_statted",
        "n_networks": len(network_ids),
        "n_objects": len(rows),
        "network_ids": network_ids,
        "registry_records_sha256": _canonical_sha256(rows),
        "complete": len(rows) == len(expected_requests),
        "daily_qc_eligibility": "unknown_until_authorized_once_evaluation",
    }


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _git_binding(paths: Sequence[Path]) -> tuple[dict[str, Any], list[str]]:
    head_result = _git("rev-parse", "HEAD")
    head = head_result.stdout.strip() if head_result.returncode == 0 else ""
    blockers: list[str] = []
    bindings: list[dict[str, str]] = []
    relative_paths = list(PROTECTED_IMPLEMENTATION_PATHS)
    for path in paths:
        try:
            relative_paths.append(path.resolve().relative_to(REPOSITORY_ROOT).as_posix())
        except ValueError:
            blockers.append(f"required_input_outside_repository:{path}")
    for relative in dict.fromkeys(relative_paths):
        tracked = _git("ls-files", "--error-unmatch", "--", relative)
        if tracked.returncode != 0:
            blockers.append(f"required_path_not_committed:{relative}")
            continue
        committed = _git("rev-parse", f"HEAD:{relative}")
        worktree = _git("hash-object", "--", relative)
        if committed.returncode != 0 or worktree.returncode != 0:
            blockers.append(f"required_path_identity_unavailable:{relative}")
            continue
        committed_blob = committed.stdout.strip()
        worktree_blob = worktree.stdout.strip()
        if committed_blob != worktree_blob:
            blockers.append(f"required_path_differs_from_head:{relative}")
        bindings.append(
            {
                "path": relative,
                "head_blob": committed_blob,
                "worktree_blob": worktree_blob,
            }
        )
    if not head:
        blockers.append("git_head_unavailable")
    return {
        "head_commit": head or None,
        "required_paths": bindings,
        "all_required_paths_committed_unchanged": not blockers,
    }, blockers


def _threshold_contract(design_path: Path) -> dict[str, Any]:
    design = yaml.safe_load(design_path.read_text(encoding="utf-8"))
    if not isinstance(design, dict):
        raise TypeError("design freeze must be a YAML mapping")
    t7 = design.get("t7_sealed_confirmatory")
    endpoints = design.get("decision_endpoints")
    if not isinstance(t7, dict) or not isinstance(endpoints, dict):
        raise TypeError("design freeze lacks T7 or decision endpoint threshold mappings")
    expected = {
        "evaluate_once": True,
        "numeric_thresholds_preregistered": True,
        "sealed_absolute_floor": 40,
    }
    if any(t7.get(key) != value for key, value in expected.items()):
        raise ValueError("T7 evaluate-once threshold contract drift")
    return {
        "design_sha256": _sha256(design_path),
        "t7": t7,
        "decision_endpoints": endpoints,
        "threshold_contract_sha256": _canonical_sha256(
            {"t7": t7, "decision_endpoints": endpoints}
        ),
    }


def _aggregation_contract(path: Path) -> tuple[dict[str, Any], list[str]]:
    if path.is_symlink() or not path.is_file():
        return (
            {"path": _recorded_path(path), "exists": False, "sha256": None},
            [
                "open_aggregation_manifest_missing",
                "t2_primary_aggregation_not_ready",
                "t2_result_set_not_complete",
            ],
        )
    value = _load_json(path)
    blockers: list[str] = []
    if value.get("manifest_schema") != "t2_v91_result_aggregation_v4":
        blockers.append("aggregation_manifest_schema_mismatch")
    if value.get("status") != "complete":
        blockers.append("t2_primary_aggregation_not_ready")
    expected = value.get("expected_item_records")
    observed = value.get("observed_item_records")
    if not _valid_positive_int(expected) or observed != expected:
        blockers.append("t2_result_set_not_complete")
    if value.get("completeness") != "complete":
        blockers.append("t2_result_set_not_complete")
    if value.get("formal_result_generated") is not True:
        blockers.append("t2_formal_result_not_generated")
    if value.get("all_executions_successful") is not True:
        blockers.append("t2_open_execution_not_successful")
    if value.get("sealed_temperature_records_read") is not False:
        blockers.append("aggregation_does_not_affirm_sealed_unread")
    return {
        "path": _recorded_path(path),
        "exists": True,
        "sha256": _sha256(path),
        "manifest_schema": value.get("manifest_schema"),
        "status": value.get("status"),
        "expected_item_records": expected,
        "observed_item_records": observed,
        "expected_result_records": expected,
        "observed_result_records": observed,
    }, blockers


def _post_t2_contract(
    path: Path, *, workload_sha256: str | None, aggregation_sha256: str | None
) -> tuple[dict[str, Any], list[str]]:
    if path.is_symlink() or not path.is_file():
        return (
            {"path": _recorded_path(path), "exists": False, "sha256": None},
            ["post_t2_input_binding_missing"],
        )
    value = _load_json(path)
    blockers: list[str] = []
    required = {
        "manifest_schema": "t2_v91_v4_post_t2_input_binding_v2",
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            blockers.append(f"post_t2_input_binding_contract_mismatch:{key}")
    if workload_sha256 is not None and value.get(
        "workload_manifest_sha256"
    ) != workload_sha256:
        blockers.append("post_t2_workload_binding_mismatch")
    if aggregation_sha256 is not None and value.get(
        "aggregation_manifest_sha256"
    ) != aggregation_sha256:
        blockers.append("post_t2_aggregation_binding_mismatch")
    return {
        "path": _recorded_path(path),
        "exists": True,
        "sha256": _sha256(path),
        "manifest_schema": value.get("manifest_schema"),
        "status": value.get("status"),
        "observed_item_records": value.get("observed_item_records"),
    }, blockers


def _model_contract(
    path: Path,
    *,
    threshold_contract_sha256: str,
    open_aggregation_manifest_sha256: str | None,
    post_t2_input_binding_sha256: str | None,
    expected_binding_paths: Mapping[str, Path],
) -> tuple[dict[str, Any], list[str], list[Path]]:
    if not path.is_file():
        return (
            {"path": path.as_posix(), "exists": False},
            ["sealed_model_freeze_manifest_missing"],
            [],
        )
    value = _load_json(path)
    blockers: list[str] = []
    bound_paths: list[Path] = []
    if value.get("manifest_schema") != MODEL_FREEZE_SCHEMA:
        blockers.append("sealed_model_freeze_schema_mismatch")
    if value.get("status") != "frozen_before_unseal":
        blockers.append("sealed_model_not_frozen_before_unseal")
    if value.get("sealed_outcomes_opened") is not False:
        blockers.append("model_freeze_does_not_affirm_sealed_unread")
    if value.get("model_selection_complete") is not True:
        blockers.append("sealed_model_selection_not_complete")
    if value.get("postfreeze_retuning_permitted") is not False:
        blockers.append("sealed_model_freeze_does_not_forbid_retuning")
    if value.get("postfreeze_retuning") is not False:
        blockers.append("sealed_model_freeze_postfreeze_retuning_mismatch")
    current_head = _git("rev-parse", "HEAD")
    if (
        current_head.returncode != 0
        or value.get("head_commit") != current_head.stdout.strip()
    ):
        blockers.append("sealed_model_freeze_head_mismatch")
    models = value.get("frozen_models")
    if (
        not isinstance(models, list)
        or not models
        or any(not isinstance(item, str) or not item for item in models)
        or len(set(models)) != len(models)
    ):
        blockers.append("sealed_model_roster_is_not_nonempty_unique_names")
    if value.get("threshold_contract_sha256") != threshold_contract_sha256:
        blockers.append("model_freeze_threshold_contract_sha_mismatch")

    bindings = value.get("input_bindings")
    required_bindings = {
        "open_aggregation_manifest",
        "post_t2_input_binding",
        "workload_manifest",
        "pre_score_freeze_manifest",
        "predictor_manifest",
        "model_roster",
        "analysis_code",
    }
    if not isinstance(bindings, Mapping) or set(bindings) != required_bindings:
        blockers.append("model_freeze_input_binding_inventory_mismatch")
    else:
        for label in sorted(required_bindings):
            binding = bindings[label]
            if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}:
                blockers.append(f"model_freeze_invalid_binding:{label}")
                continue
            relative = binding.get("path")
            digest = binding.get("sha256")
            if (
                not isinstance(relative, str)
                or not relative
                or Path(relative).is_absolute()
                or "sealed" in {part.lower() for part in Path(relative).parts}
            ):
                blockers.append(f"model_freeze_unsafe_binding_path:{label}")
                continue
            candidate = REPOSITORY_ROOT / relative
            expected_path = expected_binding_paths.get(label)
            if expected_path is None or candidate.resolve() != expected_path.resolve():
                blockers.append(f"model_freeze_unexpected_binding_path:{label}")
                continue
            if candidate.is_symlink() or not candidate.is_file():
                blockers.append(f"model_freeze_binding_missing:{label}")
                continue
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                blockers.append(f"model_freeze_invalid_binding_sha256:{label}")
                continue
            if _sha256(candidate) != digest:
                blockers.append(f"model_freeze_binding_sha256_mismatch:{label}")
                continue
            if (
                label == "open_aggregation_manifest"
                and open_aggregation_manifest_sha256 is not None
                and digest != open_aggregation_manifest_sha256
            ):
                blockers.append("model_freeze_open_aggregation_binding_mismatch")
                continue
            if (
                label == "post_t2_input_binding"
                and post_t2_input_binding_sha256 is not None
                and digest != post_t2_input_binding_sha256
            ):
                blockers.append("model_freeze_post_t2_binding_mismatch")
                continue
            bound_paths.append(candidate)
    contract = {
        "path": path.resolve().relative_to(REPOSITORY_ROOT).as_posix(),
        "exists": True,
        "sha256": _sha256(path),
        "manifest_schema": value.get("manifest_schema"),
        "status": value.get("status"),
        "frozen_models": models if isinstance(models, list) else None,
        "threshold_contract_sha256": value.get("threshold_contract_sha256"),
        "head_commit": value.get("head_commit"),
        "input_bindings": bindings if isinstance(bindings, Mapping) else None,
    }
    return contract, blockers, bound_paths


def _repo_input_binding(
    label: str, path: Path
) -> tuple[dict[str, str] | None, list[str]]:
    """Bind one regular open-only repository file without reading sealed bytes."""

    try:
        relative = path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return None, [f"model_freeze_input_outside_repository:{label}"]
    if any(part.lower() == "sealed" for part in Path(relative).parts):
        return None, [f"model_freeze_unsafe_input_path:{label}"]
    if path.is_symlink() or not path.is_file():
        return None, [f"model_freeze_input_missing:{label}"]
    return {"path": relative, "sha256": _sha256(path)}, []


def _bound_artifact_path(manifest_path: Path, record: object) -> Path | None:
    if not isinstance(record, Mapping):
        return None
    raw = record.get("path")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
        if not path.exists():
            candidate = (REPOSITORY_ROOT / raw).resolve()
            if candidate.exists():
                path = candidate
    return path


def build_model_freeze_readiness(
    *,
    workload_path: str | Path = DEFAULT_V4_WORKLOAD,
    pre_score_freeze_path: str | Path = DEFAULT_PRE_SCORE_FREEZE,
    open_aggregation_path: str | Path = DEFAULT_AGGREGATION,
    post_t2_input_binding_path: str | Path = DEFAULT_POST_T2_INPUT_BINDING,
    predictor_manifest_path: str | Path = DEFAULT_OPERATOR_PREDICTOR,
    model_roster_path: str | Path = DEFAULT_MODEL_ROSTER,
    analysis_code_path: str | Path = DEFAULT_ANALYSIS_CODE,
    design_path: str | Path = DEFAULT_DESIGN,
    model_freeze_path: str | Path = DEFAULT_MODEL_FREEZE,
) -> dict[str, Any]:
    """Audit every open-only input needed to freeze the sealed model roster.

    Missing formal open results are ordinary blockers.  This function never
    creates the model freeze and never resolves, stats, or reads a sealed
    object.  The returned candidate becomes creatable only when every direct
    and recursively bound input is committed and identical to ``HEAD``.
    """

    paths = {
        "workload_manifest": Path(workload_path),
        "pre_score_freeze_manifest": Path(pre_score_freeze_path),
        "open_aggregation_manifest": Path(open_aggregation_path),
        "post_t2_input_binding": Path(post_t2_input_binding_path),
        "predictor_manifest": Path(predictor_manifest_path),
        "model_roster": Path(model_roster_path),
        "analysis_code": Path(analysis_code_path),
    }
    blockers: list[str] = []
    bindings: dict[str, dict[str, str]] = {}
    documents: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        binding, path_blockers = _repo_input_binding(label, path)
        blockers.extend(path_blockers)
        if binding is None:
            continue
        bindings[label] = binding
        if label != "analysis_code":
            try:
                documents[label] = _load_json(path)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                blockers.append(f"model_freeze_input_invalid_json:{label}")

    threshold: dict[str, Any] | None = None
    try:
        threshold = _threshold_contract(Path(design_path))
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        blockers.append("threshold_contract_invalid_or_missing")

    workload = documents.get("workload_manifest")
    pre_score = documents.get("pre_score_freeze_manifest")
    aggregation = documents.get("open_aggregation_manifest")
    post_t2 = documents.get("post_t2_input_binding")
    predictor = documents.get("predictor_manifest")
    roster = documents.get("model_roster")

    if workload is not None:
        required = {
            "manifest_schema": "t2_v91_open_role_workload_v4",
            "execution_allowed": True,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        }
        for key, expected in required.items():
            if workload.get(key) != expected:
                blockers.append(f"final_v4_workload_contract_mismatch:{key}")
    if pre_score is not None:
        required = {
            "manifest_schema": "t2_v91_v4_pre_score_freeze_bundle_v1",
            "status": "complete_outcome_blind_pre_score_freeze",
            "selection_uses_outcomes": False,
            "v4_results_read": False,
            "achieved_skill_read": False,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        }
        for key, expected in required.items():
            if pre_score.get(key) != expected:
                blockers.append(f"pre_score_freeze_contract_mismatch:{key}")
    if workload is not None and pre_score is not None:
        workload_pre_score = workload.get("pre_score_freeze")
        if not isinstance(workload_pre_score, Mapping) or workload_pre_score.get(
            "sha256"
        ) != bindings["pre_score_freeze_manifest"]["sha256"]:
            blockers.append("final_v4_workload_pre_score_binding_mismatch")

    recursive_paths: list[Path] = []
    if aggregation is not None:
        required = {
            "manifest_schema": "t2_v91_result_aggregation_v4",
            "status": "complete",
            "completeness": "complete",
            "formal_result_generated": True,
            "all_executions_successful": True,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        }
        for key, expected in required.items():
            if aggregation.get(key) != expected:
                blockers.append(f"open_aggregation_contract_mismatch:{key}")
        if workload is not None and aggregation.get(
            "workload_manifest_sha256"
        ) != bindings["workload_manifest"]["sha256"]:
            blockers.append("open_aggregation_workload_binding_mismatch")
        if pre_score is not None and aggregation.get(
            "pre_score_freeze_sha256"
        ) != bindings["pre_score_freeze_manifest"]["sha256"]:
            blockers.append("open_aggregation_pre_score_binding_mismatch")
        merged = _bound_artifact_path(
            paths["open_aggregation_manifest"], aggregation.get("merged_item_results")
        )
        merged_record = aggregation.get("merged_item_results")
        if (
            merged is None
            or not isinstance(merged_record, Mapping)
            or merged.is_symlink()
            or not merged.is_file()
            or _sha256(merged) != merged_record.get("sha256")
        ):
            blockers.append("open_aggregation_merged_results_binding_invalid")
        else:
            recursive_paths.append(merged)

    if post_t2 is not None:
        required = {
            "manifest_schema": "t2_v91_v4_post_t2_input_binding_v2",
            "status": "complete",
            "completeness": "complete",
            "formal_result_generated": True,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        }
        for key, expected in required.items():
            if post_t2.get(key) != expected:
                blockers.append(f"post_t2_input_binding_contract_mismatch:{key}")
        if workload is not None and post_t2.get(
            "workload_manifest_sha256"
        ) != bindings["workload_manifest"]["sha256"]:
            blockers.append("post_t2_workload_binding_mismatch")
        if aggregation is not None and post_t2.get(
            "aggregation_manifest_sha256"
        ) != bindings["open_aggregation_manifest"]["sha256"]:
            blockers.append("post_t2_aggregation_binding_mismatch")
        for record_label in ("primary_y_table", "item_results"):
            record = post_t2.get(record_label)
            artifact = _bound_artifact_path(paths["post_t2_input_binding"], record)
            if (
                artifact is None
                or not isinstance(record, Mapping)
                or artifact.is_symlink()
                or not artifact.is_file()
                or _sha256(artifact) != record.get("sha256")
            ):
                blockers.append(f"post_t2_bound_artifact_invalid:{record_label}")
            else:
                recursive_paths.append(artifact)

    if predictor is not None:
        required = {
            "manifest_schema": "t2_v91_v4_train_only_operator_predictions_v1",
            "outcome_rows_read_during_fit": False,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        }
        for key, expected in required.items():
            if predictor.get(key) != expected:
                blockers.append(f"operator_predictor_contract_mismatch:{key}")
        prediction_path = _bound_artifact_path(
            paths["predictor_manifest"],
            {
                "path": predictor.get("predictions_path"),
                "sha256": predictor.get("predictions_sha256"),
            },
        )
        if (
            prediction_path is None
            or prediction_path.is_symlink()
            or not prediction_path.is_file()
            or _sha256(prediction_path) != predictor.get("predictions_sha256")
        ):
            blockers.append("operator_predictor_table_binding_invalid")
        else:
            recursive_paths.append(prediction_path)
    if pre_score is not None and predictor is not None:
        predictor_record = pre_score.get("predictor_manifest")
        if not isinstance(predictor_record, Mapping) or predictor_record.get(
            "sha256"
        ) != bindings["predictor_manifest"]["sha256"]:
            blockers.append("pre_score_operator_predictor_binding_mismatch")

    frozen_models: list[str] = []
    if roster is not None:
        selected = roster.get("selected_models")
        new_roster = (
            roster.get("manifest_schema") == "t2_v91_v4_open_model_roster_v1"
            and roster.get("status") == "model_selection_complete"
            and roster.get("model_selection_complete") is True
            and roster.get("post_selection_retuning") is False
            and roster.get("sealed_outcomes_opened") is False
            and post_t2 is not None
            and roster.get("post_t2_input_binding_sha256")
            == bindings["post_t2_input_binding"]["sha256"]
        )
        legacy_finalized_roster = (
            roster.get("schema_version") == "finalized_model_roster_v1"
            and roster.get("finalized") is True
        )
        if (
            not (new_roster or legacy_finalized_roster)
            or not isinstance(selected, list)
            or not selected
            or any(not isinstance(item, str) or not item for item in selected)
            or len(set(selected)) != len(selected)
        ):
            blockers.append("model_roster_not_finalized_unique_nonempty")
        else:
            frozen_models = list(selected)

    git_paths = [Path(design_path), *paths.values(), *recursive_paths]
    git_binding, git_blockers = _git_binding(git_paths)
    blockers.extend(git_blockers)
    head = git_binding.get("head_commit")
    candidate = None
    if threshold is not None:
        candidate = {
            "manifest_schema": MODEL_FREEZE_SCHEMA,
            "status": "frozen_before_unseal",
            "head_commit": head,
            "model_selection_complete": bool(frozen_models),
            "postfreeze_retuning": False,
            "postfreeze_retuning_permitted": False,
            "sealed_outcomes_opened": False,
            "sealed_temperature_records_read": False,
            "open_results_only": True,
            "frozen_models": frozen_models,
            "threshold_contract_sha256": threshold["threshold_contract_sha256"],
            "design_freeze": {
                "path": _recorded_path(Path(design_path)),
                "sha256": threshold["design_sha256"],
            },
            "input_bindings": bindings,
        }
    unique = sorted(set(blockers))
    if (
        candidate is None
        or candidate.get("model_selection_complete") is not True
    ) and "model_roster_not_finalized_unique_nonempty" not in unique:
        unique.append("model_selection_incomplete")
        unique.sort()
    if set(bindings) != {
        "workload_manifest",
        "pre_score_freeze_manifest",
        "open_aggregation_manifest",
        "post_t2_input_binding",
        "predictor_manifest",
        "model_roster",
        "analysis_code",
    }:
        unique.append("model_freeze_input_binding_inventory_incomplete")
        unique = sorted(set(unique))
    ready = not unique
    return {
        "manifest_schema": MODEL_FREEZE_READINESS_SCHEMA,
        "status": "ready_to_create" if ready else "blocked",
        "ready_to_create_model_freeze": ready,
        "model_freeze_created": Path(model_freeze_path).is_file(),
        "model_freeze_path": _recorded_path(Path(model_freeze_path)),
        "model_selection_complete": bool(frozen_models),
        "postfreeze_retuning": False,
        "sealed_outcomes_opened": False,
        "sealed_paths_traversed": False,
        "formal_evidence": False,
        "threshold_contract": threshold,
        "input_bindings": bindings,
        "git_commit_before_model_freeze": git_binding,
        "candidate_model_freeze": candidate,
        "blockers": unique,
    }


def create_model_freeze_manifest(
    readiness: Mapping[str, Any], *, output_path: str | Path = DEFAULT_MODEL_FREEZE
) -> dict[str, Any]:
    """Exclusively install the already-audited model freeze, or fail closed."""

    if readiness.get("manifest_schema") != MODEL_FREEZE_READINESS_SCHEMA:
        raise SealedReadinessError("model-freeze readiness schema mismatch")
    if (
        readiness.get("ready_to_create_model_freeze") is not True
        or readiness.get("blockers") != []
    ):
        raise SealedReadinessError("model-freeze readiness is blocked")
    candidate = readiness.get("candidate_model_freeze")
    git_binding = readiness.get("git_commit_before_model_freeze")
    if not isinstance(candidate, Mapping) or not isinstance(git_binding, Mapping):
        raise SealedReadinessError("model-freeze readiness lacks its candidate")
    current_head = _git("rev-parse", "HEAD")
    if (
        current_head.returncode != 0
        or current_head.stdout.strip() != candidate.get("head_commit")
        or git_binding.get("all_required_paths_committed_unchanged") is not True
    ):
        raise SealedReadinessError("model-freeze HEAD changed after readiness")
    for binding in git_binding.get("required_paths") or []:
        if not isinstance(binding, Mapping):
            raise SealedReadinessError("invalid model-freeze Git binding")
        relative = binding.get("path")
        expected = binding.get("head_blob")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise SealedReadinessError("invalid model-freeze Git identity")
        committed = _git("rev-parse", f"HEAD:{relative}")
        worktree = _git("hash-object", "--", relative)
        if (
            committed.returncode != 0
            or worktree.returncode != 0
            or committed.stdout.strip() != expected
            or worktree.stdout.strip() != expected
        ):
            raise SealedReadinessError(
                f"model-freeze input changed after readiness: {relative}"
            )
    payload = (json.dumps(dict(candidate), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError as error:
        if output.read_bytes() == payload:
            return dict(candidate)
        raise SealedReadinessError("model-freeze manifest is create-once") from error
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return dict(candidate)


def build_readiness_manifest(
    *,
    design_path: str | Path = DEFAULT_DESIGN,
    v4_workload_path: str | Path = DEFAULT_V4_WORKLOAD,
    pre_score_freeze_path: str | Path = DEFAULT_PRE_SCORE_FREEZE,
    aggregation_path: str | Path = DEFAULT_AGGREGATION,
    post_t2_input_binding_path: str | Path = DEFAULT_POST_T2_INPUT_BINDING,
    predictor_manifest_path: str | Path = DEFAULT_OPERATOR_PREDICTOR,
    model_roster_path: str | Path = DEFAULT_MODEL_ROSTER,
    analysis_code_path: str | Path = DEFAULT_ANALYSIS_CODE,
    model_freeze_path: str | Path = DEFAULT_MODEL_FREEZE,
    huc8_registry_root: str | Path = DEFAULT_HUC8_REGISTRY / "sealed",
    foen_registry_root: str | Path = DEFAULT_FOEN_REGISTRY,
    once_lock_path: str | Path = DEFAULT_ONCE_LOCK,
) -> dict[str, Any]:
    """Audit pre-unseal state without touching any sealed object or value."""

    design = Path(design_path)
    workload = Path(v4_workload_path)
    aggregation = Path(aggregation_path)
    post_t2 = Path(post_t2_input_binding_path)
    model_freeze = Path(model_freeze_path)
    once_lock = Path(once_lock_path)
    blockers: list[str] = []
    threshold = _threshold_contract(design)
    aggregation_contract, aggregation_blockers = _aggregation_contract(aggregation)
    workload_sha: str | None = None
    if workload.is_file():
        workload_sha = _sha256(workload)
    post_t2_contract, post_t2_blockers = _post_t2_contract(
        post_t2,
        workload_sha256=workload_sha,
        aggregation_sha256=aggregation_contract.get("sha256"),
    )
    model_contract, model_blockers, model_bound_paths = _model_contract(
        model_freeze,
        threshold_contract_sha256=threshold["threshold_contract_sha256"],
        open_aggregation_manifest_sha256=aggregation_contract["sha256"],
        post_t2_input_binding_sha256=post_t2_contract["sha256"],
        expected_binding_paths={
            "workload_manifest": workload,
            "pre_score_freeze_manifest": Path(pre_score_freeze_path),
            "open_aggregation_manifest": aggregation,
            "post_t2_input_binding": post_t2,
            "predictor_manifest": Path(predictor_manifest_path),
            "model_roster": Path(model_roster_path),
            "analysis_code": Path(analysis_code_path),
        },
    )
    blockers.extend(aggregation_blockers)
    blockers.extend(post_t2_blockers)
    blockers.extend(model_blockers)
    try:
        huc8 = _audit_huc8_registry(Path(huc8_registry_root))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        huc8 = {"complete": False, "error": str(error)}
        blockers.append("huc8_44_registry_contract_failed")
    try:
        foen = _audit_foen_registry(Path(foen_registry_root))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        foen = {"complete": False, "error": str(error)}
        blockers.append("foen_10_registry_contract_failed")
    if once_lock.exists():
        blockers.append("evaluate_once_lock_already_exists")

    required_paths = [design]
    if workload.is_file():
        required_paths.append(workload)
    if aggregation.is_file():
        required_paths.append(aggregation)
    if post_t2.is_file():
        required_paths.append(post_t2)
    if model_freeze.is_file():
        required_paths.append(model_freeze)
        required_paths.extend(model_bound_paths)
    git_binding, git_blockers = _git_binding(required_paths)
    blockers.extend(git_blockers)
    ready = not blockers
    return {
        "manifest_schema": READINESS_SCHEMA,
        "status": "ready" if ready else "blocked",
        "ready_for_unseal": ready,
        "formal_evidence": False,
        "sealed_outcomes_opened": False,
        "sealed_objects_opened_or_statted_by_audit": False,
        "registry_metadata_read_only": True,
        "threshold_contract": threshold,
        "aggregation_contract": aggregation_contract,
        "post_t2_input_binding_contract": post_t2_contract,
        "model_freeze_contract": model_contract,
        "sealed_registry_inventory": {
            "north_america_huc8": huc8,
            "foen_non_north_america": foen,
            "n_networks_total": int(huc8.get("n_networks") or 0)
            + int(foen.get("n_networks") or 0),
            "eligibility_warning": (
                "registry completeness is custody availability, not post-unseal "
                "temperature QC eligibility"
            ),
        },
        "git_commit_before_unseal": git_binding,
        "evaluate_once": {
            "lock_path": once_lock.as_posix(),
            "lock_absent": not once_lock.exists(),
            "claim_acknowledgement": CLAIM_ACKNOWLEDGEMENT,
            "lock_must_be_exclusively_created_before_any_sealed_read": True,
            "rerun_after_started_or_failed_is_forbidden": True,
        },
        "blockers": sorted(set(blockers)),
    }


def write_readiness_manifest(value: Mapping[str, Any], output_path: str | Path) -> Path:
    """Atomically write a metadata-only readiness report."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, output)
    return output


def claim_evaluate_once(
    readiness: Mapping[str, Any],
    *,
    lock_path: str | Path,
    acknowledgement: str,
) -> dict[str, Any]:
    """Exclusively claim one evaluation; never reads or names a vault object.

    This is only the irreversible *start ledger*.  It is intentionally not an
    unseal operation.  The caller must create it before a separately reviewed
    evaluator obtains any sealed-byte capability.
    """

    if acknowledgement != CLAIM_ACKNOWLEDGEMENT:
        raise SealedReadinessError("exact evaluate-once acknowledgement required")
    if readiness.get("manifest_schema") != READINESS_SCHEMA:
        raise SealedReadinessError("readiness manifest schema mismatch")
    if readiness.get("ready_for_unseal") is not True or readiness.get("blockers") != []:
        raise SealedReadinessError("readiness gate is not unconditionally ready")
    inventory = readiness.get("sealed_registry_inventory")
    if not isinstance(inventory, Mapping):
        raise SealedReadinessError("readiness lacks a sealed registry inventory")
    recorded_huc8 = inventory.get("north_america_huc8")
    recorded_foen = inventory.get("foen_non_north_america")
    if not isinstance(recorded_huc8, Mapping) or not isinstance(
        recorded_foen, Mapping
    ):
        raise SealedReadinessError("readiness lacks both provider registry inventories")
    try:
        observed_huc8 = _audit_huc8_registry(
            _resolve_recorded_path(recorded_huc8.get("registry_root"))
        )
        observed_foen = _audit_foen_registry(
            _resolve_recorded_path(recorded_foen.get("registry_root"))
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SealedReadinessError(
            f"sealed registry re-audit failed before once claim: {error}"
        ) from error
    if dict(recorded_huc8) != observed_huc8:
        raise SealedReadinessError(
            "HUC8 registry changed after the readiness audit"
        )
    if dict(recorded_foen) != observed_foen:
        raise SealedReadinessError("FOEN registry changed after the readiness audit")
    expected_total = observed_huc8["n_networks"] + observed_foen["n_networks"]
    if inventory.get("n_networks_total") != expected_total:
        raise SealedReadinessError("sealed registry total changed after readiness audit")
    git_binding = readiness.get("git_commit_before_unseal")
    if not isinstance(git_binding, Mapping) or git_binding.get(
        "all_required_paths_committed_unchanged"
    ) is not True:
        raise SealedReadinessError("commit-before-unseal contract is not satisfied")
    recorded_head = git_binding.get("head_commit")
    current_head = _git("rev-parse", "HEAD")
    if (
        not isinstance(recorded_head, str)
        or current_head.returncode != 0
        or current_head.stdout.strip() != recorded_head
    ):
        raise SealedReadinessError("Git HEAD changed after the readiness audit")
    required_paths = git_binding.get("required_paths")
    if not isinstance(required_paths, list) or not required_paths:
        raise SealedReadinessError("readiness lacks committed required-path bindings")
    for binding in required_paths:
        if not isinstance(binding, Mapping):
            raise SealedReadinessError("invalid required-path Git binding")
        relative = binding.get("path")
        expected_blob = binding.get("head_blob")
        if not isinstance(relative, str) or not isinstance(expected_blob, str):
            raise SealedReadinessError("invalid required-path Git identity")
        committed = _git("rev-parse", f"HEAD:{relative}")
        worktree = _git("hash-object", "--", relative)
        if (
            committed.returncode != 0
            or worktree.returncode != 0
            or committed.stdout.strip() != expected_blob
            or worktree.stdout.strip() != expected_blob
        ):
            raise SealedReadinessError(
                f"required path changed after readiness audit: {relative}"
            )
    payload = {
        "manifest_schema": ONCE_LOCK_SCHEMA,
        "status": "started_before_any_sealed_read",
        "head_commit": git_binding.get("head_commit"),
        "readiness_manifest_sha256": _canonical_sha256(dict(readiness)),
        "sealed_outcomes_opened_at_lock_creation": False,
        "rerun_permitted": False,
    }
    output = Path(lock_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise SealedReadinessError("evaluate-once lock already exists") from error
    return payload


__all__ = [
    "CLAIM_ACKNOWLEDGEMENT",
    "DEFAULT_MODEL_FREEZE_READINESS",
    "DEFAULT_OUTPUT",
    "MODEL_FREEZE_READINESS_SCHEMA",
    "MODEL_FREEZE_SCHEMA",
    "ONCE_LOCK_SCHEMA",
    "READINESS_SCHEMA",
    "SealedReadinessError",
    "build_model_freeze_readiness",
    "build_readiness_manifest",
    "claim_evaluate_once",
    "create_model_freeze_manifest",
    "write_readiness_manifest",
]
