#!/usr/bin/env python3
"""Offline replay of the public Truckee and NASA POWER reference inputs."""
import argparse
import calendar
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';SNAP=ROOT/'data/external/wrr_truckee_dwr_20261027'

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'results/wrr_review_response_20261027/audit/truckee_open_reference_replay.json');args=p.parse_args()
    manifest=json.loads((SNAP/'manifest.json').read_text());items=manifest['files'];names=[x['file'] for x in items]
    if len(names)!=len(set(names)):raise ValueError('Duplicate manifest path')
    for item in items:
        path=(SNAP/item['file']).resolve()
        if not path.is_relative_to(SNAP.resolve()) or not path.is_file():raise ValueError('Snapshot file missing or changed')
    daily=[];time_years=[];finite_years=[]
    for item in [x for x in items if 'station_code' in x]:
        site=item['station_code'];path=SNAP/item['file'];size=0
        with gzip.open(path,'rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):size+=len(block)
        if size!=item['uncompressed_source_bytes']:raise ValueError('Source file differs from EML')
        pieces=[]
        for x in pd.read_csv(path,compression='gzip',usecols=['Station_Code','Date_Time','Water_Temperature'],dtype=str,chunksize=100000):
            if not x.Station_Code.eq(site).all():raise ValueError('Station identity mismatch')
            date=pd.to_datetime(x.Date_Time,format='%m/%d/%Y %H:%M:%S',errors='coerce')
            if date.isna().any():raise ValueError('Invalid timestamp')
            value=pd.to_numeric(x.Water_Temperature,errors='coerce');pieces.append(pd.DataFrame({'time':date,'value':value,'finite':np.isfinite(value)}))
        x=pd.concat(pieces,ignore_index=True);x['day']=x.time.dt.normalize();x['grid']=(x.time.dt.minute%15==0)&x.time.dt.second.eq(0)&x.time.dt.microsecond.eq(0)
        day=x.groupby('day').agg(rows=('time','size'),unique=('time','nunique'),grid=('grid','sum'),finite=('finite','sum'),mean_c=('value','mean'))
        day['label']=day.rows.eq(96)&day.unique.eq(96)&day.grid.eq(96);day['complete']=day.label&day.finite.eq(96)
        vals=day.loc[day.complete,['mean_c']].reset_index();vals['station_code']=site;daily.append(vals)
        for year,g in day.groupby(day.index.year):
            expected=366 if calendar.isleap(int(year)) else 365;labels=int(g.label.sum());finite=int(g.complete.sum())
            time_years.append({'station_code':site,'year':int(year),'days_with_any_label':len(g),'days_with_96_unique_quarters':labels,
                               'expected_days':expected,'possible_complete_year':len(g)==expected and labels==expected})
            finite_years.append({'station_code':site,'year':int(year),'reported_days':len(g),'complete_finite_days':finite,
                                 'expected_days':expected,'finite_reference_year':len(g)==expected and finite==expected})
        print('Replayed reference station',site,flush=True)
    def compare_years(rows,filename):
        actual=pd.DataFrame(rows).sort_values(['station_code','year']).reset_index(drop=True)
        expected=pd.read_csv(SNAP/filename).sort_values(['station_code','year']).reset_index(drop=True)
        pd.testing.assert_frame_equal(actual[expected.columns],expected,check_dtype=False);return actual
    times=compare_years(time_years,'timestamp_station_years.csv');years=compare_years(finite_years,'finite_reference_years.csv')
    frame=pd.concat(daily,ignore_index=True).sort_values(['station_code','day']).reset_index(drop=True)
    expected=pd.read_parquet(SNAP/'finite_reported_daily.parquet').sort_values(['station_code','day']).reset_index(drop=True)
    if len(frame)!=len(expected) or not frame.station_code.equals(expected.station_code) or not frame.day.equals(expected.day) or not np.allclose(frame.mean_c,expected.mean_c,atol=1e-10,rtol=0):
        raise ValueError('Processed daily means differ')
    forcing=json.loads((OUT/'exploratory_forcing_status.json').read_text());response=json.loads((SNAP/'exploratory_power_response.json').read_text())
    air=pd.read_parquet(SNAP/'exploratory_air_forcing.parquet');mapping=response['properties']['parameter']['T2M']
    source=np.array([float(mapping.get(pd.Timestamp(d).strftime('%Y%m%d'),np.nan)) for d in air.date]);source[source<=-990]=np.nan
    if not np.allclose(source,air.air_temperature_c.to_numpy(float),atol=1e-10,rtol=0,equal_nan=True):raise ValueError('POWER forcing differs from saved response')
    finite=json.loads((OUT/'finite_reference_status.json').read_text());timestamp=json.loads((OUT/'time_upper_bound_status.json').read_text())
    if len(items)!=21 or len(frame)!=finite['complete_finite_days'] or int(years.finite_reference_year.sum())!=finite['complete_finite_station_years'] or int(times.possible_complete_year.sum())!=timestamp['possible_complete_years']:
        raise ValueError('Reference totals differ')
    result={'status':'passed','stations':12,'station_years':len(years),'complete_finite_days':len(frame),
            'complete_finite_years':int(years.finite_reference_year.sum()),'time_label_possible_years':int(times.possible_complete_year.sum()),
            'power_days':len(air),'power_api_version':response['header']['api']['version'],
            'scope':'Offline rebuild of the provider timestamp and finite-value screens, all complete-day means and the NASA POWER forcing from bundled public responses. No target masks, source-model weights, model predictions or scoring are replayed.',
            'limitations':'One managed watershed and previously contacted downstream stations; original estimated/corrected flags, physical time basis, sensor error, full source-model separation and redistribution conditions remain unresolved.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
