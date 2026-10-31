import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/706_summer_window_compare.py'
    spec=importlib.util.spec_from_file_location('summer_window_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def test_summer_windows_must_be_fully_contained_and_preserve_boundary_dates():
    m=module();dates=pd.date_range('2020-01-01','2020-12-31');values=np.zeros(len(dates))
    values[(dates>=pd.Timestamp('2020-08-17'))&(dates<=pd.Timestamp('2020-09-15'))]=10.
    full,summer=m.windows(values,dates)
    assert full==pytest.approx(10.) and summer==pytest.approx(5.)


def test_missing_days_do_not_form_a_synthetic_30_day_window():
    m=module();values=np.ones(62);values[::10]=np.nan
    assert np.isnan(m.max_window(values))
    values[::10]=1.;assert m.max_window(values)==pytest.approx(1.)


def test_unknown_screen_is_not_counted_as_rejected():
    m=module();years=pd.DataFrame({'station_key':['a','a'],'complete_year':[True,False],
        'observed_fraction':[1.,.9],'train_warm_fraction':[1.,np.nan],
        'julaug_complete':[True,False],'reported_window':[12.,11.]})
    groups=pd.DataFrame({'station_key':['a'],'independence_group':['g']})
    result=m.screening_counts(years,groups).set_index('rule')
    assert result.loc['warm_90_station_specific','unknown']==1
    assert result.loc['warm_90_station_specific','rejected']==0
    assert result.loc['annual_95','rejected_with_observed_30day_bound']==1


def test_influence_counts_use_strict_margins_and_station_groups():
    path=Path(__file__).resolve().parents[1]/'scripts/709_summer_influence.py'
    spec=importlib.util.spec_from_file_location('summer_influence_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=pd.DataFrame({'station_key':['a','a','b'],'independence_group':['g','g','h'],
                       'full_minus_summer':[0.,.1,.50001]})
    result=m.describe(data,'test')
    assert result['complete_station_years']==3 and result['stations']==2 and result['connected_groups']==2
    assert result['years_above_0p1_c']==1 and result['years_above_0p5_c']==1
