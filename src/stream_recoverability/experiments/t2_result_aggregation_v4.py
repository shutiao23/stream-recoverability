"""Global completeness and identity aggregation for frozen T2 v4 chunks."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from .t2_chunk_executor_v4 import V4_CHUNK_SCHEMA, _validate_results
from .t2_workload_v4 import (
    EXPECTED_V4_WORK_ITEMS,
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)

V4_AGGREGATION_SCHEMA = "t2_v91_result_aggregation_v4"


class V4AggregationBlocked(ValueError):
    """Raised when a claimed complete v4 result set is not identity-complete."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V4AggregationBlocked(f"cannot read v4 aggregation input: {path}") from error
    if not isinstance(value, dict):
        raise V4AggregationBlocked(f"v4 aggregation input is not a mapping: {path}")
    return value


def _assert_open(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise V4AggregationBlocked(f"v4 aggregation refuses sealed path: {path}")


def _read_results(path: Path, format_name: str) -> pd.DataFrame:
    if format_name == "parquet":
        return pd.read_parquet(path)
    if format_name == "csv":
        return pd.read_csv(path)
    raise V4AggregationBlocked("unsupported v4 chunk result format")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
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
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def aggregate_v4_chunk_manifests(
    *,
    workload_manifest_path: str | Path,
    chunk_manifest_paths: Sequence[str | Path],
    output_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Prove exact [0,N) coverage and the frozen total item stream SHA."""

    workload_path = Path(workload_manifest_path).resolve()
    _assert_open(workload_path)
    workload = _read_json(workload_path)
    workload_sha = _sha256_file(workload_path)
    if (
        workload.get("manifest_schema") != V4_WORKLOAD_SCHEMA
        or workload.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
        or int(workload.get("n_work_items", -1)) != EXPECTED_V4_WORK_ITEMS
        or workload.get("sealed_temperature_records_read") is not False
    ):
        raise V4AggregationBlocked("v4 aggregation workload contract mismatch")

    loaded: list[tuple[Path, dict[str, Any]]] = []
    for raw_path in chunk_manifest_paths:
        path = Path(raw_path).resolve()
        _assert_open(path)
        manifest = _read_json(path)
        if manifest.get("manifest_schema") != V4_CHUNK_SCHEMA:
            raise V4AggregationBlocked("v4 aggregation received a foreign chunk")
        loaded.append((path, manifest))
    loaded.sort(key=lambda value: int(value[1].get("start_ordinal", -1)))

    expected_start = 0
    stream = hashlib.sha256()
    statuses: Counter[str] = Counter()
    records = 0
    manifest_records: list[dict[str, Any]] = []
    for path, manifest in loaded:
        start = int(manifest.get("start_ordinal", -1))
        end = int(manifest.get("end_ordinal_exclusive", -1))
        if start != expected_start or end <= start:
            raise V4AggregationBlocked("v4 chunks overlap or leave an ordinal gap")
        required = {
            "workload_manifest_sha256": workload_sha,
            "workload_item_identity_sha256": workload["work_item_identity_sha256"],
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "item_index_file_sha256": workload["item_index"]["file_sha256"],
            "completeness": "complete",
            "sealed_temperature_records_read": False,
        }
        for key, expected in required.items():
            if manifest.get(key) != expected:
                raise V4AggregationBlocked(f"v4 chunk binding mismatch: {key}")
        results_path = path.parent / str(manifest.get("results_path", ""))
        if (
            not results_path.is_file()
            or _sha256_file(results_path) != manifest.get("results_sha256")
        ):
            raise V4AggregationBlocked("v4 chunk result bytes differ from manifest")
        frame = _read_results(results_path, str(manifest.get("results_format")))
        if len(frame) != end - start:
            raise V4AggregationBlocked("v4 chunk result count mismatch")
        _validate_results(frame, manifest=manifest, start=start, end=end)
        for item_id in frame["item_id"].astype(str):
            stream.update(item_id.encode("utf-8"))
            stream.update(b"\n")
        statuses.update(frame["status"].astype(str))
        records += len(frame)
        expected_start = end
        manifest_records.append(
            {
                "path": str(path),
                "sha256": _sha256_file(path),
                "start_ordinal": start,
                "end_ordinal_exclusive": end,
                "results_sha256": manifest["results_sha256"],
            }
        )

    stream_sha = stream.hexdigest()
    complete = (
        expected_start == EXPECTED_V4_WORK_ITEMS
        and records == EXPECTED_V4_WORK_ITEMS
        and stream_sha == workload.get("work_item_identity_sha256")
    )
    executions_successful = not bool(
        statuses.get("failed") or statuses.get("external_dependency")
    )
    status = (
        "complete"
        if complete and executions_successful
        else (
            "complete_identity_with_execution_failures"
            if complete
            else "blocked_incomplete_chunk_set"
        )
    )
    result = {
        "manifest_schema": V4_AGGREGATION_SCHEMA,
        "status": status,
        "completeness": "complete" if complete else "incomplete",
        "workload_manifest_path": str(workload_path),
        "workload_manifest_sha256": workload_sha,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "expected_item_records": EXPECTED_V4_WORK_ITEMS,
        "observed_item_records": records,
        "work_item_identity_sha256": stream_sha if complete else None,
        "frozen_work_item_identity_sha256": workload["work_item_identity_sha256"],
        "chunk_manifest_records": manifest_records,
        "n_chunks": len(manifest_records),
        "next_missing_ordinal": expected_start,
        "status_counts": dict(sorted(statuses.items())),
        "all_executions_successful": executions_successful,
        "formal_result_generated": complete and executions_successful,
        "network_inference_status": "withheld_n_lt_100_network_interval",
        "network_interval_reported": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    if output_manifest_path is not None:
        output = Path(output_manifest_path).resolve()
        _assert_open(output)
        _atomic_json(output, result)
    return result


__all__ = [
    "V4_AGGREGATION_SCHEMA",
    "V4AggregationBlocked",
    "aggregate_v4_chunk_manifests",
]
