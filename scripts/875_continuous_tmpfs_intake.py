#!/usr/bin/env python3
"""Continue the frozen USGS intake on temporary storage after disk reserve stop."""
import argparse, gzip, json, shutil, time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd, requests
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability')
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily'
PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027'
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'raw'
URL='https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items'
def freeze():
 dest=STAGE/'storage_amendment.json'
 if dest.exists():raise FileExistsError('Preserve existing amendment')
 failure=json.loads((OUT/'continuous_target_acquisition.json').read_text());plan=json.loads((OUT/'continuous_target_plan.json').read_text())
 if failure['status']!='partial_unknown' or failure['downloaded_features']!=0 or plan['target_years']!=8:raise ValueError('Original storage stop differs')
 roster=PRIVATE/'continuous_target_roster.csv'
 doc={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc storage-only amendment after original acquisition stopped with insufficient disk before downloading data',
  'scope':'The identical eight fixed target years and daily-parent time-series IDs, UTC request windows, columns and pagination; no outcome-based replacement.',
  'storage':'Raw responses, receipts and subsequent diagnostics stored only on /dev/shm; volatile on reboot. Original disk-reserve failure retained. Stop if temporary storage has less than 1 GiB free.',
  'limitations':plan['limitations'],}
 dest.write_text(json.dumps(doc,indent=2)+'\n');print('Frozen temporary-storage amendment')
def run():
 p=json.loads((STAGE/'storage_amendment.json').read_text())
 target=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str,'series_id':str}).sort_values(['station_id','year'])
 status_path=STAGE/'continuous_tmpfs_status.json';receipts_path=STAGE/'continuous_tmpfs_receipts.json'
 if status_path.exists() or receipts_path.exists():raise FileExistsError('Preserve existing temporary intake')
 receipts=[];stop=False
 for row in target.itertuples(index=False):
  item={'station_id':row.station_id,'year':int(row.year),'status':'unknown','pages':[],'features':0}
  if pd.isna(row.series_id):item['reason']='missing_unique_parent';receipts.append(item);continue
  if stop:item['reason']='service_or_storage_stop';receipts.append(item);continue
  params={'f':'json','time_series_id':row.series_id,'time':f'{row.year-1}-12-31T00:00:00Z/{row.year+1}-01-02T00:00:00Z','properties':'time,value,approval_status,qualifier,time_series_id','skipGeometry':'true','limit':50000};url=URL;page=0
  try:
   while url:
    if shutil.disk_usage(STAGE).free<1024**3:item['reason']='insufficient_tmpfs_reserve';stop=True;break
    response=requests.get(url,params=params,timeout=90,headers={'User-Agent':'stream-temperature reference qualification/1.0'});params=None
    if response.status_code!=200:
     item['http_status']=response.status_code;item['reason']='http_failure';stop=response.status_code in (401,403,429,503);break
    doc=response.json()
    if not isinstance(doc.get('features'),list):raise ValueError('Unexpected continuous response')
    if any(v.get('properties',{}).get('time_series_id') not in (None,row.series_id) for v in doc['features']):raise ValueError('Unexpected series')
    file=RAW/f'{row.station_id}_{row.year}_{page:02d}.json.gz'
    if file.exists():raise FileExistsError('Preserve previous response')
    with file.open('wb') as f:
     with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z:z.write(response.content)
    item['features']+=len(doc['features']);item['pages'].append({'file':file.name,'features':len(doc['features']),'request_url':response.url})
    next_links=[x.get('href') for x in doc.get('links',[]) if x.get('rel')=='next']
    if len(next_links)>1:raise ValueError('Ambiguous pagination')
    url=next_links[0] if next_links else None
    if url and not str(url).startswith('https://api.waterdata.usgs.gov/'):raise ValueError('Unexpected pagination host')
    page+=1
    if page>10:raise ValueError('Unexpected page count')
    time.sleep(1)
   if not url and 'reason' not in item:item['status']='completed'
  except (requests.RequestException,ValueError,KeyError,TypeError) as e:item['reason']=type(e).__name__
  receipts.append(item);receipts_path.write_text(json.dumps(receipts,indent=2)+'\n');print('Continuous target intake',len(receipts),'of',len(target),item['status'],item.get('reason',''),flush=True)
 receipts_path.write_text(json.dumps(receipts,indent=2)+'\n')
 status={'status':'completed' if all(x['status']=='completed' for x in receipts) else 'partial_unknown','requested_station_years':len(target),'completed_station_years':sum(x['status']=='completed' for x in receipts),'downloaded_features':sum(x['features'] for x in receipts),'values_analyzed':False,'predictions_evaluated':False,'storage':'temporary RAM filesystem; not durable','limitations':p['limitations']}
 status_path.write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
