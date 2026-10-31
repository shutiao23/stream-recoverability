from pathlib import Path
import importlib
import json
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
BACKUP = importlib.import_module("388_wrr_natural_backup_validation")
SYSTEM = importlib.import_module("390_wrr_developed_probability_system")
SHORT = importlib.import_module("389_wrr_short_history_backup")
SETTINGS = json.loads((ROOT / "configs/wrr_natural_backup_20261021_v2.json").read_text())


def test_daily_record_conflicts_and_missing_duplicates_have_distinct_outcomes():
    times = pd.date_range("2020-01-01", periods=24, freq="h", tz="UTC")
    frame = pd.DataFrame({"Time_UTC": times.astype(str), "WaterTemperature_Celsius": 10.0})
    # A missing duplicate does not erase a valid instrument observation.
    frame = pd.concat([pd.DataFrame({"Time_UTC": [str(times[0])], "WaterTemperature_Celsius": [np.nan]}), frame], ignore_index=True)
    assert BACKUP.qualified_daily(frame, SETTINGS).iloc[0] == 10
    # Numerous conflicting duplicates remove hourly support rather than averaging.
    conflicts = pd.DataFrame({"Time_UTC": times[:10].astype(str), "WaterTemperature_Celsius": 12.0})
    result = BACKUP.qualified_daily(pd.concat([frame, conflicts]), SETTINGS)
    assert result.isna().all()


def test_complete_calendar_year_is_not_inferred_from_summer_support():
    dates = pd.date_range("2020-01-01", "2020-12-31")
    complete = pd.Series(10.0, index=dates)
    assert BACKUP.complete_years(complete) == [2020]
    assert BACKUP.complete_years(complete.iloc[100:250]) == []


def test_unavailable_distribution_never_becomes_zero_failure_probability():
    frame = pd.DataFrame({"policy_metric": [1.0, 2.0], "local_hot_threshold_C": [2., 2.], "truth_hottest30": [1., 2.],
                          "h30_samples_C": [np.array([1., 1.2]), np.nan]})
    result = SYSTEM.prepare_point(frame, "priority")
    assert result.NN_failure_probability.iloc[0] == 0
    assert pd.isna(result.NN_failure_probability.iloc[1])
    assert not result.cdf_available.iloc[1]


def test_shared_distribution_risk_is_relative_to_the_delivered_point():
    frame = pd.DataFrame({"policy_metric": [10.], "h30_reconstructed": [10.8], "local_hot_threshold_C": [10.5], "truth_hottest30": [10.8],
                          "h30_samples_C": [np.array([10., 10.3, 10.8, 11.2])]})
    priority = SYSTEM.prepare_point(frame, "priority")
    physics = SYSTEM.prepare_point(frame, "air2stream3")
    assert priority.own_failure.iloc[0] and not physics.own_failure.iloc[0]
    assert priority.NN_failure_probability.iloc[0] == .5
    assert physics.NN_failure_probability.iloc[0] == .25
    assert priority.NN_target_abs90.iloc[0] > physics.NN_target_abs90.iloc[0]
    # Changing a hidden outcome changes labels, while deployment probabilities stay fixed.
    frame["truth_hottest30"] = 100
    changed = SYSTEM.prepare_point(frame, "priority")
    assert changed.NN_failure_probability.iloc[0] == priority.NN_failure_probability.iloc[0]
    assert changed.NN_target_abs90.iloc[0] == priority.NN_target_abs90.iloc[0]


def test_developed_ensemble_does_not_use_hidden_reference_values():
    samples = np.ones((1, 32, 365, 2))
    cases = pd.DataFrame([{"mask_positions": ";".join(map(str, range(100, 130))), "scale": 1, "mean": 0}])
    first = np.full(365, 2.)
    changed = first.copy()
    changed[100:130] = 1000
    np.testing.assert_array_equal(SYSTEM.h30_ensembles(samples, cases, [first])[0], SYSTEM.h30_ensembles(samples, cases, [changed])[0])


def test_missing_natural_history_is_reported_without_changing_primary_protocol():
    folder = ROOT / "results/wrr_submission_ready/followup_20261021/natural_backup"
    path = folder / "qualification_summary.json"
    if not path.exists():
        pytest.skip("Natural backup acquisition has not been run")
    summary = json.loads(path.read_text())
    assert summary["n_qualified_pair_years"] == 0
    assert not summary["recovery_errors_used_for_selection"]
    assert summary["reasons"]["fewer_than_three_complete_prior_primary_years"] == 3


def test_repeated_conditional_sampling_preserves_case_and_draw_axes():
    inputs = np.arange(2 * 4).reshape(2, 4, 1).astype(float)
    def predictor(data, n_sampling_times):
        assert n_sampling_times == 1
        return {"imputation": data["X"][:, None]}
    result = SYSTEM.repeated_sample_predict(predictor, {"X": inputs}, 3)["imputation"]
    assert result.shape == (2, 3, 4, 1)
    np.testing.assert_array_equal(result[:, 0], inputs)
    np.testing.assert_array_equal(result[:, 2], inputs)


def test_cold_gap_peak_diagnosis_is_conditional_on_the_declared_bound():
    observed = np.zeros(365)
    observed[150:190] = 20
    observed[10:13] = np.nan
    lower, upper = SHORT.conditional_peak_interval(observed, 100)
    assert lower == upper == 20
    _, very_high_upper = SHORT.conditional_peak_interval(observed, 1000)
    assert very_high_upper > lower


def test_complete_system_keeps_unavailable_points_and_distributions_in_cost_pool(tmp_path, monkeypatch):
    from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION
    roles = {}
    n = 64
    for role in ("development", "calibration", "test"):
        frame = pd.DataFrame({name: np.zeros(n) for name in GENERIC})
        frame["air_available"] = True
        frame["network_id"] = role
        frame["station_id"] = role
        frame["year"] = 2020
        frame["realization_id"] = np.arange(n).astype(str)
        frame["independence_group"] = [f"{role}_{i // 32}" for i in range(n)]
        frame["policy_metric"] = 3.
        frame["h30_reconstructed"] = 3.5
        frame["h30_point"] = 3.2
        frame["truth_hottest30"] = np.tile([3.4, 3.8], n // 2)
        frame["local_hot_threshold_C"] = 3.3
        frame["h30_samples_C"] = [np.tile([3., 3.1, 3.2, 3.5], 8) for _ in range(n)]
        for name in WINDOW_INFORMATION:
            frame[name + "_NN"] = 0.
        roles[role] = frame
    roles["test"].loc[0, "h30_reconstructed"] = np.nan
    roles["test"].at[1, "h30_samples_C"] = np.nan
    monkeypatch.setattr(SYSTEM, "OUT", tmp_path)
    monkeypatch.setattr(SYSTEM, "role_data", lambda role: roles[role].copy())
    SYSTEM.evaluate_system()
    operating = pd.read_csv(tmp_path / "operating.csv")
    costs = pd.read_csv(tmp_path / "decision_costs.csv")
    assert len(operating) == 9 and operating.n_candidates.eq(n).all()
    assert operating.loc[operating.method.eq("air2stream3"), "n_point_available"].eq(n - 1).all()
    counts = costs[["true_positive", "true_negative", "false_positive", "false_negative", "unknown"]].sum(axis=1)
    np.testing.assert_allclose(counts, n)
    records = pd.read_parquet(tmp_path / "admission_cases.parquet")
    assert not records.loc[records.realization_id.eq("1"), "admitted"].any()
    common = costs.loc[costs.policy.eq("direct_calibrated_NN_cost")]
    assert common.groupby(["fn_cost", "abstention_cost"]).loss.nunique().eq(1).all()
