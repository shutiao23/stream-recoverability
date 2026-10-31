import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pandas as pd


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/850_source_partial_history_factorial.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('source_history_factorial',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_target_mask_geometries_do_not_depend_on_history_climatology():
    m=module();x=m.fixed_designs(np.zeros(365,bool),0,[30,60,90],2);y=m.fixed_designs(np.ones(365,bool),4,[30,60,90],2)
    assert len(x)==9 and all(np.array_equal(a['mask'],b['mask']) for a,b in zip(x,y))
    assert sorted(int(a['mask'].sum()) for a in x)==[30]*3+[60]*3+[90]*3


def test_hidden_history_values_do_not_enter_interpolated_panel():
    m=module();dates=pd.date_range('2009-01-01','2017-12-31');frame=pd.DataFrame({'station_key':'foen|site','date':dates,'water_c':dates.dayofyear.astype(float)})
    row=SimpleNamespace(station_key='foen|site',station_id='site');first,count=m.panel_for(frame,row,'partial');changed=frame.copy();mask=changed.date.dt.year.lt(2017)&changed.date.dt.month.eq(7)&changed.date.dt.day.le(30);changed.loc[mask,'water_c']+=1000
    second,count2=m.panel_for(changed,row,'partial')
    pd.testing.assert_frame_equal(first,second);assert count==count2==240
