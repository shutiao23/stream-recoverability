#!/usr/bin/env python3
"""Independently audit daily-versus-continuous coverage disagreements."""
import json,math
from pathlib import Path
import numpy as np,pandas as pd
STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def main():
 plan=json.loads((STAGE/'reporting_resolution_plan.json').read_text());status=json.loads((STAGE/'reporting_resolution_status.json').read_text())
 c=pd.read_parquet(STAGE/'subdaily_bounded_score_cases.parquet');expected=pd.read_csv(STAGE/'reporting_resolution_summary.csv');rows=[]
 for clock in ['fixed_standard','native_civil']:
  base=c[c.continuous_clock.eq(clock)]
  for cohort in ['all','fixed_standard_full_hour_posthoc','fixed_standard_full_quarter_posthoc']:
   selected=base[base.continuous_common]
   if cohort=='fixed_standard_full_hour_posthoc':selected=selected[selected.hourly_reference_posthoc]
   if cohort=='fixed_standard_full_quarter_posthoc':selected=selected[selected.quarter_reference_posthoc]
   for method,prefix in [('D2','D2'),('stochastic','stochastic_cal')]:
    entries=[]
    for r in selected.itertuples(index=False):
     L=float(r.h30_lower_c);U=float(r.h30_upper_c);lo=float(getattr(r,prefix+'_q05'));hi=float(getattr(r,prefix+'_q95'));obs=float(r.observed_lower_bound__observed_days);truth=float(r.reference_h30);finite=math.isfinite(lo) and math.isfinite(hi)
     daily=finite and lo<=truth<=hi;possible=finite and lo<=U and hi>=L;definite=finite and lo<=L and hi>=U;mismatch=math.isfinite(obs) and obs>U+1e-9;gap=obs-U if mismatch else float('nan');distance=max(lo-U,L-hi,0.);miss=finite and not possible
     entries.append({'station_id':r.station_id,'year':r.year,'finite':finite,'daily':daily,'possible':possible,'definite':definite,'daily_covered_continuous_definitely_missed':daily and miss,'mismatch':mismatch,'qbound':mismatch and math.isfinite(obs) and math.isclose(lo,obs,abs_tol=1e-9,rel_tol=0),'gap':gap,'miss':miss,'distance':distance})
    z=pd.DataFrame(entries);g=z.loc[z.mismatch,'gap'];d=z.loc[z['miss'],'distance'];e=expected[(expected.clock==clock)&(expected.cohort==cohort)&(expected.method==method)].iloc[0]
    checks={'cases':len(z),'finite_intervals':z.finite.sum(),'daily_reference_covered':z.daily.sum(),'continuous_definite_cover':z.definite.sum(),'continuous_possible_cover':z.possible.sum(),
     'daily_covered_continuous_definitely_missed':z.daily_covered_continuous_definitely_missed.sum(),'published_bound_above_continuous_upper':z.mismatch.sum(),
     'mismatch_station_years':len(z.loc[z.mismatch,['station_id','year']].drop_duplicates()),'mismatch_q05_equals_published_bound':z.qbound.sum(),
     'mismatch_gap_median_c':g.median() if len(g) else np.nan,'mismatch_gap_max_c':g.max() if len(g) else np.nan,'mismatch_gap_le_0_01_c':(g<=.01+1e-12).sum(),
     'mismatch_gap_le_0_05_c':(g<=.05+1e-12).sum(),'continuous_nonoverlap_cases':len(d),'nonoverlap_distance_le_0_01_c':(d<=.01+1e-12).sum(),
     'nonoverlap_distance_le_0_05_c':(d<=.05+1e-12).sum(),'nonoverlap_distance_le_0_1_c':(d<=.1+1e-12).sum(),'max_nonoverlap_distance_c':d.max() if len(d) else np.nan}
    for key,value in checks.items():
     if not np.isclose(value,e[key],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Mismatch '+clock+' '+cohort+' '+method+' '+key)
    rows.append((clock,cohort,method))
 out={'status':'passed','summary_cells_recomputed':len(rows),'case_clock_rows':len(c),'scope':'Independent scalar daily/subdaily coverage, observed-bound mismatch, tolerance-distance and station-year counts.',
 'limitations':plan['limits']+' '+plan['tolerance'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'reporting_resolution_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
