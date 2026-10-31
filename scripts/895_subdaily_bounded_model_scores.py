#!/usr/bin/env python3
"""Score saved predictions against conditional subdaily H30 enclosures."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
METHODS={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
def freeze():
 path=STAGE/'subdaily_bounded_score_plan.json'
 if path.exists():raise FileExistsError('Preserve scoring plan')
 for name in ['subdaily_h30_bounds_independent_audit.json','score_independent_audit.json','prediction_replay_status.json']:
  if json.loads((STAGE/name).read_text())['status']!='passed':raise ValueError('Prior audit incomplete')
 files=[STAGE/'subdaily_h30_bounds_plan.json',STAGE/'subdaily_h30_bounds_status.json',STAGE/'subdaily_h30_bounds_years.csv',STAGE/'subdaily_h30_bounds_independent_audit.json',
   STAGE/'scored_cases.parquet',STAGE/'score_status.json',STAGE/'score_independent_audit.json',STAGE/'prediction_replay_status.json',Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after target daily scores, continuous observations, target H30 bounds and prior masks were examined; before this interval-censored subdaily scoring',
  'cohort':'All eight fixed years, 144 previously fixed masks and three available methods, evaluated under fixed-standard and native-civil clocks. Also report the already seen three-year fixed-standard full-hour subset and one full-quarter year; all such years are one station.',
  'reference':'Conditional H30 interval from clean subdaily quarter-hour slots, with each unobserved or invalid slot assumed in [-5,50] C. The exact physical bound and actual site day convention are not established. Compare models originally fitted on reported USGS daily means without pretending the reported and continuous estimands are identical.',
  'metrics':'For point p and [L,U], absolute-error lower=max(L-p,0,p-U), upper=max(|p-L|,|p-U|). Predictive interval definite coverage contains [L,U], possible coverage intersects it. Interval-score lower uses distance between predictive and reference intervals; upper is the larger score at L or U. For paired absolute-error differences use extrema at endpoints and clipped predictions. Average per-case extrema is conservative because masks share annual H30.',
  'measurement_discrepancy':'Count cases where the published-daily observed lower bound exceeds the subdaily conditional upper bound. Such cases indicate incompatibility of reporting estimands or assumptions, not evidence of hidden target leakage; do not apply an artificial projection.',
  'limitations':'Posthoc, previously opened sites and target scores, unknown actual missing-value range, clock, corrections, sensor accuracy, source overlap and independence. Model histories use interpolation and only 0-2 genuinely complete years. Repeated masks and the one-station 3-year subgroup do not give independent-climate accuracy or coverage guarantees.',
  }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen posthoc subdaily interval scoring')
def interval_error(x,l,u):return np.maximum.reduce([l-x,np.zeros_like(x),x-u]),np.maximum(np.abs(x-l),np.abs(x-u))
def difference_bounds(x,y,l,u):
 knots=np.stack([l,u,np.clip(x,l,u),np.clip(y,l,u)],axis=1);d=np.abs(x[:,None]-knots)-np.abs(y[:,None]-knots);return d.min(axis=1),d.max(axis=1)
def run():
 p=json.loads((STAGE/'subdaily_bounded_score_plan.json').read_text())
 cases=pd.read_parquet(STAGE/'scored_cases.parquet');bounds=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str});table=[];pairs=[];detail=[]
 for clock in ['fixed_standard','native_civil']:
  b=bounds[bounds.clock.eq(clock)][['station_id','year','h30_lower_c','h30_upper_c','h30_interval_width_c']]
  c=cases.merge(b,on=['station_id','year'],how='left',validate='many_to_one');l=c.h30_lower_c.to_numpy(float);u=c.h30_upper_c.to_numpy(float)
  if not np.isfinite(l).all() or not np.isfinite(u).all() or np.any(l>u+1e-10):raise ValueError('Missing H30 enclosure')
  common=np.logical_and.reduce([np.isfinite(pd.to_numeric(c[col],errors='coerce')) for col in METHODS.values()]);c['continuous_clock']=clock;c['continuous_common']=common
  diffbound=c.observed_lower_bound__observed_days.to_numpy(float)-u;c['published_bound_above_continuous_upper']=np.isfinite(diffbound)&(diffbound>1e-9)
  for label,selection in [('all',np.ones(len(c),bool)),('fixed_standard_full_hour_posthoc',c.hourly_reference_posthoc.to_numpy(bool)),('fixed_standard_full_quarter_posthoc',c.quarter_reference_posthoc.to_numpy(bool))]:
   z=c.loc[selection];g=z[z.continuous_common];L=g.h30_lower_c.to_numpy(float);U=g.h30_upper_c.to_numpy(float)
   for name,col in METHODS.items():
    x=g[col].to_numpy(float);lower,upper=interval_error(x,L,U);row={'clock':clock,'cohort':label,'method':name,'cases':len(z),'common_cases':len(g),'sites':g.station_id.nunique(),'station_years':len(g[['station_id','year']].drop_duplicates()),
      'mae_lower_c':float(lower.mean()),'mae_upper_c':float(upper.mean()),'bias_lower_c':float((x-U).mean()),'bias_upper_c':float((x-L).mean()),
      'failure_rate_definite':float((lower>.5).mean()),'failure_rate_possible':float((upper>.5).mean()),
      'published_bound_above_continuous_upper_cases':int(g.published_bound_above_continuous_upper.sum())}
    if name!='plug_in':
     prefix='D2' if name=='D2' else 'stochastic_cal';ql=g[prefix+'_q05'].to_numpy(float);qu=g[prefix+'_q95'].to_numpy(float);valid=np.isfinite(ql)&np.isfinite(qu)
     if np.any(valid&(ql>qu)):raise ValueError('Unordered predicted interval')
     ql=ql[valid];qu=qu[valid];LL=L[valid];UU=U[valid];width=qu-ql
     sl=width+20*np.maximum.reduce([ql-UU,LL-qu,np.zeros_like(LL)])
     su=np.maximum(width+20*np.maximum(ql-LL,0)+20*np.maximum(LL-qu,0),width+20*np.maximum(ql-UU,0)+20*np.maximum(UU-qu,0))
     row.update(interval_cases=int(valid.sum()),coverage_definite=float(((ql<=LL)&(qu>=UU)).mean()),coverage_possible=float(((ql<=UU)&(qu>=LL)).mean()),
       width90=float(width.mean()),interval_score_lower=float(sl.mean()),interval_score_upper=float(su.mean()))
    table.append(row)
   if len(g):
    x=g.D2.to_numpy(float)
    for comp in ['plug_in','stochastic']:
     y=g[METHODS[comp]].to_numpy(float);low,high=difference_bounds(x,y,L,U);pairs.append({'clock':clock,'cohort':label,'contrast':'D2_minus_'+comp,'common_cases':len(g),
       'mae_difference_lower_c':float(low.mean()),'mae_difference_upper_c':float(high.mean())})
  detail.append(c)
 summary=pd.DataFrame(table);paired=pd.DataFrame(pairs);summary.to_csv(STAGE/'subdaily_bounded_score_summary.csv',index=False);paired.to_csv(STAGE/'subdaily_bounded_score_pairs.csv',index=False);pd.concat(detail,ignore_index=True).to_parquet(STAGE/'subdaily_bounded_score_cases.parquet',index=False)
 status={'status':'completed_posthoc_conditional_subdaily_scoring','cases_per_clock':len(cases),'clocks':2,'summary_rows':len(summary),'paired_rows':len(paired),
  'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'subdaily_bounded_score_status.json').write_text(json.dumps(status,indent=2)+'\n');print(summary.to_string(index=False));print(paired.to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
