import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('njdep_metadata',Path(__file__).resolve().parents[1]/'scripts/632_njdep_metadata_preflight.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_metadata_retains_duplicate_station_id_as_distinct_deployments():
    html='''<select id="select-stations"><option value="">All</option>
    <option value="001" data-water-type="fresh-water" data-qa-start="01/01/2011" data-qa-end="12/31/2014">River One: 001 [001]</option>
    <option value="001" data-water-type="marine-water" data-qa-start="" data-qa-end="">River Two: 001 [001]</option></select>'''
    opts=m.metadata_options(html)
    coords=pd.DataFrame({'Buoy_ID':['001','001'],'Station':['001','001'],'Latitude':['40','41'],'Longitude':['-74','-75'],
                         'Description':['River One','River Two'],'Waterbody_Type':['Fresh Water','Marine Water']})
    joined=m.attach_coordinates(opts,coords)
    assert len(joined)==2 and joined.coordinate_matched.all()
    assert joined.Latitude.tolist()==['40','41']
    assert joined.possible_calendar_years_2010_2024.iloc[0]==4
    assert pd.isna(joined.possible_calendar_years_2010_2024.iloc[1])


def test_ambiguous_coordinate_match_is_not_silently_selected():
    options=pd.DataFrame([{'station_id':'001','label':'Unknown station'}])
    coords=pd.DataFrame({'Buoy_ID':['001','001'],'Station':['001','001'],'Latitude':['40','41'],'Longitude':['-74','-75'],
                         'Description':['River One','River Two'],'Waterbody_Type':['Fresh Water','Marine Water']})
    joined=m.attach_coordinates(options,coords)
    assert not joined.coordinate_matched.iloc[0]
    assert joined.Latitude.iloc[0]==''


def test_invalid_quality_span_does_not_become_complete():
    with pytest.raises(ValueError,match='end precedes'):
        m.covered_years(pd.Timestamp('2020-01-01'),pd.Timestamp('2019-12-31'))
    assert m.covered_years(pd.NaT,pd.Timestamp('2020-01-01')) is None


def test_timestamp_screen_counts_unique_days_and_duplicates_without_values():
    path=Path(__file__).resolve().parents[1]/'scripts/639_njdep_timestamp_qualification.py'
    spec=importlib.util.spec_from_file_location('njdep_clock_screen_test',path)
    clock=importlib.util.module_from_spec(spec);spec.loader.exec_module(clock)
    frame=pd.DataFrame({'Date_Time':['2016-02-29 00:00:00','2016-02-29 00:00:00','2017-01-01 00:00:00'],
                        'Date_Time_TZ':['EST','EST','EST']})
    result=clock.screen_clock(frame,2016)
    assert result['calendar_days']==366
    assert result['days_with_any_reported_time']==1
    assert result['days_with_no_reported_time']==365
    assert result['duplicate_timestamp_zone_rows']==1
    assert result['outside_requested_calendar_year_rows']==1
    assert result['status']=='reported_date_labels_incomplete'


def test_bad_clock_labels_are_unknown_not_incomplete_proof():
    path=Path(__file__).resolve().parents[1]/'scripts/639_njdep_timestamp_qualification.py'
    spec=importlib.util.spec_from_file_location('njdep_clock_unknown_test',path)
    clock=importlib.util.module_from_spec(spec);spec.loader.exec_module(clock)
    frame=pd.DataFrame({'Date_Time':['not-a-time'],'Date_Time_TZ':['']})
    result=clock.screen_clock(frame,2019)
    assert result['status']=='unparseable_time_unknown'
    assert result['date_label_complete_possible'] is None
