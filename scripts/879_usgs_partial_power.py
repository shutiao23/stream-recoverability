#!/usr/bin/env python3
"""Acquire NASA POWER forcing for the frozen previously opened USGS sites."""
import gzip,json,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd,requests
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');POWER=STAGE/'power';URL='https://power.larc.nasa.gov/api/temporal/daily/point'
def main():
 plan=json.loads((STAGE/'scoring_plan.json').read_text())
 out=STAGE/'forcing_status.json'
 if out.exists():raise FileExistsError('Preserve forcing status')
 r=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});sites=r.drop_duplicates('station_id');POWER.mkdir(exist_ok=True);records=[];frames=[]
 for row in sites.itertuples(index=False):
  params={'parameters':'T2M','community':'RE','latitude':round(float(row.latitude),2),'longitude':round(float(row.longitude),2),'start':'20110101','end':'20241231','format':'JSON','time-standard':'LST'}
  entry={'station_id':row.station_id,'parameters':params,'status':'unknown'}
  try:
   response=requests.get(URL,params=params,timeout=50,headers={'User-Agent':'stream-temperature reference research/1.0'});entry['http_status']=response.status_code;response.raise_for_status();data=response.json();values=data['properties']['parameter']['T2M'];dates=pd.date_range('2011-01-01','2024-12-31')
   v=pd.to_numeric(pd.Series([values.get(t.strftime('%Y%m%d'),np.nan) for t in dates]),errors='coerce');v=v.where(v.gt(-990));f=POWER/(row.station_id+'.json.gz')
   with f.open('wb') as out:
    with gzip.GzipFile(fileobj=out,mode='wb',mtime=0) as g:g.write(response.content)
   entry.update(status='completed',file=f.name,finite_days=int(np.isfinite(v).sum()),days=len(dates));frames.append(pd.DataFrame({'date':dates,'air_temperature_c':v,'station_id':row.station_id,'network_id':'usgs_partial_'+row.station_id}))
  except (requests.RequestException,ValueError,KeyError,TypeError) as e:entry['error_type']=type(e).__name__
  records.append(entry);print('POWER acquired',len(records),'of',len(sites),entry['status'],flush=True);time.sleep(1)
 if frames:
  f=POWER/'daily_air.parquet';pd.concat(frames,ignore_index=True).to_parquet(f,index=False)
 manifest={'source':'NASA POWER daily API','endpoint':URL,'time_standard':'LST','retrieved_utc':datetime.now(timezone.utc).isoformat(),'records':records,'daily_file':'daily_air.parquet' if frames else None,'attribution':'NASA POWER Project, NASA Langley Research Center. NASA requests notification on redistribution; no notification sent for this local artifact.'}
 (POWER/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(POWER/'ATTRIBUTION.txt').write_text(manifest['attribution']+'\n'+URL+'\n')
 result={'status':'completed' if len(frames)==len(sites) else 'partial_unknown','requested_sites':len(sites),'returned_sites':len(frames),'finite_days':sum(x.get('finite_days',0) for x in records),'limitations':'NASA POWER LST may not align with USGS local standard or civil day; weather is gridded, not a direct air observation.','storage':'temporary RAM filesystem; not durable'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
