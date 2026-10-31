from pathlib import Path
import importlib
import json
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
J = importlib.import_module("405_wrr_three_method_joint_power")
R = importlib.import_module("386_wrr_joint_power_plan")


@pytest.mark.parametrize("n,alpha", [(16, .005), (120, .005 / 21), (7680, .005)])
def test_direct_kl_decision_matches_the_frozen_root_bound(n, alpha):
    means = np.r_[0, np.linspace(.0001, .08, 200), .5, 1]
    expected = [R.bounded_mean_upper(float(value), n, alpha=alpha) <= .05 for value in means]
    np.testing.assert_array_equal(J.bounded_mean_below_cap(means, n, .05, alpha), expected)


def test_candidate_must_beat_native_cdf_as_well_as_boosted_direct_reference():
    counts = np.array([50000, 50000])
    good = np.array([[.3, .3], [.2, .2], [.8, .8]])
    result = J.joint_evidence(good, np.zeros_like(good), counts, .05, .05, .005, .01)
    assert result["true_joint_success"]
    weaker_only = good.copy()
    weaker_only[0] = .9
    result = J.joint_evidence(weaker_only, np.zeros_like(good), counts, .05, .05, .005, .01)
    assert not result["joint_pass"] and not result["population_target_met"]


def test_failure_of_any_reference_risk_or_zero_admission_prevents_joint_success():
    a = np.array([[.3, .3], [.2, .2], [.8, .8]])
    b = np.zeros_like(a)
    b[0] = .03
    assert not J.joint_evidence(a, b, [50000, 50000], .05, .05, .005, .01)["joint_pass"]
    a[0] = 0
    b[0] = 0
    result = J.joint_evidence(a, b, [50000, 50000], .05, .05, .005, .01)
    assert not result["positive_admission_all_three"] and not result["joint_pass"]
    with pytest.raises(ValueError, match="paired group"):
        J.joint_evidence(a[:, :1], b[:, :1], [50000, 50000], .05, .05, .005, .01)


def test_formal_calibration_matches_frozen_group_ratio_selection():
    a = np.array([[0, 10, 20], [0, 4, 20]])
    b = np.array([[0, 0, 1], [0, 0, 4]])
    totals = np.array([20, 20])
    for n in [16, 120, 3840]:
        composition = np.array([n // 2, n - n // 2])
        assert J.choose_formal(a, b, totals, composition, n, .05, .005) == R.formal_index(a, b, totals, composition, n, .05, .005)


def test_all_three_risk_and_two_gain_comparisons_share_the_error_budget():
    settings = json.loads(J.CONFIG.read_text())
    alpha = settings["alpha_allocation"]
    assert 3 * alpha["formal_calibration_per_method"] + 3 * alpha["evaluation_risk_per_method"] + 2 * alpha["paired_gain_per_reference"] == pytest.approx(settings["familywise_alpha"])
    assert settings["required_references"] == ["native_CDF", "boost_direct"]
    assert not settings["new_AU_test_errors_permitted"]
