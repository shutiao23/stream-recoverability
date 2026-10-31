#!/usr/bin/env python3
"""Posthoc intake of all sufficiently observed incomplete Rio Mora years."""
import argparse,gzip,json,shutil,time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd,requests
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');OLD=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'expansion_raw';URL='https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items';SITE='08377900'
def freeze():
 path=STAGE/'expansion_plan.json'
 if path.exists():raise FileExistsError('Preserve expansion plan')
 old=json.loads((STAGE/'measurement_support_independent_audit.json').read_text());q=json.loads((OLD/'feasibility_status.json').read_text())
 if old['status']!='passed':raise ValueError('Prior analyses incomplete')
 a=pd.read_csv(PRIVATE/'daily_year_feasibility.csv',dtype={'station_id':str});d=a[(a.station_id==SITE)&a.year.between(2011,2025)];candidate=d[(~d.complete_reference_daily)&(d.usable_days/d.days>=.75)].copy();hist=set(d.loc[d.eligible_history,'year'].astype(int));complete=set(d.loc[d.complete_reference_daily,'year'].astype(int));metadata=pd.read_csv(PRIVATE/'continuous_metadata.csv',dtype={'station_id':str,'series_id':str});s=metadata[(metadata.station_id==SITE)&metadata.daily_parent_match]
 if len(s)!=1:raise ValueError('No unique daily parent')
 rows=[]
 for r in candidate.itertuples(index=False):
  histories=sorted(hist-{int(r.year)});rows.append({'station_id':SITE,'year':int(r.year),'series_id':s.series_id.iloc[0],
    'usable_days':int(r.usable_days),'calendar_days':int(r.days),'history_years':';'.join(map(str,histories)),
    'eligible_histories':len(histories),'complete_history_years':len(set(histories)&complete),'eligible_partial_history':len(histories)>=3})
 roster=pd.DataFrame(rows).sort_values('year');dest=STAGE/'expansion_roster.csv';roster.to_csv(dest,index=False)
 files=[PRIVATE/'daily_year_feasibility.csv',PRIVATE/'continuous_metadata.csv',OLD/'feasibility_status.json',OLD/'network_status.json',STAGE/'measurement_support_independent_audit.json',Path(__file__),dest]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc expansion after this site, its observed daily values, prior model scores and measurement-support sensitivity were examined; before new target continuous observations or model errors',
  'cohort':'All Rio Mora years 2011-2025 with at least 75% usable daily values but an incomplete daily year, regardless of H30, missing pattern or prior model outcomes. Existing complete years are retained separately and are not redownloaded.',
  'selection_warning':'The site was chosen after earlier scores and NLDI screening, and these years were used as other-year histories in previous analyses. The dataset is opened and selected; this is not a blinded, prospective or independent-climate evaluation.',
  'request':'For every candidate year obtain the same public USGS instantaneous parent series, spanning prior Dec 31 UTC to following Jan 2 UTC, all records and pages, without target model scoring. Record failures as unknown.',
  'future':'Apply the same approved/blank-qualifier quarter-hour rules and conditional [-5,50] missing-slot bounds under fixed and civil clocks to every candidate; use original numeric daily gaps as hidden target values if an exploratory model evaluation is later fixed.',
  'limitations':'Partial daily years cannot be relabeled as complete; physical unknown-value range, clock convention, quality corrections, sensor accuracy, source overlap and climate independence remain unresolved. Temporary files are not durable.',
  'sites':1,'target_years':len(roster),'years_with_three_histories':int(roster.eligible_partial_history.sum()),}
 path.write_text(json.dumps(p,indent=2)+'\n');print(json.dumps({'target_years':len(roster),'years_with_three_histories':p['years_with_three_histories'],'years':roster.year.tolist()},indent=2))
def run():
 p=json.loads((STAGE/'expansion_plan.json').read_text())
 statuspath=STAGE/'expansion_acquisition.json';receiptpath=STAGE/'expansion_receipts.json'
 if statuspath.exists() or receiptpath.exists():raise FileExistsError('Preserve existing expansion result')
 roster=pd.read_csv(STAGE/'expansion_roster.csv',dtype={'station_id':str,'series_id':str});RAW.mkdir(exist_ok=True);receipts=[];stop=False
 for row in roster.itertuples(index=False):
  item={'station_id':row.station_id,'year':int(row.year),'status':'unknown','features':0,'pages':[]}
  if stop:item['reason']='service_or_storage_stop';receipts.append(item);continue
  params={'f':'json','time_series_id':row.series_id,'time':f'{row.year-1}-12-31T00:00:00Z/{row.year+1}-01-02T00:00:00Z','properties':'time,value,approval_status,qualifier,time_series_id','skipGeometry':'true','limit':50000};url=URL;page=0
  try:
   while url:
    if shutil.disk_usage(STAGE).free<1024**3:item['reason']='insufficient_tmpfs_reserve';stop=True;break
    r=requests.get(url,params=params,timeout=90,headers={'User-Agent':'stream-temperature reference qualification/1.0'});params=None
    if r.status_code!=200:item['http_status']=r.status_code;item['reason']='http_failure';stop=r.status_code in (401,403,429,503);break
    doc=r.json()
    if not isinstance(doc.get('features'),list):raise ValueError('Unexpected response')
    if any(v.get('properties',{}).get('time_series_id') not in (None,row.series_id) for v in doc['features']):raise ValueError('Unexpected series')
    f=RAW/f'{row.station_id}_{row.year}_{page:02d}.json.gz'
    if f.exists():raise FileExistsError('Preserve raw response')
    with f.open('wb') as stream:
     with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as z:z.write(r.content)
    item['features']+=len(doc['features']);item['pages'].append({'file':f.name,'features':len(doc['features']),'request_url':r.url});links=[x.get('href') for x in doc.get('links',[]) if x.get('rel')=='next']
    if len(links)>1:raise ValueError('Ambiguous pagination')
    url=links[0] if links else None
    if url and not str(url).startswith('https://api.waterdata.usgs.gov/'):raise ValueError('Unexpected pagination host')
    page+=1
    if page>10:raise ValueError('Unexpected page count')
    time.sleep(1)
   if not url and 'reason' not in item:item['status']='completed'
  except (requests.RequestException,ValueError,KeyError,TypeError) as e:item['reason']=type(e).__name__
  receipts.append(item);receiptpath.write_text(json.dumps(receipts,indent=2)+'\n');print('Rio Mora expansion',len(receipts),'of',len(roster),item['status'],item.get('reason',''),flush=True)
 receiptpath.write_text(json.dumps(receipts,indent=2)+'\n');out={'status':'completed' if all(x['status']=='completed' for x in receipts) else 'partial_unknown',
  'requested_years':len(roster),'completed_years':sum(x['status']=='completed' for x in receipts),'features':sum(x['features'] for x in receipts),'model_predictions_or_errors_calculated':False,'limitations':p['limitations']+' '+p['selection_warning'],'storage':'temporary RAM filesystem; not durable'}
 statuspath.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
