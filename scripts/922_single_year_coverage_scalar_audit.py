#!/usr/bin/env python3
"""Independent scalar audit of single-year source coverage comparisons."""
from pathlib import Path
import collections,json,math
import pandas as pd,pyarrow.parquet as pq
R=Path('/home/lzq/workspace/parttime/stream-recoverability');S=Path('/dev/shm/wrr_usgs_partial_daily_20261027');C=R/'private/wrr_review_case_evidence_20261027/annual_source_cases'
plan=json.loads((S/'single_year_coverage_numeric_plan.json').read_text())
levels=(5,10,25,50,75,90,95);cols=['design_family','peak_overlap','eval_truth_h30','observed_lower_bound__observed_days','D2']+[f'{p}_q{q:02d}' for p in ('D2','stochastic_cal') for q in levels]
saved=pd.read_csv(S/'single_year_coverage_numeric_seeds.csv').to_dict('records');counts=collections.defaultdict(lambda:collections.Counter());large_gaps=[];strict_gaps=[];large_detail=[]
for seed in range(20):
 pf=pq.ParquetFile(C/f'seed_{seed:02d}.parquet')
 for rb in pf.iter_batches(batch_size=16384,columns=cols):
  d=rb.to_pydict()
  for i in range(rb.num_rows):
   family=d['design_family'][i];y=d['eval_truth_h30'][i];bound=d['observed_lower_bound__observed_days'][i];peak=d['peak_overlap'][i]
   if family not in ('calendar','crossed'):continue
   strata=['all']+(['danger'] if peak is not None and math.isfinite(peak) and peak>=.5 else [])
   y=float(y) if y is not None else math.nan;bound=float(bound) if bound is not None else math.nan
   for prefix,method,pointcol in [('D2','distribution_regression','D2'),('stochastic_cal','stochastic_regression_calibrated','stochastic_cal_q50')]:
    p=d[pointcol][i];p=float(p) if p is not None else math.nan;qs=[d[f'{prefix}_q{q:02d}'][i] for q in levels]
    valid=math.isfinite(y) and math.isfinite(p);good=valid and all(x is not None and math.isfinite(x) for x in qs)
    if good:
     lo,hi=float(qs[0]),float(qs[-1])
     if math.isfinite(bound):lo=max(lo,bound);hi=max(hi,bound)
     c0=lo<=y<=hi;c1=lo-1e-10<=y<=hi+1e-10;c8=lo-1e-8<=y<=hi+1e-8
     if c0!=c1:strict_gaps.append(max(lo-y,y-hi,0.0))
     if c1!=c8:
      gap=max(lo-y,y-hi,0.0);large_gaps.append(gap);large_detail.append({'seed':seed,'family':family,'method':method,'gap_c':gap,'stratum':'danger' if 'danger' in strata else 'non-danger'})
    for stratum in strata:
     c=counts[(seed,family,stratum,method)];c['n_candidates']+=1;c['n_point_valid']+=valid
     if good:
      c['n_interval_valid']+=1;c['exact_covered']+=c0;c['tolerance_1e10_covered']+=c1;c['tolerance_1e8_covered']+=c8;c['exact_to_1e10_changed']+=c0!=c1;c['one10_to_one8_changed']+=c1!=c8
 print('Independent scalar seed',seed+1,'of 20',flush=True)
fields=['n_candidates','n_point_valid','n_interval_valid','exact_covered','tolerance_1e10_covered','tolerance_1e8_covered','exact_to_1e10_changed','one10_to_one8_changed']
for r in saved:
 key=(r['seed'],r['family'],r['stratum'],r['estimator']);c=counts[key]
 for f in fields:
  if c[f]!=r[f]:raise AssertionError((key,f,c[f],r[f]))
result={'status':'passed','seed_repetitions':20,'seed_family_stratum_method_cells':len(saved),'checked_count_fields_per_cell':len(fields),'strict_to_1e10_unique_family_method_cases':len(strict_gaps),'strict_changed_max_endpoint_gap_c':max(strict_gaps) if strict_gaps else 0,'strict_changed_gaps_above_1e12':sum(x>1e-12 for x in strict_gaps),'one10_to_one8_unique_family_method_cases':len(large_gaps),'one10_to_one8_min_gap_c':min(large_gaps) if large_gaps else None,'one10_to_one8_max_gap_c':max(large_gaps) if large_gaps else None,'one10_to_one8_cases_in_danger_stratum':sum(x['stratum']=='danger' for x in large_detail),'one10_to_one8_by_family_method':dict(collections.Counter(x['family']+'|'+x['method'] for x in large_detail)),
 'scope':'Independent scalar replay of finite masks, bound projection and endpoint comparisons for all 160 cells using saved source outputs. Cases repeat across seeds and masks; no independent raw-reference reconstruction.',
 'limitations':plan['limitations'],'storage':'temporary RAM; not durable'}
(S/'single_year_coverage_scalar_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
