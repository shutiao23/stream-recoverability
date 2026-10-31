from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.experiments.t2_recovery_benchmark import (
    RUNNER_CONTRACT_VERSION,
)
from stream_recoverability.experiments.t2_result_aggregation import (
    BINDING_SCHEMA,
    MIXED_MODEL_COLUMNS,
    PREDICTOR_SCHEMA,
    AggregationContractError,
    aggregate_t2_results,
)

ITEM_ID = "huc8_test-station_a-donor_regression-30-0-900-B_union_D"


def _fixture(tmp_path: Path, *, expected_n: int = 1) -> dict[str, Path]:
    design = tmp_path / "design.yaml"
    design.write_text("design_id: design_freeze_v9\n", encoding="utf-8")
    workload = {
        "manifest_schema": "t2_v91_open_role_workload_v2",
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "sealed_temperature_records_read": False,
        "input_inventory": {"sealed_input_roots_allowed": []},
        "n_networks": 1,
        "tier_1": {
            "n_work_items": expected_n,
            "online_causal_status": "ready",
        },
        "geometry_dependencies": {
            "artificial_stress": "ready",
            "natural_outage": "ready",
            "adversarial": "ready",
        },
    }
    workload_path = tmp_path / "workload_manifest.json"
    workload_path.write_text(json.dumps(workload), encoding="utf-8")
    checkpoint_dir = tmp_path / "checkpoints_v2"
    checkpoint_dir.mkdir()
    return {
        "design": design,
        "workload": workload_path,
        "checkpoint_dir": checkpoint_dir,
    }


def _write_checkpoint(paths: dict[str, Path]) -> dict[str, object]:
    record = {
        "ordinal": 0,
        "item_id": ITEM_ID,
        "network_id": "huc8_test",
        "role": "validation",
        "source_key": "open_role_qc/validation",
        "target_station": "station_a",
        "model": "donor_regression",
        "gap_length": 30,
        "placement": 0,
        "start_index": 900,
        "information_condition": "B_union_D",
        "task": "offline_archival",
        "geometry": "artificial_stress",
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "status": "complete",
        "mae_deg_c": 0.75,
        "achieved_skill": 0.25,
        "sealed_temperature_records_read": False,
    }
    checkpoint = paths["checkpoint_dir"] / f"{ITEM_ID}.json"
    checkpoint.write_text(json.dumps(record), encoding="utf-8")
    return record


def _write_binding(paths: dict[str, Path]) -> Path:
    binding = {
        "manifest_schema": BINDING_SCHEMA,
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "checkpoint_namespace": "checkpoints_v2",
        "n_records": len(list(paths["checkpoint_dir"].glob("*.json"))),
        "completeness": "complete",
        "sealed_temperature_records_read": False,
    }
    path = paths["checkpoint_dir"].parent / "checkpoint_binding.json"
    path.write_text(json.dumps(binding), encoding="utf-8")
    return path


def _write_predictors(paths: dict[str, Path]) -> Path:
    table = pd.DataFrame(
        [
            {
                "network_id": "huc8_test",
                "station_id": "station_a",
                "gap_length": 30,
                "predicted_conditional_risk": 0.8,
                "gap_length_only": 0.3,
                "acf_only": 0.4,
                "donor_r2_only": 0.5,
                "additive_d_over_4_heuristic": 0.6,
            }
        ]
    )
    table_path = paths["checkpoint_dir"].parent / "predictors.csv"
    table.to_csv(table_path, index=False)
    manifest = {
        "manifest_schema": PREDICTOR_SCHEMA,
        "fit_role": "development",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "sealed_temperature_records_read": False,
        "completeness": "complete",
        "predictions_path": table_path.name,
        "predictions_format": "csv",
        "join_keys": ["network_id", "station_id", "gap_length"],
    }
    path = table_path.parent / "predictor_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_incomplete_checkpoint_set_writes_readiness_only(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, expected_n=2)
    output = tmp_path / "aggregation"
    output.mkdir()
    (output / "t2_mixed_model_input.csv").write_text("stale\n")
    (output / "t2_mixed_model_input.parquet").write_text("stale\n")
    manifest = aggregate_t2_results(
        workload_manifest_path=paths["workload"],
        design_path=paths["design"],
        output_dir=output,
        checkpoint_dir=paths["checkpoint_dir"],
    )
    assert manifest["status"] == "blocked"
    assert manifest["passed"] is False
    assert manifest["network_inference_status"] == "withheld_n_lt_100_network_interval"
    assert manifest["network_interval"] is None
    assert "result_workload_incomplete_0_of_2" in manifest["blockers"]
    assert "checkpoint_result_set_missing_binding" in manifest["blockers"]
    assert (output / "readiness_manifest.json").is_file()
    assert not (output / "t2_mixed_model_input.csv").exists()
    assert not (output / "t2_mixed_model_input.parquet").exists()


def test_complete_bound_set_writes_inference_schema_but_withholds_small_n_ci(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _write_checkpoint(paths)
    binding = _write_binding(paths)
    predictors = _write_predictors(paths)
    output = tmp_path / "aggregation"
    manifest = aggregate_t2_results(
        workload_manifest_path=paths["workload"],
        design_path=paths["design"],
        output_dir=output,
        checkpoint_dir=paths["checkpoint_dir"],
        checkpoint_binding_path=binding,
        predictor_manifest_path=predictors,
    )
    assert manifest["status"] == "ready"
    assert manifest["passed"] is False
    assert manifest["network_inference_status"] == "withheld_n_lt_100_network_interval"
    assert manifest["network_interval"] is None
    csv = pd.read_csv(output / "t2_mixed_model_input.csv")
    parquet = pd.read_parquet(output / "t2_mixed_model_input.parquet")
    assert tuple(csv.columns) == MIXED_MODEL_COLUMNS
    assert tuple(parquet.columns) == MIXED_MODEL_COLUMNS
    assert csv.loc[0, "observed_recovery_loss"] == pytest.approx(0.75)
    assert csv.loc[0, "predicted_conditional_risk"] == pytest.approx(0.8)
    assert csv.loc[0, "station_id"] == "station_a"
    assert csv.loc[0, "item_id"] == ITEM_ID


def test_checkpoint_binding_record_count_mismatch_is_rejected(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    record = _write_checkpoint(paths)
    binding = _write_binding(paths)
    extra = paths["checkpoint_dir"] / "unbound_extra.json"
    extra.write_text(json.dumps({**record, "ordinal": 1}), encoding="utf-8")
    with pytest.raises(AggregationContractError, match="n_records"):
        aggregate_t2_results(
            workload_manifest_path=paths["workload"],
            design_path=paths["design"],
            output_dir=tmp_path / "aggregation",
            checkpoint_dir=paths["checkpoint_dir"],
            checkpoint_binding_path=binding,
        )


def test_predictor_contract_must_be_train_only_and_never_sealed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _write_checkpoint(paths)
    binding = _write_binding(paths)
    predictor_path = _write_predictors(paths)
    predictor = json.loads(predictor_path.read_text())
    predictor["outcome_rows_read_during_fit"] = True
    predictor_path.write_text(json.dumps(predictor), encoding="utf-8")
    with pytest.raises(AggregationContractError, match="outcome_rows_read_during_fit"):
        aggregate_t2_results(
            workload_manifest_path=paths["workload"],
            design_path=paths["design"],
            output_dir=tmp_path / "aggregation",
            checkpoint_dir=paths["checkpoint_dir"],
            checkpoint_binding_path=binding,
            predictor_manifest_path=predictor_path,
        )


def test_aggregation_rejects_sealed_named_path_before_read(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    sealed = tmp_path / "sealed_public_rivers_v3" / "workload.json"
    sealed.parent.mkdir()
    sealed.write_bytes(Path(paths["workload"]).read_bytes())

    with pytest.raises(AggregationContractError, match="sealed-path"):
        aggregate_t2_results(
            workload_manifest_path=sealed,
            design_path=paths["design"],
            output_dir=tmp_path / "aggregation",
        )


def test_frozen_bound_geometry_status_is_ready_not_a_blocker(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, expected_n=0)
    workload = json.loads(Path(paths["workload"]).read_text(encoding="utf-8"))
    workload["geometry_dependencies"] = {
        "artificial_stress": "ready",
        "natural_outage": "ready_frozen_catalog_bound",
        "adversarial_stress": "ready_frozen_catalog_bound",
    }
    Path(paths["workload"]).write_text(json.dumps(workload), encoding="utf-8")

    manifest = aggregate_t2_results(
        workload_manifest_path=paths["workload"],
        design_path=paths["design"],
        output_dir=tmp_path / "aggregation",
    )

    assert not any(value.startswith("geometry_") for value in manifest["blockers"])
