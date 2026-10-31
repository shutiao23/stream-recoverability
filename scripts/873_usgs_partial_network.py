#!/usr/bin/env python3
"""Check source-network contacts for four already opened USGS sites."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import requests
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.data.nldi_connectivity import parse_nldi_nwissite_ids

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usgs_partial_daily';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';CACHE=PRIVATE/'nldi'
URL='https://api.water.usgs.gov/nldi/linked-data/nwissite'

def freeze():
    h=T.load_script('usgs_partial_network_hash',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');path=OUT/'network_plan.json'
    if path.exists():raise FileExistsError('Preserve network plan')
    s=json.loads((OUT/'continuous_metadata_status.json').read_text());ids=json.loads((PRIVATE/'continuous_candidate_ids.json').read_text())
    if s['status']!='completed_metadata_only':raise ValueError('Continuous metadata unavailable')
    loader=T.load_script('usgs_partial_network_prior',ROOT/'scripts/820_usace_reference_roster.py');prior,source=loader.ids()
    all_open=set(pd.read_csv(ROOT/'results/additional_usgs_observed/cohort_metadata.csv',dtype={'station_id':str}).station_id)
    CACHE.mkdir(parents=True,exist_ok=True,mode=0o700);roster=CACHE/'network_ids.json'
    roster.write_text(json.dumps({'candidates':ids,'source':sorted(source),'other_named_prior':sorted(prior-all_open)},indent=2)+'\n');roster.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc metadata-only network check after these ten stations and daily outcomes were already opened; before continuous target values or model predictions',
       'sites':'All four daily-qualified sites; each was previously opened for observation-only evidence, so none is blind. The other-prior list removes the ten already opened cohort stations, while candidate-to-candidate connections are separately counted.',
       'navigation':'Query NLDI upstream with tributaries and downstream with diversions, bounded to 200 km. Compare with named source-panel USGS identifiers, other previously named stations and the four targets.',
       'limitations':'NLDI indexed catchments may include off-flowpath sites; the distance is bounded; a no-hit result or missing source identifiers does not establish independent watersheds or climate. Exact source contact and prior observation-only use are distinct.',
       'candidate_count':len(ids),'source_documentation':'https://api.water.usgs.gov/docs/nldi/navigation/'}
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen four-site source-network screen')

def run():
    h=T.load_script('usgs_partial_network_hash2',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');p=json.loads((OUT/'network_plan.json').read_text())
    sets=json.loads((CACHE/'network_ids.json').read_text());source=set(sets['source']);prior=set(sets['other_named_prior']);candidate=set(sets['candidates']);receipts=[];rows=[]
    for site in sets['candidates']:
        reached=set();complete=True
        for mode in ['UT','DD']:
            f=CACHE/f'{site}_{mode}.json'
            try:
                if f.exists():raise FileExistsError('Preserve existing network response')
                r=requests.get(f'{URL}/USGS-{site}/navigation/{mode}/nwissite',params={'f':'json','distance':200,'excludeGeometry':'true'},timeout=25,headers={'User-Agent':'stream-temperature reference network screening/1.0'})
                item={'site':site,'mode':mode,'http_status':r.status_code,'status':'unknown'}
                if r.status_code==200:
                    doc=r.json()
                    if not isinstance(doc.get('features'),list) or any(x.get('rel')=='next' for x in doc.get('links',[])):raise ValueError('Unexpected network response')
                    f.write_text(json.dumps(doc,indent=2)+'\n');f.chmod(0o600);reached.update(parse_nldi_nwissite_ids(doc));item.update(status='completed',)
                else:complete=False
                receipts.append(item)
                if r.status_code in (401,403,429,503):
                    complete=False;print('Network service requested stop',r.status_code,flush=True);break
            except (requests.RequestException,ValueError,KeyError) as e:
                complete=False;receipts.append({'site':site,'mode':mode,'status':'unknown','error_type':type(e).__name__})
            time.sleep(1)
        reached.discard(site);rows.append({'station_id':site,'both_directions_returned':complete,'exact_source_panel_id':site in source,
          'source_network_hits':len(reached&source),'other_prior_network_hits':len(reached&prior),'other_candidate_network_hits':len(reached&candidate),
          'source_hit_ids':';'.join(sorted(reached&source)),'other_prior_hit_ids':';'.join(sorted(reached&prior)),'candidate_hit_ids':';'.join(sorted(reached&candidate))})
        print('Network checked',len(rows),'of',len(sets['candidates']),flush=True)
        if receipts[-1].get('http_status') in (401,403,429,503):break
    complete_sites={r['station_id'] for r in rows};rows += [{'station_id':site,'both_directions_returned':False,'exact_source_panel_id':site in source,'source_network_hits':None,'other_prior_network_hits':None,'other_candidate_network_hits':None} for site in sets['candidates'] if site not in complete_sites]
    data=pd.DataFrame(rows);f=CACHE/'site_summary.csv';data.to_csv(f,index=False);f.chmod(0o600);receipt=CACHE/'receipt.json';receipt.write_text(json.dumps(receipts,indent=2)+'\n');receipt.chmod(0o600)
    result={'status':'completed' if data.both_directions_returned.all() else 'partial_unknown','sites':len(data),'sites_both_directions':int(data.both_directions_returned.sum()),
      'sites_exact_source_panel':int(data.exact_source_panel_id.sum()),'sites_with_source_network_hits':int(data.source_network_hits.fillna(0).gt(0).sum()),
      'sites_with_other_prior_network_hits':int(data.other_prior_network_hits.fillna(0).gt(0).sum()),'sites_with_other_candidate_hits':int(data.other_candidate_network_hits.fillna(0).gt(0).sum()),
      'limitations':p['limitations']}
    (OUT/'network_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
