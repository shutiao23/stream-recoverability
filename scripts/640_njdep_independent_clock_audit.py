#!/usr/bin/env python3
"""Independently verify NJDEP timestamp-label counts using Arrow and Python."""
from collections import defaultdict
from datetime import datetime
import calendar
import json
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.csv as acsv

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026';DATA=PRIVATE/'station_year_csv'

def independent_clock(path,site,year):
 options=acsv.ConvertOptions(include_columns=['Station','Date_Time','Date_Time_TZ'],column_types={'Station':pa.string(),'Date_Time':pa.string(),'Date_Time_TZ':pa.string()})
 reader=acsv.open_csv(path,read_options=acsv.ReadOptions(block_size=1024*1024),convert_options=options)
 dates=set();hour_sets=defaultdict(set);pairs=set();n=outside=bad=duplicate=0
 for batch in reader:
  for station,raw,zone in zip(batch.column(0).to_pylist(),batch.column(1).to_pylist(),batch.column(2).to_pylist()):
   if station!=site:raise ValueError('station mismatch')
   try:t=datetime.strptime(raw,'%Y-%m-%d %H:%M:%S')
   except (ValueError,TypeError):bad+=1;continue
   if t.year!=year:outside+=1;continue
   n+=1;key=(t,zone)
   if key in pairs:duplicate+=1
   pairs.add(key);dates.add(t.date());hour_sets[t.date()].add(t.hour)
 expected=366 if calendar.isleap(year) else 365
 return {'reported_year_rows':n,'outside_requested_calendar_year_rows':outside,'unparseable_timestamp_rows':bad,
   'unique_reported_timestamp_zone_pairs':len(pairs),'duplicate_timestamp_zone_rows':duplicate,
   'calendar_days':expected,'days_with_any_reported_time':len(dates),'days_with_no_reported_time':expected-len(dates),
   'days_with_24_unique_hour_labels':sum(len(v)>=24 for v in hour_sets.values())}

def main():
 plan=json.loads((OUT/'subdaily_qualification_plan.json').read_text());status=json.loads((OUT/'timestamp_screen_status.json').read_text())
 if status['status']!='reported_timestamp_label_screen_only':raise ValueError('original clock screen missing')
 saved=pd.read_csv(PRIVATE/'timestamp_year_summary.csv',dtype={'site':str}).set_index(['site','year']);checked=0
 for site in plan['station_ids']:
  for year in plan['years']:
   path=DATA/f'{site}_{year}.csv';receipt=json.loads((DATA/f'{site}_{year}.json').read_text())
   actual=independent_clock(path,site,year);row=saved.loc[(site,year)]
   for key,value in actual.items():
    if int(row[key])!=value:raise ValueError('clock recount mismatch: '+key)
   checked+=1
 if checked!=len(saved):raise ValueError('saved station-year scope differs')
 result={'status':'independent_timestamp_recount_passed','station_year_files_checked':checked,'stations':len(plan['station_ids']),
   'fields_parsed':['Station','Date_Time','Date_Time_TZ'],'temperature_values_or_model_errors_examined':False,
   'scope':'independent Arrow/Python recount of reported timestamp-day and hour labels from the same source files',
   'limitation':'does not establish real time zone, true sampling completeness, quality flags, nonestimated values, prior access or independent catchments'}
 (OUT/'independent_timestamp_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
