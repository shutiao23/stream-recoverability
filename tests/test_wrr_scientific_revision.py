"""Scientific boundary cases for the 2026-10-20c revision."""

import numpy as np
import pytest

from stream_recoverability.experiments.v19_revision.risk import (
    bounded_mean_upper,
    fixed_training_candidates,
    select_group_threshold,
)
from stream_recoverability.experiments.v19_revision.design import event_relative_designs, paired_gap_designs
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.trajectory import (
    block_residual_draws,
    conditional_trajectories,
    error_channels,
    historical_location_adjustment,
    trajectory_features,
)
from stream_recoverability.experiments.v19_revision.learning import feature_matrix, group_roles, specifications
from stream_recoverability.experiments.v19_revision.partial_identification import observed_h30_lower_bound, observationally_resolved_hot


def test_no_failures_in_twelve_groups_does_not_certify_six_percent_counterexample():
    result = select_group_threshold(
        np.zeros(240), np.zeros(240, dtype=bool), np.repeat(np.arange(12), 20), np.array([0.0])
    )
    assert result.status == "insufficient_independent_calibration_evidence"
    assert result.threshold == -np.inf
    assert result.bounded_loss_upper[0] == pytest.approx(1 - 0.05 ** (1 / 12))


def test_duplicating_masks_within_a_group_does_not_create_independent_evidence():
    scores = np.array([0.0, 0.5, 1.0, 0.2])
    failures = np.array([False, False, True, False])
    groups = np.array(["a", "b", "c", "d"])
    original = select_group_threshold(scores, failures, groups, np.array([0.1, 0.7, 1.0]))
    duplicated = select_group_threshold(
        np.repeat(scores, 25), np.repeat(failures, 25), np.repeat(groups, 25), np.array([0.1, 0.7, 1.0])
    )
    np.testing.assert_allclose(original.bounded_loss_upper, duplicated.bounded_loss_upper)
    assert original.n_groups == duplicated.n_groups == 4


def test_sufficient_independent_zero_failure_groups_can_certify_admission():
    result = select_group_threshold(np.zeros(100), np.zeros(100, dtype=bool), np.arange(100), np.array([0.0]))
    assert result.status == "certified"
    assert result.threshold == 0
    assert result.bounded_loss_upper[0] < 0.05


def test_failure_above_cap_cannot_pass_bound_even_with_many_groups():
    failures = np.arange(1000) < 60
    result = select_group_threshold(np.zeros(1000), failures, np.arange(1000), np.array([0.0]))
    assert result.status == "insufficient_independent_calibration_evidence"
    assert result.selected_risk[0] == pytest.approx(0.06)


def test_missing_scores_are_abstentions_with_their_group_denominator_retained():
    result = select_group_threshold(
        np.array([0.0, np.nan]), np.array([False, True]), np.array(["a", "a"]), np.array([0.0])
    )
    assert result.retention[0] == 0.5
    assert result.selected_risk[0] == 0


def test_group_upper_bound_is_positive_at_zero_and_respects_range():
    assert 0 < bounded_mean_upper(0, 100, alpha=0.05) < 0.05
    assert bounded_mean_upper(1, 100, alpha=0.05) == 1
    assert bounded_mean_upper(0.02, 100, alpha=0.05) > 0.02
    assert bounded_mean_upper(0.999, 1, alpha=0.001) == 1


def test_candidate_family_is_determined_only_from_explicit_training_scores():
    np.testing.assert_array_equal(fixed_training_candidates(np.array([0, 0, 1, 2]), 3), np.array([0, 2]))
    with pytest.raises(ValueError):
        fixed_training_candidates(np.array([np.nan]))


def test_positive_switch_increment_can_compensate_for_hidden_peak_underestimation():
    truth = np.concatenate([np.full(30, 25.0), np.full(30, 10.0), np.full(30, 24.8)])
    completed = truth.copy()
    completed[:30] = 24
    result = error_channels(truth, completed)
    assert result["hidden_channel_C"] == pytest.approx(-1)
    assert result["window_switch_increment_C"] == pytest.approx(0.8)
    assert result["error_C"] == pytest.approx(-0.2)
    assert result["switch_state"] == "switch_without_overestimation"


def test_conditional_trajectories_preserve_every_observed_day():
    observed = np.linspace(5, 20, 365)
    observed[170:200] = np.nan
    center = np.full(365, 10.0)
    residuals = np.sin(np.arange(1000) / 10)
    draws = conditional_trajectories(observed, center, residuals, seed=42)
    available = np.isfinite(observed)
    np.testing.assert_array_equal(draws[:, available], np.broadcast_to(observed[available], (128, available.sum())))
    features = trajectory_features(draws, ~available, 20.0)
    assert 0 <= features["probabilistic_hidden_support"] <= 1
    assert features["h30_interval_width_C"] >= 0


def test_training_residual_blocks_do_not_bridge_missing_history():
    residuals = np.concatenate([np.arange(20.0), [np.nan], np.arange(100.0, 120.0)])
    draws = block_residual_draws(residuals, 14, n_draws=100, block_days=14, rng=np.random.default_rng(1))
    np.testing.assert_array_equal(np.diff(draws, axis=1), np.ones((100, 13)))


def test_deployable_location_adjustment_uses_only_visible_anchors():
    center = np.zeros(365)
    observed = np.full(365, np.nan)
    observed[:30] = 2
    assert historical_location_adjustment(observed, center) == pytest.approx(1)


def test_crossed_design_holds_length_and_total_budget_and_preserves_empty_cells():
    support = np.zeros(365, dtype=bool)
    support[190:220] = True
    warm = np.zeros(365, dtype=bool)
    warm[120:275] = True
    designs, empty = paired_gap_designs(support, warm, seed=42, lengths=(14, 30, 60, 90))
    assert any(item["length"] == 14 and item["overlap_class"] == "full" for item in empty)
    for design in designs:
        assert design.mask.sum() == design.length
        assert not design.mask[0] and not design.mask[-1]
    contiguous = [design for design in designs if design.family == "crossed_contiguous" and design.length == 30]
    assert len(contiguous) == 12
    assert {design.overlap_class for design in contiguous} == {"none", "partial", "full"}


def test_station_scoped_forcing_preserves_station_priority_and_network_fallback(tmp_path):
    import pandas as pd

    path = tmp_path / "forcing.parquet"
    dates = pd.date_range("2020-01-01", periods=2)
    frame = pd.DataFrame({"date": list(dates) * 2, "network_id": ["network"] * 4, "station_id": ["a", "a", "b", "b"], "air_temperature_c": [1.0, 2.0, 3.0, 4.0]})
    frame.to_parquet(path, index=False)
    np.testing.assert_array_equal(station_air_series(path, "network", "a", dates), [1.0, 2.0])
    np.testing.assert_array_equal(station_air_series(path, "network", "absent", dates), [2.0, 3.0])
    assert station_air_series(path, "absent", "absent", dates) is None


def test_learning_splits_never_use_one_group_for_fitting_and_calibration_or_testing():
    groups = np.repeat(np.arange(50), 10).astype(str)
    test_counts = {str(group): 0 for group in range(50)}
    for fold in range(5):
        roles = group_roles(groups, 101, fold)
        assert set(roles.values()) == {"train", "calibration", "test"}
        for group, role in roles.items():
            test_counts[group] += role == "test"
    assert set(test_counts.values()) == {1}


def test_deployment_feature_allowlist_rejects_hidden_truth_and_errors():
    import pandas as pd

    with pytest.raises(ValueError):
        feature_matrix(pd.DataFrame({"truth_hottest30": [20.0]}), ("truth_hottest30",))
    for name, (features, kind) in specifications().items():
        assert "true_peak_hidden_fraction" not in features
        assert "abserr_policy" not in features


def test_event_replay_moves_equal_gaps_before_during_and_after_same_episode():
    events = np.zeros(365, dtype=bool)
    events[190:200] = True
    support = np.zeros(365, dtype=bool)
    support[185:215] = True
    designs, empty = event_relative_designs(events, support)
    assert not empty
    assert len(designs) == 9
    for design in designs:
        assert design.mask.sum() == design.length
        if "before" in design.key or "after" in design.key:
            assert not (design.mask & events).any()
        else:
            assert (design.mask & events).sum() == events.sum()


def test_observed_complete_window_is_a_lower_bound_without_locating_true_peak():
    rng = np.random.default_rng(42)
    for repeat in range(100):
        truth = rng.normal(15, 5, size=365)
        observed = truth.copy()
        observed[rng.random(365) < 0.05] = np.nan
        bound = observed_h30_lower_bound(observed)
        true_peak = max(np.convolve(truth, np.ones(30) / 30, mode="valid"))
        assert bound <= true_peak + 1e-10


def test_eighty_percent_window_mean_cannot_be_used_as_a_verified_hot_lower_bound():
    truth = np.r_[np.full(24, 25.0), np.zeros(6)]
    observed = truth.copy()
    observed[24:] = np.nan
    assert np.nanmean(observed) > 22
    assert truth.mean() < 22
    assert observed_h30_lower_bound(observed) == -np.inf
    assert not observationally_resolved_hot(observed_h30_lower_bound(observed), 22)


def test_observed_hot_rescue_respects_measurement_margin_and_does_not_resolve_cool():
    assert observationally_resolved_hot(20.3, 20, measurement_margin_c=0.2)
    assert not observationally_resolved_hot(20.1, 20, measurement_margin_c=0.2)
    assert not observationally_resolved_hot(19, 20)


def test_compiled_process_equations_match_existing_published_implementations():
    import pandas as pd
    from stream_recoverability.experiments.air2stream_equivalent import simulate_air2stream3, simulate_air2stream8
    from stream_recoverability.experiments.v19_revision.process import simulate_eight, simulate_three

    index = pd.date_range("2019-01-01", periods=730)
    air = 10 + 8 * np.sin(np.arange(730) / 365 * 2 * np.pi)
    discharge = 5 + np.cos(np.arange(730) / 365 * 2 * np.pi)
    short_parameters = np.array([1.0, 0.9, 5.0])
    parameters = np.array([0.0, 0.5, 0.5, 0.1, 0.5, 0.5, 0.5, 0.1])
    np.testing.assert_allclose(simulate_three(index, air, short_parameters, initial_water_temperature_c=7), simulate_air2stream3(index, air, short_parameters, initial_water_temperature_c=7), atol=1e-10, rtol=1e-10)
    np.testing.assert_allclose(simulate_eight(index, air, discharge, parameters, initial_water_temperature_c=7, discharge_reference=5), simulate_air2stream8(index, air, discharge, parameters, initial_water_temperature_c=7, discharge_reference=5), atol=1e-10, rtol=1e-10)


def test_short_interpolation_uncertainty_uses_complete_short_residual_runs():
    residuals = np.full(365 * 3, np.nan)
    residuals[[50, 400, 800]] = [-0.1, 0.0, 0.1]
    observed = np.zeros(365)
    observed[190] = np.nan
    center = np.zeros(365)
    draws = conditional_trajectories(observed, center, residuals, seed=42)
    assert np.isfinite(draws).all()
    assert draws[:, 190].std() > 0
    observed[190:220] = np.nan
    with pytest.raises(ValueError):
        conditional_trajectories(observed, center, residuals, seed=42)


def test_joint_certificate_delivery_does_not_read_hidden_truth_for_choice():
    import pandas as pd
    from stream_recoverability.experiments.v17_fitness.screen import SCREEN_FEATURES, SCREENED_ESTIMATORS
    from stream_recoverability.experiments.v19_revision.learning import certificate_delivery

    class FixedChoice:
        def predict(self, frame):
            assert "truth_hottest30" not in frame
            return pd.DataFrame({"certificate_choice": ["doy_climatology", "linear_interp"]}, index=frame.index)

    frame = pd.DataFrame({name: [1.0, 1.0] for name in SCREEN_FEATURES})
    frame["network_id"] = "network"
    frame["longest_run_month"] = 6
    for method in SCREENED_ESTIMATORS:
        frame[f"hottest30_{method}"] = [20.0, 21.0] if method == "doy_climatology" else [22.0, 23.0]
    first = certificate_delivery(FixedChoice(), frame)
    frame["truth_hottest30"] = [100.0, -100.0]
    second = certificate_delivery(FixedChoice(), frame)
    np.testing.assert_array_equal(first.policy_metric, [20.0, 23.0])
    np.testing.assert_array_equal(first.policy_metric, second.policy_metric)
    assert second.policy_bad.all()


def test_hydrological_snow_share_uses_percent_units():
    import pandas as pd
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from wrr_r3_hydrology import hydrological_strata

    frame = pd.DataFrame({"Glaciers %": [0, 0, 2, 0, np.nan], "Pt as snow": [27.4, 50, 20, np.nan, np.nan]})
    assert hydrological_strata(frame).tolist() == ["other_mountain_catchment", "snow_dominated", "glacier_influenced", "unknown_hydrological_attributes", "unknown_hydrological_attributes"]
