#!/usr/bin/env python3
"""Download two fixed RivTemp partner files and screen metadata-only year bounds."""
from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata';PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026';PLAN=OUT/'partner_screen_plan.json'
COLS=['MonitoringLocationID','MonitoringLocationName','MonitoringLocationLatitude','MonitoringLocationLongitude','MonitoringLocationHorizontalCoordinateReferenceSystem','MonitoringLocationHorizontalAccuracyMeasure','MonitoringLocationHorizontalAccuracyUnit','MonitoringLocationType']

def acquire(ds):
 path=PRIVATE/(ds['id']+'_'+ds['version']+'.csv');part=path.with_suffix('.csv.part')
 if path.exists():
  return path
 if part.exists():raise ValueError('partial partner file preserved; inspect before retrying')
 endpoint=f"https://datastream.org/api/dataset/{ds['id']}/{ds['version']}/download"
 try:r=requests.get(endpoint,params={'name':'doi.org_'+ds['doi'].replace('/','_')+'#'+ds['version']},timeout=45)
 except requests.RequestException as e:raise RuntimeError('partner catalog unavailable: '+type(e).__name__) from None
 if r.status_code!=200:raise RuntimeError('partner catalog HTTP '+str(r.status_code))
 url=r.json().get('data',{}).get('url');n=0
 if not isinstance(url,str) or not url.startswith('https://'):raise ValueError('partner endpoint did not return HTTPS file')
 try:
  with requests.get(url,stream=True,timeout=(20,120)) as res:
   if res.status_code!=200:raise RuntimeError('partner file HTTP '+str(res.status_code))
   with part.open('xb') as f:
    os.chmod(part,0o600)
    for b in res.iter_content(1024*1024):
     n+=len(b)
     if n>100_000_000:raise ValueError('partner data exceeds frozen size bound')
     f.write(b)
 except requests.RequestException as e:raise RuntimeError('partner file unavailable: '+type(e).__name__) from None
 part.rename(path);return path

def freeze(ds,path):
 target=PRIVATE/(ds['id']+'_all_locations.csv')
 if target.exists():raise ValueError('existing partner roster preserved')
 parts=[];n=0
 for chunk in pd.read_csv(path,usecols=COLS,dtype=str,keep_default_na=False,chunksize=100_000):n+=len(chunk);parts.append(chunk.drop_duplicates())
 f=pd.concat(parts,ignore_index=True).drop_duplicates().sort_values(COLS,kind='stable')
 if f.MonitoringLocationID.eq('').any():raise ValueError('partner source has missing ID')
 if f.MonitoringLocationID.duplicated().any():raise ValueError('partner station has conflicting metadata; preserve and resolve before date screening')
 f.to_csv(target,index=False);target.chmod(0o600)
 return f,{'name':ds['name'],'bytes':path.stat().st_size,'source_metadata_rows':n,'location_ids':len(f),'all_types':f.MonitoringLocationType.value_counts().to_dict()}

def main():
 p=json.loads(PLAN.read_text())
 if p['status']!='posthoc_partner_selection_before_partner_data_access' or len(p['datasets'])!=2:raise ValueError('partner plan not fixed')
 PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
 if (OUT/'partner_roster_freeze.json').exists() or (OUT/'partner_date_upper_bound.json').exists():raise RuntimeError('existing partner screen preserved')
 sources=[acquire(d) for d in p['datasets']]
 rosters=[];acquisition=[]
 for ds,path in zip(p['datasets'],sources):
  f,record=freeze(ds,path);rosters.append(f);acquisition.append(record)
 old=pd.read_csv(PRIVATE/'all_locations_before_qualification.csv',dtype=str,keep_default_na=False)
 overlap=[]
 for ds,frame in zip(p['datasets'],rosters):
  for label,other in [('MFFP',old),('other_partner',rosters[1] if ds is p['datasets'][0] else rosters[0])]:
   pairs=frame[['MonitoringLocationLatitude','MonitoringLocationLongitude']].merge(other[['MonitoringLocationLatitude','MonitoringLocationLongitude']].drop_duplicates(),on=['MonitoringLocationLatitude','MonitoringLocationLongitude'])
   overlap.append({'dataset':ds['name'],'compared_to':label,'exact_id_overlap':len(set(frame.MonitoringLocationID)&set(other.MonitoringLocationID)),'metadata_rows_with_same_coordinates':len(pairs)})
 frozen={'status':'all_partner_rosters_frozen_before_date_screen','created_utc':datetime.now(timezone.utc).isoformat(),'datasets':acquisition,'cross_dataset_overlap':overlap,
   'columns_read':COLS,'target_values_and_dates_read':False,'limitation':'exact IDs and coordinates do not establish matching or independent watersheds; initial selection is post-hoc'}
 (OUT/'partner_roster_freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
 upper=T.load_script('rivtemp_partner_upper_bound',ROOT/'scripts/628_rivtemp_metadata_year_upper_bound.py');results=[]
 for ds,path,roster in zip(p['datasets'],sources,rosters):
  dates=pd.read_csv(path,usecols=['MonitoringLocationID','ActivityStartDate'],dtype=str,keep_default_na=False)
  for scope,years in [('fixed_forward_2010_2020',list(range(2010,2021))),('published_period',list(range(ds['metadata_years'][0],ds['metadata_years'][1]+1)))]:
   table,sites=upper.upper_bound(dates,roster,years);local=PRIVATE/(ds['id']+'_'+scope+'_possible_years.csv');table.to_csv(local,index=False);local.chmod(0o600)
   selected=sites.loc[sites.at_least_four_possible_years]
   results.append({'dataset':ds['name'],'scope':scope,'station_ids':len(roster),'station_years_possible_by_label':int(table.could_be_complete_by_label.sum()),'station_ids_four_possible_years':len(selected),
      'distinct_coordinate_pairs_four_possible_years':len(selected[['MonitoringLocationLatitude','MonitoringLocationLongitude']].drop_duplicates())})
 report={'status':'posthoc_partner_date_labels_only','datasets':results,'target_temperature_values_or_predictions_read':False,
   'limitation':'distinct date labels are only an optimistic availability upper bound; sample times, complete 24-hour days, estimated values, quality, hydrographic independence and cross-dataset duplication remain unresolved'}
 (OUT/'partner_date_upper_bound.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(frozen,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
