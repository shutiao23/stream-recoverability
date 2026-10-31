import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/714_past_season_screening.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('past_season_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_future_observations_do_not_change_prior_warm_season():
    m=module();dates=pd.date_range('2010-01-01','2020-12-31')
    values=10+5*np.sin(2*np.pi*(dates.dayofyear.to_numpy()-100)/365.25)
    series=pd.Series(values,index=dates);altered=series.copy();altered.loc[altered.index.year>=2018]+=100
    a=m.prior_warm(series,2018);b=m.prior_warm(altered,2018)
    assert a['months']==b['months'] and a['fraction']==b['fraction']
    assert a['prior_complete_years']==b['prior_complete_years']==8


def test_incomplete_year_without_four_complete_history_is_unknown():
    m=module()
    assert m.warm_state(False,.95,3,4)=='unknown'
    assert m.warm_state(False,.89,4,4)=='rejected'
    assert m.warm_state(True,np.nan,0,4)=='accepted'


def test_prior_record_excludes_rejected_and_unknown_years():
    m=module();frame=pd.DataFrame({'station_key':['a']*5+['b'],'year':[2010,2011,2012,2013,2014,2010],
        'rule':['warm90_past']*6,'state':['accepted','unknown','rejected','accepted','rejected','rejected'],
        'reported_window':[10.,15.,12.,11.,10.9,20.]})
    result=m.annotate_records(frame).set_index(['station_key','year'])
    assert result.loc[('a',2012),'prior_accepted_record']==10.
    assert result.loc[('a',2012),'rejected_above_prior_record']
    assert result.loc[('a',2014),'prior_accepted_record']==11.
    assert not result.loc[('a',2014),'rejected_above_prior_record']
    assert np.isnan(result.loc[('b',2010),'prior_accepted_record'])


def test_same_station_year_is_valid_across_different_rules():
    module()
    path=Path(__file__).resolve().parents[1]/'scripts/715_past_season_multirule.py'
    spec=importlib.util.spec_from_file_location('past_multirule_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    frame=pd.DataFrame({'station_key':['a','a'],'year':[2010,2010],
                        'rule':['complete_100','annual_95'],'state':['accepted','accepted'],
                        'reported_window':[10.,10.]})
    assert len(m.annotate_records(frame))==2
    with pytest.raises(ValueError,match='Duplicate'):
        m.annotate_records(pd.concat([frame,frame.iloc[[0]]],ignore_index=True))
