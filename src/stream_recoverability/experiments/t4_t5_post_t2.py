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

INPUT_BINDING_SCHEMA = "t2_v91_v4_post_t2_input_binding_v1"
READINESS_SCHEMA = "t4_t5_v91_post_t2_readiness_v1"
T4_SCHEMA = "t4_v91_natural_counterpart_network_comparison_v1"
T5_SCHEMA = "t5_v91_frozen_pair_primary_y_contrast_v1"
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
        "network_id",
        "station_id",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "model",
        "information_condition",
        "task",
        "observed_achieved_skill",
        "predicted_recoverability",
    }
)
PAIR_COLUMNS = frozenset(
    {
        "regulated_id",
        "control_id",
        "regulated_network_id",
        "control_network_id",
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
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    for key, expected in required_binding.items():
        if binding.get(key) != expected:
            raise PostT2ContractError(f"post-T2 binding mismatch for {key}")
    item_record = binding.get("item_results")
    primary_record = binding.get("primary_y_table")
    if not isinstance(item_record, Mapping) or not isinstance(primary_record, Mapping):
        raise PostT2ContractError("post-T2 binding omits item/primary artifacts")
    _, items = _validate_artifact(binding_file, item_record, name="item results")
    _, primary = _validate_artifact(binding_file, primary_record, name="primary-y table")

    required_items = {
        "ordinal",
        "item_id",
        "network_id",
        "target_station",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "model",
        "information_condition",
        "task",
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
        raise PostT2ContractError("item results are not a complete unique ordinal stream")
    item_stream_sha = _stream_sha(items.assign(ordinal=ordinals.astype(int)))
    if (
        item_stream_sha != workload.get("work_item_identity_sha256")
        or item_stream_sha != binding.get("work_item_identity_sha256")
    ):
        raise PostT2ContractError("item result identity stream SHA-256 mismatch")
    statuses = items["status"].astype(str)
    unknown = sorted(set(statuses).difference(TERMINAL_STATUSES))
    if unknown:
        raise PostT2ContractError(f"item results contain non-success status: {unknown}")
    if items["sealed_temperature_records_read"].map(bool).any():
        raise PostT2ContractError("item results attest sealed temperature access")
    declared_counts = {str(k): int(v) for k, v in (binding.get("status_counts") or {}).items()}
    if declared_counts != dict(sorted(Counter(statuses).items())):
        raise PostT2ContractError("item status counts do not match binding")

    missing = sorted(PRIMARY_COLUMNS.difference(primary.columns))
    if missing:
        raise PostT2ContractError(f"primary-y table omits columns: {missing}")
    if primary["item_id"].astype(str).duplicated().any():
        raise PostT2ContractError("primary-y item IDs are not unique")
    complete = items.loc[statuses.eq("complete")].copy()
    if len(primary) != len(complete) or set(primary["item_id"].astype(str)) != set(
        complete["item_id"].astype(str)
    ):
        raise PostT2ContractError("primary-y table is not complete for successful items")
    item_check = complete.rename(
        columns={"target_station": "station_id", "achieved_skill": "item_achieved_skill"}
    )[
        [
            "item_id",
            "network_id",
            "station_id",
            "geometry",
            "geometry_id",
            "truth_start_date",
            "observed_missing_start_date",
            "model",
            "information_condition",
            "task",
            "item_achieved_skill",
        ]
    ]
    joined = primary.merge(
        item_check,
        on="item_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_item"),
    )
    identity_columns = (
        "network_id",
        "station_id",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "observed_missing_start_date",
        "model",
        "information_condition",
        "task",
    )
    if any(
        not joined[column].astype(str).equals(joined[f"{column}_item"].astype(str))
        for column in identity_columns
    ):
        raise PostT2ContractError("primary-y identities differ from item results")
    observed = pd.to_numeric(joined["observed_achieved_skill"], errors="coerce")
    item_y = pd.to_numeric(joined["item_achieved_skill"], errors="coerce")
    operator = pd.to_numeric(joined["predicted_recoverability"], errors="coerce")
    if (
        not np.isfinite(observed).all()
        or not np.isfinite(operator).all()
        or not np.allclose(observed, item_y, rtol=0.0, atol=1e-12)
    ):
        raise PostT2ContractError("primary y is nonfinite or differs from item achieved_skill")
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
    if geometry_manifest.get("manifest_schema") != "t2_v91_frozen_outage_geometry_binding_v1":
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
        or natural["actual_missing_truth_available"].map(str).str.lower().eq("true").any()
        or not natural["benchmark_truth_source"].eq(
            "held_out_observed_counterpart"
        ).all()
    ):
        raise PostT2ContractError("natural geometry violates planted-counterpart truth")
    pair_manifest = _read_json(pair_manifest_path)
    artifact = (pair_manifest.get("artifacts") or {}).get("pair_plan") or {}
    if _sha256_file(pair_plan_path) != artifact.get("sha256"):
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
    missing = sorted(PAIR_COLUMNS.difference(pairs.columns))
    if missing:
        raise PostT2ContractError(f"T5 pair plan omits columns: {missing}")
    forbidden = sorted({"delta_r", "t2_primary_y", "achieved_skill"} & set(pairs.columns))
    if forbidden:
        raise PostT2ContractError(f"T5 pair plan is not outcome-blind: {forbidden}")
    if (
        len(pairs) != int(pair_manifest.get("n_pair_plan_rows", -1))
        or pairs["regulated_id"].duplicated().any()
        or pairs["control_id"].duplicated().any()
    ):
        raise PostT2ContractError("T5 pair-plan cardinality/one-to-one contract mismatch")
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


def analyze_t4(primary: pd.DataFrame, natural: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compare natural planted-counterpart and artificial cells by network."""

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
    if not natural_rows["benchmark_truth_source"].eq(
        "held_out_observed_counterpart"
    ).all():
        raise PostT2ContractError("natural result does not use planted counterpart truth")
    if (
        not natural_rows["truth_start_date"].astype(str).eq(
            natural_rows["benchmark_start_date"].astype(str)
        ).all()
        or not natural_rows["observed_missing_start_date"].astype(str).eq(
            natural_rows["start_date"].astype(str)
        ).all()
    ):
        raise PostT2ContractError("natural result dates differ from frozen planted counterpart")
    natural_rows["analysis_weight"] = pd.to_numeric(
        natural_rows["benchmark_weight"], errors="coerce"
    )
    artificial_rows = primary.loc[primary["geometry"].eq("artificial_stress")].copy()
    artificial_rows["analysis_weight"] = 1.0
    networks = pd.concat(
        [
            _network_summary(artificial_rows, geometry="artificial_stress"),
            _network_summary(natural_rows, geometry="natural_outage"),
        ],
        ignore_index=True,
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
        "truth_source": "held_out_observed_counterpart",
        "actual_missing_days_scored": False,
        "aggregation_unit": "network",
        "same_network_aggregation_for_artificial_and_natural": True,
        "n_networks_by_geometry": counts,
        "network_spearman_by_geometry": correlations,
        "network_interval": None,
        "network_interval_reported": False,
    }


def analyze_t5(primary: pd.DataFrame, pairs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Join the frozen station pairs to artificial T2 primary y only."""

    artificial = primary.loc[primary["geometry"].eq("artificial_stress")].copy()
    station_y = (
        artificial.groupby(["network_id", "station_id"], as_index=False)[
            "observed_achieved_skill"
        ]
        .mean()
        .rename(columns={"observed_achieved_skill": "t2_primary_y"})
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
        pair_id = f"{regulated_key[0]}:{regulated_key[1]}|{control_key[0]}:{control_key[1]}"
        if missing:
            attrition.extend({"pair_id": pair_id, "reason": reason} for reason in missing)
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
    return contrasts, attrition_frame, {
        "manifest_schema": T5_SCHEMA,
        "status": "descriptive_only_three_frozen_pairs",
        "passed": False,
        "formal_evidence": False,
        "outcome_source": "T2_v4_primary_observed_achieved_skill",
        "geometry": "artificial_stress",
        "old_delta_r_read_or_reused": False,
        "n_pairs_frozen": len(pairs),
        "n_pairs_with_primary_y": len(contrasts),
        "n_pairs_attrited": int(len(pairs) - len(contrasts)),
        "pair_delta_mean": (
            float(contrasts["delta_t2_primary_y_regulated_minus_control"].mean())
            if not contrasts.empty
            else None
        ),
        "network_interval": None,
        "network_interval_reported": False,
    }


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
                "truth_source_required": "held_out_observed_counterpart",
                "aggregation_unit": "network",
            },
            "t5": {
                "status": "blocked_waiting_for_t2_primary_y",
                "n_pair_plan_rows": len(pairs),
                "pair_plan_outcome_blind": True,
            },
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
    manifest = {
        "manifest_schema": READINESS_SCHEMA,
        "status": "derived_outputs_written_network_inference_withheld",
        "passed": False,
        "formal_evidence": False,
        "purpose": "post_t2_derived_analysis_not_confirmation",
        "blockers": ["network_interval_withheld_n_lt_100"],
        "v4_results_read": True,
        "v4_result_binding_sha256": _sha256_file(result_binding),
        "v4_workload_sha256": binding["workload_manifest_sha256"],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "old_t4_scores_read": False,
        "old_t5_delta_r_read": False,
        "network_interval": None,
        "network_interval_reported": False,
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
    "PostT2ContractError",
    "analyze_t4",
    "analyze_t5",
    "run_post_t2_analysis",
    "validate_v4_primary_inputs",
]
