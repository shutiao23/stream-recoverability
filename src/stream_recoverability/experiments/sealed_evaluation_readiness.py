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
ONCE_LOCK_SCHEMA = "t2_t7_sealed_evaluate_once_lock_v1"
CLAIM_ACKNOWLEDGEMENT = "claim-once-before-any-sealed-read"
DEFAULT_DESIGN = REPOSITORY_ROOT / "configs/design_freeze_v9.yaml"
DEFAULT_AGGREGATION = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v1/aggregation/readiness_manifest.json"
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
PROTECTED_IMPLEMENTATION_PATHS = (
    "src/stream_recoverability/experiments/sealed_evaluation_readiness.py",
    "scripts/80_audit_sealed_evaluation_readiness.py",
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
    value = _load_json(path)
    blockers: list[str] = []
    if value.get("manifest_schema") != "t2_v91_aggregation_readiness_v1":
        blockers.append("aggregation_manifest_schema_mismatch")
    if value.get("status") != "ready":
        blockers.append("t2_primary_aggregation_not_ready")
    expected = value.get("expected_result_records")
    observed = value.get("observed_result_records")
    if not _valid_positive_int(expected) or observed != expected:
        blockers.append("t2_result_set_not_complete")
    if value.get("sealed_temperature_records_read") is not False:
        blockers.append("aggregation_does_not_affirm_sealed_unread")
    return {
        "path": path.resolve().relative_to(REPOSITORY_ROOT).as_posix(),
        "sha256": _sha256(path),
        "manifest_schema": value.get("manifest_schema"),
        "status": value.get("status"),
        "expected_result_records": expected,
        "observed_result_records": observed,
    }, blockers


def _model_contract(
    path: Path,
    *,
    threshold_contract_sha256: str,
    open_aggregation_manifest_sha256: str,
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
        "predictor_manifest",
        "geometry_manifest",
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
                and digest != open_aggregation_manifest_sha256
            ):
                blockers.append("model_freeze_open_aggregation_binding_mismatch")
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
        "input_bindings": bindings if isinstance(bindings, Mapping) else None,
    }
    return contract, blockers, bound_paths


def build_readiness_manifest(
    *,
    design_path: str | Path = DEFAULT_DESIGN,
    aggregation_path: str | Path = DEFAULT_AGGREGATION,
    model_freeze_path: str | Path = DEFAULT_MODEL_FREEZE,
    huc8_registry_root: str | Path = DEFAULT_HUC8_REGISTRY / "sealed",
    foen_registry_root: str | Path = DEFAULT_FOEN_REGISTRY,
    once_lock_path: str | Path = DEFAULT_ONCE_LOCK,
) -> dict[str, Any]:
    """Audit pre-unseal state without touching any sealed object or value."""

    design = Path(design_path)
    aggregation = Path(aggregation_path)
    model_freeze = Path(model_freeze_path)
    once_lock = Path(once_lock_path)
    blockers: list[str] = []
    threshold = _threshold_contract(design)
    aggregation_contract, aggregation_blockers = _aggregation_contract(aggregation)
    model_contract, model_blockers, model_bound_paths = _model_contract(
        model_freeze,
        threshold_contract_sha256=threshold["threshold_contract_sha256"],
        open_aggregation_manifest_sha256=aggregation_contract["sha256"],
    )
    blockers.extend(aggregation_blockers)
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

    required_paths = [design, aggregation]
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
    "DEFAULT_OUTPUT",
    "MODEL_FREEZE_SCHEMA",
    "ONCE_LOCK_SCHEMA",
    "READINESS_SCHEMA",
    "SealedReadinessError",
    "build_readiness_manifest",
    "claim_evaluate_once",
    "write_readiness_manifest",
]
