import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/866_source_support_rule_evaluation.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('source_ood_rule',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_matched_count_uses_scores_and_identity_not_outcomes():
    m=module();f=pd.DataFrame({'risk_score':[.2,.1,.1], 'station_key':['c','b','a'],'year':[2020]*3,'design_family':['crossed']*3,
      'realization_id':['r']*3,'network_id':['n']*3,'policy_choice':['air_ridge']*3,'failed':[False,False,True]})
    mask=m.matched_risk_only(f,2);g=f.copy();g['failed']=~g.failed
    assert mask.tolist()==[False,True,True] and np.array_equal(mask,m.matched_risk_only(g,2))


def test_group_weighted_error_uses_equal_group_mass():
    m=module();f=pd.DataFrame({'independence_group':['a','a','a','b'],'failed':[False,False,False,True]})
    x=m.metrics(f,np.ones(4,bool));assert x['conditional_failure']==.25 and np.isclose(x['group_weighted_failure'],.5)


def test_range_margin_tolerates_small_overrun_and_keeps_unseen_missing():
    path=Path(__file__).resolve().parents[1]/'scripts/869_source_support_margin_sensitivity.py'
    spec=importlib.util.spec_from_file_location('source_margin',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    design=pd.DataFrame({'f':[1.005,1.02,np.nan]})
    support=pd.DataFrame({'feature':['f'],'source_min':[0.],'source_max':[1.],'source_weighted_q01':[0.],'source_weighted_q99':[1.],
      'source_estimator_nan_rows':[0],'source_estimator_posinf_rows':[0],'source_estimator_neginf_rows':[0]}).set_index('feature')
    assert m.warning(design,support,['f'],0.).tolist()==[True,True,True]
    assert m.warning(design,support,['f'],.01).tolist()==[False,True,True]
