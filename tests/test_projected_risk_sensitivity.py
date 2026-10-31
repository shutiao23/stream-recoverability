import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/701_projected_risk_fit.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('projected_risk_test',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def test_source_weights_give_each_group_equal_total_weight():
    m=module();groups=pd.Series(['a','a','a','b','c','c'])
    w=m.equal_group_weights(groups)
    sums=pd.Series(w).groupby(groups).sum()
    assert np.allclose(sums.to_numpy(),[2.,2.,2.])
    with pytest.raises(ValueError):m.equal_group_weights(['a',None])


def test_features_ignore_hidden_reference_and_original_risk():
    m=module();frame=pd.DataFrame({'policy_choice':['air_ridge'], 'law_hidden_shares':['0;0.2'],
        'air_available':[1], 'clim_peak':[14.], 'h30__policy':[13.], 'train_h30_mean':[12.],
        'observed_lower_bound__observed_days':[12.7], 'D2':[13.5], 'D2_q05':[13.], 'D2_q95':[14.],
        'missing_fraction':[.3], 'risk_score':[.01], 'eval_truth_h30':[100.]})
    bundle={'features':['missing_fraction','lower_bound_minus_point','law_hidden_mean']}
    a=m.features(frame,bundle)
    frame['eval_truth_h30']=-1000.;frame['risk_score']=.99
    b=m.features(frame,bundle)
    pd.testing.assert_frame_equal(a,b)
    assert not any(c.startswith(('eval_','reference','truth','risk_score')) for c in a.columns)
    assert a.projected_interval_width.iloc[0]==pytest.approx(1.)
    assert a.projected_point_above_bound.iloc[0]==pytest.approx(.8)


def test_matched_ranking_uses_no_truth_and_has_exact_count():
    m=module();d=pd.DataFrame({'family':['crossed']*4,'station_key':['a','b','c','d'],'replicate':[0]*4,
         'year':[2015]*4,'D2':[1.,1.,1.,1.], 'original_score':[.1]*4,
         'projected_score':[.3,.1,.2,np.nan],'reference_h30':[1.,2.,3.,4.]})
    a=m.select_matched(d,2);assert a.tolist()==[False,True,True,False]
    d.reference_h30=[100.,-20.,np.nan,500.]
    assert np.array_equal(a,m.select_matched(d,2))
    with pytest.raises(ValueError):m.select_matched(d,4)


def test_reference_attached_after_selection_requires_two_matching_records():
    module()
    path=Path(__file__).resolve().parents[1]/'scripts/703_projected_risk_reference_scoring.py'
    spec=importlib.util.spec_from_file_location('reference_scoring_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    target=pd.DataFrame({'family':['crossed'],'station_key':['a'],'replicate':[0],'year':[2015],
                         'region':['r'],'independence_group':['g'],'reference_h30':[np.nan],
                         'original_selected':[True],'matched_projected_selected':[False]})
    annual=pd.DataFrame({'family':['crossed'],'station_key':['a'],'replicate':[0],'year':[2015],
                         'mode':['forward'],'output_state':['estimate'],'region':['r'],
                         'independence_group':['g'],'eval_reference_h30':[12.]})
    source=pd.DataFrame({'family':['crossed','crossed'],'station_key':['a','a'],'year':[2015,2015],
                         'eval_truth_h30':[12.,12.]})
    result=m.attach_reference(target,annual,source)
    assert result.reference_h30.tolist()==[12.]
    assert result.original_selected.tolist()==[True] and result.matched_projected_selected.tolist()==[False]
    source.loc[1,'eval_truth_h30']=13.
    with pytest.raises(ValueError,match='nonunique'):m.attach_reference(target,annual,source)
