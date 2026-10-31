"""Require unambiguous provider-day evidence without relabeling unknown codes."""
import importlib.util
from pathlib import Path
import pandas as pd

spec=importlib.util.spec_from_file_location('eccc_red',Path(__file__).resolve().parents[1]/'scripts/565_eccc_red_qualification.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_strict_hourly_day_rejects_duplicates_and_unconfirmed_codes():
    times=pd.date_range('2020-01-01',periods=24,freq='h')
    frame=pd.DataFrame({'station':m.STATION,'time':times,'value':10.,'grade':'1','status':'V','flag':''})
    daily=m.daily_quality(frame).iloc[0]
    assert bool(daily.complete_wallclock) and daily.temperature_c==10.
    duplicate=pd.concat([frame,frame.iloc[[5]]],ignore_index=True)
    daily=m.daily_quality(duplicate).iloc[0]
    assert not bool(daily.complete_wallclock) and pd.isna(daily.temperature_c)
    unknown=frame.copy();unknown.loc[0,'status']='Corrected';unknown.loc[0,'grade']=''
    daily=m.daily_quality(unknown).iloc[0]
    assert not bool(daily.complete_wallclock) and daily.valid_hour_bins==23
