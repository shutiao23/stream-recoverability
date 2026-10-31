#!/usr/bin/env python3
"""Acquire parent-series continuous water data for all daily target years."""
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import shutil
import time
import pandas as pd
import requests
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';RAW=PRIVATE/'continuous_target'
URL='https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items'

def freeze():
    h=T.load_script('usgs_continuous_hash',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');path=OUT/'continuous_target_plan.json'
    if path.exists():raise FileExistsError('Preserve continuous-target plan')
    status=json.loads((OUT/'continuous_metadata_status.json').read_text());network=json.loads((OUT/'network_status.json').read_text());daily=PRIVATE/'daily_target_roster.csv';series=PRIVATE/'continuous_metadata.csv'
    if status['status']!='completed_metadata_only' or network['status']!='completed':
        raise ValueError('Continuous metadata or network audit incomplete')
    roster=pd.read_csv(daily,dtype={'station_id':str});roster=roster[roster.eligible_partial_history].copy()
    meta=pd.read_csv(series,dtype={'station_id':str,'series_id':str});meta=meta[meta.daily_parent_match].copy()
    if meta.station_id.duplicated().any():raise ValueError('Multiple exact daily-parent series; do not choose by values')
    target=roster.merge(meta[['station_id','series_id']],on='station_id',how='left',validate='many_to_one')
    file=PRIVATE/'continuous_target_roster.csv';target.to_csv(file,index=False);file.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after all daily observations, witness results, daily feasibility and source-network metadata; before acquiring continuous water values or this cohort model errors',
      'cohort':'All eight previously identified approved complete daily target years with >=3 partially supported historical years, including the already contacted source-panel station. No selection by continuous temperatures or future prediction error.',
      'series':'Use only the unique instantaneous time-series ID identified as the parent of the original daily-mean series. Unknown or ambiguous parent IDs are retained as unknown, never replaced by a better-looking series.',
      'request':'For each target calendar year request public continuous observations for the parent series from the previous December 31 UTC to the next January 2 UTC, using one-year-plus-margin windows, pagination and saved response bytes. Request timestamp, temperature, approval status and qualifiers; no model predictions.',
      'screen_to_follow':'In fixed site-standard time and separately in documented local civil time, count genuinely distinct physical hourly bins and quarter-hour grid slots per day, retaining only approved finite records without any nonempty qualifier. Unknown codes are not assumed good. Daily DST boundaries have 23 or 25 physical hours under civil time; fixed-standard days are 24 hours. Record observed-vs-reported-daily mean differences without using them to pick cases.',
      'limitations':'Parent ID does not prove an unchanged sensor or error-free values. Strict criteria, date basis and hourly vs quarter-hour sensitivity require explicit follow-up. Source river-network overlap, previously inspected daily values, flowpath and climate independence remain unresolved. This is not a blind evaluation.',
      'sites':int(target.station_id.nunique()),'target_years':len(target),'years_with_parent':int(target.series_id.notna().sum()),
      'endpoint':URL}
    path.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({k:plan[k] for k in ['sites','target_years','years_with_parent','status']},indent=2))

def run():
    h=T.load_script('usgs_continuous_hash2',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');p=json.loads((OUT/'continuous_target_plan.json').read_text())
    if (OUT/'continuous_target_acquisition.json').exists():raise FileExistsError('Preserve intake status')
    roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str,'series_id':str});RAW.mkdir(parents=True,exist_ok=True,mode=0o700);receipts=[];stop=False
    for row in roster.sort_values(['station_id','year']).itertuples(index=False):
        result={'station_id':row.station_id,'year':int(row.year),'status':'unknown','pages':[],'features':0}
        if pd.isna(row.series_id):result['reason']='missing_unique_parent';receipts.append(result);continue
        if stop:result['reason']='service_or_storage_stop';receipts.append(result);continue
        params={'f':'json','time_series_id':row.series_id,'time':f'{row.year-1}-12-31T00:00:00Z/{row.year+1}-01-02T00:00:00Z',
                'properties':'time,value,approval_status,qualifier,time_series_id','skipGeometry':'true','limit':50000}
        url=URL;page=0
        try:
            while url:
                if shutil.disk_usage(ROOT).free<50*1024*1024:result['reason']='insufficient_disk_reserve';stop=True;break
                r=requests.get(url,params=params,timeout=90,headers={'User-Agent':'stream-temperature reference qualification/1.0'});params=None
                if r.status_code!=200:
                    result['http_status']=r.status_code;result['reason']='http_failure';stop=r.status_code in (401,403,429,503);break
                doc=r.json()
                if not isinstance(doc.get('features'),list):raise ValueError('Unexpected continuous-data response')
                for feature in doc['features']:
                    props=feature.get('properties',{})
                    if props.get('time_series_id') not in (None,row.series_id):raise ValueError('Unexpected continuous series')
                f=RAW/f'{row.station_id}_{row.year}_{page:02d}.json.gz'
                if f.exists():raise FileExistsError('Preserve raw continuous response')
                with gzip.open(f,'wb') as stream:stream.write(r.content)
                f.chmod(0o600);result['features']+=len(doc['features']);result['pages'].append({'file':f.name,'features':len(doc['features'])})
                next_links=[x.get('href') for x in doc.get('links',[]) if x.get('rel')=='next']
                if len(next_links)>1:raise ValueError('Ambiguous pagination')
                url=next_links[0] if next_links else None
                if url and not str(url).startswith('https://api.waterdata.usgs.gov/'):raise ValueError('Unexpected pagination host')
                page+=1
                if page>10:raise ValueError('Unexpected page count')
                time.sleep(1)
            if not url and 'reason' not in result:result['status']='completed'
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:result['reason']=type(e).__name__
        receipts.append(result);print('Continuous target intake',len(receipts),'of',len(roster),result['status'],result.get('reason',''),flush=True)
    file=PRIVATE/'continuous_target_receipts.json';file.write_text(json.dumps(receipts,indent=2)+'\n');file.chmod(0o600)
    out={'status':'completed' if all(x['status']=='completed' for x in receipts) else 'partial_unknown','requested_station_years':len(roster),
         'completed_station_years':sum(x['status']=='completed' for x in receipts),'downloaded_features':sum(x['features'] for x in receipts),
         'continuous_values_opened_for_qualification':False,'model_predictions_or_errors_calculated':False,'limitations':p['limitations']}
    (OUT/'continuous_target_acquisition.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
