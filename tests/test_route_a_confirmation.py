import numpy as np
import pandas as pd

from stream_recoverability.experiments.route_a_confirmation import (
    SIMPLE_COLUMNS,
    apply_route_a_model,
    confirmation_metrics,
    fit_route_a_model,
    fit_safe_release_threshold,
    grouped_confirmation_metrics,
    network_bootstrap_intervals,
    simple_predictors,
    thermal_state_changes,
    apply_safe_release_threshold,
)


def test_simple_predictors_use_only_first_seventy_percent_years() -> None:
    index = pd.date_range("2010-01-01", "2019-12-31", freq="D")
    day = np.arange(len(index), dtype=float)
    panel = pd.DataFrame(
        {
            "s1": 10 + np.sin(day / 20),
            "s2": 10 + np.sin(day / 20) + 0.2 * np.cos(day / 9),
            "s3": 9 + np.sin(day / 21),
        },
        index=index,
    )
    first = simple_predictors("n1", panel, gaps=(30, 90))
    changed = panel.copy()
    changed.loc[changed.index.year >= 2017] += 1000
    second = simple_predictors("n1", changed, gaps=(30, 90))
    pd.testing.assert_frame_equal(first, second)
    assert first["training_years"].eq("2010|2011|2012|2013|2014|2015|2016").all()


def test_fixed_simple_model_and_confirmation_metrics() -> None:
    rows = []
    for network in range(6):
        for gap in (7, 30, 90):
            values = {
                "gap_length": gap,
                "acf_only": network / 10,
                "donor_r2_only": (network + 1) / 10,
                "additive_d_over_4_heuristic": (network + 2) / 10,
                "nearest_donor_correlation": (network + 3) / 10,
                "placement_season_sin": 0.25,
                "placement_season_cos": -0.25,
            }
            loss = 0.2 + 0.01 * gap + sum(values[name] for name in SIMPLE_COLUMNS[1:])
            rows.append(
                {
                    "network_id": f"n{network}",
                    "station_id": "s1",
                    "observed_recovery_loss": loss,
                    **values,
                }
            )
    development = pd.DataFrame(rows)
    lono = development.copy()
    lono["simple_prediction"] = lono["observed_recovery_loss"] + 0.1
    lono["selected_simple_model"] = "|".join(SIMPLE_COLUMNS)
    model = fit_route_a_model(development, lono)
    applied = apply_route_a_model(model, development)
    applied["observed_recovery_loss"] = development["observed_recovery_loss"]
    metrics = confirmation_metrics(applied)
    assert metrics["station_gap_spearman"] > 0.99
    assert abs(metrics["calibration_slope"] - 1.0) < 1e-8
    assert metrics["interval_coverage"] == 1.0
    assert model.interval_radius >= 0.1


def test_real_state_change_and_grouped_metrics() -> None:
    index = pd.date_range("2010-01-01", "2019-12-31", freq="D")
    day = np.arange(len(index), dtype=float)
    values = np.sin(day / 20.0)
    values[index.year >= 2017] *= 3.0
    states = thermal_state_changes(
        "n1", pd.DataFrame({"s1": values, "s2": values + 1.0}, index=index)
    )
    assert states["thermal_state_shift"].all()

    rows = pd.DataFrame(
        {
            "network_id": ["n1", "n1", "n2", "n2"],
            "group": ["a", "a", "b", "b"],
            "predicted_loss": [1.0, 2.0, 1.5, 2.5],
            "observed_recovery_loss": [1.1, 1.9, 1.4, 2.6],
            "prediction_lower": [0.0, 1.0, 0.5, 1.5],
            "prediction_upper": [2.0, 3.0, 2.5, 3.5],
        }
    )
    grouped = grouped_confirmation_metrics(rows, group_column="group")
    assert set(grouped["group"]) == {"a", "b"}


def test_triage_threshold_is_fit_on_development_and_applied_unchanged() -> None:
    development = pd.DataFrame(
        {
            "risk": [0.1, 0.2, 0.3, 0.8, 0.9],
            "observed_recovery_loss": [0.1, 0.2, 0.6, 0.8, 0.9],
        }
    )
    threshold = fit_safe_release_threshold(development, risk_column="risk")
    confirmation = pd.DataFrame(
        {
            "risk": [0.15, 0.25, 0.7],
            "observed_recovery_loss": [0.2, 0.7, 0.8],
        }
    )
    result = apply_safe_release_threshold(
        confirmation, risk_column="risk", threshold=threshold
    )
    assert threshold == 0.2
    assert result["n_released"] == 1
    assert result["false_release_rate"] == 0.0


def test_network_bootstrap_reports_cluster_intervals() -> None:
    rows = []
    for network in range(6):
        for value in range(4):
            prediction = 0.2 * network + value
            rows.append(
                {
                    "network_id": f"n{network}",
                    "predicted_loss": prediction,
                    "observed_recovery_loss": prediction + 0.1 * network,
                    "prediction_lower": prediction - 1.0,
                    "prediction_upper": prediction + 1.0,
                }
            )
    intervals = network_bootstrap_intervals(
        pd.DataFrame(rows), repeats=40, seed=2
    )
    assert set(intervals.columns) == {"metric", "estimate", "lower_95", "upper_95"}
    assert intervals["lower_95"].le(intervals["upper_95"]).all()
