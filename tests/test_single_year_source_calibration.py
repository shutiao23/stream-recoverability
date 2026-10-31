"""Target comparisons cannot count cases supported by only one method as paired."""
import importlib.util
import os
from pathlib import Path
import sys
import pandas as pd
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
old_umask=os.umask(0o077)
try:
    spec=importlib.util.spec_from_file_location('single_year_calibration',SCRIPTS/'672_single_year_source_calibration.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
finally:
    os.umask(old_umask)


def test_one_method_support_is_not_a_two_method_comparison():
    target=pd.DataFrame([{'family':'crossed','mode':'forward','replicate':0,'station_key':'usgs|s','year':2015,
       'region':'usgs_huc01','independence_group_old':'g1','stratum':'unobserved_peak_excess',
       'reference_h30':2.,'observed_lower_bound__observed_days_old':.5,
       'D2_q05_candidate':1.,'D2_q95_candidate':1.9,
       'stochastic_cal_q05_candidate':1.,'stochastic_cal_q95_candidate':1.9}])
    support=pd.DataFrame([{'family':'crossed','mode':'forward','region':'usgs_huc01','estimator':'D2','status':'supported_exploratory','empirical_radius':.2},
       {'family':'crossed','mode':'forward','region':'usgs_huc01','estimator':'stochastic_calibrated','status':'zero_source_correction','empirical_radius':0.}])
    cases,summary=module.evaluate_target(target,support)
    assert cases.loc[cases.estimator.eq('D2'),'supported'].all()
    assert not cases.both_supported.any()
    d=summary.loc[summary.estimator.eq('D2')&summary.stratum.eq('all')].set_index('scope')
    assert d.loc['estimator_supported','n_supported']==1
    assert d.loc['estimator_supported','paired_baseline_coverage90']==0.
    assert d.loc['estimator_supported','paired_expanded_coverage90']==1.
    assert d.loc['both_methods_supported','n_supported']==0
    assert pd.isna(d.loc['both_methods_supported','paired_expanded_coverage90'])
