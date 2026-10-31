#!/usr/bin/env python3
"""Apply the previous two-clock USGS qualification and H30 bounds to all new years."""
import argparse,gzip,importlib.util,json,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'expansion_raw'
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def freeze():
 path=STAGE/'expansion_qualification_plan.json'
 if path.exists():raise FileExistsError('Preserve expansion qualification plan')
 status=json.loads((STAGE/'expansion_acquisition.json').read_text());receipt=STAGE/'expansion_receipts.json'
 if status['status']!='completed':raise ValueError('Continuous expansion intake incomplete')
 files=[STAGE/'expansion_plan.json',STAGE/'expansion_roster.csv',STAGE/'expansion_acquisition.json',receipt,STAGE/'876_continuous_qualification.py',STAGE/'893_subdaily_h30_bounds.py',USGS/'cohort_metadata.csv',DATA/'daily/08377900.parquet',Path(__file__)]
 for item in json.loads(receipt.read_text()):
  for page in item['pages']:
   f=RAW/page['file']
   files.append(f)
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after previous site scores and daily records were examined; after all five raw continuous responses were downloaded but before this qualification/bound analysis',
  'cohort':'Every fixed Rio Mora incomplete daily year meeting the prior 75% availability rule. Do not select by H30, subdaily completeness or model error.',
  'quality':'Use the same approved, finite, unique, 15-minute-grid continuous-sample rules and conservative nonempty-qualifier exclusion as the original eight-year audit. A full hour requires at least one clean on-grid observation in every physical hour and no questionable observations that day; full quarter requires all expected 15-minute slots.',
  'H30_bounds':'Use the same earlier fixed-standard and local-civil clock methods and the explicit assumption that all unknown quarter-hour values lie in [-5,50] C; report min/max annual H30 enclosure. This interval is conditional on a hypothetical range, not proof of full observation or sensor accuracy.',
  'limitations':'This station and selected years were examined as histories and prior results; masks and site are not independent climates. Daily clock, USGS quality flags/corrections, physical range and original model training support remain unresolved. Results remain temporary.',
  }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen complete expansion-year quality and H30 bound screen')
def run():
 p=json.loads((STAGE/'expansion_qualification_plan.json').read_text())
 q=module('riomora_old_quality',STAGE/'876_continuous_qualification.py');b=module('riomora_old_bounds',STAGE/'893_subdaily_h30_bounds.py');parser=T.load_script('riomora_partial_parser',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');daily=parser.valid_daily(pd.read_parquet(DATA/'daily/08377900.parquet'));meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id').loc['08377900'];offset={'MST':-7,'CST':-6}[meta.time_zone_abbreviation];days=[];bounds=[];years=[]
 for i,item in enumerate(json.loads((STAGE/'expansion_receipts.json').read_text()),1):
  records=[]
  for page in item['pages']:
   with gzip.open(RAW/page['file'],'rt') as f:doc=json.load(f)
   records.extend(x['properties'] for x in doc['features'])
  frame=pd.DataFrame(records)
  if frame.empty:raise ValueError('Empty response remains unknown')
  frame['time']=pd.to_datetime(frame.time,utc=True,errors='raise');frame['value']=pd.to_numeric(frame.value,errors='coerce');frame['approved']=frame.approval_status.fillna('').astype(str).str.lower().eq('approved');frame['qualifier_empty']=frame.qualifier.map(q.qualifier_empty);frame['on_grid']=frame.time.dt.minute.mod(15).eq(0)&frame.time.dt.second.eq(0)&frame.time.dt.microsecond.eq(0)
  year=int(item['year'])
  for clock,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',meta.native_zone)]:
   d=q.year_qualify(frame,year,zone,daily);bd=b.calculate(frame,year,zone)
   d['station_id']=item['station_id'];d['year']=year;d['clock']=clock;bd['station_id']=item['station_id'];bd['year']=year;bd['clock']=clock
   joined=bd.merge(d[['day','quarter_complete','subdaily_mean']],on='day',validate='one_to_one');good=joined.quarter_complete.to_numpy(bool)
   if not np.allclose(joined.loc[good,'lower_c'],joined.loc[good,'subdaily_mean'],atol=1e-10,rtol=0) or not np.allclose(joined.loc[good,'upper_c'],joined.loc[good,'subdaily_mean'],atol=1e-10,rtol=0):raise AssertionError('Quarter-complete daily bound mismatch')
   L=float(bd.lower_c.rolling(30,min_periods=30).mean().max());U=float(bd.upper_c.rolling(30,min_periods=30).mean().max());delta=(d.subdaily_mean-d.published_daily).dropna()
   years.append({'station_id':item['station_id'],'year':year,'clock':clock,'days':len(d),'hourly_complete_days':int(d.hourly_complete.sum()),'quarter_complete_days':int(d.quarter_complete.sum()),
      'hourly_complete_year':bool(d.hourly_complete.all()),'quarter_complete_year':bool(d.quarter_complete.all()),'unknown_slots':int(bd.unknown_slots.sum()),'h30_lower_c':L,'h30_upper_c':U,'h30_interval_width_c':U-L,
      'comparison_days':len(delta),'mean_abs_daily_difference_c':float(delta.abs().mean()) if len(delta) else np.nan,'max_abs_daily_difference_c':float(delta.abs().max()) if len(delta) else np.nan})
   days.append(d);bounds.append(bd)
  print('Rio Mora expansion qualification',i,'of 5',flush=True)
 y=pd.DataFrame(years);df=pd.concat(days,ignore_index=True);bf=pd.concat(bounds,ignore_index=True);yf=STAGE/'expansion_qualification_years.csv';dd=STAGE/'expansion_qualification_days.parquet';bb=STAGE/'expansion_bounds_days.parquet';y.to_csv(yf,index=False);df.to_parquet(dd,index=False);bf.to_parquet(bb,index=False)
 summaries={}
 for clock in ['fixed_standard','native_civil']:
  z=y[y.clock.eq(clock)];summaries[clock]={'years':len(z),'hourly_complete_years':int(z.hourly_complete_year.sum()),'quarter_complete_years':int(z.quarter_complete_year.sum()),'zero_width_H30_years':int(z.h30_interval_width_c.le(1e-10).sum()),'H30_width_le_0_1_years':int(z.h30_interval_width_c.le(.1+1e-10).sum()),'median_H30_width_c':float(z.h30_interval_width_c.median())}
 out={'status':'completed_expansion_qualification','target_years':len(y)//2,'clock_summaries':summaries,'model_predictions_calculated':False,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'expansion_qualification_status.json').write_text(json.dumps(out,indent=2)+'\n');print(y.to_string(index=False));print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
