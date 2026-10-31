import importlib.util
from datetime import date, timedelta
from pathlib import Path
import numpy as np


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/830_usace_partial_year_h30_bounds.py'
    spec=importlib.util.spec_from_file_location('usace_h30_bounds',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_missing_slot_is_bounded_and_extrema_are_attainable():
    m=module();slots=np.full(96,10.);slots[7]=np.nan
    low,high,n=m.day_bounds(slots)
    assert n==95
    assert np.isclose(low,(95*10-5)/96)
    assert np.isclose(high,(95*10+50)/96)
    slots[7]=-5;assert np.isclose(m.day_bounds(slots)[0],low)
    slots[7]=50;assert np.isclose(m.day_bounds(slots)[1],high)


def test_annual_bound_finds_maximum_instead_of_averaging_peak_windows():
    m=module();start=date(2021,1,1);days={start+timedelta(days=i):np.full(96,0.) for i in range(365)}
    for i in range(100,130):days[start+timedelta(days=i)][:]=10.
    days[start+timedelta(days=112)][0]=np.nan
    result=m.yearly_bounds(days,2021)
    assert np.isclose(result['h30_lower_c'],10-15/(96*30))
    assert np.isclose(result['h30_upper_c'],10+40/(96*30))
    assert result['missing_or_ambiguous_slots']==1
    assert result['complete_days']==364
