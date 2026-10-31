import importlib.util
from pathlib import Path
import sys
import numpy as np


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/857_partial_history_feature_support.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('partial_feature_support',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_weighted_quantile_respects_bootstrap_multiplicity():
    m=module();v=np.array([10.,1.,4.]);w=np.array([1.,3.,2.])
    assert m.weighted_quantile(v,w,.5)==1.
    assert m.weighted_quantile(v,w,.51)==4.
    assert m.weighted_quantile(v,w,.99)==10.


def test_out_of_range_and_each_nonfinite_kind_are_distinct():
    m=module();x=np.array([-2.,0.,1.,2.,np.nan,np.inf,-np.inf])
    out,tail,unseen=m.flags(x,0.,1.,.25,.75,True,False,True)
    assert out.tolist()==[True,False,False,True,False,False,False]
    assert tail.tolist()==[True,True,True,True,False,False,False]
    assert unseen.tolist()==[False,False,False,False,False,True,False]


def test_observed_only_autocorrelation_excludes_target_year():
    import pandas as pd
    path=Path(__file__).resolve().parents[1]/'scripts/859_partial_history_autocorrelation_sensitivity.py'
    spec=importlib.util.spec_from_file_location('partial_phi',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    dates=pd.date_range('2021-01-01','2025-12-31');rng=np.random.default_rng(10)
    series=pd.Series(np.sin(dates.dayofyear.to_numpy()/40)+rng.normal(0,.2,len(dates)),index=dates)
    series.loc['2022-06-04':'2022-06-10']=np.nan
    a,n=m.anomaly_phi(series,[2021,2022,2023,2024],[5,6,7,8,9])
    altered=series.copy();altered.loc['2025-01-01':'2025-12-31']+=1000
    b,n2=m.anomaly_phi(altered,[2021,2022,2023,2024],[5,6,7,8,9])
    assert np.isfinite(a) and np.isclose(a,b,atol=1e-12,rtol=0) and n==n2
