from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import pytest

from stream_recoverability.experiments.t2_w7_open_role_bd_slice import (
    FORBIDDEN_SCORED_NETWORK_IDS,
    GO_NO_GO,
    N_NETWORKS_MIN,
    PURPOSE,
    W7SliceContractError,
    W8_INCREMENTAL_R2_TRIGGER,
    collect_w7_chunk_manifest_paths,
    development_inference_status,
    write_w7_open_role_bd_slice,
)


REQUIRED_FALSE = (
    "passed",
    "formal_evidence",
    "headline_claim_licensed",
    "confirmatory_eligible",
    "new_temperatures_downloaded",
    "sealed_outcomes_opened",
    "europe_complete_enough_used",
    "mh_relabeled_as_executable",
    "operator_retuned",
    "geometry_reselected",
    "twin_e_holdout_touched",
    "later_year_public_rivers_overwritten",
    "slice_is_confirmatory_t2",
)


def _row(
    *,
    network_id: str,
    station_id: str = "s1",
    model: str = "donor_regression",
    information: str = "B_union_D",
    status: str = "complete",
    gap_length: int = 30,
    ordinal: int = 0,
    skill: float = 0.2,
    mae: float = 0.8,
) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "item_id": f"{network_id}-{model}-{information}-{ordinal}",
        "network_id": network_id,
        "target_station": station_id,
        "station_id": station_id,
        "model": model,
        "information_condition": information,
        "status": status,
        "gap_length": gap_length,
        "placement": 0,
        "achieved_skill": skill,
        "mae_deg_c": mae,
        "sealed_temperature_records_read": False,
        "role": "development",
        "geometry": "artificial_stress",
    }


def _predictors(network_ids: list[str], *, donor: float = 0.4, operator: float = 0.5) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "network_id": network,
                "station_id": "s1",
                "gap_length": 30,
                "predicted_conditional_risk": operator,
                "gap_length_only": 0.3,
                "acf_only": 0.2,
                "donor_r2_only": donor,
                "additive_d_over_4_heuristic": 0.35,
            }
            for network in network_ids
        ]
    )


def _assert_locked(manifest: dict[str, object]) -> None:
    for key in REQUIRED_FALSE:
        assert manifest[key] is False, key
    assert manifest["purpose"] == PURPOSE
    assert manifest["go_no_go"] == GO_NO_GO
    assert manifest["evaluate_success"]["passed"] is False
    assert manifest["evaluate_success"]["n_networks_min"] == N_NETWORKS_MIN
    assert manifest["evaluate_success"]["confirmatory_eligible"] is False
    assert manifest["evaluate_success"]["spearman_inference_status"] != "tested"
    assert manifest["network_inference_status"] != "tested"
    assert set(manifest["scored_network_ids"]).isdisjoint(FORBIDDEN_SCORED_NETWORK_IDS)


def test_slice_writer_does_not_set_passed_true_even_with_100_networks(tmp_path: Path) -> None:
    networks = [f"huc8_{index:08d}" for index in range(100)]
    rng = np.random.default_rng(0)
    rows = []
    predictor_rows = []
    for index, network in enumerate(networks):
        skill = 0.1 + 0.7 * (index / 99.0) + float(rng.normal(0, 0.01))
        donor = 0.2 + 0.6 * (index / 99.0)
        rows.append(
            _row(
                network_id=network,
                ordinal=index,
                skill=skill,
                mae=1.0 - skill,
            )
        )
        predictor_rows.append(
            {
                "network_id": network,
                "station_id": "s1",
                "gap_length": 30,
                "predicted_conditional_risk": 1.0 - skill,
                "gap_length_only": 0.3,
                "acf_only": 0.2,
                "donor_r2_only": donor,
                "additive_d_over_4_heuristic": 0.35,
            }
        )
    later_year = tmp_path / "results/framework/public_rivers"
    later_year.mkdir(parents=True)
    later_manifest = later_year / "operator_ablation_manifest.json"
    later_manifest.write_text('{"keep": true}\n', encoding="utf-8")
    twin = tmp_path / "results/framework/synthetic_v2/twin_e"
    twin.mkdir(parents=True)
    twin_file = twin / "twin_e_manifest.json"
    twin_file.write_text('{"keep": true}\n', encoding="utf-8")
    output = tmp_path / "results/framework/t2_recovery_benchmark_v1/w7_open_role_bd_slice"
    manifest = write_w7_open_role_bd_slice(
        output_dir=output,
        results=pd.DataFrame(rows),
        predictors=pd.DataFrame(predictor_rows),
        repo_root=tmp_path,
    )
    _assert_locked(manifest)
    assert manifest["n_networks"] == 100
    assert manifest["passed"] is False
    assert manifest["evaluate_success"]["spearman_inference_status"] == (
        "withheld_development_slice_not_confirmatory"
    )
    assert later_manifest.read_text(encoding="utf-8") == '{"keep": true}\n'
    assert twin_file.read_text(encoding="utf-8") == '{"keep": true}\n'
    written = json.loads((output / "w7_open_role_bd_slice_manifest.json").read_text())
    assert written["passed"] is False
    assert written["evaluate_success"]["passed"] is False


def test_n_lt_100_cannot_emit_tested_ci(tmp_path: Path) -> None:
    networks = ["huc8_01070004", "huc8_01090001"]
    manifest = write_w7_open_role_bd_slice(
        output_dir=tmp_path / "slice",
        results=pd.DataFrame(
            [_row(network_id=network, ordinal=index) for index, network in enumerate(networks)]
        ),
        predictors=_predictors(networks),
    )
    _assert_locked(manifest)
    assert manifest["n_networks"] == 2
    assert manifest["n_networks"] < 100
    assert development_inference_status(manifest["n_networks"]) == (
        "withheld_n_lt_100_network_interval"
    )
    assert manifest["network_inference_status"] == "withheld_n_lt_100_network_interval"
    assert manifest["evaluate_success"]["spearman_inference_status"] == (
        "withheld_n_lt_100_network_interval"
    )
    assert manifest["network_interval"] is None


def test_suwannee_loire_swiss_not_in_scored_open_role_huc8_ids(tmp_path: Path) -> None:
    rows = [
        _row(network_id="huc8_01070004", ordinal=0, skill=0.4),
        _row(network_id="huc8_03110203", ordinal=1, skill=0.9),
        _row(network_id="suwannee_river_huc31", ordinal=2, skill=0.8),
        _row(network_id="loire_mainstem", ordinal=3, skill=0.7),
        _row(network_id="swiss_aar_rhine", ordinal=4, skill=0.6),
    ]
    manifest = write_w7_open_role_bd_slice(
        output_dir=tmp_path / "slice",
        results=pd.DataFrame(rows),
        predictors=_predictors(
            [
                "huc8_01070004",
                "huc8_03110203",
                "suwannee_river_huc31",
                "loire_mainstem",
                "swiss_aar_rhine",
            ]
        ),
        workload={"network_ids": ["huc8_01070004", "huc8_01090001"]},
    )
    _assert_locked(manifest)
    scored = set(manifest["scored_network_ids"])
    assert scored == {"huc8_01070004"}
    assert "huc8_03110203" not in scored
    assert manifest["n_networks"] == 1
    leaked = set(manifest["forbidden_network_ids_leaked_into_input"])
    assert leaked == FORBIDDEN_SCORED_NETWORK_IDS


def test_mh_cells_are_not_relabeled_executable(tmp_path: Path) -> None:
    rows = [
        _row(network_id="huc8_01070004", ordinal=0, information="B_union_D", status="complete"),
        _row(
            network_id="huc8_01070004",
            ordinal=1,
            information="B_union_D_union_M",
            status="complete",
            model="xgboost",
        ),
        _row(
            network_id="huc8_01070004",
            ordinal=2,
            information="B_union_D_union_M_union_H",
            status="complete",
            model="xgboost",
        ),
    ]
    manifest = write_w7_open_role_bd_slice(
        output_dir=tmp_path / "slice",
        results=pd.DataFrame(rows),
        predictors=_predictors(["huc8_01070004"]),
    )
    assert manifest["mh_relabeled_as_executable"] is False
    assert manifest["mh_items_complete"] == 2
    assert manifest["n_first_layer_executable_complete"] == 1
    assert manifest["n_extended_information_items_in_ordinal_range"] == 2


def test_w8_failure_closure_trigger_when_operator_increment_below_threshold(
    tmp_path: Path,
) -> None:
    networks = [f"huc8_{index:08d}" for index in range(12)]
    rows = []
    predictor_rows = []
    rng = np.random.default_rng(1)
    for index, network in enumerate(networks):
        donor = 0.1 + 0.8 * (index / 11.0)
        skill = donor + float(rng.normal(0, 0.01))
        rows.append(_row(network_id=network, ordinal=index, skill=skill, mae=1.0 - skill))
        predictor_rows.append(
            {
                "network_id": network,
                "station_id": "s1",
                "gap_length": 30,
                "predicted_conditional_risk": float(rng.normal(0.5, 0.05)),
                "gap_length_only": 0.3,
                "acf_only": 0.2,
                "donor_r2_only": donor,
                "additive_d_over_4_heuristic": 0.35,
            }
        )
    manifest = write_w7_open_role_bd_slice(
        output_dir=tmp_path / "slice",
        results=pd.DataFrame(rows),
        predictors=pd.DataFrame(predictor_rows),
    )
    increment = manifest["operator_incremental_r2_vs_donor_r2_only"]
    assert increment is not None
    assert increment < W8_INCREMENTAL_R2_TRIGGER
    assert manifest["w8_failure_closure_trigger"] is True
    assert manifest["w8_failure_closure_reason"] == (
        "operator_incremental_r2_vs_donor_r2_only_lt_0.05"
    )
    assert manifest["operator_retuned"] is False
    assert manifest["passed"] is False


def test_development_inference_status_never_tested() -> None:
    assert development_inference_status(1) == "withheld_n_lt_100_network_interval"
    assert development_inference_status(67) == "withheld_n_lt_100_network_interval"
    assert development_inference_status(99) == "withheld_n_lt_100_network_interval"
    assert development_inference_status(100) != "tested"
    assert development_inference_status(150) != "tested"
    assert "tested" not in {
        development_inference_status(n) for n in (0, 5, 67, 99, 100, 200)
    }


def test_workload_sha_is_recorded_not_rehashed_into_a_pass(tmp_path: Path) -> None:
    sha = hashlib.sha256(b"frozen-workload").hexdigest()
    manifest = write_w7_open_role_bd_slice(
        output_dir=tmp_path / "slice",
        results=pd.DataFrame([_row(network_id="huc8_01070004")]),
        predictors=_predictors(["huc8_01070004"]),
        workload_manifest_sha256=sha,
        workload={
            "network_ids": ["huc8_01070004"],
            "geometry_binding": {"qualification_mode": "failure_closure6"},
        },
    )
    assert manifest["workload_manifest_sha256"] == sha
    assert manifest["qualification_mode"] == "failure_closure6"
    assert manifest["aggregation_complete_workload"] is False


def test_collect_w7_chunk_manifest_paths_unions_lists_and_rejects_missing(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps(
            {
                "chunk_manifest_paths": [
                    str(tmp_path / "a.json"),
                    str(tmp_path / "b.json"),
                ]
            }
        ),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(
            {
                "chunk_manifest_paths": [
                    str(tmp_path / "b.json"),
                    str(tmp_path / "c.json"),
                ]
            }
        ),
        encoding="utf-8",
    )
    collected = collect_w7_chunk_manifest_paths(
        aggregation_list_paths=[first, second],
    )
    assert collected == [
        tmp_path / "a.json",
        tmp_path / "b.json",
        tmp_path / "c.json",
    ]
    with pytest.raises(W7SliceContractError, match="aggregation list missing"):
        collect_w7_chunk_manifest_paths(
            aggregation_list_paths=[tmp_path / "missing.json"],
        )
