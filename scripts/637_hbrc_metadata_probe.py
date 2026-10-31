#!/usr/bin/env python3
"""Metadata-only reachability recheck for Hawke's Bay official data sources."""
from datetime import datetime,timezone
import json
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_hbrc_metadata'

def main():
 p=json.loads((OUT/'plan.json').read_text());target=OUT/'status.json'
 if p['status']!='metadata_endpoint_probe_after_initial_522' or target.exists():raise RuntimeError('fixed plan required and previous status preserved')
 try:
  response=requests.get(p['published_hilltop_endpoint'],params={'service':'Hilltop','request':'SiteList','Measurement':'Water Temperature'},timeout=30)
  hill={'http_status':response.status_code,'content_type':response.headers.get('Content-Type'),'response_bytes':len(response.content),}
 except requests.RequestException as e:hill={'http_status':None,'error_type':type(e).__name__}
 item_url='https://www.arcgis.com/sharing/rest/content/items/7815f0a28bb843d18ac91056dd7f9d80'
 try:
  r=requests.get(item_url,params={'f':'json'},timeout=20)
  if r.status_code==200:
   j=r.json();item={'http_status':200,'title':j.get('title'),'owner':j.get('owner'),'access':j.get('access'),'service_url':j.get('url'),'last_modified':j.get('modified')}
  else:item={'http_status':r.status_code}
 except (requests.RequestException,ValueError) as e:item={'http_status':None,'error_type':type(e).__name__}
 result={'status':'metadata_probe_completed','recorded_utc':datetime.now(timezone.utc).isoformat(),'hilltop_site_list':hill,'arcgis_item_metadata':item,
   'water_observations_requested':False,'reconstruction_scored':False,
   'interpretation':'a non-200 response establishes only that this request was unavailable at the time, not that the provider has no relevant stations or data; a successful SiteList would still be metadata only',
   'limitation':'the selected water-temperature name may not match all provider measurement names; river location, historical span, QA and availability remain unqualified'}
 target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
