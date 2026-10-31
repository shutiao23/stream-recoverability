#!/usr/bin/env python3
"""Compare NASA POWER UTC and LST hourly values at the Truckee test site."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import gzip
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';CACHE=PRIVATE/'power_time_standards';URL='https://power.larc.nasa.gov/api/temporal/hourly/point'

def freeze():
    dest=OUT/'power_time_standards_plan.json'
    if dest.exists():raise FileExistsError('Preserve time-standard plan')
    forcing=json.loads((OUT/'exploratory_forcing_status.json').read_text());status=json.loads((OUT/'exploratory_score_status.json').read_text())
    roster=PRIVATE/'exploratory_roster.csv';daily=PRIVATE/'exploratory_power_response.json';r=pd.read_csv(roster)
    if forcing['status']!='forcing_complete' or status['status']!='exploratory_scored' or len(r)!=4:
        raise ValueError('Fixed reference or daily forcing changed')
    years=sorted(r.year.astype(int).unique().tolist());params=forcing['parameters'];lon=float(params['longitude']);lat=float(params['latitude'])
    if years!=[2011,2013,2014,2020] or not (-127.5<lon<-112.5):raise ValueError('Expected reference years or longitude band changed')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after viewing Truckee results and NASA documentation; before inspecting hourly UTC/LST values',
          'source_documentation':'https://power.larc.nasa.gov/docs/services/api/temporal/hourly/',
          'cohort':'All four reference years at the same rounded coordinates used in the original daily T2M query; retrieve current hourly UTC and LST, not water observations.',
          'expected_rule':'At longitude -120.21 degrees, NASA 15-degree longitude bands imply LST=UTC-8 hours. Compare LST hours with UTC timestamps eight hours later, for January 1 through December 30 of each year; exclude December 31 to keep all UTC hours inside the same annual request.',
          'daily_comparison':'Compare the mean of 24 finite LST hourly T2M values against the previously retrieved POWER daily T2M for the same dates; report actual differences, missing values and rounding, without assuming equality.',
          'site_water_clock':'Provider EML labels water times PST; if that means fixed UTC-8, expected hourly label boundaries agree. This cannot establish whether the provider actually applied daylight saving or other historical clock shifts.',
          'years':years,'latitude':lat,'longitude':lon,'expected_utc_minus_lst_hours':8,
          'limits':'A current API comparison at one grid point does not validate water sensor clocks, historical API vintage, spatial representation, physical air-temperature accuracy or independent climates.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded POWER hourly time-standard check')

def one(p,year,standard):
    path=CACHE/f'{year}_{standard}.json.gz';receipt=CACHE/f'{year}_{standard}.receipt.json'
    if path.exists() and receipt.exists():
        x=json.loads(receipt.read_text())
        return x
    if path.exists() or receipt.exists():raise ValueError('Incomplete cached response')
    params={'parameters':'T2M','community':'RE','longitude':p['longitude'],'latitude':p['latitude'],
            'start':f'{year}0101','end':f'{year}1231','format':'JSON','time-standard':standard}
    response=requests.get(URL,params=params,timeout=55,headers={'User-Agent':'stream-temperature temporal alignment research/1.0'});response.raise_for_status()
    raw=response.json();values=raw['properties']['parameter']['T2M'];head=raw['header']
    if head.get('time_standard')!=standard or not isinstance(values,dict) or not values:raise ValueError('Unexpected POWER response')
    tmp=path.with_suffix('.tmp')
    try:
        with gzip.open(tmp,'wb',compresslevel=5) as f:f.write(response.content)
        os.replace(tmp,path);path.chmod(0o600)
    except Exception:
        if tmp.exists():tmp.unlink()
        raise
    result={'year':year,'standard':standard,'status':'completed','hour_labels':len(values),'api_version':head.get('api',{}).get('version'),'sources':head.get('sources',[])}
    receipt.write_text(json.dumps(result,indent=2)+'\n');receipt.chmod(0o600);return result

def retrieve(workers):
    p=json.loads((OUT/'power_time_standards_plan.json').read_text());verify(p)
    if workers<1 or workers>2:raise ValueError('Use one or two weather requests concurrently')
    CACHE.mkdir(parents=True,exist_ok=True,mode=0o700);results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one,p,y,s):(y,s) for y in p['years'] for s in ('UTC','LST')}
        for future in as_completed(futures):
            year,standard=futures[future]
            try:x=future.result()
            except Exception as e:x={'year':year,'standard':standard,'status':'unknown','error_type':type(e).__name__}
            results.append(x);print('POWER hourly',year,standard,x['status'],flush=True)
    path=CACHE/'acquisition.json';path.write_text(json.dumps(sorted(results,key=lambda x:(x['year'],x['standard'])),indent=2)+'\n');path.chmod(0o600)
    result={'status':'completed' if len(results)==8 and all(x['status']=='completed' for x in results) else 'partial_unknown',
            'requested_responses':8,'completed_responses':sum(x['status']=='completed' for x in results),'limitations':p['limits']}
    (OUT/'power_time_acquisition.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

def compare():
    p=json.loads((OUT/'power_time_standards_plan.json').read_text());verify(p);acq=json.loads((OUT/'power_time_acquisition.json').read_text())
    receipt=CACHE/'acquisition.json'
    if acq['status']!='completed':raise ValueError('Incomplete weather responses')
    items=json.loads(receipt.read_text());data={}
    for item in items:
        path=CACHE/f"{item['year']}_{item['standard']}.json.gz"
        with gzip.open(path,'rt') as f:body=json.load(f)
        data[(item['year'],item['standard'])]=body['properties']['parameter']['T2M']
    previous=json.loads((PRIVATE/'exploratory_power_response.json').read_text())['properties']['parameter']['T2M'];records=[];days=[]
    for y in p['years']:
        utc=data[(y,'UTC')];lst=data[(y,'LST')]
        for date in pd.date_range(f'{y}-01-01',f'{y}-12-30'):
            hourly=[]
            for hour in range(24):
                local=date+pd.Timedelta(hours=hour);u=local+pd.Timedelta(hours=p['expected_utc_minus_lst_hours'])
                a=float(lst.get(local.strftime('%Y%m%d%H'),np.nan));b=float(utc.get(u.strftime('%Y%m%d%H'),np.nan))
                a=a if a>-990 else np.nan;b=b if b>-990 else np.nan;records.append((a,b));hourly.append(a)
            d=float(previous.get(date.strftime('%Y%m%d'),np.nan));d=d if d>-990 else np.nan
            m=float(np.mean(hourly)) if np.isfinite(hourly).all() else np.nan;days.append((d,m))
    x=np.asarray(records,float);valid=np.isfinite(x).all(axis=1);delta=np.abs(x[:,0]-x[:,1]);d=np.asarray(days,float);ok=np.isfinite(d).all(axis=1);dd=np.abs(d[:,0]-d[:,1])
    result={'status':'computed_posthoc','expected_hours':len(x),'finite_hour_pairs':int(valid.sum()),'hour_pairs_equal_1e_6':int(np.count_nonzero(valid&(delta<=1e-6))),
            'max_hour_difference_c':float(np.max(delta[valid])) if valid.any() else None,
            'expected_days':len(d),'complete_hourly_and_daily_pairs':int(ok.sum()),'daily_differences_le_0_01':int(np.count_nonzero(ok&(dd<=.01000001))),
            'mean_daily_difference_c':float(np.mean(dd[ok])) if ok.any() else None,'max_daily_difference_c':float(np.max(dd[ok])) if ok.any() else None,
            'requested_utc_minus_lst_hours':p['expected_utc_minus_lst_hours'],'api_versions':sorted({str(x.get('api_version')) for x in items}),
            'interpretation':'A numerical match tests the current POWER products at this grid point only. PST in the DWR metadata is consistent with UTC-8 if fixed standard time; actual sensor clocks and daylight handling remain unverified.',
            'limitations':p['limits']}
    (OUT/'power_time_comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','retrieve','compare']);p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    {'freeze':freeze,'retrieve':lambda:retrieve(a.workers),'compare':compare}[a.action]()
