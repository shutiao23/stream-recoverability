#!/usr/bin/env python3
"""Conditional H30 bounds from all eight USGS continuous target years."""
import argparse,gzip,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';USGS=ROOT/'results/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'raw'
LOW,HIGH=-5.,50.
def empty(v):
 if v is None:return True
 if isinstance(v,list):return not any(str(x).strip() for x in v)
 return not str(v).strip()
def freeze():
 path=STAGE/'subdaily_h30_bounds_plan.json'
 if path.exists():raise FileExistsError('Preserve bounds plan')
 a=json.loads((STAGE/'independent_audit_status.json').read_text());s=json.loads((STAGE/'score_independent_audit.json').read_text())
 if a['status']!='passed' or s['status']!='passed':raise ValueError('Prior qualification/score audit incomplete')
 files=[STAGE/'continuous_tmpfs_receipts.json',STAGE/'continuous_qualification_days.parquet',STAGE/'continuous_qualification_years.csv',STAGE/'independent_audit_status.json',STAGE/'score_independent_audit.json',USGS/'cohort_metadata.csv',PRIVATE/'continuous_target_roster.csv',Path(__file__)]
 for item in json.loads((STAGE/'continuous_tmpfs_receipts.json').read_text()):
  for page in item['pages']:
   path_raw=RAW/page['file']
   files.append(path_raw)
 plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after daily values, target H30, continuous eligibility and model scores were examined; before subdaily H30 bounds are computed',
  'cohort':'All eight previously fixed target years, both fixed-standard and native-civil clocks. Do not select years by outcomes or network overlap.',
  'estimand':'For each reporting day, equally weighted mean of expected 15-minute physical slots; H30 is the maximum of all 30 consecutive reporting-day means wholly within that calendar year. Civil DST days contain 92 or 100 slots and are not 24 physical hours.',
  'assumption':'Every unobserved, nonfinite, unapproved, flagged, duplicated or otherwise ambiguous slot lies in [-5,50] degrees C. This is a hypothetical water-value bound, not a demonstrated instrument or physical limit; if false, H30 enclosure can fail.',
  'method':'A unique on-grid approved finite reading with empty qualifier is fixed. Missing/ambiguous expected slots receive the assumed lower or upper value. A reporting day containing off-grid observations is conservatively treated as entirely unknown. Require accepted observations themselves inside the assumed range. Maximize the 30-day rolling daily lower and upper sequences separately.',
  'comparison':'Recheck that every previously fully quarter-hour-supported day has zero-width bounds and an identical saved continuous mean. Later, score fixed model predictions against these intervals without treating their midpoint as truth, for all cases and separately the already known fixed-standard full-hour subset.',
  'limitations':'Clock choice, quality corrections, actual value range, sensor accuracy, source model overlap, historical interpolation and independent climates are unresolved. The score has already been opened and one selected site contributes all three full-hour years. Bounds are conditional, not measured truth.',
  }
 path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen all-year, two-clock conditional subdaily H30 bounds')
def calculate(frame,year,zone):
 d=frame.copy();d['day']=d.time.dt.tz_convert(zone).dt.date;d=d[d.day.map(lambda x:x.year==year)].copy();by={k:g for k,g in d.groupby('day',sort=False)};rows=[]
 for day in pd.date_range(f'{year}-01-01',f'{year}-12-31'):
  local=day.date();begin=pd.Timestamp(local,tz=zone).tz_convert('UTC');end=pd.Timestamp(local+timedelta(days=1),tz=zone).tz_convert('UTC');expected=pd.date_range(begin,end,freq='15min',inclusive='left');g=by.get(local);n=len(expected)
  known=[];offgrid=0
  if g is not None:
   offgrid=int((~g.on_grid).sum())
   if not offgrid:
    dup=g.time.duplicated(keep=False);good=g.approved&g.qualifier_empty&g.on_grid&~dup&np.isfinite(g.value)
    a=g.loc[good,['time','value']]
    if len(a) and (~a.time.isin(expected)).any():raise ValueError('Reported slot outside expected day')
    if len(a) and (~a.value.between(LOW,HIGH)).any():raise ValueError('Observed clean value violates assumed range')
    known=a.value.tolist()
  k=len(known)
  if k>n:raise ValueError('Too many known slots')
  total=float(sum(known));lower=(total+(n-k)*LOW)/n;upper=(total+(n-k)*HIGH)/n
  rows.append({'day':day,'expected_slots':n,'known_slots':k,'unknown_slots':n-k,'offgrid_rows':offgrid,'lower_c':lower,'upper_c':upper})
 return pd.DataFrame(rows)
def run():
 p=json.loads((STAGE/'subdaily_h30_bounds_plan.json').read_text())
 meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');saved=pd.read_parquet(STAGE/'continuous_qualification_days.parquet');saved.day=pd.to_datetime(saved.day);all_days=[];years=[]
 for i,item in enumerate(json.loads((STAGE/'continuous_tmpfs_receipts.json').read_text()),1):
  site=item['station_id'];year=int(item['year']);rows=[]
  for page in item['pages']:
   with gzip.open(RAW/page['file'],'rt') as f:doc=json.load(f)
   rows.extend(x['properties'] for x in doc['features'])
  frame=pd.DataFrame(rows);frame['time']=pd.to_datetime(frame.time,utc=True,errors='raise');frame['value']=pd.to_numeric(frame.value,errors='coerce');frame['approved']=frame.approval_status.fillna('').astype(str).str.lower().eq('approved');frame['qualifier_empty']=frame.qualifier.map(empty)
  frame['on_grid']=frame.time.dt.minute.mod(15).eq(0)&frame.time.dt.second.eq(0)&frame.time.dt.microsecond.eq(0)
  m=meta.loc[site];offset={'MST':-7,'CST':-6}[m.time_zone_abbreviation]
  for clock,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',m.native_zone)]:
   d=calculate(frame,year,zone);d['station_id']=site;d['year']=year;d['clock']=clock
   q=saved[saved.station_id.eq(site)&saved.year.eq(year)&saved.clock.eq(clock)][['day','quarter_complete','subdaily_mean']]
   joined=d.merge(q,on='day',validate='one_to_one');good=joined.quarter_complete.to_numpy(bool)
   if not np.allclose(joined.loc[good,'lower_c'],joined.loc[good,'subdaily_mean'],atol=1e-10,rtol=0) or not np.allclose(joined.loc[good,'upper_c'],joined.loc[good,'subdaily_mean'],atol=1e-10,rtol=0):raise AssertionError('Complete quarter-hour day differs')
   lower=float(d.lower_c.rolling(30,min_periods=30).mean().max());upper=float(d.upper_c.rolling(30,min_periods=30).mean().max())
   if lower>upper+1e-10:raise AssertionError('Invalid H30 enclosure')
   years.append({'station_id':site,'year':year,'clock':clock,'days':len(d),'known_slots':int(d.known_slots.sum()),'unknown_slots':int(d.unknown_slots.sum()),'h30_lower_c':lower,'h30_upper_c':upper,'h30_interval_width_c':upper-lower})
   all_days.append(d)
  print('Subdaily H30 bounds',i,'of 8',flush=True)
 y=pd.DataFrame(years);d=pd.concat(all_days,ignore_index=True);yf=STAGE/'subdaily_h30_bounds_years.csv';df=STAGE/'subdaily_h30_bounds_days.parquet';y.to_csv(yf,index=False);d.to_parquet(df,index=False)
 summaries={}
 for clock in ['fixed_standard','native_civil']:
  x=y[y.clock.eq(clock)];summaries[clock]={'years':len(x),'zero_width_years':int(x.h30_interval_width_c.le(1e-10).sum()),'width_at_most_0_01_c_years':int(x.h30_interval_width_c.le(.01+1e-10).sum()),'width_at_most_0_1_c_years':int(x.h30_interval_width_c.le(.1+1e-10).sum()),'median_width_c':float(x.h30_interval_width_c.median()),'maximum_width_c':float(x.h30_interval_width_c.max())}
 result={'status':'completed_conditional_subdaily_bounds','target_years':8,'day_clock_rows':len(d),'clock_summaries':summaries,'model_scores_calculated':False,'limitations':p['assumption']+' '+p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'subdaily_h30_bounds_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
