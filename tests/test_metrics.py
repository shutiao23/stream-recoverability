import numpy as np
import pandas as pd
import pytest

from stream_recoverability.evaluation.event_metrics import (
    EVENT_METRIC_COLUMNS,
    compute_event_metrics,
    event_metrics_from_frame,
)
from stream_recoverability.evaluation.metrics import (
    boundary_jump_metrics,
    compute_metrics,
    flow_metrics,
    level_metrics,
    quantile_metrics,
    temperature_metrics,
)


def test_common_metrics_use_quality_and_artificial_intersection_only():
    truth = np.array([0.0, 1.0, 2.0, 3.0])
    prediction = np.array([100.0, 2.0, 99.0, 3.0])
    quality = np.array([True, True, False, True])
    artificial = np.array([False, True, True, True])
    climatology = np.array([100.0, 3.0, 100.0, 3.0])
    result = compute_metrics(
        truth, prediction, quality, artificial, climatology_pred=climatology
    )
    assert result["n"] == 2
    assert result["mae"] == pytest.approx(0.5)
    assert result["rmse"] == pytest.approx(np.sqrt(0.5))
    assert result["bias"] == pytest.approx(0.5)
    assert result["skill"] == pytest.approx(0.5)


def test_boundary_jumps_use_observed_neighbors():
    result = boundary_jump_metrics(
        [0.0, 1.0, 2.0, 3.0, 4.0],
        [0.0, 1.5, 2.5, 3.0, 4.0],
        [True] * 5,
        [False, True, True, False, False],
    )
    assert result["boundary_jump_left"] == pytest.approx(1.5)
    assert result["boundary_jump_right"] == pytest.approx(0.5)


def test_flow_and_level_perfect_predictions_have_perfect_efficiency():
    truth = np.array([1.0, 2.0, 4.0, 8.0])
    mask = np.ones(4, dtype=bool)
    flow = flow_metrics(truth, truth, mask, mask, high_threshold=7.0, low_threshold=1.5)
    assert flow["nse"] == pytest.approx(1.0)
    assert flow["kge"] == pytest.approx(1.0)
    assert flow["pbias"] == pytest.approx(0.0)
    assert flow["high_flow_threshold"] == 7.0
    assert flow["low_flow_threshold"] == 1.5
    level = level_metrics(truth, truth, mask, mask, high_threshold=7.0)
    assert level["high_level_threshold"] == 7.0
    assert level["peak_level_error"] == pytest.approx(0.0)
    assert level["peak_timing_error_days"] == pytest.approx(0.0)


def test_temperature_extreme_metrics_are_masked():
    truth = np.arange(1.0, 11.0)
    prediction = truth.copy()
    prediction[-1] += 2.0
    quality = np.ones(10, dtype=bool)
    artificial = np.zeros(10, dtype=bool)
    artificial[-2:] = True
    result = temperature_metrics(
        truth,
        prediction,
        quality,
        artificial,
        high_threshold=9.0,
        ecological_threshold=8.5,
    )
    assert result["ecological_threshold"] == 8.5
    assert result["high_temp_n"] == 2
    assert result["high_temp_mae"] == pytest.approx(1.0)
    assert result["extreme_peak_error"] == pytest.approx(2.0)

    no_ecological_threshold = temperature_metrics(
        truth,
        prediction,
        quality,
        artificial,
        high_threshold=9.0,
    )
    assert np.isnan(no_ecological_threshold["ecological_threshold"])
    assert np.isnan(no_ecological_threshold["threshold_days_bias"])
    assert no_ecological_threshold["heatwave_duration_error"] == 0.0


def test_heatwave_duration_is_limited_to_evaluated_years():
    truth = np.array([10, 10, 10, 10, 10, 0, 0, 10, 10, 10], dtype=float)
    prediction = truth.copy()
    prediction[-3:] = 0.0
    artificial = np.zeros(len(truth), dtype=bool)
    artificial[-3:] = True
    dates = pd.to_datetime(
        [
            *[f"2019-01-{day:02d}" for day in range(1, 8)],
            *[f"2020-01-{day:02d}" for day in range(1, 4)],
        ]
    )
    result = temperature_metrics(
        truth,
        prediction,
        np.ones(len(truth), dtype=bool),
        artificial,
        high_threshold=9.0,
        dates=dates,
    )
    assert result["heatwave_duration_error"] == -3.0
    assert result["heatwave_duration_scope"] == "years_intersecting_artificial_mask"


def test_quantile_coverage_width_pinball_and_crps():
    truth = np.array([1.0, 2.0, 3.0])
    mask = np.ones(3, dtype=bool)
    result = quantile_metrics(
        truth,
        {"q05": truth - 1.0, "q50": truth, "q95": truth + 1.0},
        mask,
        mask,
    )
    assert result["coverage_90"] == pytest.approx(1.0)
    assert result["interval_width_90"] == pytest.approx(2.0)
    assert result["pinball_q50"] == pytest.approx(0.0)
    exact = quantile_metrics(truth, {0.05: truth, 0.5: truth, 0.95: truth}, mask, mask)
    assert exact["approx_crps"] == pytest.approx(0.0)


def test_event_output_fields_and_frame_grouping_align_with_specification():
    row = compute_event_metrics(
        [0.0, 1.0, 2.0, 3.0],
        [99.0, 1.5, 2.5, 3.0],
        [True] * 4,
        [False, True, True, False],
        target="T",
        metadata={
            "scenario_id": "BLK1",
            "station_id": "S1",
            "model": "linear",
            "seed": 7,
            "gap_lengths": [2],
            "variables": ["T"],
        },
    )
    assert set(EVENT_METRIC_COLUMNS).issubset(row)
    assert row["mask_seed"] == 7
    assert row["gap_length"] == 2
    assert row["MAE"] == pytest.approx(0.5)
    assert np.isnan(row["high_temp_threshold"])
    assert np.isnan(row["ecological_threshold"])

    daily = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=4),
            "scenario_id": "BLK1",
            "station_id": "S1",
            "model": "linear",
            "target": "T",
            "y_true": [0.0, 1.0, 2.0, 3.0],
            "y_pred": [100.0, 1.5, 2.5, 3.0],
            "quality_approved": [True] * 4,
            "artificial_mask": [False, True, True, False],
        }
    )
    grouped = event_metrics_from_frame(daily)
    assert len(grouped) == 1
    assert grouped.loc[0, "MAE"] == pytest.approx(0.5)


def test_event_metrics_retain_frozen_catalog_context_and_score_extrema():
    dates = pd.date_range("2020-01-01", periods=7)
    truth = np.array([99.0, 2.0, 10.0, 6.0, 1.0, 4.0, 99.0])
    prediction = np.array([100.0, 3.0, 8.0, 11.0, 4.0, 0.0, 100.0])
    metadata = {
        "station_id": "S1",
        "pair_id": "PAIR-1",
        "anchor_id": "ANCHOR-1",
        "event_id": "EVENT-1",
        "control_id": "CONTROL-1",
        "catalog_role": "event_episode",
        "event_type": "flood",
        "raw_episode_start_index": 1,
        "raw_episode_end_index": 5,
        "raw_episode_start_date": "2020-01-02",
        "raw_episode_end_date": "2020-01-06",
        "raw_episode_length": 5,
        "window_start_index": 0,
        "window_end_index": 6,
        "window_center_index": 3,
        "window_start_date": "2020-01-01",
        "window_end_date": "2020-01-07",
        "window_center_date": "2020-01-04",
        "event_peak_index": 2,
        "event_peak_date": "2020-01-03",
        "event_peak_value": 10.0,
        "event_min_index": 4,
        "event_min_date": "2020-01-05",
        "event_min_value": 1.0,
        "event_intensity": 10.0,
        "event_definition": "training station-season q90 flood process",
        "minimum_duration_days": 1,
        "merge_gap_days": 2,
        "fixed_window_length": 7,
        "episode_component_count": 2,
        "rising_phase_start_index": 1,
        "rising_phase_end_index": 1,
        "rising_phase_start_date": "2020-01-02",
        "rising_phase_end_date": "2020-01-02",
        "recession_phase_start_index": 3,
        "recession_phase_end_index": 5,
        "recession_phase_start_date": "2020-01-04",
        "recession_phase_end_date": "2020-01-06",
        "threshold_reference_scope": "training_station_season",
        "climatology_half_window_days": 7,
        "threshold_doy_half_window_days": 15,
    }
    row = compute_event_metrics(
        truth,
        prediction,
        np.ones(7, dtype=bool),
        np.ones(7, dtype=bool),
        target="X",
        metadata=metadata,
        dates=dates,
    )

    for name, expected in metadata.items():
        assert row[name] == expected
    assert row["peak_error"] == pytest.approx(1.0)
    assert row["timing_error"] == pytest.approx(1.0)
    assert row["event_peak_magnitude_error"] == pytest.approx(1.0)
    assert row["event_peak_timing_error_days"] == pytest.approx(1.0)
    assert row["minimum_error"] == pytest.approx(-1.0)
    assert row["minimum_timing_error"] == pytest.approx(1.0)
    assert row["event_minimum_magnitude_error"] == pytest.approx(-1.0)
    assert row["event_minimum_timing_error_days"] == pytest.approx(1.0)
    assert row["station"] == "S1"
    assert row["event_start"] == "2020-01-02"
    assert row["event_end"] == "2020-01-06"
    assert row["event_length"] == 5
    assert row["matched_control_id"] == "CONTROL-1"


def test_low_flow_minimum_populates_d4_common_extremum_fields():
    row = compute_event_metrics(
        [5.0, 2.0, 1.0, 3.0],
        [5.0, 0.0, 2.0, 3.0],
        [True] * 4,
        [True] * 4,
        target="X",
        metadata={
            "event_type": "low_flow",
            "raw_episode_start_date": "2020-01-01",
            "raw_episode_end_date": "2020-01-04",
            "event_min_date": "2020-01-03",
            "event_min_value": 1.0,
        },
        dates=pd.date_range("2020-01-01", periods=4),
    )

    assert row["minimum_error"] == pytest.approx(-1.0)
    assert row["minimum_timing_error"] == pytest.approx(1.0)
    assert row["peak_error"] == pytest.approx(-1.0)
    assert row["timing_error"] == pytest.approx(1.0)


def test_event_frame_preserves_event_anchor_and_bounds_for_extrema_metrics():
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=5),
            "scenario_id": "M7b-1",
            "station_id": "S1",
            "model": "linear",
            "target": "F",
            "event_id": "EVENT-1",
            "pair_id": "PAIR-1",
            "catalog_role": "event_episode",
            "raw_episode_start_date": "2020-01-02",
            "raw_episode_end_date": "2020-01-04",
            "event_peak_date": "2020-01-03",
            "event_peak_value": 8.0,
            "event_definition": "frozen flood definition",
            "y_true": [0.0, 2.0, 8.0, 3.0, 0.0],
            "y_pred": [99.0, 2.0, 4.0, 9.0, 99.0],
            "quality_approved": True,
            "artificial_mask": True,
        }
    )

    grouped = event_metrics_from_frame(daily)

    assert len(grouped) == 1
    assert grouped.loc[0, "event_id"] == "EVENT-1"
    assert grouped.loc[0, "raw_episode_start_date"] == "2020-01-02"
    assert grouped.loc[0, "event_definition"] == "frozen flood definition"
    assert grouped.loc[0, "peak_error"] == pytest.approx(1.0)
    assert grouped.loc[0, "timing_error"] == pytest.approx(1.0)
