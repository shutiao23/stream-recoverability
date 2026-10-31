from pathlib import Path
import importlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
F = importlib.import_module("416_wrr_state_risk_factorial")


def test_random_rejection_preserves_original_truth_counts_and_candidate_denominator():
    frame = pd.DataFrame({"truth_hottest30": [2., 2., 0., 0.], "local_hot_threshold_C": [1.] * 4,
                          "reconstruction_point": [2., 0., np.nan, 3.]})
    settings = {"false_negative_costs": [5], "abstention_costs": [.05]}
    rows = pd.DataFrame(F.decision_rows({"n_candidates": 4}, frame, np.array([True, False, False, False]),
                                       np.array([.8, .4, .1, .2]), settings)).set_index("policy")
    assert rows.n_candidates.eq(4).all() and rows.true_hot.eq(2).all()
    np.testing.assert_allclose(rows[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1), 4)
    assert rows.loc["random_matched_screen", "unknown"] == 3
    expected = rows.loc["reconstruct_all", "loss"] / 3 + 2 * .05 / 3
    assert rows.loc["random_matched_screen", "loss"] == pytest.approx(expected)


def test_matched_support_cannot_change_candidate_order_or_erase_unavailable_cases():
    first = pd.DataFrame({"network_id": ["a", "a"], "station_id": ["s", "s"], "year": [2000, 2001],
                          "realization_id": ["one", "two"], "cdf_available": [True, True], "reconstruction_point": [10., 11.]})
    second = first.copy(); second.loc[1, "cdf_available"] = False
    np.testing.assert_array_equal(F.common_support({"one": first, "two": second}, ["one", "two"]), [True, False])
    assert len(first) == len(second) == 2
    with pytest.raises(RuntimeError, match="ordering"):
        F.common_support({"one": first, "two": second.iloc[::-1]}, ["one", "two"])
