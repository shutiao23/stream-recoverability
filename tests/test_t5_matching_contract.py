from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.experiments.t5_matching_contract import (
    FROZEN_MATCHING_FACTORS,
    build_station_covariates,
    make_pair_attrition,
    make_pair_plan,
    matching_readiness,
    reject_outcome_columns,
)


def _nldi(path: Path, station_ids: list[str]) -> None:
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": f"USGS-{station_id}",
                "properties": {"identifier": f"USGS-{station_id}"},
            }
            for station_id in station_ids
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def _inputs(cache: Path) -> tuple[pd.DataFrame, ...]:
    predictors = pd.DataFrame(
        [
            {
                "network_id": network,
                "station_id": target,
                "role": "development",
                "gap_length": gap,
                "n_donors": 2,
                "donor_station_ids": donors,
            }
            for network, target, donors in (
                ("huc8_a", "01000001", "01000011|01000012"),
                ("huc8_b", "02000001", "02000011|02000012"),
            )
            for gap in (30, 90)
        ]
    )
    gages = pd.DataFrame(
        {
            "STAID": ["01000001", "02000001"],
            "MAJ_NDAMS_2009": [1, 0],
            "DRAIN_SQKM": [100.0, 110.0],
            "AGGECOREGION": ["NorthEast", "NorthEast"],
        }
    )
    bfi = pd.DataFrame(
        {"STAID": ["01000001", "02000001"], "BFI_AVE": [40.0, 42.0]}
    )
    stations = pd.DataFrame(
        {
            "site_id": [
                "01000001",
                "01000011",
                "01000012",
                "02000001",
                "02000011",
                "02000012",
            ],
            "latitude": [40.0, 40.1, 39.9, 41.0, 41.1, 40.9],
            "longitude": [-75.0, -75.0, -75.0, -76.0, -76.0, -76.0],
        }
    )
    split = pd.DataFrame(
        {
            "network_id": ["huc8_a", "huc8_b"],
            "role": ["development", "development"],
            "climate_band": ["humid", "humid"],
            "regulation_stratum": ["regulated", "natural"],
        }
    )
    for target, upstream, downstream in (
        ("01000001", ["01000011"], ["01000012"]),
        ("02000001", ["02000011"], ["02000012"]),
    ):
        _nldi(cache / f"{target}_UM_200.json", upstream)
        _nldi(cache / f"{target}_DM_200.json", downstream)
    return predictors, gages, bfi, stations, split


def test_outcome_columns_are_rejected() -> None:
    with pytest.raises(ValueError, match="outcome columns"):
        reject_outcome_columns([pd.DataFrame({"recoverability_r": [0.7]})])


def test_legacy_station_metric_shape_is_rejected(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    legacy = inputs[1].rename(columns={"STAID": "station_id"})

    with pytest.raises(ValueError, match="STAID"):
        build_station_covariates(
            inputs[0],
            gages=legacy,
            bfi=inputs[2],
            station_catalog=inputs[3],
            split_catalog=inputs[4],
            nldi_cache_dir=tmp_path,
        )


def test_complete_six_factor_rows_make_deterministic_pair(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    covariates, attrition = build_station_covariates(
        inputs[0],
        gages=inputs[1],
        bfi=inputs[2],
        station_catalog=inputs[3],
        split_catalog=inputs[4],
        nldi_cache_dir=tmp_path,
    )

    first = make_pair_plan(covariates)
    second = make_pair_plan(covariates.sample(frac=1.0, random_state=7))

    assert attrition.empty
    assert len(first) == 1
    pd.testing.assert_frame_equal(first, second)
    assert first.loc[0, "regulated_id"] == "01000001"
    assert first.loc[0, "control_id"] == "02000001"
    assert first.loc[0, "donor_count_abs_diff"] == 0
    assert bool(first.loc[0, "donor_direction_match"])
    assert bool(first.loc[0, "climate_match"])
    assert "delta_r" not in first.columns


def test_missing_direction_cache_is_explicit_attrition(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    (tmp_path / "02000001_DM_200.json").unlink()

    covariates, attrition = build_station_covariates(
        inputs[0],
        gages=inputs[1],
        bfi=inputs[2],
        station_catalog=inputs[3],
        split_catalog=inputs[4],
        nldi_cache_dir=tmp_path,
    )

    assert len(covariates) == 2
    assert "direction_cache_missing" in set(attrition["reason"])
    assert make_pair_plan(covariates).empty


def test_pair_attrition_separates_exact_stratum_failure(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    inputs[1].loc[1, "AGGECOREGION"] = "WestMnts"
    covariates, _ = build_station_covariates(
        inputs[0],
        gages=inputs[1],
        bfi=inputs[2],
        station_catalog=inputs[3],
        split_catalog=inputs[4],
        nldi_cache_dir=tmp_path,
    )

    pair_attrition = make_pair_attrition(covariates, make_pair_plan(covariates))

    assert len(pair_attrition) == 2
    assert set(pair_attrition["reason"]) == {
        "no_eligible_opposite_exposure_in_exact_stratum"
    }


def test_readiness_never_claims_t5_result(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    covariates, attrition = build_station_covariates(
        inputs[0],
        gages=inputs[1],
        bfi=inputs[2],
        station_catalog=inputs[3],
        split_catalog=inputs[4],
        nldi_cache_dir=tmp_path,
    )
    pairs = make_pair_plan(covariates)
    pair_attrition = make_pair_attrition(covariates, pairs)

    manifest = matching_readiness(
        covariates,
        attrition,
        pairs,
        matching_factors=FROZEN_MATCHING_FACTORS,
        pair_attrition=pair_attrition,
    )

    assert manifest["status"] == "descriptive_infeasible_confound_control"
    assert manifest["pair_plan_ready"] is False
    assert manifest["pair_plan_preserved_for_audit"] is True
    assert manifest["n_station_pairs"] == 1
    assert manifest["n_unique_network_pairs"] == 1
    assert manifest["balance_supports_formal_confound_control"] is False
    assert manifest["balance_diagnostics"][
        "max_log_drainage_area_abs_diff"
    ] > 0
    assert manifest["balance_diagnostics"][
        "max_standardized_l1_match_distance"
    ] > 0
    assert manifest["causal_interpretation_allowed"] is False
    assert manifest["t5_pass_claim_allowed"] is False
    assert "t5_passed" in manifest["forbidden_claims"]
    assert manifest["t2_primary_y_bound"] is False
    assert manifest["formal_run_allowed"] is False
    assert manifest["sealed_outcomes_opened"] is False
    assert manifest["passed"] is False
