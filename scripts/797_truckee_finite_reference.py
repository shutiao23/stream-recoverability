#!/usr/bin/env python3
"""Check complete finite reported-temperature years in the fixed Truckee data."""
import argparse
import calendar
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'

def freeze():
    dest=OUT/'finite_reference_plan.json'
    if dest.exists():raise FileExistsError('Preserve finite-reference plan')
    time=json.loads((OUT/'time_upper_bound_status.json').read_text());audit=json.loads((OUT/'time_upper_bound_independent_audit.json').read_text())
    if time['status']!='timestamp_upper_bound_completed' or audit['status']!='passed':raise ValueError('Timestamp screen not independently checked')
    p={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc after inspecting public metadata, acquiring station files and seeing timestamp coverage; before reading numerical water values or computing target prediction errors',
        'cohort':'All 12 fixed station files; no selection by temperature, peak, model prediction or error.',
        'rule':'A reported-clock day needs exactly 96 unique valid quarter-hour labels and 96 finite numeric water-temperature values; a reference year needs every day of a complete calendar year. Use the arithmetic mean of those 96 reported values for each eligible day; retain incomplete and unavailable years.',
        'source_quality':'EML states the published data passed provider validation and invalid data are NA. The files do not contain individual estimated/corrected-value flags, the exact application of PST versus DST remains uncertain, and prior contacts include the same managed river network. Finite values are provisional published-data references, not strict independent nonestimated sensor truth.',
        'no_scoring':'Produce completeness, availability and daily means only. Do not compute annual H30, prediction errors, or choose an analysis station or year using temperature outcomes.',
        }
    dest.write_text(json.dumps(p,indent=2)+'\n');print('Recorded finite-value reference qualification plan')

def run():
    p=json.loads((OUT/'finite_reference_plan.json').read_text())
    annual=[];stations=[];daily_all=[]
    time_years=pd.read_csv(PRIVATE/'timestamp_station_years.csv')
    for entry in json.loads((PRIVATE/'acquisition.json').read_text()):
        site=entry['station_code'];path=PRIVATE/'raw'/f'{site}.csv.gz'
        chunks=[]
        for x in pd.read_csv(path,compression='gzip',usecols=['Station_Code','Date_Time','Water_Temperature'],dtype=str,chunksize=100000):
            if not x.Station_Code.eq(site).all():raise ValueError('Unexpected station')
            date=pd.to_datetime(x.Date_Time,format='%m/%d/%Y %H:%M:%S',errors='coerce')
            if date.isna().any():raise ValueError('Unparseable time label')
            value=pd.to_numeric(x.Water_Temperature,errors='coerce')
            chunks.append(pd.DataFrame({'time':date,'finite':np.isfinite(value),'value':value}))
        x=pd.concat(chunks,ignore_index=True);x['day']=x.time.dt.normalize();x['on_grid']=(x.time.dt.minute%15==0)&x.time.dt.second.eq(0)&x.time.dt.microsecond.eq(0)
        by=x.groupby('day').agg(rows=('time','size'),unique=('time','nunique'),on_grid=('on_grid','sum'),finite=('finite','sum'),mean_c=('value','mean'))
        by['complete']=by.rows.eq(96)&by.unique.eq(96)&by.on_grid.eq(96)&by.finite.eq(96)
        reference=by.loc[by.complete,['mean_c']].reset_index();reference['station_code']=site;daily_all.append(reference)
        years=[]
        for year,g in by.groupby(by.index.year):
            expected=366 if calendar.isleap(int(year)) else 365;count=int(g.complete.sum());ok=len(g)==expected and count==expected
            years.append({'station_code':site,'year':int(year),'reported_days':len(g),'complete_finite_days':count,
                          'expected_days':expected,'finite_reference_year':bool(ok)})
        frame=pd.DataFrame(years);annual.append(frame)
        label=time_years[time_years.station_code.eq(site)].set_index('year')
        if not set(frame.year).issubset(set(label.index)):raise ValueError('Timestamp and finite year cohorts differ')
        for r in frame.itertuples(index=False):
            if r.complete_finite_days>int(label.loc[r.year,'days_with_96_unique_quarters']):raise ValueError('Finite day exceeds timestamp upper bound')
        stations.append({'station_code':site,'reference_years':int(frame.finite_reference_year.sum()),
                         'at_least_four_finite_reference_years':bool(frame.finite_reference_year.sum()>=4),
                         'complete_finite_days':int(by.complete.sum()),'reported_days':len(by)})
        print('Finite reference screened:',site,flush=True)
    yearly=pd.concat(annual,ignore_index=True);sites=pd.DataFrame(stations);daily=pd.concat(daily_all,ignore_index=True)
    if daily.duplicated(['station_code','day']).any():raise ValueError('Duplicate daily values')
    for name,frame in [('finite_reference_years.csv',yearly),('finite_reference_stations.csv',sites)]:
        path=PRIVATE/name;frame.to_csv(path,index=False);path.chmod(0o600)
    path=PRIVATE/'finite_reported_daily.parquet';daily.to_parquet(path,index=False);path.chmod(0o600)
    status={'status':'finite_published_reference_screened','stations':len(sites),'station_years':len(yearly),
            'complete_finite_station_years':int(yearly.finite_reference_year.sum()),
            'stations_with_four_finite_reference_years':int(sites.at_least_four_finite_reference_years.sum()),
            'complete_finite_days':len(daily),'annual_h30_calculated':False,'prediction_errors_calculated':False,
            'limitations':p['source_quality']}
    (OUT/'finite_reference_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
