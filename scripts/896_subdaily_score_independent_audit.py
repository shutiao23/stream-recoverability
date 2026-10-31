#!/usr/bin/env python3
"""Independently recheck bounded subdaily error and interval-score formulas."""
import json,math
from pathlib import Path
import numpy as np,pandas as pd
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');METHODS={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}
def main():
 p=json.loads((STAGE/'subdaily_bounded_score_plan.json').read_text());status=json.loads((STAGE/'subdaily_bounded_score_status.json').read_text())
 c=pd.read_parquet(STAGE/'subdaily_bounded_score_cases.parquet');bounds=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str}).set_index(['station_id','year','clock']);summary=pd.read_csv(STAGE/'subdaily_bounded_score_summary.csv');paired=pd.read_csv(STAGE/'subdaily_bounded_score_pairs.csv');measure=[];contrast=[]
 for r in c.itertuples(index=False):
  b=bounds.loc[(r.station_id,r.year,r.continuous_clock)];L=float(b.h30_lower_c);U=float(b.h30_upper_c)
  if not math.isclose(L,r.h30_lower_c,abs_tol=1e-10) or not math.isclose(U,r.h30_upper_c,abs_tol=1e-10):raise AssertionError('Reference join differs')
  predictions={n:float(getattr(r,col)) for n,col in METHODS.items()}
  if not all(math.isfinite(x) for x in predictions.values()):continue
  condition={'all':True,'fixed_standard_full_hour_posthoc':bool(r.hourly_reference_posthoc),'fixed_standard_full_quarter_posthoc':bool(r.quarter_reference_posthoc)}
  obs=float(r.observed_lower_bound__observed_days);contradiction=math.isfinite(obs) and obs>U+1e-9
  if contradiction!=bool(r.published_bound_above_continuous_upper):raise AssertionError('Cross-representation bound diagnostic differs')
  for cohort,include in condition.items():
   if not include:continue
   for name,x in predictions.items():
    error_low=0. if L<=x<=U else min(abs(x-L),abs(x-U));error_high=max(abs(x-L),abs(x-U))
    a={'clock':r.continuous_clock,'cohort':cohort,'method':name,'station_id':r.station_id,'year':r.year,'error_low':error_low,'error_high':error_high,'bias_low':x-U,'bias_high':x-L,'definite_failure':error_low>.5,'possible_failure':error_high>.5,'bound_mismatch':contradiction}
    if name!='plug_in':
     prefix='D2' if name=='D2' else 'stochastic_cal';qlo=float(getattr(r,prefix+'_q05'));qhi=float(getattr(r,prefix+'_q95'));valid=math.isfinite(qlo) and math.isfinite(qhi)
     if valid:
      if qlo>qhi:raise AssertionError('Unordered interval')
      width=qhi-qlo
      def score(y):return width+20*max(qlo-y,0)+20*max(y-qhi,0)
      knots=[L,U,min(max(qlo,L),U),min(max(qhi,L),U)];a.update(interval_cases=1,definite_cover=qlo<=L and qhi>=U,possible_cover=qlo<=U and qhi>=L,width=width,score_low=min(score(y) for y in knots),score_high=max(score(L),score(U)))
    measure.append(a)
   x=predictions['D2']
   for other in ['plug_in','stochastic']:
    y=predictions[other];knots=[L,U,min(max(x,L),U),min(max(y,L),U)];vals=[abs(x-t)-abs(y-t) for t in knots];contrast.append({'clock':r.continuous_clock,'cohort':cohort,'contrast':'D2_minus_'+other,'low':min(vals),'high':max(vals)})
 m=pd.DataFrame(measure);d=pd.DataFrame(contrast)
 for row in summary.itertuples(index=False):
  z=m[m.clock.eq(row.clock)&m.cohort.eq(row.cohort)&m.method.eq(row.method)]
  checks={'cases':len(z),'common_cases':len(z),'sites':z.station_id.nunique(),'station_years':len(z[['station_id','year']].drop_duplicates()),'mae_lower_c':z.error_low.mean(),'mae_upper_c':z.error_high.mean(),'bias_lower_c':z.bias_low.mean(),'bias_upper_c':z.bias_high.mean(),
   'failure_rate_definite':z.definite_failure.mean(),'failure_rate_possible':z.possible_failure.mean(),'published_bound_above_continuous_upper_cases':z.bound_mismatch.sum()}
  if row.method!='plug_in':
   v=z[z.interval_cases.eq(1)];checks.update(interval_cases=len(v),coverage_definite=v.definite_cover.mean(),coverage_possible=v.possible_cover.mean(),width90=v.width.mean(),interval_score_lower=v.score_low.mean(),interval_score_upper=v.score_high.mean())
  for k,value in checks.items():
   if not np.isclose(value,getattr(row,k),atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Score mismatch '+row.clock+' '+row.cohort+' '+row.method+' '+k)
 for row in paired.itertuples(index=False):
  z=d[d.clock.eq(row.clock)&d.cohort.eq(row.cohort)&d.contrast.eq(row.contrast)]
  if len(z)!=row.common_cases or not np.isclose(z.low.mean(),row.mae_difference_lower_c,atol=1e-10,rtol=0) or not np.isclose(z.high.mean(),row.mae_difference_upper_c,atol=1e-10,rtol=0):raise AssertionError('Paired difference bounds differ')
 out={'status':'passed','case_clock_rows':len(c),'summary_cells':len(summary),'paired_cells':len(paired),'scope':'Independent scalar point-error, coverage, interval-score and paired-contrast bounds using the separately audited subdaily target enclosures.',
  'limitations':p['limitations']+' '+p['measurement_discrepancy'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'subdaily_bounded_score_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
