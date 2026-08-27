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
import pyarrow as pa
import pyarrow.parquet as pq

from .t2_recovery_benchmark import (
    EXTENDED_INFORMATION_CONDITIONS,
    WorkItem,
    _cell_contract,
)
from .t2_result_aggregation_v4 import (
    V4_AGGREGATION_SCHEMA,
    _assert_full_row_identities,
    _expected_identities,
)
from .t2_train_only_predictors import JOIN_KEYS, PREDICTOR_COLUMNS, SIDECAR_SCHEMA
from .t2_train_only_predictors_v4 import (
    GAP_ROSTER_SOURCE as V4_GAP_ROSTER_SOURCE,
)
from .t2_train_only_predictors_v4 import SIDECAR_SCHEMA as V4_SIDECAR_SCHEMA
from .t2_workload_v4 import (
    V4_INDEX_DRAFT_SCHEMA,
    V4_ITEM_INDEX_SCHEMA,
    V4_PRE_SCORE_FREEZE_SCHEMA,
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
BASE_PRIMARY_GRID = (
    ("pchip_or_linear", "B", "offline_archival", "none"),
    ("kalman", "B", "offline_archival", "none"),
    ("donor_regression", "D", "offline_archival", "none"),
    ("xgboost", "D", "offline_archival", "none"),
    ("donor_regression", "B_union_D", "offline_archival", "none"),
    ("xgboost", "B_union_D", "offline_archival", "none"),
)

SENSITIVITY_GRIDS = {
    "M": tuple(
        (model, information, "offline_archival", str(lag))
        for model in ("donor_regression", "xgboost")
        for information in ("B_union_D_union_M",)
        for lag in (-1, 0, 1)
    ),
    "M_H": tuple(
        (model, information, "offline_archival", str(lag))
        for model in ("donor_regression", "xgboost")
        for information in ("B_union_D_union_M_union_H",)
        for lag in (-1, 0, 1)
    ),
}
# Backward import name; the primary grid is now intentionally base-only.
PRIMARY_COMMON_GRID = BASE_PRIMARY_GRID
FIXED_PRIMARY_GEOMETRIES = ("artificial_stress", "natural_outage")
LEDGER_SCHEMA = "t2_v91_v4_exhaustive_pre_score_item_ledger_v1"
FEASIBILITY_SCHEMA = "t2_v91_v4_outcome_blind_feasibility_census_v1"
NETWORK_INTERVAL_FLOOR = 100


class PrimaryAggregationBlocked(ValueError):
    """Raised when a present artifact violates the pre/post-score boundary."""


def _equal_hierarchical_event_weights(
    events: set[tuple[Any, ...]], *, grid_size: int
) -> dict[tuple[Any, ...], tuple[float, float, float, float, float, float]]:
    """Equal geometry/network/gap/event/grid mass, independent of row counts."""

    if not events or grid_size < 1:
        return {}
    geometries = sorted({event[3] for event in events})
    networks_by_geometry = {
        geometry: {event[1] for event in events if event[3] == geometry}
        for geometry in geometries
    }
    gaps_by_geometry_network = {
        (geometry, network): {
            event[7] for event in events if event[3] == geometry and event[1] == network
        }
        for geometry in geometries
        for network in networks_by_geometry[geometry]
    }
    events_by_stratum = Counter((event[3], event[1], event[7]) for event in events)
    weights = {}
    for event in events:
        geometry, network, gap = event[3], event[1], event[7]
        parts = (
            1.0 / len(geometries),
            1.0 / len(networks_by_geometry[geometry]),
            1.0 / len(gaps_by_geometry_network[(geometry, network)]),
            1.0 / events_by_stratum[(geometry, network, gap)],
            1.0 / grid_size,
        )
        weights[event] = (*parts, float(np.prod(parts)))
    return weights


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
        raise PrimaryAggregationBlocked(
            f"cannot read primary binding input: {path}"
        ) from error
    if not isinstance(value, dict):
        raise PrimaryAggregationBlocked(
            f"primary binding input is not a mapping: {path}"
        )
    return value


def _assert_open(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise PrimaryAggregationBlocked(f"primary binding refuses sealed path: {path}")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
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
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
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
                raise PrimaryAggregationBlocked(
                    f"frozen artifact already differs: {path}"
                )
            return
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _install_create_once(path: Path, temporary: Path) -> None:
    """Install completed temporary bytes without permitting replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if _sha256_file(path) != _sha256_file(temporary):
            raise PrimaryAggregationBlocked(f"frozen artifact already differs: {path}")
        return
    try:
        os.link(temporary, path)
    except FileExistsError:
        if _sha256_file(path) != _sha256_file(temporary):
            raise PrimaryAggregationBlocked(
                f"concurrent frozen artifact differs: {path}"
            )
    os.chmod(path, 0o444)


class _ParquetSink:
    """Small streaming Parquet sink with deterministic schema and create-once install."""

    def __init__(self, output: Path, schema: pa.Schema) -> None:
        self.output = output
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        os.close(descriptor)
        self.temporary = Path(name)
        self.temporary.unlink()
        self.schema = schema
        self.writer: pq.ParquetWriter | None = pq.ParquetWriter(
            self.temporary, schema, compression="zstd"
        )
        self.rows: list[dict[str, Any]] = []
        self.n_rows = 0

    def append(self, row: Mapping[str, Any]) -> None:
        self.rows.append(dict(row))
        if len(self.rows) >= 20_000:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        table = pa.Table.from_pylist(self.rows, schema=self.schema)
        if self.writer is None:
            raise PrimaryAggregationBlocked("streaming sink is already closed")
        self.writer.write_table(table, row_group_size=20_000)
        self.n_rows += len(self.rows)
        self.rows.clear()

    def close(self) -> dict[str, Any]:
        self.flush()
        if self.writer is None:
            raise PrimaryAggregationBlocked("streaming sink is already closed")
        self.writer.close()
        self.writer = None
        _install_create_once(self.output, self.temporary)
        record = {
            "path": self.output.name,
            "format": "parquet",
            "sha256": _sha256_file(self.output),
            "n_rows": self.n_rows,
        }
        if self.temporary.exists():
            self.temporary.unlink()
        return record

    def abort(self) -> None:
        if self.writer is not None:
            self.writer.close()
            self.writer = None
        if self.temporary.exists():
            self.temporary.unlink()


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


def _update_logical_result_digest(
    digest: Any, frame: pd.DataFrame, columns: list[str]
) -> None:
    """Hash ordered logical rows independent of their container bytes."""

    def normalize(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return [normalize(item) for item in value.tolist()]
        if isinstance(value, np.generic):
            return normalize(value.item())
        if isinstance(value, Mapping):
            return {
                str(key): normalize(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and bool(missing):
            return None
        return value

    aligned = frame.reindex(columns=columns)
    for values in aligned.itertuples(index=False, name=None):
        normalized = [normalize(value) for value in values]
        digest.update(
            json.dumps(
                normalized,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        )
        digest.update(b"\n")


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
    source = (
        json.loads(source_json) if isinstance(source_json, str) else dict(source_json)
    )
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


def _load_workload_index(
    workload_path: Path,
) -> tuple[dict[str, Any], pd.DataFrame, Path]:
    workload = _read_json(workload_path)
    if (
        workload.get("manifest_schema")
        not in {V4_INDEX_DRAFT_SCHEMA, V4_WORKLOAD_SCHEMA}
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
    if record.get("manifest_schema") != V4_ITEM_INDEX_SCHEMA or _sha256_file(
        index_path
    ) != record.get("file_sha256"):
        raise PrimaryAggregationBlocked("v4 item index identity mismatch")
    index = pd.read_parquet(index_path).sort_values("ordinal", kind="stable")
    n_items = int(workload.get("n_work_items", -1))
    if (
        len(index) != n_items
        or index["ordinal"].astype(int).tolist() != list(range(n_items))
        or _stream_sha(index) != workload.get("work_item_identity_sha256")
    ):
        raise PrimaryAggregationBlocked(
            "v4 item index is not the complete frozen stream"
        )
    return workload, index, index_path


def _load_sidecar(
    manifest_path: Path,
    *,
    workload: Mapping[str, Any],
    workload_path: Path,
    index_path: Path,
) -> tuple[dict[str, Any], pd.DataFrame, Path]:
    manifest = _read_json(manifest_path)
    required = {
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "recovery_result_rows_read": False,
        "sealed_temperature_records_read": False,
        "completeness": "complete",
        "join_keys": list(JOIN_KEYS),
        "input_sha256_by_network": workload.get("input_sha256_by_network"),
        "catalog_split_sha256": (workload.get("input_inventory") or {}).get(
            "catalog_split_sha256"
        ),
        "network_covariance_fit_scope": "within_network_first_70pct_calendar_years",
        "learned_calibration": False,
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise PrimaryAggregationBlocked(f"train-only sidecar mismatch for {key}")
    schema = manifest.get("manifest_schema")
    if schema == SIDECAR_SCHEMA:
        if manifest.get("workload_manifest_sha256") != workload.get(
            "source_v3_workload_sha256"
        ):
            raise PrimaryAggregationBlocked(
                "train-only sidecar mismatch for workload_manifest_sha256"
            )
    elif schema == V4_SIDECAR_SCHEMA:
        v2_required = {
            "index_draft_manifest_sha256": _sha256_file(workload_path),
            "item_index_sha256": _sha256_file(index_path),
            "item_index_work_item_identity_sha256": workload.get(
                "work_item_identity_sha256"
            ),
            "source_v3_workload_sha256": workload.get("source_v3_workload_sha256"),
            "input_inventory": workload.get("input_inventory"),
            "input_inventory_contract_sha256": _canonical_sha(
                workload.get("input_inventory")
            ),
            "input_inventory_sha256": workload.get(
                "input_sha256_by_network_sha256"
            ),
            "input_sha256_by_network_sha256": workload.get(
                "input_sha256_by_network_sha256"
            ),
            "gap_roster_source": V4_GAP_ROSTER_SOURCE,
            "predictor_columns": list(PREDICTOR_COLUMNS),
            "achieved_skill_read": False,
            "sealed_input_roots_allowed": [],
        }
        for key, expected in v2_required.items():
            if manifest.get(key) != expected:
                raise PrimaryAggregationBlocked(
                    f"v4 train-only sidecar mismatch for {key}"
                )
        if (
            _artifact_path(
                manifest_path, str(manifest.get("index_draft_manifest_path", ""))
            )
            != workload_path
            or _artifact_path(
                manifest_path, str(manifest.get("item_index_path", ""))
            )
            != index_path
        ):
            raise PrimaryAggregationBlocked(
                "v4 train-only sidecar path bindings differ from the item-index draft"
            )
        source_v3_path = _artifact_path(
            workload_path, str(workload.get("source_v3_workload_path", ""))
        )
        manifest_source_v3_path = _artifact_path(
            manifest_path, str(manifest.get("source_v3_workload_path", ""))
        )
        design_path = _artifact_path(
            manifest_path, str(manifest.get("design_path", ""))
        )
        if (
            manifest_source_v3_path != source_v3_path
            or not source_v3_path.is_file()
            or _sha256_file(source_v3_path)
            != manifest.get("source_v3_workload_sha256")
            or not design_path.is_file()
            or _sha256_file(design_path) != manifest.get("design_sha256")
            or _read_json(source_v3_path).get("design_sha256")
            != manifest.get("design_sha256")
        ):
            raise PrimaryAggregationBlocked(
                "v4 train-only sidecar source-workload/design binding is invalid"
            )
        gaps_by_geometry = manifest.get("gaps_by_geometry")
        gap_roster = {
            "gaps": manifest.get("gaps"),
            "gaps_by_geometry": gaps_by_geometry,
        }
        if (
            not isinstance(gaps_by_geometry, Mapping)
            or set(gaps_by_geometry)
            != {"adversarial_stress", *FIXED_PRIMARY_GEOMETRIES}
            or manifest.get("gap_roster_sha256") != _canonical_sha(gap_roster)
        ):
            raise PrimaryAggregationBlocked(
                "v4 train-only sidecar gap-roster binding is invalid"
            )
    else:
        raise PrimaryAggregationBlocked("unsupported train-only sidecar schema")
    try:
        gaps = [int(value) for value in manifest.get("gaps") or []]
    except (TypeError, ValueError) as error:
        raise PrimaryAggregationBlocked(
            "train-only sidecar gap roster is invalid"
        ) from error
    if not gaps or gaps != sorted(set(gaps)) or any(value < 1 for value in gaps):
        raise PrimaryAggregationBlocked("train-only sidecar gap roster is invalid")
    path = _artifact_path(manifest_path, str(manifest.get("parquet_path", "")))
    _assert_open(path)
    if not path.is_file() or _sha256_file(path) != manifest.get("parquet_sha256"):
        raise PrimaryAggregationBlocked("train-only predictor table SHA mismatch")
    predictors = pd.read_parquet(path)
    required_columns = {*JOIN_KEYS, *PREDICTOR_COLUMNS, "role", "fit_role"}
    if not required_columns.issubset(predictors.columns):
        raise PrimaryAggregationBlocked(
            "train-only predictor table lacks frozen columns"
        )
    if predictors.duplicated(list(JOIN_KEYS)).any():
        raise PrimaryAggregationBlocked("train-only predictor keys are not unique")
    if not predictors["role"].astype(str).eq(predictors["fit_role"].astype(str)).all():
        raise PrimaryAggregationBlocked(
            "sidecar fit role differs from its network role"
        )
    if schema == V4_SIDECAR_SCHEMA and (
        len(predictors) != int(manifest.get("n_rows", -1))
        or predictors["gap_length"].astype(int).nunique()
        != int(manifest.get("n_unique_gaps", -1))
        or set(predictors["gap_length"].astype(int)) != set(gaps)
    ):
        raise PrimaryAggregationBlocked(
            "v4 train-only predictor table is not roster-complete"
        )
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
        for network, record in (
            workload.get("auxiliary_network_bindings") or {}
        ).items()
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
        "open_qc_temperature_csv_bytes_traversed": True,
        "open_qc_excluded_temperature_fields_decoded": False,
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
        "pre_score_freeze_sha256": (workload.get("pre_score_freeze") or {}).get(
            "sha256"
        ),
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
        raise PrimaryAggregationBlocked(
            "pre-score eligibility does not cover the item index"
        )
    allowed = {
        "complete",
        "reference_complete",
        "structural_not_applicable",
        "data_ineligible",
    }
    if not set(table["pre_score_status"].astype(str)).issubset(allowed):
        raise PrimaryAggregationBlocked(
            "pre-score eligibility contains an unknown status"
        )
    ineligible = table["pre_score_status"].astype(str).eq("data_ineligible")
    if table.loc[ineligible, "reason"].fillna("").astype(str).str.strip().eq("").any():
        raise PrimaryAggregationBlocked(
            "data-ineligible pre-score audit has a blank reason"
        )
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
    """Two-pass streaming freeze of base and sensitivity lattices."""

    workload_path = Path(workload_manifest_path).resolve()
    predictor_manifest_file = Path(predictor_manifest_path).resolve()
    eligibility_manifest_file = Path(eligibility_manifest_path).resolve()
    output = Path(output_dir).resolve()
    for path in (
        workload_path,
        predictor_manifest_file,
        eligibility_manifest_file,
        output,
    ):
        _assert_open(path)
    if not workload_path.is_file():
        return _blocked_readiness(
            output, ["v4_index_draft_absent", "v4_item_index_absent"]
        )
    workload = _read_json(workload_path)
    if workload.get("manifest_schema") not in {
        V4_INDEX_DRAFT_SCHEMA,
        V4_WORKLOAD_SCHEMA,
    }:
        raise PrimaryAggregationBlocked(
            "lattice requires the v4 index draft/final workload"
        )
    record = workload.get("item_index") or {}
    index_path = _artifact_path(workload_path, str(record.get("path", "")))
    if (
        record.get("manifest_schema") != V4_ITEM_INDEX_SCHEMA
        or not index_path.is_file()
        or _sha256_file(index_path) != record.get("file_sha256")
    ):
        return _blocked_readiness(output, ["v4_item_index_absent_or_invalid"])
    if not predictor_manifest_file.is_file() or not eligibility_manifest_file.is_file():
        blockers = []
        if not predictor_manifest_file.is_file():
            blockers.append("train_only_predictor_sidecar_absent")
        if not eligibility_manifest_file.is_file():
            blockers.append("outcome_blind_pre_score_eligibility_audit_absent")
        return _blocked_readiness(output, blockers)
    sidecar_manifest, sidecar, sidecar_path = _load_sidecar(
        predictor_manifest_file,
        workload=workload,
        workload_path=workload_path,
        index_path=index_path,
    )
    sidecar["station_id"] = sidecar["station_id"].astype(str)
    sidecar_lookup = {
        (str(row.network_id), str(row.station_id), int(row.gap_length)): row._asdict()
        for row in sidecar.itertuples(index=False)
    }
    eligibility_manifest = _read_json(eligibility_manifest_file)
    eligibility_record = eligibility_manifest.get("eligibility_table") or {}
    eligibility_path = _artifact_path(
        eligibility_manifest_file, str(eligibility_record.get("path", ""))
    )
    # Validate the complete audit without materializing its 2.49M item-id set.
    required_eligibility = {
        "manifest_schema": ELIGIBILITY_AUDIT_SCHEMA,
        "builder_schema": "t2_v91_v4_pre_score_eligibility_builder_v1",
        "status": "complete_outcome_blind_pre_score_audit",
        "completeness": "complete",
        "workload_manifest_sha256": _sha256_file(workload_path),
        "item_index_file_sha256": _sha256_file(index_path),
        "achieved_skill_read": False,
        "selection_uses_outcomes": False,
        "open_qc_temperature_value_columns_read": [],
        "open_qc_temperature_na_availability_read": False,
        "open_qc_temperature_csv_bytes_traversed": True,
        "open_qc_excluded_temperature_fields_decoded": False,
        "gap_truth_values_read": False,
        "model_fit_or_prediction_run": False,
        "old_outcomes_read": False,
        "expected_item_records": int(workload.get("n_work_items", -1)),
        "observed_item_records": int(workload.get("n_work_items", -1)),
        "work_item_identity_sha256": workload.get("work_item_identity_sha256"),
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    for key, expected in required_eligibility.items():
        if eligibility_manifest.get(key) != expected:
            raise PrimaryAggregationBlocked(f"pre-score eligibility mismatch for {key}")
    if not eligibility_path.is_file() or _sha256_file(
        eligibility_path
    ) != eligibility_record.get("sha256"):
        raise PrimaryAggregationBlocked("pre-score eligibility table SHA mismatch")
    if FORBIDDEN_OUTCOME_COLUMNS & set(
        pq.ParquetFile(eligibility_path).schema_arrow.names
    ):
        raise PrimaryAggregationBlocked("pre-score eligibility is not outcome-blind")

    grids: dict[str, tuple[tuple[str, str, str, str], ...]] = {
        "base_primary": BASE_PRIMARY_GRID,
        **{f"sensitivity_{key}": value for key, value in SENSITIVITY_GRIDS.items()},
    }
    bit_lookup = {
        name: {cell: 1 << position for position, cell in enumerate(grid)}
        for name, grid in grids.items()
    }
    full_masks = {name: (1 << len(grid)) - 1 for name, grid in grids.items()}
    event_masks: dict[str, dict[tuple[Any, ...], int]] = {name: {} for name in grids}
    design_rosters = {
        name: {
            "networks": set(),
            "geometries": set(),
            "gaps": set(),
            "gaps_by_geometry": {
                geometry: set() for geometry in FIXED_PRIMARY_GEOMETRIES
            },
            "network_geometry_gap_strata": set(),
        }
        for name in grids
    }
    expected_n = int(workload.get("n_work_items", -1))
    item_digest = hashlib.sha256()
    status_counts: Counter[str] = Counter()
    indexed_gaps_by_geometry: dict[str, set[int]] = {
        geometry: set()
        for geometry in (
            "adversarial_stress",
            "artificial_stress",
            "natural_outage",
        )
    }

    def rows(path: Path, columns: list[str]):
        for batch in pq.ParquetFile(path).iter_batches(
            batch_size=20_000, columns=columns
        ):
            yield from batch.to_pylist()

    index_columns = ["ordinal", "item_id", "meteorology_lag_days", "source_item_json"]
    eligibility_columns = ["item_id", "pre_score_status", "reason"]
    next_ordinal = 0
    for raw, audit in zip(
        rows(index_path, index_columns),
        rows(eligibility_path, eligibility_columns),
        strict=True,
    ):
        if int(raw["ordinal"]) != next_ordinal or str(raw["item_id"]) != str(
            audit["item_id"]
        ):
            raise PrimaryAggregationBlocked("index/eligibility streams differ")
        next_ordinal += 1
        item_id = str(raw["item_id"])
        item_digest.update(item_id.encode())
        item_digest.update(b"\n")
        source = json.loads(str(raw["source_item_json"]))
        lag = str(raw["meteorology_lag_days"])
        geometry = str(source["geometry"])
        if geometry not in indexed_gaps_by_geometry:
            raise PrimaryAggregationBlocked(
                f"formal item index contains unknown geometry: {geometry}"
            )
        indexed_gaps_by_geometry[geometry].add(int(source["gap_length"]))
        structural = _structural_status(source, lag)
        pre_status = str(audit["pre_score_status"])
        if structural != "complete" and structural != pre_status:
            raise PrimaryAggregationBlocked(
                "pre-score audit contradicts structural applicability"
            )
        if structural == "complete" and pre_status not in {
            "complete",
            "data_ineligible",
        }:
            raise PrimaryAggregationBlocked(
                "pre-score audit changed an executable cell structurally"
            )
        status_counts[pre_status] += 1
        event = (
            str(source["role"]),
            str(source["network_id"]),
            str(source["target_station"]),
            str(source["geometry"]),
            str(source.get("geometry_id") or ""),
            str(source.get("truth_start_date") or ""),
            str(source.get("observed_missing_start_date") or ""),
            int(source["gap_length"]),
            int(source["placement"]),
            int(source["start_index"]),
        )
        cell = (
            str(source["model"]),
            str(source["information_condition"]),
            str(source["task"]),
            lag,
        )
        predictor_key = (event[1], event[2], event[7])
        predictor = sidecar_lookup.get(predictor_key)
        predictor_ok = predictor is not None and str(predictor["role"]) == event[0]
        for name, lookup in bit_lookup.items():
            bit = lookup.get(cell)
            if bit is None or event[3] not in FIXED_PRIMARY_GEOMETRIES:
                continue
            roster = design_rosters[name]
            roster["networks"].add(event[1])
            roster["geometries"].add(event[3])
            roster["gaps"].add(event[7])
            roster["gaps_by_geometry"][event[3]].add(event[7])
            roster["network_geometry_gap_strata"].add((event[1], event[3], event[7]))
            if pre_status == "complete" and predictor_ok:
                event_masks[name][event] = event_masks[name].get(event, 0) | bit
    if (
        next_ordinal != expected_n
        or next_ordinal != int(eligibility_record.get("n_rows", -1))
        or item_digest.hexdigest() != workload.get("work_item_identity_sha256")
    ):
        raise PrimaryAggregationBlocked("pre-score streams are not identity-complete")

    declared_predictor_gaps = {
        int(value) for value in sidecar_manifest.get("gaps") or []
    }
    indexed_gaps = set().union(*indexed_gaps_by_geometry.values())
    missing_predictor_gaps = sorted(indexed_gaps - declared_predictor_gaps)
    if missing_predictor_gaps:
        raise PrimaryAggregationBlocked(
            "train-only predictor gap roster is incomplete for the formal item index: "
            f"{missing_predictor_gaps}"
        )
    if sidecar_manifest.get("manifest_schema") == V4_SIDECAR_SCHEMA:
        declared_by_geometry = {
            str(geometry): sorted(map(int, gaps))
            for geometry, gaps in (
                sidecar_manifest.get("gaps_by_geometry") or {}
            ).items()
        }
        observed_by_geometry = {
            geometry: sorted(gaps)
            for geometry, gaps in indexed_gaps_by_geometry.items()
        }
        if declared_by_geometry != observed_by_geometry:
            raise PrimaryAggregationBlocked(
                "v4 train-only predictor geometry gap roster differs from the formal "
                "item index"
            )

    eligible_events = {
        name: {event for event, mask in masks.items() if mask == full_masks[name]}
        for name, masks in event_masks.items()
    }
    census_lattices: dict[str, Any] = {}
    lattice_ready: dict[str, bool] = {}
    for name, events in eligible_events.items():
        selected = {
            "networks": {event[1] for event in events},
            "geometries": {event[3] for event in events},
            "gaps": {event[7] for event in events},
            "gaps_by_geometry": {
                geometry: {event[7] for event in events if event[3] == geometry}
                for geometry in FIXED_PRIMARY_GEOMETRIES
            },
            "network_geometry_gap_strata": {
                (event[1], event[3], event[7]) for event in events
            },
        }
        candidates = design_rosters[name]
        expected_networks = set(
            map(
                str,
                workload.get("network_ids")
                or (workload.get("input_sha256_by_network") or {}).keys(),
            )
        )
        required_geometries = set(FIXED_PRIMARY_GEOMETRIES)
        required_artificial_gaps = set(
            candidates["gaps_by_geometry"]["artificial_stress"]
        )
        blockers = []
        missing_networks = sorted(expected_networks - selected["networks"])
        missing_geometries = sorted(required_geometries - selected["geometries"])
        missing_artificial_gaps = sorted(
            required_artificial_gaps
            - selected["gaps_by_geometry"]["artificial_stress"]
        )
        if missing_networks:
            blockers.append(
                f"missing_required_networks:{','.join(map(str, missing_networks))}"
            )
        if missing_geometries:
            blockers.append(
                f"missing_required_geometries:{','.join(missing_geometries)}"
            )
        if missing_artificial_gaps:
            blockers.append(
                "missing_required_artificial_gaps:"
                f"{','.join(map(str, missing_artificial_gaps))}"
            )
        if not selected["gaps_by_geometry"]["natural_outage"]:
            blockers.append("no_pre_score_eligible_natural_gap")
        if not events:
            blockers.append("no_complete_events")
        lattice_ready[name] = not blockers

        def sorted_roster(value: Mapping[str, Any]) -> dict[str, Any]:
            return {
                "networks": sorted(value["networks"]),
                "geometries": sorted(value["geometries"]),
                "gaps": sorted(value["gaps"]),
                "gaps_by_geometry": {
                    geometry: sorted(gaps)
                    for geometry, gaps in value["gaps_by_geometry"].items()
                },
                "network_geometry_gap_strata": sorted(
                    value["network_geometry_gap_strata"]
                ),
            }

        selected_network_geometry_pairs = {
            (event[1], event[3]) for event in events
        }
        candidate_network_geometry_pairs = {
            (network, geometry)
            for network, geometry, _gap in candidates[
                "network_geometry_gap_strata"
            ]
        }
        census_lattices[name] = {
            "status": "ready"
            if not blockers
            else "blocked_insufficient_pre_score_support",
            "blockers": blockers,
            "grid": [list(cell) for cell in grids[name]],
            "grid_sha256": _canonical_sha(grids[name]),
            "pre_score_roster_rule": (
                "event_is_selected_iff_all_frozen_grid_cells_are_pre_score_complete_"
                "and_the_train_only_predictor_key_is_present"
            ),
            "fixed_roster": sorted_roster(selected),
            "pre_score_eligible_roster": sorted_roster(selected),
            "design_candidate_roster": sorted_roster(candidates),
            "coverage_gate": {
                "required_networks": sorted(expected_networks),
                "required_geometries": sorted(required_geometries),
                "required_artificial_gaps": sorted(required_artificial_gaps),
                "natural_gap_rule": "at_least_one_eligible_natural_gap_globally",
                "network_geometry_gap_cross_product_required": False,
                "network_coverage": {
                    "required": len(expected_networks),
                    "selected": len(selected["networks"]),
                    "fraction": (
                        len(selected["networks"] & expected_networks)
                        / len(expected_networks)
                        if expected_networks
                        else 0.0
                    ),
                },
                "geometry_coverage": {
                    "required": len(required_geometries),
                    "selected": len(selected["geometries"]),
                    "fraction": (
                        len(selected["geometries"] & required_geometries)
                        / len(required_geometries)
                    ),
                },
                "gap_coverage_by_geometry": {
                    geometry: {
                        "candidate": len(candidates["gaps_by_geometry"][geometry]),
                        "selected": len(selected["gaps_by_geometry"][geometry]),
                        "selected_values": sorted(
                            selected["gaps_by_geometry"][geometry]
                        ),
                    }
                    for geometry in FIXED_PRIMARY_GEOMETRIES
                },
                "network_geometry_pair_coverage": {
                    "candidate": len(candidate_network_geometry_pairs),
                    "selected": len(selected_network_geometry_pairs),
                    "fraction": (
                        len(selected_network_geometry_pairs)
                        / len(candidate_network_geometry_pairs)
                        if candidate_network_geometry_pairs
                        else 0.0
                    ),
                },
            },
            "n_complete_events": len(events),
            "minimum_rule": (
                "all_required_networks_and_geometries_plus_all_declared_artificial_"
                "gaps_and_at_least_one_natural_gap;no_global_natural_gap_cross_product"
            ),
        }
    census = {
        "manifest_schema": FEASIBILITY_SCHEMA,
        "status": "complete_outcome_blind_census",
        "lattices": census_lattices,
        "selection_uses_outcomes": False,
        "v4_results_read": False,
        "sealed_temperature_records_read": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    census_path = output / "feasibility_census.json"
    _create_once_json(census_path, census)

    identity_fields = [
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
    ]
    lattice_schema = pa.schema(
        [("ordinal", pa.int64())]
        + [
            (
                name,
                pa.int64()
                if name in {"gap_length", "placement", "start_index"}
                else pa.string(),
            )
            for name in identity_fields
        ]
        + [
            (name, pa.float64())
            for name in (
                "analysis_weight",
                "geometry_weight",
                "network_weight",
                "gap_weight",
                "event_weight",
                "model_information_lag_weight",
            )
        ]
    )
    ledger_schema = pa.schema(
        [
            ("ordinal", pa.int64()),
            ("item_id", pa.string()),
            ("role", pa.string()),
            ("network_id", pa.string()),
            ("station_id", pa.string()),
            ("pre_score_status", pa.string()),
            ("pre_score_reason", pa.string()),
            ("predictor_eligible", pa.bool_()),
            ("lattice_name", pa.string()),
            ("included", pa.bool_()),
            ("final_reason", pa.string()),
        ]
    )
    predictor_schema = pa.schema(
        [
            (
                name,
                pa.int64()
                if name in {"gap_length", "placement", "start_index"}
                else pa.string(),
            )
            for name in OPERATOR_JOIN_KEYS
        ]
        + [
            (name, pa.float64())
            for name in (
                "predicted_recoverability",
                "gap_length_only",
                "acf_only",
                "donor_r2_only",
                "additive_d_over_4_heuristic",
            )
        ]
    )
    sinks = {
        name: _ParquetSink(
            output
            / (
                "analyzable_lattice.parquet"
                if name == "base_primary"
                else f"{name}_lattice.parquet"
            ),
            lattice_schema,
        )
        for name in grids
    }
    ledger_sink = _ParquetSink(output / "exhaustive_item_ledger.parquet", ledger_schema)
    attrition_sink = _ParquetSink(
        output / "data_ineligible_attrition.parquet",
        pa.schema(
            [
                ("item_id", pa.string()),
                ("role", pa.string()),
                ("network_id", pa.string()),
                ("reason", pa.string()),
            ]
        ),
    )
    exclusion_sink = _ParquetSink(
        output / "pre_score_exclusion_attrition.parquet",
        pa.schema(
            [
                ("ordinal", pa.int64()),
                ("item_id", pa.string()),
                ("role", pa.string()),
                ("network_id", pa.string()),
                ("station_id", pa.string()),
                ("lattice_name", pa.string()),
                ("pre_score_status", pa.string()),
                ("reason", pa.string()),
            ]
        ),
    )
    predictor_sink = _ParquetSink(
        output / "operator_univariate_predictions.parquet", predictor_schema
    )

    # Equal geometry -> network -> gap -> event -> grid weights.
    event_weights: dict[str, dict[tuple[Any, ...], tuple[float, ...]]] = {}
    for name, events in eligible_events.items():
        if not lattice_ready[name]:
            event_weights[name] = {}
            continue
        event_weights[name] = _equal_hierarchical_event_weights(
            events, grid_size=len(grids[name])
        )

    try:
        next_ordinal = 0
        for raw, audit in zip(
            rows(index_path, index_columns),
            rows(eligibility_path, eligibility_columns),
            strict=True,
        ):
            source = json.loads(str(raw["source_item_json"]))
            lag = str(raw["meteorology_lag_days"])
            event = (
                str(source["role"]),
                str(source["network_id"]),
                str(source["target_station"]),
                str(source["geometry"]),
                str(source.get("geometry_id") or ""),
                str(source.get("truth_start_date") or ""),
                str(source.get("observed_missing_start_date") or ""),
                int(source["gap_length"]),
                int(source["placement"]),
                int(source["start_index"]),
            )
            cell = (
                str(source["model"]),
                str(source["information_condition"]),
                str(source["task"]),
                lag,
            )
            predictor_key = (event[1], event[2], event[7])
            predictor = sidecar_lookup.get(predictor_key)
            predictor_ok = predictor is not None and str(predictor["role"]) == event[0]
            lattice_name = next(
                (name for name, grid in grids.items() if cell in grid),
                "outside_frozen_lattices",
            )
            included = (
                lattice_name in grids
                and lattice_ready[lattice_name]
                and event in eligible_events[lattice_name]
            )
            if str(audit["pre_score_status"]) != "complete":
                final_reason = str(audit.get("reason") or audit["pre_score_status"])
            elif lattice_name == "outside_frozen_lattices":
                final_reason = "outside_predeclared_base_and_sensitivity_grids"
            elif event[3] not in FIXED_PRIMARY_GEOMETRIES:
                final_reason = "geometry_outside_fixed_primary_roster"
            elif not predictor_ok:
                final_reason = "train_only_predictor_unavailable_or_role_mismatch"
            elif not lattice_ready[lattice_name]:
                final_reason = "lattice_blocked_insufficient_fixed_roster_support"
            elif event not in eligible_events[lattice_name]:
                final_reason = "event_missing_one_or_more_frozen_grid_cells"
            else:
                final_reason = "included"
            ledger_sink.append(
                {
                    "ordinal": int(raw["ordinal"]),
                    "item_id": str(raw["item_id"]),
                    "role": event[0],
                    "network_id": event[1],
                    "station_id": event[2],
                    "pre_score_status": str(audit["pre_score_status"]),
                    "pre_score_reason": str(audit.get("reason") or ""),
                    "predictor_eligible": predictor_ok,
                    "lattice_name": lattice_name,
                    "included": included,
                    "final_reason": final_reason,
                }
            )
            if not included:
                exclusion_sink.append(
                    {
                        "ordinal": int(raw["ordinal"]),
                        "item_id": str(raw["item_id"]),
                        "role": event[0],
                        "network_id": event[1],
                        "station_id": event[2],
                        "lattice_name": lattice_name,
                        "pre_score_status": str(audit["pre_score_status"]),
                        "reason": final_reason,
                    }
                )
            if str(audit["pre_score_status"]) == "data_ineligible":
                attrition_sink.append(
                    {
                        "item_id": str(raw["item_id"]),
                        "role": event[0],
                        "network_id": event[1],
                        "reason": str(audit.get("reason") or "data_ineligible"),
                    }
                )
            if included:
                geometry_w, network_w, gap_w, event_w, grid_w, analysis_w = (
                    event_weights[lattice_name][event]
                )
                identity = {
                    "item_id": str(raw["item_id"]),
                    "role": event[0],
                    "network_id": event[1],
                    "station_id": event[2],
                    "geometry": event[3],
                    "geometry_id": event[4],
                    "truth_start_date": event[5],
                    "observed_missing_start_date": event[6],
                    "gap_length": event[7],
                    "placement": event[8],
                    "start_index": event[9],
                    "model": cell[0],
                    "information_condition": cell[1],
                    "task": cell[2],
                    "meteorology_lag_days": cell[3],
                }
                sinks[lattice_name].append(
                    {
                        "ordinal": int(raw["ordinal"]),
                        **identity,
                        "analysis_weight": analysis_w,
                        "geometry_weight": geometry_w,
                        "network_weight": network_w,
                        "gap_weight": gap_w,
                        "event_weight": event_w,
                        "model_information_lag_weight": grid_w,
                    }
                )
                if lattice_name == "base_primary":
                    assert predictor is not None
                    predictor_sink.append(
                        {
                            **identity,
                            "predicted_recoverability": float(
                                predictor["predicted_conditional_risk"]
                            ),
                            "gap_length_only": float(predictor["gap_length_only"]),
                            "acf_only": float(predictor["acf_only"]),
                            "donor_r2_only": float(predictor["donor_r2_only"]),
                            "additive_d_over_4_heuristic": float(
                                predictor["additive_d_over_4_heuristic"]
                            ),
                        }
                    )
            next_ordinal += 1
        if next_ordinal != expected_n:
            raise PrimaryAggregationBlocked("second-pass ledger is incomplete")
        lattice_records = {name: sink.close() for name, sink in sinks.items()}
        ledger_record = ledger_sink.close()
        attrition_record = attrition_sink.close()
        exclusion_record = exclusion_sink.close()
        predictor_record = predictor_sink.close()
    except Exception:
        for sink in [
            *sinks.values(),
            ledger_sink,
            attrition_sink,
            exclusion_sink,
            predictor_sink,
        ]:
            sink.abort()
        raise

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
        "fit_scope": "within_each_open_network_first70pct_calendar_years",
        "fit_role": "within_each_open_network_train_window",
        "learned_calibration": False,
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "source_sidecar_manifest_sha256": _sha256_file(predictor_manifest_file),
        "source_sidecar_table_sha256": _sha256_file(sidecar_path),
        "source_sidecar_fit_role_note": sidecar_manifest.get("fit_role_note"),
        "predictions_path": predictor_record["path"],
        "predictions_sha256": predictor_record["sha256"],
        "n_prediction_rows": predictor_record["n_rows"],
    }
    predictor_output_manifest = output / "operator_predictor_manifest.json"
    _create_once_json(predictor_output_manifest, predictor_manifest)
    base_record = lattice_records["base_primary"]
    n_analyzable_networks = len(
        {event[1] for event in eligible_events["base_primary"]}
    )
    manifest = {
        "manifest_schema": LATTICE_FREEZE_SCHEMA,
        "status": (
            "frozen_before_v4_scoring"
            if lattice_ready["base_primary"]
            else "blocked_base_lattice_insufficient_pre_score_support"
        ),
        "index_draft_manifest_path": str(workload_path),
        "index_draft_manifest_sha256": _sha256_file(workload_path),
        "workload_manifest_path": str(workload_path),
        "workload_manifest_sha256": _sha256_file(workload_path),
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "item_index": {
            "path": str(index_path),
            "sha256": _sha256_file(index_path),
            "n_rows": expected_n,
        },
        "pre_score_eligibility_manifest_sha256": _sha256_file(
            eligibility_manifest_file
        ),
        "pre_score_eligibility_table_sha256": _sha256_file(eligibility_path),
        "train_only_sidecar_manifest_sha256": _sha256_file(predictor_manifest_file),
        "train_only_sidecar_table_sha256": _sha256_file(sidecar_path),
        "base_primary_grid": [list(value) for value in BASE_PRIMARY_GRID],
        "base_primary_grid_sha256": _canonical_sha(BASE_PRIMARY_GRID),
        "sensitivity_grids": {
            key: [list(value) for value in grid]
            for key, grid in SENSITIVITY_GRIDS.items()
        },
        "weight_contract": {
            "hierarchy": [
                "geometry",
                "network",
                "gap",
                "event",
                "model_information_lag",
            ],
            "each_parent_mass": "equal",
            "product_column": "analysis_weight",
        },
        "feasibility_census": {
            "path": census_path.name,
            "sha256": _sha256_file(census_path),
        },
        "exhaustive_item_ledger": ledger_record,
        "analyzable_lattice": base_record,
        "sensitivity_lattices": {
            key.removeprefix("sensitivity_"): value
            for key, value in lattice_records.items()
            if key.startswith("sensitivity_")
        },
        "data_ineligible_attrition": attrition_record,
        "pre_score_exclusion_attrition": exclusion_record,
        "operator_predictor_manifest": {
            "path": predictor_output_manifest.name,
            "sha256": _sha256_file(predictor_output_manifest),
        },
        "operator_predictor_table": predictor_record,
        "n_analyzable_events": len(eligible_events["base_primary"])
        if lattice_ready["base_primary"]
        else 0,
        "n_analyzable_items": base_record["n_rows"],
        "n_data_ineligible_items": attrition_record["n_rows"],
        "n_pre_score_excluded_items": exclusion_record["n_rows"],
        "frozen_roster_may_shrink_after_scoring": False,
        "execution_allowed": lattice_ready["base_primary"],
        "network_inference_status": (
            "eligible_for_network_interval_after_scoring"
            if n_analyzable_networks >= NETWORK_INTERVAL_FLOOR
            else "withheld_n_lt_100_network_interval"
        ),
        "network_interval_reported": False,
        "evidence_blockers": (
            []
            if n_analyzable_networks >= NETWORK_INTERVAL_FLOOR
            else ["n_analyzable_networks_lt_100"]
        ),
        "selection_uses_outcomes": False,
        "v4_results_read": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    _create_once_json(output / "lattice_freeze_manifest.json", manifest)
    readiness = {
        "manifest_schema": READINESS_SCHEMA,
        "status": manifest["status"],
        "blockers": (
            []
            if manifest["execution_allowed"]
            else ["base_lattice_insufficient_pre_score_support"]
        ),
        "analyzable_lattice_frozen": manifest["execution_allowed"],
        "lattice_freeze_manifest_sha256": _sha256_file(
            output / "lattice_freeze_manifest.json"
        ),
        "execution_allowed": manifest["execution_allowed"],
        "evidence_blockers": manifest["evidence_blockers"],
        "v4_results_read": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    _atomic_json(output / "readiness_manifest.json", readiness)
    return manifest


def create_pre_score_freeze_bundle(
    *,
    index_draft_manifest_path: str | Path,
    eligibility_manifest_path: str | Path,
    lattice_freeze_manifest_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Create the one object the final workload and every chunk must bind."""

    draft_path = Path(index_draft_manifest_path).resolve()
    eligibility_path = Path(eligibility_manifest_path).resolve()
    lattice_path = Path(lattice_freeze_manifest_path).resolve()
    output = Path(output_path).resolve()
    for path in (draft_path, eligibility_path, lattice_path, output):
        _assert_open(path)
    draft = _read_json(draft_path)
    eligibility = _read_json(eligibility_path)
    lattice = _read_json(lattice_path)
    if draft.get("manifest_schema") != V4_INDEX_DRAFT_SCHEMA:
        raise PrimaryAggregationBlocked("pre-score bundle requires an index draft")
    index_record = draft.get("item_index") or {}
    if (
        eligibility.get("workload_manifest_sha256") != _sha256_file(draft_path)
        or lattice.get("index_draft_manifest_sha256") != _sha256_file(draft_path)
        or lattice.get("pre_score_eligibility_manifest_sha256")
        != _sha256_file(eligibility_path)
        or lattice.get("item_index", {}).get("sha256")
        != index_record.get("file_sha256")
    ):
        raise PrimaryAggregationBlocked(
            "pre-score components do not share one draft identity"
        )
    if (
        lattice.get("manifest_schema") != LATTICE_FREEZE_SCHEMA
        or lattice.get("status") != "frozen_before_v4_scoring"
    ):
        raise PrimaryAggregationBlocked(
            "pre-score bundle requires a ready frozen base lattice"
        )
    sensitivity_records = lattice.get("sensitivity_lattices")
    if not isinstance(sensitivity_records, Mapping) or set(sensitivity_records) != {
        "M",
        "M_H",
    }:
        raise PrimaryAggregationBlocked(
            "pre-score bundle requires exact M and M_H sensitivity lattices"
        )

    def bind(owner: Path, record: Mapping[str, Any]) -> dict[str, Any]:
        path = _artifact_path(owner, str(record.get("path", "")))
        if not path.is_file() or _sha256_file(path) != record.get("sha256"):
            raise PrimaryAggregationBlocked("pre-score bundle artifact SHA mismatch")
        return {**dict(record), "path": str(path.relative_to(output.parent))}

    eligibility_table = bind(eligibility_path, eligibility["eligibility_table"])
    census = bind(lattice_path, lattice["feasibility_census"])
    census_value = _read_json(
        _artifact_path(lattice_path, lattice["feasibility_census"]["path"])
    )
    ledger = bind(lattice_path, lattice["exhaustive_item_ledger"])
    exclusion_attrition = bind(
        lattice_path, lattice["pre_score_exclusion_attrition"]
    )
    predictor_table = bind(lattice_path, lattice["operator_predictor_table"])
    predictor_manifest = bind(lattice_path, lattice["operator_predictor_manifest"])
    base_lattice = bind(lattice_path, lattice["analyzable_lattice"])
    sensitivities = {
        key: bind(lattice_path, record)
        for key, record in sensitivity_records.items()
    }
    census_lattices = census_value.get("lattices") or {}
    if set(census_lattices) != {"base_primary", "sensitivity_M", "sensitivity_M_H"}:
        raise PrimaryAggregationBlocked("pre-score census lattice roster is incomplete")
    allowed_sensitivity_statuses = {
        "ready",
        "blocked_insufficient_pre_score_support",
    }
    if (
        any(not isinstance(value, Mapping) for value in census_lattices.values())
        or census_lattices["base_primary"].get("status") != "ready"
        or any(
            census_lattices[f"sensitivity_{key}"].get("status")
            not in allowed_sensitivity_statuses
            for key in ("M", "M_H")
        )
    ):
        raise PrimaryAggregationBlocked("pre-score census lattice status is invalid")
    bundle = {
        "manifest_schema": V4_PRE_SCORE_FREEZE_SCHEMA,
        "status": "complete_outcome_blind_pre_score_freeze",
        "index_draft_manifest": {
            "path": str(draft_path.relative_to(output.parent)),
            "sha256": _sha256_file(draft_path),
        },
        "index_draft_manifest_sha256": _sha256_file(draft_path),
        "item_index_file_sha256": index_record.get("file_sha256"),
        "eligibility_manifest": {
            "path": str(eligibility_path.relative_to(output.parent)),
            "sha256": _sha256_file(eligibility_path),
        },
        "eligibility_table": eligibility_table,
        "feasibility_census": census,
        "exhaustive_item_ledger": ledger,
        "pre_score_exclusion_attrition": exclusion_attrition,
        "base_lattice_manifest": {
            "path": str(lattice_path.relative_to(output.parent)),
            "sha256": _sha256_file(lattice_path),
        },
        "base_lattice": base_lattice,
        "sensitivity_lattices": sensitivities,
        "predictor_manifest": predictor_manifest,
        "predictor_table": predictor_table,
        "base_lattice_status": lattice.get("status"),
        "sensitivity_lattice_statuses": {
            key: (census_value.get("lattices") or {})
            .get(f"sensitivity_{key}", {})
            .get("status")
            for key in sensitivities
        },
        "selection_uses_outcomes": False,
        "frozen_roster_may_shrink_after_scoring": False,
        "v4_results_read": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _create_once_json(output, bundle)
    return bundle


def bind_complete_v4_primary_results(
    *,
    workload_manifest_path: str | Path,
    aggregation_manifest_path: str | Path,
    item_results_path: str | Path | None = None,
    lattice_freeze_manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Bind complete result bytes to the already-frozen lattice without selection."""

    workload_path = Path(workload_manifest_path).resolve()
    aggregation_path = Path(aggregation_manifest_path).resolve()
    freeze_path = Path(lattice_freeze_manifest_path).resolve()
    output = Path(output_dir).resolve()
    for path in (workload_path, aggregation_path, freeze_path, output):
        _assert_open(path)
    workload = _read_json(workload_path)
    aggregation = _read_json(aggregation_path)
    freeze = _read_json(freeze_path)
    if (
        freeze.get("manifest_schema") != LATTICE_FREEZE_SCHEMA
        or freeze.get("status") != "frozen_before_v4_scoring"
    ):
        raise PrimaryAggregationBlocked(
            "primary results lack a valid pre-score lattice freeze"
        )
    if freeze.get("workload_manifest_sha256") != _sha256_file(workload_path):
        pre_score = workload.get("pre_score_freeze") or {}
        base_manifest = (pre_score.get("artifacts") or {}).get(
            "base_lattice_manifest"
        ) or {}
        if base_manifest.get("sha256") != _sha256_file(freeze_path):
            raise PrimaryAggregationBlocked(
                "lattice freeze/final workload binding mismatch"
            )
    code_inventory_sha = str(
        (workload.get("execution_code_inventory") or {}).get("inventory_sha256", "")
    )
    execution_head = str(aggregation.get("execution_head_commit", ""))
    if len(code_inventory_sha) != 64 or len(execution_head) not in {40, 64}:
        raise PrimaryAggregationBlocked("complete aggregation lacks code provenance")
    required_aggregation = {
        "manifest_schema": V4_AGGREGATION_SCHEMA,
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "all_executions_successful": True,
        "workload_manifest_sha256": _sha256_file(workload_path),
        "work_item_identity_sha256": workload.get("work_item_identity_sha256"),
        "pre_score_freeze_sha256": (workload.get("pre_score_freeze") or {}).get(
            "sha256"
        ),
        "execution_code_inventory_sha256": code_inventory_sha,
        "sealed_temperature_records_read": False,
    }
    for key, expected in required_aggregation.items():
        if aggregation.get(key) != expected:
            raise PrimaryAggregationBlocked(f"complete aggregation mismatch for {key}")
    merged_record = aggregation.get("merged_item_results")
    if not isinstance(merged_record, Mapping):
        raise PrimaryAggregationBlocked(
            "aggregation omits its create-once merged results"
        )
    results_path = _artifact_path(aggregation_path, str(merged_record.get("path", "")))
    _assert_open(results_path)
    if (
        not results_path.is_file()
        or _sha256_file(results_path) != merged_record.get("sha256")
        or int(merged_record.get("n_rows", -1)) != int(workload.get("n_work_items", -1))
    ):
        raise PrimaryAggregationBlocked("aggregator-bound merged results differ")
    if (
        item_results_path is not None
        and Path(item_results_path).resolve() != results_path
    ):
        raise PrimaryAggregationBlocked(
            "binder refuses an item-results path not bound by aggregation"
        )
    results = pd.read_parquet(results_path)
    n_items = int(workload.get("n_work_items", -1))
    result_columns = sorted(str(column) for column in results.columns)
    merged_digest = hashlib.sha256()
    _update_logical_result_digest(merged_digest, results, result_columns)
    index_record = workload.get("item_index") or {}
    index_path = _artifact_path(workload_path, str(index_record.get("path", "")))
    chunk_records = aggregation.get("chunk_manifest_records") or []
    if not chunk_records or int(aggregation.get("n_chunks", -1)) != len(chunk_records):
        raise PrimaryAggregationBlocked("aggregation lacks exhaustive chunk provenance")
    chunk_digest = hashlib.sha256()
    next_start = 0
    for chunk in chunk_records:
        path = Path(str(chunk.get("path", ""))).resolve()
        if not path.is_file() or _sha256_file(path) != chunk.get("sha256"):
            raise PrimaryAggregationBlocked("aggregation chunk provenance drifted")
        chunk_manifest = _read_json(path)
        start = int(chunk_manifest.get("start_ordinal", -1))
        end = int(chunk_manifest.get("end_ordinal_exclusive", -1))
        if start != next_start or end <= start:
            raise PrimaryAggregationBlocked(
                "aggregation chunk provenance is not contiguous"
            )
        if (
            chunk_manifest.get("workload_manifest_sha256")
            != _sha256_file(workload_path)
            or chunk_manifest.get("pre_score_freeze_sha256")
            != (workload.get("pre_score_freeze") or {}).get("sha256")
            or chunk_manifest.get("execution_head_commit")
            != aggregation.get("execution_head_commit")
            or chunk_manifest.get("execution_code_inventory_sha256")
            != (workload.get("execution_code_inventory") or {}).get(
                "inventory_sha256"
            )
            or chunk.get("start_ordinal") != start
            or chunk.get("end_ordinal_exclusive") != end
            or chunk.get("results_sha256") != chunk_manifest.get("results_sha256")
        ):
            raise PrimaryAggregationBlocked("aggregation chunk binding drifted")
        chunk_results = path.parent / str(chunk_manifest.get("results_path", ""))
        if not chunk_results.is_file() or _sha256_file(chunk_results) != chunk.get(
            "results_sha256"
        ):
            raise PrimaryAggregationBlocked("aggregation chunk result bytes drifted")
        frame = (
            pd.read_parquet(chunk_results)
            if chunk_manifest.get("results_format") == "parquet"
            else pd.read_csv(chunk_results)
        )
        if len(frame) != end - start:
            raise PrimaryAggregationBlocked("aggregation chunk result count drifted")
        _assert_full_row_identities(frame, _expected_identities(index_path, start, end))
        _update_logical_result_digest(chunk_digest, frame, result_columns)
        next_start = end
    if len(results) != n_items or _stream_sha(results) != workload.get(
        "work_item_identity_sha256"
    ):
        raise PrimaryAggregationBlocked(
            "item results do not match the complete v4 stream"
        )
    statuses = results["status"].astype(str)
    if not set(statuses).issubset(TERMINAL_RESULT_STATUSES):
        raise PrimaryAggregationBlocked("item results contain failed/nonterminal rows")
    if results["sealed_temperature_records_read"].map(bool).any():
        raise PrimaryAggregationBlocked("item results attest sealed access")
    if next_start != n_items:
        raise PrimaryAggregationBlocked("aggregation chunk provenance is incomplete")
    if chunk_digest.hexdigest() != merged_digest.hexdigest():
        raise PrimaryAggregationBlocked(
            "aggregator-bound merged results differ from their chunks"
        )
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
        columns={
            "target_station": "station_id",
            "achieved_skill": "observed_achieved_skill",
        }
    )[[*PRIMARY_IDENTITY_COLUMNS, "observed_achieved_skill"]]
    primary["meteorology_lag_days"] = pd.to_numeric(
        primary["meteorology_lag_days"], errors="coerce"
    ).map(lambda value: "none" if pd.isna(value) else str(int(value)))
    observed = pd.to_numeric(primary["observed_achieved_skill"], errors="coerce")
    if not np.isfinite(observed).all():
        raise PrimaryAggregationBlocked("primary y contains a nonfinite achieved skill")
    primary_path = output / "primary_y.parquet"
    output.mkdir(parents=True, exist_ok=True)
    _create_once_table(primary_path, primary)

    def frozen_record(name: str) -> dict[str, Any]:
        record = freeze[name]
        return {**record, "path": str(_artifact_path(freeze_path, str(record["path"])))}

    complete_excluded = results.loc[
        statuses.eq("complete") & ~results["item_id"].astype(str).isin(lattice_ids),
        ["item_id", "role", "network_id"],
    ].copy()
    complete_excluded["reason"] = "outside_outcome_blind_frozen_common_lattice"
    excluded_path = output / "complete_item_outcome_blind_attrition.parquet"
    _create_once_table(excluded_path, complete_excluded)
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
        "item_results": {
            "path": str(results_path),
            "format": "parquet",
            "sha256": _sha256_file(results_path),
            "n_rows": len(results),
        },
        "primary_y_table": {
            "path": primary_path.name,
            "format": "parquet",
            "sha256": _sha256_file(primary_path),
            "n_rows": len(primary),
        },
        "analyzable_lattice": frozen_record("analyzable_lattice"),
        "data_ineligible_attrition": frozen_record("data_ineligible_attrition"),
        "operator_predictor_manifest": frozen_record("operator_predictor_manifest"),
        "operator_predictor_table": frozen_record("operator_predictor_table"),
        "complete_item_outcome_blind_attrition": {
            "path": excluded_path.name,
            "format": "parquet",
            "sha256": _sha256_file(excluded_path),
            "n_rows": len(complete_excluded),
        },
        "lattice_freeze_manifest_sha256": _sha256_file(freeze_path),
        "aggregation_manifest_sha256": _sha256_file(aggregation_path),
        "achieved_skill_used_for_selection": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    _create_once_json(output / "post_t2_input_binding.json", binding)
    return binding


__all__ = [
    "BASE_PRIMARY_GRID",
    "ELIGIBILITY_AUDIT_SCHEMA",
    "LATTICE_FREEZE_SCHEMA",
    "PRIMARY_COMMON_GRID",
    "SENSITIVITY_GRIDS",
    "PrimaryAggregationBlocked",
    "bind_complete_v4_primary_results",
    "create_pre_score_freeze_bundle",
    "freeze_v4_analyzable_lattice",
]
