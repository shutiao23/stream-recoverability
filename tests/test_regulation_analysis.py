import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.regulation import (
    annual_demeaned_skill_events,
    annual_thermal_metrics,
    circular_doy_climatology,
    predict_climatology,
    rescore_with_state_climatology,
)


def test_circular_climatology_and_annual_metrics_are_calendar_stable() -> None:
    dates = pd.date_range("2019-01-01", "2020-12-31", freq="D")
    phase = 2 * np.pi * (dates.dayofyear.to_numpy() - 1) / 365.25
    values = 10.0 + 5.0 * np.sin(phase)
    frame = pd.DataFrame({"date": dates, "S1_T": values})
    climatology = circular_doy_climatology(dates, values, half_window_days=7)
    prediction = predict_climatology(climatology, dates)
    assert len(climatology) == 366
    assert np.isfinite(prediction).all()
    annual = annual_thermal_metrics(frame, ["S1"])
    assert set(annual["year"]) == {2019, 2020}
    assert annual["annual_amplitude_degC"].between(9.9, 10.1).all()


def test_annual_demeaning_removes_a_models_constant_low_frequency_advantage() -> None:
    rows = []
    dates = pd.date_range("2019-01-01", periods=4, freq="D")
    truth_anomaly = np.array([1.0, 2.0, 3.0, 4.0])
    for model, predicted_anomaly in (
        ("climatology", np.zeros(4)),
        ("offset_only", np.full(4, truth_anomaly.mean())),
        ("shape", truth_anomaly + 10.0),
    ):
        for date, truth, prediction in zip(
            dates, truth_anomaly, predicted_anomaly, strict=True
        ):
            rows.append(
                {
                    "date": date,
                    "scenario_id": "scenario",
                    "station_id": "S1",
                    "model": model,
                    "training_seed": np.nan,
                    "mask_seed": 101,
                    "gap_length": 4,
                    "anchor_id": "A1",
                    "y_true": 10.0 + truth,
                    "y_pred": 10.0 + prediction,
                    "climatology_pred": 10.0,
                    "quality_approved": True,
                    "artificial_mask": True,
                }
            )
    result = annual_demeaned_skill_events(pd.DataFrame(rows)).set_index("model")
    assert result.loc["offset_only", "annual_demeaned_skill"] == pytest.approx(0.0)
    assert result.loc["shape", "annual_demeaned_skill"] == pytest.approx(1.0)


def test_state_climatology_rescoring_uses_named_fit_period() -> None:
    dates = pd.date_range("2016-01-01", "2020-12-31", freq="D")
    wide = pd.DataFrame({"date": dates, "S1_T": 12.0})
    predictions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-01-01", "2019-01-02"]),
            "scenario_id": "scenario",
            "station_id": "S1",
            "model": "candidate",
            "training_seed": np.nan,
            "mask_seed": 101,
            "gap_length": 2,
            "anchor_id": "A1",
            "y_true": [13.0, 11.0],
            "y_pred": [12.5, 11.5],
        }
    )
    result = rescore_with_state_climatology(
        predictions,
        wide,
        ["S1"],
        fit_start="2016-01-01",
        fit_end="2020-12-31",
    )
    assert result.loc[0, "state_climatology_MAE"] == pytest.approx(1.0)
    assert result.loc[0, "MAE"] == pytest.approx(0.5)
    assert result.loc[0, "state_climatology_skill"] == pytest.approx(0.5)
    assert bool(result.loc[0, "post_hoc_state_control"])
