"""Equal-count comparator uses only score and identity, including tied scores."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('matched_release',Path(__file__).resolve().parents[1]/'scripts/556_release_matched_retention.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_same_count_label_independence_and_ties():
    f=pd.DataFrame({'network_id':['n']*4,'station_key':['a','b','c','d'],'year':[2020]*4,
                    'design_family':['calendar']*4,'realization_id':['r']*4,
                    'risk_score':[.01,.02,.02,.9], 'D2':[1.,1.,1.,1.],
                    'eval_truth_h30':[1.,2.,1.,2.], 'independence_group':['g1','g1','g2','g2'],
                    'output':['estimate','observed_bound','estimate','unknown']})
    chosen,cutoff,ties=m.select_score_only(f,2)
    assert chosen.sum()==2 and cutoff==.02 and ties==2 and chosen[0]
    changed=f.copy();changed['eval_truth_h30']=[50.,-9.,100.,0.]
    assert np.array_equal(chosen,m.select_score_only(changed,2)[0])
    s,_=m.evaluate(f,bootstrap=30)
    assert s['n_equal_numerical']==2 and s['three_only']==s['score_only']
    with pytest.raises(ValueError,match='infeasible'):
        m.select_score_only(f,5)
