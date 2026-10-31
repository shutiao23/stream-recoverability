#!/usr/bin/env python3
"""Post-hoc floating-point coverage sensitivity for historical source fits."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');S=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
CASES=ROOT/'private/wrr_review_case_evidence_20261027/annual_source_cases';SCORES=ROOT/'results/wrr_review_response_20261027/annual';PLAN=S/'single_year_coverage_numeric_plan.json'
def inputs():
 return [*(CASES/f'seed_{i:02d}.parquet' for i in range(20)),*(SCORES/f'seed_{i:02d}.csv' for i in range(20)),SCORES/'source_scorecard_summary.csv',ROOT/'scripts/528_review_response_annual.py',ROOT/'scripts/576_verify_private_annual_predictions.py',Path(__file__)]
def freeze():
 if PLAN.exists():raise FileExistsError('Preserve frozen plan')
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after USGS and whole-archive numerical boundary analyses, prior to reading single-year coverage sensitivity results',
 'scope':'All twenty saved single-year source repetitions, both families, both strata and both estimators. Reproduce the method-specific 1e-8 C coverage saved per seed and its median for crossed danger; compare strict and 1e-10 C comparisons on the same cases and support-projected quantile endpoints.',
 'availability':'Replicate the original per-method valid point, finite reference and all-seven-finite quantile mask, including cases whose observed lower bound is unavailable. Do not compare different case cohorts as a paired method effect.',
 'limitations':'Repeated masks and seeds use the same archive and are not independent climates. A machine-scale numerical comparison tolerance is not physical sensor uncertainty, recalibration, a new model, or a coverage guarantee. This uses saved predictions and truths, not independent reconstruction.',
 }
 PLAN.write_text(json.dumps(p,indent=2)+'\n');print('Plan frozen',flush=True)
def run():
 plan=json.loads(PLAN.read_text())
 levels=[5,10,25,50,75,90,95];columns=['design_family','peak_overlap','eval_truth_h30','observed_lower_bound__observed_days','D2']+[f'{p}_q{q:02d}' for p in ('D2','stochastic_cal') for q in levels];rows=[];gap_max=0.;gap_count=0;gap_above=0
 for seed in range(20):
  d=pd.read_parquet(CASES/f'seed_{seed:02d}.parquet',columns=columns);saved=pd.read_csv(SCORES/f'seed_{seed:02d}.csv')
  for family in ('calendar','crossed'):
   for stratum in ('all','danger'):
    chosen=d.design_family.eq(family)
    if stratum=='danger':chosen &= d.peak_overlap.ge(.5)
    block=d.loc[chosen];y=block.eval_truth_h30.to_numpy(float);bound=block.observed_lower_bound__observed_days.to_numpy(float)
    for prefix,name,pointcol in [('D2','distribution_regression','D2'),('stochastic_cal','stochastic_regression_calibrated','stochastic_cal_q50')]:
     point=block[pointcol].to_numpy(float);point=np.where(np.isfinite(bound),np.maximum(point,bound),point);q=block[[f'{prefix}_q{v:02d}' for v in levels]].to_numpy(float)
     valid=np.isfinite(point)&np.isfinite(y);good=valid&np.isfinite(q).all(axis=1);y0=y[good];b0=bound[good];q0=q[good];q0=np.where(np.isfinite(b0[:,None]),np.maximum(q0,b0[:,None]),q0);low=q0[:,0];high=q0[:,-1]
     def cov(e):return (y0>=low-e)&(y0<=high+e)
     a,b,c=cov(0),cov(1e-10),cov(1e-8);flag=(a!=b);gaps=np.maximum.reduce([low[flag]-y0[flag],y0[flag]-high[flag],np.zeros(flag.sum())]);gap_count+=int(flag.sum());gap_above+=int((gaps>1e-12).sum());gap_max=max(gap_max,float(gaps.max()) if gaps.size else 0.)
     x=saved[(saved.family==family)&(saved.stratum==stratum)&(saved.estimator==name)]
     if len(x)!=1 or int(x.iloc[0]['n'])!=int(valid.sum()) or not np.isclose(x.iloc[0].coverage90,c.mean(),atol=1e-12,rtol=0):raise AssertionError(f'Saved mismatch {seed} {family} {stratum} {name}')
     rows.append(dict(seed=seed,family=family,stratum=stratum,estimator=name,n_candidates=len(block),n_point_valid=int(valid.sum()),n_interval_valid=len(y0),exact_covered=int(a.sum()),tolerance_1e10_covered=int(b.sum()),tolerance_1e8_covered=int(c.sum()),exact_to_1e10_changed=int(flag.sum()),one10_to_one8_changed=int((b!=c).sum()),coverage_exact=float(a.mean()),coverage_1e10=float(b.mean()),coverage_1e8=float(c.mean()),saved_coverage_reproduced=True))
  print(f'Checked seed {seed+1}/20',flush=True)
 table=pd.DataFrame(rows);summary=[];stored=pd.read_csv(SCORES/'source_scorecard_summary.csv')
 for (family,stratum,estimator),g in table.groupby(['family','stratum','estimator']):
  old=stored[(stored.family==family)&(stored.stratum==stratum)&(stored.estimator==estimator)]
  if len(old)!=1 or not np.isclose(old.iloc[0].coverage90_median,g.coverage_1e8.median(),atol=1e-12,rtol=0):raise AssertionError('Median does not reproduce original')
  summary.append(dict(family=family,stratum=stratum,estimator=estimator,seeds=len(g),exact_median=float(g.coverage_exact.median()),tolerance_1e10_median=float(g.coverage_1e10.median()),tolerance_1e8_median=float(g.coverage_1e8.median()),max_1e10_to_1e8_changed=int(g.one10_to_one8_changed.max()),saved_median_reproduced=True))
 f=S/'single_year_coverage_numeric_seeds.csv';g=S/'single_year_coverage_numeric_summary.csv';table.to_csv(f,index=False);pd.DataFrame(summary).to_csv(g,index=False)
 result={'status':'passed_posthoc_sensitivity','seed_repetitions':20,'method_family_stratum_seed_cells':len(table),'summary_cells':len(summary),'saved_coverage_and_median_reproduced':True,'strict_to_1e10_changes_count_with_overlapping_strata':gap_count,'changed_endpoint_max_c':gap_max,'changed_endpoint_gaps_above_1e12_c':gap_above,'max_1e10_to_1e8_changed_per_cell':int(table.one10_to_one8_changed.max()),'limitations':plan['limitations'],'storage':'temporary RAM; not durable'}
 (S/'single_year_coverage_numeric_status.json').write_text(json.dumps(result,indent=2)+'\n');print(pd.DataFrame(summary).to_string(index=False));print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);arg=a.parse_args();freeze() if arg.action=='freeze' else run()
