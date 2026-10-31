#!/usr/bin/env python3
"""Acquire frozen NJDEP station-years locally for reference qualification only."""
from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026'
URL='https://njdep.rutgers.edu/continuous/api/latest/download/csv//';MAX_BYTES=30_000_000

def main():
 planpath=OUT/'subdaily_qualification_plan.json';p=json.loads(planpath.read_text())
 if p['status']!='posthoc_two_site_qualification_plan_before_observation_download':raise ValueError('qualification plan missing')
 status=OUT/'subdaily_acquisition.json'
 if status.exists():raise RuntimeError('existing acquisition preserved')
 folder=PRIVATE/'station_year_csv';folder.mkdir(parents=True,exist_ok=True,mode=0o700);rows=[]
 for site in p['station_ids']:
  if not site.isalnum():raise ValueError('unsafe station identity')
  for year in p['years']:
   target=folder/f'{site}_{year}.csv';part=folder/f'{site}_{year}.csv.part';receipt=folder/f'{site}_{year}.json'
   if target.exists():
    if not receipt.exists():raise ValueError('existing local source has no matching receipt')
   else:
    if part.exists():raise RuntimeError('partial source file preserved for review')
    data={'station':site,'startDate':f'01/01/{year}','endDate':f'01/01/{year+1}','affiliation':'','project':'','watertype':'','stationType':'','county':'','municipality':'','huc14':'','params[]':'Temp'}
    try:
     with requests.post(URL,data=data,stream=True,timeout=(20,90)) as res:
      if res.status_code!=200:raise RuntimeError('provider CSV returned HTTP '+str(res.status_code))
      if 'csv' not in res.headers.get('Content-Type','').lower():raise ValueError('provider did not return CSV')
      n=0
      with part.open('xb') as f:
       os.chmod(part,0o600)
       for b in res.iter_content(1024*1024):
        n+=len(b)
        if n>MAX_BYTES:raise ValueError('station-year file exceeds fixed size limit')
        f.write(b)
    except requests.RequestException as e:raise RuntimeError('provider station-year download failed: '+type(e).__name__) from None
    if part.stat().st_size==0:raise ValueError('provider returned empty CSV')
    part.rename(target);record={'site':site,'year':year,'bytes':target.stat().st_size,'url':URL,'parameter':'Temp','date_start':f'01/01/{year}','date_end':f'01/01/{year+1}','end_boundary':'provider semantics not assumed'}
    receipt.write_text(json.dumps(record,indent=2)+'\n');receipt.chmod(0o600)
   rows.append({'site':site,'year':year,'bytes':target.stat().st_size,})
   print('Acquired station-year',site,year,flush=True)
 result={'status':'station_year_files_acquired','acquired_utc':datetime.now(timezone.utc).isoformat(),'stations':len(p['station_ids']),'station_year_files':len(rows),
   'provider_endpoint':URL,'parameter':'Temp','local_files':'private/wrr_njdep_reference_20261026/station_year_csv/',
   'water_temperature_values_scored':False,'quality_or_complete_years_established':False,
   'limitation':'post-hoc two-site selection; CSV acquisition does not establish unique complete days, physical time zone, nonestimated values, individual quality flags, sensor accuracy or independent watershed'}
 status.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
