#!/usr/bin/env python3
"""Explore year-boundary count semantics and a second metadata-selected site."""
import json
from datetime import datetime,timezone
from pathlib import Path
import requests
import wrr_tr_common as T
ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata'


def main():
 p=json.loads((OUT/'count_semantics_plan.json').read_text());dst=OUT/'count_semantics_status.json'
 if p['status']!='posthoc_two_station_count_semantics_probe' or dst.exists():raise ValueError('fixed plan required; existing results preserved')
 mod=T.load_script('njdep_count_semantics',ROOT/'scripts/634_njdep_count_probe.py');session=requests.Session();boundaries=[]
 for year in p['boundary_comparison_years']:
  a=mod.get_count(session,p['primary_station'],f'01/01/{year}',f'12/31/{year}')
  b=mod.get_count(session,p['primary_station'],f'01/01/{year}',f'01/01/{year+1}')
  boundaries.append({'year':year,'end_december_31':a,'end_next_january_1':b});print('boundary',year,a,b,flush=True)
 station=p['secondary_station'];control=mod.get_count(session,station);rows=[]
 for year in p['secondary_years']:
  row={'year':year}|mod.get_count(session,station,f'01/01/{year}',f'01/01/{year+1}');rows.append(row);print('secondary',year,row['status'],row['count'],flush=True)
 status={'status':'posthoc_count_semantics_completed','completed_utc':datetime.now(timezone.utc).isoformat(),
   'primary_station':p['primary_station'],'boundary_comparisons':boundaries,'secondary_station':station,'secondary_control':control,'secondary_year_counts':rows,
   'no_temperature_values_requested':True,'no_predictions_scored':True,
   'limitations':'end-date convention is inferred only from returned record counts; multiple data parameters, duplicates, estimated values, missing hours, incomplete QA and watershed overlap remain unresolved'}
 dst.write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()
