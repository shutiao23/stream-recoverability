#!/usr/bin/env python3
"""Post-hoc exact versus numerical tolerance sensitivity in main annual cases."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json
import numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability')
OUT=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
DATA=ROOT/'private/wrr_review_case_evidence_20261027/results/wrr_review_response_20261027/whole_archive/annual_case_evidence.parquet'
ANNUAL=ROOT/'results/wrr_review_response_20261027/whole_archive/annual.csv'
SUMMARY=ROOT/'results/wrr_review_response_20261027/whole_archive/peak_visibility_annual.csv'
PLAN=OUT/'main_coverage_numeric_corrected_plan.json'
def freeze():
 if PLAN.exists():raise FileExistsError('Preserve prior posthoc plan')
 files=[DATA,ANNUAL,SUMMARY,ROOT/'scripts/521_whole_archive.py',ROOT/'scripts/578_peak_visibility_diagnostics.py',Path(__file__)]
 d={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after the first script failed before reporting results because pandas mode attribute shadowed the mode column; corrected column selection before computing results',
 'scope':'All saved incomplete-year whole-archive cases on common finite D2 and stochastic quantile/reference/bound inputs. Compare inclusive exact coverage against absolute 1e-10 and 1e-8 C tolerances in each family/mode and peak-visibility stratum. Reproduce stored 1e-8 pooled coverage in peak_visibility_annual.csv; also report equal case weights and equal group weights, not treated as independent stations.',
 'limits':'Same saved references, outputs and prior-outcome-defined strata; no independent reference or raw-data recomputation. Tolerances are numerical comparisons, not physical sensor error. This audit cannot establish population calibration or coverage.',
 }
 PLAN.write_text(json.dumps(d,indent=2)+'\n');print('Plan frozen')
def run():
 p=json.loads(PLAN.read_text())
 d=pd.read_parquet(DATA);summary=pd.read_csv(SUMMARY);keys=['family','mode','replicate','station_key','year']
 if d.duplicated(keys).any():raise ValueError('Duplicate keys')
 n=['reference_h30','observed_lower_bound__observed_days']+[f'{m}_q{k:02d}' for m in ('D2','stochastic_cal') for k in (5,10,25,50,75,90,95)]
 rows=[]
 for (family,mode),g in d.groupby(['family','mode'],sort=True):
  a=g[np.isfinite(g[n].to_numpy(float)).all(axis=1)].copy();a['stratum']=np.where(a.reference_h30-a.observed_lower_bound__observed_days<=1e-8,'bound_matches_reference','unobserved_peak_excess')
  if (a.reference_h30<a.observed_lower_bound__observed_days-1e-8).any():raise ValueError('Observed bound above reference')
  for stratum in ('all','bound_matches_reference','unobserved_peak_excess'):
   sub=a if stratum=='all' else a[a.stratum.eq(stratum)]
   for name,method in [('D2','D2'),('stochastic_cal','stochastic_calibrated')]:
    y=sub.reference_h30.to_numpy(float);lo=sub[name+'_q05'].to_numpy(float);hi=sub[name+'_q95'].to_numpy(float)
    def covered(t):return (y>=lo-t)&(y<=hi+t)
    c0,c1,c8=covered(0),covered(1e-10),covered(1e-8)
    s=summary[(summary.family==family)&(summary['mode']==mode)&(summary.stratum==stratum)&(summary.estimator==method)]
    if len(s)!=1 or int(s.iloc[0].n)!=len(sub) or not np.isclose(s.iloc[0].coverage90,c8.mean(),atol=1e-12,rtol=0):raise AssertionError('Stored pooled 1e-8 coverage does not match')
    row={'family':family,'mode':mode,'stratum':stratum,'method':method,'n_cases':len(sub),'stations':sub.station_key.nunique(),'groups':sub.independence_group.nunique(),'exact_covered':int(c0.sum()),'tolerance_1e10_covered':int(c1.sum()),'tolerance_1e8_covered':int(c8.sum()),'exact_to_1e10_changed':int((c0!=c1).sum()),'1e10_to_1e8_changed':int((c1!=c8).sum()),'exact_rate':float(c0.mean()),'tolerance_1e10_rate':float(c1.mean()),'tolerance_1e8_rate':float(c8.mean()),'saved_coverage_reproduced':True}
    rows.append(row)
 df=pd.DataFrame(rows);f=OUT/'main_coverage_numeric_corrected_summary.csv';df.to_csv(f,index=False)
 out={'status':'passed_posthoc_sensitivity','rows':len(df),'annual_case_rows':len(d),'tolerances_c':[0,1e-10,1e-8],'total_exact_to_1e10_all_strata_cases':int(df[df.stratum.eq('all')].exact_to_1e10_changed.sum()),'limitations':p['limits'],'storage':'temporary RAM; not durable'}
 (OUT/'main_coverage_numeric_corrected_status.json').write_text(json.dumps(out,indent=2)+'\n');print(df.to_string(index=False));print(json.dumps(out,indent=2))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);a=parser.parse_args();freeze() if a.action=='freeze' else run()
