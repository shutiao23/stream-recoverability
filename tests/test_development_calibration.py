from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.conditional_observability import INFORMATION_SETS
from stream_recoverability.analysis.development_calibration import (
    fit_calibrator,
    leave_one_network_out_calibration,
    regime_memory_weight,
    station_gap_operator_predictions,
)


def _complete_series() -> pd.DataFrame:
    rng = np.random.default_rng(2718)
    n = 700
    weather = np.empty(n)
    flow = np.empty(n)
    target_a = np.empty(n)
    target_b = np.empty(n)
    weather[0] = flow[0] = target_a[0] = target_b[0] = 0.0
    for time in range(1, n):
        weather[time] = 0.75 * weather[time - 1] + rng.normal(0.0, 0.7)
        flow[time] = 0.55 * flow[time - 1] + 0.25 * weather[time] + rng.normal(0.0, 0.6)
        target_a[time] = (
            0.72 * target_a[time - 1]
            + 0.25 * target_b[time - 1]
            + 0.40 * weather[time]
            + 0.20 * flow[time]
            + rng.normal(0.0, 0.3)
        )
        target_b[time] = (
            0.35 * target_b[time - 1]
            + 0.30 * target_a[time - 1]
            + 0.35 * weather[time]
            + 0.25 * flow[time]
            + rng.normal(0.0, 0.35)
        )
    return pd.DataFrame(
        {
            "temperature_a": target_a,
            "temperature_b": target_b,
            "air_temperature": weather,
            "discharge": flow,
        }
    )


def test_station_gap_interface_contains_all_four_information_classes() -> None:
    assert "B_union_D_union_M_union_H" in INFORMATION_SETS
    predictions = station_gap_operator_predictions(
        _complete_series(),
        network_id="river_one",
        target_stations=("temperature_a", "temperature_b"),
        gaps=(5, 10),
        donor_stations={
            "temperature_a": ("temperature_b",),
            "temperature_b": ("temperature_a",),
        },
        meteorology_columns=("air_temperature",),
        hydraulics_columns=("discharge",),
    )
    assert len(predictions) == 4
    assert not predictions.duplicated(
        ["network_id", "station_id", "gap_length"]
    ).any()
    for information in ("boundary", "donor", "meteorology", "hydraulics"):
        assert predictions[f"{information}_conditional_risk"].notna().all()
        assert predictions[f"{information}_conditional_variance"].notna().all()
        assert (predictions[f"{information}_incremental_information"] >= -1e-7).all()
    assert (
        predictions["complete_operator_risk"]
        <= predictions["boundary_conditional_risk"] + 1e-7
    ).all()
    assert predictions["memory_weight"].eq(1.0).all()


def test_regime_weighting_scales_only_the_boundary_increment() -> None:
    series = _complete_series()
    uniform = station_gap_operator_predictions(
        series,
        network_id="river_one",
        target_stations=("temperature_b",),
        gaps=(10,),
        donor_stations={"temperature_b": ("temperature_a",)},
        meteorology_columns=("air_temperature",),
        hydraulics_columns=("discharge",),
        memory_weighting="uniform",
    ).iloc[0]
    weighted = station_gap_operator_predictions(
        series,
        network_id="river_one",
        target_stations=("temperature_b",),
        gaps=(10,),
        donor_stations={"temperature_b": ("temperature_a",)},
        meteorology_columns=("air_temperature",),
        hydraulics_columns=("discharge",),
        memory_weighting="regime",
        memory_lower=0.0,
        memory_upper=1.0,
    ).iloc[0]
    assert 0.0 <= weighted["memory_weight"] <= 1.0
    full = weighted["complete_operator_risk"]
    without_boundary = full + weighted["boundary_incremental_information"]
    expected = without_boundary - weighted["memory_weight"] * (
        without_boundary - full
    )
    assert weighted["predicted_conditional_risk"] == pytest.approx(expected)
    assert weighted["predicted_conditional_risk"] >= uniform[
        "predicted_conditional_risk"
    ] - 1e-10
    assert regime_memory_weight(0.1, lower=0.2, upper=0.7) == 0.0
    assert regime_memory_weight(0.8, lower=0.2, upper=0.7) == 1.0


def _calibration_panel() -> pd.DataFrame:
    rows = []
    offsets = {"n1": -0.03, "n2": -0.01, "n3": 0.01, "n4": 0.03}
    network_risk = {"n1": 0.00, "n2": 0.08, "n3": 0.16, "n4": 0.24}
    for network, offset in offsets.items():
        for station in range(3):
            for gap in (7, 30, 90):
                risk = 0.2 + network_risk[network] + station * 0.12 + gap * 0.004
                rows.append(
                    {
                        "network_id": network,
                        "station_id": f"s{station}",
                        "gap_length": gap,
                        "memory_regime": (
                            "high_memory" if station == 0 else "low_memory"
                        ),
                        "predicted_conditional_risk": risk,
                        "observed_recovery_loss": 0.08 + 1.35 * risk + offset,
                    }
                )
    return pd.DataFrame(rows)


def test_linear_lono_outputs_calibration_rank_coverage_and_residuals() -> None:
    result = leave_one_network_out_calibration(
        _calibration_panel(), method="linear", coverage=0.90
    )
    assert len(result.predictions) == len(_calibration_panel())
    assert result.predictions["held_out_network"].eq(
        result.predictions["network_id"]
    ).all()
    assert set(result.folds["held_out_network"]) == {"n1", "n2", "n3", "n4"}
    assert result.summary["calibration_slope"] == pytest.approx(1.0, abs=0.03)
    assert result.summary["calibration_intercept"] == pytest.approx(0.0, abs=0.03)
    assert result.summary["rank_spearman"] > 0.95
    assert result.summary["network_rank_spearman"] > 0.95
    assert 0.0 <= result.summary["interval_coverage"] <= 1.0
    assert 0.0 <= result.summary["network_equal_interval_coverage"] <= 1.0
    assert 0.0 <= result.summary["network_simultaneous_interval_coverage"] <= 1.0
    assert set(result.residuals["gap_length"]) == {7, 30, 90}
    assert {
        "residual_mean",
        "residual_std",
        "mae",
        "rmse",
        "residual_prediction_spearman",
    }.issubset(result.residuals)


def test_monotonic_calibrator_and_lono_predictions_are_order_preserving() -> None:
    calibrator = fit_calibrator(
        [0.1, 0.2, 0.3, 0.4],
        [0.2, 0.1, 0.5, 0.6],
        method="monotonic",
    )
    predicted = calibrator.predict([0.1, 0.2, 0.3, 0.4])
    assert np.diff(predicted).min() >= 0.0

    result = leave_one_network_out_calibration(
        _calibration_panel(), method="isotonic"
    )
    for _, group in result.predictions.groupby("held_out_network"):
        ordered = group.sort_values("predicted_conditional_risk")
        assert np.diff(ordered["calibrated_prediction"]).min() >= -1e-12


def test_lono_calibration_gives_each_training_network_equal_weight() -> None:
    rows = []
    for network, observed, repeats in (
        ("large", 0.0, 100),
        ("small_a", 9.0, 1),
        ("small_b", 6.0, 1),
        ("held", 5.0, 1),
    ):
        for station in range(repeats):
            rows.append(
                {
                    "network_id": network,
                    "station_id": f"s{station}",
                    "gap_length": 30,
                    "memory_regime": "low_memory",
                    "predicted_conditional_risk": 0.0,
                    "observed_recovery_loss": observed,
                }
            )
    result = leave_one_network_out_calibration(pd.DataFrame(rows), coverage=0.90)
    held = result.predictions.loc[result.predictions["network_id"].eq("held")]
    assert held["calibrated_prediction"].iloc[0] == pytest.approx(5.0)
    assert result.folds["interval_calibration_unit"].eq(
        "network_max_absolute_inner_lono_residual"
    ).all()
    assert result.folds.loc[
        result.folds["held_out_network"].eq("held"),
        "n_interval_calibration_networks",
    ].iloc[0] == 3
