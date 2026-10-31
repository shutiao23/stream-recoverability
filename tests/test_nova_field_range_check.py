"""Reported-hour ranges must not silently fill or de-duplicate data."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

path=Path(__file__).resolve().parents[1]/'scripts/753_nova_field_range_check.py'
spec=importlib.util.spec_from_file_location('nova_field_range_check',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_daily_range_requires_24_unique_finite_hour_labels():
    times=pd.date_range('2012-01-01',periods=24,freq='h')
    f=pd.DataFrame({'timestamp':times,'value':np.arange(24,dtype=float)})
    r=m.full_day_ranges(f)
    assert len(r)==1 and r.iloc[0].minimum==0 and r.iloc[0].maximum==23
    assert m.full_day_ranges(f.iloc[:-1]).empty
    assert m.full_day_ranges(pd.concat([f,f.iloc[[0]]],ignore_index=True)).empty
    f.loc[5,'value']=np.nan
    assert m.full_day_ranges(f).empty


def test_field_distance_to_interval_does_not_assume_time_or_sensor_accuracy():
    assert m.excess(5.,4.,6.)==0.
    assert m.excess(3.,4.,6.)==1.
    assert m.excess(7.,4.,6.)==1.
