"""Six-way and both-method availability must use the correct denominators."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('heat_gap_source_comparison',SCRIPTS/'743_heat_gap_source_compare.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_source_common_cohorts_and_interval_availability():
    rows=[]
    for i in range(205):
        for method in m.METHODS:
            for dep in m.DEPS:
                for version in m.VERSIONS:
                    for side in m.SIDES:
                        available=not ((i==0 and method=='stochastic_calibrated' and version=='candidate' and side=='stress')
                                       or (i==1 and method=='D2' and version=='original' and side=='baseline'))
                        metric=np.nan if i==2 and version=='candidate' and side=='stress' else .9
                        rows.append({'station_key':f's{i}', 'replicate':0,'independence_group':f'g{i%5}',
                            'region':f'r{i%3}','estimator':method,'dependence':dep,'version':version,'side':side,
                            'available':available,'truth_slope':.2,'error':1. if side=='baseline' else 2.,
                            'squared_error':1. if side=='baseline' else 4.,'missing_coverage95':metric,
                            'width95':1.,'interval_score95':2.})
    result,_=m.summary(pd.DataFrame(rows))
    a=result[(result.estimator=='D2')&(result.dependence=='independent')&(result.version=='candidate')]
    single=a[a.scope=='estimator_six_way'].iloc[0];both=a[a.scope=='both_methods_six_way'].iloc[0]
    assert single.n_common==204 and both.n_common==203
    assert both.interval_common==202
    assert both.baseline_rmse==1. and both.stress_rmse==2. and both.mse_difference==3.
    assert both.bootstrap_low==3. and both.bootstrap_high==3.


def test_identical_point_contrasts_share_resampling_limits():
    path=SCRIPTS.parent/'results/wrr_review_response_20261027/heat_gap_source_sensitivity/source_interactions.csv'
    table=pd.read_csv(path)
    for _,group in table.groupby(['estimator','comparison']):
        assert group.n_common.nunique()==1
        assert np.allclose(group.interaction_mean,group.interaction_mean.iloc[0],rtol=0,atol=1e-12)
        assert np.allclose(group.bootstrap_low,group.bootstrap_low.iloc[0],rtol=0,atol=1e-12)
        assert np.allclose(group.bootstrap_high,group.bootstrap_high.iloc[0],rtol=0,atol=1e-12)
