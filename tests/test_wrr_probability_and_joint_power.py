from pathlib import Path
import importlib
import json
import sys

import numpy as np
import pandas as pd
import pytest
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
P = importlib.import_module("385_wrr_probability_development")
J = importlib.import_module("386_wrr_joint_power_plan")


def test_target_year_hidden_values_cannot_change_normalizers_or_visible_input():
    dates = pd.date_range("2000-01-01", "2003-12-31")
    values = pd.Series(np.sin(np.arange(len(dates)) / 20), index=dates)
    target_dates = dates[dates.year == 2003]
    changed = values.copy()
    changed.loc[target_dates[100:130]] += 1000
    first, mean, scale = P.standardize(values, 2003, target_dates)
    second, other_mean, other_scale = P.standardize(changed, 2003, target_dates)
    assert mean == other_mean and scale == other_scale
    first[100:130] = second[100:130] = np.nan
    np.testing.assert_allclose(first, second, equal_nan=True)


def test_unavailable_air_is_not_invented():
    dates = pd.date_range("2000-01-01", periods=366)
    values, mean, scale = P.standardize(pd.Series(np.nan, index=dates), 2000, dates)
    assert np.isnan(values).all() and mean == 0 and scale == 1


@pytest.mark.parametrize("name,length", [("peak30", 30), ("peak90", 90), ("start60", 60), ("end60", 60), ("fragmented60", 60)])
def test_development_masks_have_explicit_boundary_and_fragment_support(name, length):
    mask = P.mask_design(name, 365, 170)
    assert mask.sum() == length
    if name == "start60":
        assert mask[0] and not mask[-1]
    if name == "end60":
        assert mask[-1] and not mask[0]
    if name == "fragmented60":
        assert (mask & ~np.r_[False, mask[:-1]]).sum() == 2


def test_probability_scenarios_preserve_observed_values_before_h30():
    samples = np.full((1, 32, 366, 2), 100.0)
    samples[:, :, 100:130, 0] = 2
    cases = pd.DataFrame([{"n_days": 366, "mean": 0, "scale": 1, "truth_h30": 1, "mask_positions": ";".join(map(str, range(100, 130)))}])
    result = P.prediction_rows(samples, cases, [np.ones(366)])
    assert result.h30_point.iloc[0] == pytest.approx(2)
    assert result.crps_C.iloc[0] == pytest.approx(1)


def test_group_count_kernel_handles_unavailable_scores_and_equal_thresholds():
    frame = pd.DataFrame({"independence_group": ["a", "a", "b", "b"], "policy_bad": [False, True, True, True]})
    accepted, failed, totals, groups = J.group_counts(frame, [.1, .9, .2, np.inf], [.15, .2, 1])
    np.testing.assert_array_equal(accepted, [[1, 1, 2], [0, 1, 1]])
    np.testing.assert_array_equal(failed, [[0, 0, 1], [0, 1, 1]])
    np.testing.assert_array_equal(totals, [2, 2])
    assert groups == ["a", "b"]


def test_simulated_formal_budget_requires_sufficient_independent_draws():
    accepted = np.full((2, 3), 10)
    failed = np.zeros((2, 3))
    totals = np.array([10, 10])
    assert J.formal_index(accepted, failed, totals, [30, 30], 60, .05, .005) is None
    assert J.formal_index(accepted, failed, totals, [500, 500], 1000, .05, .005) == 2


def test_paired_gain_bound_controls_the_exact_binary_tail():
    n, p, alpha = 200, .6, .02
    true_mean = 2 * p - 1
    lower = J.hoeffding_gain_lower(2 * np.arange(n + 1) / n - 1, n, alpha)
    probability_of_wrong_lower_bound = binom.pmf(np.arange(n + 1), n, p)[lower > true_mean].sum()
    assert probability_of_wrong_lower_bound <= alpha
    assert J.hoeffding_gain_lower(.1, 118, alpha) < .05


def test_planning_alpha_is_shared_across_both_models_and_gain():
    config = json.loads((ROOT / "configs/wrr_joint_power_20261021.json").read_text())
    a = config["alpha_allocation"]
    assert 2 * a["formal_calibration_per_model"] + 2 * a["test_risk_per_model"] + a["paired_gain"] == pytest.approx(config["familywise_alpha"])
    assert "not_new_observations" in config["status"]
