import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.v19_revision.target_risk_laws import (
    adjust_neural_draws, residual_law_draws, restore_neural_draws, tolerance_features,
)
from stream_recoverability.experiments.v19_revision.trajectory import window_means


def history():
    dates = pd.date_range("2000-01-01", "2003-12-31")
    residuals = np.sin(np.arange(len(dates)) / 20) + (dates.year.to_numpy() - 2001) * .2
    residuals[dates.year == 2003] = np.nan
    target = dates[dates.year == 2003]
    center = np.full(len(target), 10.)
    observed = center.copy(); observed[100:190] = np.nan
    states = np.column_stack([np.sin(np.arange(len(dates)) / 100), np.cos(np.arange(len(dates)) / 70)])
    return dates, residuals, target, center, observed, states


def test_air_only_distribution_is_invariant_to_every_discharge_state_value():
    dates, residuals, target, center, observed, states = history()
    first = residual_law_draws("seasonal_air_slow", observed, center, target, residuals, dates,
                               history_states=states, target_states=states[-len(target):], seed=17, n_draws=32)
    changed = states.copy(); changed[:, 1] = np.arange(len(changed)) * 10000
    second = residual_law_draws("seasonal_air_slow", observed, center, target, residuals, dates,
                                history_states=changed, target_states=changed[-len(target):], seed=17, n_draws=32)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first[:, :100], np.broadcast_to(observed[:100], (32, 100)))


def test_native_failure_probability_uses_the_delivered_point_not_a_cdf_median():
    samples = np.array([10., 10.1, 10.2, 10.3])
    assert tolerance_features(samples, 0.)["CDF_failure_probability"] == 1.
    assert tolerance_features(samples, 10.15)["CDF_failure_probability"] == 0.
    assert tolerance_features(np.array([.5, -.5, .500001]), 0.)["CDF_failure_probability"] == pytest.approx(1 / 3)
    assert np.isnan(tolerance_features(np.array([np.nan]), 0.)["CDF_failure_probability"])


def test_neural_cache_replay_and_visible_adjustment_keep_observations_and_sample_identity():
    observed = np.full(365, 10.); observed[100:190] = np.nan
    normalized = np.zeros((3, 366, 2), dtype=np.float32)
    normalized[:, 100:190, 0] = np.array([1., 2., 3.])[:, None]
    expected_paths = normalized[:, :365, 0].astype(float) + 10
    expected_paths[:, np.isfinite(observed)] = observed[np.isfinite(observed)]
    expected = window_means(expected_paths).max(axis=1)
    draws = restore_neural_draws(normalized, observed, 10., 1., expected)
    with pytest.raises(ValueError, match="reproduce"):
        restore_neural_draws(normalized, observed, 10., 1., expected + 1)
    adjusted = adjust_neural_draws(draws, observed, np.full(365, 9.))
    np.testing.assert_array_equal(adjusted[:, :100], draws[:, :100])
    assert (adjusted[:, 100:190] > draws[:, 100:190]).all()
