"""Availability screening must distinguish partial-year intervals and series."""
import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('usgs_count_screen', Path(__file__).resolve().parents[1] / 'scripts/548_usgs_approved_count_preflight.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_only_matching_full_calendar_year_and_approved_counts_are_eligible():
    roster=pd.DataFrame([{'station_id':'001','series_id':'mean-series'}])
    values=[{'start_date':'2020-01-01','end_date':'2020-12-31','interval_type':'calendar_year','approval_status':'approved','sample_count':366,'value':'19.2'},
            {'start_date':'2021-04-01','end_date':'2021-10-31','interval_type':'calendar_year','approval_status':'approved','sample_count':214,'value':'20.1'},
            {'start_date':'2022-01-01','end_date':'2022-12-31','interval_type':'calendar_year','approval_status':'approved','sample_count':364,'value':'10.4'}]
    doc={'features':[{'properties':{'monitoring_location_id':'USGS-001','data':[
        {'parent_time_series_id':'wrong-series','parent_statistic_id':'00003','values':values},
        {'parent_time_series_id':'mean-series','parent_statistic_id':'00003','values':values}]}}]}
    result=module.extract_counts(doc,roster).set_index('year')
    assert result.count_complete.to_dict()=={2020:True,2021:False,2022:False}
    assert not bool(result.loc[2021,'interval_full_year'])
    assert 'value' not in result.columns
    doc['features'][0]['properties']['data'][-1]['values'].append(values[0])
    with pytest.raises(ValueError,match='Duplicate series/year'):
        module.extract_counts(doc,roster)
