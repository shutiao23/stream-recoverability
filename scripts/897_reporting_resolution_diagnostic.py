#!/usr/bin/env python3
"""Diagnose published-day versus subdaily H30 interval disagreements."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def freeze():
 path=STAGE/'reporting_resolution_plan.json'
 if path.exists():raise FileExistsError('Preserve reporting-resolution plan')
 for n in ['subdaily_h30_bounds_independent_audit.json','subdaily_bounded_score_independent_audit.json']:
  if json.loads((STAGE/n).read_text())['status']!='passed':raise ValueError('Prior bound or score audit incomplete')
 files=[STAGE/'subdaily_bounded_score_cases.parquet',STAGE/'subdaily_bounded_score_status.json',STAGE/'subdaily_bounded_score_independent_audit.json',STAGE/'subdaily_h30_bounds_independent_audit.json',Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after daily and subdaily interval coverages and cross-representation bound mismatches were examined',
  'cohort':'All 144 fixed cases for each clock and the previously identified 54 full-hour and 18 full-quarter cases; all selected support subgroups are posthoc and come from one station.',
  'diagnostics':'For each predictive method distinguish daily-reference coverage, definite/possible continuous-reference coverage, changes from reported-covered to continuous-definitely-uncovered, published lower bounds above continuous upper H30, and whether q05 equals the published lower bound. Record absolute gap sizes and counts <=0.01, <=0.05 and <=0.1 C.',
  'tolerance':'Counts of non-overlap distances within fixed 0.01, 0.05 and 0.1 C are descriptive numerical sensitivities chosen after inspecting results. They are not sensor error estimates, revised predictions, calibration procedures or guarantees.',
  'limits':'The daily and equally weighted 15-minute targets differ in rounding, reporting-day convention and possible corrections. All subdaily enclosures assume unknown values in [-5,50] C. Physical accuracy, source overlap and independent climate are unverified; repeated masks share station-year outcomes.',
  }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen posthoc reporting-resolution diagnostic')
def run():
 p=json.loads((STAGE/'reporting_resolution_plan.json').read_text())
 c=pd.read_parquet(STAGE/'subdaily_bounded_score_cases.parquet');rows=[]
 for clock in ['fixed_standard','native_civil']:
  base=c[c.continuous_clock.eq(clock)]
  for cohort,mask in [('all',np.ones(len(base),bool)),('fixed_standard_full_hour_posthoc',base.hourly_reference_posthoc.to_numpy(bool)),('fixed_standard_full_quarter_posthoc',base.quarter_reference_posthoc.to_numpy(bool))]:
   z=base.loc[mask & base.continuous_common.to_numpy(bool)];L=z.h30_lower_c.to_numpy(float);U=z.h30_upper_c.to_numpy(float);reported=z.reference_h30.to_numpy(float);obs=z.observed_lower_bound__observed_days.to_numpy(float);mismatch=np.isfinite(obs)&(obs>U+1e-9);gap=obs[mismatch]-U[mismatch]
   for name,prefix in [('D2','D2'),('stochastic','stochastic_cal')]:
    lo=z[prefix+'_q05'].to_numpy(float);hi=z[prefix+'_q95'].to_numpy(float);valid=np.isfinite(lo)&np.isfinite(hi);daily=valid&(lo<=reported)&(hi>=reported);possible=valid&(lo<=U)&(hi>=L);definite=valid&(lo<=L)&(hi>=U);distance=np.maximum.reduce([lo-U,L-hi,np.zeros(len(z))]);miss=valid&~possible
    qbound=np.isfinite(obs)&np.isclose(lo,obs,atol=1e-9,rtol=0)
    row={'clock':clock,'cohort':cohort,'method':name,'cases':len(z),'finite_intervals':int(valid.sum()),'daily_reference_covered':int(daily.sum()),
      'continuous_definite_cover':int(definite.sum()),'continuous_possible_cover':int(possible.sum()),'daily_covered_continuous_definitely_missed':int((daily&miss).sum()),
      'published_bound_above_continuous_upper':int(mismatch.sum()),'mismatch_station_years':len(z.loc[mismatch,['station_id','year']].drop_duplicates()),
      'mismatch_q05_equals_published_bound':int((mismatch&qbound).sum()),'mismatch_gap_median_c':float(np.median(gap)) if len(gap) else None,'mismatch_gap_max_c':float(np.max(gap)) if len(gap) else None,
      'mismatch_gap_le_0_01_c':int((gap<=.01+1e-12).sum()),'mismatch_gap_le_0_05_c':int((gap<=.05+1e-12).sum()),
      'continuous_nonoverlap_cases':int(miss.sum()),'nonoverlap_distance_le_0_01_c':int((miss&(distance<=.01+1e-12)).sum()),
      'nonoverlap_distance_le_0_05_c':int((miss&(distance<=.05+1e-12)).sum()),'nonoverlap_distance_le_0_1_c':int((miss&(distance<=.1+1e-12)).sum()),
      'max_nonoverlap_distance_c':float(np.max(distance[miss])) if miss.any() else None}
    rows.append(row)
 table=pd.DataFrame(rows);dest=STAGE/'reporting_resolution_summary.csv';table.to_csv(dest,index=False)
 out={'status':'completed_posthoc_reporting_resolution_diagnostic','rows':len(table),'limits':p['limits']+' '+p['tolerance'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'reporting_resolution_status.json').write_text(json.dumps(out,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
