#!/usr/bin/env python3
"""Scalar independent audit of main annual machine-tolerance sensitivity."""
from pathlib import Path
import collections,json,math,statistics
import pandas as pd
R=Path('/home/lzq/workspace/parttime/stream-recoverability');S=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
source=R/'private/wrr_review_case_evidence_20261027/results/wrr_review_response_20261027/whole_archive/annual_case_evidence.parquet'
plan=json.loads((S/'main_coverage_numeric_corrected_plan.json').read_text())
a=pd.read_parquet(source).to_dict('records');table=pd.read_csv(S/'main_coverage_numeric_corrected_summary.csv').to_dict('records');acc=collections.defaultdict(lambda:collections.Counter());gaps=[];b_diffs=[];sides=collections.Counter()
for x in a:
 names=['reference_h30','observed_lower_bound__observed_days']+[f'{p}_q{q:02d}' for p in ('D2','stochastic_cal') for q in (5,10,25,50,75,90,95)]
 if not all(math.isfinite(float(x[n])) for n in names):continue
 y=float(x['reference_h30']);b=float(x['observed_lower_bound__observed_days']);stratum='bound_matches_reference' if y-b<=1e-8 else 'unobserved_peak_excess'
 for prefix,method in [('D2','D2'),('stochastic_cal','stochastic_calibrated')]:
  lo=float(x[prefix+'_q05']);hi=float(x[prefix+'_q95'])
  c0=lo<=y<=hi;c1=lo-1e-10<=y<=hi+1e-10;c8=lo-1e-8<=y<=hi+1e-8
  for label in ('all',stratum):
   c=acc[(x['family'],x['mode'],label,method)];c['n_cases']+=1;c['exact_covered']+=c0;c['tolerance_1e10_covered']+=c1;c['tolerance_1e8_covered']+=c8;c['exact_to_1e10_changed']+=c0!=c1;c['1e10_to_1e8_changed']+=c1!=c8
  if c0!=c1:
   gaps.append(max(lo-y,y-hi,0));b_diffs.append(abs(y-b));sides['below_lower' if y<lo else 'above_upper']+=1
for r in table:
 key=tuple(r[k] for k in ('family','mode','stratum','method'));c=acc[key]
 for k in ('n_cases','exact_covered','tolerance_1e10_covered','tolerance_1e8_covered','exact_to_1e10_changed','1e10_to_1e8_changed'):
  if c[k]!=r[k]:raise AssertionError((key,k,c[k],r[k]))
result={'status':'passed','input_case_rows':len(a),'summary_cells':len(table),'scalar_checked_counts':6,'all_strata_comparisons_changed':len(gaps),
 'changed_case_endpoint_gap_max_c':max(gaps) if gaps else 0,'changed_case_endpoint_gap_median_c':statistics.median(gaps) if gaps else 0,
 'changed_case_gaps_above_1e12_c':sum(x>1e-12 for x in gaps),'changed_case_reference_bound_difference_max_c':max(b_diffs) if b_diffs else 0,
 'changed_case_endpoint_direction':dict(sides),'scope':'Independent scalar recomputation of pooled coverage for 24 preexisting post-hoc comparison cells and endpoint gaps. Repeated masked cases and methods are not independent station-years.',
 'limitations':plan['limits'],'storage':'temporary RAM; not durable'}
(S/'main_coverage_numeric_scalar_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
