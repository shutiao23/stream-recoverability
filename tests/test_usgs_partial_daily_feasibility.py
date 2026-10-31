import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/871_usgs_partial_daily_feasibility.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('usgs_partial_feasibility',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_estimated_unapproved_and_ambiguous_days_are_not_observations():
    m=module();f=pd.DataFrame({'date':pd.date_range('2020-01-01',periods=5),'water_c':[5]*5,
      'reported':[True]*5,'unapproved':[False,False,True,False,False],'ambiguous':[False,False,False,True,False],
      'estimated':[False,True,False,False,False]})
    x=m.valid_daily(f);assert x.notna().tolist()==[True,False,False,False,True]


def test_partial_history_requires_coverage_endpoints_and_bounded_gaps():
    m=module();x=pd.Series(np.ones(365));x.iloc[50:95]=np.nan;assert m.history_ok(x)
    x.iloc[95]=np.nan;assert not m.history_ok(x)
    x.iloc[50:96]=1;x.iloc[0]=np.nan;assert not m.history_ok(x)


@pytest.mark.parametrize('missing_index', [0, -1])
def test_a_short_gap_at_either_year_endpoint_is_ineligible(missing_index):
    m=module();x=pd.Series(np.ones(365));x.iloc[missing_index]=np.nan
    assert not m.history_ok(x)


def test_short_runs_do_not_override_the_minimum_history_coverage():
    m=module();x=pd.Series(np.ones(365))
    # Three separated 31-day gaps pass the run-length limit, but leave fewer
    # than 75% observed days. Both observed endpoints remain available.
    for start in (30, 140, 250):x.iloc[start:start+31]=np.nan
    assert x.notna().mean()<.75
    assert not m.history_ok(x)


@pytest.mark.parametrize('days', [0, 300, 364, 367])
def test_history_requires_a_full_calendar_year_even_with_only_short_gaps(days):
    m=module();x=pd.Series(np.ones(days))
    if days:x.iloc[10:12]=np.nan
    assert not m.history_ok(x)


@pytest.mark.parametrize('days', [365, 366])
def test_complete_nonleap_and_leap_histories_remain_eligible(days):
    assert module().history_ok(pd.Series(np.ones(days)))
