import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def module():
    path = Path(__file__).resolve().parents[1] / 'scripts/684_archive_matched_release_trend.py'
    spec = importlib.util.spec_from_file_location('archive_matched', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_count_matching_excludes_flagged_and_breaks_ties_by_year_without_truth():
    select = module().select_score
    score = [0.1, 0.1, 0.01, 0.02, np.nan]
    point = [1., 2., 3., np.nan, 5.]
    quality = [0., np.nan, 1., 0., 0.]
    years = [2003, 2001, 2000, 2002, 2004]
    assert select(score, point, quality, years, 1).tolist() == [False, True, False, False, False]
    assert select(score, point, quality, years, 2).tolist() == [True, True, False, False, False]
    assert select(score, point, quality, years, 3) is None
    assert not select(score, point, quality, years, 0).any()


def test_count_matching_rejects_duplicate_years():
    with pytest.raises(ValueError, match='unique'):
        module().select_score([0.1, 0.2], [1., 2.], [0., 0.], [2010, 2010], 1)


def test_values_only_uses_years_and_not_censored_values():
    run = module().fit
    years = np.arange(2000, 2006)
    exact = np.array([1., 2., 3., 4., 5., np.nan])
    result = run(years, exact, np.array([np.nan]*5 + [100.]), 'values_only', 10.)
    assert result['available']
    assert result['slope'] == pytest.approx(10.)
    assert result['squared_error'] == pytest.approx(0.)
    assert not run(years, np.array([1., 2., 3., 4., np.nan, np.nan]), np.full(6, np.nan), 'values_only', 10.)['available']


def test_empty_prediction_file_retains_complete_observed_archive(tmp_path):
    path = Path(__file__).resolve().parents[1] / 'scripts/685_archive_matched_release_trend_empty.py'
    spec = importlib.util.spec_from_file_location('archive_empty', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.ARCHIVE = tmp_path
    folder = tmp_path/'calendar'/'forward'/'replicate_0'/'station'
    folder.mkdir(parents=True)
    (folder/'design.json').write_text(json.dumps({'station_key':'site', 'region':'region', 'independence_group':'group'}))
    pred = folder/'annual_predictions.parquet'
    pd.DataFrame().to_parquet(pred)
    years = np.arange(2010,2016)
    truth = np.array([1.,2.,4.,3.,5.,6.])
    a = pd.DataFrame({'family':'calendar','mode':'forward','station_key':'site','replicate':0,
                      'year':years,'output_state':'complete_observed','quality_flag':np.nan,
                      'released_estimate':np.nan,'observed_lower_bound':np.nan,'eval_reference_h30':truth})
    expected = float(runner.slope(years,truth))
    old = []
    for method,name in [('values_only','released_values_only'),('values_and_bounds','released_values_and_bounds')]:
        result = runner.fit(years,truth,np.full(len(years),np.nan),method,expected)
        old.append({'family':'calendar','mode':'forward','station_key':'site','replicate':0,'method':name,
                    'available':result['available'],'truth_slope':expected,'slope':result['slope']})
    previous = pd.DataFrame(old).set_index(runner.ARCHIVE_KEY+['method'])
    metadata, rows = runner.one(pred, a.groupby(runner.ARCHIVE_KEY), previous)
    assert metadata['supported'] and metadata['n_masked'] == metadata['n_numeric'] == 0
    assert len(rows) == 4


def test_independent_censored_likelihood_agrees_on_right_censoring():
    from stream_recoverability.experiments.tr_revision.statistics import lower_bound_trend
    path = Path(__file__).resolve().parents[1] / 'scripts/688_matched_working_likelihood_audit.py'
    spec = importlib.util.spec_from_file_location('likelihood_audit', path)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    years = np.arange(2010, 2018)
    exact = np.array([1.,1.5,1.2,1.9,2.1,2.0,np.nan,np.nan])
    lower = np.array([np.nan]*6+[2.4,2.6])
    available, slope = audit.independent_fit(years,exact,lower)
    original = lower_bound_trend(years,exact,lower)
    assert available and original['converged']
    assert slope == pytest.approx(original['slope'], abs=1e-5)
