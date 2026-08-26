"""Capability-gated scaffold for the single sealed T2/T7 evaluation.

The default entry point is metadata-only.  It cannot open a vault and it never
creates the evaluate-once lock.  Byte access exists only behind an injected
``SealedObjectReader`` capability, after the existing readiness manifest,
once-lock, model freeze, Git HEAD, and formal T2-v4 input/output identities have
all been revalidated.

This module deliberately does not provide a filesystem vault reader.  Tests use
``MemorySealedObjectReader`` with synthetic provider fixtures.  A separately
reviewed production adapter is required at the actual evaluate-once ceremony.
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
from typing import Any, Protocol

import pandas as pd

from stream_recoverability.data.ingest_qc import (
    VERDICT_ACCEPTED,
    VERDICT_ACCEPTED_WITH_FLAGS,
    qc_station_series,
)

from .sealed_evaluation_readiness import (
    MODEL_FREEZE_SCHEMA,
    ONCE_LOCK_SCHEMA,
    READINESS_SCHEMA,
)
from .t2_primary_aggregation_v2 import INPUT_BINDING_SCHEMA
from .t2_workload_v4 import V4_RUNNER_CONTRACT_VERSION, V4_WORKLOAD_SCHEMA

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT_SCHEMA = "t2_t7_sealed_evaluator_preflight_v1"
RUN_LEDGER_SCHEMA = "t2_t7_sealed_evaluate_once_run_ledger_v1"
RESULT_SCHEMA = "t2_t7_sealed_evaluate_once_qc_result_v1"
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
    / "results/framework/t2_recovery_benchmark_v4/workload_manifest.json"
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

    @property
    def key(self) -> str:
        year = "all" if self.request_year is None else str(self.request_year)
        return f"{self.provider}/{self.network_id}/{self.site_id}/{year}"


class SealedObjectReader(Protocol):
    """The only byte capability accepted by the evaluator."""

    def read_object(self, reference: SealedObjectRef) -> bytes:
        """Return exactly one registered object body."""


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
    if readiness and (
        readiness.get("manifest_schema") != READINESS_SCHEMA
        or readiness.get("ready_for_unseal") is not True
        or readiness.get("blockers") != []
    ):
        blockers.append("readiness_gate_not_unconditionally_ready")

    try:
        lock = _load_mapping(lock_file)
    except SealedEvaluatorError:
        lock = {}
        blockers.append("evaluate_once_lock_missing_or_invalid")
    if lock and (
        lock.get("manifest_schema") != ONCE_LOCK_SCHEMA
        or lock.get("status") != "started_before_any_sealed_read"
        or lock.get("rerun_permitted") is not False
        or lock.get("sealed_outcomes_opened_at_lock_creation") is not False
    ):
        blockers.append("evaluate_once_lock_contract_mismatch")
    if (
        readiness
        and lock
        and lock.get("readiness_manifest_sha256") != _canonical_sha256(readiness)
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
        and not _model_binding(model, "aggregation_manifest", result_file, result_sha)
    ):
        blockers.append("model_freeze_v4_result_binding_mismatch")

    current_head_result = _git("rev-parse", "HEAD")
    current_head = current_head_result.stdout.strip()
    recorded_head = lock.get("head_commit")
    git_binding = readiness.get("git_commit_before_unseal")
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
    return {
        "manifest_schema": PREFLIGHT_SCHEMA,
        "status": "authorized" if not unique else "blocked",
        "authorized_for_object_reads": not unique,
        "formal_evidence": False,
        "dry_run_metadata_only": True,
        "evaluate_once_lock_claimed_by_preflight": False,
        "vault_path_resolved_or_statted": False,
        "sealed_objects_read": 0,
        "failure_or_interrupt_forbids_rerun": True,
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
            "failed_or_interrupted_once_run_is_nonretryable": True,
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
    """Recreate opaque object references from registry metadata only.

    The registry roots are taken from the already audited readiness record.
    This function never constructs, resolves, or stats a vault path.
    """

    inventory = readiness.get("sealed_registry_inventory")
    if not isinstance(inventory, Mapping):
        raise SealedEvaluatorError("readiness lacks sealed registry inventory")
    specs = (
        ("north_america_huc8", "usgs_nwis", "sha256", None),
        ("foen_non_north_america", "foen", "response_sha256", "request_year"),
    )
    references: list[SealedObjectRef] = []
    for label, provider, sha_field, year_field in specs:
        provider_inventory = inventory.get(label)
        if not isinstance(provider_inventory, Mapping):
            raise SealedEvaluatorError(f"readiness lacks provider inventory: {label}")
        root_value = provider_inventory.get("registry_root")
        if not isinstance(root_value, str) or not root_value:
            raise SealedEvaluatorError(f"provider registry root is invalid: {label}")
        root = Path(root_value)
        if not root.is_absolute():
            root = REPOSITORY_ROOT / root
        if root.is_symlink() or not root.is_dir():
            raise SealedEvaluatorError(f"provider registry root is invalid: {label}")
        paths = sorted(root.glob("*/*.json"))
        rows = [_load_mapping(path) for path in paths]
        if _canonical_sha256(rows) != provider_inventory.get("registry_records_sha256"):
            raise SealedEvaluatorError(
                f"provider registry changed after readiness: {label}"
            )
        if len(rows) != provider_inventory.get("n_objects"):
            raise SealedEvaluatorError(f"provider object count changed: {label}")
        for row in rows:
            digest = row.get(sha_field)
            byte_count = row.get("byte_count")
            if (
                not isinstance(digest, str)
                or not _SHA256.fullmatch(digest)
                or isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or byte_count < 1
            ):
                raise SealedEvaluatorError(f"invalid strict registry row: {label}")
            year = row.get(year_field) if year_field is not None else None
            if year is not None and (
                isinstance(year, bool) or not isinstance(year, int)
            ):
                raise SealedEvaluatorError("invalid FOEN request year in registry")
            references.append(
                SealedObjectRef(
                    provider=provider,
                    network_id=str(row.get("network_id")),
                    site_id=str(row.get("site_id")),
                    request_year=year,
                    expected_sha256=digest,
                    expected_byte_count=byte_count,
                )
            )
    keys = [reference.key for reference in references]
    if len(keys) != len(set(keys)):
        raise SealedEvaluatorError("duplicate sealed object registry identity")
    return tuple(references)


def parse_huc8_nwis_response(payload: bytes, *, site_id: str) -> pd.DataFrame:
    """Parse one NWIS JSON response into the provider-neutral QC columns."""

    try:
        document = json.loads(payload.decode("utf-8"))
        series = document["value"]["timeSeries"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SealedEvaluatorError("invalid NWIS JSON response") from error
    rows: list[dict[str, Any]] = []
    for item in series:
        source = item.get("sourceInfo") or {}
        codes = source.get("siteCode") or []
        observed_site = str((codes[0] if codes else {}).get("value", ""))
        variable_codes = (item.get("variable") or {}).get("variableCode") or []
        parameters = {str(code.get("value", "")) for code in variable_codes}
        if observed_site != str(site_id) or "00010" not in parameters:
            raise SealedEvaluatorError("NWIS response identity/parameter mismatch")
        for block in item.get("values") or []:
            for point in block.get("value") or []:
                rows.append(
                    {
                        "site_id": str(site_id),
                        "date": point.get("dateTime"),
                        "temperature_c": point.get("value"),
                        "approval_code": ",".join(
                            str(value) for value in (point.get("qualifiers") or [])
                        ),
                    }
                )
    return _normalize_provider_rows(rows, provider="usgs_nwis")


def parse_foen_response(payload: bytes, *, site_id: str) -> pd.DataFrame:
    """Parse one FOEN daily-mean GraphQL response into neutral QC columns."""

    try:
        document = json.loads(payload.decode("utf-8"))
        if document.get("errors"):
            raise SealedEvaluatorError("FOEN response contains GraphQL errors")
        rows = document["data"]["water"]["observations"]["data_1day_mean"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SealedEvaluatorError("invalid FOEN GraphQL response") from error
    normalized: list[dict[str, Any]] = []
    for row in rows:
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
        normalized.append(
            {
                "site_id": str(site_id),
                "date": row.get("timestamp"),
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
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
    frame["provider"] = provider
    return frame.dropna(subset=["date"]).reset_index(drop=True)


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


def evaluate_with_injected_reader(
    preflight: Mapping[str, Any],
    *,
    references: Sequence[SealedObjectRef],
    reader: SealedObjectReader,
    output_dir: str | Path,
    fixture_execution: bool = False,
) -> dict[str, Any]:
    """Exercise the once-run QC path after authorization.

    ``fixture_execution`` must remain true in this repository version.  This
    makes tests meaningful while ensuring no production vault adapter can be
    slipped into an ordinary CLI invocation.
    """

    if preflight.get("manifest_schema") != PREFLIGHT_SCHEMA:
        raise SealedEvaluatorError("evaluator preflight schema mismatch")
    if (
        preflight.get("authorized_for_object_reads") is not True
        or preflight.get("blockers") != []
    ):
        raise SealedEvaluatorError("object reads forbidden by evaluator preflight")
    if fixture_execution is not True or not isinstance(
        reader, MemorySealedObjectReader
    ):
        raise SealedEvaluatorError(
            "production sealed reader is deliberately absent from this scaffold"
        )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ledger = output / "run_ledger.json"
    ledger_payload = {
        "manifest_schema": RUN_LEDGER_SCHEMA,
        "status": "started_nonretryable",
        "rerun_permitted": False,
        "fixture_execution": True,
        "preflight_sha256": _canonical_sha256(dict(preflight)),
    }
    try:
        with ledger.open("x", encoding="utf-8") as handle:
            json.dump(ledger_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise SealedEvaluatorError(
            "once-run ledger already exists; rerun forbidden"
        ) from error

    observations: list[pd.DataFrame] = []
    object_failures: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        for ref in references:
            if ref.key in seen:
                raise SealedEvaluatorError("duplicate registered object identity")
            seen.add(ref.key)
            body = reader.read_object(ref)
            if len(body) != ref.expected_byte_count:
                raise SealedEvaluatorError(f"sealed byte-count mismatch: {ref.key}")
            if hashlib.sha256(body).hexdigest() != ref.expected_sha256:
                raise SealedEvaluatorError(f"sealed SHA-256 mismatch: {ref.key}")
            try:
                if ref.provider == "usgs_nwis":
                    frame = parse_huc8_nwis_response(body, site_id=ref.site_id)
                elif ref.provider == "foen":
                    frame = parse_foen_response(body, site_id=ref.site_id)
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
        station_qc, attrition, eligible = _network_qc(panel, references)
        station_qc.to_csv(output / "sealed_station_qc.csv", index=False)
        attrition.to_csv(output / "sealed_network_attrition.csv", index=False)
        eligible.to_csv(output / "eligible_sealed_networks.csv", index=False)
        pd.DataFrame(object_failures, columns=["object_key", "reason"]).to_csv(
            output / "sealed_object_attrition.csv", index=False
        )
        provider_counts = Counter(ref.provider for ref in references)
        manifest = {
            "manifest_schema": RESULT_SCHEMA,
            "status": "fixture_complete_not_formal_evidence",
            "formal_evidence": False,
            "fixture_execution": True,
            "rerun_permitted": False,
            "failure_or_interrupt_would_forbid_rerun": True,
            "n_objects_read_once": len(reader.read_keys),
            "n_objects_by_provider": dict(sorted(provider_counts.items())),
            "n_object_parse_failures": len(object_failures),
            "n_station_qc_rows": len(station_qc),
            "n_eligible_networks": len(eligible),
            "n_attrited_networks": len(attrition),
            "v4_bindings": {
                key: preflight["bindings"][key]
                for key in (
                    "v4_workload",
                    "v4_result_binding",
                    "model_freeze",
                    "head_commit",
                )
            },
            "sealed_qc_attrition": {
                "station_qc": "sealed_station_qc.csv",
                "object_attrition": "sealed_object_attrition.csv",
                "network_attrition": "sealed_network_attrition.csv",
                "eligible_networks": "eligible_sealed_networks.csv",
            },
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        ledger_payload["status"] = "fixture_complete_nonretryable"
        ledger.write_text(
            json.dumps(ledger_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest
    except BaseException:
        ledger_payload["status"] = "failed_nonretryable"
        ledger.write_text(
            json.dumps(ledger_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise


__all__ = [
    "DEFAULT_PREFLIGHT_OUTPUT",
    "PREFLIGHT_SCHEMA",
    "MemorySealedObjectReader",
    "SealedEvaluatorError",
    "SealedObjectReader",
    "SealedObjectRef",
    "build_evaluator_preflight",
    "evaluate_with_injected_reader",
    "parse_foen_response",
    "parse_huc8_nwis_response",
    "registered_object_references",
    "write_preflight",
]
