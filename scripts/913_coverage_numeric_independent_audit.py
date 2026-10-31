#!/usr/bin/env python3
"""Scalar recheck of post-hoc exact and machine-tolerant interval counts."""
import json, math
from pathlib import Path
import pandas as pd
S=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
D=Path('/home/lzq/workspace/parttime/stream-recoverability/data/external/additional_usgs_observed/daily')
cases=pd.read_parquet(S/'qualifier_aware_scored_cases.parquet').to_dict('records')
bounds=pd.read_csv(S/'subdaily_h30_bounds_years.csv',dtype={'station_id':str}).to_dict('records')
table=pd.read_csv(S/'coverage_numeric_tolerance_summary.csv').to_dict('records')
truth={}
for site,year in {(str(c['station_id']),int(c['year'])) for c in cases}:
 d=pd.read_parquet(D/(site+'.parquet'));d.date=pd.to_datetime(d.date);v=d[d.date.dt.year.eq(year)].sort_values('date').water_c.tolist()
 truth[(site,year)]=max(sum(v[i:i+30])/30 for i in range(len(v)-29))
lookup={(r['station_id'],int(r['year']),r['clock']):r for r in bounds}
keys=['cases','reported_exact_covered','reported_tolerant_covered','scalar_exact_covered','scalar_tolerant_covered','exact_arithmetic_changed_cases','tolerant_arithmetic_changed_cases','continuous_definite_exact','continuous_definite_tolerant','continuous_possible_exact','continuous_possible_tolerant','failure_exact','failure_with_numeric_tolerance']
for r in table:
 counts={k:0 for k in keys}
 for c in cases:
  if r['cohort']=='fixed_standard_full_hour_posthoc' and not c['hourly_reference_posthoc']:continue
  if r['cohort']=='fixed_standard_full_quarter_posthoc' and not c['quarter_reference_posthoc']:continue
  suffix='old' if r['history']=='original' else 'new';prefix='D2' if r['method']=='D2' else 'stochastic_cal'
  lo=float(c[prefix+'_q05_'+suffix]);hi=float(c[prefix+'_q95_'+suffix]);p=float(c['D2_'+suffix] if r['method']=='D2' else c[prefix+'_q50_'+suffix])
  if not all(map(math.isfinite,(lo,hi,p))):continue
  b=lookup[(str(c['station_id']),int(c['year']),r['clock'])];L=float(b['h30_lower_c']);U=float(b['h30_upper_c']);y=float(c['reference_h30']);z=truth[(str(c['station_id']),int(c['year']))];t=1e-10
  cover=lambda x,e:lo<=x+e and x<=hi+e
  exact=cover(y,0);tol=cover(y,t);s_exact=cover(z,0);s_tol=cover(z,t)
  counts['cases']+=1;counts['reported_exact_covered']+=exact;counts['reported_tolerant_covered']+=tol;counts['scalar_exact_covered']+=s_exact;counts['scalar_tolerant_covered']+=s_tol
  counts['exact_arithmetic_changed_cases']+=exact!=s_exact;counts['tolerant_arithmetic_changed_cases']+=tol!=s_tol
  counts['continuous_definite_exact']+=lo<=L and hi>=U;counts['continuous_definite_tolerant']+=lo<=L+t and hi>=U-t
  counts['continuous_possible_exact']+=lo<=U and hi>=L;counts['continuous_possible_tolerant']+=lo<=U+t and hi>=L-t
  counts['failure_exact']+=abs(p-y)>.5;counts['failure_with_numeric_tolerance']+=abs(p-y)>.5+t
 for k in keys:
  if counts[k]!=r[k]:raise AssertionError((r['clock'],r['cohort'],r['history'],r['method'],k,counts[k],r[k]))
result={'status':'passed','independent_scalar_cells':len(table),'metrics_per_cell':len(keys),'tolerance_c':1e-10,'scope':'Recomputed every saved 24-cell coverage and failure summary from case outputs, daily series, and conditional bounds using scalar comparisons.','limitation':'Post-hoc numerical tolerance is not physical measurement uncertainty; underlying case predictions and source weights are not reproduced here.','storage':'temporary RAM filesystem; not durable'}
(S/'coverage_numeric_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
