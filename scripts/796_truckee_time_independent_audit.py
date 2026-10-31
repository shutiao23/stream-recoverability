#!/usr/bin/env python3
"""Independently recompute Truckee timestamp-only completeness upper bounds."""
import calendar
import csv
from datetime import datetime
import gzip
import json
from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'

def main():
    status=json.loads((OUT/'time_upper_bound_status.json').read_text());acq=json.loads((OUT/'time_acquisition.json').read_text())
    old=PRIVATE/'timestamp_station_years.csv';receipt=PRIVATE/'acquisition.json'
    if status['status']!='timestamp_upper_bound_completed' or acq['status']!='completed':
        raise ValueError('Original screen is incomplete')
    rows=[];station_rows=0
    for item in json.loads(receipt.read_text()):
        site=item['station_code'];path=PRIVATE/'raw'/f'{site}.csv.gz'
        days=defaultdict(lambda:{'n':0,'slots':set(),'valid':0})
        with gzip.open(path,'rt',newline='',encoding='utf-8-sig') as f:
            for rec in csv.DictReader(f):
                if rec['Station_Code']!=site:raise ValueError('Unexpected station identity')
                time=datetime.strptime(rec['Date_Time'],'%m/%d/%Y %H:%M:%S');day=time.date();x=days[day];x['n']+=1
                x['slots'].add((time.hour,time.minute,time.second,time.microsecond))
                x['valid']+=int(time.minute%15==0 and time.second==0 and time.microsecond==0)
        per_year=defaultdict(lambda:{'any':0,'complete':0})
        for day,val in days.items():
            y=per_year[day.year];y['any']+=1;y['complete']+=int(val['n']==96 and len(val['slots'])==96 and val['valid']==96)
        for year,value in per_year.items():
            expected=366 if calendar.isleap(year) else 365
            rows.append({'station_code':site,'year':year,'days_with_any_label':value['any'],
                'days_with_96_unique_quarters':value['complete'],'expected_days':expected,
                'possible_complete_year':value['any']==expected and value['complete']==expected})
        station_rows+=1;print('Independent timestamp audit:',station_rows,flush=True)
    current=pd.DataFrame(rows).sort_values(['station_code','year']).reset_index(drop=True)
    saved=pd.read_csv(old).sort_values(['station_code','year']).reset_index(drop=True)
    pd.testing.assert_frame_equal(current[saved.columns],saved,check_dtype=False)
    if len(current)!=status['station_years'] or int(current.possible_complete_year.sum())!=status['possible_complete_years']:
        raise AssertionError('Aggregate timestamp result differs')
    result={'status':'passed','stations':station_rows,'station_years_recomputed':len(current),
            'possible_complete_years_recomputed':int(current.possible_complete_year.sum()),
            'scope':'Separate csv/datetime/set implementation over the same 12 downloaded files; only station and timestamp fields interpreted.',
            'limitations':'Ignores temperature missingness, sensor QC, estimated/corrected values, daylight convention, prior network contact and independence; identical inputs are not independent physical validation.'}
    (OUT/'time_upper_bound_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
