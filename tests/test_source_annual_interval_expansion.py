import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'source_annual_expansion', Path(__file__).resolve().parents[1] / 'scripts/581_source_annual_interval_expansion.py'
)
expansion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(expansion)


def test_equal_group_weights_ignore_repetition_of_an_entire_group():
    y = np.array([0., 1., 3., 6.])
    lo = np.zeros(4)
    hi = np.ones(4)
    groups = np.array(['a', 'b', 'c', 'd'])
    baseline = expansion.correction(y, lo, hi, groups, alpha=.25)
    repeated = expansion.correction(np.r_[y, [0.] * 100], np.r_[lo, np.zeros(100)],
                                    np.r_[hi, np.ones(100)], np.r_[groups, ['a'] * 100], alpha=.25)
    assert baseline['status'] == 'supported_exploratory'
    assert repeated['empirical_radius'] == baseline['empirical_radius']
    assert baseline['n_source_groups'] == 4
    assert baseline['group_max_radius'] == 5.
    assert expansion.correction(y, lo, hi, groups)['group_max_radius'] is None


def test_small_and_degenerate_source_pools_are_withheld():
    assert expansion.correction([3., 4.], [0., 0.], [1., 1.], ['a', 'b'])['status'] == 'insufficient_source_groups'
    assert expansion.correction([0., .5, 1.], [0., 0., 0.], [1., 1., 1.], ['a', 'b', 'c'])['status'] == 'zero_source_correction'
    assert expansion.correction([], [], [], [])['status'] == 'no_source_cases'
    with pytest.raises(ValueError, match='reversed'):
        expansion.correction([2.], [3.], [1.], ['a'])


def test_group_level_rank_diagnostic_requires_enough_groups():
    names = [f'g{i}' for i in range(9)]
    result = expansion.correction(np.arange(1., 10.), np.zeros(9), np.zeros(9), names)
    assert result['group_max_rank'] == 9
    assert result['group_max_radius'] == 9.
    insufficient = expansion.correction(np.arange(1., 9.), np.zeros(8), np.zeros(8), names[:8])
    assert insufficient['group_max_rank'] == 9
    assert insufficient['group_max_radius'] is None


def test_expansion_respects_observed_support_and_never_loses_coverage():
    y = np.array([3., 3.5])
    lo, hi = np.array([2.5, 2.]), np.array([3., 3.])
    lower, upper = expansion.intervals(lo, hi, np.array([2.4, np.nan]), .5)
    np.testing.assert_allclose(lower, [2.4, 1.5])
    np.testing.assert_allclose(upper, [3.5, 3.5])
    old = expansion.scores(y, lo, hi)
    new = expansion.scores(y, lower, upper)
    assert np.all(new['coverage90'] >= old['coverage90'])
    assert np.all(new['width90'] >= old['width90'])
    assert new['interval_score90'][0] > old['interval_score90'][0]


def test_common_method_comparison_uses_both_eligible_and_supported_cases():
    rows = []
    for year in (2010, 2011, 2012):
        for method in ('D2', 'stochastic_calibrated'):
            row = dict(family='crossed', mode='forward', region='r', station_key='s',
                       year=year, replicate=0, independence_group='g', estimator=method,
                       stratum='all', baseline_available=not (year == 2011 and method == 'stochastic_calibrated'),
                       supported=not (year == 2012 and method == 'stochastic_calibrated'))
            for metric in ('coverage90', 'width90', 'interval_score90', 'zero90'):
                row['base_' + metric] = 1.
                row['new_' + metric] = 1.
            rows.append(row)
    result = expansion.summarize(pd.DataFrame(rows), None)
    common = result[result.scope.eq('both_methods_common')].set_index('estimator')
    assert common.n_eligible.eq(2).all()
    assert common.n_supported.eq(1).all()
    own = result[result.scope.eq('estimator_available')].set_index('estimator')
    assert own.loc['D2', 'n_eligible'] == 3
    assert own.loc['stochastic_calibrated', 'n_eligible'] == 2
