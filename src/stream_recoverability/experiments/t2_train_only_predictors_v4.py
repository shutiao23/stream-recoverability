"""Build the outcome-blind predictor sidecar for the complete T2 v4 gap roster.

This is deliberately separate from the seven-gap v1 sidecar.  The v4 item
index is read only to recover its geometry-specific gap roster.  Predictors are
then fit from each open network's first 70% of calendar years, without reading
T2 results, achieved skill, or sealed temperature records.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from stream_recoverability.analysis.conditional_observability import (
    var1_gap_conditional_risk,
)
from stream_recoverability.experiments.recoverability_baselines import (
    acf_only,
    additive_heuristic,
    donor_r2_only,
    gap_length_only,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    discover_failure_closure_networks,
    read_panel,
)
from stream_recoverability.experiments.t2_result_aggregation import (
    input_inventory_sha256,
)
from stream_recoverability.experiments.t2_train_only_predictors import (
    ESTIMATOR_ID,
    JOIN_KEYS,
    PREDICTOR_COLUMNS,
    PredictorContractError,
    _eligible_donors,
    _fit_var1,
    _lag_correlation,
    _train_doy_anomalies,
    _year_block_cv_r2,
    _year_split,
)
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_INDEX_DRAFT_SCHEMA,
    V4_ITEM_INDEX_SCHEMA,
)

SIDECAR_SCHEMA = "t2_v91_train_only_predictors_v2"
FIT_SCOPE = "within_each_open_network_first70pct_calendar_years"
GAP_ROSTER_SOURCE = "formal_v4_item_index_source_item_json"
EXPECTED_INDEX_COLUMNS = (
    "ordinal",
    "item_id",
    "source_v3_ordinal",
    "source_v3_item_id",
    "network_id",
    "meteorology_lag_days",
    "source_item_json",
)
EXPECTED_GEOMETRIES = (
    "adversarial_stress",
    "artificial_stress",
    "natural_outage",
)
FORBIDDEN_SOURCE_ITEM_FIELDS = frozenset(
    {
        "achieved_skill",
        "observed_achieved_skill",
        "observed_recovery_loss",
        "recovery_loss",
        "target_values",
        "truth_values",
    }
)


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


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PredictorContractError(f"cannot read predictor prerequisite {path}") from error
    if not isinstance(value, dict):
        raise PredictorContractError(f"predictor prerequisite is not a mapping: {path}")
    return value


def _refuse_sealed_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise PredictorContractError(f"refusing a sealed-path predictor input: {path}")


def _repo_path(repo: Path, value: object, *, label: str) -> Path:
    path = Path(str(value))
    resolved = (repo / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as error:
        raise PredictorContractError(f"{label} escapes the repository") from error
    _refuse_sealed_path(resolved)
    return resolved


def _validated_gap_roster(
    item_index_path: Path,
    item_record: Mapping[str, Any],
) -> tuple[tuple[int, ...], dict[str, list[int]], int]:
    if _sha256_file(item_index_path) != str(item_record.get("file_sha256", "")):
        raise PredictorContractError("v4 item-index SHA-256 mismatch")
    parquet = pq.ParquetFile(item_index_path)
    columns = tuple(parquet.schema_arrow.names)
    if columns != EXPECTED_INDEX_COLUMNS:
        raise PredictorContractError("v4 item-index columns differ from the frozen schema")
    if tuple(item_record.get("columns") or ()) != EXPECTED_INDEX_COLUMNS:
        raise PredictorContractError("v4 item-index manifest column roster mismatch")
    expected_rows = int(item_record.get("n_rows", -1))
    if parquet.metadata.num_rows != expected_rows:
        raise PredictorContractError("v4 item-index row count mismatch")
    if item_record.get("manifest_schema") != V4_ITEM_INDEX_SCHEMA:
        raise PredictorContractError("unsupported v4 item-index schema")

    gaps_by_geometry: dict[str, set[int]] = defaultdict(set)
    observed_rows = 0
    for batch in parquet.iter_batches(columns=["source_item_json"], batch_size=100_000):
        for payload in batch.column(0).to_pylist():
            try:
                item = json.loads(str(payload))
            except json.JSONDecodeError as error:
                raise PredictorContractError("invalid source_item_json in v4 index") from error
            if not isinstance(item, dict):
                raise PredictorContractError("v4 source item is not a mapping")
            forbidden = FORBIDDEN_SOURCE_ITEM_FIELDS.intersection(item)
            if forbidden:
                raise PredictorContractError(
                    f"v4 item index contains forbidden outcome fields: {sorted(forbidden)}"
                )
            geometry = str(item.get("geometry", ""))
            if geometry not in EXPECTED_GEOMETRIES:
                raise PredictorContractError(f"unknown v4 geometry: {geometry}")
            try:
                gap = int(item["gap_length"])
            except (KeyError, TypeError, ValueError) as error:
                raise PredictorContractError("invalid gap_length in v4 item index") from error
            if gap <= 0:
                raise PredictorContractError("v4 gap lengths must be positive")
            gaps_by_geometry[geometry].add(gap)
            observed_rows += 1
    if observed_rows != expected_rows:
        raise PredictorContractError("incomplete v4 item-index gap scan")
    if set(gaps_by_geometry) != set(EXPECTED_GEOMETRIES):
        raise PredictorContractError("v4 item index does not contain all three geometries")
    normalized = {
        geometry: sorted(gaps_by_geometry[geometry])
        for geometry in EXPECTED_GEOMETRIES
    }
    gaps = tuple(sorted(set().union(*gaps_by_geometry.values())))
    return gaps, normalized, observed_rows


def predict_network_panel_v2(
    network_id: str,
    panel: pd.DataFrame,
    *,
    role: str,
    gaps: Sequence[int],
    skip_ineligible: bool = False,
) -> pd.DataFrame:
    """Fit each station once, then predict all unique v4 gap lengths."""

    if role not in {"development", "validation"}:
        raise PredictorContractError("predictor role must be development or validation")
    gap_roster = tuple(sorted({int(value) for value in gaps}))
    if not gap_roster or gap_roster[0] <= 0 or len(gap_roster) != len(gaps):
        raise PredictorContractError("predictor gaps must be unique positive integers")
    wide = panel.copy()
    if not isinstance(wide.index, pd.DatetimeIndex):
        wide.index = pd.DatetimeIndex(pd.to_datetime(wide.index))
    wide = wide.apply(pd.to_numeric, errors="coerce").sort_index()
    if wide.index.has_duplicates or wide.shape[1] < 2:
        raise PredictorContractError("panel must have unique dates and at least two stations")

    train, _ = _year_split(wide.index)
    train_dates = wide.index[train]
    anomalies = _train_doy_anomalies(wide, train)
    years = train_dates.year.to_numpy()
    rows: list[dict[str, Any]] = []
    attrition: list[dict[str, str]] = []
    for target, station in enumerate(wide.columns.astype(str)):
        try:
            candidates = _eligible_donors(anomalies, target)
            transition, sigma, donors, n_pairs, stabilized = _fit_var1(
                anomalies, train_dates, target, candidates
            )
        except PredictorContractError as error:
            if not skip_ineligible:
                raise
            attrition.append(
                {
                    "network_id": str(network_id),
                    "station_id": str(station),
                    "reason": str(error),
                }
            )
            continue
        target_values = anomalies[:, target]
        donor_values = [anomalies[:, donor] for donor in donors]
        donor_cv = float(_year_block_cv_r2(target_values, donor_values, years))
        phi = float(_lag_correlation(target_values, 1.0))
        if not np.isfinite(donor_cv) or not np.isfinite(phi):
            raise PredictorContractError(
                f"non-finite train-only baseline for {network_id}/{station}"
            )
        donor_cv = float(np.clip(donor_cv, 0.0, 1.0))
        for gap in gap_roster:
            rho_d4 = float(_lag_correlation(target_values, float(gap) / 4.0))
            if not np.isfinite(rho_d4):
                raise PredictorContractError(
                    f"non-finite d/4 ACF for {network_id}/{station}/gap_{gap}"
                )
            operator = var1_gap_conditional_risk(
                transition,
                sigma,
                target=0,
                donors=list(range(1, len(donors) + 1)),
                gap_length=gap,
            )
            row = {
                "network_id": str(network_id),
                "station_id": str(station),
                "gap_length": gap,
                "predicted_conditional_risk": float(
                    operator["predicted_conditional_risk"]
                ),
                "gap_length_only": gap_length_only(gap),
                "acf_only": acf_only(phi, gap),
                "donor_r2_only": donor_r2_only(donor_cv, gap),
                "additive_d_over_4_heuristic": additive_heuristic(donor_cv, rho_d4),
                "role": role,
                "fit_role": role,
                "estimator_id": ESTIMATOR_ID,
                "train_start": str(train_dates.min().date()),
                "train_end": str(train_dates.max().date()),
                "n_train_years": len(pd.unique(years)),
                "n_var_pairs": n_pairs,
                "n_donors": len(donors),
                "donor_station_ids": "|".join(
                    str(wide.columns[donor]) for donor in donors
                ),
                "donor_r2_year_block_cv_raw": donor_cv,
                "acf1_raw": phi,
                "rho_d_over_4_raw": rho_d4,
                "transition_stabilized": stabilized,
            }
            if not all(np.isfinite(float(row[name])) for name in PREDICTOR_COLUMNS):
                raise PredictorContractError(
                    f"non-finite predictor for {network_id}/{station}/gap_{gap}"
                )
            rows.append(row)
    result = pd.DataFrame(rows)
    if result.duplicated(list(JOIN_KEYS)).any():
        raise PredictorContractError("predictor join keys are not unique")
    result.attrs["station_attrition"] = attrition
    return result


def _install_create_once(path: Path, temporary: Path) -> None:
    if path.exists():
        if _sha256_file(path) != _sha256_file(temporary):
            raise PredictorContractError(f"frozen predictor artifact differs: {path}")
        return
    try:
        os.link(temporary, path)
    except FileExistsError:
        if _sha256_file(path) != _sha256_file(temporary):
            raise PredictorContractError(f"concurrent predictor artifact differs: {path}")
    os.chmod(path, 0o444)


def _create_once_table(path: Path, frame: pd.DataFrame, *, parquet: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        if parquet:
            frame.to_parquet(temporary, index=False)
        else:
            frame.to_csv(temporary, index=False)
        _install_create_once(path, temporary)
    finally:
        temporary.unlink(missing_ok=True)


def _create_once_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise PredictorContractError(f"frozen predictor manifest differs: {path}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def build_v4_train_only_predictor_sidecar(
    *,
    repo_root: str | Path,
    index_draft_manifest_path: str | Path,
    design_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build a create-once predictor sidecar covering every v4 index gap."""

    repo = Path(repo_root).resolve()
    draft_path = Path(index_draft_manifest_path).resolve()
    design = Path(design_path).resolve()
    output = Path(output_dir).resolve()
    for path in (draft_path, design, output):
        _refuse_sealed_path(path)
    draft = _read_mapping(draft_path)
    if draft.get("manifest_schema") != V4_INDEX_DRAFT_SCHEMA:
        raise PredictorContractError("unsupported v4 index-draft schema")
    if (
        draft.get("sealed_paths_traversed") is not False
        or draft.get("sealed_temperature_records_read") is not False
        or (draft.get("input_inventory") or {}).get("sealed_input_roots_allowed") != []
    ):
        raise PredictorContractError("v4 index draft does not keep sealed inputs closed")
    item_record = draft.get("item_index")
    if not isinstance(item_record, Mapping):
        raise PredictorContractError("v4 index draft lacks its item-index record")
    item_index_path = _repo_path(repo, item_record.get("path"), label="item index")
    if not item_index_path.is_file():
        raise PredictorContractError("v4 item index is absent")
    gaps, gaps_by_geometry, scanned_rows = _validated_gap_roster(
        item_index_path, item_record
    )

    source_v3_path = _repo_path(
        repo, draft.get("source_v3_workload_path"), label="source v3 workload"
    )
    source_v3 = _read_mapping(source_v3_path)
    source_v3_sha = _sha256_file(source_v3_path)
    if source_v3_sha != draft.get("source_v3_workload_sha256"):
        raise PredictorContractError("v4 draft/source-v3 workload SHA-256 mismatch")
    design_sha = _sha256_file(design)
    if source_v3.get("design_sha256") != design_sha:
        raise PredictorContractError("source-v3 workload/design SHA-256 mismatch")
    if source_v3.get("input_inventory") != draft.get("input_inventory"):
        raise PredictorContractError("v4 draft/source-v3 input inventory mismatch")

    networks, discovery = discover_failure_closure_networks(repo)
    expected_ids = [str(value) for value in draft.get("network_ids") or []]
    if expected_ids != [network.network_id for network in networks]:
        raise PredictorContractError("open network order differs from the v4 index draft")
    input_map = {network.network_id: network.wide_sha256 for network in networks}
    if input_map != draft.get("input_sha256_by_network"):
        raise PredictorContractError("open network bytes differ from the v4 index draft")
    inventory_sha = input_inventory_sha256(input_map)
    if inventory_sha != draft.get("input_sha256_by_network_sha256"):
        raise PredictorContractError("v4 input-inventory identity mismatch")

    frames: list[pd.DataFrame] = []
    station_attrition: list[dict[str, str]] = []
    for network in networks:
        panel_path = _repo_path(repo, network.wide_path, label="open-role panel")
        if not panel_path.is_file():
            raise PredictorContractError(f"open-role panel is absent: {network.network_id}")
        panel = read_panel(repo, network)
        frame = predict_network_panel_v2(
            network.network_id,
            panel,
            role=network.role,
            gaps=gaps,
            skip_ineligible=True,
        )
        station_attrition.extend(frame.attrs.get("station_attrition", []))
        frames.append(frame)
    predictions = pd.concat(frames, ignore_index=True)
    predictions = predictions.sort_values(list(JOIN_KEYS), kind="stable").reset_index(
        drop=True
    )
    eligible_stations = int(
        predictions[["network_id", "station_id"]].drop_duplicates().shape[0]
    )
    expected_rows = eligible_stations * len(gaps)
    if len(predictions) != expected_rows:
        raise PredictorContractError(
            f"v4 predictor sidecar incomplete: {len(predictions)} of {expected_rows} rows"
        )
    if set(predictions["gap_length"].astype(int)) != set(gaps):
        raise PredictorContractError("v4 predictor output does not cover the full gap roster")

    output.mkdir(parents=True, exist_ok=True)
    parquet_path = output / "train_only_predictors.parquet"
    csv_path = output / "train_only_predictors.csv"
    attrition_path = output / "predictor_station_attrition.csv"
    _create_once_table(parquet_path, predictions, parquet=True)
    _create_once_table(csv_path, predictions, parquet=False)
    _create_once_table(
        attrition_path,
        pd.DataFrame(
            station_attrition, columns=["network_id", "station_id", "reason"]
        ),
        parquet=False,
    )
    gap_roster_sha = _canonical_sha(
        {"gaps": list(gaps), "gaps_by_geometry": gaps_by_geometry}
    )
    manifest: dict[str, Any] = {
        "manifest_schema": SIDECAR_SCHEMA,
        "index_draft_manifest_path": str(draft_path.relative_to(repo)),
        "index_draft_manifest_sha256": _sha256_file(draft_path),
        "item_index_path": str(item_index_path.relative_to(repo)),
        "item_index_sha256": _sha256_file(item_index_path),
        "item_index_work_item_identity_sha256": item_record.get(
            "work_item_identity_sha256"
        ),
        "item_index_rows_scanned": scanned_rows,
        "source_v3_workload_path": str(source_v3_path.relative_to(repo)),
        "source_v3_workload_sha256": source_v3_sha,
        "design_path": str(design.relative_to(repo)),
        "design_sha256": design_sha,
        "input_inventory": draft.get("input_inventory"),
        "input_inventory_contract_sha256": _canonical_sha(draft["input_inventory"]),
        "input_inventory_sha256": inventory_sha,
        "input_sha256_by_network": dict(sorted(input_map.items())),
        "input_sha256_by_network_sha256": inventory_sha,
        "catalog_split_sha256": (draft.get("input_inventory") or {}).get(
            "catalog_split_sha256"
        ),
        "gap_roster_source": GAP_ROSTER_SOURCE,
        "gap_roster_sha256": gap_roster_sha,
        "gaps": list(gaps),
        "gaps_by_geometry": gaps_by_geometry,
        "n_unique_gaps": len(gaps),
        "fit_scope": FIT_SCOPE,
        "fit_role": "development",
        "fit_role_note": (
            "Reserved aggregation-contract role for learned calibration; raw "
            "predictors fit each open network's own first-70%-years window."
        ),
        "network_covariance_fit_scope": "within_network_first_70pct_calendar_years",
        "validation_application": "raw_frozen_formula_no_development_outcome_calibration",
        "learned_calibration": False,
        "calibration_status": "not_fit_raw_predictors_only",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "recovery_result_rows_read": False,
        "achieved_skill_read": False,
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "operator_estimator": ESTIMATOR_ID,
        "operator_information_set": "B_union_D",
        "donor_r2_estimator": "leave_one_train_year_out_r2",
        "join_keys": list(JOIN_KEYS),
        "predictor_columns": list(PREDICTOR_COLUMNS),
        "n_networks": len(networks),
        "n_stations_inventory": int(sum(network.n_stations for network in networks)),
        "n_stations_predictor_eligible": eligible_stations,
        "n_stations_predictor_ineligible": len(station_attrition),
        "n_rows": len(predictions),
        "roles": discovery.get("roles"),
        "predictions_path": csv_path.name,
        "predictions_format": "csv",
        "predictions_sha256": _sha256_file(csv_path),
        "parquet_path": parquet_path.name,
        "parquet_sha256": _sha256_file(parquet_path),
        "station_attrition_path": attrition_path.name,
        "station_attrition_sha256": _sha256_file(attrition_path),
        "completeness": "complete",
        "formal_evidence": False,
        "purpose": "v4_train_only_predictor_sidecar_not_t2_recovery_evidence",
    }
    _create_once_json(output / "predictor_manifest.json", manifest)
    return manifest


__all__ = [
    "FIT_SCOPE",
    "GAP_ROSTER_SOURCE",
    "SIDECAR_SCHEMA",
    "build_v4_train_only_predictor_sidecar",
    "predict_network_panel_v2",
]
