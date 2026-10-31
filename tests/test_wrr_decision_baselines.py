import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.v19_revision.decision_baselines import (
    action_counts, action_loss, cost_action, fit_matched, probability_calibration,
)


def test_cost_rule_minimizes_each_conditional_loss():
    p = np.linspace(0, 1, 101)
    for fn_cost in (1, 5, 10):
        for abstention_cost in (0, 0.05, 0.25, 1):
            action = cost_action(p, fn_cost, abstention_cost)
            losses = np.column_stack([fn_cost * p, 1 - p, np.full(len(p), abstention_cost)])
            np.testing.assert_allclose(losses[np.arange(len(p)), action], losses.min(axis=1))


def test_counts_and_loss_preserve_original_pool():
    action = np.array([0, 0, 1, 1, 2, 2])
    truth = np.array([0, 1, 0, 1, 0, 1])
    counts = action_counts(action, truth)
    assert sum(counts[k] for k in ("true_positive", "true_negative", "false_negative", "false_positive", "unknown")) == len(truth)
    assert action_loss(action, truth, 5, 0.1).sum() == pytest.approx(6.2)


def test_one_class_calibration_remains_uncertain():
    result = probability_calibration(np.array([0.1, 0.3]), [0, 0], [0, 0.5, 1])
    np.testing.assert_allclose(result, 1 / 6)


def test_truth_cannot_be_model_feature():
    with pytest.raises(ValueError, match="Truth"):
        fit_matched(pd.DataFrame({"truth_hottest30": [1, 2]}), ("truth_hottest30",), [0, 1], objective="probability", seed=1)


def test_reject_invalid_probabilities():
    with pytest.raises(ValueError):
        cost_action([np.nan], 5, 0.05)
