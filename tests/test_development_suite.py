from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_suite import (
    cross_domain_transfer_summary,
    full_regret_curve,
    gaussian_mutual_information,
    greedy_mutual_information_indices,
    leave_one_network_out_nested_predictions,
    leave_one_network_out_predictions,
    lono_advancement_gate,
    lono_metrics,
    nested_lono_metrics,
    regime_shift_stress_test,
    run_development_suite,
    station_gap_metrics,
    station_gap_table,
)
from stream_recoverability.experiments.sensor_policy import POLICIES
from stream_recoverability.experiments.synthetic_river import advection_chain


def _development_scores() -> pd.DataFrame:
    rows = []
    for network in range(8):
        for station in range(2):
            for gap_index, gap in enumerate((7, 30, 90)):
                operator = 0.15 + 0.11 * network + 0.07 * station + 0.04 * gap_index
                noise = 0.015 * ((network + station + gap_index) % 3 - 1)
                rows.append(
                    {
                        "network_id": f"n{network}",
                        "station_id": f"s{station}",
                        "gap_length": gap,
                        "predicted_conditional_risk": operator,
                        "donor_r2": ((3 * network + 5 * station + gap_index) % 11) / 10,
                        "observed_recovery_loss": 0.3 + 1.7 * operator + noise,
                        "fit_regime": "cold" if network < 4 else "warm",
                        "evaluation_regime": (
                            "cold"
                            if network < 3
                            else "warm"
                            if network < 7
                            else "shifted"
                        ),
                        "domain": "US" if network % 2 == 0 else "Europe",
                    }
                )
    return pd.DataFrame(rows)


def test_station_gap_is_the_evaluation_unit() -> None:
    scores = _development_scores()
    duplicated = pd.concat([scores, scores], ignore_index=True)
    units = station_gap_table(duplicated)
    metrics = station_gap_metrics(duplicated)
    assert len(units) == len(scores)
    assert metrics["unit"].eq("station_gap").all()
    assert set(metrics["predictor"]) == {"operator", "donor_r2", "gap_length"}
    operator = metrics.set_index("predictor").loc["operator"]
    assert operator["spearman"] > 0.99
    assert operator["r2"] > 0.99


def test_lono_compares_operator_donor_and_gap_length() -> None:
    predictions = leave_one_network_out_predictions(_development_scores())
    metrics = lono_metrics(predictions).set_index("predictor")
    assert set(metrics.index) == {"operator", "donor_r2", "gap_length"}
    assert metrics.loc["operator", "r2"] > metrics.loc["donor_r2", "r2"]
    assert metrics.loc["operator", "spearman"] > metrics.loc["gap_length", "spearman"]
    assert predictions.groupby(["predictor", "network_id"]).size().gt(0).all()


def test_advancement_gate_requires_both_fixed_gains() -> None:
    passing = pd.DataFrame(
        {
            "predictor": ["operator", "donor_r2"],
            "spearman": [0.80, 0.70],
            "r2": [0.60, 0.55],
        }
    )
    passed = lono_advancement_gate(passing)
    assert np.isclose(passed["delta_spearman"], 0.10)
    assert np.isclose(passed["delta_r2"], 0.05)
    assert passed["passed"] is True

    failing = passing.copy()
    failing.loc[failing["predictor"].eq("operator"), "r2"] = 0.59
    assert lono_advancement_gate(failing)["passed"] is False


def test_nested_lono_measures_operator_increment_after_simple_combination() -> None:
    scores = _development_scores()
    scores["acf_only"] = scores["gap_length"] / 100.0
    scores["donor_r2_only"] = scores["donor_r2"]
    scores["additive_d_over_4_heuristic"] = scores["donor_r2"] / 2.0
    predictions = leave_one_network_out_nested_predictions(scores)
    metrics = nested_lono_metrics(predictions)
    gate_metrics = lono_metrics(leave_one_network_out_predictions(scores))
    gate = lono_advancement_gate(
        gate_metrics, incremental_r2=metrics["operator_incremental_r2"]
    )
    assert len(predictions) == len(scores)
    assert predictions["selected_simple_model"].str.len().gt(0).all()
    assert predictions["simple_interval_calibration_unit"].eq(
        "network_max_absolute_inner_lono_residual"
    ).all()
    assert predictions["n_simple_interval_calibration_networks"].eq(7).all()
    assert (
        predictions["simple_prediction_lower"]
        <= predictions["simple_prediction"]
    ).all()
    assert (
        predictions["simple_prediction"]
        <= predictions["simple_prediction_upper"]
    ).all()
    assert metrics["operator_incremental_r2"] > 0.05
    assert gate["delta_r2"] == round(metrics["operator_incremental_r2"], 12)


def test_nested_lono_uses_declared_simple_candidate_models() -> None:
    scores = _development_scores()
    scores["acf_only"] = scores["gap_length"] / 100.0
    scores["donor_r2_only"] = scores["donor_r2"]
    scores["additive_d_over_4_heuristic"] = scores["donor_r2"] / 2.0
    predictions = leave_one_network_out_nested_predictions(
        scores,
        candidate_models=(("gap_length",), ("donor_r2_only",)),
    )
    assert set(predictions["selected_simple_model"]).issubset(
        {"gap_length", "donor_r2_only"}
    )


def test_nested_simple_selection_never_reads_the_outer_network_outcome() -> None:
    scores = _development_scores()
    scores["acf_only"] = scores["gap_length"] / 100.0
    scores["donor_r2_only"] = scores["donor_r2"]
    scores["additive_d_over_4_heuristic"] = scores["donor_r2"] / 2.0
    original = leave_one_network_out_nested_predictions(scores)
    changed = scores.copy()
    changed.loc[changed["network_id"].eq("n0"), "observed_recovery_loss"] += 1000.0
    rerun = leave_one_network_out_nested_predictions(changed)
    original_model = original.loc[
        original["held_out_network"].eq("n0"), "selected_simple_model"
    ].unique()
    rerun_model = rerun.loc[
        rerun["held_out_network"].eq("n0"), "selected_simple_model"
    ].unique()
    assert np.array_equal(original_model, rerun_model)
    original_radius = original.loc[
        original["held_out_network"].eq("n0"), "simple_interval_radius"
    ].unique()
    rerun_radius = rerun.loc[
        rerun["held_out_network"].eq("n0"), "simple_interval_radius"
    ].unique()
    assert np.array_equal(original_radius, rerun_radius)


def test_greedy_mutual_information_is_an_explicit_placement_baseline() -> None:
    covariance = np.array(
        [
            [1.0, 0.7, 0.1, 0.0],
            [0.7, 1.2, 0.6, 0.1],
            [0.1, 0.6, 1.1, 0.5],
            [0.0, 0.1, 0.5, 0.9],
        ]
    )
    selected = greedy_mutual_information_indices(covariance, 2)
    assert len(selected) == 2
    chosen_information = gaussian_mutual_information(covariance, selected)
    alternatives = [
        gaussian_mutual_information(covariance, (left, right))
        for left in range(4)
        for right in range(left + 1, 4)
    ]
    assert np.isclose(chosen_information, max(alternatives))
    assert chosen_information > 0


def test_regret_curve_covers_every_budget_policy_and_has_zero_oracle_regret() -> None:
    river = advection_chain(n_stations=5)
    curve = full_regret_curve(
        river, budgets=(1, 2, 3, 4), gap_length=14, random_repeats=2
    )
    expected_policies = (set(POLICIES) - {"current_network"}) | {
        "greedy_mutual_information"
    }
    assert set(curve["policy"]) == expected_policies
    assert curve.groupby("k")["policy"].nunique().eq(len(expected_policies)).all()
    assert curve.loc[curve["policy"].eq("oracle"), "absolute_regret"].abs().lt(1e-12).all()
    assert curve["absolute_regret"].ge(-1e-10).all()
    assert set(curve["protected_fraction"]) == {0.2, 0.4, 0.6, 0.8}
    assert curve["evidence_role"].eq("synthetic_implementation_only").all()
    assert ~curve["independent_realized_outcomes"].any()
    assert curve["selection_and_evaluation_share_true_covariance"].all()


def test_regime_shift_stress_test_reports_degradation_by_predictor() -> None:
    stress = regime_shift_stress_test(_development_scores())
    assert set(stress) == {"by_regime", "degradation"}
    assert set(stress["by_regime"]["stratum"]) == {"stable", "regime_shift"}
    assert set(stress["degradation"]["predictor"]) == {
        "operator",
        "donor_r2",
        "gap_length",
    }
    assert {
        "spearman_loss",
        "r2_loss",
        "rmse_increase",
    }.issubset(stress["degradation"].columns)


def test_cross_domain_transfer_and_end_to_end_suite() -> None:
    scores = _development_scores()
    transfer = cross_domain_transfer_summary(scores)
    assert set(transfer["target_domain"]) == {"US", "Europe"}
    assert set(transfer["predictor"]) == {"operator", "donor_r2", "gap_length"}
    assert transfer.groupby("target_domain")["predictor"].nunique().eq(3).all()
    assert {
        "operator_delta_spearman_vs_donor",
        "operator_delta_r2_vs_donor",
    }.issubset(transfer.columns)

    us_to_europe = cross_domain_transfer_summary(scores, source_domain="US")
    assert set(us_to_europe["training_domain"]) == {"US"}
    assert set(us_to_europe["target_domain"]) == {"Europe"}

    result = run_development_suite(
        scores, advection_chain(n_stations=4), budgets=(1, 2, 3)
    )
    assert set(result) == {
        "station_gap_metrics",
        "lono_predictions",
        "lono_metrics",
        "advancement_gate",
        "regret_curve",
        "regime_shift",
        "cross_domain_transfer",
    }
    assert result["advancement_gate"]["passed"] is True
