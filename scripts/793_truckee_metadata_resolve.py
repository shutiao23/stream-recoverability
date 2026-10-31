#!/usr/bin/env python3
"""Retrieve the same frozen metadata tables via public DataONE resolution."""
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
from urllib.parse import quote
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';NODE='https://cn.dataone.org/cn/v2/resolve/'

def freeze():
    dest=OUT/'station_metadata_access_amendment.json';source=OUT/'station_metadata_plan.json'
    if dest.exists():raise FileExistsError('Preserve existing access amendment')
    plan=json.loads(source.read_text())
    if any(OUT.glob('station_metadata_*.csv')):raise ValueError('Some metadata tables were already saved')
    result={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc access amendment before saving station metadata tables or opening observations',
        'reason':'The coordinating-node object endpoint returned HTTP 404 for the first frozen table. Its public resolve endpoint redirects to the DataONE member-node object service; two test metadata table responses were seen but not saved.',
        'method':'Retrieve the same three preselected metadata table identifiers through the public resolver, and verify the member-node address and EML-declared byte size. No station measurement tables are requested.',
        'limits':plan['requirements']}
    dest.write_text(json.dumps(result,indent=2)+'\n');print('Recorded DataONE public-resolver amendment')

def fetch():
    amendment=json.loads((OUT/'station_metadata_access_amendment.json').read_text());p=json.loads((OUT/'station_metadata_plan.json').read_text())
    output=[]
    for i,item in enumerate(p['tables'],1):
        dest=OUT/f'station_metadata_{i:02d}.csv'
        if dest.exists():raise FileExistsError('Preserve saved metadata')
        r=requests.get(NODE+quote(item['url'],safe=''),timeout=35,headers={'User-Agent':'stream-temperature reference qualification/1.0'});r.raise_for_status()
        if not r.url.startswith('https://gmn.edirepository.org/mn/v2/object/') or len(r.content)!=item['size']:
            raise ValueError('Unexpected member node or declared byte size')
        frame=pd.read_csv(io.BytesIO(r.content),dtype=str);dest.write_bytes(r.content)
        output.append({'name':item['name'],'file':dest.name,'rows':len(frame),'columns':list(frame.columns),'byte_size_matches_eml':True})
        print('Retrieved metadata table:',item['name'],flush=True)
    status={'status':'completed','tables':output,'station_time_series_opened':False,'temperature_values_opened':False,'model_errors_opened':False,
            'limitations':p['requirements'],'rights_note':p['rights']}
    (OUT/'station_metadata_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);a=p.parse_args();freeze() if a.action=='freeze' else fetch()
