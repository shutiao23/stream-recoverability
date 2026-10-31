from pathlib import Path
import importlib
import json
import sys

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
B = importlib.import_module("393_wrr_developed_calibration_budget")
SETTINGS = json.loads((ROOT / "configs/wrr_developed_calibration_budget_20261021.json").read_text())


def fixture_data():
    return {"cal_groups": np.array(["a", "a", "b", "b"]), "cal_failure": np.array([False, False, True, True]),
            "cal_truth_hot": np.array([False, False, True, True]), "cal_hot_probability": np.array([.1, .2, .8, .9]),
            "test_hot_probability": np.array([.1, np.nan, .9]), "test_cdf_available": np.array([True, False, True]),
            "test_point_available": np.array([True, True, False]), "test_point_hot": np.array([False, False, True]),
            "test_truth_hot": np.array([False, True, True]), "test_failure": np.array([False, True, False]),
            "test_groups": np.array(["x", "x", "y"]),
            "scores": {"native_CDF": {"cal": np.array([.1, .1, .9, .9]), "test": np.array([.1, .1, .1]), "candidates": np.array([.1, .9])}}}


def test_all_calibration_group_subsets_are_included_despite_repeated_cases():
    groups = np.repeat(np.arange(9).astype(str), 10)
    subsets = B.group_subsets(groups, [3, 5, 7, 9])
    assert len(subsets) == 247
    assert [sum(n == size for n, _ in subsets) for size in [3, 5, 7, 9]] == [84, 126, 36, 1]
    assert len({(n, tuple(ids)) for n, ids in subsets}) == 247


@pytest.mark.parametrize("budget", [0, 10])
def test_calibration_budget_cannot_invent_observed_groups(budget):
    with pytest.raises(ValueError):
        B.group_subsets(np.arange(9), [budget])


def test_budget_sensitivity_keeps_missing_distributions_and_points_unknown():
    row = B.evaluate_subset(fixture_data(), ("a",), SETTINGS)[0]
    assert row["n_candidates"] == 3
    assert row["accepted"] == 1 and row["failed"] == 0
    assert row["unknown"] == 2 and row["formal_accepted"] == 0
    assert sum(row[k] for k in ("true_positive", "true_negative", "false_positive", "false_negative", "unknown")) == 3
    assert row["magnitude_screen_loss"] == pytest.approx(2 * .05 / 3)


def test_no_returned_magnitudes_have_no_estimated_numeric_risk():
    data = fixture_data()
    data["scores"]["native_CDF"]["test"][:] = np.inf
    row = B.evaluate_subset(data, ("a",), SETTINGS)[0]
    assert row["accepted"] == 0 and np.isnan(row["risk"]) and np.isnan(row["equal_group_risk"])
    assert row["unknown"] == row["n_candidates"]


def test_summary_excludes_undefined_risks_and_reports_empty_subsets():
    data = pd.DataFrame({"calibration_groups": [3, 3], "score_kind": ["native_CDF", "native_CDF"], "accepted": [0, 1],
                         "formal_accepted": [0, 0], "retention": [0., .5], "risk": [np.nan, .1],
                         "magnitude_screen_loss": [.05, .04], "direct_calibrated_CDF_loss": [.05, .05]})
    row = B.summary(data).iloc[0]
    assert row.subsets == 2 and row.nonempty_subsets == 1
    assert row.risk_median == .1 and row.retention_median == .25


def test_next_confirmation_requires_both_strong_references_with_shared_alpha():
    spec = yaml.safe_load((ROOT / "configs/wrr_next_confirmation_20261021.yaml").read_text())
    assert len(spec["direct_reference_family"]) == 2
    assert "native_conditional_CDF_tolerance_exceedance_probability" in spec["direct_reference_family"]
    assert "against_each_direct_reference" in spec["joint_success"][1]
    a = spec["joint_error_allocation"]
    assert a["methods"] == 3 and a["direct_references"] == 2
    total = a["methods"] * (a["formal_calibration_per_method"] + a["evaluation_risk_per_method"]) + a["direct_references"] * a["paired_gain_per_direct_reference"]
    assert total == pytest.approx(spec["familywise_alpha"])
    assert not spec["sample_size"]["current_source_planning"]["covers_new_two_reference_joint_procedure"]
