#!/usr/bin/env python3
"""Independently recheck USGS feature flags and mandatory history gate."""
import json,sys
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_features as F
USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def main():
 p=json.loads((STAGE/'feature_support_plan.json').read_text());s=json.loads((STAGE/'feature_support_status.json').read_text())
 c=pd.read_parquet(STAGE/'scored_cases.parquet');bounds=pd.read_csv(USACE/'partial_history_feature_support.csv').set_index('feature');model=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');x=F.design_matrix(c,simulation=True).reindex(columns=model['features']);summary=pd.read_csv(STAGE/'feature_support_summary.csv').set_index('margin_fraction');features=pd.read_csv(STAGE/'feature_support_counts.csv').set_index(['margin_fraction','feature'])
 for margin in [0.,.01]:
  allwarn=np.zeros(len(c),bool);other=np.zeros(len(c),bool)
  for name in model['features']:
   a=bounds.loc[name];lo=float(a.source_min);hi=float(a.source_max);ql=float(a.source_weighted_q01);qh=float(a.source_weighted_q99);scale=qh-ql if np.isfinite(ql) and np.isfinite(qh) and qh>ql else hi-lo
   if not np.isfinite(scale) or scale<=0:scale=1.
   flags=[]
   for v in x[name].to_numpy(float):
    if np.isnan(v):flag=a.source_estimator_nan_rows==0
    elif np.isposinf(v):flag=a.source_estimator_posinf_rows==0
    elif np.isneginf(v):flag=a.source_estimator_neginf_rows==0
    elif not np.isfinite(lo) or not np.isfinite(hi):flag=True
    else:flag=v<lo-margin*scale or v>hi+margin*scale
    flags.append(flag)
   flags=np.asarray(flags,bool);allwarn|=flags
   if name!='n_complete_years':other|=flags
   if int(flags.sum())!=int(features.loc[(margin,name),'flagged_cases']):raise AssertionError('Feature count differs')
  h=c.hourly_reference_posthoc.to_numpy(bool);expected={'cases':len(c),'any_feature_flagged':int(allwarn.sum()),'any_noncount_feature_flagged':int(other.sum()),
    'target_years_noncount_flagged':len(c.loc[other,['station_id','year']].drop_duplicates()),'hourly_supported_cases':int(h.sum()),'hourly_supported_noncount_flagged':int((other&h).sum())}
  if any(int(summary.loc[margin,k])!=v for k,v in expected.items()):raise AssertionError('Support aggregate differs')
 lower=pd.to_numeric(c.observed_lower_bound__observed_days,errors='coerce').to_numpy(float)
 if c.n_complete_years.ge(4).any() or np.isinf(lower).any():raise ValueError('Mandatory gate input changed')
 g=s['gate'];checks={'cases':len(c),'individual_score_le_0_1':int(c.risk_score.le(.1).sum()),'numerical_states_if_no_quality_flag_or_optional_limits':0,
   'bound_states_if_no_quality_flag_or_optional_limits':int(np.isfinite(lower).sum()),'unknown_states_if_no_quality_flag_or_optional_limits':int(np.isnan(lower).sum())}
 if any(g[k]!=v for k,v in checks.items()):raise AssertionError('Conditional gate count differs')
 out={'status':'passed','cases':len(c),'features_checked':len(model['features']),'margins_checked':2,'scope':'Independent scalar feature comparisons and mandatory history gate on saved USGS cases.',
 'limitations':'The same source extrema, source model feature-design routine and target cases are reused; no causal, physical accuracy, independent climate or risk guarantee.','storage':'temporary RAM filesystem; not durable'}
 (STAGE/'feature_support_independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
