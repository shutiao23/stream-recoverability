"""Outcome-blind T2 v4 lattice freeze and post-score primary binding.

The first phase is deliberately unable to accept a result table.  It freezes
the exact item rows, common model/information/lag grid, and weights using only
the v4 item index, a SHA-bound pre-score eligibility audit, and the existing
train-only predictor sidecar.  The second phase can run only against those
create-once bytes and never chooses rows using ``achieved_skill``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .t2_recovery_benchmark import (
    EXTENDED_INFORMATION_CONDITIONS,
    WorkItem,
    _cell_contract,
)
from .t2_result_aggregation_v4 import V4_AGGREGATION_SCHEMA
from .t2_train_only_predictors import JOIN_KEYS, PREDICTOR_COLUMNS, SIDECAR_SCHEMA
from .t2_workload_v4 import (
    V4_ITEM_INDEX_SCHEMA,
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)
from .t4_t5_post_t2 import (
    INPUT_BINDING_SCHEMA,
    OPERATOR_JOIN_KEYS,
    OPERATOR_PREDICTOR_SCHEMA,
    PRIMARY_IDENTITY_COLUMNS,
)

LATTICE_FREEZE_SCHEMA = "t2_v91_v4_analyzable_lattice_freeze_v1"
ELIGIBILITY_AUDIT_SCHEMA = "t2_v91_v4_pre_score_eligibility_audit_v1"
READINESS_SCHEMA = "t2_v91_v4_primary_aggregation_readiness_v2"
TERMINAL_RESULT_STATUSES = frozenset(
    {"complete", "reference_complete", "structural_not_applicable", "data_ineligible"}
)
FORBIDDEN_OUTCOME_COLUMNS = frozenset(
    {
        "achieved_skill",
        "observed_achieved_skill",
        "fill_mae",
        "mae_deg_c",
        "recoverability",
        "predicted_recoverability",
    }
)

# This grid is frozen independently of event outcomes.  Artificial placements
# and eligible natural counterparts can support every cell.  Adversarial
# geometries that remove B or D are retained in the workload but cannot enter
# this common primary lattice.
PRIMARY_COMMON_GRID = (
    ("pchip_or_linear", "B", "offline_archival", "none"),
    ("kalman", "B", "offline_archival", "none"),
    ("donor_regression", "D", "offline_archival", "none"),
    ("xgboost", "D", "offline_archival", "none"),
    ("donor_regression", "B_union_D", "offline_archival", "none"),
    ("xgboost", "B_union_D", "offline_archival", "none"),
    *tuple(
        (model, information, "offline_archival", str(lag))
        for model in ("donor_regression", "xgboost")
        for information in EXTENDED_INFORMATION_CONDITIONS
        for lag in (-1, 0, 1)
    ),
)


class PrimaryAggregationBlocked(ValueError):
    """Raised when a present artifact violates the pre/post-score boundary."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PrimaryAggregationBlocked(f"cannot read primary binding input: {path}") from error
    if not isinstance(value, dict):
        raise PrimaryAggregationBlocked(f"primary binding input is not a mapping: {path}")
    return value


def _assert_open(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise PrimaryAggregationBlocked(f"primary binding refuses sealed path: {path}")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _create_once_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise PrimaryAggregationBlocked(f"frozen artifact already differs: {path}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _create_once_table(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    frame.to_parquet(temporary, index=False)
    try:
        if path.exists():
            if _sha256_file(path) != _sha256_file(temporary):
                raise PrimaryAggregationBlocked(f"frozen artifact already differs: {path}")
            return
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _artifact_path(manifest_path: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    local = (manifest_path.parent / path).resolve()
    if local.exists():
        return local
    for parent in (manifest_path.parent, *manifest_path.parents):
        if (parent / "pyproject.toml").is_file():
            return (parent / path).resolve()
    return local


def _stream_sha(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for item_id in frame.sort_values("ordinal", kind="stable")["item_id"].astype(str):
        digest.update(item_id.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _source_rows(index: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in index.to_dict(orient="records"):
        source = json.loads(str(record["source_item_json"]))
        lag = str(record["meteorology_lag_days"])
        rows.append(
            {
                "ordinal": int(record["ordinal"]),
                "item_id": str(record["item_id"]),
                "role": str(source["role"]),
                "network_id": str(source["network_id"]),
                "station_id": str(source["target_station"]),
                "geometry": str(source["geometry"]),
                "geometry_id": str(source.get("geometry_id") or ""),
                "truth_start_date": str(source.get("truth_start_date") or ""),
                "observed_missing_start_date": str(
                    source.get("observed_missing_start_date") or ""
                ),
                "gap_length": int(source["gap_length"]),
                "placement": int(source["placement"]),
                "start_index": int(source["start_index"]),
                "model": str(source["model"]),
                "information_condition": str(source["information_condition"]),
                "task": str(source["task"]),
                "meteorology_lag_days": lag,
                "source_item_json": str(record["source_item_json"]),
            }
        )
    return pd.DataFrame(rows)


def _structural_status(source_json: str | Mapping[str, Any], lag: str) -> str:
    source = json.loads(source_json) if isinstance(source_json, str) else dict(source_json)
    item = WorkItem(**source)
    if item.information_condition in EXTENDED_INFORMATION_CONDITIONS:
        if item.start_index < 0:
            return "data_ineligible"
        if item.model == "climatology":
            return "reference_complete"
        if item.model not in {"donor_regression", "xgboost"}:
            return "structural_not_applicable"
        if item.boundary_mode == "none" or item.donor_mask_rule == (
            "mask_all_network_stations_during_gap"
        ):
            return "structural_not_applicable"
        return "complete" if lag in {"-1", "0", "1"} else "structural_not_applicable"
    contract = _cell_contract(item)
    category = str(contract["category"])
    return {
        "executable": "complete",
        "reference": "reference_complete",
        "data_ineligible": "data_ineligible",
        "structural_not_applicable": "structural_not_applicable",
    }.get(category, "structural_not_applicable")


def _load_workload_index(workload_path: Path) -> tuple[dict[str, Any], pd.DataFrame, Path]:
    workload = _read_json(workload_path)
    if (
        workload.get("manifest_schema") != V4_WORKLOAD_SCHEMA
        or workload.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
        or workload.get("sealed_paths_traversed") is not False
        or workload.get("sealed_temperature_records_read") is not False
    ):
        raise PrimaryAggregationBlocked("v4 workload/open-custody contract mismatch")
    record = workload.get("item_index")
    if not isinstance(record, Mapping):
        raise PrimaryAggregationBlocked("v4 item index metadata is absent")
    index_path = _artifact_path(workload_path, str(record.get("path", "")))
    _assert_open(index_path)
    if not index_path.is_file():
        raise PrimaryAggregationBlocked("v4 item index is absent")
    if (
        record.get("manifest_schema") != V4_ITEM_INDEX_SCHEMA
        or _sha256_file(index_path) != record.get("file_sha256")
    ):
        raise PrimaryAggregationBlocked("v4 item index identity mismatch")
    index = pd.read_parquet(index_path).sort_values("ordinal", kind="stable")
    n_items = int(workload.get("n_work_items", -1))
    if (
        len(index) != n_items
        or index["ordinal"].astype(int).tolist() != list(range(n_items))
        or _stream_sha(index) != workload.get("work_item_identity_sha256")
    ):
        raise PrimaryAggregationBlocked("v4 item index is not the complete frozen stream")
    return workload, index, index_path


def _load_sidecar(
    manifest_path: Path,
) -> tuple[dict[str, Any], pd.DataFrame, Path]:
    manifest = _read_json(manifest_path)
    required = {
        "manifest_schema": SIDECAR_SCHEMA,
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "recovery_result_rows_read": False,
        "sealed_temperature_records_read": False,
        "completeness": "complete",
        "join_keys": list(JOIN_KEYS),
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise PrimaryAggregationBlocked(f"train-only sidecar mismatch for {key}")
    path = _artifact_path(manifest_path, str(manifest.get("parquet_path", "")))
    _assert_open(path)
    if not path.is_file() or _sha256_file(path) != manifest.get("parquet_sha256"):
        raise PrimaryAggregationBlocked("train-only predictor table SHA mismatch")
    predictors = pd.read_parquet(path)
    required_columns = {*JOIN_KEYS, *PREDICTOR_COLUMNS}
    if not required_columns.issubset(predictors.columns):
        raise PrimaryAggregationBlocked("train-only predictor table lacks frozen columns")
    if predictors.duplicated(list(JOIN_KEYS)).any():
        raise PrimaryAggregationBlocked("train-only predictor keys are not unique")
    return manifest, predictors, path


def _load_eligibility(
    manifest_path: Path,
    *,
    workload_path: Path,
    workload: Mapping[str, Any],
    index_path: Path,
    item_ids: set[str],
) -> tuple[dict[str, Any], pd.DataFrame, Path]:
    manifest = _read_json(manifest_path)
    coverage_map = {
        str(network): str((record or {}).get("coverage_sha256", ""))
        for network, record in (workload.get("auxiliary_network_bindings") or {}).items()
    }
    required = {
        "manifest_schema": ELIGIBILITY_AUDIT_SCHEMA,
        "builder_schema": "t2_v91_v4_pre_score_eligibility_builder_v1",
        "status": "complete_outcome_blind_pre_score_audit",
        "completeness": "complete",
        "workload_manifest_sha256": _sha256_file(workload_path),
        "item_index_file_sha256": _sha256_file(index_path),
        "input_qc_inventory_sha256": workload.get("input_sha256_by_network_sha256"),
        "auxiliary_coverage_bindings_sha256": _canonical_sha(coverage_map),
        "placements_read_from_frozen_item_index": True,
        "selection_uses_outcomes": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "open_qc_date_labels_read": True,
        "open_qc_station_header_read": True,
        "open_qc_temperature_value_columns_read": [],
        "open_qc_temperature_na_availability_read": False,
        "gap_truth_values_read": False,
        "auxiliary_provider_qc_values_read_for_declared_information_coverage": True,
        "temperature_date_and_roster_classification": (
            "design_metadata_not_recovery_outcome"
        ),
        "model_fit_or_prediction_run": False,
        "old_outcomes_read": False,
        "expected_item_records": len(item_ids),
        "observed_item_records": len(item_ids),
        "work_item_identity_sha256": workload.get("work_item_identity_sha256"),
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise PrimaryAggregationBlocked(f"pre-score eligibility mismatch for {key}")
    record = manifest.get("eligibility_table")
    if not isinstance(record, Mapping):
        raise PrimaryAggregationBlocked("pre-score eligibility table is unbound")
    table_path = _artifact_path(manifest_path, str(record.get("path", "")))
    _assert_open(table_path)
    if not table_path.is_file() or _sha256_file(table_path) != record.get("sha256"):
        raise PrimaryAggregationBlocked("pre-score eligibility table SHA mismatch")
    table = pd.read_parquet(table_path)
    forbidden = FORBIDDEN_OUTCOME_COLUMNS.intersection(table.columns)
    required_columns = {"item_id", "pre_score_status", "reason"}
    if forbidden or not required_columns.issubset(table.columns):
        raise PrimaryAggregationBlocked("pre-score eligibility is not outcome-blind")
    if (
        len(table) != int(record.get("n_rows", -1))
        or len(table) != len(item_ids)
        or table["item_id"].astype(str).duplicated().any()
        or set(table["item_id"].astype(str)) != item_ids
    ):
        raise PrimaryAggregationBlocked("pre-score eligibility does not cover the item index")
    allowed = {"complete", "reference_complete", "structural_not_applicable", "data_ineligible"}
    if not set(table["pre_score_status"].astype(str)).issubset(allowed):
        raise PrimaryAggregationBlocked("pre-score eligibility contains an unknown status")
    ineligible = table["pre_score_status"].astype(str).eq("data_ineligible")
    if table.loc[ineligible, "reason"].fillna("").astype(str).str.strip().eq("").any():
        raise PrimaryAggregationBlocked("data-ineligible pre-score audit has a blank reason")
    return manifest, table, table_path


def _blocked_readiness(output_dir: Path, blockers: list[str]) -> dict[str, Any]:
    manifest = {
        "manifest_schema": READINESS_SCHEMA,
        "status": "blocked_waiting_for_frozen_v4_item_index",
        "blockers": blockers,
        "analyzable_lattice_frozen": False,
        "v4_results_read": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    _atomic_json(output_dir / "readiness_manifest.json", manifest)
    return manifest


def freeze_v4_analyzable_lattice(
    *,
    workload_manifest_path: str | Path,
    predictor_manifest_path: str | Path,
    eligibility_manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create the outcome-blind lattice before any v4 result scoring."""

    workload_path = Path(workload_manifest_path).resolve()
    predictor_manifest_file = Path(predictor_manifest_path).resolve()
    eligibility_manifest_file = Path(eligibility_manifest_path).resolve()
    output = Path(output_dir).resolve()
    for path in (workload_path, predictor_manifest_file, eligibility_manifest_file, output):
        _assert_open(path)
    if not workload_path.is_file():
        return _blocked_readiness(output, ["v4_workload_manifest_absent", "v4_item_index_absent"])
    try:
        workload, raw_index, index_path = _load_workload_index(workload_path)
    except PrimaryAggregationBlocked as error:
        if "item index" in str(error):
            return _blocked_readiness(output, ["v4_item_index_absent_or_invalid"])
        raise
    if not predictor_manifest_file.is_file() or not eligibility_manifest_file.is_file():
        blockers = []
        if not predictor_manifest_file.is_file():
            blockers.append("train_only_predictor_sidecar_absent")
        if not eligibility_manifest_file.is_file():
            blockers.append("outcome_blind_pre_score_eligibility_audit_absent")
        return _blocked_readiness(output, blockers)

    _, sidecar, sidecar_path = _load_sidecar(predictor_manifest_file)
    index = _source_rows(raw_index)
    _, eligibility, eligibility_path = _load_eligibility(
        eligibility_manifest_file,
        workload_path=workload_path,
        workload=workload,
        index_path=index_path,
        item_ids=set(index["item_id"]),
    )
    eligibility = eligibility.assign(item_id=eligibility["item_id"].astype(str))
    index = index.merge(eligibility, on="item_id", how="left", validate="one_to_one")
    expected = index.apply(
        lambda row: _structural_status(row["source_item_json"], row["meteorology_lag_days"]),
        axis=1,
    )
    audit_status = index["pre_score_status"].astype(str)
    structural = expected.ne("complete")
    if not audit_status.loc[structural].eq(expected.loc[structural]).all():
        raise PrimaryAggregationBlocked("pre-score audit contradicts structural applicability")
    if not audit_status.loc[~structural].isin({"complete", "data_ineligible"}).all():
        raise PrimaryAggregationBlocked("pre-score audit changed an executable cell structurally")

    sidecar_keys = sidecar.loc[:, list(JOIN_KEYS)].copy()
    sidecar_keys["station_id"] = sidecar_keys["station_id"].astype(str)
    index["station_id"] = index["station_id"].astype(str)
    index = index.merge(
        sidecar_keys.assign(predictor_eligible=True),
        on=list(JOIN_KEYS),
        how="left",
        validate="many_to_one",
    )
    index["predictor_eligible"] = index["predictor_eligible"].fillna(False)
    index["grid_cell"] = list(
        zip(
            index["model"],
            index["information_condition"],
            index["task"],
            index["meteorology_lag_days"],
        )
    )
    event_columns = [
        "role", "network_id", "station_id", "geometry", "geometry_id",
        "truth_start_date", "observed_missing_start_date", "gap_length",
        "placement", "start_index",
    ]
    required_grid = frozenset(PRIMARY_COMMON_GRID)
    candidates = index.loc[
        audit_status.eq("complete")
        & index["predictor_eligible"]
        & index["grid_cell"].isin(required_grid)
    ].copy()
    eligible_event_keys: list[tuple[Any, ...]] = []
    for key, piece in candidates.groupby(event_columns, sort=False, dropna=False):
        if frozenset(piece["grid_cell"]) == required_grid and len(piece) == len(required_grid):
            eligible_event_keys.append(key if isinstance(key, tuple) else (key,))
    event_index = pd.MultiIndex.from_tuples(eligible_event_keys, names=event_columns)
    candidate_index = pd.MultiIndex.from_frame(candidates[event_columns])
    lattice = candidates.loc[candidate_index.isin(event_index)].copy()
    if lattice.empty:
        raise PrimaryAggregationBlocked("no event supports the frozen common primary grid")

    geometries = sorted(lattice["geometry"].unique())
    gap_counts = lattice.groupby("geometry")["gap_length"].nunique().to_dict()
    placement_counts = (
        lattice.groupby(["geometry", "gap_length"])["placement"].nunique().to_dict()
    )
    lattice["model_information_lag_weight"] = 1.0 / len(required_grid)
    lattice["geometry_weight"] = 1.0 / len(geometries)
    lattice["gap_weight"] = lattice.apply(
        lambda row: 1.0 / int(gap_counts[row["geometry"]]), axis=1
    )
    lattice["placement_weight"] = lattice.apply(
        lambda row: 1.0 / int(placement_counts[(row["geometry"], row["gap_length"])]),
        axis=1,
    )
    lattice["analysis_weight"] = lattice[
        ["model_information_lag_weight", "geometry_weight", "gap_weight", "placement_weight"]
    ].prod(axis=1)
    lattice_columns = [
        "ordinal", *PRIMARY_IDENTITY_COLUMNS, "analysis_weight",
        "model_information_lag_weight", "geometry_weight", "gap_weight",
        "placement_weight",
    ]
    lattice = lattice.loc[:, lattice_columns].sort_values("ordinal", kind="stable")
    lattice_path = output / "analyzable_lattice.parquet"
    _create_once_table(lattice_path, lattice)

    attrition = index.loc[audit_status.eq("data_ineligible"), ["item_id", "role", "network_id", "reason"]].copy()
    attrition_path = output / "data_ineligible_attrition.parquet"
    _create_once_table(attrition_path, attrition)

    expanded = lattice.merge(sidecar, on=list(JOIN_KEYS), how="left", validate="many_to_one")
    expanded = expanded.rename(columns={"predicted_conditional_risk": "predicted_recoverability"})
    predictor_columns = [
        *OPERATOR_JOIN_KEYS,
        "predicted_recoverability",
        "gap_length_only",
        "acf_only",
        "donor_r2_only",
        "additive_d_over_4_heuristic",
    ]
    expanded = expanded.loc[:, predictor_columns]
    if expanded.isna().any(axis=None):
        raise PrimaryAggregationBlocked("expanded train-only predictors contain missing values")
    predictor_path = output / "operator_univariate_predictions.parquet"
    _create_once_table(predictor_path, expanded)
    predictor_manifest = {
        "manifest_schema": OPERATOR_PREDICTOR_SCHEMA,
        "join_keys": list(OPERATOR_JOIN_KEYS),
        "join_keys_sha256": _canonical_sha(OPERATOR_JOIN_KEYS),
        "prediction_column": "predicted_recoverability",
        "univariate_columns": ["gap_length_only", "acf_only", "donor_r2_only"],
        "additive_baseline_column": "additive_d_over_4_heuristic",
        "operator_univariate_columns_sha256": _canonical_sha(
            [
                "predicted_recoverability",
                "gap_length_only",
                "acf_only",
                "donor_r2_only",
                "additive_d_over_4_heuristic",
            ]
        ),
        "fit_role": "development",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "source_sidecar_manifest_sha256": _sha256_file(predictor_manifest_file),
        "source_sidecar_table_sha256": _sha256_file(sidecar_path),
        "predictions_path": predictor_path.name,
        "predictions_sha256": _sha256_file(predictor_path),
        "n_prediction_rows": len(expanded),
    }
    predictor_output_manifest = output / "operator_predictor_manifest.json"
    _create_once_json(predictor_output_manifest, predictor_manifest)

    manifest = {
        "manifest_schema": LATTICE_FREEZE_SCHEMA,
        "status": "frozen_before_v4_scoring",
        "workload_manifest_path": str(workload_path),
        "workload_manifest_sha256": _sha256_file(workload_path),
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "item_index": {"path": str(index_path), "sha256": _sha256_file(index_path), "n_rows": len(index)},
        "pre_score_eligibility_manifest_sha256": _sha256_file(eligibility_manifest_file),
        "pre_score_eligibility_table_sha256": _sha256_file(eligibility_path),
        "train_only_sidecar_manifest_sha256": _sha256_file(predictor_manifest_file),
        "train_only_sidecar_table_sha256": _sha256_file(sidecar_path),
        "common_grid": [list(value) for value in PRIMARY_COMMON_GRID],
        "common_grid_sha256": _canonical_sha(PRIMARY_COMMON_GRID),
        "weight_contract": {
            "model_information_lag": "equal_over_frozen_common_grid",
            "geometry": "equal_over_analyzable_geometries",
            "gap": "equal_within_geometry",
            "placement": "equal_within_geometry_gap",
            "product_column": "analysis_weight",
        },
        "analyzable_lattice": {"path": lattice_path.name, "format": "parquet", "sha256": _sha256_file(lattice_path), "n_rows": len(lattice)},
        "data_ineligible_attrition": {"path": attrition_path.name, "format": "parquet", "sha256": _sha256_file(attrition_path), "n_rows": len(attrition)},
        "operator_predictor_manifest": {"path": predictor_output_manifest.name, "sha256": _sha256_file(predictor_output_manifest)},
        "operator_predictor_table": {"path": predictor_path.name, "format": "parquet", "sha256": _sha256_file(predictor_path), "n_rows": len(expanded)},
        "n_analyzable_events": int(lattice[event_columns].drop_duplicates().shape[0]),
        "n_analyzable_items": len(lattice),
        "n_data_ineligible_items": len(attrition),
        "selection_uses_outcomes": False,
        "v4_results_read": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    _create_once_json(output / "lattice_freeze_manifest.json", manifest)
    return manifest


def bind_complete_v4_primary_results(
    *,
    workload_manifest_path: str | Path,
    aggregation_manifest_path: str | Path,
    item_results_path: str | Path,
    lattice_freeze_manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Bind complete result bytes to the already-frozen lattice without selection."""

    workload_path = Path(workload_manifest_path).resolve()
    aggregation_path = Path(aggregation_manifest_path).resolve()
    results_path = Path(item_results_path).resolve()
    freeze_path = Path(lattice_freeze_manifest_path).resolve()
    output = Path(output_dir).resolve()
    for path in (workload_path, aggregation_path, results_path, freeze_path, output):
        _assert_open(path)
    workload = _read_json(workload_path)
    aggregation = _read_json(aggregation_path)
    freeze = _read_json(freeze_path)
    if freeze.get("manifest_schema") != LATTICE_FREEZE_SCHEMA or freeze.get("status") != "frozen_before_v4_scoring":
        raise PrimaryAggregationBlocked("primary results lack a valid pre-score lattice freeze")
    if freeze.get("workload_manifest_sha256") != _sha256_file(workload_path):
        raise PrimaryAggregationBlocked("lattice freeze/workload binding mismatch")
    required_aggregation = {
        "manifest_schema": V4_AGGREGATION_SCHEMA,
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "all_executions_successful": True,
        "workload_manifest_sha256": _sha256_file(workload_path),
        "work_item_identity_sha256": workload.get("work_item_identity_sha256"),
        "sealed_temperature_records_read": False,
    }
    for key, expected in required_aggregation.items():
        if aggregation.get(key) != expected:
            raise PrimaryAggregationBlocked(f"complete aggregation mismatch for {key}")
    results = pd.read_parquet(results_path)
    n_items = int(workload.get("n_work_items", -1))
    if len(results) != n_items or _stream_sha(results) != workload.get("work_item_identity_sha256"):
        raise PrimaryAggregationBlocked("item results do not match the complete v4 stream")
    statuses = results["status"].astype(str)
    if not set(statuses).issubset(TERMINAL_RESULT_STATUSES):
        raise PrimaryAggregationBlocked("item results contain failed/nonterminal rows")
    if results["sealed_temperature_records_read"].map(bool).any():
        raise PrimaryAggregationBlocked("item results attest sealed access")
    lattice_record = freeze["analyzable_lattice"]
    lattice_path = _artifact_path(freeze_path, str(lattice_record["path"]))
    if _sha256_file(lattice_path) != lattice_record["sha256"]:
        raise PrimaryAggregationBlocked("frozen lattice bytes drifted after scoring")
    lattice = pd.read_parquet(lattice_path)
    lattice_ids = set(lattice["item_id"].astype(str))
    selected = results.loc[results["item_id"].astype(str).isin(lattice_ids)].copy()
    if len(selected) != len(lattice) or not selected["status"].eq("complete").all():
        raise PrimaryAggregationBlocked("a frozen analyzable item did not complete")
    primary = selected.rename(
        columns={"target_station": "station_id", "achieved_skill": "observed_achieved_skill"}
    )[[*PRIMARY_IDENTITY_COLUMNS, "observed_achieved_skill"]]
    primary["meteorology_lag_days"] = pd.to_numeric(
        primary["meteorology_lag_days"], errors="coerce"
    ).map(lambda value: "none" if pd.isna(value) else str(int(value)))
    observed = pd.to_numeric(primary["observed_achieved_skill"], errors="coerce")
    if not np.isfinite(observed).all():
        raise PrimaryAggregationBlocked("primary y contains a nonfinite achieved skill")
    primary_path = output / "primary_y.parquet"
    output.mkdir(parents=True, exist_ok=True)
    primary.to_parquet(primary_path, index=False)
    copied_results_path = output / "item_results.parquet"
    results.to_parquet(copied_results_path, index=False)

    def frozen_record(name: str) -> dict[str, Any]:
        record = freeze[name]
        return {**record, "path": str(_artifact_path(freeze_path, str(record["path"]))) }

    complete_excluded = results.loc[
        statuses.eq("complete") & ~results["item_id"].astype(str).isin(lattice_ids),
        ["item_id", "role", "network_id"],
    ].copy()
    complete_excluded["reason"] = "outside_outcome_blind_frozen_common_lattice"
    excluded_path = output / "complete_item_outcome_blind_attrition.parquet"
    complete_excluded.to_parquet(excluded_path, index=False)
    binding = {
        "manifest_schema": INPUT_BINDING_SCHEMA,
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "workload_manifest_sha256": _sha256_file(workload_path),
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "expected_item_records": n_items,
        "observed_item_records": len(results),
        "work_item_identity_sha256": workload["work_item_identity_sha256"],
        "status_counts": dict(sorted(Counter(statuses).items())),
        "primary_y_column": "observed_achieved_skill",
        "operator_column": "predicted_recoverability",
        "primary_table_complete_for_all_complete_items": True,
        "primary_complete_item_scope": "frozen_analyzable_lattice",
        "complete_item_outcome_blind_attrition_complete": True,
        "item_records_validated_against_frozen_v4_stream": True,
        "primary_table_derived_without_row_selection": True,
        "analyzable_lattice_frozen_before_result_scoring": True,
        "analyzable_lattice_selection_uses_outcomes": False,
        "common_grid_complete": True,
        "analysis_weight_column": "analysis_weight",
        "data_ineligible_attrition_complete": True,
        "operator_predictions_train_only": True,
        "item_results": {"path": copied_results_path.name, "format": "parquet", "sha256": _sha256_file(copied_results_path), "n_rows": len(results)},
        "primary_y_table": {"path": primary_path.name, "format": "parquet", "sha256": _sha256_file(primary_path), "n_rows": len(primary)},
        "analyzable_lattice": frozen_record("analyzable_lattice"),
        "data_ineligible_attrition": frozen_record("data_ineligible_attrition"),
        "operator_predictor_manifest": frozen_record("operator_predictor_manifest"),
        "operator_predictor_table": frozen_record("operator_predictor_table"),
        "complete_item_outcome_blind_attrition": {"path": excluded_path.name, "format": "parquet", "sha256": _sha256_file(excluded_path), "n_rows": len(complete_excluded)},
        "lattice_freeze_manifest_sha256": _sha256_file(freeze_path),
        "aggregation_manifest_sha256": _sha256_file(aggregation_path),
        "achieved_skill_used_for_selection": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    _atomic_json(output / "post_t2_input_binding.json", binding)
    return binding


__all__ = [
    "ELIGIBILITY_AUDIT_SCHEMA",
    "LATTICE_FREEZE_SCHEMA",
    "PRIMARY_COMMON_GRID",
    "PrimaryAggregationBlocked",
    "bind_complete_v4_primary_results",
    "freeze_v4_analyzable_lattice",
]
