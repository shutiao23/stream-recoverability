#!/usr/bin/env python3
"""Inventory all public USACE/UNM reservoir-network reference metadata."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import bs4
import pandas as pd
import requests
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'
COLLECTION='https://www.hydroshare.org/resource/430ee557554948b5811830c1e2ec41aa/'

def freeze():
    OUT.mkdir(parents=True,exist_ok=True);dest=OUT/'metadata_plan.json'
    if dest.exists():raise FileExistsError('Preserve network metadata plan')
    r=requests.get(COLLECTION,timeout=25,headers={'User-Agent':'stream-temperature reference qualification/1.0'});r.raise_for_status()
    soup=bs4.BeautifulSoup(r.content,'html.parser');resources={}
    for a in soup.find_all('a',href=True):
        m=re.fullmatch(r'/resource/([0-9a-f]{32})/?',a['href']);title=' '.join(a.get_text(' ',strip=True).split())
        if m and 'water quality data' in title.lower():resources[m.group(1)]=title
    if len(resources)!=11:raise ValueError('Unexpected collection membership')
    html=OUT/'collection_metadata.html';html.write_bytes(r.content)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc exploratory intake after previous reference attempts and public collection descriptions were inspected; before opening any selected temperature values or model errors',
          'collection':COLLECTION,'resource_count':len(resources),'resources':[{'id':k,'title':resources[k]} for k in sorted(resources)],
          'retrieval':'For every listed resource, request its public metadata RDF and file-name/size inventory only. Do not download level-0/level-1 temperature files at this stage.',
          'early_probe':'An endpoint-discovery request inadvertently retrieved one complete resource ZIP into memory; no ZIP members or temperature values were opened, and the response was not retained.',
          'selection':'Classify each resource by public date envelope, declared level-1 QA/QC file names, referenced USGS IDs, geographic position and named prior-contact inventories. Retain unknowns. Freeze a separate data-access and qualification plan before reading station files.',
          'license':'Resource metadata says CC BY 4.0 with required attribution and requests courtesy notification of derivative work. No notification or external message has been sent.',
          'limitations':'Posthoc and not random. Reservoir influence, monitoring-site linkage, source-model overlap, quality corrections, timezone and completeness require explicit verification; archive pages do not establish independent climates or reference accuracy.',
          }
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded all 11 resource metadata-only intake')

def one(item):
    rid=item['id'];headers={'User-Agent':'stream-temperature reference qualification/1.0'}
    xml=requests.get(f'https://www.hydroshare.org/resource/{rid}/data/resourcemetadata.xml',timeout=30,headers=headers);xml.raise_for_status()
    listing=requests.get(f'https://www.hydroshare.org/hsapi/resource/{rid}/files/',timeout=30,headers=headers);listing.raise_for_status();j=listing.json()
    if j.get('next') is not None or not isinstance(j.get('results'),list):raise ValueError('Resource listing paginated or invalid')
    root=ET.fromstring(xml.content);abstract=[];coverage=[];titles=[];licenses=[]
    for el in root.iter():
        tag=el.tag.rsplit('}',1)[-1];text=' '.join(''.join(el.itertext()).split())
        if tag=='description' and text:abstract.append(text)
        elif tag=='coverage' and text:coverage.append(text)
        elif tag=='title' and text:titles.append(text)
        elif tag=='rights' and text:licenses.append(text)
    scope=' '.join(abstract+coverage);ids=sorted(set(re.findall(r'\b\d{8,15}\b',scope)))
    files=[{'file_name':x.get('file_name'),'size':x.get('size'),'content_type':x.get('content_type'),'url':x.get('url')} for x in j['results']]
    if not any('level1' in str(x['file_name']).lower() for x in files):raise ValueError('No declared QA/QC filename')
    return {'resource_id':rid,'title':item['title'],'metadata_titles':titles,'coverage':coverage,'descriptions':abstract,
            'numeric_ids_found_in_metadata':ids,'rights_text':licenses,'files':files,
            }

def fetch(workers):
    plan=json.loads((OUT/'metadata_plan.json').read_text())
    if workers<1 or workers>3:raise ValueError('Use 1–3 metadata workers')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);done=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one,x):x['id'] for x in plan['resources']}
        for future in as_completed(futures):
            rid=futures[future]
            try:
                record=future.result();dest=PRIVATE/f'metadata_{rid}.json'
                if dest.exists():raise FileExistsError('Preserve saved metadata')
                dest.write_text(json.dumps(record,indent=2)+'\n');dest.chmod(0o600)
                entry={'id':rid,'status':'completed',}
            except Exception as e:entry={'id':rid,'status':'unknown','error_type':type(e).__name__}
            done.append(entry);print('Resource metadata',len(done),'/',len(futures),entry['status'],flush=True)
    receipt=PRIVATE/'metadata_receipt.json';receipt.write_text(json.dumps(sorted(done,key=lambda x:x['id']),indent=2)+'\n');receipt.chmod(0o600)
    result={'status':'completed' if len(done)==11 and all(x['status']=='completed' for x in done) else 'partial_unknown',
            'resources_requested':11,'resources_completed':sum(x['status']=='completed' for x in done),
            'temperature_members_opened':False,'prediction_errors_opened':False,'limitations':plan['limitations']}
    (OUT/'metadata_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);p.add_argument('--workers',type=int,default=2);a=p.parse_args();freeze() if a.action=='freeze' else fetch(a.workers)
