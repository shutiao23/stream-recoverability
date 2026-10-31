"""Fail-closed aggregation contract for the v9.1 T2 result workload.

The runner deliberately writes small, resumable result cells.  This module is
the separate boundary between those cells and statistical inference.  It does
not discover or open temperature panels (especially sealed panels): result
sources are identified by a result-set binding or chunk manifest through
paths, record counts, ordinal ranges and item ids.

Incomplete, unbound, or mismatched result sets produce a readiness manifest
only.  CSV/Parquet inference inputs are written only after every frozen work
item is terminal, all executable cells succeeded, and a train-only predictor
contract joins without missing or duplicate keys.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    RUNNER_CONTRACT_VERSION,
)

WORKLOAD_SCHEMAS = frozenset(
    {"t2_v91_open_role_workload_v2", "t2_v91_open_role_workload_v3"}
)
BINDING_SCHEMA = "t2_v91_checkpoint_result_binding_v1"
CHUNK_SCHEMA = "t2_v91_result_chunk_v1"
PREDICTOR_SCHEMA = "t2_v91_train_only_predictors_v1"
READINESS_SCHEMA = "t2_v91_aggregation_readiness_v1"
INFERENCE_SCHEMA = "t2_v91_mixed_model_input_v1"

TERMINAL_STATUSES = {
    "complete",
    "reference_complete",
    "structural_not_applicable",
    "data_ineligible",
    "external_dependency",
    "failed",
}
NON_SUCCESS_STATUSES = {"external_dependency", "failed"}
PREDICTOR_COLUMNS = (
    "predicted_conditional_risk",
    "gap_length_only",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
)
MINIMUM_JOIN_KEYS = ("network_id", "station_id", "gap_length")
MIXED_MODEL_COLUMNS = (
    "observed_recovery_loss",
    "observed_achieved_skill",
    "predicted_conditional_risk",
    "gap_length_only",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
    "network_id",
    "station_id",
    "gap_length",
    "placement",
    "start_index",
    "model",
    "information_condition",
    "task",
    "geometry",
    "role",
    "source_key",
    "item_id",
)


class AggregationContractError(ValueError):
    """Raised when an artifact claims completeness but violates its contract."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AggregationContractError(f"JSON artifact is not a mapping: {path}")
    return payload


def _assert_not_sealed_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.parts):
        raise AggregationContractError(
            f"refusing a sealed-path aggregation input: {path}"
        )


def _checkpoint_paths(checkpoint_dir: str | Path) -> list[Path]:
    """List the checkpoint-v2 result files without reading panels."""

    directory = Path(checkpoint_dir).resolve()
    _assert_not_sealed_path(directory)
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def _load_workload(workload_path: Path, design_path: Path) -> dict[str, Any]:
    _assert_not_sealed_path(workload_path.resolve())
    _assert_not_sealed_path(design_path.resolve())
    workload = _read_json(workload_path)
    if workload.get("manifest_schema") not in WORKLOAD_SCHEMAS:
        raise AggregationContractError("unsupported T2 workload schema")
    if workload.get("runner_contract_version") != RUNNER_CONTRACT_VERSION:
        raise AggregationContractError("runner contract does not match checkpoint_v2")
    if workload.get("sealed_temperature_records_read") is not False:
        raise AggregationContractError(
            "workload does not attest sealed outcomes stayed closed"
        )
    if (workload.get("input_inventory") or {}).get("sealed_input_roots_allowed") != []:
        raise AggregationContractError("workload allowlist permits sealed input roots")
    return workload


def _load_checkpoint_source(
    checkpoint_dir: Path,
    binding_path: Path,
    *,
    checkpoint_namespace: str,
) -> list[dict[str, Any]]:
    _assert_not_sealed_path(binding_path.resolve())
    binding = _read_json(binding_path)
    if binding.get("manifest_schema") != BINDING_SCHEMA:
        raise AggregationContractError("unsupported checkpoint result binding schema")
    paths = _checkpoint_paths(checkpoint_dir)
    required = {
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "checkpoint_namespace": checkpoint_namespace,
        "n_records": len(paths),
        "completeness": "complete",
        "sealed_temperature_records_read": False,
    }
    for key, expected in required.items():
        if binding.get(key) != expected:
            raise AggregationContractError(f"checkpoint binding mismatch for {key}")
    return [_read_json(path) for path in paths]


def _read_table(path: Path, format_name: str) -> pd.DataFrame:
    _assert_not_sealed_path(path.resolve())
    if format_name == "parquet":
        return pd.read_parquet(path)
    if format_name == "csv":
        return pd.read_csv(path)
    raise AggregationContractError(f"unsupported result table format: {format_name}")


def _load_chunks(chunk_manifest_paths: Sequence[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest_path in chunk_manifest_paths:
        _assert_not_sealed_path(manifest_path.resolve())
        manifest = _read_json(manifest_path)
        if manifest.get("manifest_schema") != CHUNK_SCHEMA:
            raise AggregationContractError("unsupported T2 chunk schema")
        for key, expected in {
            "runner_contract_version": RUNNER_CONTRACT_VERSION,
            "completeness": "complete",
            "sealed_temperature_records_read": False,
        }.items():
            if manifest.get(key) != expected:
                raise AggregationContractError(f"chunk manifest mismatch for {key}")
        table_path = (manifest_path.parent / str(manifest["results_path"])).resolve()
        if not table_path.is_file():
            raise AggregationContractError("chunk result table is absent")
        frame = _read_table(table_path, str(manifest.get("results_format")))
        if len(frame) != int(manifest.get("n_records", -1)):
            raise AggregationContractError("chunk row count mismatch")
        start = int(manifest.get("start_ordinal", -1))
        end = int(manifest.get("end_ordinal_exclusive", -1))
        if start < 0 or end <= start or end - start != len(frame):
            raise AggregationContractError("chunk has an invalid [start,end) binding")
        if "ordinal" not in frame or "item_id" not in frame:
            raise AggregationContractError("chunk table omits ordinal/item_id")
        numeric_ordinals = pd.to_numeric(frame["ordinal"], errors="coerce")
        if numeric_ordinals.isna().any() or [
            int(value) for value in numeric_ordinals
        ] != list(range(start, end)):
            raise AggregationContractError(
                "chunk ordinals are not contiguous [start,end)"
            )
        if manifest.get("ordinal_contiguous") is not True:
            raise AggregationContractError("chunk does not attest ordinal continuity")
        if str(frame.iloc[0]["item_id"]) != manifest.get("first_item_id"):
            raise AggregationContractError("chunk first item_id mismatch")
        if str(frame.iloc[-1]["item_id"]) != manifest.get("last_item_id"):
            raise AggregationContractError("chunk last item_id mismatch")
        records.extend(frame.where(pd.notna(frame), None).to_dict(orient="records"))
    return records


def _validate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_n: int,
) -> tuple[pd.DataFrame, list[str]]:
    required = {
        "ordinal",
        "item_id",
        "network_id",
        "target_station",
        "model",
        "gap_length",
        "placement",
        "start_index",
        "information_condition",
        "task",
        "geometry",
        "runner_contract_version",
        "status",
    }
    ordinals: list[int] = []
    item_ids: list[str] = []
    status_counts = Counter()
    normalized: list[dict[str, Any]] = []
    for raw in records:
        missing = required - set(raw)
        if missing:
            raise AggregationContractError(
                f"result row missing fields: {sorted(missing)}"
            )
        record = dict(raw)
        if record["runner_contract_version"] != RUNNER_CONTRACT_VERSION:
            raise AggregationContractError("result row runner contract mismatch")
        status = str(record["status"])
        if status not in TERMINAL_STATUSES:
            raise AggregationContractError(
                f"non-terminal/unknown result status: {status}"
            )
        if record.get("sealed_temperature_records_read") is True:
            raise AggregationContractError(
                "result row reports reading sealed temperature outcomes"
            )
        if status in {"complete", "reference_complete"}:
            for metric in ("mae_deg_c", "achieved_skill"):
                value = pd.to_numeric(
                    pd.Series([record.get(metric)]), errors="coerce"
                ).iloc[0]
                if not np.isfinite(value):
                    raise AggregationContractError(
                        f"complete row has non-finite {metric}"
                    )
        ordinals.append(int(record["ordinal"]))
        item_ids.append(str(record["item_id"]))
        status_counts[status] += 1
        normalized.append(record)
    if len(set(ordinals)) != len(ordinals) or len(set(item_ids)) != len(item_ids):
        raise AggregationContractError(
            "duplicate ordinal or item_id across result sources"
        )
    if any(ordinal < 0 or ordinal >= expected_n for ordinal in ordinals):
        raise AggregationContractError(
            "result ordinal lies outside the frozen workload"
        )
    blockers: list[str] = []
    complete_identity_stream = len(records) == expected_n and set(ordinals) == set(
        range(expected_n)
    )
    if not complete_identity_stream:
        blockers.append(f"result_workload_incomplete_{len(records)}_of_{expected_n}")
    for status in sorted(NON_SUCCESS_STATUSES):
        if status_counts[status]:
            blockers.append(f"{status}_cells_{status_counts[status]}")
    return pd.DataFrame(normalized), blockers


def _workload_scope_blockers(workload: Mapping[str, Any]) -> list[str]:
    blockers = []
    for geometry, status in (workload.get("geometry_dependencies") or {}).items():
        if not str(status).startswith("ready"):
            blockers.append(f"geometry_{geometry}_{status}")
    online = (workload.get("tier_1") or {}).get("online_causal_status")
    if online and online != "ready":
        blockers.append(f"online_causal_{online}")
    return blockers


def _load_predictors(manifest_path: Path) -> tuple[pd.DataFrame, list[str]]:
    _assert_not_sealed_path(manifest_path.resolve())
    manifest = _read_json(manifest_path)
    if manifest.get("manifest_schema") != PREDICTOR_SCHEMA:
        raise AggregationContractError("unsupported train-only predictor schema")
    for key, expected in {
        "fit_role": "development",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "sealed_temperature_records_read": False,
        "completeness": "complete",
    }.items():
        if manifest.get(key) != expected:
            raise AggregationContractError(f"predictor contract mismatch for {key}")
    table_path = (manifest_path.parent / str(manifest["predictions_path"])).resolve()
    if not table_path.is_file():
        raise AggregationContractError("predictor table is absent")
    predictors = _read_table(table_path, str(manifest.get("predictions_format")))
    join_keys = [str(value) for value in (manifest.get("join_keys") or [])]
    if not set(MINIMUM_JOIN_KEYS).issubset(join_keys):
        raise AggregationContractError("predictor join keys omit network/station/gap")
    missing = set(join_keys).union(PREDICTOR_COLUMNS) - set(predictors.columns)
    if missing:
        raise AggregationContractError(
            f"predictor table missing columns: {sorted(missing)}"
        )
    if predictors.duplicated(join_keys).any():
        raise AggregationContractError("predictor join keys are not unique")
    for name in PREDICTOR_COLUMNS:
        numeric = pd.to_numeric(predictors[name], errors="coerce")
        if not np.isfinite(numeric).all():
            raise AggregationContractError(f"predictor column is not finite: {name}")
        predictors[name] = numeric.astype(float)
    return predictors, join_keys


def _blocked_manifest(
    *,
    workload_path: Path,
    design_path: Path,
    expected_n: int,
    observed_n: int,
    n_networks: int,
    blockers: Sequence[str],
) -> dict[str, Any]:
    inference_status = (
        "withheld_n_lt_100_network_interval"
        if n_networks < 100
        else "withheld_aggregation_not_ready"
    )
    return {
        "manifest_schema": READINESS_SCHEMA,
        "status": "blocked",
        "purpose": "pipeline_readiness_not_evidence",
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "workload_manifest_path": str(workload_path),
        "design_path": str(design_path),
        "expected_result_records": int(expected_n),
        "observed_result_records": int(observed_n),
        "n_networks": int(n_networks),
        "network_inference_status": inference_status,
        "network_interval": None,
        "blockers": list(dict.fromkeys(str(value) for value in blockers)),
        "inference_tables_written": False,
        "sealed_temperature_records_read": False,
    }


def aggregate_t2_results(
    *,
    workload_manifest_path: str | Path,
    design_path: str | Path,
    output_dir: str | Path,
    checkpoint_dir: str | Path | None = None,
    checkpoint_binding_path: str | Path | None = None,
    chunk_manifest_paths: Sequence[str | Path] = (),
    predictor_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate sources and write either readiness-only or mixed-model tables."""

    workload_path = Path(workload_manifest_path).resolve()
    design = Path(design_path).resolve()
    output = Path(output_dir).resolve()
    workload = _load_workload(workload_path, design)
    expected_n = int((workload.get("tier_1") or {}).get("n_work_items") or 0)
    checkpoint_namespace = str(
        (workload.get("tier_1") or {}).get("checkpoint_namespace") or "checkpoints_v2"
    )
    n_networks = int(workload.get("n_networks") or 0)
    blockers = _workload_scope_blockers(workload)
    records: list[dict[str, Any]] = []

    checkpoint_paths = []
    if checkpoint_dir is not None:
        checkpoint_paths = _checkpoint_paths(checkpoint_dir)
        if checkpoint_binding_path is None:
            blockers.append("checkpoint_result_set_missing_binding")
        else:
            records.extend(
                _load_checkpoint_source(
                    Path(checkpoint_dir),
                    Path(checkpoint_binding_path),
                    checkpoint_namespace=checkpoint_namespace,
                )
            )
    if chunk_manifest_paths:
        records.extend(_load_chunks([Path(value) for value in chunk_manifest_paths]))
    if not records:
        blockers.append("no_bound_result_records")

    frame = pd.DataFrame()
    if records:
        frame, record_blockers = _validate_records(records, expected_n=expected_n)
        blockers.extend(record_blockers)
    elif checkpoint_paths:
        blockers.append(
            f"result_workload_incomplete_{len(checkpoint_paths)}_of_{expected_n}"
        )
    elif expected_n:
        blockers.append(f"result_workload_incomplete_0_of_{expected_n}")

    if predictor_manifest_path is None:
        blockers.append("missing_train_only_operator_and_univariate_predictor_contract")

    readiness = output / "readiness_manifest.json"
    output.mkdir(parents=True, exist_ok=True)
    if blockers:
        manifest = _blocked_manifest(
            workload_path=workload_path,
            design_path=design,
            expected_n=expected_n,
            observed_n=len(records),
            n_networks=n_networks,
            blockers=blockers,
        )
        # A prior ready run must never leave result-looking tables beside a
        # newer blocked manifest.
        for stale_name in ("t2_mixed_model_input.csv", "t2_mixed_model_input.parquet"):
            stale = output / stale_name
            if stale.is_file():
                stale.unlink()
        readiness.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest

    predictors, join_keys = _load_predictors(Path(predictor_manifest_path))
    outcomes = frame.loc[frame["status"].eq("complete")].copy()
    outcomes = outcomes.rename(
        columns={
            "target_station": "station_id",
            "mae_deg_c": "observed_recovery_loss",
            "achieved_skill": "observed_achieved_skill",
        }
    )
    before = len(outcomes)
    joined = outcomes.merge(
        predictors, on=join_keys, how="left", validate="many_to_one"
    )
    if joined[list(PREDICTOR_COLUMNS)].isna().any(axis=None):
        manifest = _blocked_manifest(
            workload_path=workload_path,
            design_path=design,
            expected_n=expected_n,
            observed_n=len(records),
            n_networks=int(outcomes["network_id"].nunique()),
            blockers=["predictor_join_has_missing_rows"],
        )
        readiness.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest
    if len(joined) != before:
        raise AggregationContractError("predictor join changed outcome row cardinality")
    missing_schema = set(MIXED_MODEL_COLUMNS) - set(joined.columns)
    if missing_schema:
        raise AggregationContractError(
            f"mixed-model schema missing columns: {sorted(missing_schema)}"
        )
    table = joined[list(MIXED_MODEL_COLUMNS)].sort_values(
        [
            "network_id",
            "station_id",
            "gap_length",
            "placement",
            "model",
            "information_condition",
        ]
    )
    csv_path = output / "t2_mixed_model_input.csv"
    parquet_path = output / "t2_mixed_model_input.parquet"
    table.to_csv(csv_path, index=False)
    table.to_parquet(parquet_path, index=False)
    actual_networks = int(table["network_id"].nunique())
    inference_status = (
        "withheld_n_lt_100_network_interval"
        if actual_networks < 100
        else "ready_for_hierarchical_confirmation_not_evaluated"
    )
    manifest = {
        "manifest_schema": READINESS_SCHEMA,
        "inference_input_schema": INFERENCE_SCHEMA,
        "status": "ready",
        "purpose": "mixed_model_input_not_a_result",
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "workload_manifest_path": str(workload_path),
        "design_path": str(design),
        "expected_result_records": expected_n,
        "observed_result_records": len(records),
        "n_inference_rows": len(table),
        "n_networks": actual_networks,
        "network_inference_status": inference_status,
        "network_interval": None,
        "join_keys": join_keys,
        "csv": {"path": csv_path.name},
        "parquet": {"path": parquet_path.name},
        "inference_tables_written": True,
        "sealed_temperature_records_read": False,
    }
    readiness.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


__all__ = [
    "BINDING_SCHEMA",
    "CHUNK_SCHEMA",
    "INFERENCE_SCHEMA",
    "MIXED_MODEL_COLUMNS",
    "PREDICTOR_COLUMNS",
    "PREDICTOR_SCHEMA",
    "READINESS_SCHEMA",
    "AggregationContractError",
    "aggregate_t2_results",
]
