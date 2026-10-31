#!/usr/bin/env python3
"""Independently reconstruct global estimator roles and support counts."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
from collections import Counter
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usace_reservoir';SOURCE=ROOT/'results/wrr_review_completion_20261024';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def main():
    helper=T.load_script('usace_support_audit_helpers',ROOT/'scripts/856_partial_history_feature_support_plan.py')
    plan=json.loads((OUT/'partial_history_feature_support_plan.json').read_text());status=json.loads((OUT/'partial_history_feature_support_status.json').read_text())
    c=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet');c=c[c.policy_choice.ne('unavailable')&c.eval_truth_h30.notna()].reset_index(drop=True)
    if 'training_partition' in c:raise ValueError('Independently implemented role logic requires standard source cases')
    config=json.loads((ROOT/'configs/wrr_review_completion_20261024.json').read_text());names=config['fit_role_names'];shares=np.asarray(config['fit_role_shares'])
    region='global_source_candidate';number=sorted(set(c.region.unique())|{region}).index(region)
    rng=np.random.default_rng(plain_seed(7,0,number));group_names=np.array(sorted(c.independence_group.unique()));rng.shuffle(group_names)
    cuts=np.maximum.accumulate(np.round(np.cumsum(shares)[:-1]*len(group_names)).astype(int));parts=np.split(group_names,cuts)
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');roles={k:list(map(str,v)) for k,v in zip(names,parts)}
    if roles!=bundle['roles']:raise AssertionError('Independently reconstructed role assignment differs')
    weights={}
    for name,part in zip(names,parts):
        n=Counter(rng.choice(part,len(part),replace=True).tolist());weights[name]=c.independence_group.map(n).fillna(0).to_numpy(float)
    fit=weights['estimator']>0;other=((weights['interval_calibration']>0)|(weights['risk_learning']>0)|(weights['rule_calibration']>0))&c.design_family.eq('crossed').to_numpy()
    if fit.sum()!=status['source_fit_rows'] or other.sum()!=status['source_non_estimator_crossed_rows'] or (fit&other).any():raise AssertionError('Source role support differs')
    x=F.design_matrix(c,simulation=True).reindex(columns=bundle['features']);t=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet');y=F.design_matrix(t,simulation=True).reindex(columns=bundle['features'])
    w=weights['estimator'][fit].astype(int);source=x.loc[fit];hold=x.loc[other];expected=pd.read_csv(PRIVATE/'partial_history_feature_support.csv').set_index('feature');target_flags=[];held_flags=[]
    for name in bundle['features']:
        v=source[name].to_numpy(float);fv=v[np.isfinite(v)];fw=w[np.isfinite(v)]
        if len(fv):
            expanded=np.sort(np.repeat(fv,fw));lo=float(expanded[0]);hi=float(expanded[-1]);qlo=float(expanded[int(np.ceil(.01*len(expanded)))-1]);qhi=float(expanded[int(np.ceil(.99*len(expanded)))-1])
        else:lo=hi=qlo=qhi=np.nan
        s=expected.loc[name]
        for col,value in [('source_min',lo),('source_max',hi),('source_weighted_q01',qlo),('source_weighted_q99',qhi)]:
            if not np.isclose(value,s[col],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Training bound differs: '+name+' '+col)
        has_nan=bool(np.isnan(v).any());has_pos=bool(np.isposinf(v).any());has_neg=bool(np.isneginf(v).any())
        def manual(z):
            finite=np.isfinite(z);out=finite&((z<lo)|(z>hi)) if np.isfinite(lo) else finite.copy()
            tail=finite&((z<qlo)|(z>qhi)) if np.isfinite(qlo) else finite.copy()
            missing=np.array([np.isnan(u) and not has_nan or np.isposinf(u) and not has_pos or np.isneginf(u) and not has_neg for u in z])
            return out,tail,missing
        f=manual(y[name].to_numpy(float));g=manual(hold[name].to_numpy(float))
        for col,value in [('target_outside_minmax',sum(f[0])),('target_outside_weighted_q01_q99',sum(f[1])),('target_unseen_nonfinite',sum(f[2])),
                          ('source_other_outside_minmax',sum(g[0])),('source_other_outside_weighted_q01_q99',sum(g[1])),('source_other_unseen_nonfinite',sum(g[2]))]:
            if int(s[col])!=int(value):raise AssertionError('Feature count differs: '+name+' '+col)
        target_flags.append(f);held_flags.append(g)
    for label,flags in [('target',target_flags),('source_non_estimator_crossed',held_flags)]:
        outside=np.column_stack([x[0] for x in flags]);unseen=np.column_stack([x[2] for x in flags]);keep=np.asarray(bundle['features'])!='n_complete_years';s=status[label]
        for key,val in [('outside_minmax_cases',outside.any(axis=1).sum()),('outside_minmax_excluding_complete_count_cases',outside[:,keep].any(axis=1).sum()),
                        ('unseen_nonfinite_cases',unseen.any(axis=1).sum()),('any_minmax_or_unseen_excluding_complete_count_cases',(outside|unseen)[:,keep].any(axis=1).sum())]:
            if int(val)!=s[key]:raise AssertionError('Aggregate differs: '+label+' '+key)
    for field in ['n_complete_years','law_phi_a','law_phi_r']:
        if not np.allclose(y[field],pd.to_numeric(t[field],errors='coerce'),atol=0,rtol=0,equal_nan=True):raise AssertionError('Feature mapping differs: '+field)
    result={'status':'passed','features':len(bundle['features']),'source_estimator_cases':int(fit.sum()),'source_other_crossed_cases':int(other.sum()),'target_cases':len(t),
      'scope':'Independent reconstruction of source group bootstrap multiplicities, expanded weighted quantiles and scalar source/target support flags for all 68 design features.',
      'limits':'The same case tables and feature-design routine are reused; this does not verify hidden-case construction, interpret support as a calibrated risk, or establish independence.'}
    (OUT/'partial_history_feature_support_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
