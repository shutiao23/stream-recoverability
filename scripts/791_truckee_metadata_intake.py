#!/usr/bin/env python3
"""Retrieve public Truckee EML metadata through its DataONE coordinating node."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from urllib.parse import quote
import requests
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr'
IDENT='https://pasta.lternet.edu/package/metadata/eml/edi/2411/1';NODE='https://cn.dataone.org/cn/v2/object/'

def freeze():
    OUT.mkdir(parents=True,exist_ok=True);dest=OUT/'plan.json'
    if dest.exists():raise FileExistsError('Preserve Truckee metadata plan')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc exploration after California catalog discovery, prior Truckee catalog inspection, direct EDI 403, and finding the public DataONE coordinating node; before accessing station tables or observations',
        'source':'California Department of Water Resources Truckee River Continuous Water Quality, EDI package edi.2411.1; current public metadata through DataONE',
        'metadata_identifier':IDENT,'dataone_coordinating_node':NODE,
        'purpose':'Retrieve EML metadata only, inspect source attribution, station and instrument table descriptors, date/quality fields and declared access; assess prior river-network contact before deciding reference qualification.',
        'previous_contact':'Earlier project catalogs contain Truckee USGS station metadata, but this fact does not prove observations were processed or that the new DWR station locations are identical. Check exact identities, catchments and data exposure before any independent claim.',
        'staging':'No water measurements or prediction errors are requested. Station files, years and quality criteria require a separately recorded plan after metadata inspection.',
        'limitations':'Public EML access is not proof of four complete quality-qualified years, timestamps, sensor independence or climate independence; provider and package licenses may differ and must be reconciled.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded Truckee metadata-only intake')

def fetch():
    p=json.loads((OUT/'plan.json').read_text());target=OUT/'metadata.xml'
    if target.exists():raise FileExistsError('Preserve first metadata response')
    r=requests.get(NODE+quote(IDENT,safe=''),timeout=40,headers={'User-Agent':'stream-temperature reference qualification/1.0'});r.raise_for_status()
    root=ET.fromstring(r.content)
    if root.attrib.get('packageId')!='edi.2411.1':raise ValueError('Unexpected EML package')
    target.write_bytes(r.content)
    entities=[]
    for x in root.iter():
        if x.tag.split('}')[-1]!='dataTable':continue
        info={'entity_name':None,'object_name':None,'urls':[],'attribute_names':[]}
        for el in x.iter():
            tag=el.tag.split('}')[-1]
            if tag=='entityName' and info['entity_name'] is None:info['entity_name']=el.text
            elif tag=='objectName' and info['object_name'] is None:info['object_name']=el.text
            elif tag=='url' and el.text:info['urls'].append(el.text.strip())
            elif tag=='attributeName' and el.text:info['attribute_names'].append(el.text.strip())
        entities.append(info)
    if len(entities)<12:raise ValueError('Metadata lacks expected tables')
    (OUT/'entity_metadata.json').write_text(json.dumps(entities,indent=2)+'\n')
    summary={'status':'metadata_acquired','http_status':r.status_code,'bytes':len(r.content),'data_tables':len(entities),'station_data_opened':False,'temperature_values_opened':False,'model_errors_opened':False,'limitations':p['limitations']}
    (OUT/'metadata_status.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);a=p.parse_args();freeze() if a.action=='freeze' else fetch()
