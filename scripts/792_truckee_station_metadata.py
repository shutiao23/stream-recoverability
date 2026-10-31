#!/usr/bin/env python3
"""Read only the three Truckee station/instrument metadata tables."""
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';NODE='https://cn.dataone.org/cn/v2/object/'
NAMES={'Stations Metadata','Instrument Type Date Ranges','Instrument Specifications'}

def tables():
    root=ET.parse(OUT/'metadata.xml').getroot();out=[]
    for elem in root.iter():
        if elem.tag.split('}')[-1]!='dataTable':continue
        children=list(elem);name=next((x.text for x in children if x.tag.split('}')[-1]=='entityName'),None)
        if name not in NAMES:continue
        urls=[x.text.strip() for x in elem.iter() if x.tag.split('}')[-1]=='url' and x.text]
        sizes=[int(x.text) for x in elem.iter() if x.tag.split('}')[-1]=='size' and x.text]
        if len(urls)!=1 or len(sizes)!=1:raise ValueError('Ambiguous EML table metadata')
        out.append({'name':name,'url':urls[0],'size':sizes[0],})
    if {x['name'] for x in out}!=NAMES:raise ValueError('Expected metadata tables absent')
    return sorted(out,key=lambda x:x['name'])

def freeze():
    status=json.loads((OUT/'metadata_status.json').read_text());source=OUT/'metadata.xml';dest=OUT/'station_metadata_plan.json'
    if dest.exists():raise FileExistsError('Preserve metadata table plan')
    if status['status']!='metadata_acquired':raise ValueError('EML metadata changed')
    entries=tables();plan={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc after inspecting public EML and prior Truckee catalog records; before reading station tables or target measurements',
        'requests':'Only the station list, sensor date ranges and instrument specifications named by EML, through public DataONE API. No station time-series table is requested.',
        'tables':entries,'rights':'The EDI EML describes CC0, whereas the state discovery catalog says CC BY; retain source attribution and reconcile the discrepancy for any release.',
        'requirements':'Evaluate station dates and prior-site proximity/network contact before selecting sites. EML says data passed validation and labels timestamp PST, but station-level estimated flags and the precise DST convention remain to be clarified; missing or corrected measurements are not presumed absent.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded station/instrument metadata-only retrieval')

def fetch():
    p=json.loads((OUT/'station_metadata_plan.json').read_text())
    outputs=[]
    for index,item in enumerate(p['tables'],1):
        dest=OUT/f'station_metadata_{index:02d}.csv'
        if dest.exists():raise FileExistsError('Preserve previously acquired metadata table')
        r=requests.get(NODE+quote(item['url'],safe=''),timeout=35,headers={'User-Agent':'stream-temperature reference qualification/1.0'});r.raise_for_status()
        if len(r.content)!=item['size']:raise ValueError('Table differs from EML size')
        table=pd.read_csv(io.BytesIO(r.content),dtype=str);dest.write_bytes(r.content)
        outputs.append({'name':item['name'],'file':dest.name,'rows':len(table),'columns':list(table.columns)})
        print('Retrieved metadata table:',item['name'],flush=True)
    status={'status':'completed','tables':outputs,'station_time_series_opened':False,'temperature_values_opened':False,'model_errors_opened':False,
            'limitations':p['requirements'],'rights_note':p['rights']}
    (OUT/'station_metadata_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);a=p.parse_args();freeze() if a.action=='freeze' else fetch()
