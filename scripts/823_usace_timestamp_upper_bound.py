#!/usr/bin/env python3
"""Acquire fixed level-1 files and inspect only their 15-minute time labels."""
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

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';RAW=PRIVATE/'raw_level1'

def freeze():
    dest=OUT/'time_upper_bound_plan.json'
    if dest.exists():raise FileExistsError('Preserve timestamp plan')
    roster=PRIVATE/'roster.csv';rstatus=json.loads((OUT/'roster_status.json').read_text());network=json.loads((OUT/'network_status.json').read_text());support=json.loads((OUT/'support_metadata_status.json').read_text())
    if network['status']!='completed' or support['status']!='completed':raise ValueError('Metadata or bounded network audit incomplete')
    f=pd.read_csv(roster,dtype={'resource_id':str,'gage_ids':str});f=f[f.metadata_candidate].sort_values('resource_id')
    if len(f)!=10:raise ValueError('Fixed metadata-candidate count differs')
    receipt=PRIVATE/'nldi_metadata/receipt.json';summary=PRIVATE/'nldi_metadata/gage_summary.csv'
    files=[]
    for r in f.itertuples(index=False):
        url=str(r.latest_level1_url)
        if url.startswith('http://www.hydroshare.org/'):url='https://'+url[len('http://'):]
        if not url.startswith('https://www.hydroshare.org/resource/'+r.resource_id+'/data/contents/') or 'level1-qaqc_' not in str(r.latest_level1_filename).lower():
            raise ValueError('Unexpected candidate file URL')
        files.append({'resource_id':r.resource_id,'filename':r.latest_level1_filename,'url':url,'expected_bytes':int(r.latest_level1_size),'gage_ids':str(r.gage_ids).split(';')})
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc after all source metadata, README, exact prior-ID and bounded NLDI results, before opening candidate level-1 files or target errors',
          'selection':'All 10 frozen metadata candidates, including those with known prior network hits; retain the 11th exact prior-gage resource as excluded. No candidate selected by observed temperatures or reconstruction errors.',
          'resource_files':files,'total_expected_bytes':sum(x['expected_bytes'] for x in files),
          'time_rule':'Each resource README says timestamp is ISO 8601 Mountain Standard Time, UTC-07:00. Treat naive labels as reported fixed MST; convert explicitly offset labels to UTC-07. A day is possibly complete only with exactly 96 unique on-grid quarter-hour labels and no duplicates; a calendar year needs every day. This is a timestamp-only upper bound.',
          'handling':'Full level-1 files contain water values and will be stored privately under source CC BY 4.0 with attribution due before sharing. Qualification parses only timestamp fields, not temperature values or model errors.',
          'network_limits':'A 200-km NLDI screen is a bounded gauge proxy, not proof of a sensor\u2019s actual flowline or climate independence. Some candidates have known earlier source/network connections; upstream/downstream and tributary sites are not automatically independent.',
          'quality_limits':'Authors describe quality control plus fouling/calibration corrections, but timestamp completeness does not establish finite, nonestimated, uncorrected or physically accurate water values. Unknown point flags, metadata vintage, sensor clocks and reservoir operations remain.',
          }
    dest.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({'resources':len(files),'expected_bytes':plan['total_expected_bytes']},indent=2))

def one(item):
    RAW.mkdir(parents=True,exist_ok=True,mode=0o700);dest=RAW/f"{item['resource_id']}.csv.gz";receipt=RAW/f"{item['resource_id']}.json"
    if dest.exists() and receipt.exists():
        x=json.loads(receipt.read_text())
        return x
    if dest.exists() or receipt.exists():raise ValueError('Incomplete existing cache')
    tmp=RAW/f"{item['resource_id']}.tmp";size=0;
    try:
        with requests.get(item['url'],stream=True,timeout=(15,45),headers={'User-Agent':'stream-temperature reference qualification/1.0'}) as r:
            r.raise_for_status()
            if not r.url.startswith('https://storage.googleapis.com/') or r.url.startswith('https://www.hydroshare.org/'):raise ValueError('Unexpected resource host')
            with gzip.open(tmp,'wb',compresslevel=5) as f:
                for block in r.iter_content(256*1024):
                    if block:
                        size+=len(block)
                        if size>item['expected_bytes']:raise ValueError('Source file exceeds declared size')
                        f.write(block)
        if size!=item['expected_bytes']:raise ValueError('Source file size differs from metadata')
        os.replace(tmp,dest);dest.chmod(0o600)
        result={'resource_id':item['resource_id'],'status':'completed','bytes':size,}
        receipt.write_text(json.dumps(result,indent=2)+'\n');receipt.chmod(0o600);return result
    except Exception:
        if tmp.exists():tmp.unlink()
        raise

def acquire(workers):
    p=json.loads((OUT/'time_upper_bound_plan.json').read_text());verify(p)
    if not 1<=workers<=2:raise ValueError('Use one or two simultaneous downloads')
    results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fs={pool.submit(one,item):item['resource_id'] for item in p['resource_files']}
        for future in as_completed(fs):
            rid=fs[future]
            try:r=future.result()
            except Exception as e:r={'resource_id':rid,'status':'unknown','error_type':type(e).__name__}
            results.append(r);print('Level-1 file',len(results),'/',len(fs),r['status'],flush=True)
    path=PRIVATE/'time_acquisition.json';path.write_text(json.dumps(sorted(results,key=lambda x:x['resource_id']),indent=2)+'\n');path.chmod(0o600)
    status={'status':'completed' if len(results)==10 and all(x['status']=='completed' for x in results) else 'partial_unknown',
        'requested_resources':10,'downloaded_resources':sum(x['status']=='completed' for x in results),'raw_water_values_downloaded':True,'water_values_qualified_or_scored':False,'model_errors_opened':False,'limits':p['quality_limits']}
    (OUT/'time_acquisition.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

def timestamps(values):
    text=values.astype(str).str.strip();explicit=text.str.contains(r'(?:Z|[+-]\d{2}:?\d{2})$',regex=True)
    if explicit.all():
        t=pd.to_datetime(text,utc=True,errors='coerce').dt.tz_convert('Etc/GMT+7').dt.tz_localize(None);kind='explicit_offsets_to_utc_minus_7'
    elif not explicit.any():t=pd.to_datetime(text,errors='coerce');kind='naive_labels_assumed_fixed_mst'
    else:raise ValueError('Mixed timestamp offset semantics')
    if t.isna().any():raise ValueError('Unparseable timestamp')
    return t,kind

def screen():
    p=json.loads((OUT/'time_upper_bound_plan.json').read_text());verify(p);a=json.loads((OUT/'time_acquisition.json').read_text());receipt=PRIVATE/'time_acquisition.json'
    if a['status']!='completed':raise ValueError('Partial data cannot be counted as empty')
    years=[];sites=[]
    for item in json.loads(receipt.read_text()):
        rid=item['resource_id'];path=RAW/f'{rid}.csv.gz'
        chunks=[];kinds=set()
        for block in pd.read_csv(path,compression='gzip',usecols=['timestamp'],dtype=str,chunksize=100000):
            t,kind=timestamps(block.timestamp);chunks.append(t);kinds.add(kind)
        if len(kinds)!=1:raise ValueError('Timestamp semantics vary across chunks')
        t=pd.concat(chunks,ignore_index=True);d=pd.DataFrame({'day':t.dt.normalize(),'time':t,'valid':t.dt.minute.mod(15).eq(0)&t.dt.second.eq(0)&t.dt.microsecond.eq(0)})
        grouped=d.groupby('day').agg(rows=('time','size'),unique=('time','nunique'),valid=('valid','sum'))
        grouped['possible_day']=grouped.rows.eq(96)&grouped.unique.eq(96)&grouped.valid.eq(96);rows=[]
        for y,g in grouped.groupby(grouped.index.year):
            expected=366 if pd.Timestamp(int(y),12,31).is_leap_year else 365;n=int(g.possible_day.sum());rows.append({'resource_id':rid,'year':int(y),'days_with_labels':len(g),
                'days_with_96_unique_quarters':n,'expected_days':expected,'possible_complete_year':len(g)==expected and n==expected})
        year=pd.DataFrame(rows);years.append(year);sites.append({'resource_id':rid,'timestamp_format':next(iter(kinds)),
            'reported_years':len(year),'possible_complete_years':int(year.possible_complete_year.sum()),'at_least_four_possible_years':bool(year.possible_complete_year.sum()>=4)})
        print('Timestamp-only screen',len(sites),'of 10',flush=True)
    annual=pd.concat(years,ignore_index=True);site=pd.DataFrame(sites)
    for name,frame in [('timestamp_station_years.csv',annual),('timestamp_station_summary.csv',site)]:
        path=PRIVATE/name;frame.to_csv(path,index=False);path.chmod(0o600)
    status={'status':'timestamp_upper_bound_completed','resources':len(site),'station_years':len(annual),
            'possible_complete_years':int(annual.possible_complete_year.sum()),'sites_at_least_four_possible_years':int(site.at_least_four_possible_years.sum()),
            'timestamp_formats':site.timestamp_format.value_counts().to_dict(),'water_values_evaluated':False,'prediction_errors_evaluated':False,
            'limitations':p['time_rule']+' '+p['network_limits']+' '+p['quality_limits']}
    (OUT/'time_upper_bound_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    q=argparse.ArgumentParser();q.add_argument('action',choices=['freeze','acquire','screen']);q.add_argument('--workers',type=int,default=2);a=q.parse_args()
    {'freeze':freeze,'acquire':lambda:acquire(a.workers),'screen':screen}[a.action]()
