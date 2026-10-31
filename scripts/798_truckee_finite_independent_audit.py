#!/usr/bin/env python3
"""Independently audit all Truckee finite-value days and eligible years."""
import calendar
import csv
from datetime import datetime
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'

def main():
    status=json.loads((OUT/'finite_reference_status.json').read_text());p=json.loads((OUT/'finite_reference_plan.json').read_text())
    if status['status']!='finite_published_reference_screened':
        raise ValueError('Finite reference output incomplete')
    daily=[];annual=[];site_count=0
    for item in json.loads((PRIVATE/'acquisition.json').read_text()):
        site=item['station_code'];path=PRIVATE/'raw'/f'{site}.csv.gz'
        days=defaultdict(lambda:{'n':0,'slots':set(),'grid':0,'finite':0,'sum':0.})
        with gzip.open(path,'rt',newline='',encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row['Station_Code']!=site:raise ValueError('Station identity mismatch')
                t=datetime.strptime(row['Date_Time'],'%m/%d/%Y %H:%M:%S');item_day=days[t.date()]
                item_day['n']+=1;item_day['slots'].add((t.hour,t.minute,t.second,t.microsecond))
                item_day['grid']+=int(t.minute%15==0 and t.second==0 and t.microsecond==0)
                try:value=float(row['Water_Temperature'])
                except (ValueError,TypeError):continue
                if math.isfinite(value):item_day['finite']+=1;item_day['sum']+=value
        years=defaultdict(lambda:{'days':0,'complete':0})
        for day,x in days.items():
            ok=x['n']==96 and len(x['slots'])==96 and x['grid']==96 and x['finite']==96
            years[day.year]['days']+=1;years[day.year]['complete']+=int(ok)
            if ok:daily.append((site,pd.Timestamp(day),x['sum']/96))
        for year,x in years.items():
            expected=366 if calendar.isleap(year) else 365
            annual.append((site,year,x['days'],x['complete'],expected,x['days']==expected and x['complete']==expected))
        site_count+=1;print('Independent finite reference audit:',site_count,flush=True)
    observed=pd.DataFrame(annual,columns=['station_code','year','reported_days','complete_finite_days','expected_days','finite_reference_year']).sort_values(['station_code','year']).reset_index(drop=True)
    expected=pd.read_csv(PRIVATE/'finite_reference_years.csv').sort_values(['station_code','year']).reset_index(drop=True)
    pd.testing.assert_frame_equal(observed,expected,check_dtype=False)
    d=pd.DataFrame(daily,columns=['station_code','day','mean_c']).sort_values(['station_code','day']).reset_index(drop=True)
    prior=pd.read_parquet(PRIVATE/'finite_reported_daily.parquet').sort_values(['station_code','day']).reset_index(drop=True)
    if len(d)!=len(prior) or not d.station_code.equals(prior.station_code) or not d.day.equals(prior.day) or not np.allclose(d.mean_c,prior.mean_c,atol=1e-10,rtol=0):
        raise AssertionError('Finite daily means differ')
    if len(d)!=status['complete_finite_days'] or int(observed.finite_reference_year.sum())!=status['complete_finite_station_years']:
        raise AssertionError('Finite reference totals differ')
    report={'status':'passed','stations':site_count,'station_years_recomputed':len(observed),'complete_finite_days_recomputed':len(d),
            'complete_finite_years_recomputed':int(observed.finite_reference_year.sum()),'scope':'Independent csv/datetime/set and scalar mean computation over all 12 downloaded provider files.',
            'limitations':'Uses the same provider files; finite numeric values and 96 timestamps do not prove nonestimated measurements, correct physical day, calibration, independent climate or sensor accuracy. No H30 or model error evaluated.'}
    (OUT/'finite_reference_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
