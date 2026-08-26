from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from stream_recoverability.experiments.t4_t5_readiness import (
    audit_t4_scores,
    audit_t5_pairs,
    geometry_networks_from_blocks,
    readiness_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def _freeze() -> dict:
    return yaml.safe_load((ROOT / "configs/design_freeze_v9.yaml").read_text())


def _valid_t4_row(network_id: str) -> dict:
    return {
        "network_id": network_id,
        "station_id": "01234567",
        "gap_length": 30,
        "fill_mae": 0.4,
        "achieved_skill": 0.6,
        "recoverability_r": 0.7,
        "truth_source": "held_out_observed_days",
        "geometry_source": "real_missing_blocks_length_season",
        "formal_evidence": False,
    }


def test_t4_audit_exposes_a_missing_geometry_network() -> None:
    scores = pd.DataFrame([_valid_t4_row("river_a")])

    audit = audit_t4_scores(
        scores, required_geometry_networks=["river_a", "willamette_mainstem"]
    )

    assert "willamette_mainstem" in audit["missing_geometry_networks"]
    assert audit["input_contract_ready"] is False
    assert audit["passed"] is False


def test_t5_audit_rejects_legacy_coarse_pairs() -> None:
    freeze = _freeze()
    pairs = pd.DataFrame(
        {
            "regulated_id": ["regulated_a", "regulated_b"],
            "control_id": ["control_a", "control_b"],
            "delta_r": [-0.03, float("nan")],
            "aggecoregion": ["SEPlains", "WestMnts"],
        }
    )

    audit = audit_t5_pairs(
        pairs,
        matching_factors=freeze["t5_confound_control"]["matching_factors"],
    )

    assert audit["freeze_factor_set_complete"] is True
    assert audit["n_pairs_with_finite_delta_r"] < audit["n_pairs_declared"]
    assert audit["missing_pair_audit_columns"]
    assert audit["input_contract_ready"] is False
    assert audit["passed"] is False


def test_readiness_manifest_preserves_twin_e_miss_and_blocks_formal_run() -> None:
    freeze = _freeze()
    scores = pd.DataFrame([_valid_t4_row("river_a")])
    pairs = pd.DataFrame(
        {
            "regulated_id": ["regulated_a"],
            "control_id": ["control_a"],
            "delta_r": [-0.03],
        }
    )
    twin = {"gate": {"passed": False, "status": "twin_e_operator_calibration_miss"}}

    manifest = readiness_manifest(
        freeze,
        t4_scores=scores,
        t4_geometry_networks=["river_a"],
        t5_pairs=pairs,
        twin_e_manifest=twin,
    )

    assert manifest["status"] == "blocked_waiting_for_t2_primary_y"
    assert manifest["formal_run_allowed"] is False
    assert manifest["t5_twin_e"]["negative_result_locked"] is True
    assert manifest["t5_twin_e"]["generator_retuning_allowed"] is False
    assert manifest["passed"] is False


def test_geometry_networks_union_is_read_only(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    pd.DataFrame({"network_id": ["river_a", "river_b"]}).to_csv(first, index=False)
    pd.DataFrame({"network_id": ["river_b", "river_c"]}).to_csv(second, index=False)

    assert geometry_networks_from_blocks([first, second]) == [
        "river_a",
        "river_b",
        "river_c",
    ]
