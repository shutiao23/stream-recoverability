#!/usr/bin/env python3
"""Independently recompute fixed-mask qualifier-aware paired scores."""
import json,math
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');METHODS={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
def main():
 p=json.loads((STAGE/'qualifier_aware_score_plan.json').read_text());s=json.loads((STAGE/'qualifier_aware_score_status.json').read_text());cor=json.loads((STAGE/'qualifier_aware_pairs_correction.json').read_text())
 if cor['status']!='corrected_duplicate_summary_rows':raise ValueError('Paired summary correction missing')
 c=pd.read_parquet(STAGE/'qualifier_aware_scored_cases.parquet');bounds=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str}).set_index(['station_id','year','clock']);roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});qual=pd.read_csv(STAGE/'qualifier_aware_roster_v2.csv',dtype={'station_id':str}).fillna('');truth={}
 for r in roster.itertuples(index=False):
  d=pd.read_parquet(DATA/'daily'/(r.station_id+'.parquet'));d.date=pd.to_datetime(d.date);d=d[d.date.dt.year.eq(r.year)].sort_values('date');idx=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
  if len(d)!=len(idx) or not np.array_equal(d.date.to_numpy(),idx.to_numpy()) or not np.isfinite(d.water_c).all():raise ValueError('Reference year incomplete')
  z=d.water_c.to_numpy(float);truth[(r.station_id,r.year)]=max(sum(z[i:i+30])/30 for i in range(len(z)-29))
 if len(c)!=144 or c.duplicated(['station_id','year','realization_id']).any():raise AssertionError('Case roster differs')
 summary=pd.read_csv(STAGE/'qualifier_aware_score_summary.csv');pairs=pd.read_csv(STAGE/'qualifier_aware_score_pairs_corrected.csv');yearly=pd.read_csv(STAGE/'qualifier_aware_score_by_year.csv',dtype={'station_id':str});metrics=[];diffs=[];boundary=[]
 for r in c.itertuples(index=False):
  independent_y=truth[(r.station_id,r.year)];y=float(r.reference_h30)
  if not np.isclose(independent_y,y,atol=1e-10,rtol=0) or r.mask_runs_old!=r.mask_runs_new or not np.isclose(r.observed_lower_bound__observed_days_old,r.observed_lower_bound__observed_days_new,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Truth, mask or visible bound changed')
  q=qual[qual.station_id.eq(r.station_id)&qual.year.eq(r.year)]
  if len(q)!=1:raise ValueError('Qualifier roster mismatch')
  history_unchanged=q.iloc[0].history_years==q.iloc[0].original_history_years
  for cohort,inc in [('all',True),('fixed_standard_full_hour_posthoc',bool(r.hourly_reference_posthoc))]:
   if not inc:continue
   for name,col in METHODS.items():
    old=float(getattr(r,col+'_old'));new=float(getattr(r,col+'_new'));diffs.append({'cohort':cohort,'method':name,'difference':abs(new-y)-abs(old-y)})
    for version,value,suffix in [('original',old,'old'),('qualifier_aware',new,'new')]:
     item={'reference':'reported_daily','clock':'reported','cohort':cohort,'history':version,'method':name,'station_id':r.station_id,'year':r.year,'abs_error':abs(value-y),'bias':value-y,'failure':abs(value-y)>.5}
     if name!='plug_in':
      pre='D2' if name=='D2' else 'stochastic_cal';lo=float(getattr(r,pre+'_q05_'+suffix));hi=float(getattr(r,pre+'_q95_'+suffix));item.update(interval=math.isfinite(lo) and math.isfinite(hi),cover=lo<=y<=hi,width=hi-lo,interval_score=hi-lo+20*max(lo-y,0)+20*max(y-hi,0))
      if cohort=='all':boundary.append({'method':name,'history':version,'changed':bool((lo<=y<=hi)!=(lo<=independent_y<=hi)),'truth_difference':abs(y-independent_y)})
     metrics.append(item)
   for clock in ['fixed_standard','native_civil']:
    b=bounds.loc[(r.station_id,r.year,clock)];L=float(b.h30_lower_c);U=float(b.h30_upper_c)
    for name,col in METHODS.items():
     for version,suffix in [('original','old'),('qualifier_aware','new')]:
      value=float(getattr(r,col+'_'+suffix));el=0. if L<=value<=U else min(abs(value-L),abs(value-U));eu=max(abs(value-L),abs(value-U));item={'reference':'conditional_subdaily','clock':clock,'cohort':cohort,'history':version,'method':name,'station_id':r.station_id,'year':r.year,'error_low':el,'error_high':eu}
      if name!='plug_in':
       pre='D2' if name=='D2' else 'stochastic_cal';lo=float(getattr(r,pre+'_q05_'+suffix));hi=float(getattr(r,pre+'_q95_'+suffix));item.update(interval=math.isfinite(lo) and math.isfinite(hi),cover_definite=lo<=L and hi>=U,cover_possible=lo<=U and hi>=L,width=hi-lo)
      metrics.append(item)
  if history_unchanged:
   fields=['h30__policy','D2','risk_score']+[f'D2_q{k:02d}' for k in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{k:02d}' for k in (5,10,25,50,75,90,95)]
   if any(not np.isclose(float(getattr(r,x+'_old')),float(getattr(r,x+'_new')),atol=1e-10,rtol=0,equal_nan=True) for x in fields):raise AssertionError('Unchanged history changed output')
 m=pd.DataFrame(metrics);d=pd.DataFrame(diffs)
 for r in summary.itertuples(index=False):
  z=m[(m.reference==r.reference)&(m.clock==r.clock)&(m.cohort==r.cohort)&(m.history==r.history)&(m.method==r.method)];checks={'cases':len(z),'sites':z.station_id.nunique(),'target_years':len(z[['station_id','year']].drop_duplicates())}
  if r.reference=='reported_daily':
   checks.update(mae_c=z.abs_error.mean(),bias_c=z.bias.mean(),failure_rate=z.failure.astype(float).mean())
   if r.method!='plug_in':
    zz=z[z.interval];checks.update(interval_cases=len(zz),coverage90=zz.cover.astype(float).mean(),width90_c=zz.width.mean(),interval_score90=zz.interval_score.mean())
  else:
   checks.update(mae_lower_c=z.error_low.mean(),mae_upper_c=z.error_high.mean())
   if r.method!='plug_in':
    zz=z[z.interval];checks.update(interval_cases=len(zz),coverage_definite=zz.cover_definite.astype(float).mean(),coverage_possible=zz.cover_possible.astype(float).mean(),width90_c=zz.width.mean())
  for k,v in checks.items():
   if not np.isclose(v,getattr(r,k),atol=1e-9,rtol=0,equal_nan=True):raise AssertionError('Summary mismatch: '+k+' '+str((r.reference,r.clock,r.cohort,r.history,r.method,v,getattr(r,k))))
 for r in pairs.itertuples(index=False):
  z=d[(d.cohort==r.cohort)&(d.method==r.method)]
  if len(z)!=r.cases or not np.isclose(z.difference.mean(),r.mean_MAE_change_c,atol=1e-10,rtol=0):raise AssertionError('Paired contrast differs')
 for r in yearly.itertuples(index=False):
  for version,col in [('original','original_mae'),('qualifier_aware','qualifier_aware_mae')]:
   z=m[(m.reference=='reported_daily')&(m.cohort=='all')&(m.history==version)&(m.method==r.method)&(m.station_id==r.station_id)&(m.year==r.year)]
   if len(z)!=r.cases or not np.isclose(z.abs_error.mean(),getattr(r,col),atol=1e-10,rtol=0):raise AssertionError('Year result differs')
 bd=pd.DataFrame(boundary);boundary_counts=bd.groupby(['method','history']).changed.sum().to_dict();boundary_counts={f'{k[0]}|{k[1]}':int(v) for k,v in boundary_counts.items()}
 out={'status':'passed','coverage_changes_under_independent_roundoff':boundary_counts,'max_H30_arithmetic_difference_c':float(bd.truth_difference.max()),'target_cases':len(c),'target_years':len(truth),'summary_cells':len(summary),'corrected_paired_cells':len(pairs),'year_method_cells':len(yearly),
  'scope':'Independent scalar reported and conditional subdaily score comparisons, fixed-mask identity, observed-bound consistency and unchanged-history prediction checks.',
  'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'qualifier_aware_score_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
