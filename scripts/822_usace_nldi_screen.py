#!/usr/bin/env python3
"""Metadata-only bounded network screening around candidate USGS gauge proxies."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import threading
import time
import pandas as pd
import requests
import wrr_tr_common as T
from stream_recoverability.data.nldi_connectivity import parse_nldi_nwissite_ids

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';CACHE=PRIVATE/'nldi_metadata'
URL='https://api.water.usgs.gov/nldi/linked-data/nwissite';LOCK=threading.Lock();NEXT=0.;STOP=threading.Event()

def freeze():
    target=OUT/'network_plan.json'
    if target.exists():raise FileExistsError('Preserve NLDI plan')
    roster=PRIVATE/'roster.csv';status=json.loads((OUT/'roster_status.json').read_text());support=json.loads((OUT/'support_metadata_status.json').read_text())
    if support['status']!='completed':raise ValueError('Candidate or metadata support incomplete')
    f=pd.read_csv(roster,dtype={'resource_id':str,'gage_ids':str});f=f[f.metadata_candidate]
    ids=sorted({s for v in f.gage_ids for s in str(v).split(';') if s})
    prior,source=T.load_script('usace_network_prior',ROOT/'scripts/820_usace_reference_roster.py').ids()
    CACHE.mkdir(parents=True,exist_ok=True,mode=0o700);path=CACHE/'prior_ids.json';path.write_text(json.dumps({'prior':sorted(prior),'source':sorted(source),'candidate':ids},indent=2)+'\n');path.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc metadata-only network screen, before opening candidate station temperature files or model errors',
          'cohort':'All USGS gages referenced by the 10 metadata candidates, including both upstream gages of the confluence site.',
          'navigation':'For each referenced USGS gage query USGS NLDI upstream with tributaries (UT) and downstream with diversions (DD), at 200 km; compare returned indexed USGS site identifiers to named prior IDs and candidate gages.',
          'limitations':'The monitoring site may be offset from its referenced USGS gage. NLDI indexes catchments and can return off-flowpath sites; 200 km is bounded, not proof of disconnection beyond the search. USGS source records or coordinates may be incomplete; neither a clean result nor a missing response establishes independent climate or no prior exposure.',
          'site_ids':len(ids),'requests':2*len(ids),'source_documentation':'https://api.water.usgs.gov/docs/nldi/navigation/'}
    target.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded bounded NLDI candidate network screen')

def request(site,mode):
    global NEXT
    if STOP.is_set():return {'site':site,'mode':mode,'status':'unknown_service_stop'}
    with LOCK:
        delay=max(0.,NEXT-time.monotonic());NEXT=max(NEXT,time.monotonic())+1.
    if delay:time.sleep(delay)
    if STOP.is_set():return {'site':site,'mode':mode,'status':'unknown_service_stop'}
    path=CACHE/f'{site}_{mode}.json'
    if path.exists():
        response=json.loads(path.read_text());return {'site':site,'mode':mode,'status':'completed','returned_ids':len(parse_nldi_nwissite_ids(response)),'cached':True}
    try:
        r=requests.get(f'{URL}/USGS-{site}/navigation/{mode}/nwissite',params={'f':'json','distance':200,'excludeGeometry':'true'},timeout=25,
                       headers={'User-Agent':'stream-temperature reference network screening/1.0'})
        if r.status_code in (401,403,429,503):STOP.set()
        if r.status_code!=200:return {'site':site,'mode':mode,'status':'unknown_http','http_status':r.status_code}
        doc=r.json()
        if not isinstance(doc,dict) or not isinstance(doc.get('features'),list) or any(x.get('rel')=='next' for x in doc.get('links',[])):
            raise ValueError('Unexpected or paginated NLDI response')
        path.write_text(json.dumps(doc,indent=2)+'\n');path.chmod(0o600)
        return {'site':site,'mode':mode,'status':'completed','returned_ids':len(parse_nldi_nwissite_ids(doc)),'cached':False}
    except (requests.RequestException,ValueError,KeyError) as e:return {'site':site,'mode':mode,'status':'unknown_exception','error_type':type(e).__name__}

def run(workers):
    plan=json.loads((OUT/'network_plan.json').read_text())
    if workers<1 or workers>2:raise ValueError('Use 1–2 paced network workers')
    ids=json.loads((CACHE/'prior_ids.json').read_text());alljobs=[(s,m) for s in ids['candidate'] for m in ('UT','DD')];results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(request,s,m):(s,m) for s,m in alljobs}
        for future in as_completed(futures):
            item=future.result();results.append(item);print('NLDI requests',len(results),'/',len(alljobs),item['status'],flush=True)
    receipt=CACHE/'receipt.json';receipt.write_text(json.dumps(sorted(results,key=lambda x:(x['site'],x['mode'])),indent=2)+'\n');receipt.chmod(0o600)
    prior=set(ids['prior']);source=set(ids['source']);candidates=set(ids['candidate']);rows=[]
    for site in ids['candidate']:
        items=[x for x in results if x['site']==site];complete=len(items)==2 and all(x['status']=='completed' for x in items)
        reached=set()
        for x in items:
            if x['status']=='completed':reached.update(parse_nldi_nwissite_ids(json.loads((CACHE/f"{site}_{x['mode']}.json").read_text())))
        reached.discard(site)
        rows.append({'site':site,'both_directions_returned':complete,'prior_gage_hits':len(reached&prior),
                     'source_panel_gage_hits':len(reached&source),'other_candidate_gage_hits':len(reached&candidates),
                     'prior_hit_ids':';'.join(sorted(reached&prior)),'candidate_hit_ids':';'.join(sorted(reached&candidates))})
    data=pd.DataFrame(rows);dest=CACHE/'gage_summary.csv';data.to_csv(dest,index=False);dest.chmod(0o600)
    result={'status':'completed' if all(x['status']=='completed' for x in results) else 'partial_unknown',
        'requested':len(alljobs),'completed':sum(x['status']=='completed' for x in results),'gages':len(ids['candidate']),
        'gages_both_directions':int(data.both_directions_returned.sum()),'gages_with_prior_hits':int(data.prior_gage_hits.gt(0).sum()),
        'gages_with_source_panel_hits':int(data.source_panel_gage_hits.gt(0).sum()),'gages_with_other_candidate_hits':int(data.other_candidate_gage_hits.gt(0).sum()),
        'temperature_values_opened':False,'prediction_errors_opened':False,'limitations':plan['limitations']}
    (OUT/'network_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);p.add_argument('--workers',type=int,default=2);a=p.parse_args();freeze() if a.action=='freeze' else run(a.workers)
