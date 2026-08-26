import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.evidence_boundaries import (
    MIN_INDEPENDENT_CLUSTERS,
    WITHHELD_STATUS,
    decide_inference_status,
    firth_logistic,
    flag_separated_coefficients,
    independent_cluster_count,
    recoverability_type,
    topology_confound_rows,
    type_classification_table,
    withhold_node_importance_intervals,
    withhold_overlap_inference,
    year_block_mean_interval,
)


def test_independent_cluster_count_is_conservative():
    assert independent_cluster_count(20, 3, 3) == 3
    assert independent_cluster_count(1, 3, 3) == 1
    assert independent_cluster_count(np.nan, 3, None) == 3


def test_decide_inference_status_withholds_below_floor():
    assert decide_inference_status(n_independent_clusters=1) == WITHHELD_STATUS
    assert decide_inference_status(n_independent_clusters=4) == WITHHELD_STATUS
    assert (
        decide_inference_status(n_independent_clusters=5, is_reference=True)
        == "reference_not_tested"
    )
    assert decide_inference_status(n_independent_clusters=5) == "tested"


def test_withhold_overlap_inference_clears_pseudoreplicated_p_values():
    frame = pd.DataFrame(
        {
            "model": ["xgboost", "climatology", "kalman"],
            "hypothesis_family": ["frontier_model_vs_climatology"] * 3,
            "hypothesis_status": ["tested", "reference_not_tested", "tested"],
            "n_hypothesis_clusters": [1, 1, 1],
            "n_years": [3, 3, 3],
            "n_bootstrap_clusters": [3, 3, 3],
            "p_value": [1e-6, np.nan, 0.01],
            "p_bh": [1e-5, np.nan, 0.02],
            "bh_reject": [True, False, True],
            "statistical_frontier_days": [365.0, np.nan, 8.0],
            "skill_ci_lower": [0.1, np.nan, 0.2],
            "skill_ci_upper": [0.3, np.nan, 0.4],
        }
    )
    result = withhold_overlap_inference(frame)
    tested = result.loc[result["model"].eq("xgboost")].iloc[0]
    assert tested["hypothesis_status"] == WITHHELD_STATUS
    assert pd.isna(tested["p_value"])
    assert pd.isna(tested["statistical_frontier_days"])
    assert bool(tested["inference_claim_allowed"]) is False
    reference = result.loc[result["model"].eq("climatology")].iloc[0]
    assert reference["hypothesis_status"] == "reference_not_tested"


def test_year_block_interval_withholds_with_three_years():
    frame = pd.DataFrame(
        {
            "anchor_year": [2018, 2019, 2020],
            "unit_impact": [0.1, 0.2, 0.05],
        }
    )
    lower, upper = year_block_mean_interval(
        frame, "unit_impact", year_col="anchor_year", n_boot=50, seed=1
    )
    assert np.isnan(lower) and np.isnan(upper)


def test_year_block_interval_returns_finite_interval_with_enough_years():
    frame = pd.DataFrame(
        {
            "anchor_year": list(range(2010, 2010 + MIN_INDEPENDENT_CLUSTERS)),
            "unit_impact": [0.1, 0.12, 0.08, 0.11, 0.09],
        }
    )
    lower, upper = year_block_mean_interval(
        frame, "unit_impact", year_col="anchor_year", n_boot=200, seed=3
    )
    assert np.isfinite(lower) and np.isfinite(upper)
    assert lower <= upper


def test_node_importance_ci_withheld_for_three_years():
    frame = pd.DataFrame(
        {
            "station_id": ["B1"],
            "failed_station_id": ["S2"],
            "impact": [0.105],
            "impact_ci_lower": [0.044],
            "impact_ci_upper": [0.169],
            "n_anchor_years": [3],
        }
    )
    result = withhold_node_importance_intervals(frame).iloc[0]
    assert result["inference_status"] == WITHHELD_STATUS
    assert pd.isna(result["impact_ci_lower"])
    assert result["impact"] == pytest.approx(0.105)


def test_type_margin_flags_near_threshold_chattahoochee_site():
    frame = pd.DataFrame(
        {
            "station_id": ["02334430", "P3", "B1"],
            "donor_component": [0.3665, 0.1063, 0.4644],
            "memory_component": [0.3979, 0.5530, 0.0585],
        }
    )
    result = type_classification_table(frame).set_index("station_id")
    assert result.loc["02334430", "recoverability_type"] == "memory_dominated"
    assert bool(result.loc["02334430", "near_classification_threshold"])
    assert result.loc["P3", "recoverability_type"] == "memory_dominated"
    assert not bool(result.loc["P3", "near_classification_threshold"])
    assert result.loc["B1", "recoverability_type"] == "donor_dominated"


def test_topology_audit_aliases_both_memory_sites():
    table = topology_confound_rows().set_index("station_id")
    assert bool(table.loc["P3", "network_endpoint"])
    assert "aliased" in table.loc["P3", "identifiability_note"]
    assert bool(table.loc["02334430", "network_endpoint"])
    assert table.loc["02334430", "donor_direction"] == "all_downstream"


def test_firth_logistic_recovers_unseparated_association():
    rng = np.random.default_rng(7)
    x1 = rng.normal(size=200)
    logits = -0.2 + 0.8 * x1
    y = (rng.uniform(size=200) < 1 / (1 + np.exp(-logits))).astype(float)
    design = np.column_stack([np.ones(200), x1])
    fitted = firth_logistic(y, design)
    assert fitted["converged"]
    assert fitted["odds_ratio"][1] > 1.0


def test_flag_separated_coefficients_suppresses_exploding_odds():
    frame = pd.DataFrame(
        {
            "term": ["z_memory_range_index", "ecoregion_Alaska"],
            "coefficient_log_odds": [0.92, 23.0],
            "odds_ratio": [2.52, 1e10],
            "wald_p_value": [0.0167, 0.84],
        }
    )
    result = flag_separated_coefficients(frame).set_index("term")
    assert result.loc["z_memory_range_index", "reporting_status"] == "reported"
    assert (
        result.loc["ecoregion_Alaska", "reporting_status"]
        == "suppressed_complete_separation"
    )
    assert pd.isna(result.loc["ecoregion_Alaska", "odds_ratio"])


def test_recoverability_type_uses_component_comparison():
    assert recoverability_type(0.5, 0.4) == "donor_dominated"
    assert recoverability_type(0.4, 0.5) == "memory_dominated"
    assert recoverability_type(0.5, 0.5) == "donor_dominated"
