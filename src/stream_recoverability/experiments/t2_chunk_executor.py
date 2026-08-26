"""Atomic, range-bounded execution of the frozen v9.1 T2 workload.

The historical runner checkpoints one JSON document per work item.  This
module is the production-oriented alternative: one explicit half-open ordinal
range is evaluated into one Parquet or CSV table and published together with
an aggregation-compatible SHA-bound manifest.  It deliberately consumes the
global ordinals from :func:`iter_all_work_items`; filters may not redefine the
ordinal namespace.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import islice
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    RUNNER_CONTRACT_VERSION,
    OpenNetwork,
    discover_failure_closure_networks,
    execute_item,
    iter_all_work_items,
    json_safe,
    load_v91_budget,
)
from stream_recoverability.experiments.t2_result_aggregation import (
    CHUNK_SCHEMA,
    input_inventory_sha256,
)

WORKLOAD_SCHEMA = "t2_v91_open_role_workload_v3"
MAX_CHUNK_ITEMS = 5_000
RESULT_FORMATS = frozenset({"parquet", "csv"})
TERMINAL_STATUSES = frozenset(
    {
        "complete",
        "reference_complete",
        "structural_not_applicable",
        "data_ineligible",
        "external_dependency",
        "failed",
    }
)


class ChunkExecutionError(ValueError):
    """Raised before a chunk can be created or safely resumed."""


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


def _item_stream_sha(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row["item_id"]).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _ordinal_item_sha(rows: Sequence[Mapping[str, Any]]) -> str:
    identities = [
        {"ordinal": int(row["ordinal"]), "item_id": str(row["item_id"])}
        for row in rows
    ]
    return _canonical_sha(identities)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ChunkExecutionError(f"cannot read JSON contract {path}: {error}") from error
    if not isinstance(value, dict):
        raise ChunkExecutionError(f"JSON contract is not a mapping: {path}")
    return value


def _assert_not_sealed_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise ChunkExecutionError(f"refusing a sealed-path chunk input/output: {path}")


def _validate_range(start_ordinal: int, end_ordinal_exclusive: int) -> tuple[int, int]:
    if isinstance(start_ordinal, bool) or isinstance(end_ordinal_exclusive, bool):
        raise ChunkExecutionError("chunk ordinals must be integers")
    try:
        start = int(start_ordinal)
        end = int(end_ordinal_exclusive)
    except (TypeError, ValueError) as error:
        raise ChunkExecutionError("chunk ordinals must be integers") from error
    if start != start_ordinal or end != end_ordinal_exclusive:
        raise ChunkExecutionError("chunk ordinals must be exact integers")
    if start < 0 or end <= start:
        raise ChunkExecutionError("chunk range must satisfy 0 <= start < end")
    if end - start > MAX_CHUNK_ITEMS:
        raise ChunkExecutionError(
            f"chunk range exceeds the {MAX_CHUNK_ITEMS}-item production maximum"
        )
    return start, end


def _load_workload_contract(
    workload_path: Path, design_path: Path
) -> tuple[dict[str, Any], str, str, int]:
    workload = _read_json(workload_path)
    if workload.get("manifest_schema") != WORKLOAD_SCHEMA:
        raise ChunkExecutionError("chunk execution requires the v3 T2 workload")
    if workload.get("runner_contract_version") != RUNNER_CONTRACT_VERSION:
        raise ChunkExecutionError("workload runner contract mismatch")
    workload_sha = _sha256_file(workload_path)
    design_sha = _sha256_file(design_path)
    if workload.get("design_sha256") != design_sha:
        raise ChunkExecutionError("workload/design SHA-256 mismatch")
    if workload.get("sealed_temperature_records_read") is not False:
        raise ChunkExecutionError("workload does not attest that sealed outcomes stayed closed")
    if workload.get("sealed_input_roots_allowed") != []:
        raise ChunkExecutionError("workload permits sealed input roots")
    inventory = workload.get("input_inventory") or {}
    if not isinstance(inventory, dict) or inventory.get("sealed_input_roots_allowed") != []:
        raise ChunkExecutionError("workload input inventory permits sealed roots")
    tier_1 = workload.get("tier_1") or {}
    expected_n = int(tier_1.get("n_work_items") or 0)
    expected_stream_sha = str(
        tier_1.get("work_item_identity_sha256")
        or tier_1.get("workload_item_identity_sha256")
        or ""
    )
    if expected_n < 1 or len(expected_stream_sha) != 64:
        raise ChunkExecutionError("v3 workload lacks its full item-count/SHA binding")
    return workload, workload_sha, design_sha, expected_n


def _validate_network_inventory(
    workload: Mapping[str, Any],
    networks: Sequence[OpenNetwork],
    discovered_inventory: Mapping[str, Any],
) -> tuple[dict[str, str], str, str]:
    declared_inventory = workload.get("input_inventory") or {}
    if dict(discovered_inventory) != dict(declared_inventory):
        raise ChunkExecutionError("current open-role inventory differs from the v3 workload")
    declared_ids = [str(value) for value in (workload.get("network_ids") or [])]
    actual_ids = [network.network_id for network in networks]
    if actual_ids != declared_ids or len(networks) != int(workload.get("n_networks") or 0):
        raise ChunkExecutionError("current network roster differs from the v3 workload")
    input_map = {network.network_id: network.wide_sha256 for network in networks}
    if len(input_map) != len(networks):
        raise ChunkExecutionError("duplicate network ids in current input inventory")
    return (
        input_map,
        input_inventory_sha256(input_map),
        _canonical_sha(declared_inventory),
    )


def _chunk_identity(
    *,
    workload_sha: str,
    design_sha: str,
    input_inventory_sha: str,
    workload_input_inventory_sha: str,
    start: int,
    end: int,
    results_format: str,
) -> str:
    return _canonical_sha(
        {
            "workload_manifest_sha256": workload_sha,
            "design_sha256": design_sha,
            "input_inventory_sha256": input_inventory_sha,
            "workload_input_inventory_sha256": workload_input_inventory_sha,
            "runner_contract_version": RUNNER_CONTRACT_VERSION,
            "start_ordinal": start,
            "end_ordinal_exclusive": end,
            "results_format": results_format,
        }
    )


def _read_results(path: Path, results_format: str) -> pd.DataFrame:
    if results_format == "parquet":
        return pd.read_parquet(path)
    if results_format == "csv":
        return pd.read_csv(path)
    raise ChunkExecutionError(f"unsupported results format: {results_format}")


def _validate_table_identity(
    frame: pd.DataFrame, *, start: int, end: int, manifest: Mapping[str, Any]
) -> None:
    missing = {"ordinal", "item_id", "runner_contract_version", "status"} - set(
        frame.columns
    )
    if missing:
        raise ChunkExecutionError(f"chunk result table lacks fields: {sorted(missing)}")
    ordinals = pd.to_numeric(frame["ordinal"], errors="coerce")
    expected = list(range(start, end))
    if ordinals.isna().any() or [int(value) for value in ordinals] != expected:
        raise ChunkExecutionError("chunk result ordinals are not the declared contiguous range")
    if frame["item_id"].astype(str).duplicated().any():
        raise ChunkExecutionError("chunk result item_id values are not unique")
    if not frame["runner_contract_version"].eq(RUNNER_CONTRACT_VERSION).all():
        raise ChunkExecutionError("chunk rows have a different runner contract")
    if not frame["status"].astype(str).isin(TERMINAL_STATUSES).all():
        raise ChunkExecutionError("chunk contains a non-terminal result status")
    rows = frame[["ordinal", "item_id"]].to_dict(orient="records")
    if manifest.get("ordinal_item_identity_sha256") != _ordinal_item_sha(rows):
        raise ChunkExecutionError("chunk ordinal/item_id SHA-256 mismatch")
    if manifest.get("item_id_stream_sha256") != _item_stream_sha(rows):
        raise ChunkExecutionError("chunk item-id stream SHA-256 mismatch")
    if str(frame.iloc[0]["item_id"]) != manifest.get("first_item_id"):
        raise ChunkExecutionError("chunk first item_id mismatch")
    if str(frame.iloc[-1]["item_id"]) != manifest.get("last_item_id"):
        raise ChunkExecutionError("chunk last item_id mismatch")


def _resume_existing(
    chunk_dir: Path,
    *,
    expected_binding: Mapping[str, Any],
    start: int,
    end: int,
) -> dict[str, Any]:
    manifest_path = chunk_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ChunkExecutionError(
            f"refusing an incomplete or foreign existing chunk directory: {chunk_dir}"
        )
    manifest = _read_json(manifest_path)
    for key, expected in expected_binding.items():
        if manifest.get(key) != expected:
            raise ChunkExecutionError(f"existing chunk binding/hash mismatch for {key}")
    results_name = manifest.get("results_path")
    if not isinstance(results_name, str) or Path(results_name).name != results_name:
        raise ChunkExecutionError("existing chunk has an unsafe result-table path")
    results_path = chunk_dir / results_name
    if not results_path.is_file():
        raise ChunkExecutionError("existing chunk result table is missing")
    if _sha256_file(results_path) != manifest.get("results_sha256"):
        raise ChunkExecutionError("existing chunk result-table SHA-256 mismatch")
    frame = _read_results(results_path, str(manifest.get("results_format")))
    if len(frame) != int(manifest.get("n_records", -1)) or len(frame) != end - start:
        raise ChunkExecutionError("existing chunk result-table row count mismatch")
    _validate_table_identity(frame, start=start, end=end, manifest=manifest)
    input_map = {
        str(key): str(value)
        for key, value in (manifest.get("input_sha256_by_network") or {}).items()
    }
    if input_inventory_sha256(input_map) != manifest.get("input_inventory_sha256"):
        raise ChunkExecutionError("existing chunk input inventory SHA-256 mismatch")
    return manifest


def _write_results(frame: pd.DataFrame, path: Path, results_format: str) -> None:
    if results_format == "parquet":
        frame.to_parquet(path, index=False)
    elif results_format == "csv":
        frame.to_csv(path, index=False)
    else:  # pragma: no cover - validated at entry
        raise ChunkExecutionError(f"unsupported results format: {results_format}")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def execute_t2_chunk(
    *,
    repo_root: str | Path,
    workload_manifest_path: str | Path,
    design_path: str | Path,
    output_dir: str | Path,
    start_ordinal: int,
    end_ordinal_exclusive: int,
    results_format: str = "parquet",
) -> dict[str, Any]:
    """Execute and atomically publish one immutable T2 ordinal chunk.

    A pre-existing, byte-valid chunk with the same binding is returned without
    executing any work items.  Any collision, changed binding, or changed table
    is rejected; completed chunks are never silently overwritten.
    """

    start, end = _validate_range(start_ordinal, end_ordinal_exclusive)
    if results_format not in RESULT_FORMATS:
        raise ChunkExecutionError("results_format must be 'parquet' or 'csv'")
    repo = Path(repo_root).resolve()
    workload_path = Path(workload_manifest_path).resolve()
    design = Path(design_path).resolve()
    output = Path(output_dir).resolve()
    for path in (repo, workload_path, design, output):
        _assert_not_sealed_path(path)
    workload, workload_sha, design_sha, expected_n = _load_workload_contract(
        workload_path, design
    )
    if end > expected_n:
        raise ChunkExecutionError(
            f"chunk end {end} exceeds frozen workload size {expected_n}"
        )
    budget = load_v91_budget(repo)
    if budget.get("design_sha256") != design_sha:
        raise ChunkExecutionError("loaded v9.1 budget differs from the bound design")
    networks, discovered_inventory = discover_failure_closure_networks(repo)
    input_map, inventory_sha, workload_inventory_sha = _validate_network_inventory(
        workload, networks, discovered_inventory
    )
    chunk_sha = _chunk_identity(
        workload_sha=workload_sha,
        design_sha=design_sha,
        input_inventory_sha=inventory_sha,
        workload_input_inventory_sha=workload_inventory_sha,
        start=start,
        end=end,
        results_format=results_format,
    )
    chunk_dir = output / f"chunk_{start:07d}_{end:07d}"
    expected_binding = {
        "manifest_schema": CHUNK_SCHEMA,
        "workload_manifest_sha256": workload_sha,
        "design_sha256": design_sha,
        "workload_input_inventory_sha256": workload_inventory_sha,
        "input_inventory_sha256": inventory_sha,
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "chunk_identity_sha256": chunk_sha,
        "start_ordinal": start,
        "end_ordinal_exclusive": end,
        "n_records": end - start,
        "results_format": results_format,
        "completeness": "complete",
        "sealed_temperature_records_read": False,
    }
    if chunk_dir.exists():
        return _resume_existing(
            chunk_dir, expected_binding=expected_binding, start=start, end=end
        )

    items = list(islice(iter_all_work_items(repo, networks, budget), start, end))
    if len(items) != end - start:
        raise ChunkExecutionError("global work-item stream ended before the requested chunk")
    expected_ordinals = list(range(start, end))
    if [item.ordinal for item in items] != expected_ordinals:
        raise ChunkExecutionError("iter_all_work_items violated global ordinal continuity")
    if len({item.item_id for item in items}) != len(items):
        raise ChunkExecutionError("iter_all_work_items emitted duplicate item_id values")

    lookup = {network.network_id: network for network in networks}
    records: list[dict[str, Any]] = []
    for item in items:
        network = lookup.get(item.network_id)
        if network is None:
            raise ChunkExecutionError(f"work item references an unknown network: {item.network_id}")
        raw = execute_item(repo, network, item)
        record = json_safe(raw)
        if not isinstance(record, dict):
            raise ChunkExecutionError("runner returned a non-mapping result")
        if int(record.get("ordinal", -1)) != item.ordinal or record.get("item_id") != item.item_id:
            raise ChunkExecutionError("runner changed work-item ordinal/item_id identity")
        if record.get("runner_contract_version") != RUNNER_CONTRACT_VERSION:
            raise ChunkExecutionError("runner result contract mismatch")
        if record.get("input_sha256") != network.wide_sha256:
            raise ChunkExecutionError("runner result input SHA-256 mismatch")
        if record.get("sealed_temperature_records_read") is not False:
            raise ChunkExecutionError("runner result does not attest sealed outcomes stayed closed")
        if str(record.get("status")) not in TERMINAL_STATUSES:
            raise ChunkExecutionError("runner returned a non-terminal result status")
        records.append(record)

    frame = pd.DataFrame(records)
    identity_rows = [
        {"ordinal": item.ordinal, "item_id": item.item_id} for item in items
    ]
    manifest: dict[str, Any] = {
        **expected_binding,
        "purpose": "bounded_pipeline_execution_not_evidence",
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "workload_expected_result_records": expected_n,
        "workload_item_identity_sha256": str(
            (workload.get("tier_1") or {}).get("work_item_identity_sha256")
            or (workload.get("tier_1") or {}).get("workload_item_identity_sha256")
        ),
        "ordinal_contiguous": True,
        "first_item_id": items[0].item_id,
        "last_item_id": items[-1].item_id,
        "item_id_stream_sha256": _item_stream_sha(identity_rows),
        "ordinal_item_identity_sha256": _ordinal_item_sha(identity_rows),
        "input_sha256_by_network": input_map,
        "results_path": f"results.{results_format}",
        "status_counts": dict(sorted(Counter(str(row["status"]) for row in records).items())),
        "sealed_temperature_records_read": False,
    }

    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{chunk_dir.name}.", dir=output))
    try:
        result_path = staging / str(manifest["results_path"])
        _write_results(frame, result_path, results_format)
        manifest["results_sha256"] = _sha256_file(result_path)
        manifest_path = staging / "manifest.json"
        payload = (
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
        with manifest_path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.rename(staging, chunk_dir)
        except OSError:
            if not chunk_dir.exists():
                raise
            resumed = _resume_existing(
                chunk_dir, expected_binding=expected_binding, start=start, end=end
            )
            shutil.rmtree(staging)
            return resumed
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return manifest


__all__ = [
    "MAX_CHUNK_ITEMS",
    "ChunkExecutionError",
    "execute_t2_chunk",
]
