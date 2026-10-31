#!/usr/bin/env python3
"""Independently rederive all published-daily target scores and clock H30."""
import json,math
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';DATA=ROOT/'data/external/additional_usgs_observed';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def main():
 s=json.loads((STAGE/'score_status.json').read_text());p=json.loads((STAGE/'score_execution_plan.json').read_text())
 cases=pd.read_parquet(STAGE/'scored_cases.parquet');roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});q=pd.read_csv(STAGE/'continuous_qualification_years.csv',dtype={'station_id':str});fixed=q[q.clock.eq('fixed_standard')].set_index(['station_id','year']);civil=q[q.clock.eq('native_civil')].set_index(['station_id','year']);sub=pd.read_parquet(STAGE/'continuous_qualification_days.parquet');sub.day=pd.to_datetime(sub.day)
 refs={};peryear=[]
 for r in roster.itertuples(index=False):
  d=pd.read_parquet(DATA/'daily'/(r.station_id+'.parquet'));d['date']=pd.to_datetime(d.date);d=d[d.date.dt.year.eq(r.year)].sort_values('date');expected=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
  if len(d)!=len(expected) or not np.array_equal(d.date.to_numpy(),expected.to_numpy()) or not np.isfinite(d.water_c).all() or not d.reported.all() or d.unapproved.any() or d.ambiguous.any() or d.estimated.any():raise ValueError('Target quality mismatch')
  v=d.water_c.to_numpy(float);truth=max(sum(v[i:i+30])/30 for i in range(len(v)-29));refs[(r.station_id,r.year)]=truth
  g=cases[cases.station_id.eq(r.station_id)&cases.year.eq(r.year)]
  if len(g)!=18 or not np.allclose(g.reference_h30,truth,atol=1e-9,rtol=0):raise AssertionError('Target truth or cases differ')
  if bool(fixed.loc[(r.station_id,r.year)].hourly_complete_year)!=bool(g.hourly_reference_posthoc.iloc[0]):raise AssertionError('Hourly cohort differs')
  for row in g.itertuples(index=False):
   lower=float(row.observed_lower_bound__observed_days)
   if math.isfinite(lower) and lower>truth+1e-9 or row.D2<lower-1e-9 or row.D2_q05<lower-1e-9 or row.stochastic_cal_q05<lower-1e-9:raise AssertionError('Observed bound inconsistent')
  for clock,qual in [('fixed_standard',fixed),('native_civil',civil)]:
   if bool(qual.loc[(r.station_id,r.year)].quarter_complete_year):
    z=sub[sub.station_id.eq(r.station_id)&sub.year.eq(r.year)&sub.clock.eq(clock)].sort_values('day');x=z.subdaily_mean.to_numpy(float)
    if len(x)!=len(expected) or not np.isfinite(x).all():raise ValueError('Continuous reference incomplete')
    continuous=max(sum(x[i:i+30])/30 for i in range(len(x)-29));clocktable=pd.read_csv(STAGE/'reference_clock_comparison.csv',dtype={'station_id':str});v=clocktable[clocktable.station_id.eq(r.station_id)&clocktable.year.eq(r.year)].iloc[0]
    if not np.isclose(continuous,v[clock+'_continuous_h30'],atol=1e-10,rtol=0):raise AssertionError('Clock H30 differs')
  for name,col in [('plug_in','h30__policy'),('D2','D2'),('stochastic','stochastic_cal_q50')]:peryear.append({'station_id':r.station_id,'year':r.year,'method':name,'cases':len(g),'mae':float(np.mean([abs(float(v)-truth) for v in g[col]]))})
 saved=pd.read_csv(STAGE/'score_by_year.csv',dtype={'station_id':str}).sort_values(['station_id','year','method']).reset_index(drop=True);actual=pd.DataFrame(peryear).sort_values(['station_id','year','method']).reset_index(drop=True);pd.testing.assert_frame_equal(actual,saved,check_dtype=False,atol=1e-10,rtol=0)
 summary=pd.read_csv(STAGE/'score_summary.csv');paired=pd.read_csv(STAGE/'score_pairs.csv');methods={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
 for cohort,mask in [('all',np.ones(len(cases),bool)),('fixed_standard_full_hour_posthoc',cases.hourly_reference_posthoc.to_numpy(bool)),('fixed_standard_full_quarter_posthoc',cases.quarter_reference_posthoc.to_numpy(bool))]:
  g=cases.loc[mask].copy();common=np.logical_and.reduce([np.isfinite(pd.to_numeric(g[v],errors='coerce')) for v in methods.values()]);z=g.loc[common]
  for name,col in methods.items():
   row=summary[(summary.cohort==cohort)&(summary.method==name)].iloc[0];truth=z.reference_h30.to_numpy(float);v=z[col].to_numpy(float);err=v-truth
   checks={'cases':len(g),'available':np.isfinite(pd.to_numeric(g[col],errors='coerce')).sum(),'common_cases':len(z),'sites':z.station_id.nunique(),'station_years':len(z[['station_id','year']].drop_duplicates()),'mae':np.abs(err).mean(),'bias':err.mean(),'failure_rate':(np.abs(err)>.5).mean()}
   if name!='plug_in':
    prefix='D2' if name=='D2' else 'stochastic_cal';lo=z[prefix+'_q05'].to_numpy(float);hi=z[prefix+'_q95'].to_numpy(float);valid=np.isfinite(lo)&np.isfinite(hi);scores=[(b-a)+20*max(a-t,0)+20*max(t-b,0) for a,b,t in zip(lo[valid],hi[valid],truth[valid])];checks.update(interval_cases=int(valid.sum()),coverage90=((lo[valid]<=truth[valid])&(truth[valid]<=hi[valid])).mean(),width90=(hi[valid]-lo[valid]).mean(),interval_score90=np.mean(scores))
   for k,v in checks.items():
    if not np.isclose(v,row[k],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Summary differs: '+cohort+' '+name+' '+k)
  y=z.reference_h30.to_numpy(float);d=np.abs(z.D2.to_numpy(float)-y)
  for name in ['plug_in','stochastic']:
   row=paired[(paired.cohort==cohort)&(paired.contrast=='D2_minus_'+name)].iloc[0];val=np.mean(d-np.abs(z[methods[name]].to_numpy(float)-y))
   if len(z)!=row.common_cases or not np.isclose(val,row.mean_absolute_error_difference_c,atol=1e-10,rtol=0):raise AssertionError('Paired score differs')
 out={'status':'passed','sites':len(set(r.station_id for r in roster.itertuples(index=False))),'target_years':len(roster),'target_cases':len(cases),'score_cells_checked':len(summary),'paired_cells_checked':len(paired),'year_method_cells_checked':len(actual),
   'scope':'Independent arithmetic for approved daily H30, observed-bound constraints, all per-year and aggregate scores, paired differences and full-quarter two-clock H30.',
   'limitations':'Same source records and saved model predictions are used; source model not retrained, measurement/clock quality not proven and independent climates not established.','storage':'temporary RAM filesystem; not durable'}
 (STAGE/'score_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
