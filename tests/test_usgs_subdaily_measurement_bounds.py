import importlib.util
from datetime import timedelta,timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd


def load(name):
    path=Path(__file__).resolve().parents[1]/'scripts'/name
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('usgs_tmp_'+name[:3],path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_subdaily_missing_slot_and_offgrid_are_conservatively_bounded():
    m=load('893_subdaily_h30_bounds.py');start=pd.Timestamp('2017-01-01T07:00:00Z');times=pd.date_range(start,periods=96,freq='15min').delete(3)
    f=pd.DataFrame({'time':times,'value':10.,'approved':True,'qualifier_empty':True,'on_grid':True});d=m.calculate(f,2017,timezone(timedelta(hours=-7))).iloc[0]
    assert int(d.expected_slots)==96 and int(d.known_slots)==95
    assert np.isclose(d.lower_c,(95*10-5)/96) and np.isclose(d.upper_c,(95*10+50)/96)
    extra=pd.DataFrame({'time':[start+pd.Timedelta(minutes=1)],'value':[10.],'approved':[True],'qualifier_empty':[True],'on_grid':[False]})
    e=m.calculate(pd.concat([f,extra],ignore_index=True),2017,timezone(timedelta(hours=-7))).iloc[0]
    assert int(e.known_slots)==0 and e.lower_c==-5 and e.upper_c==50


def test_soft_support_projection_uses_explicit_margin_and_preserves_nan_bounds():
    m=load('899_measurement_support_sensitivity.py');q=np.array([[1.,2.,3.],[1.,2.,3.]])
    result=m.project(q,np.array([2.5,np.nan]),.5)
    assert np.allclose(result,[[2.,2.,3.],[1.,2.,3.]])
