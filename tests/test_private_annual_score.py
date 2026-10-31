import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    "private_annual_score", Path(__file__).resolve().parents[1] / "scripts/576_verify_private_annual_predictions.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_quadrature_respects_bound_and_has_normal_tails():
    quantiles = np.array([[-2., -1., 0., 1., 2., 3., 4.], [5.] * 7])
    samples, clipped = audit.quadrature(quantiles, np.array([0.5, 5.]))
    assert np.all(samples >= np.array([0.5, 5.])[:, None])
    assert np.all(samples[1] == 5.)
    assert np.all(clipped[0] >= 0.5)
    unbounded, _ = audit.quadrature(quantiles[:1], np.array([np.nan]))
    assert unbounded[0, 0] < quantiles[0, 0]
    assert unbounded[0, -1] > quantiles[0, -1]


def test_crps_and_tail_crps_for_degenerate_forecast():
    samples = np.full((2, 128), 5.)
    truth = np.array([5., 7.])
    np.testing.assert_allclose(audit.crps(samples, truth), [0., 2.])
    np.testing.assert_allclose(audit.crps(samples, truth, np.array([6., 6.])), [0., 1.])


def test_comparison_detects_changed_score_and_accepts_matching_missing_values():
    source = pd.DataFrame({"seed": [0, 1], "score": [1., np.nan]})
    assert audit.compare(source, source.copy(), ["seed"], ["score"]) == 2
    altered = source.copy()
    altered.loc[0, "score"] = 1.1
    with pytest.raises(ValueError, match="score differs"):
        audit.compare(altered, source, ["seed"], ["score"])
