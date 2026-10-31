#!/usr/bin/env python3
"""Count provider records for all post-hoc QA-span candidates, without values."""
from __future__ import annotations
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026'

def candidate_years(start,end):
 a=pd.to_datetime(start,format='%m/%d/%Y',errors='raise');b=pd.to_datetime(end,format='%m/%d/%Y',errors='raise')
 return [year for year in range(2010,2025) if a<=pd.Timestamp(year,1,1) and b>=pd.Timestamp(year,12,31)]

def work(row,folder,planhash):
 mod=T.load_script('njdep_count_worker',ROOT/'scripts/634_njdep_count_probe.py');site=row['station_id'];years=candidate_years(row['qa_start'],row['qa_end'])
 if len(years)<4:raise ValueError('frozen candidate does not satisfy QA envelope')
 dest=folder/(site+'.json')
 if dest.exists():
  x=json.loads(dest.read_text())
  if x['site']!=site or x['years']!=years:raise ValueError('existing candidate receipt differs')
  return x
 s=requests.Session();control=mod.get_count(s,site);values=[]
 for y in years:values.append({'year':y}|mod.get_count(s,site,f'01/01/{y}',f'01/01/{y+1}'))
 data={'site':site,'years':years,'control':control,'counts':values}
 dest.write_text(json.dumps(data,indent=2)+'\n');dest.chmod(0o600);return data

def main():
 planpath=OUT/'all_candidate_counts_plan.json';p=json.loads(planpath.read_text());src=PRIVATE/'all_water_types_span_candidates.csv'
 if p['status']!='posthoc_all_span_candidate_count_plan':raise ValueError('candidate plan or roster changed')
 status=OUT/'all_candidate_counts_status.json'
 if status.exists():raise RuntimeError('existing aggregate status preserved')
 data=pd.read_csv(src,dtype={'station_id':str,'huc14':str},keep_default_na=False)
 if len(data)!=26 or data.station_id.duplicated().any():raise ValueError('candidate scope or identity differs')
 folder=PRIVATE/'candidate_count_receipts';folder.mkdir(parents=True,exist_ok=True,mode=0o700);
 with ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda row:work(row,folder,planhash),data.to_dict('records')))
 rows=[]
 for x in results:
  r=x['counts'];ok=all(z['status']=='returned' for z in r);nonzero=sum(z['count']>0 for z in r if z['status']=='returned')
  rows.append({'site':x['site'],'candidate_years':len(r),'returned_years':sum(z['status']=='returned' for z in r),
      'nonzero_count_years':nonzero,'all_year_counts_returned':ok,'no_date_control_status':x['control']['status'],
      'no_date_control_count':x['control'].get('count')})
 table=pd.DataFrame(rows);table.to_csv(PRIVATE/'candidate_counts_summary.csv',index=False);(PRIVATE/'candidate_counts_summary.csv').chmod(0o600)
 state={'status':'posthoc_record_counts_not_reference_qualification','candidates':len(table),'queried_candidate_years':int(table.candidate_years.sum()),
   'returned_year_counts':int(table.returned_years.sum()),'candidates_all_counts_returned':int(table.all_year_counts_returned.sum()),
   'candidates_four_or_more_nonzero_count_years':int((table.all_year_counts_returned&table.nonzero_count_years.ge(4)).sum()),
   'candidates_fewer_than_four_nonzero_count_years':int((table.all_year_counts_returned&table.nonzero_count_years.lt(4)).sum()),
   'candidates_unresolved_requests':int((~table.all_year_counts_returned).sum()),'no_date_controls_returned':int(table.no_date_control_status.eq('returned').sum()),
   'no_temperature_values_requested':True,'no_predictions_scored':True,
   'limitations':'post-hoc metadata-selected QA envelopes and provider record counts, not temperature-only counts or unique-date coverage; waterbody type, subdaily completeness, quality, no-estimate status, date boundary and watershed independence remain unverified; blank-QA-span stations remain unresolved'}
 status.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))
if __name__=='__main__':main()
