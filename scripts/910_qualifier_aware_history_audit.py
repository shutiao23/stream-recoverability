#!/usr/bin/env python3
"""Independently verify raw qualifier exclusion and requalification."""
import collections,gzip,json
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def blank(v):
 if v is None:return True
 if isinstance(v,list):return all(not str(x).strip() for x in v)
 return not str(v).strip()
def longest(a):
 m=run=0
 for missing in a:
  run=run+1 if missing else 0;m=max(m,run)
 return m
def qualifies(a):
 valid=np.isfinite(a);return bool(len(a) in (365,366) and valid.mean()>=.75 and valid[0] and valid[-1] and longest(~valid)<=45)
def main():
 plan=json.loads((STAGE/'qualifier_aware_history_plan.json').read_text());status=json.loads((STAGE/'qualifier_aware_history_status.json').read_text());correction=json.loads((STAGE/'qualifier_aware_roster_correction.json').read_text())
 initial=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});final=pd.read_csv(STAGE/'qualifier_aware_roster_v2.csv',dtype={'station_id':str,'huc2':str}).fillna('');details=pd.read_csv(STAGE/'qualifier_aware_history_details.csv',dtype={'station_id':str});snap=pd.read_parquet(STAGE/'qualifier_aware_daily.parquet');snap.date=pd.to_datetime(snap.date);meta=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str,'hydrologic_unit_code':str}).set_index('station_id');flagged_by_site={};removed=0;excluded=0;unchanged=0
 for site in sorted(initial.station_id.unique()):
  with gzip.open(DATA/'raw'/(site+'.json.gz'),'rt') as f:doc=json.load(f)
  flags=set()
  for item in doc['features']:
   r=item.get('properties',item);t=str(r['time']);v=pd.Timestamp(t)
   if len(t)!=10 and v.tzinfo is not None:v=v.tz_convert(meta.loc[site,'native_zone']).tz_localize(None)
   if not blank(r.get('qualifier')):flags.add(v.normalize())
  d=pd.read_parquet(DATA/'daily'/(site+'.parquet'));d['date']=pd.to_datetime(d.date);before={x.date:(float(x.water_c) if bool(x.reported) and not bool(x.unapproved) and not bool(x.ambiguous) and not bool(x.estimated) and pd.notna(x.water_c) and np.isfinite(x.water_c) else np.nan) for x in d.itertuples(index=False)}
  after={day:(np.nan if day in flags else value) for day,value in before.items()};s=snap[snap.station_id.eq(site)].set_index('date').water_c
  if set(s.index)!=set(after) or not np.allclose(s.reindex(sorted(after)).to_numpy(float),np.asarray([after[k] for k in sorted(after)]),atol=1e-12,rtol=0,equal_nan=True):raise AssertionError('Strict daily snapshot differs')
  flagged_by_site[site]=len(flags)
  for r in initial[initial.station_id.eq(site)].itertuples(index=False):
   expected=final[final.station_id.eq(site)&final.year.eq(r.year)]
   if len(expected)!=1:raise ValueError('Target roster mismatch')
   expected=expected.iloc[0];kept=[];gone=[];complete=0
   for year in map(int,r.history_years.split(';')):
    idx=pd.date_range(f'{year}-01-01',f'{year}-12-31');a=np.asarray([before.get(t,np.nan) for t in idx],float);b=np.asarray([after.get(t,np.nan) for t in idx],float);keep=qualifies(b)
    if keep:kept.append(year);complete+=int(np.isfinite(b).all())
    else:gone.append(year)
    count=int((np.isfinite(a)&~np.isfinite(b)).sum());removed+=count;excluded+=not keep
    z=details[details.station_id.eq(site)&details.target_year.eq(r.year)&details.history_year.eq(year)]
    if len(z)!=1:raise ValueError('History detail missing')
    z=z.iloc[0];checks={'before_usable_days':np.isfinite(a).sum(),'after_usable_days':np.isfinite(b).sum(),'removed_qualified_days':count,'original_history_complete':np.isfinite(a).all(),'qualifier_aware_history_complete':np.isfinite(b).all(),'retained':keep}
    if any(z[k]!=v for k,v in checks.items()):raise AssertionError('History qualification differs')
   target=np.asarray([after.get(t,np.nan) for t in pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')],float);same=';'.join(map(str,kept))==r.history_years;unchanged+=same
   checks={'history_years':';'.join(map(str,kept)),'excluded_history_years':';'.join(map(str,gone)),'eligible_histories':len(kept),'complete_history_years':complete,'target_daily_complete':bool(np.isfinite(target).all()),'eligible_partial_history':bool(np.isfinite(target).all() and len(kept)>=3),'huc2':str(meta.loc[site,'hydrologic_unit_code'])[:2]}
   if any(expected[k]!=v for k,v in checks.items()):raise AssertionError('Alternative roster differs')
 if removed!=status['history_assignment_flagged_days_removed'] or excluded!=status['history_year_assignments_excluded']:raise AssertionError('Aggregate mismatch')
 result={'status':'passed','targets':len(initial),'sites':initial.station_id.nunique(),'unchanged_history_targets':int(unchanged),'history_assignments_removed':int(excluded),'repeated_assignment_qualified_days_removed':int(removed),
   'source_daily_nonblank_qualifier_dates_by_site':flagged_by_site,'scope':'Independent raw-qualifier date extraction, scalar gap-run test, strict daily snapshot, original target preservation and source metadata checks.',
   'limitations':plan['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'qualifier_aware_history_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
