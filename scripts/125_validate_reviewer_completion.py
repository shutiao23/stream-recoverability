#!/usr/bin/env python3
"""Validate reviewer-completion artifacts and manuscript/result agreement."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/development_v11/reviewer_completion"


def main() -> None:
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    manuscript = (ROOT / "paper/development_v11/manuscript.md").read_text(
        encoding="utf-8"
    )
    references = (ROOT / "paper/references.bib").read_text(encoding="utf-8")
    protocol = yaml.safe_load(
        (ROOT / "configs/route_a_second_confirmation_protocol.yaml").read_text(
            encoding="utf-8"
        )
    )
    lstm = json.loads(
        (OUTPUT / "lstm_sensitivity_manifest.json").read_text(encoding="utf-8")
    )
    air2stream = json.loads(
        (
            ROOT
            / "results/development_v11/independent_air2stream_equivalent/manifest.json"
        ).read_text(encoding="utf-8")
    )
    geometry = json.loads(
        (ROOT / "results/development_v11/matched_outage_geometry/summary.json").read_text(
            encoding="utf-8"
        )
    )
    heterogeneity = json.loads(
        (OUTPUT / "us_heterogeneity_manifest.json").read_text(encoding="utf-8")
    )
    second = json.loads(
        (
            ROOT
            / "results/development_v11/second_confirmation/scoring/summary.json"
        ).read_text(encoding="utf-8")
    )

    empirical = {
        (item["phase"], item["scope"]): item for item in summary["empirical_transfer"]
    }
    supported = empirical[("confirmation", "supported_only")]
    all_cells = empirical[("confirmation", "all_cells_with_network_mean_fallback")]
    assert supported["n"] == 780
    assert round(supported["spearman"], 3) == 0.934
    assert round(supported["r2"], 3) == 0.812
    assert all_cells["n"] == 1440
    assert round(all_cells["spearman"], 3) == 0.633
    assert "0.934" in manuscript and "0.812" in manuscript
    assert "0.0171" in manuscript
    assert "3.247" in manuscript
    assert "second independent confirmation" in manuscript
    for value in ("0.338", "0.173", "0.566", "0.734", "0.0024", "0.119"):
        assert value in manuscript

    roster = pd.read_csv(OUTPUT / "model_roster_metrics.csv")
    assert set(roster["model_family"]) == {
        "seasonal_boundary_ridge",
        "donor_blup_ridge",
        "xgboost_b_d",
    }
    replay = pd.read_csv(OUTPUT / "placement_replay_curve.csv")
    assert replay["independent_realized_outcomes"].all()
    assert replay["network_id"].nunique() >= 14
    assert replay.loc[replay["policy"].eq("oracle"), "regret"].eq(0).all()

    for figure in range(1, 6):
        matches = list(OUTPUT.glob(f"figure_0{figure}_*.png"))
        assert len(matches) == 1 and matches[0].stat().st_size > 10_000
    figure_6 = OUTPUT / "figure_06_us_heterogeneity.png"
    assert figure_6.stat().st_size > 10_000

    for key in (
        "caselton1984monitoring",
        "krause2008sensor",
        "pardo1998gauges",
        "alfonso2012voi",
        "oh2025sensors",
        "moffat2007gap",
        "richardson2007longgaps",
        "denhertog2006kriging",
        "yamamoto2000kriging",
        "auer2024uncertainty",
        "toffolon2015air2stream",
    ):
        assert f"{{{key}," in references
        assert f"@{key}" in manuscript

    for term in ("authorization consumed", "burned", "stop-loss", "BL-016"):
        assert term.lower() not in manuscript.lower()

    assert protocol["minimum_valid_scored_networks"] == 40
    assert protocol["target_scored_networks"] == [60, 80]
    assert (
        protocol["evidence_separation"]["first_confirmation_networks_reusable"] is False
    )
    assert second["attempted_networks"] == 60
    assert second["attrited_networks"] == 3
    assert second["scored_networks"] == 57
    assert round(second["empirical_supported_horizon_metrics"]["network_spearman"], 3) == 0.805
    assert second["triage"]["endpoint_passed"] is False
    assert lstm["architecture_assertion"] == {
        "recurrent_module": "torch.nn.LSTM",
        "bidirectional": True,
        "is_gru": False,
    }
    assert lstm["n_completed_providers"] >= 7
    assert lstm["completed_networks"] == 14
    assert lstm["failed_networks"] == 0
    assert (
        lstm["training"]["outer_evaluation_labels_used_for_fit_or_validation"] is False
    )
    assert lstm["full_roster_coverage"] is False
    assert "Rahmani_et_al_model_reimplementation" in lstm["not_a_claim_of"]
    assert round(lstm["results"]["empirical_vs_lstm_station_gap_spearman"], 3) == 0.338
    assert round(lstm["results"]["empirical_vs_lstm_network_spearman"], 3) == 0.631
    assert lstm["training"]["fraction_hit_epoch_limit"] > 0.9

    assert air2stream["model"]["published_equation"] is True
    assert air2stream["model"]["original_executable_used"] is False
    assert air2stream["coverage"]["input_eligible_networks"] == 8
    assert air2stream["coverage"]["fitted_stations"] == 14
    assert air2stream["results"]["n_station_gaps"] == 89
    assert round(
        air2stream["results"]["empirical_risk_vs_air2stream_network_spearman"], 3
    ) == 0.238

    assert geometry["n_networks"] == 49
    assert geometry["v11_empirical_curve_matched_rows"] == 1327
    assert round(geometry["metrics"]["natural_empirical"]["network_spearman"], 3) == 0.566
    assert round(geometry["metrics"]["artificial_empirical"]["network_spearman"], 3) == 0.734
    assert geometry["consistency"]["empirical_rank_delta"]["ci95_upper"] < 0.0

    assert heterogeneity["risk_models"] == {
        "fitting_period_empirical": 100,
        "simple_descriptors": 104,
    }
    levels = pd.read_csv(OUTPUT / "us_heterogeneity_level_slopes.csv")
    simple = levels.loc[levels["risk_model"].eq("simple_descriptors")]
    arid = simple.loc[simple["level"].eq("arid_semiarid"), "adjusted_calibration_slope"].iloc[0]
    maritime = simple.loc[simple["level"].eq("maritime"), "adjusted_calibration_slope"].iloc[0]
    assert round(arid, 3) == 1.160
    assert round(maritime, 3) == 0.649
    print("reviewer completion validation passed")


if __name__ == "__main__":
    main()
