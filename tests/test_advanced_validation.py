import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.advanced_validation import (
    calibration_components,
    clopper_pearson_upper,
    evaluate_risk_control,
    finite_sample_quantile,
    interval_metrics,
    mondrian_intervals,
    network_block_scaled_intervals,
    risk_control_threshold,
)


def test_finite_sample_quantile_uses_conformal_rank() -> None:
    assert finite_sample_quantile([1, 2, 3, 4], 0.8) == 4


def test_mondrian_intervals_use_horizon_specific_scores_and_fallback() -> None:
    calibration = pd.DataFrame(
        {
            "gap_length": [7, 7, 7, 90, 90, 90],
            "prediction": [1.0] * 6,
            "observed_recovery_loss": [1.1, 1.2, 1.3, 2.0, 2.5, 3.0],
        }
    )
    evaluation = pd.DataFrame(
        {
            "network_id": ["a", "b", "c"],
            "gap_length": [7, 90, 365],
            "predicted_loss": [1.0, 1.0, 1.0],
            "observed_recovery_loss": [1.0, 1.0, 1.0],
        }
    )
    result = mondrian_intervals(
        calibration,
        evaluation,
        calibration_prediction="prediction",
        evaluation_prediction="predicted_loss",
        coverage=0.5,
        min_stratum_rows=3,
    )
    assert result.loc[0, "conformal_radius"] < result.loc[1, "conformal_radius"]
    assert result.loc[2, "conformal_source"] == "global_fallback"


def test_interval_metrics_count_whole_network_coverage() -> None:
    frame = pd.DataFrame(
        {
            "network_id": ["a", "a", "b"],
            "predicted_loss": [1.0, 1.0, 1.0],
            "observed_recovery_loss": [1.0, 3.0, 1.0],
            "prediction_lower": [0.0, 0.0, 0.0],
            "prediction_upper": [2.0, 2.0, 2.0],
        }
    )
    result = interval_metrics(frame)
    assert result["row_coverage"] == 2 / 3
    assert result["network_simultaneous_coverage"] == 0.5


def test_network_block_scaled_interval_uses_one_score_per_network() -> None:
    calibration = pd.DataFrame(
        {
            "network_id": ["a", "a", "b", "b", "c", "c"],
            "prediction": [1.0] * 6,
            "observed_recovery_loss": [1.0, 1.1, 1.0, 1.2, 1.0, 1.3],
        }
    )
    evaluation = pd.DataFrame(
        {
            "network_id": ["z", "z"],
            "predicted_loss": [1.0, 2.0],
            "observed_recovery_loss": [1.0, 2.0],
        }
    )
    result = network_block_scaled_intervals(
        calibration,
        evaluation,
        calibration_prediction="prediction",
        evaluation_prediction="predicted_loss",
        coverage=0.5,
    )
    assert result["conformal_calibration_networks"].eq(3).all()
    assert result.loc[1, "conformal_radius"] > result.loc[0, "conformal_radius"]


def test_calibration_components_remove_network_means() -> None:
    frame = pd.DataFrame(
        {
            "network_id": ["a", "a", "b", "b"],
            "predicted_loss": [0.0, 1.0, 10.0, 11.0],
            "observed_recovery_loss": [0.0, 1.0, 100.0, 101.0],
        }
    )
    result = calibration_components(frame)
    assert result["within_network_spearman"] == 1.0
    assert result["between_network_spearman"] == pytest.approx(1.0)


def test_risk_control_refuses_small_budget_at_five_percent() -> None:
    calibration = pd.DataFrame(
        {
            "risk": np.arange(20, dtype=float),
            "observed_recovery_loss": np.zeros(20),
        }
    )
    rule = risk_control_threshold(calibration, risk_column="risk")
    assert rule["status"] == "no_certified_release"
    evaluated = evaluate_risk_control(calibration, rule, risk_column="risk")
    assert evaluated["n_released"] == 0


def test_clopper_pearson_can_certify_zero_errors_with_enough_labels() -> None:
    assert clopper_pearson_upper(0, 100) < 0.05
    calibration = pd.DataFrame(
        {
            "risk": np.arange(100, dtype=float),
            "observed_recovery_loss": np.zeros(100),
        }
    )
    rule = risk_control_threshold(calibration, risk_column="risk")
    assert rule["status"] == "certified"
    assert rule["n_certified"] == 100
