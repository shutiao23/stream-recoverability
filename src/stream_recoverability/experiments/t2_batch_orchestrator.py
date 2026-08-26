"""Fail-closed orchestration for immutable T2 ordinal chunks.

The orchestrator is intentionally a planning and custody layer.  It never
starts execution unless the caller supplies the exact workload file SHA, item
count, and planned chunk count.  The default CLI is dry-run only.  A contract
spec describes where a workload version stores its immutable bindings, so a
future v4 workload can be audited and planned before it has an execution
adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from stream_recoverability.experiments.t2_chunk_executor import (
    MAX_CHUNK_ITEMS,
    execute_t2_chunk,
)

BATCH_SCHEMA = "t2_batch_orchestration_v1"
AGGREGATION_LIST_SCHEMA = "t2_batch_aggregation_manifest_list_v1"
DEFAULT_MAX_WORKERS = 2
MAX_WORKERS = 8


class BatchOrchestrationError(ValueError):
    """Raised when a batch cannot be planned or resumed safely."""


@dataclass(frozen=True)
class WorkloadContractSpec:
    """JSON-pointer bindings needed to audit one workload contract."""

    name: str
    workload_manifest_schema: str
    chunk_manifest_schema: str
    item_count_pointer: str
    item_identity_sha256_pointer: str
    runner_contract_pointer: str = "/runner_contract_version"
    sealed_read_pointer: str = "/sealed_temperature_records_read"
    sealed_roots_pointer: str = "/sealed_input_roots_allowed"
    executor_adapter: str | None = None


V3_CONTRACT = WorkloadContractSpec(
    name="legacy_v3",
    workload_manifest_schema="t2_v91_open_role_workload_v3",
    chunk_manifest_schema="t2_v91_result_chunk_v1",
    item_count_pointer="/tier_1/n_work_items",
    item_identity_sha256_pointer="/tier_1/work_item_identity_sha256",
    executor_adapter="t2_v91_chunk_executor",
)


def load_contract_spec(path: str | Path) -> WorkloadContractSpec:
    """Load a parameterized workload contract (for example a future v4)."""

    value = _read_json(Path(path))
    allowed = {field.name for field in WorkloadContractSpec.__dataclass_fields__.values()}
    extra = set(value) - allowed
    if extra:
        raise BatchOrchestrationError(f"unknown contract-spec fields: {sorted(extra)}")
    try:
        return WorkloadContractSpec(**value)
    except TypeError as error:
        raise BatchOrchestrationError(f"invalid contract spec: {error}") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BatchOrchestrationError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise BatchOrchestrationError(f"JSON document is not a mapping: {path}")
    return value


def _json_pointer(value: Mapping[str, Any], pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise BatchOrchestrationError(f"JSON pointer must start with '/': {pointer}")
    current: Any = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or token not in current:
            raise BatchOrchestrationError(f"workload lacks JSON pointer {pointer}")
        current = current[token]
    return current


def _assert_open_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise BatchOrchestrationError(f"refusing sealed-path batch input/output: {path}")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_chunk_ranges(start: int, end: int, chunk_size: int) -> list[tuple[int, int]]:
    """Return contiguous, disjoint half-open ordinal ranges."""

    if any(isinstance(value, bool) for value in (start, end, chunk_size)):
        raise BatchOrchestrationError("range values must be integers")
    if start < 0 or end <= start:
        raise BatchOrchestrationError("batch range must satisfy 0 <= start < end")
    if chunk_size < 1 or chunk_size > MAX_CHUNK_ITEMS:
        raise BatchOrchestrationError(
            f"chunk_size must be between 1 and {MAX_CHUNK_ITEMS}"
        )
    ranges = [
        (ordinal, min(ordinal + chunk_size, end))
        for ordinal in range(start, end, chunk_size)
    ]
    if ranges[0][0] != start or ranges[-1][1] != end:
        raise AssertionError("internal range coverage error")
    for previous, current in pairwise(ranges):
        if previous[1] != current[0]:
            raise AssertionError("internal range overlap/gap error")
    return ranges


def _audit_workload(
    workload_path: Path,
    expected_workload_sha256: str,
    contract: WorkloadContractSpec,
) -> tuple[dict[str, Any], str, int, str, str]:
    if len(expected_workload_sha256) != 64:
        raise BatchOrchestrationError("an exact 64-character workload SHA-256 is required")
    actual_sha = _sha256_file(workload_path)
    if actual_sha != expected_workload_sha256:
        raise BatchOrchestrationError("explicit workload SHA-256 acknowledgement mismatch")
    workload = _read_json(workload_path)
    if workload.get("manifest_schema") != contract.workload_manifest_schema:
        raise BatchOrchestrationError("workload manifest schema differs from contract spec")
    if _json_pointer(workload, contract.sealed_read_pointer) is not False:
        raise BatchOrchestrationError("workload does not attest sealed outcomes stayed closed")
    if _json_pointer(workload, contract.sealed_roots_pointer) != []:
        raise BatchOrchestrationError("workload permits sealed input roots")
    try:
        item_count = int(_json_pointer(workload, contract.item_count_pointer))
    except (TypeError, ValueError) as error:
        raise BatchOrchestrationError("workload item count is not an integer") from error
    item_identity = str(_json_pointer(workload, contract.item_identity_sha256_pointer))
    runner_contract = str(_json_pointer(workload, contract.runner_contract_pointer))
    if item_count < 1 or len(item_identity) != 64 or not runner_contract:
        raise BatchOrchestrationError("workload lacks a valid item-count/identity binding")
    return workload, actual_sha, item_count, item_identity, runner_contract


def _validate_chunk_manifest(
    manifest: Mapping[str, Any],
    *,
    contract: WorkloadContractSpec,
    workload_sha: str,
    runner_contract: str,
    start: int,
    end: int,
) -> None:
    expected = {
        "manifest_schema": contract.chunk_manifest_schema,
        "workload_manifest_sha256": workload_sha,
        "runner_contract_version": runner_contract,
        "start_ordinal": start,
        "end_ordinal_exclusive": end,
        "n_records": end - start,
        "completeness": "complete",
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise BatchOrchestrationError(
                f"chunk [{start},{end}) binding mismatch for {key}"
            )


def _aggregation_list(state: Mapping[str, Any]) -> dict[str, Any]:
    succeeded = [
        str(chunk["manifest_path"])
        for chunk in state["chunks"]
        if chunk["status"] == "succeeded"
    ]
    missing = [
        [int(chunk["start_ordinal"]), int(chunk["end_ordinal_exclusive"])]
        for chunk in state["chunks"]
        if chunk["status"] != "succeeded"
    ]
    return {
        "manifest_schema": AGGREGATION_LIST_SCHEMA,
        "purpose": "aggregation_input_custody_not_evidence",
        "batch_plan_sha256": state["batch_plan_sha256"],
        "workload_manifest_sha256": state["workload_manifest_sha256"],
        "workload_item_identity_sha256": state["workload_item_identity_sha256"],
        "expected_workload_item_count": state["expected_workload_item_count"],
        "planned_chunk_count": state["planned_chunk_count"],
        "completed_chunk_count": len(succeeded),
        "chunk_manifest_paths": succeeded,
        "missing_ordinal_ranges": missing,
        "ready_for_aggregation": not missing,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }


ChunkExecutor = Callable[..., dict[str, Any]]


def orchestrate_t2_batch(
    *,
    repo_root: str | Path,
    workload_manifest_path: str | Path,
    design_path: str | Path,
    state_path: str | Path,
    chunks_output_dir: str | Path,
    expected_workload_sha256: str,
    contract: WorkloadContractSpec = V3_CONTRACT,
    start_ordinal: int = 0,
    end_ordinal_exclusive: int | None = None,
    chunk_size: int = MAX_CHUNK_ITEMS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    execute: bool = False,
    allow_full_workload: bool = False,
    acknowledge_item_count: int | None = None,
    acknowledge_chunk_count: int | None = None,
    resume: bool = False,
    results_format: str = "parquet",
    execution_mode: str = "network_cache_v1",
    chunk_executor: ChunkExecutor = execute_t2_chunk,
) -> dict[str, Any]:
    """Plan or execute a SHA-bound batch, persisting progress atomically."""

    repo = Path(repo_root).resolve()
    workload_path = Path(workload_manifest_path).resolve()
    design = Path(design_path).resolve()
    state_file = Path(state_path).resolve()
    chunks_output = Path(chunks_output_dir).resolve()
    for path in (repo, workload_path, design, state_file, chunks_output):
        _assert_open_path(path)
    _, workload_sha, expected_items, item_identity, runner_contract = _audit_workload(
        workload_path, expected_workload_sha256, contract
    )
    end = expected_items if end_ordinal_exclusive is None else end_ordinal_exclusive
    if end > expected_items:
        raise BatchOrchestrationError("batch end exceeds the workload item count")
    ranges = build_chunk_ranges(start_ordinal, end, chunk_size)
    if max_workers < 1 or max_workers > MAX_WORKERS:
        raise BatchOrchestrationError(f"max_workers must be between 1 and {MAX_WORKERS}")
    is_full = start_ordinal == 0 and end == expected_items
    if execute and is_full and not allow_full_workload:
        raise BatchOrchestrationError(
            "full workload execution requires explicit allow_full_workload=True"
        )
    if execute:
        if acknowledge_item_count != expected_items:
            raise BatchOrchestrationError("exact workload item-count acknowledgement required")
        if acknowledge_chunk_count != len(ranges):
            raise BatchOrchestrationError("exact planned chunk-count acknowledgement required")
        if contract.executor_adapter != "t2_v91_chunk_executor":
            raise BatchOrchestrationError(
                "this contract has no approved chunk executor adapter; dry-run only"
            )

    contract_dict = asdict(contract)
    plan_identity = {
        "manifest_schema": BATCH_SCHEMA,
        "contract": contract_dict,
        "workload_manifest_sha256": workload_sha,
        "workload_item_identity_sha256": item_identity,
        "expected_workload_item_count": expected_items,
        "start_ordinal": start_ordinal,
        "end_ordinal_exclusive": end,
        "chunk_size": chunk_size,
        "ranges": ranges,
        "results_format": results_format,
        "execution_mode": execution_mode,
    }
    plan_sha = _canonical_sha(plan_identity)
    if state_file.exists():
        state = _read_json(state_file)
        if state.get("batch_plan_sha256") != plan_sha:
            raise BatchOrchestrationError("existing state belongs to a different batch plan")
        if execute and not resume and any(
            chunk.get("status") != "planned" for chunk in state.get("chunks", [])
        ):
            raise BatchOrchestrationError("existing execution state requires resume=True")
    else:
        state = {
            **plan_identity,
            "batch_plan_sha256": plan_sha,
            "purpose": "bounded_pipeline_orchestration_not_evidence",
            "full_workload": is_full,
            "planned_chunk_count": len(ranges),
            "max_workers": max_workers,
            "fail_fast": True,
            "status": "planned",
            "chunks": [
                {
                    "chunk_index": index,
                    "start_ordinal": start,
                    "end_ordinal_exclusive": chunk_end,
                    "status": "planned",
                    "attempts": 0,
                }
                for index, (start, chunk_end) in enumerate(ranges)
            ],
            "aggregation_manifest_list_path": str(
                state_file.with_name("aggregation_chunk_manifests.json")
            ),
            "sealed_temperature_records_read": False,
            "formal_evidence": False,
            "passed": False,
        }
        _atomic_json(state_file, state)
    aggregation_path = Path(str(state["aggregation_manifest_list_path"]))
    _atomic_json(aggregation_path, _aggregation_list(state))
    if not execute:
        return state

    # Stale "running" entries cannot have been atomically published by this
    # process.  On explicit resume they are retried; succeeded entries are
    # independently revalidated below.
    for chunk in state["chunks"]:
        if chunk["status"] in {"failed", "running"}:
            if not resume:
                raise BatchOrchestrationError("failed/running state requires resume=True")
            chunk["status"] = "planned"
            chunk.pop("error", None)

    for chunk in state["chunks"]:
        if chunk["status"] != "succeeded":
            continue
        manifest_path = Path(str(chunk.get("manifest_path", "")))
        if not manifest_path.is_file() or _sha256_file(manifest_path) != chunk.get(
            "manifest_sha256"
        ):
            raise BatchOrchestrationError("resume found a changed/missing chunk manifest")
        _validate_chunk_manifest(
            _read_json(manifest_path),
            contract=contract,
            workload_sha=workload_sha,
            runner_contract=runner_contract,
            start=int(chunk["start_ordinal"]),
            end=int(chunk["end_ordinal_exclusive"]),
        )

    state["status"] = "running"
    state["max_workers"] = max_workers
    state["acknowledgements"] = {
        "workload_sha256": expected_workload_sha256,
        "workload_item_count": acknowledge_item_count,
        "planned_chunk_count": acknowledge_chunk_count,
        "full_workload_execution_allowed": bool(allow_full_workload),
    }
    _atomic_json(state_file, state)

    state_lock = threading.Lock()

    def publish() -> None:
        with state_lock:
            _atomic_json(state_file, state)
            _atomic_json(aggregation_path, _aggregation_list(state))

    def run_one(chunk: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
        start = int(chunk["start_ordinal"])
        chunk_end = int(chunk["end_ordinal_exclusive"])
        manifest = chunk_executor(
            repo_root=repo,
            workload_manifest_path=workload_path,
            design_path=design,
            output_dir=chunks_output,
            start_ordinal=start,
            end_ordinal_exclusive=chunk_end,
            results_format=results_format,
            execution_mode=execution_mode,
        )
        _validate_chunk_manifest(
            manifest,
            contract=contract,
            workload_sha=workload_sha,
            runner_contract=runner_contract,
            start=start,
            end=chunk_end,
        )
        manifest_path = chunks_output / f"chunk_{start:07d}_{chunk_end:07d}/manifest.json"
        if not manifest_path.is_file():
            raise BatchOrchestrationError("chunk executor did not atomically publish manifest")
        if _read_json(manifest_path) != manifest:
            raise BatchOrchestrationError("returned chunk manifest differs from published bytes")
        return manifest, manifest_path

    pending = [chunk for chunk in state["chunks"] if chunk["status"] == "planned"]
    pending_iterator = iter(pending)
    futures: dict[Future[tuple[dict[str, Any], Path]], dict[str, Any]] = {}
    failure_seen = False
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for _ in range(min(max_workers, len(pending))):
            chunk = next(pending_iterator)
            chunk["status"] = "running"
            chunk["attempts"] = int(chunk.get("attempts", 0)) + 1
            futures[pool.submit(run_one, chunk)] = chunk
        publish()
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                chunk = futures.pop(future)
                try:
                    _, manifest_path = future.result()
                except Exception as error:  # noqa: BLE001 - persisted fail-fast boundary
                    chunk["status"] = "failed"
                    chunk["error"] = f"{type(error).__name__}: {error}"
                    failure_seen = True
                else:
                    chunk["status"] = "succeeded"
                    chunk["manifest_path"] = str(manifest_path)
                    chunk["manifest_sha256"] = _sha256_file(manifest_path)
                publish()
            while not failure_seen and len(futures) < max_workers:
                try:
                    chunk = next(pending_iterator)
                except StopIteration:
                    break
                chunk["status"] = "running"
                chunk["attempts"] = int(chunk.get("attempts", 0)) + 1
                futures[pool.submit(run_one, chunk)] = chunk
                publish()

    state["status"] = (
        "failed_stopped" if failure_seen else "complete"
    )
    publish()
    if failure_seen:
        raise BatchOrchestrationError("batch stopped after a chunk failure; state is resumable")
    return state


__all__ = [
    "AGGREGATION_LIST_SCHEMA",
    "BATCH_SCHEMA",
    "DEFAULT_MAX_WORKERS",
    "MAX_WORKERS",
    "V3_CONTRACT",
    "BatchOrchestrationError",
    "WorkloadContractSpec",
    "build_chunk_ranges",
    "load_contract_spec",
    "orchestrate_t2_batch",
]
