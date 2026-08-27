"""Capability-gated scaffold for the single sealed T2/T7 evaluation.

The default preflight entry point is metadata-only: it never creates the
evaluate-once lock and never reads vault bytes.  Production object reads are
available only after an irreversible evaluate-once lock is claimed and
``evaluate_production_sealed_once`` is invoked exactly once.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.foen_sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_FOEN_REGISTRY,
)
from stream_recoverability.data.foen_sealed_corpus import (
    DEFAULT_SEALED_VAULT as DEFAULT_FOEN_VAULT,
)
from stream_recoverability.data.foen_sealed_corpus import LockedFoenCatalog
from stream_recoverability.data.ingest_qc import (
    VERDICT_ACCEPTED,
    VERDICT_ACCEPTED_WITH_FLAGS,
    qc_station_series,
)
from stream_recoverability.data.sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_HUC8_REGISTRY,
)
from stream_recoverability.data.sealed_corpus import (
    DEFAULT_SEALED_VAULT as DEFAULT_HUC8_VAULT,
)
from stream_recoverability.data.sealed_corpus import LockedV3Catalog

from .sealed_evaluation_readiness import (
    MODEL_FREEZE_SCHEMA,
    ONCE_LOCK_SCHEMA,
    READINESS_SCHEMA,
    _audit_foen_registry,
    _audit_huc8_registry,
    build_readiness_manifest,
)
from .t2_primary_aggregation_v2 import INPUT_BINDING_SCHEMA
from .t2_workload_v4 import V4_RUNNER_CONTRACT_VERSION, V4_WORKLOAD_SCHEMA

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT_SCHEMA = "t2_t7_sealed_evaluator_preflight_v1"
FIXTURE_LEDGER_SCHEMA = "t2_t7_synthetic_fixture_ledger_v1"
FIXTURE_RESULT_SCHEMA = "t2_t7_synthetic_fixture_qc_result_v1"
PRODUCTION_LEDGER_SCHEMA = "t2_t7_sealed_evaluate_once_run_ledger_v1"
PRODUCTION_RESULT_SCHEMA = "t2_t7_sealed_qc_result_v1"
DEFAULT_SEALED_QC_OUTPUT = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1"
)
DEFAULT_READINESS = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/preunseal_readiness_manifest.json"
)
DEFAULT_ONCE_LOCK = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/evaluate_once_lock.json"
)
DEFAULT_MODEL_FREEZE = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/model_freeze_manifest.json"
)
DEFAULT_V4_WORKLOAD = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/workload_manifest_v3.json"
)
DEFAULT_V4_RESULT_BINDING = (
    REPOSITORY_ROOT
    / "results/framework/t2_recovery_benchmark_v4/primary_aggregation_v2/post_t2_input_binding.json"
)
DEFAULT_PREFLIGHT_OUTPUT = (
    REPOSITORY_ROOT
    / "results/framework/t2_sealed_confirmatory_v1/evaluator_scaffold_preflight.json"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACCEPTED_VERDICTS = frozenset({VERDICT_ACCEPTED, VERDICT_ACCEPTED_WITH_FLAGS})
PROTECTED_EVALUATOR_PATHS = (
    "src/stream_recoverability/experiments/sealed_evaluator_scaffold.py",
    "scripts/90_preflight_sealed_evaluator.py",
    "scripts/92_claim_sealed_evaluate_once.py",
    "scripts/93_run_sealed_evaluate_once.py",
    "tests/test_sealed_evaluator_scaffold.py",
)


class SealedEvaluatorError(RuntimeError):
    """Raised before or during the non-retryable sealed evaluation."""


@dataclass(frozen=True)
class SealedObjectRef:
    """Opaque object identity derived from a public strict-registry sidecar."""

    provider: str
    network_id: str
    site_id: str
    request_year: int | None
    expected_sha256: str
    expected_byte_count: int
    request_start: str | None = None
    request_end: str | None = None
    request_end_inclusive: bool = False

    @property
    def key(self) -> str:
        year = "all" if self.request_year is None else str(self.request_year)
        return f"{self.provider}/{self.network_id}/{self.site_id}/{year}"


class MemorySealedObjectReader:
    """Fixture-only reader; it has no filesystem path or vault knowledge."""

    def __init__(self, objects: Mapping[str, bytes]) -> None:
        self._objects = dict(objects)
        self.read_keys: list[str] = []

    def read_object(self, reference: SealedObjectRef) -> bytes:
        if reference.key in self.read_keys:
            raise SealedEvaluatorError("mock object requested more than once")
        self.read_keys.append(reference.key)
        try:
            return self._objects[reference.key]
        except KeyError as error:
            raise SealedEvaluatorError(
                f"mock object is absent: {reference.key}"
            ) from error


def _date_only(value: str | None) -> str:
    if not value:
        return ""
    return str(value)[:10]


def vault_path_for_reference(
    reference: SealedObjectRef,
    *,
    huc8_vault: Path = DEFAULT_HUC8_VAULT,
    foen_vault: Path = DEFAULT_FOEN_VAULT,
) -> Path:
    """Resolve one locked registry object to its immutable vault path."""

    if reference.provider == "usgs_nwis":
        start = _date_only(reference.request_start)
        end = _date_only(reference.request_end)
        stem = f"{reference.site_id}_{start}_{end}"
        return huc8_vault / reference.network_id / f"{stem}.sealed"
    if reference.provider == "foen":
        if reference.request_year is None:
            raise SealedEvaluatorError("FOEN reference lacks request_year")
        stem = f"{reference.site_id}_{reference.request_year:04d}"
        return foen_vault / reference.network_id / f"{stem}.sealed"
    raise SealedEvaluatorError(f"unsupported sealed provider: {reference.provider}")


class FilesystemSealedObjectReader:
    """Production vault reader authorized only after evaluate-once lock claim."""

    def __init__(
        self,
        *,
        huc8_vault: str | Path = DEFAULT_HUC8_VAULT,
        foen_vault: str | Path = DEFAULT_FOEN_VAULT,
    ) -> None:
        self.huc8_vault = Path(huc8_vault)
        self.foen_vault = Path(foen_vault)
        self.read_keys: list[str] = []

    def read_object(self, reference: SealedObjectRef) -> bytes:
        if reference.key in self.read_keys:
            raise SealedEvaluatorError("sealed object requested more than once")
        object_path = vault_path_for_reference(
            reference,
            huc8_vault=self.huc8_vault,
            foen_vault=self.foen_vault,
        )
        if object_path.is_symlink() or not object_path.is_file():
            raise SealedEvaluatorError(f"sealed vault object missing: {reference.key}")
        body = object_path.read_bytes()
        if len(body) != reference.expected_byte_count:
            raise SealedEvaluatorError(f"sealed byte-count mismatch: {reference.key}")
        if hashlib.sha256(body).hexdigest() != reference.expected_sha256:
            raise SealedEvaluatorError(f"sealed SHA-256 mismatch: {reference.key}")
        self.read_keys.append(reference.key)
        return body


_FIXTURE_EXECUTION_TOKEN = object()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_mapping(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SealedEvaluatorError(f"required metadata is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SealedEvaluatorError(f"cannot read metadata {path}: {error}") from error
    if not isinstance(value, dict):
        raise SealedEvaluatorError(f"metadata is not a mapping: {path}")
    return value


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _resolve_recorded(value: object) -> Path:
    path = Path(str(value or ""))
    return (path if path.is_absolute() else REPOSITORY_ROOT / path).resolve()


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _model_binding(
    model: Mapping[str, Any], label: str, expected_path: Path, expected_sha: str
) -> bool:
    bindings = model.get("input_bindings")
    if not isinstance(bindings, Mapping):
        return False
    binding = bindings.get(label)
    if not isinstance(binding, Mapping):
        return False
    return (
        str(binding.get("path")) == _relative(expected_path)
        and str(binding.get("sha256")) == expected_sha
    )


def build_evaluator_preflight(
    *,
    readiness_path: str | Path = DEFAULT_READINESS,
    once_lock_path: str | Path = DEFAULT_ONCE_LOCK,
    model_freeze_path: str | Path = DEFAULT_MODEL_FREEZE,
    v4_workload_path: str | Path = DEFAULT_V4_WORKLOAD,
    v4_result_binding_path: str | Path = DEFAULT_V4_RESULT_BINDING,
    run_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Revalidate authorization metadata without resolving or stating a vault."""

    readiness_file = Path(readiness_path).resolve()
    lock_file = Path(once_lock_path).resolve()
    model_file = Path(model_freeze_path).resolve()
    workload_file = Path(v4_workload_path).resolve()
    result_file = Path(v4_result_binding_path).resolve()
    ledger_file = (
        Path(run_ledger_path).resolve()
        if run_ledger_path is not None
        else lock_file.with_name("evaluate_once_run_ledger.json")
    )
    blockers: list[str] = []

    try:
        readiness = _load_mapping(readiness_file)
    except SealedEvaluatorError:
        readiness = {}
        blockers.append("readiness_manifest_missing_or_invalid")
    try:
        lock = _load_mapping(lock_file)
    except SealedEvaluatorError:
        lock = {}
        blockers.append("evaluate_once_lock_missing_or_invalid")
    post_claim_readiness: dict[str, Any] | None = None
    if lock.get("manifest_schema") == ONCE_LOCK_SCHEMA and lock.get(
        "status"
    ) == "started_before_any_sealed_read":
        post_claim_readiness = build_readiness_manifest(
            once_lock_path=lock_file, for_post_claim_evaluation=True
        )
    readiness_for_gate = post_claim_readiness or readiness
    if readiness_for_gate and (
        readiness_for_gate.get("manifest_schema") != READINESS_SCHEMA
        or readiness_for_gate.get("ready_for_unseal") is not True
        or readiness_for_gate.get("blockers") != []
    ):
        blockers.append("readiness_gate_not_unconditionally_ready")
    if lock and (
        lock.get("manifest_schema") != ONCE_LOCK_SCHEMA
        or lock.get("status") != "started_before_any_sealed_read"
        or lock.get("rerun_permitted") is not False
        or lock.get("sealed_outcomes_opened_at_lock_creation") is not False
    ):
        blockers.append("evaluate_once_lock_contract_mismatch")
    if (
        readiness_for_gate
        and lock
        and lock.get("readiness_manifest_sha256") != _canonical_sha256(readiness_for_gate)
    ):
        blockers.append("evaluate_once_lock_readiness_sha_mismatch")
    readiness_once = readiness.get("evaluate_once")
    if readiness and (
        not isinstance(readiness_once, Mapping)
        or _resolve_recorded(readiness_once.get("lock_path")) != lock_file
    ):
        blockers.append("readiness_once_lock_path_mismatch")

    try:
        model = _load_mapping(model_file)
    except SealedEvaluatorError:
        model = {}
        blockers.append("model_freeze_missing_or_invalid")
    if model and (
        model.get("manifest_schema") != MODEL_FREEZE_SCHEMA
        or model.get("status") != "frozen_before_unseal"
        or model.get("model_selection_complete") is not True
        or model.get("postfreeze_retuning_permitted") is not False
        or model.get("sealed_outcomes_opened") is not False
    ):
        blockers.append("model_freeze_contract_mismatch")
    readiness_model = readiness.get("model_freeze_contract")
    if (
        readiness
        and model
        and (
            not isinstance(readiness_model, Mapping)
            or _resolve_recorded(readiness_model.get("path")) != model_file
            or readiness_model.get("sha256") != _sha256_file(model_file)
        )
    ):
        blockers.append("readiness_model_freeze_binding_mismatch")

    try:
        workload = _load_mapping(workload_file)
    except SealedEvaluatorError:
        workload = {}
        blockers.append("formal_v4_workload_missing_or_invalid")
    workload_sha = _sha256_file(workload_file) if workload else ""
    if workload and (
        workload.get("manifest_schema") != V4_WORKLOAD_SCHEMA
        or workload.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
        or workload.get("sealed_temperature_records_read") is not False
        or workload.get("sealed_input_roots_allowed") != []
    ):
        blockers.append("formal_v4_workload_contract_mismatch")

    try:
        result = _load_mapping(result_file)
    except SealedEvaluatorError:
        result = {}
        blockers.append("complete_v4_result_binding_missing_or_invalid")
    result_sha = _sha256_file(result_file) if result else ""
    if result and (
        result.get("manifest_schema") != INPUT_BINDING_SCHEMA
        or result.get("status") != "complete"
        or result.get("completeness") != "complete"
        or result.get("formal_result_generated") is not True
        or result.get("sealed_temperature_records_read") is not False
        or result.get("workload_manifest_sha256") != workload_sha
        or result.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
    ):
        blockers.append("complete_v4_result_binding_contract_mismatch")

    if (
        model
        and workload
        and not _model_binding(model, "workload_manifest", workload_file, workload_sha)
    ):
        blockers.append("model_freeze_v4_workload_binding_mismatch")
    if (
        model
        and result
        and not _model_binding(model, "post_t2_input_binding", result_file, result_sha)
    ):
        blockers.append("model_freeze_v4_result_binding_mismatch")

    current_head_result = _git("rev-parse", "HEAD")
    current_head = current_head_result.stdout.strip()
    recorded_head = lock.get("head_commit")
    git_binding = (readiness_for_gate or readiness).get("git_commit_before_unseal")
    if (
        current_head_result.returncode != 0
        or not current_head
        or recorded_head != current_head
        or not isinstance(git_binding, Mapping)
        or git_binding.get("head_commit") != current_head
        or git_binding.get("all_required_paths_committed_unchanged") is not True
    ):
        blockers.append("head_binding_mismatch")
    if isinstance(git_binding, Mapping):
        required = git_binding.get("required_paths")
        if not isinstance(required, list) or not required:
            blockers.append("head_required_path_bindings_missing")
        else:
            for binding in required:
                if not isinstance(binding, Mapping):
                    blockers.append("head_required_path_binding_invalid")
                    continue
                relative = binding.get("path")
                expected = binding.get("head_blob")
                if not isinstance(relative, str) or not isinstance(expected, str):
                    blockers.append("head_required_path_binding_invalid")
                    continue
                committed = _git("rev-parse", f"HEAD:{relative}")
                worktree = _git("hash-object", "--", relative)
                if (
                    committed.returncode != 0
                    or worktree.returncode != 0
                    or committed.stdout.strip() != expected
                    or worktree.stdout.strip() != expected
                ):
                    blockers.append(f"head_required_path_drift:{relative}")
    for relative in PROTECTED_EVALUATOR_PATHS:
        tracked = _git("ls-files", "--error-unmatch", "--", relative)
        committed = _git("rev-parse", f"HEAD:{relative}")
        worktree = _git("hash-object", "--", relative)
        if (
            tracked.returncode != 0
            or committed.returncode != 0
            or worktree.returncode != 0
            or committed.stdout.strip() != worktree.stdout.strip()
        ):
            blockers.append(f"evaluator_path_not_committed_unchanged:{relative}")
    if ledger_file.exists():
        blockers.append("evaluate_once_run_ledger_already_exists_no_rerun")

    unique = sorted(set(blockers))
    production_reader_available = True
    authorized = (
        not unique
        and lock.get("manifest_schema") == ONCE_LOCK_SCHEMA
        and lock.get("status") == "started_before_any_sealed_read"
        and not ledger_file.exists()
    )
    return {
        "manifest_schema": PREFLIGHT_SCHEMA,
        "status": "authorized" if authorized else "blocked",
        "authorized_for_object_reads": authorized,
        "production_reader_available": production_reader_available,
        "formal_evidence": False,
        "dry_run_metadata_only": not authorized,
        "evaluate_once_lock_claimed_by_preflight": False,
        "vault_path_resolved_or_statted": False,
        "sealed_objects_read": 0,
        "production_evaluate_once_semantics_implemented": True,
        "bindings": {
            "readiness": {
                "path": _relative(readiness_file),
                "sha256": _sha256_file(readiness_file) if readiness else None,
            },
            "once_lock": {
                "path": _relative(lock_file),
                "sha256": _sha256_file(lock_file) if lock else None,
            },
            "model_freeze": {
                "path": _relative(model_file),
                "sha256": _sha256_file(model_file) if model else None,
            },
            "v4_workload": {
                "path": _relative(workload_file),
                "sha256": workload_sha or None,
            },
            "v4_result_binding": {
                "path": _relative(result_file),
                "sha256": result_sha or None,
            },
            "head_commit": current_head or None,
        },
        "run_ledger_path": _relative(ledger_file),
        "future_output_contract": {
            "sealed_qc_attrition_required": True,
            "eligible_network_inventory_required": True,
            "v4_workload_and_result_bindings_required": True,
            "production_evaluate_once_runner_required": True,
            "minimum_stations_per_network": 3,
            "minimum_common_qualified_years": 8,
            "minimum_distinct_approved_days_per_station_year": 300,
        },
        "blockers": unique,
    }


def write_preflight(value: Mapping[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, output)
    return output


def registered_object_references(
    readiness: Mapping[str, Any],
) -> tuple[SealedObjectRef, ...]:
    """Replay both locked catalogs and strict public registries into references."""

    inventory = readiness.get("sealed_registry_inventory")
    if not isinstance(inventory, Mapping):
        raise SealedEvaluatorError("readiness lacks sealed registry inventory")

    recorded_huc8 = inventory.get("north_america_huc8")
    recorded_foen = inventory.get("foen_non_north_america")
    if not isinstance(recorded_huc8, Mapping) or not isinstance(
        recorded_foen, Mapping
    ):
        raise SealedEvaluatorError("readiness lacks both provider inventories")
    huc8_root = (DEFAULT_HUC8_REGISTRY / "sealed").resolve()
    foen_root = DEFAULT_FOEN_REGISTRY.resolve()
    try:
        observed_huc8 = _audit_huc8_registry(huc8_root)
        observed_foen = _audit_foen_registry(foen_root)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SealedEvaluatorError(f"strict registry replay failed: {error}") from error
    if dict(recorded_huc8) != observed_huc8:
        raise SealedEvaluatorError("HUC8 registry differs from readiness and lock")
    if dict(recorded_foen) != observed_foen:
        raise SealedEvaluatorError("FOEN registry differs from readiness and lock")
    if inventory.get("n_networks_total") != 54:
        raise SealedEvaluatorError("sealed candidate inventory must contain 54 networks")

    huc8_catalog = LockedV3Catalog.load()
    huc8_expected = {
        (request.network_id, request.site_id): request
        for request in huc8_catalog.requests("sealed")
    }
    huc8_rows = [_load_mapping(path) for path in sorted(huc8_root.glob("*/*.json"))]
    if {
        (str(row["network_id"]), str(row["site_id"])) for row in huc8_rows
    } != set(huc8_expected):
        raise SealedEvaluatorError("HUC8 registry is not the complete locked request set")

    foen_catalog = LockedFoenCatalog.load()
    foen_expected = {
        (request.network_id, request.site_id, request.year): request
        for request in foen_catalog.requests()
    }
    foen_rows = [_load_mapping(path) for path in sorted(foen_root.glob("*/*.json"))]
    if {
        (str(row["network_id"]), str(row["site_id"]), int(row["request_year"]))
        for row in foen_rows
    } != set(foen_expected):
        raise SealedEvaluatorError("FOEN registry is not the complete locked request set")

    references: list[SealedObjectRef] = []
    for row in huc8_rows:
        request = huc8_expected[(str(row["network_id"]), str(row["site_id"]))]
        references.append(
            SealedObjectRef(
                provider="usgs_nwis",
                network_id=request.network_id,
                site_id=request.site_id,
                request_year=None,
                expected_sha256=str(row["sha256"]),
                expected_byte_count=int(row["byte_count"]),
                request_start=request.start,
                request_end=request.end,
                request_end_inclusive=True,
            )
        )
    for row in foen_rows:
        identity = (
            str(row["network_id"]),
            str(row["site_id"]),
            int(row["request_year"]),
        )
        request = foen_expected[identity]
        references.append(
            SealedObjectRef(
                provider="foen",
                network_id=request.network_id,
                site_id=request.site_id,
                request_year=request.year,
                expected_sha256=str(row["response_sha256"]),
                expected_byte_count=int(row["byte_count"]),
                request_start=request.start,
                request_end=request.end_exclusive,
                request_end_inclusive=False,
            )
        )
    keys = [reference.key for reference in references]
    if len(references) != 2880:
        raise SealedEvaluatorError("sealed registry replay did not yield 2880 objects")
    if len(keys) != len(set(keys)):
        raise SealedEvaluatorError("duplicate sealed object registry identity")
    return tuple(references)


def _timestamp_in_request(
    value: object,
    *,
    request_start: str | None,
    request_end: str | None,
    request_end_inclusive: bool,
) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if not isinstance(timestamp, pd.Timestamp) or pd.isna(timestamp):
        raise SealedEvaluatorError("provider row has an invalid timestamp")
    if request_start is not None:
        start = pd.to_datetime(request_start, utc=True, errors="coerce")
        if not isinstance(start, pd.Timestamp) or pd.isna(start) or timestamp < start:
            raise SealedEvaluatorError("provider timestamp precedes request range")
    if request_end is not None:
        end = pd.to_datetime(request_end, utc=True, errors="coerce")
        if not isinstance(end, pd.Timestamp) or pd.isna(end):
            raise SealedEvaluatorError("request range has an invalid end")
        if request_end_inclusive:
            if timestamp.normalize() > end.normalize():
                raise SealedEvaluatorError("provider timestamp follows request range")
        elif timestamp >= end:
            raise SealedEvaluatorError("provider timestamp follows request range")
    return timestamp


def parse_huc8_nwis_response(
    payload: bytes,
    *,
    site_id: str,
    request_start: str | None = None,
    request_end: str | None = None,
) -> pd.DataFrame:
    """Parse one NWIS JSON response into the provider-neutral QC columns."""

    try:
        document = json.loads(payload.decode("utf-8"))
        series = document["value"]["timeSeries"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SealedEvaluatorError("invalid NWIS JSON response") from error
    rows: list[dict[str, Any]] = []
    if not isinstance(series, list):
        raise SealedEvaluatorError("NWIS timeSeries is not a list")
    for item in series:
        if not isinstance(item, Mapping):
            raise SealedEvaluatorError("NWIS timeSeries row is not a mapping")
        source = item.get("sourceInfo") or {}
        codes = source.get("siteCode") or []
        observed_site = str((codes[0] if codes else {}).get("value", ""))
        variable = item.get("variable") or {}
        variable_codes = variable.get("variableCode") or []
        parameters = {str(code.get("value", "")) for code in variable_codes}
        if observed_site != str(site_id) or "00010" not in parameters:
            raise SealedEvaluatorError("NWIS response identity/parameter mismatch")
        unit = str((variable.get("unit") or {}).get("unitCode", ""))
        normalized_unit = unit.strip().lower().replace("°", "").replace("degrees", "deg")
        if normalized_unit not in {"deg c", "degc", "c", "celsius"}:
            raise SealedEvaluatorError("NWIS temperature unit is not Celsius")
        options = (variable.get("options") or {}).get("option") or []
        statistics = {
            str(option.get("optionCode", ""))
            for option in options
            if isinstance(option, Mapping)
            and str(option.get("name", "")).strip().lower() == "statistic"
        }
        if "00003" not in statistics:
            raise SealedEvaluatorError("NWIS response is not daily mean statistic 00003")
        for block in item.get("values") or []:
            for point in block.get("value") or []:
                if not isinstance(point, Mapping):
                    raise SealedEvaluatorError("NWIS value row is not a mapping")
                timestamp = _timestamp_in_request(
                    point.get("dateTime"),
                    request_start=request_start,
                    request_end=request_end,
                    request_end_inclusive=True,
                )
                rows.append(
                    {
                        "site_id": str(site_id),
                        "date": timestamp,
                        "temperature_c": point.get("value"),
                        "approval_code": ",".join(
                            str(value) for value in (point.get("qualifiers") or [])
                        ),
                    }
                )
    return _normalize_provider_rows(rows, provider="usgs_nwis")


def parse_foen_response(
    payload: bytes,
    *,
    site_id: str,
    request_year: int | None = None,
    request_start: str | None = None,
    request_end: str | None = None,
) -> pd.DataFrame:
    """Parse one FOEN daily-mean GraphQL response into neutral QC columns."""

    try:
        document = json.loads(payload.decode("utf-8"))
        if document.get("errors"):
            raise SealedEvaluatorError("FOEN response contains GraphQL errors")
        rows = document["data"]["water"]["observations"]["data_1day_mean"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SealedEvaluatorError("invalid FOEN GraphQL response") from error
    if not isinstance(rows, list):
        raise SealedEvaluatorError("FOEN daily observations are not a list")
    if request_year is not None:
        request_start = request_start or f"{request_year:04d}-01-01T00:00:00Z"
        request_end = request_end or f"{request_year + 1:04d}-01-01T00:00:00Z"
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SealedEvaluatorError("FOEN observation row is not a mapping")
        station = row.get("station") or {}
        if str(station.get("no", "")) != str(site_id):
            raise SealedEvaluatorError("FOEN response station mismatch")
        if str(row.get("parameterName", "")) != "WT":
            raise SealedEvaluatorError("FOEN response parameter mismatch")
        unit = str(row.get("unitSymbol", "")).strip().lower().replace("°", "")
        if unit not in {"c", "degc", "celsius"}:
            raise SealedEvaluatorError("FOEN temperature unit is not Celsius")
        state = row.get("releaseState")
        approval = "A" if state in {2, 3, "2", "3"} else "P"
        timestamp = _timestamp_in_request(
            row.get("timestamp"),
            request_start=request_start,
            request_end=request_end,
            request_end_inclusive=False,
        )
        if request_year is not None and timestamp.year != request_year:
            raise SealedEvaluatorError("FOEN timestamp differs from request year")
        normalized.append(
            {
                "site_id": str(site_id),
                "date": timestamp,
                "temperature_c": row.get("value"),
                "approval_code": approval,
            }
        )
    return _normalize_provider_rows(normalized, provider="foen")


def _normalize_provider_rows(
    rows: Sequence[Mapping[str, Any]], *, provider: str
) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=["site_id", "date", "temperature_c", "approval_code"],
    )
    if frame.empty:
        return frame.assign(provider=pd.Series(dtype=str))
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise SealedEvaluatorError("provider response contains an invalid timestamp")
    frame["date"] = frame["date"].dt.normalize()
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
    frame["provider"] = provider
    for _, group in frame.groupby(["site_id", "date"], sort=False, dropna=False):
        if len(group) > 1 and (
            group["temperature_c"].nunique(dropna=False) != 1
            or group["approval_code"].astype(str).nunique(dropna=False) != 1
        ):
            raise SealedEvaluatorError("conflicting duplicate provider calendar day")
    return frame.drop_duplicates(["site_id", "date"]).reset_index(drop=True)


def _network_qc(
    observations: pd.DataFrame, references: Sequence[SealedObjectRef]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    station_rows: list[dict[str, Any]] = []
    membership: dict[str, set[str]] = defaultdict(set)
    for ref in references:
        membership[ref.network_id].add(ref.site_id)
    for (network_id, site_id), group in observations.groupby(
        ["network_id", "site_id"], sort=True
    ):
        row = qc_station_series(
            group["date"],
            group["temperature_c"],
            site_id=str(site_id),
            approval_codes=group["approval_code"],
        )
        row["network_id"] = str(network_id)
        row["provider"] = str(group["provider"].iloc[0])
        station_rows.append(row)
    station_qc = pd.DataFrame(
        station_rows,
        columns=[
            "site_id",
            "n_raw",
            "n_sentinel",
            "n_out_of_range",
            "n_provisional_dropped",
            "n_constant_run_days",
            "n_jump",
            "qualified_years",
            "verdict",
            "notes",
            "network_id",
            "provider",
        ],
    )
    attrition: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for network_id in sorted(membership):
        members = sorted(membership[network_id])
        accepted = set(
            station_qc.loc[
                station_qc["network_id"].eq(network_id)
                & station_qc["verdict"].isin(_ACCEPTED_VERDICTS),
                "site_id",
            ].astype(str)
        )
        filtered = observations.loc[
            observations["network_id"].eq(network_id)
            & observations["site_id"].astype(str).isin(accepted)
            & observations["approval_code"]
            .astype(str)
            .str.lower()
            .isin({"a", "approved"})
            & observations["temperature_c"].between(-5.0, 45.0, inclusive="both")
        ].copy()
        filtered["year"] = filtered["date"].dt.year
        counts = (
            filtered.drop_duplicates(["site_id", "date"])
            .groupby(["site_id", "year"])
            .size()
        )
        qualified_by_site = {
            site: {
                int(year)
                for (observed_site, year), count in counts.items()
                if observed_site == site and count >= 300
            }
            for site in accepted
        }
        selected_sites: tuple[str, ...] = ()
        common_years: list[int] = []
        # The locked rule is existence of an exact >=3-station common-year
        # subset, not intersection over every otherwise accepted station.
        for size in range(len(accepted), 2, -1):
            candidates: list[tuple[tuple[str, ...], list[int]]] = []
            for subset in combinations(sorted(accepted), size):
                years = sorted(
                    set.intersection(*(qualified_by_site[site] for site in subset))
                )
                if len(years) >= 8:
                    candidates.append((subset, years))
            if candidates:
                selected_sites, common_years = min(
                    candidates, key=lambda item: (-len(item[1]), item[0])
                )
                break
        reasons: list[str] = []
        if len(accepted) < 3:
            reasons.append("fewer_than_3_qc_accepted_stations")
        if len(common_years) < 8:
            reasons.append("fewer_than_8_common_300_day_years")
        record = {
            "network_id": network_id,
            "provider": (
                str(filtered["provider"].iloc[0])
                if not filtered.empty
                else next(
                    ref.provider for ref in references if ref.network_id == network_id
                )
            ),
            "n_locked_stations": len(members),
            "n_qc_accepted_stations": len(accepted),
            "n_selected_common_stations": len(selected_sites),
            "selected_common_station_ids": "|".join(selected_sites),
            "n_common_qualified_years": len(common_years),
            "common_qualified_years": "|".join(map(str, common_years)),
        }
        if reasons:
            attrition.append({**record, "reason": ";".join(reasons)})
        else:
            eligible.append(record)
    return station_qc, pd.DataFrame(attrition), pd.DataFrame(eligible)


def _collapse_observation_days(panel: pd.DataFrame) -> pd.DataFrame:
    for _, group in panel.groupby(
        ["provider", "network_id", "site_id", "date"], sort=False, dropna=False
    ):
        if len(group) > 1 and (
            group["temperature_c"].nunique(dropna=False) != 1
            or group["approval_code"].astype(str).nunique(dropna=False) != 1
        ):
            raise SealedEvaluatorError("conflicting duplicate synthetic calendar day")
    return panel.drop_duplicates(["provider", "network_id", "site_id", "date"])


def evaluate_synthetic_fixture(
    *,
    references: Sequence[SealedObjectRef],
    reader: MemorySealedObjectReader,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run synthetic parser/QC fixtures without any production authorization."""

    return _evaluate_synthetic_fixture(
        references=references,
        reader=reader,
        output_dir=output_dir,
        _fixture_token=_FIXTURE_EXECUTION_TOKEN,
    )


def _evaluate_synthetic_fixture(
    *,
    references: Sequence[SealedObjectRef],
    reader: MemorySealedObjectReader,
    output_dir: str | Path,
    _fixture_token: object,
) -> dict[str, Any]:
    """Private implementation guarded by an internal synthetic-only token.

    This is not an evaluate-once path, does not consume a formal authorization,
    and deliberately has no generic reader interface.
    """

    if _fixture_token is not _FIXTURE_EXECUTION_TOKEN:
        raise SealedEvaluatorError("internal synthetic fixture token required")
    if type(reader) is not MemorySealedObjectReader:
        raise SealedEvaluatorError("synthetic fixture requires the exact memory reader")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ledger = output / "synthetic_fixture_ledger.json"
    ledger_payload = {
        "manifest_schema": FIXTURE_LEDGER_SCHEMA,
        "status": "synthetic_fixture_started",
        "formal_evidence": False,
        "production_authorization_consumed": False,
    }
    try:
        with ledger.open("x", encoding="utf-8") as handle:
            json.dump(ledger_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise SealedEvaluatorError("synthetic fixture ledger already exists") from error

    observations: list[pd.DataFrame] = []
    object_failures: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        for ref in references:
            if ref.key in seen:
                raise SealedEvaluatorError("duplicate registered object identity")
            seen.add(ref.key)
            body = reader.read_object(ref)
            if type(body) is not bytes:
                raise SealedEvaluatorError("synthetic fixture body must be exact bytes")
            if len(body) != ref.expected_byte_count:
                raise SealedEvaluatorError(f"synthetic byte-count mismatch: {ref.key}")
            if hashlib.sha256(body).hexdigest() != ref.expected_sha256:
                raise SealedEvaluatorError(f"synthetic SHA-256 mismatch: {ref.key}")
            try:
                if ref.provider == "usgs_nwis":
                    frame = parse_huc8_nwis_response(
                        body,
                        site_id=ref.site_id,
                        request_start=ref.request_start,
                        request_end=ref.request_end,
                    )
                elif ref.provider == "foen":
                    frame = parse_foen_response(
                        body,
                        site_id=ref.site_id,
                        request_year=ref.request_year,
                        request_start=ref.request_start,
                        request_end=ref.request_end,
                    )
                else:
                    raise SealedEvaluatorError(
                        f"unsupported sealed provider: {ref.provider}"
                    )
            except SealedEvaluatorError as error:
                object_failures.append({"object_key": ref.key, "reason": str(error)})
                continue
            frame["network_id"] = ref.network_id
            observations.append(frame)
        panel = (
            pd.concat(observations, ignore_index=True)
            if observations
            else pd.DataFrame(
                columns=[
                    "site_id",
                    "date",
                    "temperature_c",
                    "approval_code",
                    "provider",
                    "network_id",
                ]
            )
        )
        panel = _collapse_observation_days(panel)
        station_qc, attrition, eligible = _network_qc(panel, references)
        station_qc.to_csv(output / "synthetic_station_qc.csv", index=False)
        attrition.to_csv(output / "synthetic_network_attrition.csv", index=False)
        eligible.to_csv(output / "synthetic_eligible_networks.csv", index=False)
        pd.DataFrame(object_failures, columns=["object_key", "reason"]).to_csv(
            output / "synthetic_object_attrition.csv", index=False
        )
        provider_counts = Counter(ref.provider for ref in references)
        manifest = {
            "manifest_schema": FIXTURE_RESULT_SCHEMA,
            "status": "synthetic_fixture_complete_not_formal_evidence",
            "formal_evidence": False,
            "synthetic_fixture_execution": True,
            "production_authorization_consumed": False,
            "production_evaluate_once_semantics": False,
            "n_synthetic_objects_read": len(reader.read_keys),
            "n_objects_by_provider": dict(sorted(provider_counts.items())),
            "n_object_parse_failures": len(object_failures),
            "n_station_qc_rows": len(station_qc),
            "n_eligible_networks": len(eligible),
            "n_attrited_networks": len(attrition),
            "synthetic_qc_outputs": {
                "station_qc": "synthetic_station_qc.csv",
                "object_attrition": "synthetic_object_attrition.csv",
                "network_attrition": "synthetic_network_attrition.csv",
                "eligible_networks": "synthetic_eligible_networks.csv",
            },
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        ledger_payload["status"] = "synthetic_fixture_complete"
        ledger.write_text(
            json.dumps(ledger_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest
    except BaseException:
        ledger_payload["status"] = "synthetic_fixture_failed"
        ledger.write_text(
            json.dumps(ledger_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise


def _validate_production_authorization(
    *,
    readiness_path: Path,
    once_lock_path: Path,
    model_freeze_path: Path,
    ledger_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    preflight = build_evaluator_preflight(
        readiness_path=readiness_path,
        once_lock_path=once_lock_path,
        model_freeze_path=model_freeze_path,
        run_ledger_path=ledger_path,
    )
    blockers = list(preflight.get("blockers") or [])
    if preflight.get("authorized_for_object_reads") is not True:
        if "evaluate_once_lock_missing_or_invalid" in blockers:
            pass
        elif not blockers:
            blockers.append("production_authorization_not_granted")
    readiness = _load_mapping(readiness_path)
    lock = _load_mapping(once_lock_path)
    model = _load_mapping(model_freeze_path)
    return readiness, lock, model, blockers


def evaluate_production_sealed_once(
    *,
    readiness_path: str | Path = DEFAULT_READINESS,
    once_lock_path: str | Path = DEFAULT_ONCE_LOCK,
    model_freeze_path: str | Path = DEFAULT_MODEL_FREEZE,
    output_dir: str | Path = DEFAULT_SEALED_QC_OUTPUT,
    sealed_absolute_floor: int = 40,
) -> dict[str, Any]:
    """Run the single authorized sealed temperature QC pass."""

    readiness_file = Path(readiness_path).resolve()
    lock_file = Path(once_lock_path).resolve()
    model_file = Path(model_freeze_path).resolve()
    output = Path(output_dir)
    ledger_path = lock_file.with_name("evaluate_once_run_ledger.json")
    readiness, lock, model, blockers = _validate_production_authorization(
        readiness_path=readiness_file,
        once_lock_path=lock_file,
        model_freeze_path=model_file,
        ledger_path=ledger_path,
    )
    if blockers:
        raise SealedEvaluatorError(
            "production sealed evaluation blocked: " + ";".join(sorted(set(blockers)))
        )

    readiness_source = build_readiness_manifest(
        once_lock_path=lock_file, for_post_claim_evaluation=True
    )
    references = registered_object_references(readiness_source)
    output.mkdir(parents=True, exist_ok=True)
    ledger_payload = {
        "manifest_schema": PRODUCTION_LEDGER_SCHEMA,
        "status": "production_evaluate_once_started",
        "formal_evidence": False,
        "production_authorization_consumed": True,
        "readiness_manifest_sha256": _canonical_sha256(readiness_source),
        "evaluate_once_lock_sha256": _canonical_sha256(lock),
        "model_freeze_sha256": _sha256_file(model_file),
        "n_registered_objects": len(references),
    }
    try:
        with ledger_path.open("x", encoding="utf-8") as handle:
            json.dump(ledger_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise SealedEvaluatorError("evaluate-once run ledger already exists") from error

    reader = FilesystemSealedObjectReader()
    observations: list[pd.DataFrame] = []
    object_failures: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        for ref in references:
            if ref.key in seen:
                raise SealedEvaluatorError("duplicate registered object identity")
            seen.add(ref.key)
            try:
                body = reader.read_object(ref)
            except SealedEvaluatorError as error:
                object_failures.append({"object_key": ref.key, "reason": str(error)})
                continue
            try:
                if ref.provider == "usgs_nwis":
                    frame = parse_huc8_nwis_response(
                        body,
                        site_id=ref.site_id,
                        request_start=ref.request_start,
                        request_end=ref.request_end,
                    )
                elif ref.provider == "foen":
                    frame = parse_foen_response(
                        body,
                        site_id=ref.site_id,
                        request_year=ref.request_year,
                        request_start=ref.request_start,
                        request_end=ref.request_end,
                    )
                else:
                    raise SealedEvaluatorError(
                        f"unsupported sealed provider: {ref.provider}"
                    )
            except SealedEvaluatorError as error:
                object_failures.append({"object_key": ref.key, "reason": str(error)})
                continue
            frame["network_id"] = ref.network_id
            observations.append(frame)
        panel = (
            pd.concat(observations, ignore_index=True)
            if observations
            else pd.DataFrame(
                columns=[
                    "site_id",
                    "date",
                    "temperature_c",
                    "approval_code",
                    "provider",
                    "network_id",
                ]
            )
        )
        panel = _collapse_observation_days(panel)
        station_qc, attrition, eligible = _network_qc(panel, references)
        station_qc.to_csv(output / "station_qc.csv", index=False)
        attrition.to_csv(output / "network_attrition.csv", index=False)
        eligible.to_csv(output / "eligible_networks.csv", index=False)
        pd.DataFrame(object_failures, columns=["object_key", "reason"]).to_csv(
            output / "object_attrition.csv", index=False
        )
        provider_counts = Counter(ref.provider for ref in references)
        huc8_eligible = eligible.loc[eligible["provider"].eq("usgs_nwis")]
        n_huc8_eligible = len(huc8_eligible)
        sealed_floor_met = n_huc8_eligible >= sealed_absolute_floor
        manifest = {
            "manifest_schema": PRODUCTION_RESULT_SCHEMA,
            "status": "complete",
            "formal_evidence": False,
            "production_authorization_consumed": True,
            "production_evaluate_once_semantics": True,
            "sealed_outcomes_opened": True,
            "sealed_temperature_records_read": True,
            "n_sealed_objects_read": len(reader.read_keys),
            "n_objects_by_provider": dict(sorted(provider_counts.items())),
            "n_object_parse_failures": len(object_failures),
            "n_station_qc_rows": len(station_qc),
            "n_eligible_networks": len(eligible),
            "n_huc8_eligible_networks": n_huc8_eligible,
            "n_foen_eligible_networks": int(
                eligible["provider"].eq("foen").sum() if not eligible.empty else 0
            ),
            "sealed_absolute_floor": sealed_absolute_floor,
            "sealed_absolute_floor_met": sealed_floor_met,
            "passed": sealed_floor_met,
            "purpose": "sealed_qc_not_confirmatory_t2_scoring",
            "evaluate_once_lock_sha256": _canonical_sha256(lock),
            "outputs": {
                "station_qc": "station_qc.csv",
                "object_attrition": "object_attrition.csv",
                "network_attrition": "network_attrition.csv",
                "eligible_networks": "eligible_networks.csv",
            },
        }
        (output / "sealed_qc_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        ledger_payload["status"] = "production_evaluate_once_complete"
        ledger_payload["sealed_qc_manifest_sha256"] = _sha256_file(
            output / "sealed_qc_manifest.json"
        )
        ledger_payload["n_sealed_objects_read"] = len(reader.read_keys)
        ledger_path.write_text(
            json.dumps(ledger_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest
    except BaseException:
        ledger_payload["status"] = "production_evaluate_once_failed"
        ledger_path.write_text(
            json.dumps(ledger_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise


__all__ = [
    "DEFAULT_PREFLIGHT_OUTPUT",
    "DEFAULT_SEALED_QC_OUTPUT",
    "FIXTURE_LEDGER_SCHEMA",
    "FIXTURE_RESULT_SCHEMA",
    "PRODUCTION_LEDGER_SCHEMA",
    "PRODUCTION_RESULT_SCHEMA",
    "PREFLIGHT_SCHEMA",
    "FilesystemSealedObjectReader",
    "MemorySealedObjectReader",
    "SealedEvaluatorError",
    "SealedObjectRef",
    "build_evaluator_preflight",
    "evaluate_production_sealed_once",
    "evaluate_synthetic_fixture",
    "parse_foen_response",
    "parse_huc8_nwis_response",
    "registered_object_references",
    "vault_path_for_reference",
    "write_preflight",
]
