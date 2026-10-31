#!/usr/bin/env python3
"""Independently recompute finite daily means and year eligibility."""
import calendar
import csv
from datetime import datetime,timedelta,timezone
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path
import re
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def mst(text):
    t=datetime.fromisoformat(text.strip().replace('Z','+00:00'))
    return t.astimezone(timezone(timedelta(hours=-7))).replace(tzinfo=None) if t.tzinfo else t

def main():
    status=json.loads((OUT/'finite_reference_status.json').read_text());plan=json.loads((OUT/'finite_reference_plan.json').read_text());receipt=PRIVATE/'time_acquisition.json'
    if status['status']!='finite_level1_reference_screened':
        raise ValueError('Finite reference screen incomplete')
    days_out=[];year_out=[];outliers={};flags={}
    for item in json.loads(receipt.read_text()):
        rid=item['resource_id'];path=PRIVATE/'raw_level1'/f'{rid}.csv.gz'
        days=defaultdict(lambda:{'rows':0,'slots':set(),'grid':0,'valid':0,'sum':0.});bad=0
        with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);flags[rid]=[x for x in reader.fieldnames if re.search(r'flag|qualifier|qualit|estimat',x,re.I)]
            for r in reader:
                t=mst(r['timestamp']);d=days[t.date()];d['rows']+=1;d['slots'].add((t.hour,t.minute,t.second,t.microsecond))
                d['grid']+=int(t.minute%15==0 and t.second==0 and t.microsecond==0)
                try:v=float(r['temp_degC'])
                except (ValueError,TypeError):continue
                if math.isfinite(v) and -5<=v<=50:d['valid']+=1;d['sum']+=v
                elif math.isfinite(v):bad+=1
        yearly=defaultdict(lambda:{'days':0,'valid':0})
        for day,d in days.items():
            good=d['rows']==96 and len(d['slots'])==96 and d['grid']==96 and d['valid']==96
            yearly[day.year]['days']+=1;yearly[day.year]['valid']+=int(good)
            if good:days_out.append((rid,pd.Timestamp(day),d['sum']/96))
        for year,x in yearly.items():
            expected=366 if calendar.isleap(year) else 365
            year_out.append((rid,year,x['days'],x['valid'],expected,x['days']==expected and x['valid']==expected))
        outliers[rid]=bad;print('Independent finite-value audit',len(outliers),'of 10',flush=True)
    actual=pd.DataFrame(year_out,columns=['resource_id','year','reported_days','complete_finite_days','expected_days','finite_reference_year']).sort_values(['resource_id','year']).reset_index(drop=True)
    expected=pd.read_csv(PRIVATE/'finite_reference_years.csv').sort_values(['resource_id','year']).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual,expected,check_dtype=False)
    actual_days=pd.DataFrame(days_out,columns=['resource_id','day','mean_c']).sort_values(['resource_id','day']).reset_index(drop=True)
    expected_days=pd.read_parquet(PRIVATE/'finite_daily.parquet').sort_values(['resource_id','day']).reset_index(drop=True)
    if len(actual_days)!=len(expected_days) or not actual_days.resource_id.equals(expected_days.resource_id) or not actual_days.day.equals(expected_days.day) or not np.allclose(actual_days.mean_c,expected_days.mean_c,atol=1e-10,rtol=0):
        raise AssertionError('Finite daily means differ')
    sites=pd.read_csv(PRIVATE/'finite_reference_sites.csv').set_index('resource_id')
    if any(int(sites.loc[k,'finite_values_outside_sensor_range'])!=v for k,v in outliers.items()):raise AssertionError('Out-of-range count differs')
    if sum(bool(x) for x in flags.values())!=status['files_with_flag_like_columns']:raise AssertionError('Quality-like header count differs')
    if len(actual_days)!=status['complete_finite_days'] or int(actual.finite_reference_year.sum())!=status['complete_finite_station_years']:raise AssertionError('Reference denominator differs')
    result={'status':'passed','resources':len(outliers),'station_years_recomputed':len(actual),'complete_days_recomputed':len(actual_days),
            'complete_years_recomputed':int(actual.finite_reference_year.sum()),
            'scope':'Independent csv/datetime/set and scalar mean computation over the same saved level-1 files.',
            'limitations':'Published values may include corrections or estimates; finite data and sensor-range checks do not establish physical truth, instrument uncertainty, independent watershed or climate. No H30 or model-error score was computed.'}
    (OUT/'finite_reference_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
