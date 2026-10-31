#!/usr/bin/env python3
"""Acquire current public metadata for previously unlisted CAMELSH site IDs."""
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_camelsh_hourly'
PRIVATE=ROOT/'private/wrr_camelsh_hourly_reference_20261027';CACHE=PRIVATE/'current_metadata'
SERIES='https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items'
SITES='https://waterservices.usgs.gov/nwis/site/'

def freeze():
    dest=OUT/'unlisted_metadata_plan.json'
    if dest.exists():raise FileExistsError('Preserve metadata extension plan')
    status=json.loads((OUT/'metadata_status.json').read_text());f=PRIVATE/'metadata_screen.csv'
    frame=pd.read_csv(f,dtype={'station_id':str});ids=sorted(frame.loc[frame.metadata_status.eq('not_in_existing_daily_catalog'),'station_id'])
    if len(ids)!=status['status_counts']['not_in_existing_daily_catalog'] or len(ids)!=len(set(ids)):raise ValueError('Unlisted roster differs')
    CACHE.mkdir(parents=True,exist_ok=True,mode=0o700);path=CACHE/'station_ids.json';path.write_text(json.dumps(ids,indent=2)+'\n');path.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc metadata extension after the first 12-site count preflight; before accessing the new target time-series metadata or any target temperatures',
          'selection':'All archive station IDs without a matching record in the existing local USGS daily-temperature metadata, not filtered by expected results.',
          'site_ids':len(ids),'requests':'Current USGS site metadata and time-series metadata for water-temperature daily mean (00010/00003), 25 sites per batch. No water observations, annual statistics or model errors.',
          'limitations':'Missing or failed responses remain unknown. Current metadata dates and site types do not establish complete approved years, physical accuracy, time support, network independence or permissions for derived data.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded metadata extension for',len(ids),'unlisted IDs')

def retrieve():
    plan=json.loads((OUT/'unlisted_metadata_plan.json').read_text());path=CACHE/'station_ids.json'
    ids=json.loads(path.read_text());receipts=[]
    for start in range(0,len(ids),25):
        batch=ids[start:start+25];index=start//25+1;entry={'batch':index,'requested_sites':len(batch)}
        for kind in ('sites','series'):
            dest=CACHE/f'{kind}_{index:02d}.dat'
            params=({'format':'rdb','sites':','.join(batch),'siteOutput':'expanded'} if kind=='sites' else
                    {'f':'json','monitoring_location_id':','.join('USGS-'+x for x in batch),
                     'parameter_code':'00010','statistic_id':'00003','limit':1000})
            try:
                if dest.exists():body=dest.read_bytes();status=200
                else:
                    response=requests.get(SITES if kind=='sites' else SERIES,params=params,timeout=35,headers={'User-Agent':'stream-temperature reference screening/1.0'})
                    status=response.status_code;body=response.content
                part={'http_status':status,'status':'unknown'}
                if status==200:
                    if kind=='sites':
                        lines=[x for x in body.decode('utf-8').splitlines() if x and not x.startswith('#')]
                        if len(lines)<2 or not {'agency_cd','site_no'}.issubset(lines[0].split('\t')):raise ValueError('Invalid site metadata')
                        data=pd.read_csv(io.StringIO('\n'.join(lines)),sep='\t',skiprows=[1],dtype=str)
                        if not data.agency_cd.eq('USGS').all() or not set(data.site_no).issubset(set(batch)):raise ValueError('Unexpected site metadata')
                        part['rows']=len(data)
                    else:
                        data=json.loads(body)
                        if not isinstance(data.get('features'),list) or any(x.get('rel')=='next' for x in data.get('links',[])):raise ValueError('Invalid or paginated series metadata')
                        if any(str(x['properties'].get('monitoring_location_id','')).removeprefix('USGS-') not in batch or str(x['properties'].get('parameter_code'))!='00010' or str(x['properties'].get('statistic_id'))!='00003' for x in data['features']):raise ValueError('Unexpected series metadata')
                        part['rows']=len(data['features'])
                    if not dest.exists():dest.write_bytes(body);dest.chmod(0o600)
                    part.update(status='completed',)
                entry[kind]=part
            except (requests.RequestException,ValueError,KeyError,UnicodeDecodeError,pd.errors.ParserError) as exc:
                entry[kind]={'status':'unknown','error_type':type(exc).__name__}
        receipts.append(entry);print('Metadata batch',index,'site',entry['sites']['status'],'series',entry['series']['status'],flush=True)
    path=CACHE/'receipt.json';path.write_text(json.dumps(receipts,indent=2)+'\n');path.chmod(0o600)
    done=sum(x['sites']['status']=='completed' and x['series']['status']=='completed' for x in receipts)
    result={'status':'completed' if done==len(receipts) else 'partial_unknown','requested_sites':len(ids),'batches':len(receipts),
            'complete_batches':done,'site_rows_returned':sum(x['sites'].get('rows',0) for x in receipts),
            'series_rows_returned':sum(x['series'].get('rows',0) for x in receipts),
            'temperature_values_opened':False,'model_errors_opened':False,'limits':plan['limitations']}
    (OUT/'unlisted_metadata_acquisition.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','retrieve']);a=p.parse_args();freeze() if a.action=='freeze' else retrieve()
