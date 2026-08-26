from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import stream_recoverability.experiments.t4_t5_post_t2 as post_t2
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
)
from stream_recoverability.experiments.t4_t5_post_t2 import (
    INPUT_BINDING_SCHEMA,
    OPERATOR_JOIN_KEYS,
    OPERATOR_PREDICTOR_SCHEMA,
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
            "role": ["development", "validation"],
            "network_id": ["net-a", "net-b"],
            "target_station": ["00000001", "00000002"],
            "geometry": ["natural_outage", "artificial_stress"],
            "geometry_id": ["natural-1", ""],
            "truth_start_date": ["2001-01-01", "2001-02-01"],
            "observed_missing_start_date": ["1999-01-01", ""],
            "model": ["donor_regression", "donor_regression"],
            "information_condition": ["B_union_D", "B_union_D"],
            "task": ["offline_archival", "offline_archival"],
            "gap_length": [7, 7],
            "placement": [0, 0],
            "start_index": [100, 200],
            "meteorology_lag_days": [None, None],
            "status": ["complete", "complete"],
            "achieved_skill": [0.7, 0.6],
            "sealed_temperature_records_read": [False, False],
        }
    )
    primary = items.rename(
        columns={
            "target_station": "station_id",
            "achieved_skill": "observed_achieved_skill",
        }
    )[
        [
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
        ]
    ].copy()
    lattice = primary.drop(columns="observed_achieved_skill").copy()
    lattice["analysis_weight"] = 1.0
    predictors = lattice.drop(columns="analysis_weight").copy()
    predictors["predicted_recoverability"] = [0.8, 0.65]
    items_path = tmp_path / "items.parquet"
    primary_path = tmp_path / "primary.parquet"
    lattice_path = tmp_path / "lattice.parquet"
    attrition_path = tmp_path / "data_ineligible_attrition.csv"
    predictor_path = tmp_path / "operator_predictions.parquet"
    predictor_manifest_path = tmp_path / "operator_predictor_manifest.json"
    items.to_parquet(items_path, index=False)
    primary.to_parquet(primary_path, index=False)
    lattice.to_parquet(lattice_path, index=False)
    pd.DataFrame(columns=["item_id", "role", "network_id", "reason"]).to_csv(
        attrition_path, index=False
    )
    predictors.to_parquet(predictor_path, index=False)
    predictor_manifest = {
        "manifest_schema": OPERATOR_PREDICTOR_SCHEMA,
        "join_keys": list(OPERATOR_JOIN_KEYS),
        "prediction_column": "predicted_recoverability",
        "fit_role": "development",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "predictions_path": predictor_path.name,
        "predictions_sha256": _sha(predictor_path),
        "n_prediction_rows": len(predictors),
    }
    predictor_manifest_path.write_text(json.dumps(predictor_manifest), encoding="utf-8")
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
        "analyzable_lattice_frozen_before_result_scoring": True,
        "analyzable_lattice_selection_uses_outcomes": False,
        "common_grid_complete": True,
        "analysis_weight_column": "analysis_weight",
        "data_ineligible_attrition_complete": True,
        "operator_predictions_train_only": True,
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
        "analyzable_lattice": {
            "path": lattice_path.name,
            "format": "parquet",
            "sha256": _sha(lattice_path),
            "n_rows": 2,
        },
        "data_ineligible_attrition": {
            "path": attrition_path.name,
            "format": "csv",
            "sha256": _sha(attrition_path),
            "n_rows": 0,
        },
        "operator_predictor_manifest": {
            "path": predictor_manifest_path.name,
            "sha256": _sha(predictor_manifest_path),
        },
        "operator_predictor_table": {
            "path": predictor_path.name,
            "format": "parquet",
            "sha256": _sha(predictor_path),
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


def test_v4_primary_binding_rejects_primary_supplied_operator_even_if_sha_is_updated(
    tmp_path: Path,
) -> None:
    workload, binding_path, _ = _valid_v4_inputs(tmp_path)
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    primary_path = tmp_path / "primary.parquet"
    primary = pd.read_parquet(primary_path)
    primary["predicted_recoverability"] = primary["observed_achieved_skill"]
    primary.to_parquet(primary_path, index=False)
    binding["primary_y_table"]["sha256"] = _sha(primary_path)
    binding_path.write_text(json.dumps(binding), encoding="utf-8")

    with pytest.raises(PostT2ContractError, match="must not supply predicted"):
        validate_v4_primary_inputs(workload, binding_path)


def test_v4_primary_binding_rejects_predictor_fit_that_read_outcomes(
    tmp_path: Path,
) -> None:
    workload, binding_path, _ = _valid_v4_inputs(tmp_path)
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "operator_predictor_manifest.json"
    predictor = json.loads(manifest_path.read_text(encoding="utf-8"))
    predictor["outcome_rows_read_during_fit"] = True
    manifest_path.write_text(json.dumps(predictor), encoding="utf-8")
    binding["operator_predictor_manifest"]["sha256"] = _sha(manifest_path)
    binding_path.write_text(json.dumps(binding), encoding="utf-8")

    with pytest.raises(PostT2ContractError, match="outcome_rows_read_during_fit"):
        validate_v4_primary_inputs(workload, binding_path)


def test_common_grid_rejects_eventwise_model_information_selection() -> None:
    lattice = pd.DataFrame(
        {
            "role": ["development", "development"],
            "network_id": ["n1", "n2"],
            "station_id": ["s1", "s2"],
            "geometry": ["artificial_stress", "artificial_stress"],
            "geometry_id": ["g1", "g2"],
            "truth_start_date": ["2001-01-01", "2001-01-01"],
            "observed_missing_start_date": ["", ""],
            "gap_length": [30, 30],
            "placement": [0, 0],
            "start_index": [10, 20],
            "model": ["donor_regression", "xgboost"],
            "information_condition": ["D", "D"],
            "task": ["offline_archival", "offline_archival"],
            "meteorology_lag_days": [None, None],
        }
    )

    with pytest.raises(PostT2ContractError, match="common model-information grid"):
        post_t2._assert_common_grid_complete(lattice)


def test_common_grid_rejects_eventwise_model_information_reweighting() -> None:
    lattice = pd.DataFrame(
        {
            "role": ["development"] * 4,
            "network_id": ["n1", "n1", "n2", "n2"],
            "station_id": ["s1", "s1", "s2", "s2"],
            "geometry": ["artificial_stress"] * 4,
            "geometry_id": ["g1", "g1", "g2", "g2"],
            "truth_start_date": ["2001-01-01"] * 4,
            "observed_missing_start_date": [""] * 4,
            "gap_length": [30] * 4,
            "placement": [0] * 4,
            "start_index": [10, 10, 20, 20],
            "model": ["donor_regression", "xgboost"] * 2,
            "information_condition": ["D"] * 4,
            "task": ["offline_archival"] * 4,
            "meteorology_lag_days": [None] * 4,
            "analysis_weight": [0.5, 0.5, 0.9, 0.1],
        }
    )

    with pytest.raises(PostT2ContractError, match="aggregation weights by event"):
        post_t2._assert_common_grid_complete(lattice)


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
            "truth_start_date": [
                "2001-01-01",
                "2001-01-01",
                "2002-01-01",
                "2002-01-01",
            ],
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
    assert manifest["analysis_name"] == "natural_geometry_observed_counterpart"
    assert manifest["actual_missing_days_scored"] is False
    assert manifest["natural_and_artificial_directly_comparable"] is False


def test_t4_network_interval_blocker_is_dynamic_at_one_hundred_networks() -> None:
    network_ids = [f"net-{index:03d}" for index in range(100)]
    geometry_ids = [f"g-{index:03d}" for index in range(100)]
    primary = pd.DataFrame(
        {
            "network_id": network_ids,
            "station_id": ["s1"] * 100,
            "geometry": ["natural_outage"] * 100,
            "geometry_id": geometry_ids,
            "truth_start_date": ["2001-01-01"] * 100,
            "observed_missing_start_date": ["1999-01-01"] * 100,
            "observed_achieved_skill": [index / 100 for index in range(100)],
            "predicted_recoverability": [index / 100 for index in range(100)],
            "analysis_weight": [1.0] * 100,
        }
    )
    natural = pd.DataFrame(
        {
            "geometry_id": geometry_ids,
            "network_id": network_ids,
            "station_id": ["s1"] * 100,
            "benchmark_start_date": ["2001-01-01"] * 100,
            "start_date": ["1999-01-01"] * 100,
            "benchmark_truth_source": ["held_out_observed_counterpart"] * 100,
            "benchmark_weight": [0.01] * 100,
        }
    )

    _, manifest = analyze_t4(primary, natural)

    assert manifest["status"] == "ready_for_hierarchical_confirmation_not_evaluated"
    assert manifest["network_interval_reported"] is False


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
    assert contrasts.iloc[0][
        "delta_t2_primary_y_regulated_minus_control"
    ] == pytest.approx(-0.2)
    assert len(attrition) == 1
    assert manifest["old_delta_r_read_or_reused"] is False
    assert manifest["n_pairs_frozen"] == 2
    assert manifest["status"] == "descriptive_infeasible_confound_control"
    assert manifest["n_unique_network_pairs"] == 1
    assert manifest["formal_run_allowed"] is False


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
    assert manifest["t5"]["status"] == "descriptive_infeasible_confound_control"
    assert manifest["t5"]["n_station_pairs"] == 3
    assert manifest["t5"]["n_unique_network_pairs"] == 2
    assert manifest["t5"]["caliper_invented_or_applied"] is False
    diagnostics = manifest["frozen_inputs"]["t5_pair_plan"]["balance_diagnostics"]
    assert diagnostics["n_unique_network_pairs"] == 2
    assert diagnostics["max_drainage_area_ratio"] > 30
    assert diagnostics["balance_supports_formal_confound_control"] is False
    assert not (tmp_path / "output/t5_pair_contrasts.csv").exists()


def _copied_pair_contract(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = ROOT / "results/framework/t5_matching_contract_v1"
    pair_path = tmp_path / "pair_plan.csv"
    covariate_path = tmp_path / "station_covariates.csv"
    manifest_path = tmp_path / "pair_manifest.json"
    pd.read_csv(source / "pair_plan.csv", dtype=str).to_csv(pair_path, index=False)
    pd.read_csv(
        source / "station_covariates.csv",
        dtype={"network_id": str, "station_id": str},
    ).to_csv(covariate_path, index=False)
    manifest = json.loads(
        (source / "readiness_manifest.json").read_text(encoding="utf-8")
    )
    manifest["artifacts"]["pair_plan"].update(
        {"path": pair_path.name, "sha256": _sha(pair_path)}
    )
    manifest["artifacts"]["station_covariates"].update(
        {"path": covariate_path.name, "sha256": _sha(covariate_path)}
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return pair_path, covariate_path, manifest_path


def test_pair_contract_rejects_outcome_column_even_when_plan_sha_is_rebound(
    tmp_path: Path,
) -> None:
    pair_path, _, manifest_path = _copied_pair_contract(tmp_path)
    pair = pd.read_csv(pair_path, dtype=str)
    pair["observed_achieved_skill"] = 0.5
    pair.to_csv(pair_path, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["pair_plan"]["sha256"] = _sha(pair_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PostT2ContractError, match="not outcome-blind"):
        run_post_t2_analysis(
            workload_path=tmp_path / "missing-workload.json",
            result_binding_path=tmp_path / "missing-binding.json",
            geometry_catalog_path=ROOT
            / "results/framework/t2_outage_geometry_v1/natural_outage_catalog.csv",
            geometry_manifest_path=ROOT
            / "results/framework/t2_outage_geometry_v1/geometry_binding_manifest.json",
            pair_plan_path=pair_path,
            pair_manifest_path=manifest_path,
            output_dir=tmp_path / "output",
        )


def test_pair_contract_rejects_exposure_drift_in_bound_covariates(
    tmp_path: Path,
) -> None:
    pair_path, covariate_path, manifest_path = _copied_pair_contract(tmp_path)
    covariates = pd.read_csv(
        covariate_path, dtype={"network_id": str, "station_id": str}
    )
    covariates.loc[covariates["station_id"].eq("05536995"), "regulated"] = False
    covariates.to_csv(covariate_path, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["station_covariates"]["sha256"] = _sha(covariate_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PostT2ContractError, match="exposure, role, or exact-match"):
        run_post_t2_analysis(
            workload_path=tmp_path / "missing-workload.json",
            result_binding_path=tmp_path / "missing-binding.json",
            geometry_catalog_path=ROOT
            / "results/framework/t2_outage_geometry_v1/natural_outage_catalog.csv",
            geometry_manifest_path=ROOT
            / "results/framework/t2_outage_geometry_v1/geometry_binding_manifest.json",
            pair_plan_path=pair_path,
            pair_manifest_path=manifest_path,
            output_dir=tmp_path / "output",
        )
