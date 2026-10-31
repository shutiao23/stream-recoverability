#!/usr/bin/env python3
"""Check unresolved USGS donor identifiers against the public site service.

This verifies identifier existence only, not the provenance of cached
temperatures, provider permissions or data quality. No temperatures requested.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import re
import requests
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance/usgs_metadata'
URL='https://waterservices.usgs.gov/nwis/site/'

def freeze():
    dest=OUT/'donor_usgs_metadata_plan.json'
    if dest.exists():raise FileExistsError('Preserve existing metadata plan')
    audit=json.loads((OUT/'donor_provenance_status.json').read_text());ind=json.loads((OUT/'donor_provenance_independent_audit.json').read_text())
    if not audit['donor_visibility_counts_match_saved_cases'] or ind['status']!='passed':raise ValueError('Donor audit incomplete')
    jobs=T.load_script('metadata_donor_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')
    frame=pd.DataFrame(jobs);frame=frame[frame.provider.eq('usgs')]
    used=set()
    for split in ('leave_one_year_out','before_2010'):
        c=pd.read_parquet(ROOT/'private/wrr_open_source_sensitivity_20261026/candidate_cases'/split/'seed_00.parquet',
                          columns=['network_id','station_id','provider','policy_choice','eval_truth_h30'])
        c=c[c.provider.eq('usgs')&c.policy_choice.ne('unavailable')&c.eval_truth_h30.notna()]
        used.update(zip(c.network_id.astype(str),c.station_id.astype(str)))
    frame=frame[[ (str(n),str(s)) in used for n,s in zip(frame.network_id,frame.station_id) ]]
    st=pd.read_parquet(T.E1/'station_years.parquet',columns=['network_id','provider','station_id'])
    cov=pd.read_csv(T.COVERAGE,dtype=str,usecols=['network_id','provider','station_id'])
    keys=lambda d:set(zip(d.network_id.astype(str),d.provider.astype(str),d.station_id.astype(str)))
    known=keys(st)|keys(cov);old=set(pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype={'site_no':str}).site_no.astype(str));rows=[]
    for path,g in frame.groupby('input_path',sort=True):
        networks=g.network_id.unique()
        if len(networks)!=1:raise ValueError('Ambiguous USGS panel network')
        network=str(networks[0])
        with open(path,encoding='utf-8-sig',newline='') as f:header=next(csv.reader(f))
        for station in header[1:]:
            if (network,'usgs',station) not in known and station not in old:rows.append({'network_id':network,'station_id':station})
    result=pd.DataFrame(rows).drop_duplicates().sort_values(['network_id','station_id']).reset_index(drop=True)
    panel_total=int(pd.read_csv(OUT/'donor_provenance_panels.csv').set_index('provider').loc['usgs','outside_all_local_catalogs'])
    if len(result)!=panel_total:raise ValueError('Unresolved panel roster differs')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);path=PRIVATE/'unresolved_columns.csv';result.to_csv(path,index=False);path.chmod(0o600)
    identifiers=sorted(set(result.station_id.astype(str)));valid=[x for x in identifiers if re.fullmatch(r'\d{8,15}',x)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after the donor provenance audit; identifiers selected without prediction-error or site-service results',
          'selection':'All USGS-labeled panel donor columns not matched to any of the three local inventories, whether or not visible in a specific case.',
          'panel_columns':len(result),'unique_identifiers':len(identifiers),'valid_usgs_id_syntax':len(valid),
          'endpoint':URL,'metadata_fields':'public USGS site identifiers and station metadata only; no water temperatures',
          'interpretation':'A returned USGS site number verifies that the identifier appears in USGS metadata. It does not establish that local panel data came from the same source or have public redistribution rights; non-returned IDs remain unresolved.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps(plan,indent=2))

def execute():
    plan=json.loads((OUT/'donor_usgs_metadata_plan.json').read_text());roster=PRIVATE/'unresolved_columns.csv'
    ids=sorted(set(pd.read_csv(roster,dtype=str).station_id));ids=[x for x in ids if re.fullmatch(r'\d{8,15}',x)]
    results=[];batches=[]
    for number,start in enumerate(range(0,len(ids),40),1):
        chunk=ids[start:start+40];params={'format':'rdb','siteOutput':'basic','sites':','.join('USGS:'+x for x in chunk)}
        attempt={'batch':number,'requested_ids':len(chunk),'status':'unknown'}
        try:
            response=requests.get(URL,params=params,timeout=25,headers={'User-Agent':'Stream-temperature source provenance research/1.0'})
            attempt.update(http_status=response.status_code,bytes=len(response.content))
            if response.status_code==200:
                lines=[x for x in response.text.splitlines() if x and not x.startswith('#')]
                if len(lines)<2 or not {'agency_cd','site_no'}.issubset(lines[0].split('\t')):raise ValueError('Unexpected USGS response')
                table=pd.read_csv(io.StringIO('\n'.join(lines)),sep='\t',skiprows=[1],dtype=str)
                if not set(table.site_no).issubset(set(chunk)) or not table.agency_cd.eq('USGS').all():raise ValueError('Unexpected site identity')
                path=PRIVATE/f'batch_{number:02d}.rdb';path.write_bytes(response.content);path.chmod(0o600)
                results.extend(table.site_no.tolist());attempt.update(status='completed',returned_rows=len(table),)
        except (requests.RequestException,ValueError,pd.errors.ParserError) as exc:
            attempt['error_type']=type(exc).__name__
        batches.append(attempt);print('USGS metadata batch',number,attempt['status'],flush=True)
    returned=sorted(set(results));missing=sorted(set(ids)-set(returned))
    p=PRIVATE/'returned_ids.json';p.write_text(json.dumps(returned,indent=2)+'\n');p.chmod(0o600)
    out={'status':'completed' if all(b['status']=='completed' for b in batches) else 'partial_service_response',
         'planned_unique_identifiers':plan['unique_identifiers'],'valid_syntax_queried':len(ids),
         'returned_unique_identifiers':len(returned),'valid_syntax_not_returned':len(missing),
         'unqueried_nonstandard_identifiers':plan['unique_identifiers']-len(ids),'batches':batches,'limits':plan['interpretation']}
    (OUT/'donor_usgs_metadata_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args()
    if a.action=='freeze':freeze()
    else:execute()
