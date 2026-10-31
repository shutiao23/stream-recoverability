#!/usr/bin/env python3
"""Conservatively qualify all fixed USGS parent-series target years."""
import argparse,gzip,json,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import importlib
helper=importlib.import_module('871_usgs_partial_daily_feasibility')
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');RAW=STAGE/'raw'
def freeze():
 dest=STAGE/'qualification_plan.json'
 if dest.exists():raise FileExistsError('Preserve qualification plan')
 status=json.loads((STAGE/'continuous_tmpfs_status.json').read_text());receipt=STAGE/'continuous_tmpfs_receipts.json'
 if status['status']!='completed' or status['completed_station_years']!=8:raise ValueError('Complete target intake unavailable')
 doc={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after original daily values/witnesses and one continuous response first/last sample values were inspected for format; before full continuous quality/completeness or model errors were calculated',
  'cohort':'All eight fixed target years and four sites; no exclusion based on network overlap, values, completeness or model outcomes.',
  'quality':'A usable subdaily observation has finite numeric water temperature, USGS approval Approved, no nonempty qualifier, a distinct UTC timestamp and quarter-hour grid alignment. Any extra nonfinite, flagged, duplicate or off-grid observation makes that reporting day incomplete under both rules; this is conservative and absence of qualifiers does not prove error-free measurements.',
  'day_rules':'Evaluate all target calendar days twice: fixed site standard time from the reported MST or CST abbreviation, and the metadata native local civil zone. Full-hour support requires at least one clean on-grid sample in each physical UTC hour of the reporting day; full-quarter support requires all distinct expected quarter-hour timestamps. Civil DST days have 23 or 25 hours, not 24; fixed-standard days always span 24 physical hours.',
  'comparison':'For each day with full quarter-hour support, compare arithmetic mean of all subdaily temperatures with the previously reported USGS approved daily mean on the same date. Summarize both clocks for all sites/years; do not use numerical agreement to select the scoring cohort. A difference can reflect published rounding, clock, method, sublocation or revision.',
  'limitations':'Parent-series linkage, approved status and clear qualifier do not establish unchanged instrument, physical accuracy, source-model separation or independent climate. Previously inspected daily targets and witness years make this retrospective. A 24-hour bin screen with >=1 point/hour is weaker than requiring all quarter-hour values.',
  }
 dest.write_text(json.dumps(doc,indent=2)+'\n');print('Frozen continuous quality and two-clock qualification')
def qualifier_empty(v):
 if v is None:return True
 if isinstance(v,list):return not any(str(x).strip() for x in v)
 return not str(v).strip()
def year_qualify(df,year,zone,published):
 ts=df.time.dt.tz_convert(zone);d=df.copy();d['day']=ts.dt.date;d=d[d.day.map(lambda x:x.year==year)].copy();duplicate=d.time.duplicated(keep=False)
 d['good']=d.approved&d.qualifier_empty&np.isfinite(d.value)&d.on_grid&~duplicate
 by={day:g for day,g in d.groupby('day',sort=False)}; rows=[]
 for day in pd.date_range(f'{year}-01-01',f'{year}-12-31'):
  local=day.date();start=pd.Timestamp(local,tz=zone).tz_convert('UTC');end=pd.Timestamp(local+timedelta(days=1),tz=zone).tz_convert('UTC')
  expected=pd.date_range(start,end,freq='15min',inclusive='left');expected_hours=pd.date_range(start,end,freq='h',inclusive='left');g=by.get(local)
  if g is None:rows.append({'day':day,'expected_hours':len(expected_hours),'n_rows':0,'hourly_complete':False,'quarter_complete':False,'subdaily_mean':np.nan,'published_daily':published.get(day,np.nan)});continue
  actual=pd.DatetimeIndex(g.time);clean=bool(g.good.all());hours=pd.DatetimeIndex(g.time.dt.floor('h').unique());hourly=clean and len(hours)==len(expected_hours) and set(hours)==set(expected_hours)
  quarter=clean and len(actual)==len(expected) and set(actual)==set(expected)
  rows.append({'day':day,'expected_hours':len(expected_hours),'n_rows':len(g),'hourly_complete':hourly,'quarter_complete':quarter,'subdaily_mean':float(g.value.mean()) if quarter else np.nan,'published_daily':published.get(day,np.nan)})
 return pd.DataFrame(rows)
def run():
 p=json.loads((STAGE/'qualification_plan.json').read_text());status=json.loads((STAGE/'continuous_tmpfs_status.json').read_text());receipt=STAGE/'continuous_tmpfs_receipts.json'
 meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');target=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});all_years=[];all_days=[];qualifier_counts={}
 for n,item in enumerate(json.loads(receipt.read_text()),1):
  site=item['station_id'];year=item['year'];frames=[]
  for page in item['pages']:
   f=RAW/page['file']
   with gzip.open(f,'rt') as stream:doc=json.load(stream)
   if len(doc['features'])!=page['features']:raise ValueError('Response feature count changed')
   frames.extend(v['properties'] for v in doc['features'])
  frame=pd.DataFrame(frames)
  if frame.empty:raise ValueError('Empty response is unknown, not an incomplete year')
  frame['time']=pd.to_datetime(frame.time,utc=True,errors='raise');frame['value']=pd.to_numeric(frame.value,errors='coerce');frame['approved']=frame.approval_status.fillna('').astype(str).str.lower().eq('approved')
  frame['qualifier_empty']=frame.qualifier.map(qualifier_empty);frame['on_grid']=frame.time.dt.minute.mod(15).eq(0)&frame.time.dt.second.eq(0)&frame.time.dt.microsecond.eq(0)
  for v in frame.qualifier:
   key='none' if qualifier_empty(v) else str(v);qualifier_counts[key]=qualifier_counts.get(key,0)+1
  daily=helper.valid_daily(pd.read_parquet(DATA/'daily'/(site+'.parquet')))
  ident=meta.loc[site];offset={'MST':-7,'CST':-6}.get(ident.time_zone_abbreviation)
  if offset is None or not isinstance(ident.native_zone,str):raise ValueError('Unknown time convention')
  for clock,zone in [('fixed_standard',timezone(timedelta(hours=offset))),('native_civil',ident.native_zone)]:
   days=year_qualify(frame,year,zone,daily);days['station_id']=site;days['year']=year;days['clock']=clock;all_days.append(days)
   diff=(days.subdaily_mean-days.published_daily).dropna()
   all_years.append({'station_id':site,'year':year,'clock':clock,'days':len(days),'hourly_complete_days':int(days.hourly_complete.sum()),'quarter_complete_days':int(days.quarter_complete.sum()),
    'hourly_complete_year':bool(days.hourly_complete.all()),'quarter_complete_year':bool(days.quarter_complete.all()),'comparison_days':len(diff),
    'mean_abs_daily_difference_c':float(diff.abs().mean()) if len(diff) else np.nan,'max_abs_daily_difference_c':float(diff.abs().max()) if len(diff) else np.nan,
    'days_abs_diff_at_most_0_05_c':int((diff.abs()<=.05+1e-10).sum())})
  print('Qualified continuous target',n,'of 8',flush=True)
 yearly=pd.DataFrame(all_years);day=pd.concat(all_days,ignore_index=True);y=STAGE/'continuous_qualification_years.csv';d=STAGE/'continuous_qualification_days.parquet';yearly.to_csv(y,index=False);day.to_parquet(d,index=False)
 q=STAGE/'qualifier_counts.json';q.write_text(json.dumps(qualifier_counts,indent=2,sort_keys=True)+'\n')
 summary={}
 for name in ['fixed_standard','native_civil']:
  x=yearly[yearly.clock.eq(name)];z=day[day.clock.eq(name)];diff=(z.subdaily_mean-z.published_daily).dropna()
  summary[name]={'station_years':len(x),'hourly_complete_years':int(x.hourly_complete_year.sum()),'quarter_complete_years':int(x.quarter_complete_year.sum()),
   'hourly_complete_days':int(x.hourly_complete_days.sum()),'quarter_complete_days':int(x.quarter_complete_days.sum()),'compared_days':len(diff),
   'mean_abs_daily_difference_c':float(diff.abs().mean()) if len(diff) else None,'max_abs_daily_difference_c':float(diff.abs().max()) if len(diff) else None,
   'days_abs_diff_at_most_0_05_c':int((diff.abs()<=.05+1e-10).sum())}
 result={'status':'completed_continuous_qualification','station_years':len(target),'sites':target.station_id.nunique(),'comparisons':summary,
  'qualifier_categories':len(qualifier_counts),'model_predictions_calculated':False,
  'storage':'temporary RAM filesystem; not durable','limitations':p['limitations']}
 (STAGE/'continuous_qualification_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
