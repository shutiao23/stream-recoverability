#!/usr/bin/env python3
"""Independently recompute the reservoir network's timestamp-only upper bound."""
import calendar
import csv
from datetime import datetime,timedelta,timezone
import gzip
import json
from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def mst_time(text):
    t=datetime.fromisoformat(text.strip().replace('Z','+00:00'))
    return t.astimezone(timezone(timedelta(hours=-7))).replace(tzinfo=None) if t.tzinfo else t

def main():
    status=json.loads((OUT/'time_upper_bound_status.json').read_text());acquisition=json.loads((OUT/'time_acquisition.json').read_text());receipt=PRIVATE/'time_acquisition.json'
    if status['status']!='timestamp_upper_bound_completed' or acquisition['status']!='completed':
        raise ValueError('Source timestamp screen incomplete')
    saved=PRIVATE/'timestamp_station_years.csv'
    rows=[];total=0
    for item in json.loads(receipt.read_text()):
        rid=item['resource_id'];path=PRIVATE/'raw_level1'/f'{rid}.csv.gz'
        days=defaultdict(lambda:{'n':0,'slots':set(),'valid':0})
        with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                t=mst_time(row['timestamp']);x=days[t.date()];x['n']+=1;x['slots'].add((t.hour,t.minute,t.second,t.microsecond))
                x['valid']+=int(t.minute%15==0 and t.second==0 and t.microsecond==0)
        years=defaultdict(lambda:{'days':0,'valid':0})
        for date,x in days.items():
            years[date.year]['days']+=1;years[date.year]['valid']+=int(x['n']==96 and len(x['slots'])==96 and x['valid']==96)
        for y,x in years.items():
            expected=366 if calendar.isleap(y) else 365
            rows.append({'resource_id':rid,'year':y,'days_with_labels':x['days'],'days_with_96_unique_quarters':x['valid'],
                         'expected_days':expected,'possible_complete_year':x['days']==expected and x['valid']==expected})
        total+=1;print('Independent source timestamp audit',total,'of 10',flush=True)
    actual=pd.DataFrame(rows).sort_values(['resource_id','year']).reset_index(drop=True)
    expected=pd.read_csv(saved,dtype={'resource_id':str}).sort_values(['resource_id','year']).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual[expected.columns],expected,check_dtype=False)
    result={'status':'passed','resources':total,'station_years_recomputed':len(actual),'possible_complete_years_recomputed':int(actual.possible_complete_year.sum()),
            'scope':'Independent csv/datetime/set implementation of time-label counts, using the same downloaded level-1 files and fixed UTC-7 interpretation.',
            'limits':'Time labels do not verify finite temperature, quality, nonestimated values, sensor clocks, independent basins or model performance.'}
    (OUT/'time_upper_bound_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
