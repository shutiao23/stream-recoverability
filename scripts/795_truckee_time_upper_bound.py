#!/usr/bin/env python3
"""Acquire fixed DWR files and compute timestamp-only reference upper bounds.

Full files contain temperature measurements; the qualification calculation
reads only station and timestamp columns, not temperature or model errors.
"""
from __future__ import annotations
import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import gzip
import json
import os
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr'
PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';NODE='https://cn.dataone.org/cn/v2/resolve/'

def entities():
    stations=pd.read_csv(OUT/'station_metadata_03.csv',dtype=str)
    codes=set(stations.Station_Code);rows=[]
    for e in ET.parse(OUT/'metadata.xml').getroot().iter():
        if e.tag.split('}')[-1]!='dataTable':continue
        children=list(e);name=next((x.text for x in children if x.tag.split('}')[-1]=='entityName'),None)
        if name not in codes:continue
        urls=[x.text.strip() for x in e.iter() if x.tag.split('}')[-1]=='url' and x.text]
        sizes=[int(x.text) for x in e.iter() if x.tag.split('}')[-1]=='size' and x.text]
        if len(urls)!=1 or len(sizes)!=1:raise ValueError('Ambiguous station file')
        rows.append({'station_code':name,'url':urls[0],'bytes':sizes[0],})
    if len(rows)!=12 or {x['station_code'] for x in rows}!=codes:raise ValueError('Unexpected DWR station roster')
    return sorted(rows,key=lambda x:x['station_code'])

def freeze():
    target=OUT/'time_upper_bound_plan.json'
    if target.exists():raise FileExistsError('Preserve time-support plan')
    metadata=json.loads((OUT/'station_metadata_status.json').read_text());prior=json.loads((OUT/'prior_proximity_status.json').read_text())
    if metadata['status']!='completed' or prior['status']!='metadata_only_with_known_truckee_prior_cache':raise ValueError('Metadata or prior-contact check incomplete')
    roster=entities();stations=pd.read_csv(OUT/'station_metadata_03.csv',dtype=str)
    invalid=[]
    for row in stations.itertuples(index=False):
        begin=pd.to_datetime(row.Dataset_Begin_Date,errors='raise');end=pd.to_datetime(row.Dataset_End_Date,errors='raise')
        if begin>end:invalid.append(row.Station_Code)
    p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after metadata, prior-cache and coordinate screening; before station time-series download or target error evaluation',
       'selection':'All 12 EML station files, not selected by temperature, label completeness or prediction error. Include the one station with an inconsistent reported date envelope; mark that metadata inconsistency unresolved.',
       'invalid_date_envelopes':invalid,'resources':roster,'estimated_raw_bytes':sum(x['bytes'] for x in roster),
       'time_upper_bound':'Count only station code and timestamp labels. Treat EML PST as reported clock labels; a day can be complete only if all 96 unique quarter-hour labels occur exactly once. A year can be complete only if every calendar day meets that condition. Early hourly periods fail this deliberately strict 15-minute test.',
       'limitations':'Full source files contain measurements and will be downloaded into an ignored local folder; the time-screen calculation does not evaluate those values. A time-label upper bound ignores NA values, point quality, estimated/corrected status and clock uncertainty. All sites are one managed watershed, with previously accessed downstream USGS sites; no independent climate or scored accuracy claim.'}
    target.write_text(json.dumps(p,indent=2)+'\n');print(json.dumps({'station_files':len(roster),'total_bytes':p['estimated_raw_bytes'],'inconsistent_date_envelopes':len(invalid)},indent=2))

def acquire_one(item):
    dest=PRIVATE/'raw'/f"{item['station_code']}.csv.gz";receipt=dest.with_suffix('.receipt.json')
    dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if dest.exists() and receipt.exists():
        saved=json.loads(receipt.read_text())
        return saved
    if dest.exists() or receipt.exists():raise ValueError('Incomplete existing cache; preserve for inspection')
    tmp=dest.with_suffix('.tmp');size=0
    try:
        with requests.get(NODE+quote(item['url'],safe=''),timeout=(15,45),stream=True,headers={'User-Agent':'stream-temperature reference qualification/1.0'}) as response:
            response.raise_for_status()
            if not response.url.startswith('https://gmn.edirepository.org/mn/v2/object/'):raise ValueError('Unexpected source member node')
            with gzip.open(tmp,'wb',compresslevel=5) as f:
                for block in response.iter_content(256*1024):
                    if not block:continue
                    size+=len(block)
                    if size>item['bytes']:raise ValueError('Downloaded file exceeds EML size')
                    f.write(block)
        if size!=item['bytes']:raise ValueError('Downloaded station file differs from EML')
        os.replace(tmp,dest);dest.chmod(0o600)
        saved={'station_code':item['station_code'],'status':'completed','source_bytes':size,}
        receipt.write_text(json.dumps(saved,indent=2)+'\n');receipt.chmod(0o600);return saved
    except Exception:
        if tmp.exists():tmp.unlink()
        raise

def acquire(workers):
    p=json.loads((OUT/'time_upper_bound_plan.json').read_text());verify(p)
    if workers<1 or workers>3:raise ValueError('Workers must be 1 to 3')
    items=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(acquire_one,x):x['station_code'] for x in p['resources']}
        for future in as_completed(futures):
            site=futures[future]
            try:result=future.result()
            except Exception as e:result={'station_code':site,'status':'unknown','error_type':type(e).__name__}
            items.append(result);print('Truckee file',site,result['status'],flush=True)
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);path=PRIVATE/'acquisition.json';path.write_text(json.dumps(sorted(items,key=lambda x:x['station_code']),indent=2)+'\n');path.chmod(0o600)
    status={'status':'completed' if len(items)==12 and all(x['status']=='completed' for x in items) else 'partial_unknown',
            'requested_station_files':12,'available_station_files':sum(x['status']=='completed' for x in items),
            'raw_measurement_files_downloaded':True,'temperature_values_scored':False,'model_errors_opened':False,
            'limits':p['limitations']}
    (OUT/'time_acquisition.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

def screen():
    p=json.loads((OUT/'time_upper_bound_plan.json').read_text());verify(p);a=json.loads((OUT/'time_acquisition.json').read_text());receipt=PRIVATE/'acquisition.json'
    if a['status']!='completed':raise ValueError('Incomplete station acquisition; no unavailable site assumed empty')
    results=[];days=[]
    for entry in json.loads(receipt.read_text()):
        site=entry['station_code'];path=PRIVATE/'raw'/f'{site}.csv.gz'
        pieces=[];row_total=0
        for block in pd.read_csv(path,compression='gzip',usecols=['Station_Code','Date_Time'],dtype=str,chunksize=100000):
            if not block.Station_Code.eq(site).all():raise ValueError('Wrong station in file')
            stamp=pd.to_datetime(block.Date_Time,format='%m/%d/%Y %H:%M:%S',errors='coerce')
            if stamp.isna().any():raise ValueError('Unparseable reported time label')
            row_total+=len(stamp);pieces.append(stamp)
        timestamps=pd.concat(pieces,ignore_index=True)
        good=(timestamps.dt.minute%15==0)&timestamps.dt.second.eq(0)&timestamps.dt.microsecond.eq(0)
        d=pd.DataFrame({'day':timestamps.dt.normalize(),'stamp':timestamps,'valid':good})
        daily=d.groupby('day').agg(rows=('stamp','size'),unique=('stamp','nunique'),valid=('valid','sum'))
        daily['label_complete']=daily.rows.eq(96)&daily.unique.eq(96)&daily.valid.eq(96)
        annual=[]
        for year,g in daily.groupby(daily.index.year):
            expected=366 if calendar.isleap(int(year)) else 365;complete=int(g.label_complete.sum())
            full=len(g)==expected and complete==expected
            annual.append({'station_code':site,'year':int(year),'days_with_any_label':len(g),'days_with_96_unique_quarters':complete,
                           'expected_days':expected,'possible_complete_year':bool(full)})
        z=pd.DataFrame(annual);days.append(z)
        results.append({'station_code':site,'rows':row_total,'reported_years':len(z),'possible_complete_years':int(z.possible_complete_year.sum()),
                        'at_least_four_possible_years':bool(z.possible_complete_year.sum()>=4),
                        'invalid_metadata_envelope':site in p['invalid_date_envelopes']})
        print('Time labels screened:',site,flush=True)
    annual=pd.concat(days,ignore_index=True);stations=pd.DataFrame(results)
    for name,frame in [('timestamp_station_years.csv',annual),('timestamp_station_summary.csv',stations)]:
        f=PRIVATE/name;frame.to_csv(f,index=False);f.chmod(0o600)
    out={'status':'timestamp_upper_bound_completed','stations':len(stations),'station_years':len(annual),
         'possible_complete_years':int(annual.possible_complete_year.sum()),'sites_at_least_four_possible_years':int(stations.at_least_four_possible_years.sum()),
         'stations_with_inconsistent_metadata_envelope':int(stations.invalid_metadata_envelope.sum()),
         'temperature_values_analyzed':False,'prediction_errors_analyzed':False,'limitations':p['limitations']}
    (OUT/'time_upper_bound_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','acquire','screen']);parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args();{'freeze':freeze,'acquire':lambda:acquire(args.workers),'screen':screen}[args.action]()
