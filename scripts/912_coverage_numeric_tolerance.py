#!/usr/bin/env python3
"""Compare exact and machine-scale coverage checks under two H30 arithmetic paths."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');DATA=ROOT/'data/external/additional_usgs_observed';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');TOL=1e-10
def freeze():
 path=STAGE/'coverage_numeric_tolerance_plan.json'
 if path.exists():raise FileExistsError('Preserve numeric tolerance plan')
 if json.loads((STAGE/'qualifier_aware_score_independent_audit.json').read_text())['status']!='passed':raise ValueError('Independent score audit incomplete')
 score=STAGE/'qualifier_aware_scored_cases.parquet';bounds=STAGE/'subdaily_h30_bounds_years.csv';files=[score,bounds,STAGE/'qualifier_aware_score_independent_audit.json',STAGE/'qualifier_aware_score_status.json',Path(__file__)]
 c=pd.read_parquet(score)
 files += [DATA/'daily'/(str(site)+'.parquet') for site in sorted(c.station_id.unique())]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after an independent H30 arithmetic path revealed coverage changes at exact floating-point interval boundaries',
   'scope':'All 144 fixed target masks and both history versions; also the previously examined 54-hourly and 18-quarter-hour subsets. Check D2 and stochastic intervals against reported-daily H30 and both conditional subdaily clock targets.',
   'tolerance':'Use an absolute 1e-10 C tolerance only to identify machine-scale comparisons, not as sensor error or a revised prediction. Preserve exact reported results separately. For conditional reference [L,U], definite coverage is q05<=L+tol and q95>=U-tol; possible coverage is q05<=U+tol and q95>=L-tol.',
   'reference_arithmetic':'Independently compute reported H30 via scalar 30-day sums from the same saved daily series and check against saved H30 within 1e-10 C; compare exact and tolerant coverage under both arithmetic paths.',
   'threshold':'Separately count point errors >0.5 C and >0.5+tol C; this is numerical boundary sensitivity, not recalibration.',
   'limitations':'The tolerance was selected after seeing a floating-point artifact. It is not a physical error bound and does not resolve time, sensor, calibration or independence. Repeated masks are not independent station-years.',
   }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen floating-point coverage sensitivity')
def run():
 p=json.loads((STAGE/'coverage_numeric_tolerance_plan.json').read_text())
 c=pd.read_parquet(STAGE/'qualifier_aware_scored_cases.parquet');bounds=pd.read_csv(STAGE/'subdaily_h30_bounds_years.csv',dtype={'station_id':str});truth={}
 for (site,year),g in c.groupby(['station_id','year']):
  d=pd.read_parquet(DATA/'daily'/(site+'.parquet'));d.date=pd.to_datetime(d.date);d=d[d.date.dt.year.eq(year)].sort_values('date');x=d.water_c.to_numpy(float)
  if len(x) not in (365,366) or not np.isfinite(x).all():raise ValueError('Reported target incomplete')
  truth[(site,year)]=max(sum(x[i:i+30])/30 for i in range(len(x)-29))
 c['scalar_reference']=[truth[(r.station_id,r.year)] for r in c.itertuples(index=False)]
 if not np.allclose(c.scalar_reference,c.reference_h30,atol=TOL,rtol=0):raise AssertionError('Independent target differs beyond tolerance')
 summaries=[]
 for clock in ['fixed_standard','native_civil']:
  z=c.merge(bounds[bounds.clock.eq(clock)][['station_id','year','h30_lower_c','h30_upper_c']],on=['station_id','year'],validate='many_to_one')
  for cohort,mask in [('all',np.ones(len(z),bool)),('fixed_standard_full_hour_posthoc',z.hourly_reference_posthoc.to_numpy(bool)),('fixed_standard_full_quarter_posthoc',z.quarter_reference_posthoc.to_numpy(bool))]:
   g=z.loc[mask];L=g.h30_lower_c.to_numpy(float);U=g.h30_upper_c.to_numpy(float);reported=g.reference_h30.to_numpy(float);scalar=g.scalar_reference.to_numpy(float)
   for history,suffix in [('original','old'),('qualifier_aware','new')]:
    for name,prefix in [('D2','D2'),('stochastic','stochastic_cal')]:
     lo=g[prefix+'_q05_'+suffix].to_numpy(float);point=g[prefix+'_q50_'+suffix].to_numpy(float) if name=='stochastic' else g['D2_'+suffix].to_numpy(float);hi=g[prefix+'_q95_'+suffix].to_numpy(float);finite=np.isfinite(lo)&np.isfinite(hi)&np.isfinite(point);lo=lo[finite];point=point[finite];hi=hi[finite];l=L[finite];u=U[finite];y=reported[finite];s=scalar[finite]
     exact=(lo<=y)&(hi>=y);tol=(lo<=y+TOL)&(hi>=y-TOL);scalar_exact=(lo<=s)&(hi>=s);scalar_tol=(lo<=s+TOL)&(hi>=s-TOL)
     summaries.append({'clock':clock,'cohort':cohort,'history':history,'method':name,'cases':len(lo),'reported_exact_covered':int(exact.sum()),'reported_tolerant_covered':int(tol.sum()),
       'scalar_exact_covered':int(scalar_exact.sum()),'scalar_tolerant_covered':int(scalar_tol.sum()),'exact_arithmetic_changed_cases':int((exact!=scalar_exact).sum()),
       'tolerant_arithmetic_changed_cases':int((tol!=scalar_tol).sum()),'continuous_definite_exact':int(((lo<=l)&(hi>=u)).sum()),
       'continuous_definite_tolerant':int(((lo<=l+TOL)&(hi>=u-TOL)).sum()),'continuous_possible_exact':int(((lo<=u)&(hi>=l)).sum()),
       'continuous_possible_tolerant':int(((lo<=u+TOL)&(hi>=l-TOL)).sum()),'failure_exact':int((abs(point-y)>.5).sum()),'failure_with_numeric_tolerance':int((abs(point-y)>.5+TOL).sum())})
 table=pd.DataFrame(summaries);file=STAGE/'coverage_numeric_tolerance_summary.csv';table.to_csv(file,index=False)
 out={'status':'completed_posthoc_numeric_tolerance_sensitivity','tolerance_c':TOL,'target_cases':len(c),'summary_rows':len(table),
      'maximum_independent_vs_saved_H30_difference_c':float(np.max(abs(c.scalar_reference-c.reference_h30))),
      'max_exact_arithmetic_changed_cases':int(table.exact_arithmetic_changed_cases.max()),'max_tolerant_arithmetic_changed_cases':int(table.tolerant_arithmetic_changed_cases.max()),
      'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'coverage_numeric_tolerance_status.json').write_text(json.dumps(out,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
