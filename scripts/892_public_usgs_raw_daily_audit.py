#!/usr/bin/env python3
"""Audit published daily target values and qualifier labels against snapshots."""
import collections,gzip,json
from pathlib import Path
from datetime import timezone
import numpy as np,pandas as pd
BASE=Path(__file__).resolve().parents[1]
def main():
 roster=pd.read_csv(BASE/'metadata/target_roster.csv',dtype={'station_id':str});meta=pd.read_csv(BASE/'metadata/cohort_metadata.csv',dtype={'station_id':str}).set_index('station_id');totals=collections.Counter();years=0
 for row in roster.itertuples(index=False):
  with gzip.open(BASE/'daily_original'/(row.station_id+'.json.gz'),'rt') as f:doc=json.load(f)
  p=meta.loc[row.station_id];groups=collections.defaultdict(list)
  for x in doc['features']:
   r=x.get('properties',x);text=str(r['time']);stamp=pd.Timestamp(text)
   if len(text)!=10 and stamp.tzinfo is not None:stamp=stamp.tz_convert(p.native_zone).tz_localize(None)
   day=stamp.normalize()
   if day.year==row.year:groups[day].append(r)
  processed=pd.read_parquet(BASE/'daily'/(row.station_id+'.parquet'));processed['date']=pd.to_datetime(processed.date);g=processed[processed.date.dt.year.eq(row.year)].set_index('date');dates=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31')
  if set(groups)!=set(dates) or len(g)!=len(dates) or g.index.has_duplicates:raise ValueError('Daily target dates differ')
  raw_values=[];processed_values=[]
  for d in dates:
   entries=groups[d];values=[]
   for r in entries:
    qualifier=r.get('qualifier');blank=qualifier is None or qualifier=='' or qualifier==[]
    totals['raw_rows']+=1;totals['rows_with_nonempty_qualifier']+=int(not blank);totals['nonapproved_rows']+=int(str(r.get('approval_status','')).lower()!='approved')
    try:v=float(r['value'])
    except (TypeError,ValueError):v=float('nan')
    values.append(v)
   if len(entries)!=1 or not np.isfinite(values[0]) or not blank or str(entries[0].get('approval_status','')).lower()!='approved':raise ValueError('Target daily source quality or multiplicity differs')
   x=g.loc[d]
   if not bool(x.reported) or bool(x.unapproved) or bool(x.ambiguous) or bool(x.estimated) or not np.isfinite(x.water_c):raise ValueError('Processed target quality differs')
   raw_values.append(values[0]);processed_values.append(float(x.water_c))
  a=np.asarray(raw_values);b=np.asarray(processed_values)
  if not np.allclose(a,b,atol=1e-10,rtol=0):raise AssertionError('Raw and processed published daily target values differ')
  if not np.isclose(np.max(np.convolve(a,np.ones(30)/30,mode='valid')),np.max(np.convolve(b,np.ones(30)/30,mode='valid')),atol=1e-10,rtol=0):raise AssertionError('Raw daily H30 differs')
  years+=1;print('Audited raw daily target',years,'of',len(roster),flush=True)
 out={'status':'passed','sites':int(roster.station_id.nunique()),'target_years':years,'raw_daily_rows':totals['raw_rows'],
      'raw_target_rows_with_nonempty_qualifier':totals['rows_with_nonempty_qualifier'],'raw_target_nonapproved_rows':totals['nonapproved_rows'],
      'scope':'Posthoc comparison of previously downloaded raw daily API responses with processed target daily values; raw/processed 30-day maxima also checked.',
      'limitations':'Blank qualifiers and approved status do not prove absence of unrecorded corrections or physical measurement error; no model fitting, independent climate or true reporting-clock validation.'}
 (BASE/'results/raw_daily_reference_replay.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
