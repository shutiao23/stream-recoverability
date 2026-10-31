#!/usr/bin/env python3
"""Acquire the published DataStream CSV locally after recording terms and plan.

Source data is intentionally kept in the private directory pending clarification
of redistribution language. The download URL is short-lived and is never logged.
No source rows are displayed or scored by this acquisition step.
"""
from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata'
PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026'
DATASET='09ab9bf0-789b-4487-918e-b5c8cf258225';VERSION='1.0.0'
EXPECTED='125a39196c7e1401ad9f5197431e24748c65556d0a14be03771737ef7bff1cf9'
MAX_BYTES=100_000_000

def main():
 plan=json.loads((OUT/'plan.json').read_text())
 if plan['dataset_doi']!='10.25976/sz2k-b624' or plan['status']!='metadata_only_plan_no_data_downloaded':raise ValueError('pre-download plan changed')
 PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);PRIVATE.chmod(0o700)
 data=PRIVATE/'rivtemp_mffp_v1.csv';part=PRIVATE/'rivtemp_mffp_v1.csv.part'
 if data.exists():
  pass
 else:
  if part.exists():raise ValueError('incomplete previous download preserved; resolve before retrying')
  endpoint=f'https://datastream.org/api/dataset/{DATASET}/{VERSION}/download'
  try:r=requests.get(endpoint,params={'name':'doi.org_10.25976_sz2k-b624#1.0.0'},timeout=45)
  except requests.RequestException as e:raise RuntimeError('DataStream download endpoint unavailable: '+type(e).__name__) from None
  if r.status_code!=200:raise RuntimeError('DataStream download endpoint returned HTTP '+str(r.status_code))
  signed=r.json().get('data',{}).get('url')
  if not isinstance(signed,str) or not signed.startswith('https://'):raise ValueError('download endpoint did not return an HTTPS file')
  count=0
  try:
   with requests.get(signed,stream=True,timeout=(20,120)) as res:
    if res.status_code!=200:raise RuntimeError('DataStream file host returned HTTP '+str(res.status_code))
    with part.open('xb') as f:
     os.chmod(part,0o600)
     for chunk in res.iter_content(1024*1024):
      count+=len(chunk)
      if count>MAX_BYTES:raise ValueError('source exceeds frozen size limit; partial preserved')
      f.write(chunk)
  except requests.RequestException as e:raise RuntimeError('DataStream file download failed: '+type(e).__name__) from None
  part.rename(data)
 status={'status':'downloaded','source_dataset':'RivTemp--MFFP_QC','doi':'10.25976/sz2k-b624','data_version':VERSION,
  'acquired_utc':datetime.now(timezone.utc).isoformat(),'bytes':data.stat().st_size,
  'catalog':'https://datastream.org/en-ca/dataset/'+DATASET,'terms':'https://datastream.org/en-ca/terms',
  'access':'public dataset download through the provider endpoint; website states use is subject to terms and dataset disclaimer',
  'local_storage':'private/wrr_rivtemp_reference_20261026/rivtemp_mffp_v1.csv',
  'redistribution':'not included in candidate package while ODC-BY and database-transfer disclaimer are clarified',
  'scope':'file retrieval only; no rows or model outcomes inspected'}
 (OUT/'acquisition.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()
