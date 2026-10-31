#!/usr/bin/env python3
"""Retrieve candidate README and USGS site metadata, without sensor tables."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SITE='https://waterservices.usgs.gov/nwis/site/'

def freeze():
    target=OUT/'support_metadata_plan.json'
    if target.exists():raise FileExistsError('Preserve support metadata plan')
    status=json.loads((OUT/'roster_status.json').read_text());roster=PRIVATE/'roster.csv'
    if status['status']!='metadata_screened':raise ValueError('Candidate roster changed')
    f=pd.read_csv(roster,dtype={'resource_id':str,'gage_ids':str});f=f[f.metadata_candidate].sort_values('resource_id')
    if len(f)!=status['metadata_candidates']:raise ValueError('Candidate count differs')
    support=[]
    for r in f.itertuples(index=False):
        info=json.loads((PRIVATE/f'metadata_{r.resource_id}.json').read_text());readmes=[x for x in info['files'] if x['file_name']=='README.md']
        if len(readmes)!=1:raise ValueError('Ambiguous resource README')
        u=str(readmes[0]['url']);u='https://'+u[len('http://'):] if u.startswith('http://www.hydroshare.org/') else u
        if not u.startswith('https://www.hydroshare.org/resource/'):raise ValueError('Unexpected README host')
        support.append({'resource_id':r.resource_id,'readme_url':u,'gage_ids':str(r.gage_ids).split(';')})
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after collection metadata and preliminary prior-ID probe, before reading any candidate sensor-file contents or prediction errors',
          'cohort':'All 10 metadata candidates; request only their small README files and public USGS metadata for all referenced gauge IDs.',
          'requests':support,'interpretation':'README content can contain examples but is not a quality guarantee. USGS coordinates or HUC labels are not proof of same monitoring sensor or independent watershed; unresolved flags are retained.',
          'license':'Authors specify CC BY 4.0 and request courtesy notification of derivative work. No notification or external message is sent by this local metadata check.'}
    target.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded README and gauge-metadata intake')

def one(item):
    r=requests.get(item['readme_url'],timeout=25,headers={'User-Agent':'stream-temperature reference qualification/1.0'});r.raise_for_status()
    if len(r.content)>1024*1024:raise ValueError('README unexpectedly large')
    text=r.content.decode('utf-8-sig');dest=PRIVATE/f"readme_{item['resource_id']}.txt"
    if dest.exists():raise FileExistsError('Preserve previously saved README')
    dest.write_text(text);dest.chmod(0o600)
    return {'resource_id':item['resource_id'],'status':'completed','bytes':len(r.content),}

def fetch(workers):
    plan=json.loads((OUT/'support_metadata_plan.json').read_text())
    if workers<1 or workers>3:raise ValueError('Use 1–3 workers')
    entries=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one,x):x['resource_id'] for x in plan['requests']}
        for future in as_completed(futures):
            rid=futures[future]
            try:r=future.result()
            except Exception as e:r={'resource_id':rid,'status':'unknown','error_type':type(e).__name__}
            entries.append(r);print('README metadata',len(entries),'/',len(futures),r['status'],flush=True)
    ids=sorted({x for r in plan['requests'] for x in r['gage_ids']});site_status={'status':'unknown','ids_requested':len(ids)}
    try:
        r=requests.get(SITE,params={'format':'rdb','sites':','.join(ids),'siteOutput':'expanded'},timeout=30,
                       headers={'User-Agent':'stream-temperature reference qualification/1.0'});site_status['http_status']=r.status_code
        if r.status_code==200:
            lines=[x for x in r.text.splitlines() if x and not x.startswith('#')]
            if len(lines)<2 or not {'site_no','agency_cd'}.issubset(lines[0].split('\t')):raise ValueError('Unexpected USGS site response')
            frame=pd.read_csv(io.StringIO('\n'.join(lines)),sep='\t',skiprows=[1],dtype=str)
            if not set(frame.site_no).issubset(set(ids)) or not frame.agency_cd.eq('USGS').all() or frame.site_no.duplicated().any():raise ValueError('Unexpected USGS site IDs')
            dest=PRIVATE/'usgs_gage_metadata.rdb';dest.write_bytes(r.content);dest.chmod(0o600)
            site_status.update(status='completed',ids_returned=len(frame),)
    except (requests.RequestException,ValueError,KeyError,pd.errors.ParserError) as e:site_status['error_type']=type(e).__name__
    receipt=PRIVATE/'support_metadata_receipt.json';receipt.write_text(json.dumps({'readmes':sorted(entries,key=lambda x:x['resource_id']),'usgs_site_metadata':site_status},indent=2)+'\n');receipt.chmod(0o600)
    result={'status':'completed' if all(x['status']=='completed' for x in entries) and site_status['status']=='completed' else 'partial_unknown',
            'candidate_resources':len(entries),'readmes_available':sum(x['status']=='completed' for x in entries),
            'usgs_gage_ids_requested':len(ids),'usgs_gage_ids_returned':site_status.get('ids_returned',0),
            'temperature_files_opened':False,'model_errors_opened':False,'limitations':plan['interpretation']}
    (OUT/'support_metadata_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);p.add_argument('--workers',type=int,default=2);a=p.parse_args();freeze() if a.action=='freeze' else fetch(a.workers)
