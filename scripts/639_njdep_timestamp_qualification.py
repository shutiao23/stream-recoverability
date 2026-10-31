#!/usr/bin/env python3
"""Screen returned NJDEP clock labels without reading temperature values.

A missing reported date label rules out a complete reference year in that
reported-day convention only. A present label does not establish 24-hour
coverage, quality, nonestimated water values or a physical time zone.
"""
from __future__ import annotations
import calendar
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026';DATA=PRIVATE/'station_year_csv'

def screen_clock(frame,year):
    times=pd.to_datetime(frame.Date_Time,format='%Y-%m-%d %H:%M:%S',errors='coerce')
    invalid=int(times.isna().sum());in_year=times.dt.year.eq(year);t=times.loc[in_year]
    keys=pd.DataFrame({'time':t,'zone':frame.loc[in_year,'Date_Time_TZ']})
    unique=int(len(keys.drop_duplicates()));duplicates=int(len(keys)-unique)
    dates=t.dt.normalize();counts=dates.value_counts();expected=366 if calendar.isleap(year) else 365
    label_days=int(counts.size);missing=expected-label_days
    if missing<0:raise ValueError('too many day labels in year')
    # The >=24 check is only an upper-bound diagnostic; duplicates and data
    # quality can make these records inadequate even when the count passes.
    hours=pd.DataFrame({'day':dates,'hour':t.dt.hour}).drop_duplicates().groupby('day').hour.nunique()
    return {'reported_year_rows':int(in_year.sum()),'outside_requested_calendar_year_rows':int((~in_year & times.notna()).sum()),
      'unparseable_timestamp_rows':invalid,'unique_reported_timestamp_zone_pairs':unique,'duplicate_timestamp_zone_rows':duplicates,
      'calendar_days':expected,'days_with_any_reported_time':label_days,'days_with_no_reported_time':missing,
      'days_with_24_unique_hour_labels':int(hours.ge(24).sum()),
      'date_label_complete_possible':bool(missing==0) if invalid==0 else None,
      'status':'reported_date_labels_incomplete' if invalid==0 and missing>0 else ('requires_subdaily_and_quality_review' if invalid==0 else 'unparseable_time_unknown')}

def main():
    plan=json.loads((OUT/'subdaily_qualification_plan.json').read_text());acq=json.loads((OUT/'subdaily_acquisition.json').read_text())
    if acq['status']!='station_year_files_acquired' or len(plan['station_ids'])!=2:raise ValueError('frozen two-site source acquisition required')
    dst=OUT/'timestamp_screen_status.json';local=PRIVATE/'timestamp_year_summary.csv'
    if dst.exists() or local.exists():raise RuntimeError('existing timestamp screening preserved')
    rows=[];zones=set()
    for site in plan['station_ids']:
        for year in plan['years']:
            path=DATA/f'{site}_{year}.csv';receipt=json.loads((DATA/f'{site}_{year}.json').read_text())
            cols=['Station','Date_Time','Date_Time_TZ','Submission ID']
            frame=pd.read_csv(path,usecols=cols,dtype=str,keep_default_na=False)
            if len(frame) and not frame.Station.eq(site).all():raise ValueError('returned station identity does not match request')
            zones.update(frame.Date_Time_TZ.unique());rows.append({'site':site,'year':year}|screen_clock(frame,year))
    table=pd.DataFrame(rows);table.to_csv(local,index=False);local.chmod(0o600)
    grouped=table.groupby('site').date_label_complete_possible.apply(lambda s:int(s.eq(True).sum()))
    status={'status':'reported_timestamp_label_screen_only','station_year_files':len(table),'stations':len(grouped),
      'station_years_with_missing_reported_date_labels':int(table.status.eq('reported_date_labels_incomplete').sum()),
      'station_years_with_unparseable_times':int(table.status.eq('unparseable_time_unknown').sum()),
      'station_years_requiring_further_quality_review':int(table.status.eq('requires_subdaily_and_quality_review').sum()),
      'stations_with_at_least_four_possible_label_years':int(grouped.ge(4).sum()),'provider_time_zone_labels':sorted(map(str,zones)),
      'columns_read':['Station','Date_Time','Date_Time_TZ','Submission ID'],'temperature_values_read_for_scoring':False,'models_scored':False,
      'scope':'year-by-year checks of returned source timestamp labels; per-station/year details remain local',
      'limitation':'post-hoc two-site availability selection; reported-clock labels and timezone abbreviations do not prove physical day boundaries, complete subdaily intervals, nonestimated water data, sensor QA or independent rivers'}
    dst.write_text(json.dumps(status,indent=2)+'\n');print(table[['site','year','reported_year_rows','days_with_any_reported_time','days_with_no_reported_time','days_with_24_unique_hour_labels','status']].to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
