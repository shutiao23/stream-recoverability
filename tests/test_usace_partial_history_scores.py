import importlib.util
from pathlib import Path
import sys
import numpy as np


def module():
    p=Path(__file__).resolve().parents[1]/'scripts/839_usace_partial_history_score.py'
    if str(p.parent) not in sys.path:sys.path.insert(0,str(p.parent))
    s=importlib.util.spec_from_file_location('usace_partial_scores',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_point_error_bounds_include_every_reference_value():
    m=module();p=np.array([0.,2.,5.]);l=np.array([1.,1.,1.]);u=np.array([3.,3.,3.]);low,high=m.error_bounds(p,l,u)
    assert np.allclose(low,[1,0,2]) and np.allclose(high,[3,1,4])
    for truth in np.linspace(1,3,101):assert np.all((np.abs(p-truth)>=low)&(np.abs(p-truth)<=high))


def test_paired_contrast_bounds_are_tight_for_one_case():
    m=module();p=np.array([2.]);q=np.array([7.]);l=np.array([0.]);u=np.array([10.]);low,high=m.pair_bounds(p,q,l,u)
    truth=np.linspace(0,10,10001);observed=np.abs(p[0]-truth)-np.abs(q[0]-truth)
    assert np.isclose(low[0],observed.min()) and np.isclose(high[0],observed.max())
