import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.v19_revision.state_trajectory import state_conditioned_draws, sample_crps


def test_empirical_crps_matches_pair_definition():
    samples = np.array([3, -2, 0, 0.5])
    expected = np.abs(samples - 1).mean() - np.abs(samples[:, None] - samples).mean() / 2
    assert sample_crps(samples, 1) == pytest.approx(expected)


def test_state_scenarios_exclude_target_and_preserve_observations():
    history = pd.date_range("2000-01-01", "2003-12-31")
    residuals = np.sin(np.arange(len(history)) / 20) + (history.year.to_numpy() - 2001) * 0.2
    residuals[history.year == 2003] = np.nan
    dates = history[history.year == 2003]
    center = np.full(len(dates), 10.0)
    observed = center.copy()
    observed[100:190] = np.nan
    draws = state_conditioned_draws(observed, center, dates, residuals, history, seed=1, n_draws=32)
    np.testing.assert_array_equal(draws[:, :100], np.full((32, 100), 10))
    assert np.isfinite(draws).all()
    assert np.std(draws[:, 100:190].mean(axis=1)) > 0.05
    residuals[-1] = 1
    with pytest.raises(ValueError, match="Target-year"):
        state_conditioned_draws(observed, center, dates, residuals, history, seed=1)
