import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


audit = module('peak_visibility_diagnostics', SCRIPTS / '578_peak_visibility_diagnostics.py')
scoring = module('annual_scoring', SCRIPTS / '576_verify_private_annual_predictions.py')


def test_reference_strata_are_outcome_based_and_validate_bound():
    labels = audit.classify([10., 10.1, 10.000000005], [10., 10., 10.])
    assert list(labels) == ['bound_matches_reference', 'unobserved_peak_excess', 'bound_matches_reference']
    with pytest.raises(ValueError, match='reference below'):
        audit.classify([9.9], [10.])
    with pytest.raises(ValueError, match='finite'):
        audit.classify([np.nan], [10.])


def test_group_resampling_uses_whole_clusters_and_reports_equal_group_mean():
    groups = np.array(['a', 'a', 'b'])
    values = np.array([0., 0., 1.])
    bounds, equal_group = audit.cluster_bootstrap(groups, values, draws=1000, seed=47)
    assert equal_group == 0.5
    generator = np.random.default_rng(47)
    choice = generator.integers(0, 2, size=(1000, 2))
    group_n = np.array([2., 1.])
    group_total = np.array([0., 1.])
    expected = group_total[choice].sum(axis=1) / group_n[choice].sum(axis=1)
    np.testing.assert_allclose(bounds, np.quantile(expected, [.025, .975]))


def test_scoring_uses_zero_width_and_interval_miss_consistently():
    q = np.array([[4.] * 7, [5.] * 7])
    metric = audit.case_metrics(q, np.array([4., 7.]), np.array([0., 0.]), scoring)
    np.testing.assert_allclose(metric.mae, [0., 2.])
    np.testing.assert_allclose(metric.crps, [0., 2.])
    np.testing.assert_allclose(metric.coverage90, [1., 0.])
    np.testing.assert_allclose(metric.interval_score90, [0., 40.])
    assert metric.zero90.eq(1).all()
    with pytest.raises(ValueError, match='quantile order'):
        audit.case_metrics(np.array([[1., 2., 3., 4., 3., 6., 7.]]), np.array([4.]), np.array([0.]), scoring)
