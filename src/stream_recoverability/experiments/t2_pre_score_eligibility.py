"""Stream the outcome-blind, pre-score eligibility audit for T2 v4.

Temperature values are outside this module's read set.  Open-QC files supply
only their SHA-bound station header and date labels.  Frozen ``start_index``
values are reused as-is.  Exact extended-cell eligibility is computed from
provider-QC auxiliary availability on train and gap dates, never from a model
fit, prediction, gap truth, or achieved skill.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from stream_recoverability.data.t2_information_adapters import (
    HYDRAULICS_VARIABLES,
    METEOROLOGY_VARIABLES,
    _provider_eligible,
)
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    NETWORK_SCHEMA_VERSION,
    PARSER_CONTRACT_VERSION,
    TERMINAL_STATUSES,
)

from .t2_information_runner_integration import V2_AUXILIARY_ROOT
from .t2_primary_aggregation_v2 import (
    ELIGIBILITY_AUDIT_SCHEMA,
    PrimaryAggregationBlocked,
    _artifact_path,
    _assert_open,
    _atomic_json,
    _canonical_sha,
    _create_once_json,
    _read_json,
    _sha256_file,
    _structural_status,
)
from .t2_recovery_benchmark import (
    EXTENDED_INFORMATION_CONDITIONS,
    MIN_TRAIN_OBSERVATIONS,
    OpenNetwork,
    _year_split,
    discover_failure_closure_networks,
)
from .t2_workload_v4 import (
    V4_INDEX_DRAFT_SCHEMA,
    V4_ITEM_INDEX_SCHEMA,
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)

ELIGIBILITY_BUILDER_SCHEMA = "t2_v91_v4_pre_score_eligibility_builder_v1"
ELIGIBILITY_TABLE_NAME = "eligibility.parquet"
STREAM_BATCH_ROWS = 20_000
VARIABLE_ROSTER = METEOROLOGY_VARIABLES + HYDRAULICS_VARIABLES


@dataclass(frozen=True)
class NetworkAvailability:
    """Boolean auxiliary availability aligned to locked open-QC date labels."""

    network_id: str
    role: str
    dates: pd.DatetimeIndex
    site_ids: tuple[str, ...]
    # lag -> feature x date. Feature order is site-major VARIABLE_ROSTER.
    available_by_lag: Mapping[int, np.ndarray]
    train_mask: np.ndarray
    provenance: Mapping[str, Any]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        return False
    return True


def _artifact(
    repo: Path, directory: Path, manifest: Mapping[str, Any], key: str
) -> tuple[Path, str]:
    record = (manifest.get("artifacts") or {}).get(key)
    if not isinstance(record, Mapping):
        raise PrimaryAggregationBlocked(f"v2.3 auxiliary manifest lacks {key}")
    path = (repo / str(record.get("path", ""))).resolve()
    if not _inside(path, directory):
        raise PrimaryAggregationBlocked(f"v2.3 auxiliary {key} escaped its network")
    sha = str(record.get("sha256", ""))
    if len(sha) != 64 or _sha256_file(path) != sha:
        raise PrimaryAggregationBlocked(f"v2.3 auxiliary {key} SHA mismatch")
    return path, sha


def _date_header_only(
    network: OpenNetwork, repo: Path
) -> tuple[pd.DatetimeIndex, tuple[str, ...]]:
    path = (repo / network.wide_path).resolve()
    _assert_open(path)
    if not path.is_file() or _sha256_file(path) != network.wide_sha256:
        raise PrimaryAggregationBlocked("open-QC date/header source SHA mismatch")
    header = pd.read_csv(path, nrows=0)
    if not len(header.columns) or str(header.columns[0]) != "date":
        raise PrimaryAggregationBlocked("open-QC panel lacks its locked date column")
    sites = tuple(str(value) for value in header.columns[1:])
    if not sites or len(sites) != len(set(sites)):
        raise PrimaryAggregationBlocked("open-QC station header is empty or duplicated")
    # Projection is deliberate: no temperature column or its NA mask is parsed.
    date_frame = pd.read_csv(path, usecols=["date"], dtype={"date": "string"})
    dates = pd.DatetimeIndex(pd.to_datetime(date_frame["date"], errors="raise"))
    if (
        dates.tz is not None
        or dates.has_duplicates
        or not dates.is_monotonic_increasing
        or not dates.equals(dates.normalize())
        or len(dates) != network.n_days
        or len(sites) != network.n_stations
    ):
        raise PrimaryAggregationBlocked("open-QC date/header contract mismatch")
    return dates, sites


def _availability_matrices(
    daily: pd.DataFrame,
    *,
    dates: pd.DatetimeIndex,
    sites: Sequence[str],
) -> dict[int, np.ndarray]:
    features = [(site, variable) for site in sites for variable in VARIABLE_ROSTER]
    feature_index = {value: index for index, value in enumerate(features)}
    date_index = {value: index for index, value in enumerate(dates)}
    matrices = {
        lag: np.zeros((len(features), len(dates)), dtype=bool) for lag in (-1, 0, 1)
    }
    if daily.duplicated(["date", "site_id", "variable"]).any():
        # Match the formal adapter, which rejects duplicates before QC filtering.
        raise PrimaryAggregationBlocked("v2.3 auxiliary has duplicate features")
    eligible, _ = _provider_eligible(daily)
    selected = daily.loc[eligible, ["date", "site_id", "variable"]].copy()
    selected["date"] = pd.to_datetime(selected["date"], errors="raise")
    for row in selected.itertuples(index=False):
        variable = str(row.variable)
        feature_position = feature_index.get((str(row.site_id), variable))
        if feature_position is None:
            continue
        source_date = pd.Timestamp(row.date)
        for lag, matrix in matrices.items():
            aligned = source_date - pd.Timedelta(
                days=lag if variable in METEOROLOGY_VARIABLES else 0
            )
            date_position = date_index.get(aligned)
            if date_position is not None:
                matrix[feature_position, date_position] = True
    return matrices


def _load_network_availability(
    repo: Path,
    network: OpenNetwork,
    binding: Mapping[str, Any],
    *,
    split_sha256: str,
) -> NetworkAvailability:
    dates, sites = _date_header_only(network, repo)
    directory = (
        repo / V2_AUXILIARY_ROOT / network.role / "networks" / network.network_id
    ).resolve()
    manifest_path = directory / "network_manifest.json"
    if not _inside(manifest_path, directory):
        raise PrimaryAggregationBlocked("v2.3 auxiliary manifest is absent or unsafe")
    manifest = _read_json(manifest_path)
    required_manifest = {
        "manifest_schema": NETWORK_SCHEMA_VERSION,
        "parser_contract_version": PARSER_CONTRACT_VERSION,
        "acquisition_terminal": True,
        "network_id": network.network_id,
        "role": network.role,
        "split_sha256": split_sha256,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "v1_ogc_root_read_or_mutated": False,
    }
    for key, expected in required_manifest.items():
        if manifest.get(key) != expected:
            raise PrimaryAggregationBlocked(f"v2.3 auxiliary mismatch for {key}")
    required_binding = {
        "network_id": network.network_id,
        "role": network.role,
        "network_manifest_schema": NETWORK_SCHEMA_VERSION,
        "network_plan_sha256": manifest.get("network_plan_sha256"),
        "materialization_status": manifest.get("status"),
    }
    for key, expected in required_binding.items():
        if binding.get(key) != expected:
            raise PrimaryAggregationBlocked(f"v2.3 workload binding mismatch for {key}")
    if manifest.get("status") not in TERMINAL_STATUSES:
        raise PrimaryAggregationBlocked("v2.3 auxiliary status is not terminal")
    manifest_sites = tuple(str(value) for value in (manifest.get("site_ids") or ()))
    if len(manifest_sites) != len(set(manifest_sites)) or set(manifest_sites) != set(
        sites
    ):
        raise PrimaryAggregationBlocked(
            "v2.3 auxiliary station roster differs from open QC"
        )
    if _sha256_file(manifest_path) != binding.get("network_manifest_sha256"):
        raise PrimaryAggregationBlocked(
            "v2.3 manifest differs from v4 workload binding"
        )
    daily_path, daily_sha = _artifact(repo, directory, manifest, "daily_long_auxiliary")
    coverage_path, coverage_sha = _artifact(repo, directory, manifest, "coverage")
    schema_path, schema_sha = _artifact(repo, directory, manifest, "adapter_schema")
    expected_artifacts = {
        "daily_long_sha256": daily_sha,
        "coverage_sha256": coverage_sha,
        "adapter_schema_sha256": schema_sha,
    }
    for key, expected in expected_artifacts.items():
        if binding.get(key) != expected:
            raise PrimaryAggregationBlocked(
                f"v2.3 workload artifact mismatch for {key}"
            )
    schema = _read_json(schema_path)
    if (
        schema.get("acquisition_schema") != NETWORK_SCHEMA_VERSION
        or schema.get("parser_contract_version") != PARSER_CONTRACT_VERSION
        or tuple((schema.get("variables") or {}).get("M") or ())
        != METEOROLOGY_VARIABLES
        or tuple((schema.get("variables") or {}).get("H") or ()) != HYDRAULICS_VARIABLES
    ):
        raise PrimaryAggregationBlocked("v2.3 adapter schema mismatch")
    coverage = pd.read_csv(coverage_path, dtype={"site_id": "string"})
    required_coverage = {
        "network_id",
        "role",
        "site_id",
        "variable",
        "source_status",
        "eligible_coverage",
    }
    if (
        not required_coverage.issubset(coverage.columns)
        or set(coverage["network_id"].astype(str)) != {network.network_id}
        or set(coverage["role"].astype(str)) != {network.role}
        or not set(coverage["site_id"].astype(str)).issubset(set(sites))
    ):
        raise PrimaryAggregationBlocked("v2.3 coverage catalog mismatch")
    coverage_pairs = coverage[["site_id", "variable"]].astype(str)
    expected_pairs = {
        (site, variable) for site in sites for variable in VARIABLE_ROSTER
    }
    if (
        coverage_pairs.duplicated().any()
        or set(map(tuple, coverage_pairs.to_numpy())) != expected_pairs
    ):
        raise PrimaryAggregationBlocked("v2.3 coverage catalog is not roster-complete")
    projected_columns = [
        "date",
        "site_id",
        "variable",
        "value",
        "source",
        "natural_observed",
        "qc_status",
        "approval_status",
        "quality_approved",
    ]
    daily = pd.read_parquet(daily_path, columns=projected_columns)
    if not set(daily["site_id"].astype(str)).issubset(set(sites)):
        raise PrimaryAggregationBlocked("v2.3 daily table contains a foreign station")
    available = _availability_matrices(daily, dates=dates, sites=sites)
    train, _ = _year_split(dates)
    return NetworkAvailability(
        network_id=network.network_id,
        role=network.role,
        dates=dates,
        site_ids=sites,
        available_by_lag=available,
        train_mask=np.asarray(train, dtype=bool),
        provenance={
            "open_qc_wide_path": network.wide_path,
            "open_qc_wide_sha256": network.wide_sha256,
            "network_manifest_path": str(manifest_path.relative_to(repo)),
            "network_manifest_sha256": _sha256_file(manifest_path),
            "daily_long_sha256": daily_sha,
            "coverage_sha256": coverage_sha,
            "adapter_schema_sha256": schema_sha,
        },
    )


def _extended_coverage_status(
    source: Mapping[str, Any], lag: int, availability: NetworkAvailability
) -> tuple[str, str]:
    start = int(source["start_index"])
    length = int(source["gap_length"])
    stop = start + length
    if start < 0 or stop > len(availability.dates):
        return "data_ineligible", "frozen_gap_outside_open_qc_date_index"
    truth_start = str(source.get("truth_start_date") or "")
    if truth_start and pd.Timestamp(truth_start) != availability.dates[start]:
        return "data_ineligible", "frozen_start_index_date_binding_mismatch"
    variables = METEOROLOGY_VARIABLES + (
        HYDRAULICS_VARIABLES
        if source["information_condition"] == "B_union_D_union_M_union_H"
        else ()
    )
    variable_positions = [VARIABLE_ROSTER.index(variable) for variable in variables]
    feature_positions = [
        site * len(VARIABLE_ROSTER) + variable
        for site in range(len(availability.site_ids))
        for variable in variable_positions
    ]
    matrix = availability.available_by_lag[int(lag)][feature_positions]
    train = availability.train_mask.copy()
    train[start:stop] = False
    train_counts = matrix[:, train].sum(axis=1)
    if bool((train_counts < MIN_TRAIN_OBSERVATIONS).any()):
        return "data_ineligible", "requested_auxiliary_train_coverage_lt_365_days"
    if not bool(matrix[:, start:stop].all()):
        return "data_ineligible", "requested_auxiliary_gap_coverage_incomplete"
    return "complete", ""


def _status_for_row(
    source: Mapping[str, Any], lag_label: str, availability: NetworkAvailability | None
) -> tuple[str, str]:
    structural = _structural_status(source, lag_label)
    if structural != "complete":
        reason = {
            "reference_complete": "reference_cell_ignores_available_information",
            "structural_not_applicable": "frozen_model_information_cell_not_applicable",
            "data_ineligible": "frozen_start_index_is_data_ineligible",
        }[structural]
        return structural, reason
    if str(source["information_condition"]) not in EXTENDED_INFORMATION_CONDITIONS:
        return "complete", ""
    if availability is None:
        raise PrimaryAggregationBlocked("extended item lacks v2.3 network availability")
    return _extended_coverage_status(source, int(lag_label), availability)


def _existing(
    output: Path, required_binding: Mapping[str, Any]
) -> dict[str, Any] | None:
    manifest_path = output / "manifest.json"
    table_path = output / ELIGIBILITY_TABLE_NAME
    if not manifest_path.exists() and not table_path.exists():
        return None
    if table_path.is_file() and not manifest_path.exists():
        # Recoverable crash boundary: rebuild to a temporary file and require
        # exact byte equality before sealing the missing manifest.
        return None
    if not manifest_path.is_file() or not table_path.is_file():
        raise PrimaryAggregationBlocked("partial pre-score eligibility freeze exists")
    manifest = _read_json(manifest_path)
    for key, expected in required_binding.items():
        if manifest.get(key) != expected:
            raise PrimaryAggregationBlocked(
                f"existing eligibility binding mismatch: {key}"
            )
    record = manifest.get("eligibility_table") or {}
    if _sha256_file(table_path) != record.get("sha256"):
        raise PrimaryAggregationBlocked("existing eligibility table SHA mismatch")
    return manifest


def _blocked(output: Path, blockers: list[str]) -> dict[str, Any]:
    manifest = {
        "manifest_schema": ELIGIBILITY_BUILDER_SCHEMA,
        "status": "blocked_waiting_for_formal_v4_item_index",
        "blockers": blockers,
        "eligibility_table_written": False,
        "v4_results_read": False,
        "achieved_skill_read": False,
        "open_qc_temperature_value_columns_read": [],
        "gap_truth_values_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    _atomic_json(output / "readiness_manifest.json", manifest)
    return manifest


def build_pre_score_eligibility(
    *,
    repo_root: str | Path,
    workload_manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Stream all frozen items to a create-once pre-score eligibility table."""

    repo = Path(repo_root).resolve()
    workload_path = Path(workload_manifest_path).resolve()
    output = Path(output_dir).resolve()
    for path in (repo, workload_path, output):
        _assert_open(path)
    if not workload_path.is_file():
        return _blocked(output, ["formal_v4_workload_absent", "v4_item_index_absent"])
    workload = _read_json(workload_path)
    if (
        workload.get("manifest_schema")
        not in {V4_INDEX_DRAFT_SCHEMA, V4_WORKLOAD_SCHEMA}
        or workload.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
        or workload.get("sealed_paths_traversed") is not False
        or workload.get("sealed_temperature_records_read") is not False
    ):
        raise PrimaryAggregationBlocked(
            "pre-score builder requires the formal open-only v4 workload"
        )
    record = workload.get("item_index")
    if (
        not isinstance(record, Mapping)
        or record.get("manifest_schema") != V4_ITEM_INDEX_SCHEMA
    ):
        return _blocked(output, ["v4_item_index_metadata_absent_or_invalid"])
    index_path = _artifact_path(workload_path, str(record.get("path", "")))
    if not index_path.is_file():
        return _blocked(output, ["v4_item_index_absent"])
    if _sha256_file(index_path) != record.get("file_sha256"):
        raise PrimaryAggregationBlocked("pre-score v4 item index SHA mismatch")
    networks, _ = discover_failure_closure_networks(repo)
    input_map = {network.network_id: network.wide_sha256 for network in networks}
    if input_map != workload.get("input_sha256_by_network") or _canonical_sha(
        input_map
    ) != workload.get("input_sha256_by_network_sha256"):
        raise PrimaryAggregationBlocked(
            "open-QC inventory differs from the v4 workload"
        )
    network_lookup = {network.network_id: network for network in networks}
    bindings = workload.get("auxiliary_network_bindings") or {}
    if set(network_lookup) != set(bindings):
        raise PrimaryAggregationBlocked(
            "v2.3 binding roster differs from open-QC inventory"
        )
    coverage_map = {
        network: str((binding or {}).get("coverage_sha256", ""))
        for network, binding in bindings.items()
    }
    required_binding = {
        "manifest_schema": ELIGIBILITY_AUDIT_SCHEMA,
        "builder_schema": ELIGIBILITY_BUILDER_SCHEMA,
        "workload_manifest_sha256": _sha256_file(workload_path),
        "item_index_file_sha256": _sha256_file(index_path),
        "input_qc_inventory_sha256": workload.get("input_sha256_by_network_sha256"),
        "auxiliary_coverage_bindings_sha256": _canonical_sha(coverage_map),
        "placements_read_from_frozen_item_index": True,
        "selection_uses_outcomes": False,
        "achieved_skill_read": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    prior = _existing(output, required_binding)
    if prior is not None:
        return prior

    split_sha = str(
        (workload.get("input_inventory") or {}).get("catalog_split_sha256", "")
    )
    if len(split_sha) != 64:
        raise PrimaryAggregationBlocked("v4 workload lacks its open-QC split binding")
    availability = {
        network_id: _load_network_availability(
            repo,
            network_lookup[network_id],
            binding,
            split_sha256=split_sha,
        )
        for network_id, binding in sorted(bindings.items())
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".eligibility.", suffix=".parquet.tmp", dir=output
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    writer: pq.ParquetWriter | None = None
    item_digest = hashlib.sha256()
    statuses: Counter[str] = Counter()
    next_ordinal = 0
    try:
        parquet = pq.ParquetFile(index_path)
        required_columns = {
            "ordinal",
            "item_id",
            "network_id",
            "meteorology_lag_days",
            "source_item_json",
        }
        if not required_columns.issubset(parquet.schema_arrow.names):
            raise PrimaryAggregationBlocked("v4 index omits pre-score fields")
        for batch in parquet.iter_batches(
            batch_size=STREAM_BATCH_ROWS, columns=sorted(required_columns)
        ):
            frame = batch.to_pandas()
            output_rows: list[dict[str, str]] = []
            for row in frame.itertuples(index=False):
                ordinal = int(row.ordinal)
                if ordinal != next_ordinal:
                    raise PrimaryAggregationBlocked(
                        "v4 index ordinals are not contiguous"
                    )
                next_ordinal += 1
                item_id = str(row.item_id)
                item_digest.update(item_id.encode())
                item_digest.update(b"\n")
                source = json.loads(str(row.source_item_json))
                if str(source["network_id"]) != str(row.network_id):
                    raise PrimaryAggregationBlocked("v4 index source identity mismatch")
                status, reason = _status_for_row(
                    source,
                    str(row.meteorology_lag_days),
                    availability.get(str(row.network_id)),
                )
                statuses[status] += 1
                output_rows.append(
                    {"item_id": item_id, "pre_score_status": status, "reason": reason}
                )
            table = pa.Table.from_pylist(
                output_rows,
                schema=pa.schema(
                    [
                        ("item_id", pa.string()),
                        ("pre_score_status", pa.string()),
                        ("reason", pa.string()),
                    ]
                ),
            )
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=STREAM_BATCH_ROWS)
        if writer is not None:
            writer.close()
            writer = None
        expected_n = int(workload.get("n_work_items", -1))
        if next_ordinal != expected_n or item_digest.hexdigest() != workload.get(
            "work_item_identity_sha256"
        ):
            raise PrimaryAggregationBlocked(
                "eligibility stream differs from frozen v4 identity"
            )
        table_path = output / ELIGIBILITY_TABLE_NAME
        if table_path.exists():
            if _sha256_file(table_path) != _sha256_file(temporary):
                raise PrimaryAggregationBlocked("orphan eligibility table differs")
        else:
            os.link(temporary, table_path)
            os.chmod(table_path, 0o444)
        manifest = {
            **required_binding,
            "status": "complete_outcome_blind_pre_score_audit",
            "completeness": "complete",
            "expected_item_records": expected_n,
            "observed_item_records": next_ordinal,
            "work_item_identity_sha256": item_digest.hexdigest(),
            "status_counts": dict(sorted(statuses.items())),
            "eligibility_table": {
                "path": ELIGIBILITY_TABLE_NAME,
                "format": "parquet",
                "sha256": _sha256_file(table_path),
                "n_rows": next_ordinal,
            },
            "network_availability_bindings": {
                key: dict(value.provenance)
                for key, value in sorted(availability.items())
            },
            "coverage_rule": {
                "structural_applicability": "derived_from_frozen_item_fields_before_scoring",
                "base_placement": "reuse_frozen_start_index_no_temperature_reopen",
                "extended_train": f"all_requested_station_variable_features_at_least_{MIN_TRAIN_OBSERVATIONS}_finite_provider_qc_days",
                "extended_gap": "all_requested_station_variable_features_finite_every_gap_day",
                "meteorology_alignment": "source_date_equals_target_date_plus_lag_days",
                "hydraulics_alignment": "same_provider_calendar_day_label",
            },
            "open_qc_date_labels_read": True,
            "open_qc_station_header_read": True,
            "open_qc_temperature_value_columns_read": [],
            "open_qc_temperature_na_availability_read": False,
            "open_qc_temperature_csv_bytes_traversed": True,
            "open_qc_excluded_temperature_fields_decoded": False,
            "gap_truth_values_read": False,
            "auxiliary_provider_qc_values_read_for_declared_information_coverage": True,
            "temperature_date_and_roster_classification": "design_metadata_not_recovery_outcome",
            "model_fit_or_prediction_run": False,
            "old_outcomes_read": False,
            "formal_evidence": False,
            "passed": False,
        }
        _create_once_json(output / "manifest.json", manifest)
        return manifest
    finally:
        if writer is not None:
            writer.close()
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "ELIGIBILITY_BUILDER_SCHEMA",
    "NetworkAvailability",
    "build_pre_score_eligibility",
]
