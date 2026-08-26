"""Fail-closed T4/T5 analyses derived only from a complete T2 v4 result set.

The module never discovers temperature panels.  It consumes an identity-bound
item table and a primary-y table whose bytes are declared by a separate v4
aggregate binding.  Until those files exist and validate, it emits readiness
only.  In particular, the legacy T4 scores and legacy T5 ``delta_r`` values are
not inputs to this contract.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .t2_workload_v4 import V4_RUNNER_CONTRACT_VERSION, V4_WORKLOAD_SCHEMA

INPUT_BINDING_SCHEMA = "t2_v91_v4_post_t2_input_binding_v2"
OPERATOR_PREDICTOR_SCHEMA = "t2_v91_v4_train_only_operator_predictions_v1"
READINESS_SCHEMA = "t4_t5_v91_post_t2_readiness_v2"
T4_SCHEMA = "t4_v91_natural_geometry_observed_counterpart_v1"
T5_SCHEMA = "t5_v91_frozen_pair_primary_y_contrast_v1"
PAIR_MANIFEST_SCHEMA = "t5_v9_1_outcome_blind_matching_readiness_v1"
FROZEN_MATCHING_FACTORS = frozenset(
    {
        "donor_count",
        "donor_direction",
        "nearest_donor_distance",
        "drainage_area",
        "climate",
        "bfi",
    }
)
TERMINAL_STATUSES = frozenset(
    {
        "complete",
        "reference_complete",
        "structural_not_applicable",
        "data_ineligible",
    }
)
PRIMARY_COLUMNS = frozenset(
    {
        "item_id",
        "role",
        "network_id",
        "station_id",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "model",
        "information_condition",
        "task",
        "gap_length",
        "placement",
        "start_index",
        "meteorology_lag_days",
        "observed_achieved_skill",
    }
)
PRIMARY_IDENTITY_COLUMNS = (
    "item_id",
    "role",
    "network_id",
    "station_id",
    "geometry",
    "geometry_id",
    "truth_start_date",
    "observed_missing_start_date",
    "gap_length",
    "placement",
    "start_index",
    "model",
    "information_condition",
    "task",
    "meteorology_lag_days",
)
OPERATOR_JOIN_KEYS = PRIMARY_IDENTITY_COLUMNS
EVENT_IDENTITY_COLUMNS = (
    "role",
    "network_id",
    "station_id",
    "geometry",
    "geometry_id",
    "truth_start_date",
    "observed_missing_start_date",
    "gap_length",
    "placement",
    "start_index",
)
COMMON_GRID_COLUMNS = (
    "model",
    "information_condition",
    "task",
    "meteorology_lag_days",
)
PAIR_COLUMNS = frozenset(
    {
        "regulated_id",
        "control_id",
        "regulated_network_id",
        "control_network_id",
    }
)
FULL_PAIR_COLUMNS = frozenset(
    {
        *PAIR_COLUMNS,
        "role",
        "donor_count",
        "donor_count_abs_diff",
        "donor_direction",
        "donor_direction_match",
        "nearest_donor_distance_abs_diff",
        "log_drainage_area_abs_diff",
        "climate",
        "climate_match",
        "bfi_abs_diff",
        "standardized_l1_match_distance",
    }
)
FORBIDDEN_PAIR_OUTCOME_COLUMNS = frozenset(
    {
        "achieved_skill",
        "delta_r",
        "fill_mae",
        "observed_achieved_skill",
        "predicted_recoverability",
        "recoverability",
        "recoverability_r",
        "t2_primary_y",
    }
)


class PostT2ContractError(ValueError):
    """Raised when a present artifact claims a contract it does not satisfy."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PostT2ContractError(f"JSON artifact is not a mapping: {path}")
    return value


def _read_table(path: Path, format_name: str | None = None) -> pd.DataFrame:
    kind = format_name or path.suffix.lstrip(".").lower()
    if kind == "parquet":
        return pd.read_parquet(path)
    if kind == "csv":
        return pd.read_csv(path, dtype={"station_id": str, "target_station": str})
    raise PostT2ContractError(f"unsupported table format: {kind}")


def _assert_open_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise PostT2ContractError(f"refusing sealed-path input: {path}")


def _stream_sha(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for item_id in frame.sort_values("ordinal", kind="mergesort")["item_id"]:
        digest.update(str(item_id).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _artifact_path(binding_path: Path, record: Mapping[str, Any]) -> Path:
    raw = Path(str(record.get("path", "")))
    return raw.resolve() if raw.is_absolute() else (binding_path.parent / raw).resolve()


def _validate_artifact(
    binding_path: Path, record: Mapping[str, Any], *, name: str
) -> tuple[Path, pd.DataFrame]:
    path = _artifact_path(binding_path, record)
    _assert_open_path(path)
    if not path.is_file():
        raise PostT2ContractError(f"bound {name} is absent: {path}")
    if _sha256_file(path) != record.get("sha256"):
        raise PostT2ContractError(f"bound {name} SHA-256 mismatch")
    frame = _read_table(path, str(record.get("format", "")))
    if len(frame) != int(record.get("n_rows", -1)):
        raise PostT2ContractError(f"bound {name} row count mismatch")
    return path, frame


def _validate_file_record(
    binding_path: Path, record: Mapping[str, Any], *, name: str
) -> Path:
    path = _artifact_path(binding_path, record)
    _assert_open_path(path)
    if not path.is_file():
        raise PostT2ContractError(f"bound {name} is absent: {path}")
    if _sha256_file(path) != record.get("sha256"):
        raise PostT2ContractError(f"bound {name} SHA-256 mismatch")
    return path


def _normalized_identity(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    result = frame.loc[:, list(columns)].copy()
    for column in columns:
        if column in {"gap_length", "start_index"}:
            numeric = pd.to_numeric(result[column], errors="coerce")
            result[column] = numeric.map(
                lambda value: "" if pd.isna(value) else str(int(value))
            )
        elif column == "meteorology_lag_days":
            numeric = pd.to_numeric(result[column], errors="coerce")
            result[column] = numeric.map(
                lambda value: "none" if pd.isna(value) else str(int(value))
            )
        else:
            result[column] = result[column].fillna("").astype(str)
    return result


def _assert_same_identities(
    left: pd.DataFrame,
    right: pd.DataFrame,
    columns: tuple[str, ...],
    *,
    message: str,
) -> None:
    left_ids = (
        _normalized_identity(left, columns)
        .sort_values(list(columns))
        .reset_index(drop=True)
    )
    right_ids = (
        _normalized_identity(right, columns)
        .sort_values(list(columns))
        .reset_index(drop=True)
    )
    if len(left_ids) != len(right_ids) or not left_ids.equals(right_ids):
        raise PostT2ContractError(message)


def _assert_common_grid_complete(lattice: pd.DataFrame) -> None:
    normalized = _normalized_identity(
        lattice, EVENT_IDENTITY_COLUMNS + COMMON_GRID_COLUMNS
    )
    expected: frozenset[tuple[str, ...]] | None = None
    expected_cell_weights: dict[tuple[str, ...], float] | None = None
    for _, piece in normalized.groupby(
        list(EVENT_IDENTITY_COLUMNS), sort=False, dropna=False
    ):
        cells = frozenset(
            tuple(str(row[column]) for column in COMMON_GRID_COLUMNS)
            for _, row in piece.iterrows()
        )
        if len(cells) != len(piece):
            raise PostT2ContractError(
                "analyzable lattice duplicates a common-grid cell"
            )
        if expected is None:
            expected = cells
        elif cells != expected:
            raise PostT2ContractError(
                "analyzable lattice is not complete on a common model-information grid"
            )
        if "analysis_weight" in lattice.columns:
            raw_weights = pd.to_numeric(
                lattice.loc[piece.index, "analysis_weight"], errors="coerce"
            )
            normalized_weights = raw_weights / raw_weights.sum()
            cell_weights = {
                tuple(str(row[column]) for column in COMMON_GRID_COLUMNS): float(weight)
                for (_, row), weight in zip(piece.iterrows(), normalized_weights)
            }
            if expected_cell_weights is None:
                expected_cell_weights = cell_weights
            elif any(
                not np.isclose(
                    cell_weights[cell],
                    expected_cell_weights[cell],
                    rtol=0.0,
                    atol=1e-12,
                )
                for cell in cells
            ):
                raise PostT2ContractError(
                    "analyzable lattice changes model-information aggregation weights by event"
                )
    if not expected:
        raise PostT2ContractError("analyzable lattice has no common-grid cells")


def validate_v4_primary_inputs(
    workload_path: str | Path,
    binding_path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validate complete v4 item and primary-y tables, including byte identity."""

    workload_file = Path(workload_path).resolve()
    binding_file = Path(binding_path).resolve()
    _assert_open_path(workload_file)
    _assert_open_path(binding_file)
    workload = _read_json(workload_file)
    binding = _read_json(binding_file)
    if workload.get("manifest_schema") != V4_WORKLOAD_SCHEMA:
        raise PostT2ContractError("post-T2 input is not a formal v4 workload")
    if workload.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION:
        raise PostT2ContractError("v4 runner contract mismatch")
    if (
        workload.get("sealed_paths_traversed") is not False
        or workload.get("sealed_temperature_records_read") is not False
    ):
        raise PostT2ContractError("v4 workload lacks an open-only attestation")
    if binding.get("manifest_schema") != INPUT_BINDING_SCHEMA:
        raise PostT2ContractError("unsupported post-T2 input binding")
    required_binding = {
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "workload_manifest_sha256": _sha256_file(workload_file),
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "expected_item_records": int(workload.get("n_work_items", -1)),
        "observed_item_records": int(workload.get("n_work_items", -1)),
        "work_item_identity_sha256": workload.get("work_item_identity_sha256"),
        "primary_y_column": "observed_achieved_skill",
        "operator_column": "predicted_recoverability",
        "primary_table_complete_for_all_complete_items": True,
        "item_records_validated_against_frozen_v4_stream": True,
        "primary_table_derived_without_row_selection": True,
        "analyzable_lattice_frozen_before_result_scoring": True,
        "analyzable_lattice_selection_uses_outcomes": False,
        "common_grid_complete": True,
        "analysis_weight_column": "analysis_weight",
        "data_ineligible_attrition_complete": True,
        "operator_predictions_train_only": True,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    for key, expected in required_binding.items():
        if binding.get(key) != expected:
            raise PostT2ContractError(f"post-T2 binding mismatch for {key}")
    item_record = binding.get("item_results")
    primary_record = binding.get("primary_y_table")
    lattice_record = binding.get("analyzable_lattice")
    attrition_record = binding.get("data_ineligible_attrition")
    predictor_manifest_record = binding.get("operator_predictor_manifest")
    predictor_table_record = binding.get("operator_predictor_table")
    records = (
        item_record,
        primary_record,
        lattice_record,
        attrition_record,
        predictor_manifest_record,
        predictor_table_record,
    )
    if not all(isinstance(record, Mapping) for record in records):
        raise PostT2ContractError(
            "post-T2 binding omits item, primary, lattice, attrition, or predictor artifacts"
        )
    assert isinstance(item_record, Mapping)
    assert isinstance(primary_record, Mapping)
    assert isinstance(lattice_record, Mapping)
    assert isinstance(attrition_record, Mapping)
    assert isinstance(predictor_manifest_record, Mapping)
    assert isinstance(predictor_table_record, Mapping)
    _, items = _validate_artifact(binding_file, item_record, name="item results")
    _, primary = _validate_artifact(
        binding_file, primary_record, name="primary-y table"
    )
    _, lattice = _validate_artifact(
        binding_file, lattice_record, name="frozen analyzable lattice"
    )
    _, attrition = _validate_artifact(
        binding_file, attrition_record, name="data-ineligible attrition"
    )
    predictor_manifest_path = _validate_file_record(
        binding_file,
        predictor_manifest_record,
        name="train-only operator predictor manifest",
    )
    predictor_table_path, predictors = _validate_artifact(
        binding_file,
        predictor_table_record,
        name="train-only operator predictor table",
    )
    predictor_manifest = _read_json(predictor_manifest_path)
    required_predictor_manifest = {
        "manifest_schema": OPERATOR_PREDICTOR_SCHEMA,
        "join_keys": list(OPERATOR_JOIN_KEYS),
        "prediction_column": "predicted_recoverability",
        "fit_role": "development",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "predictions_sha256": predictor_table_record.get("sha256"),
        "n_prediction_rows": int(predictor_table_record.get("n_rows", -1)),
    }
    for key, expected in required_predictor_manifest.items():
        if predictor_manifest.get(key) != expected:
            raise PostT2ContractError(f"operator predictor manifest mismatch for {key}")
    declared_prediction_path = _artifact_path(
        predictor_manifest_path,
        {"path": predictor_manifest.get("predictions_path", "")},
    )
    if declared_prediction_path != predictor_table_path:
        raise PostT2ContractError(
            "operator predictor manifest points to a different table"
        )

    required_items = {
        "ordinal",
        "item_id",
        "role",
        "network_id",
        "target_station",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "model",
        "information_condition",
        "task",
        "gap_length",
        "placement",
        "start_index",
        "meteorology_lag_days",
        "status",
        "achieved_skill",
        "sealed_temperature_records_read",
    }
    missing = sorted(required_items.difference(items.columns))
    if missing:
        raise PostT2ContractError(f"item results omit columns: {missing}")
    expected_n = int(workload["n_work_items"])
    ordinals = pd.to_numeric(items["ordinal"], errors="coerce")
    if (
        len(items) != expected_n
        or ordinals.isna().any()
        or sorted(ordinals.astype(int).tolist()) != list(range(expected_n))
        or items["item_id"].astype(str).duplicated().any()
    ):
        raise PostT2ContractError(
            "item results are not a complete unique ordinal stream"
        )
    item_stream_sha = _stream_sha(items.assign(ordinal=ordinals.astype(int)))
    if item_stream_sha != workload.get(
        "work_item_identity_sha256"
    ) or item_stream_sha != binding.get("work_item_identity_sha256"):
        raise PostT2ContractError("item result identity stream SHA-256 mismatch")
    statuses = items["status"].astype(str)
    unknown = sorted(set(statuses).difference(TERMINAL_STATUSES))
    if unknown:
        raise PostT2ContractError(f"item results contain non-success status: {unknown}")
    if items["sealed_temperature_records_read"].map(bool).any():
        raise PostT2ContractError("item results attest sealed temperature access")
    declared_counts = {
        str(k): int(v) for k, v in (binding.get("status_counts") or {}).items()
    }
    if declared_counts != dict(sorted(Counter(statuses).items())):
        raise PostT2ContractError("item status counts do not match binding")

    missing = sorted(PRIMARY_COLUMNS.difference(primary.columns))
    if missing:
        raise PostT2ContractError(f"primary-y table omits columns: {missing}")
    if "predicted_recoverability" in primary.columns:
        raise PostT2ContractError(
            "primary-y table must not supply predicted_recoverability; use bound train-only predictors"
        )
    if primary["item_id"].astype(str).duplicated().any():
        raise PostT2ContractError("primary-y item IDs are not unique")
    complete = items.loc[statuses.eq("complete")].copy()
    if len(primary) != len(complete) or set(primary["item_id"].astype(str)) != set(
        complete["item_id"].astype(str)
    ):
        raise PostT2ContractError(
            "primary-y table is not complete for successful items"
        )
    item_check = complete.rename(
        columns={
            "target_station": "station_id",
            "achieved_skill": "item_achieved_skill",
        }
    )[[*PRIMARY_IDENTITY_COLUMNS, "item_achieved_skill"]]
    _assert_same_identities(
        primary,
        item_check,
        PRIMARY_IDENTITY_COLUMNS,
        message="primary-y identities differ from item results",
    )
    joined = primary.merge(
        item_check,
        on="item_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_item"),
    )
    observed = pd.to_numeric(joined["observed_achieved_skill"], errors="coerce")
    item_y = pd.to_numeric(joined["item_achieved_skill"], errors="coerce")
    if not np.isfinite(observed).all() or not np.allclose(
        observed, item_y, rtol=0.0, atol=1e-12
    ):
        raise PostT2ContractError(
            "primary y is nonfinite or differs from item achieved_skill"
        )

    lattice_required = {*PRIMARY_IDENTITY_COLUMNS, "analysis_weight"}
    missing = sorted(lattice_required.difference(lattice.columns))
    if missing:
        raise PostT2ContractError(f"analyzable lattice omits columns: {missing}")
    if lattice["item_id"].astype(str).duplicated().any():
        raise PostT2ContractError("analyzable lattice item IDs are not unique")
    weight = pd.to_numeric(lattice["analysis_weight"], errors="coerce")
    if not np.isfinite(weight).all() or (weight <= 0).any():
        raise PostT2ContractError(
            "analyzable lattice weights must be finite and positive"
        )
    lattice = lattice.assign(analysis_weight=weight.astype(float))
    _assert_same_identities(
        primary,
        lattice,
        PRIMARY_IDENTITY_COLUMNS,
        message="primary-y table differs from the frozen analyzable lattice",
    )
    _assert_common_grid_complete(lattice)

    attrition_required = {"item_id", "role", "network_id", "reason"}
    missing = sorted(attrition_required.difference(attrition.columns))
    if missing:
        raise PostT2ContractError(f"data-ineligible attrition omits columns: {missing}")
    if attrition["item_id"].astype(str).duplicated().any():
        raise PostT2ContractError("data-ineligible attrition item IDs are not unique")
    data_ineligible = items.loc[statuses.eq("data_ineligible")]
    if set(attrition["item_id"].astype(str)) != set(
        data_ineligible["item_id"].astype(str)
    ):
        raise PostT2ContractError("data-ineligible attrition is not complete")
    if attrition["reason"].fillna("").astype(str).str.strip().eq("").any():
        raise PostT2ContractError("data-ineligible attrition contains a blank reason")
    if not attrition.empty:
        attrition_identity = attrition[["item_id", "role", "network_id"]].copy()
        expected_attrition_identity = data_ineligible[
            ["item_id", "role", "network_id"]
        ].copy()
        _assert_same_identities(
            attrition_identity,
            expected_attrition_identity,
            ("item_id", "role", "network_id"),
            message="data-ineligible attrition identities differ from item results",
        )

    predictor_required = {*OPERATOR_JOIN_KEYS, "predicted_recoverability"}
    missing = sorted(predictor_required.difference(predictors.columns))
    if missing:
        raise PostT2ContractError(f"operator predictor table omits columns: {missing}")
    normalized_predictor_keys = _normalized_identity(predictors, OPERATOR_JOIN_KEYS)
    if normalized_predictor_keys.duplicated().any():
        raise PostT2ContractError("operator predictor join keys are not unique")
    _assert_same_identities(
        lattice,
        predictors,
        OPERATOR_JOIN_KEYS,
        message="operator predictor table differs from the frozen analyzable lattice",
    )
    operator = pd.to_numeric(predictors["predicted_recoverability"], errors="coerce")
    if not np.isfinite(operator).all():
        raise PostT2ContractError(
            "operator predictor table contains nonfinite predictions"
        )
    predictors = predictors.assign(predicted_recoverability=operator.astype(float))
    primary = primary.merge(
        lattice[[*PRIMARY_IDENTITY_COLUMNS, "analysis_weight"]],
        on=list(PRIMARY_IDENTITY_COLUMNS),
        how="left",
        validate="one_to_one",
    ).merge(
        predictors[[*OPERATOR_JOIN_KEYS, "predicted_recoverability"]],
        on=list(OPERATOR_JOIN_KEYS),
        how="left",
        validate="one_to_one",
    )
    if primary[["analysis_weight", "predicted_recoverability"]].isna().any(axis=None):
        raise PostT2ContractError("post-T2 lattice/predictor join has missing rows")
    return items, primary, binding


def _validate_frozen_inputs(
    geometry_catalog_path: Path,
    geometry_manifest_path: Path,
    pair_plan_path: Path,
    pair_manifest_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    for path in (
        geometry_catalog_path,
        geometry_manifest_path,
        pair_plan_path,
        pair_manifest_path,
    ):
        _assert_open_path(path)
        if not path.is_file():
            raise PostT2ContractError(f"frozen prerequisite absent: {path}")
    geometry_manifest = _read_json(geometry_manifest_path)
    if (
        geometry_manifest.get("manifest_schema")
        != "t2_v91_frozen_outage_geometry_binding_v1"
    ):
        raise PostT2ContractError("natural geometry manifest schema mismatch")
    natural_record = geometry_manifest.get("natural_outage") or {}
    if _sha256_file(geometry_catalog_path) != natural_record.get("file_sha256"):
        raise PostT2ContractError("natural geometry catalog SHA-256 mismatch")
    natural = pd.read_csv(
        geometry_catalog_path,
        dtype={"network_id": str, "station_id": str, "geometry_id": str},
    )
    if len(natural) != int(natural_record.get("n_geometry_rows", -1)):
        raise PostT2ContractError("natural geometry catalog row count mismatch")
    if (
        not natural["benchmark_eligible"].map(str).str.lower().eq("true").all()
        or natural["actual_missing_truth_available"]
        .map(str)
        .str.lower()
        .eq("true")
        .any()
        or not natural["benchmark_truth_source"]
        .eq("held_out_observed_counterpart")
        .all()
    ):
        raise PostT2ContractError("natural geometry violates planted-counterpart truth")
    pair_manifest = _read_json(pair_manifest_path)
    required_pair_manifest = {
        "schema_version": PAIR_MANIFEST_SCHEMA,
        "status": "pair_plan_ready_waiting_for_t2_primary_y",
        "purpose": "matching_contract_and_attrition_not_t5_evidence",
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "passed": False,
        "sealed_outcomes_opened": False,
        "t2_outcome_columns_read": False,
        "t2_primary_y_bound": False,
        "old_two_pair_result_reused": False,
        "matching_unit": "target_station",
        "exposure": "upstream_major_dam_2009",
        "exposure_derivation": "full_gages_ii_MAJ_NDAMS_2009_ge_1",
        "factor_contract_matches_freeze": True,
        "pair_plan_ready": True,
        "formal_run_allowed": False,
        "calipers": None,
        "n_pair_plan_rows": 3,
    }
    for key, expected in required_pair_manifest.items():
        if pair_manifest.get(key) != expected:
            raise PostT2ContractError(f"T5 pair manifest mismatch for {key}")
    if (
        set(pair_manifest.get("frozen_matching_factors") or [])
        != FROZEN_MATCHING_FACTORS
    ):
        raise PostT2ContractError("T5 pair manifest differs from the six-factor freeze")
    allowed_roles = {str(value) for value in (pair_manifest.get("roles_allowed") or [])}
    if allowed_roles != {"development", "validation"}:
        raise PostT2ContractError("T5 pair manifest role contract mismatch")
    artifact = (pair_manifest.get("artifacts") or {}).get("pair_plan") or {}
    if _artifact_path(pair_manifest_path, artifact) != pair_plan_path or _sha256_file(
        pair_plan_path
    ) != artifact.get("sha256"):
        raise PostT2ContractError("T5 pair-plan SHA-256 mismatch")
    pairs = pd.read_csv(
        pair_plan_path,
        dtype={
            "regulated_id": str,
            "control_id": str,
            "regulated_network_id": str,
            "control_network_id": str,
        },
    )
    missing = sorted(FULL_PAIR_COLUMNS.difference(pairs.columns))
    if missing:
        raise PostT2ContractError(f"T5 pair plan omits columns: {missing}")
    forbidden = sorted(FORBIDDEN_PAIR_OUTCOME_COLUMNS & set(pairs.columns))
    if forbidden:
        raise PostT2ContractError(f"T5 pair plan is not outcome-blind: {forbidden}")
    regulated_keys = pairs[["regulated_network_id", "regulated_id"]].astype(str)
    control_keys = pairs[["control_network_id", "control_id"]].astype(str)
    if (
        len(pairs) != int(pair_manifest.get("n_pair_plan_rows", -1))
        or regulated_keys.duplicated().any()
        or control_keys.duplicated().any()
    ):
        raise PostT2ContractError(
            "T5 pair-plan cardinality/one-to-one contract mismatch"
        )
    if not pairs["role"].astype(str).isin(allowed_roles).all():
        raise PostT2ContractError("T5 pair-plan contains a forbidden role")
    bool_contract = pairs["donor_direction_match"].map(str).str.lower().eq(
        "true"
    ) & pairs["climate_match"].map(str).str.lower().eq("true")
    donor_diff = pd.to_numeric(pairs["donor_count_abs_diff"], errors="coerce")
    numeric_balance_columns = (
        "nearest_donor_distance_abs_diff",
        "log_drainage_area_abs_diff",
        "bfi_abs_diff",
        "standardized_l1_match_distance",
    )
    balance = pairs.loc[:, list(numeric_balance_columns)].apply(
        pd.to_numeric, errors="coerce"
    )
    if (
        not bool_contract.all()
        or not donor_diff.eq(0).all()
        or not np.isfinite(balance.to_numpy(dtype=float)).all()
        or (balance < 0).any(axis=None)
    ):
        raise PostT2ContractError(
            "T5 pair-plan matching fields violate their declarations"
        )

    covariate_artifact = (pair_manifest.get("artifacts") or {}).get(
        "station_covariates"
    ) or {}
    covariate_path = _artifact_path(pair_manifest_path, covariate_artifact)
    if not covariate_path.is_file() or _sha256_file(
        covariate_path
    ) != covariate_artifact.get("sha256"):
        raise PostT2ContractError("T5 station-covariate SHA-256 mismatch")
    covariates = pd.read_csv(
        covariate_path, dtype={"network_id": str, "station_id": str}
    )
    covariate_required = {
        "network_id",
        "station_id",
        "role",
        "regulated",
        "donor_count",
        "donor_direction",
        "climate",
        "nearest_donor_distance_km",
        "drainage_area_sqkm",
        "bfi",
        "eligible_for_matching",
    }
    missing = sorted(covariate_required.difference(covariates.columns))
    if missing:
        raise PostT2ContractError(f"T5 station covariates omit columns: {missing}")
    if covariates[["network_id", "station_id"]].astype(str).duplicated().any():
        raise PostT2ContractError("T5 station covariates duplicate a station identity")
    forbidden = sorted(FORBIDDEN_PAIR_OUTCOME_COLUMNS & set(covariates.columns))
    if forbidden:
        raise PostT2ContractError(
            f"T5 station covariates are not outcome-blind: {forbidden}"
        )
    eligible_covariates = covariates.loc[
        covariates["eligible_for_matching"].map(str).str.lower().eq("true")
    ].copy()

    def scale(column: pd.Series) -> float:
        values = pd.to_numeric(column, errors="coerce")
        finite = values[np.isfinite(values)]
        if len(finite) < 2:
            return 1.0
        value = float(finite.quantile(0.75) - finite.quantile(0.25))
        return value if value > 0 else 1.0

    log_area = np.log(
        pd.to_numeric(eligible_covariates["drainage_area_sqkm"], errors="coerce")
    )
    scales = {
        "nearest": scale(eligible_covariates["nearest_donor_distance_km"]),
        "drainage": scale(log_area),
        "bfi": scale(eligible_covariates["bfi"]),
    }
    lookup = {
        (str(row.network_id), str(row.station_id)): row
        for row in covariates.itertuples(index=False)
    }
    for row in pairs.itertuples(index=False):
        regulated_key = (str(row.regulated_network_id), str(row.regulated_id))
        control_key = (str(row.control_network_id), str(row.control_id))
        regulated = lookup.get(regulated_key)
        control = lookup.get(control_key)
        if regulated is None or control is None:
            raise PostT2ContractError("T5 pair station is absent from bound covariates")
        if (
            regulated_key[0] == control_key[0]
            or str(regulated.regulated).lower() != "true"
            or str(control.regulated).lower() != "false"
            or str(regulated.eligible_for_matching).lower() != "true"
            or str(control.eligible_for_matching).lower() != "true"
            or str(regulated.role) != str(row.role)
            or str(control.role) != str(row.role)
            or int(regulated.donor_count) != int(row.donor_count)
            or int(control.donor_count) != int(row.donor_count)
            or str(regulated.donor_direction) != str(row.donor_direction)
            or str(control.donor_direction) != str(row.donor_direction)
            or str(regulated.climate) != str(row.climate)
            or str(control.climate) != str(row.climate)
        ):
            raise PostT2ContractError(
                "T5 pair exposure, role, or exact-match factors drifted"
            )
        nearest_diff = abs(
            float(regulated.nearest_donor_distance_km)
            - float(control.nearest_donor_distance_km)
        )
        drainage_diff = abs(
            float(np.log(float(regulated.drainage_area_sqkm)))
            - float(np.log(float(control.drainage_area_sqkm)))
        )
        bfi_diff = abs(float(regulated.bfi) - float(control.bfi))
        standardized = (
            nearest_diff / scales["nearest"]
            + drainage_diff / scales["drainage"]
            + bfi_diff / scales["bfi"]
        )
        declared = (
            float(row.nearest_donor_distance_abs_diff),
            float(row.log_drainage_area_abs_diff),
            float(row.bfi_abs_diff),
            float(row.standardized_l1_match_distance),
        )
        computed = (nearest_diff, drainage_diff, bfi_diff, standardized)
        if not np.allclose(declared, computed, rtol=0.0, atol=1e-10):
            raise PostT2ContractError("T5 pair continuous-factor diagnostics drifted")

    network_pairs = pairs[["regulated_network_id", "control_network_id"]].astype(str)
    n_unique_network_pairs = len(network_pairs.drop_duplicates())
    if len(pairs) != 3 or n_unique_network_pairs != 2:
        raise PostT2ContractError(
            "current T5 plan must remain three station pairs in two network pairs"
        )
    balance_diagnostics = {
        "n_station_pairs": len(pairs),
        "n_unique_network_pairs": n_unique_network_pairs,
        "max_nearest_donor_distance_abs_diff_km": float(
            balance["nearest_donor_distance_abs_diff"].max()
        ),
        "max_log_drainage_area_abs_diff": float(
            balance["log_drainage_area_abs_diff"].max()
        ),
        "max_drainage_area_ratio": float(
            np.exp(balance["log_drainage_area_abs_diff"].max())
        ),
        "max_bfi_abs_diff": float(balance["bfi_abs_diff"].max()),
        "max_standardized_l1_match_distance": float(
            balance["standardized_l1_match_distance"].max()
        ),
        "caliper_invented_or_applied": False,
        "balance_supports_formal_confound_control": False,
    }
    identities = {
        "natural_geometry": {
            "path": str(geometry_catalog_path),
            "sha256": _sha256_file(geometry_catalog_path),
            "n_rows": len(natural),
        },
        "t5_pair_plan": {
            "path": str(pair_plan_path),
            "sha256": _sha256_file(pair_plan_path),
            "n_rows": len(pairs),
            "balance_diagnostics": balance_diagnostics,
        },
        "t5_station_covariates": {
            "path": str(covariate_path),
            "sha256": _sha256_file(covariate_path),
            "n_rows": len(covariates),
        },
    }
    return natural, pairs, identities


def _network_summary(rows: pd.DataFrame, *, geometry: str) -> pd.DataFrame:
    data = rows.loc[rows["geometry"].eq(geometry)].copy()
    if data.empty:
        return pd.DataFrame(
            columns=[
                "geometry",
                "network_id",
                "n_primary_items",
                "predicted_recoverability",
                "observed_achieved_skill",
            ]
        )
    data["analysis_weight"] = pd.to_numeric(
        data.get("analysis_weight", 1.0), errors="coerce"
    ).fillna(0.0)
    records = []
    for network_id, piece in data.groupby("network_id", sort=True):
        weight = piece["analysis_weight"].to_numpy(dtype=float)
        if weight.sum() <= 0:
            continue
        records.append(
            {
                "geometry": geometry,
                "network_id": str(network_id),
                "n_primary_items": len(piece),
                "predicted_recoverability": float(
                    np.average(piece["predicted_recoverability"], weights=weight)
                ),
                "observed_achieved_skill": float(
                    np.average(piece["observed_achieved_skill"], weights=weight)
                ),
            }
        )
    return pd.DataFrame(records)


def analyze_t4(
    primary: pd.DataFrame, natural: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Describe observed counterparts selected by natural-missing geometry."""

    natural_rows = primary.loc[primary["geometry"].eq("natural_outage")].merge(
        natural[
            [
                "geometry_id",
                "network_id",
                "station_id",
                "benchmark_start_date",
                "start_date",
                "benchmark_truth_source",
                "benchmark_weight",
            ]
        ],
        on=["geometry_id", "network_id", "station_id"],
        how="left",
        validate="many_to_one",
    )
    if natural_rows["benchmark_truth_source"].isna().any():
        raise PostT2ContractError("natural result row is absent from frozen geometry")
    if (
        not natural_rows["benchmark_truth_source"]
        .eq("held_out_observed_counterpart")
        .all()
    ):
        raise PostT2ContractError(
            "natural result does not use planted counterpart truth"
        )
    if (
        not natural_rows["truth_start_date"]
        .astype(str)
        .eq(natural_rows["benchmark_start_date"].astype(str))
        .all()
        or not natural_rows["observed_missing_start_date"]
        .astype(str)
        .eq(natural_rows["start_date"].astype(str))
        .all()
    ):
        raise PostT2ContractError(
            "natural result dates differ from frozen planted counterpart"
        )
    natural_rows["analysis_weight"] = pd.to_numeric(
        natural_rows.get("analysis_weight", 1.0), errors="coerce"
    ) * pd.to_numeric(natural_rows["benchmark_weight"], errors="coerce")
    artificial_rows = primary.loc[primary["geometry"].eq("artificial_stress")].copy()
    artificial_rows["analysis_weight"] = pd.to_numeric(
        artificial_rows.get("analysis_weight", 1.0), errors="coerce"
    )
    summaries = [
        _network_summary(artificial_rows, geometry="artificial_stress"),
        _network_summary(natural_rows, geometry="natural_outage"),
    ]
    nonempty = [summary for summary in summaries if not summary.empty]
    networks = (
        pd.concat(nonempty, ignore_index=True)
        if nonempty
        else pd.DataFrame(columns=summaries[0].columns)
    )
    correlations: dict[str, float | None] = {}
    counts: dict[str, int] = {}
    for geometry, piece in networks.groupby("geometry", sort=True):
        counts[str(geometry)] = len(piece)
        value = piece["predicted_recoverability"].corr(
            piece["observed_achieved_skill"], method="spearman"
        )
        correlations[str(geometry)] = float(value) if np.isfinite(value) else None
    n_natural = counts.get("natural_outage", 0)
    return networks, {
        "manifest_schema": T4_SCHEMA,
        "status": (
            "withheld_n_lt_100_network_interval"
            if n_natural < 100
            else "ready_for_hierarchical_confirmation_not_evaluated"
        ),
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "analysis_name": "natural_geometry_observed_counterpart",
        "truth_source": "held_out_observed_counterpart",
        "actual_missing_days_scored": False,
        "actual_missing_performance_estimand": False,
        "aggregation_unit": "network",
        "same_network_outer_unit_for_artificial_and_natural": True,
        "same_internal_weighting_for_artificial_and_natural": False,
        "natural_and_artificial_directly_comparable": False,
        "n_networks_by_geometry": counts,
        "network_spearman_by_geometry": correlations,
        "network_interval": None,
        "network_interval_reported": False,
        "forbidden_claims": [
            "actual_missing_day_recovery_performance",
            "natural_and_artificial_effect_equivalence",
            "t4_passed",
            "formal_confirmation",
        ],
    }


def analyze_t5(
    primary: pd.DataFrame, pairs: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Join the frozen station pairs to artificial T2 primary y only."""

    artificial = primary.loc[primary["geometry"].eq("artificial_stress")].copy()
    artificial["analysis_weight"] = pd.to_numeric(
        artificial.get("analysis_weight", 1.0), errors="coerce"
    )
    station_records = []
    for (network_id, station_id), piece in artificial.groupby(
        ["network_id", "station_id"], sort=True
    ):
        weights = piece["analysis_weight"].to_numpy(dtype=float)
        if not np.isfinite(weights).all() or weights.sum() <= 0:
            continue
        station_records.append(
            {
                "network_id": str(network_id),
                "station_id": str(station_id),
                "t2_primary_y": float(
                    np.average(piece["observed_achieved_skill"], weights=weights)
                ),
            }
        )
    station_y = pd.DataFrame(
        station_records, columns=["network_id", "station_id", "t2_primary_y"]
    )
    rows = []
    attrition = []
    lookup = {
        (str(row.network_id), str(row.station_id)): float(row.t2_primary_y)
        for row in station_y.itertuples(index=False)
    }
    for row in pairs.itertuples(index=False):
        regulated_key = (str(row.regulated_network_id), str(row.regulated_id))
        control_key = (str(row.control_network_id), str(row.control_id))
        missing = []
        if regulated_key not in lookup:
            missing.append("regulated_t2_primary_y_missing")
        if control_key not in lookup:
            missing.append("control_t2_primary_y_missing")
        pair_id = (
            f"{regulated_key[0]}:{regulated_key[1]}|{control_key[0]}:{control_key[1]}"
        )
        if missing:
            attrition.extend(
                {"pair_id": pair_id, "reason": reason} for reason in missing
            )
            continue
        regulated_y = lookup[regulated_key]
        control_y = lookup[control_key]
        rows.append(
            {
                "pair_id": pair_id,
                "regulated_network_id": regulated_key[0],
                "regulated_id": regulated_key[1],
                "control_network_id": control_key[0],
                "control_id": control_key[1],
                "regulated_t2_primary_y": regulated_y,
                "control_t2_primary_y": control_y,
                "delta_t2_primary_y_regulated_minus_control": regulated_y - control_y,
            }
        )
    contrasts = pd.DataFrame(rows)
    attrition_frame = pd.DataFrame(attrition, columns=["pair_id", "reason"])
    network_pairs = pairs[["regulated_network_id", "control_network_id"]].astype(str)
    n_unique_network_pairs = len(network_pairs.drop_duplicates())
    numeric_balance = {}
    for column in (
        "nearest_donor_distance_abs_diff",
        "log_drainage_area_abs_diff",
        "bfi_abs_diff",
        "standardized_l1_match_distance",
    ):
        if column in pairs:
            values = pd.to_numeric(pairs[column], errors="coerce")
            numeric_balance[f"max_{column}"] = (
                float(values.max()) if np.isfinite(values).any() else None
            )
    if "log_drainage_area_abs_diff" in pairs:
        values = pd.to_numeric(pairs["log_drainage_area_abs_diff"], errors="coerce")
        numeric_balance["max_drainage_area_ratio"] = (
            float(np.exp(values.max())) if np.isfinite(values).any() else None
        )
    return (
        contrasts,
        attrition_frame,
        {
            "manifest_schema": T5_SCHEMA,
            "status": "descriptive_infeasible_confound_control",
            "passed": False,
            "formal_evidence": False,
            "headline_claim_licensed": False,
            "formal_run_allowed": False,
            "outcome_source": "T2_v4_primary_observed_achieved_skill",
            "geometry": "artificial_stress",
            "old_delta_r_read_or_reused": False,
            "n_pairs_frozen": len(pairs),
            "n_station_pairs": len(pairs),
            "n_unique_network_pairs": n_unique_network_pairs,
            "independent_unit": "regulated_control_network_pair",
            "n_pairs_with_primary_y": len(contrasts),
            "n_pairs_attrited": int(len(pairs) - len(contrasts)),
            "pair_delta_mean": (
                float(contrasts["delta_t2_primary_y_regulated_minus_control"].mean())
                if not contrasts.empty
                else None
            ),
            "network_interval": None,
            "network_interval_reported": False,
            "caliper_invented_or_applied": False,
            "rematching_performed": False,
            "balance_supports_formal_confound_control": False,
            "balance_diagnostics": numeric_balance,
            "forbidden_claims": [
                "causal_regulation_effect",
                "formal_confound_control",
                "three_independent_pairs",
                "t5_passed",
                "network_interval",
            ],
        },
    )


def run_post_t2_analysis(
    *,
    workload_path: str | Path,
    result_binding_path: str | Path,
    geometry_catalog_path: str | Path,
    geometry_manifest_path: str | Path,
    pair_plan_path: str | Path,
    pair_manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write readiness only when v4 is absent; otherwise write derived tables."""

    workload = Path(workload_path).resolve()
    result_binding = Path(result_binding_path).resolve()
    output = Path(output_dir).resolve()
    natural, pairs, frozen_identities = _validate_frozen_inputs(
        Path(geometry_catalog_path).resolve(),
        Path(geometry_manifest_path).resolve(),
        Path(pair_plan_path).resolve(),
        Path(pair_manifest_path).resolve(),
    )
    blockers = []
    if not workload.is_file():
        blockers.append("missing_formal_v4_workload_manifest")
    if not result_binding.is_file():
        blockers.append("missing_complete_v4_result_binding")
    output.mkdir(parents=True, exist_ok=True)
    readiness_path = output / "readiness_manifest.json"
    if blockers:
        for name in (
            "t4_network_comparison.csv",
            "t4_result_manifest.json",
            "t5_pair_contrasts.csv",
            "t5_pair_attrition.csv",
            "t5_result_manifest.json",
        ):
            stale = output / name
            if stale.is_file():
                stale.unlink()
        manifest = {
            "manifest_schema": READINESS_SCHEMA,
            "status": "blocked_waiting_for_complete_t2_v4_results",
            "passed": False,
            "formal_evidence": False,
            "headline_claim_licensed": False,
            "purpose": "post_t2_analysis_readiness_not_evidence",
            "blockers": blockers,
            "v4_results_read": False,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
            "old_t4_scores_read": False,
            "old_t5_delta_r_read": False,
            "network_interval": None,
            "network_interval_reported": False,
            "frozen_inputs": frozen_identities,
            "t4": {
                "status": "blocked_waiting_for_t2_primary_y",
                "analysis_name": "natural_geometry_observed_counterpart",
                "truth_source_required": "held_out_observed_counterpart",
                "actual_missing_days_scored": False,
                "actual_missing_performance_estimand": False,
                "aggregation_unit": "network",
                "natural_and_artificial_directly_comparable": False,
            },
            "t5": {
                "status": "descriptive_infeasible_confound_control",
                "n_pair_plan_rows": len(pairs),
                "n_station_pairs": len(pairs),
                "n_unique_network_pairs": int(
                    pairs[["regulated_network_id", "control_network_id"]]
                    .astype(str)
                    .drop_duplicates()
                    .shape[0]
                ),
                "independent_unit": "regulated_control_network_pair",
                "pair_plan_outcome_blind": True,
                "formal_run_allowed": False,
                "caliper_invented_or_applied": False,
                "rematching_performed": False,
                "balance_supports_formal_confound_control": False,
                "forbidden_claims": [
                    "causal_regulation_effect",
                    "formal_confound_control",
                    "three_independent_pairs",
                    "t5_passed",
                ],
            },
            "forbidden_claims": [
                "actual_missing_day_recovery_performance",
                "causal_regulation_effect",
                "t4_passed",
                "t5_passed",
                "formal_confirmation",
            ],
        }
        readiness_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest

    _, primary, binding = validate_v4_primary_inputs(workload, result_binding)
    primary = primary.copy()
    primary["network_id"] = primary["network_id"].astype(str)
    primary["station_id"] = primary["station_id"].astype(str)
    primary["observed_achieved_skill"] = pd.to_numeric(
        primary["observed_achieved_skill"], errors="raise"
    )
    primary["predicted_recoverability"] = pd.to_numeric(
        primary["predicted_recoverability"], errors="raise"
    )
    t4_table, t4_manifest = analyze_t4(primary, natural)
    t5_table, t5_attrition, t5_manifest = analyze_t5(primary, pairs)
    artifacts = {}
    for name, table in (
        ("t4_network_comparison.csv", t4_table),
        ("t5_pair_contrasts.csv", t5_table),
        ("t5_pair_attrition.csv", t5_attrition),
    ):
        path = output / name
        table.to_csv(path, index=False)
        artifacts[name] = {"sha256": _sha256_file(path), "n_rows": len(table)}
    (output / "t4_result_manifest.json").write_text(
        json.dumps(t4_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "t5_result_manifest.json").write_text(
        json.dumps(t5_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    n_t4_networks = int(
        (t4_manifest.get("n_networks_by_geometry") or {}).get("natural_outage", 0)
    )
    dynamic_blockers = []
    if n_t4_networks < 100:
        dynamic_blockers.append("t4_network_interval_withheld_n_lt_100")
    else:
        dynamic_blockers.append("t4_network_interval_not_implemented")
    dynamic_blockers.append(
        "t5_infeasible_confound_control_"
        f"{int(t5_manifest['n_unique_network_pairs'])}_network_pair_units"
    )
    manifest = {
        "manifest_schema": READINESS_SCHEMA,
        "status": "derived_outputs_written_inference_withheld",
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "purpose": "post_t2_derived_analysis_not_confirmation",
        "blockers": dynamic_blockers,
        "v4_results_read": True,
        "v4_result_binding_sha256": _sha256_file(result_binding),
        "v4_workload_sha256": binding["workload_manifest_sha256"],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "old_t4_scores_read": False,
        "old_t5_delta_r_read": False,
        "network_interval": None,
        "network_interval_reported": False,
        "forbidden_claims": [
            "actual_missing_day_recovery_performance",
            "causal_regulation_effect",
            "three_independent_pairs",
            "t4_passed",
            "t5_passed",
            "formal_confirmation",
        ],
        "frozen_inputs": frozen_identities,
        "artifacts": artifacts,
        "t4": t4_manifest,
        "t5": t5_manifest,
    }
    readiness_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


__all__ = [
    "INPUT_BINDING_SCHEMA",
    "OPERATOR_JOIN_KEYS",
    "OPERATOR_PREDICTOR_SCHEMA",
    "PostT2ContractError",
    "analyze_t4",
    "analyze_t5",
    "run_post_t2_analysis",
    "validate_v4_primary_inputs",
]
