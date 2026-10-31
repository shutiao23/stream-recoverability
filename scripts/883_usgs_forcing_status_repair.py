#!/usr/bin/env python3
"""Recover forcing status after saved files were written but final status failed."""
import argparse,gzip,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');POWER=STAGE/'power'
def freeze():
 p=STAGE/'forcing_repair_plan.json'
 if p.exists() or (STAGE/'forcing_status.json').exists():raise FileExistsError('Preserve existing forcing state')
 plan=json.loads((STAGE/'scoring_plan.json').read_text());manifest=json.loads((POWER/'manifest.json').read_text());r=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str})
 if len(manifest['records'])!=r.station_id.nunique() or any(x['status']!='completed' for x in manifest['records']):raise ValueError('Incomplete saved responses')
 files=[STAGE/'scoring_plan.json',POWER/'manifest.json',POWER/'daily_air.parquet',PRIVATE/'continuous_target_roster.csv',STAGE/'879_usgs_partial_power.py',Path(__file__)]
 files += [POWER/x['file'] for x in manifest['records']]
 doc={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc repair after four responses and daily forcing were saved but an accidentally shadowed status-path variable caused AttributeError; before target predictions',
 'procedure':'Read each unchanged saved NASA POWER JSON response, independently rebuild all daily T2M values and check the stored combined table, source coordinates, period, local-solar-time parameter, content hashes and target coverage; then write a separate corrected forcing status without another network request.',
 'limitations':'Reconstruction verifies stored data and parameters, not NASA physical accuracy, USGS day alignment, historical API consistency or model validity.',
 }
 p.write_text(json.dumps(doc,indent=2)+'\n');print('Frozen saved-response forcing status repair')
def run():
 p=json.loads((STAGE/'forcing_repair_plan.json').read_text())
 manifest=json.loads((POWER/'manifest.json').read_text());r=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str}).drop_duplicates('station_id').set_index('station_id');frames=[]
 for item in manifest['records']:
  site=item['station_id'];q=item['parameters'];meta=r.loc[site]
  if q['time-standard']!='LST' or q['start']!='20110101' or q['end']!='20241231' or q['parameters']!='T2M' or q['latitude']!=round(float(meta.latitude),2) or q['longitude']!=round(float(meta.longitude),2):raise ValueError('Forcing request differs')
  f=POWER/item['file']
  with gzip.open(f,'rt') as stream:doc=json.load(stream)
  v=doc['properties']['parameter']['T2M'];dates=pd.date_range('2011-01-01','2024-12-31');values=pd.to_numeric(pd.Series([v.get(d.strftime('%Y%m%d'),np.nan) for d in dates]),errors='coerce');values=values.where(values.gt(-990))
  if int(np.isfinite(values).sum())!=item['finite_days']:raise ValueError('Forcing count differs')
  frames.append(pd.DataFrame({'date':dates,'air_temperature_c':values,'station_id':site,'network_id':'usgs_partial_'+site}))
 actual=pd.concat(frames,ignore_index=True).sort_values(['station_id','date']).reset_index(drop=True);expected=pd.read_parquet(POWER/'daily_air.parquet').sort_values(['station_id','date']).reset_index(drop=True)
 pd.testing.assert_frame_equal(actual,expected,check_dtype=False,atol=1e-10,rtol=0)
 if set(actual.station_id)!=set(r.index):raise ValueError('Forcing roster differs')
 out={'status':'completed','requested_sites':len(r),'returned_sites':len(frames),'finite_days':int(np.isfinite(actual.air_temperature_c).sum()),'status_repaired_after_variable_shadowing':True,'no_network_retry':True,
 'limitations':'NASA POWER LST may not align with USGS local standard or civil day; weather is gridded, not a direct air observation.','storage':'temporary RAM filesystem; not durable'}
 (STAGE/'forcing_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
