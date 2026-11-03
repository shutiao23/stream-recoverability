"""Nested random-stream checks for the pathwise Gaussian AR(1) bridge."""

import numpy as np

from stream_recoverability.experiments.tr_revision.baselines import (
    ar1_bridge,
    ar1_bridge_pathwise,
)


def _synthetic_case(n=180, seed=20261102):
    rng = np.random.default_rng(seed)
    residual = np.zeros(n)
    for t in range(1, n):
        residual[t] = 0.85 * residual[t - 1] + rng.normal(0.0, 0.5)
    mean = 10.0 + 2.0 * np.sin(np.arange(n) / 17.0)
    observed = mean + rng.normal(0.0, 0.3, size=n)
    observed[:5] = np.nan
    observed[40:67] = np.nan
    observed[-8:] = np.nan
    return observed, mean, residual


def test_pathwise_prefix_matches_larger_ensemble_exactly():
    observed, mean, residual = _synthetic_case()
    prefix = ar1_bridge_pathwise(observed, mean, residual, seed=7, draws=20)
    full = ar1_bridge_pathwise(observed, mean, residual, seed=7, draws=500)
    assert full.shape == (500, len(mean))
    assert np.allclose(prefix, full[:20], rtol=0.0, atol=0.0)
    assert np.array_equal(np.isnan(prefix), np.isnan(full[:20]))
    assert not np.allclose(full[:20], full[20:40])


def test_first_paths_do_not_depend_on_total_draws():
    observed, mean, residual = _synthetic_case()
    reference = ar1_bridge_pathwise(observed, mean, residual, seed=11, draws=20)
    for total in (20, 33, 100, 500):
        candidate = ar1_bridge_pathwise(observed, mean, residual, seed=11, draws=total)
        assert candidate.shape == (total, len(mean))
        assert np.array_equal(candidate[:20], reference)


def test_pathwise_preserves_observations_and_fills_gaps():
    observed, mean, residual = _synthetic_case()
    missing = ~np.isfinite(observed)
    paths = ar1_bridge_pathwise(observed, mean, residual, seed=3, draws=20)
    np.testing.assert_array_equal(
        paths[:, ~missing], np.broadcast_to(observed[~missing], paths[:, ~missing].shape)
    )
    assert np.isfinite(paths[:, missing]).all()


def test_pathwise_rejects_undefined_gap_mean_like_legacy():
    observed, mean, residual = _synthetic_case()
    mean = mean.copy()
    mean[50] = np.nan
    pathwise = ar1_bridge_pathwise(observed, mean, residual, seed=5, draws=20)
    legacy = ar1_bridge(observed, mean, residual, seed=5, draws=20)
    assert pathwise.shape == legacy.shape == (20, len(mean))
    assert np.isnan(pathwise).all() and np.isnan(legacy).all()


def test_legacy_bridge_keeps_shape_and_finite_gap_values():
    observed, mean, residual = _synthetic_case()
    missing = ~np.isfinite(observed)
    paths = ar1_bridge(observed, mean, residual, seed=7, draws=20)
    assert paths.shape == (20, len(mean))
    assert np.isfinite(paths).all()
    np.testing.assert_array_equal(
        paths[:, ~missing], np.broadcast_to(observed[~missing], paths[:, ~missing].shape)
    )
