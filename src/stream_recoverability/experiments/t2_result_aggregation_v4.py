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
import pyarrow as pa
import pyarrow.parquet as pq

from .t2_chunk_executor_v4 import V4_CHUNK_SCHEMA, _validate_results
from .t2_workload_v4 import (
    EXECUTION_CODE_INVENTORY_SCHEMA,
    EXECUTION_CODE_PATHS,
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
        raise V4AggregationBlocked(
            f"cannot read v4 aggregation input: {path}"
        ) from error
    if not isinstance(value, dict):
        raise V4AggregationBlocked(f"v4 aggregation input is not a mapping: {path}")
    return value


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _assert_open(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise V4AggregationBlocked(f"v4 aggregation refuses sealed path: {path}")


def _read_results(path: Path, format_name: str) -> pd.DataFrame:
    if format_name == "parquet":
        return pd.read_parquet(path)
    if format_name == "csv":
        return pd.read_csv(
            path,
            dtype={
                "item_id": "string",
                "network_id": "string",
                "target_station": "string",
            },
        )
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


def _create_once_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise V4AggregationBlocked("formal aggregation manifest is create-once")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _install_create_once(path: Path, temporary: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if _sha256_file(path) != _sha256_file(temporary):
            raise V4AggregationBlocked("create-once merged result already differs")
        return
    try:
        os.link(temporary, path)
    except FileExistsError:
        if _sha256_file(path) != _sha256_file(temporary):
            raise V4AggregationBlocked("concurrent merged result differs")
    os.chmod(path, 0o444)


def _expected_identities(index_path: Path, start: int, end: int) -> pd.DataFrame:
    frame = pd.read_parquet(
        index_path,
        filters=[("ordinal", ">=", start), ("ordinal", "<", end)],
        columns=["ordinal", "item_id", "meteorology_lag_days", "source_item_json"],
    ).sort_values("ordinal", kind="stable")
    rows = []
    for raw in frame.to_dict(orient="records"):
        source = json.loads(str(raw["source_item_json"]))
        rows.append(
            {
                "ordinal": int(raw["ordinal"]),
                "item_id": str(raw["item_id"]),
                "role": str(source["role"]),
                "network_id": str(source["network_id"]),
                "target_station": str(source["target_station"]),
                "model": str(source["model"]),
                "gap_length": int(source["gap_length"]),
                "placement": int(source["placement"]),
                "start_index": int(source["start_index"]),
                "information_condition": str(source["information_condition"]),
                "task": str(source["task"]),
                "geometry": str(source["geometry"]),
                "geometry_id": str(source.get("geometry_id") or ""),
                "truth_start_date": str(source.get("truth_start_date") or ""),
                "observed_missing_start_date": str(
                    source.get("observed_missing_start_date") or ""
                ),
                "meteorology_lag_days": str(raw["meteorology_lag_days"]),
            }
        )
    return pd.DataFrame(rows)


def _assert_full_row_identities(results: pd.DataFrame, expected: pd.DataFrame) -> None:
    columns = list(expected.columns)
    missing = set(columns) - set(results.columns)
    if missing:
        raise V4AggregationBlocked(
            f"v4 results omit frozen identity fields: {sorted(missing)}"
        )
    actual = results.loc[:, columns].copy()
    for column in columns:
        if column in {"ordinal", "gap_length", "placement", "start_index"}:
            actual[column] = pd.to_numeric(actual[column], errors="coerce")
            expected[column] = pd.to_numeric(expected[column], errors="coerce")
        elif column == "meteorology_lag_days":
            actual[column] = pd.to_numeric(actual[column], errors="coerce").map(
                lambda value: "none" if pd.isna(value) else str(int(value))
            )
        else:
            actual[column] = actual[column].fillna("").astype(str)
            expected[column] = expected[column].fillna("").astype(str)
    if not actual.reset_index(drop=True).equals(expected.reset_index(drop=True)):
        raise V4AggregationBlocked(
            "v4 result row identities differ from frozen item index"
        )


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
    code_inventory = workload.get("execution_code_inventory")
    if (
        not isinstance(code_inventory, Mapping)
        or code_inventory.get("manifest_schema") != EXECUTION_CODE_INVENTORY_SCHEMA
        or code_inventory.get("path_roster") != list(EXECUTION_CODE_PATHS)
        or code_inventory.get("all_paths_committed_unchanged") is not True
        or code_inventory.get("inventory_sha256")
        != _canonical_sha(code_inventory.get("paths") or [])
    ):
        raise V4AggregationBlocked("v4 aggregation code inventory mismatch")
    code_inventory_sha = str(code_inventory["inventory_sha256"])
    index_record = workload.get("item_index") or {}
    index_path = Path(str(index_record.get("path", "")))
    if not index_path.is_absolute():
        index_path = (workload_path.parent / index_path).resolve()
        if not index_path.exists():
            for parent in workload_path.parents:
                if (parent / "pyproject.toml").is_file():
                    index_path = (parent / str(index_record.get("path", ""))).resolve()
                    break
    if not index_path.is_file() or _sha256_file(index_path) != index_record.get(
        "file_sha256"
    ):
        raise V4AggregationBlocked("v4 aggregation cannot verify the frozen item index")

    output = (
        Path(output_manifest_path).resolve()
        if output_manifest_path is not None
        else workload_path.parent / "aggregation_v4" / "manifest.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".merged_results.", suffix=".parquet.tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()

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
    validated_results: list[tuple[Path, str]] = []
    result_schemas: list[pa.Schema] = []
    execution_head: str | None = None
    try:
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
                "pre_score_freeze_sha256": (workload.get("pre_score_freeze") or {}).get(
                    "sha256"
                ),
                "execution_code_inventory_sha256": code_inventory_sha,
            }
            for key, expected in required.items():
                if manifest.get(key) != expected:
                    raise V4AggregationBlocked(f"v4 chunk binding mismatch: {key}")
            chunk_head = str(manifest.get("execution_head_commit", ""))
            if len(chunk_head) not in {40, 64} or any(
                character not in "0123456789abcdef" for character in chunk_head
            ):
                raise V4AggregationBlocked("v4 chunk lacks a valid execution HEAD")
            if execution_head is None:
                execution_head = chunk_head
            elif chunk_head != execution_head:
                raise V4AggregationBlocked("v4 chunks used different execution HEADs")
            results_path = path.parent / str(manifest.get("results_path", ""))
            if not results_path.is_file() or _sha256_file(results_path) != manifest.get(
                "results_sha256"
            ):
                raise V4AggregationBlocked("v4 chunk result bytes differ from manifest")
            frame = _read_results(results_path, str(manifest.get("results_format")))
            if len(frame) != end - start:
                raise V4AggregationBlocked("v4 chunk result count mismatch")
            _validate_results(frame, manifest=manifest, start=start, end=end)
            _assert_full_row_identities(
                frame, _expected_identities(index_path, start, end)
            )
            table = pa.Table.from_pandas(frame, preserve_index=False)
            result_schemas.append(table.schema)
            validated_results.append(
                (results_path, str(manifest.get("results_format")))
            )
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
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

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
        "pre_score_freeze_sha256": (workload.get("pre_score_freeze") or {}).get(
            "sha256"
        ),
        "execution_head_commit": execution_head,
        "execution_code_inventory_sha256": code_inventory_sha,
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
    if complete and executions_successful:
        union_schema = pa.unify_schemas(result_schemas, promote_options="permissive")
        writer = pq.ParquetWriter(temporary, union_schema, compression="zstd")
        try:
            for result_path, result_format in validated_results:
                frame = _read_results(result_path, result_format)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                arrays = []
                for field in union_schema:
                    if field.name in table.column_names:
                        arrays.append(table[field.name].cast(field.type))
                    else:
                        arrays.append(pa.nulls(len(table), type=field.type))
                writer.write_table(pa.Table.from_arrays(arrays, schema=union_schema))
        finally:
            writer.close()
        merged = output.parent / "item_results.parquet"
        _install_create_once(merged, temporary)
        result["merged_item_results"] = {
            "path": merged.name,
            "format": "parquet",
            "sha256": _sha256_file(merged),
            "n_rows": records,
        }
        result["chunk_manifest_set_sha256"] = hashlib.sha256(
            json.dumps(manifest_records, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    else:
        result["merged_item_results"] = None
    if temporary.exists():
        temporary.unlink()
    manifest_output = (
        output
        if complete and executions_successful
        else output.parent / "partial_readiness_manifest.json"
    )
    _assert_open(manifest_output)
    if complete and executions_successful:
        _create_once_json(manifest_output, result)
    else:
        _atomic_json(manifest_output, result)
    return result


__all__ = [
    "V4_AGGREGATION_SCHEMA",
    "V4AggregationBlocked",
    "aggregate_v4_chunk_manifests",
]
