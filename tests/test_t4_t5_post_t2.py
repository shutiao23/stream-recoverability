from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.experiments.t2_workload_v4 import (
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)
from stream_recoverability.experiments.t4_t5_post_t2 import (
    INPUT_BINDING_SCHEMA,
    PostT2ContractError,
    analyze_t4,
    analyze_t5,
    run_post_t2_analysis,
    validate_v4_primary_inputs,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stream_sha(ids: list[str]) -> str:
    digest = hashlib.sha256()
    for value in ids:
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _valid_v4_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    ids = ["item-a", "item-b"]
    items = pd.DataFrame(
        {
            "ordinal": [0, 1],
            "item_id": ids,
            "network_id": ["net-a", "net-b"],
            "target_station": ["00000001", "00000002"],
            "geometry": ["natural_outage", "artificial_stress"],
            "geometry_id": ["natural-1", ""],
            "truth_start_date": ["2001-01-01", "2001-02-01"],
            "observed_missing_start_date": ["1999-01-01", ""],
            "model": ["donor_regression", "donor_regression"],
            "information_condition": ["B_union_D", "B_union_D"],
            "task": ["offline_archival", "offline_archival"],
            "status": ["complete", "complete"],
            "achieved_skill": [0.7, 0.6],
            "sealed_temperature_records_read": [False, False],
        }
    )
    primary = items.rename(
        columns={"target_station": "station_id", "achieved_skill": "observed_achieved_skill"}
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
            "observed_achieved_skill",
        ]
    ].copy()
    primary["predicted_recoverability"] = [0.8, 0.65]
    items_path = tmp_path / "items.parquet"
    primary_path = tmp_path / "primary.parquet"
    items.to_parquet(items_path, index=False)
    primary.to_parquet(primary_path, index=False)
    workload_path = tmp_path / "workload.json"
    workload = {
        "manifest_schema": V4_WORKLOAD_SCHEMA,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "n_work_items": 2,
        "work_item_identity_sha256": _stream_sha(ids),
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    workload_path.write_text(json.dumps(workload), encoding="utf-8")
    binding_path = tmp_path / "binding.json"
    binding = {
        "manifest_schema": INPUT_BINDING_SCHEMA,
        "status": "complete",
        "completeness": "complete",
        "formal_result_generated": True,
        "workload_manifest_sha256": _sha(workload_path),
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "expected_item_records": 2,
        "observed_item_records": 2,
        "work_item_identity_sha256": _stream_sha(ids),
        "primary_y_column": "observed_achieved_skill",
        "operator_column": "predicted_recoverability",
        "primary_table_complete_for_all_complete_items": True,
        "item_records_validated_against_frozen_v4_stream": True,
        "primary_table_derived_without_row_selection": True,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "status_counts": {"complete": 2},
        "item_results": {
            "path": items_path.name,
            "format": "parquet",
            "sha256": _sha(items_path),
            "n_rows": 2,
        },
        "primary_y_table": {
            "path": primary_path.name,
            "format": "parquet",
            "sha256": _sha(primary_path),
            "n_rows": 2,
        },
    }
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    return workload_path, binding_path, items_path


def test_v4_primary_binding_validates_complete_identity_stream(tmp_path: Path) -> None:
    workload, binding, _ = _valid_v4_inputs(tmp_path)

    items, primary, parsed = validate_v4_primary_inputs(workload, binding)

    assert len(items) == len(primary) == 2
    assert parsed["completeness"] == "complete"


def test_v4_primary_binding_rejects_byte_drift(tmp_path: Path) -> None:
    workload, binding, items_path = _valid_v4_inputs(tmp_path)
    frame = pd.read_parquet(items_path)
    frame.loc[0, "achieved_skill"] = 0.1
    frame.to_parquet(items_path, index=False)

    with pytest.raises(PostT2ContractError, match="SHA-256 mismatch"):
        validate_v4_primary_inputs(workload, binding)


def test_t4_uses_only_frozen_counterpart_truth_and_network_aggregation() -> None:
    primary = pd.DataFrame(
        {
            "item_id": ["n1", "n2", "a1", "a2"],
            "network_id": ["net-a", "net-b", "net-a", "net-b"],
            "station_id": ["s1", "s2", "s1", "s2"],
            "geometry": [
                "natural_outage",
                "natural_outage",
                "artificial_stress",
                "artificial_stress",
            ],
            "geometry_id": ["g1", "g2", "", ""],
            "truth_start_date": ["2001-01-01", "2001-01-01", "2002-01-01", "2002-01-01"],
            "observed_missing_start_date": ["1999-01-01", "1999-02-01", "", ""],
            "model": ["m"] * 4,
            "information_condition": ["D"] * 4,
            "task": ["offline_archival"] * 4,
            "observed_achieved_skill": [0.2, 0.8, 0.3, 0.7],
            "predicted_recoverability": [0.1, 0.9, 0.2, 0.8],
        }
    )
    natural = pd.DataFrame(
        {
            "geometry_id": ["g1", "g2"],
            "network_id": ["net-a", "net-b"],
            "station_id": ["s1", "s2"],
            "benchmark_start_date": ["2001-01-01", "2001-01-01"],
            "start_date": ["1999-01-01", "1999-02-01"],
            "benchmark_truth_source": [
                "held_out_observed_counterpart",
                "held_out_observed_counterpart",
            ],
            "benchmark_weight": [0.5, 0.5],
        }
    )

    table, manifest = analyze_t4(primary, natural)

    assert set(table["geometry"]) == {"natural_outage", "artificial_stress"}
    assert manifest["aggregation_unit"] == "network"
    assert manifest["truth_source"] == "held_out_observed_counterpart"
    assert manifest["network_interval_reported"] is False
    assert manifest["status"] == "withheld_n_lt_100_network_interval"


def test_t5_joins_frozen_pairs_to_artificial_primary_y_without_old_delta() -> None:
    primary = pd.DataFrame(
        {
            "network_id": ["treated-net", "control-net", "treated-net"],
            "station_id": ["t1", "c1", "t1"],
            "geometry": ["artificial_stress", "artificial_stress", "natural_outage"],
            "observed_achieved_skill": [0.4, 0.6, 0.99],
        }
    )
    pairs = pd.DataFrame(
        {
            "regulated_id": ["t1", "missing"],
            "control_id": ["c1", "c1"],
            "regulated_network_id": ["treated-net", "treated-net"],
            "control_network_id": ["control-net", "control-net"],
        }
    )

    contrasts, attrition, manifest = analyze_t5(primary, pairs)

    assert len(contrasts) == 1
    assert contrasts.iloc[0]["delta_t2_primary_y_regulated_minus_control"] == pytest.approx(-0.2)
    assert len(attrition) == 1
    assert manifest["old_delta_r_read_or_reused"] is False
    assert manifest["n_pairs_frozen"] == 2


def test_current_repo_writes_blocked_readiness_without_reading_old_results(
    tmp_path: Path,
) -> None:
    manifest = run_post_t2_analysis(
        workload_path=tmp_path / "absent_workload.json",
        result_binding_path=tmp_path / "absent_binding.json",
        geometry_catalog_path=ROOT
        / "results/framework/t2_outage_geometry_v1/natural_outage_catalog.csv",
        geometry_manifest_path=ROOT
        / "results/framework/t2_outage_geometry_v1/geometry_binding_manifest.json",
        pair_plan_path=ROOT / "results/framework/t5_matching_contract_v1/pair_plan.csv",
        pair_manifest_path=ROOT
        / "results/framework/t5_matching_contract_v1/readiness_manifest.json",
        output_dir=tmp_path / "output",
    )

    assert manifest["status"] == "blocked_waiting_for_complete_t2_v4_results"
    assert manifest["v4_results_read"] is False
    assert manifest["old_t4_scores_read"] is False
    assert manifest["old_t5_delta_r_read"] is False
    assert manifest["t5"]["n_pair_plan_rows"] == 3
    assert not (tmp_path / "output/t5_pair_contrasts.csv").exists()
