#!/usr/bin/env python3
"""Acquire two post-hoc NJDEP reference candidates without model scoring."""
from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026';URL='https://njdep.rutgers.edu/continuous/api/latest/download/csv//'

def main():
 plan=json.loads((OUT/'subdaily_extension_plan.json').read_text());dst=OUT/'subdaily_extension_acquisition.json'
 if plan['status']!='posthoc_two_additional_sites_before_download' or dst.exists():raise ValueError('extension plan required; existing result preserved')
 folder=PRIVATE/'station_year_csv';folder.mkdir(parents=True,exist_ok=True,mode=0o700);count=0
 for site in plan['stations']:
  if not site.isalnum():raise ValueError('unsafe site ID')
  for year in plan['years']:
   target=folder/f'{site}_{year}.csv';part=folder/f'{site}_{year}.csv.part';receipt=folder/f'{site}_{year}.json'
   if target.exists():
    if not receipt.exists():raise ValueError('existing source has no matching receipt')
   else:
    if part.exists():raise RuntimeError('partial source file preserved')
    data={'station':site,'startDate':f'01/01/{year}','endDate':f'01/01/{year+1}','affiliation':'','project':'','watertype':'','stationType':'','county':'','municipality':'','huc14':'','params[]':'Temp'}
    try:
     with requests.post(URL,data=data,stream=True,timeout=(20,90)) as res:
      if res.status_code!=200 or 'csv' not in res.headers.get('Content-Type','').lower():raise RuntimeError('invalid provider response HTTP '+str(res.status_code))
      n=0
      with part.open('xb') as f:
       os.chmod(part,0o600)
       for block in res.iter_content(1024*1024):
        n+=len(block)
        if n>30_000_000:raise ValueError('station-year exceeds fixed size limit')
        f.write(block)
    except requests.RequestException as e:raise RuntimeError('provider request failed: '+type(e).__name__) from None
    if part.stat().st_size==0:raise ValueError('empty station-year file')
    part.rename(target);receipt.write_text(json.dumps({'site':site,'year':year,'bytes':target.stat().st_size,'parameter':'Temp','end_boundary':'not assumed'},indent=2)+'\n');receipt.chmod(0o600)
   count+=1;print('Acquired extension station-year',site,year,flush=True)
 result={'status':'posthoc_extension_files_acquired','stations':len(plan['stations']),'station_year_files':count,'acquired_utc':datetime.now(timezone.utc).isoformat(),
  'temperature_values_scored':False,'local_only':True,'limitation':'source retrieval alone does not establish observed 24-hour completeness, measurement quality, clocks, no estimates or independent watersheds'}
 dst.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
