"""Post-review matched learners and explicit three-action decision losses.

These are supplementary analyses on opened data, not a new confirmation.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression

from .learning import ConstantProbability, feature_matrix


def fit_matched(frame, features, response, *, objective, seed):
    parameters = dict(max_depth=4, max_iter=350, learning_rate=0.06,
                      min_samples_leaf=40, random_state=seed)
    matrix = feature_matrix(frame, features)
    response = np.asarray(response)
    if objective == "quantile":
        return HistGradientBoostingRegressor(loss="quantile", quantile=0.9,
                                            **parameters).fit(matrix, response)
    if objective != "probability":
        raise ValueError(f"Unknown objective {objective}")
    if len(np.unique(response)) == 1:
        return ConstantProbability(float(response[0]))
    return HistGradientBoostingClassifier(loss="log_loss", **parameters).fit(matrix, response)


def predict_matched(model, frame, features, *, objective):
    matrix = feature_matrix(frame, features)
    return model.predict(matrix) if objective == "quantile" else model.predict_proba(matrix)[:, 1]


def probability_calibration(calibration_probability, response, test_probability):
    """Platt calibration on groups disjoint from fitting and evaluation."""
    response = np.asarray(response, dtype=int)
    if not len(response):
        raise ValueError("Calibration must contain labelled observations")
    if len(np.unique(response)) < 2:
        # Jeffreys smoothing avoids declaring certainty from one-class calibration.
        return np.full(len(test_probability), (response.sum() + 0.5) / (len(response) + 1))

    def logit(values):
        p = np.clip(values, 1e-6, 1 - 1e-6)
        return (np.log(p) - np.log1p(-p)).reshape(-1, 1)

    model = LogisticRegression(C=1, max_iter=2000)
    model.fit(logit(calibration_probability), response)
    return model.predict_proba(logit(test_probability))[:, 1]


def cost_action(probability, false_negative_cost, abstention_cost):
    """Actions 0=cool, 1=hot, 2=unknown; ties prefer returning information."""
    p = np.asarray(probability, dtype=float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Probabilities must be finite in [0,1]")
    if false_negative_cost < 0 or abstention_cost < 0:
        raise ValueError("Costs must be nonnegative")
    return np.argmin(np.column_stack([false_negative_cost * p, 1 - p,
                                     np.full(len(p), abstention_cost)]), axis=1)


def action_loss(action, truth_hot, false_negative_cost, abstention_cost):
    action, truth = np.asarray(action), np.asarray(truth_hot, dtype=bool)
    if action.shape != truth.shape or not np.isin(action, [0, 1, 2]).all():
        raise ValueError("Actions and truth must be matching vectors")
    return (false_negative_cost * ((action == 0) & truth)
            + ((action == 1) & ~truth) + abstention_cost * (action == 2))


def action_counts(action, truth_hot):
    action, truth = np.asarray(action), np.asarray(truth_hot, dtype=bool)
    return {"n_candidates": len(action), "true_hot": int(truth.sum()),
            "true_positive": int(((action == 1) & truth).sum()),
            "true_negative": int(((action == 0) & ~truth).sum()),
            "false_negative": int(((action == 0) & truth).sum()),
            "false_positive": int(((action == 1) & ~truth).sum()),
            "unknown": int((action == 2).sum())}
