import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('rivtemp_date_bound',Path(__file__).resolve().parents[1]/'scripts/628_rivtemp_metadata_year_upper_bound.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def test_leap_year_missing_one_day_is_not_a_complete_label_year():
    roster=pd.DataFrame({'MonitoringLocationID':['a','b'],'MonitoringLocationLatitude':['1','2'],'MonitoringLocationLongitude':['3','4']})
    days=pd.date_range('2020-01-01','2020-12-31')
    entries=[{'MonitoringLocationID':'a','ActivityStartDate':str(d.date())} for d in days]
    entries += [{'MonitoringLocationID':'b','ActivityStartDate':str(d.date())} for d in days if str(d.date())!='2020-02-29']
    entries.append(entries[0].copy())
    years,sites=mod.upper_bound(pd.DataFrame(entries),roster,years=[2020])
    years=years.set_index('MonitoringLocationID')
    assert bool(years.loc['a','could_be_complete_by_label'])
    assert years.loc['a','distinct_labels']==366
    assert not bool(years.loc['b','could_be_complete_by_label'])
    assert not sites.at_least_four_possible_years.any()


def test_invalid_date_or_unfrozen_location_does_not_silently_pass():
    roster=pd.DataFrame({'MonitoringLocationID':['a'],'MonitoringLocationLatitude':['1'],'MonitoringLocationLongitude':['2']})
    with pytest.raises(ValueError,match='unparseable'):
        mod.upper_bound(pd.DataFrame({'MonitoringLocationID':['a'],'ActivityStartDate':['2020-02-30']}),roster,years=[2020])
    with pytest.raises(ValueError,match='outside frozen roster'):
        mod.upper_bound(pd.DataFrame({'MonitoringLocationID':['b'],'ActivityStartDate':['2020-01-01']}),roster,years=[2020])
