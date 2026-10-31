#!/usr/bin/env python3
"""Independently inspect LightGBM leaf paths for clipped external features."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def booster_evaluate(c,bundle,offsets):
    x=F.design_matrix(c,simulation=True).reindex(columns=bundle['features'])
    raw=np.column_stack([m.booster_.predict(x,num_threads=1) for m in bundle['quantile_models']])
    leaves=np.stack([m.booster_.predict(x,pred_leaf=True,num_threads=1) for m in bundle['quantile_models']],axis=1)
    classifier=bundle['classifier'];score=classifier.booster_.predict(x,num_threads=1) if classifier is not None else np.full(len(c),bundle['constant_probability'])
    cleaves=classifier.booster_.predict(x,pred_leaf=True,num_threads=1) if classifier is not None else np.empty((len(c),0))
    q=np.sort(raw+c.h30__policy.to_numpy(float)[:,None],axis=1)
    lower=c.observed_lower_bound__observed_days.to_numpy(float);valid=np.isfinite(lower);q[valid]=np.maximum(q[valid],lower[valid,None])
    overlap=c.peak_overlap.to_numpy(float);bins=np.where(overlap<=0,0,np.searchsorted([0,.25,.5,.75,1],overlap,side='left'))
    layers=c.policy_choice.where(c.policy_choice.isin(['air_ridge','donor_ridge']),'other').astype(str)
    difficulty=np.array([f'{a}|{b}' for a,b in zip(bins,layers)])
    for k in np.unique(difficulty):
        if k not in offsets:raise ValueError('Unsupported difficulty cell')
        q[difficulty==k]+=np.asarray(offsets[k])
    q=np.sort(q,axis=1);q[valid]=np.maximum(q[valid],lower[valid,None])
    return raw,leaves,q,score,cleaves

def main():
    h=T.load_script('usace_clip_audit_hash',ROOT/'scripts/856_partial_history_feature_support_plan.py');plan=json.loads((OUT/'partial_history_clipping_plan.json').read_text());status=json.loads((OUT/'partial_history_clipping_status.json').read_text())
    c=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet');support=pd.read_csv(PRIVATE/'partial_history_feature_support.csv').set_index('feature')
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text())
    raw,leaves,q,score,cleaves=booster_evaluate(c,bundle,cal['D2_offsets']);qcols=[f'D2_q{int(x*100):02d}' for x in F.QUANTILES]
    if not np.allclose(q,c[qcols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True) or not np.allclose(score,c.risk_score,atol=1e-10,rtol=0,equal_nan=True):
        raise AssertionError('Manual booster plus calibration does not reproduce original outputs')
    saved=pd.read_csv(OUT/'partial_history_clipping_summary.csv').set_index('scenario');rows=[]
    variants={'count_only':['n_complete_years'],'anomaly_autocorrelation_only':['law_phi_a'],
              'residual_autocorrelation_only':['law_phi_r'],'all_three':['n_complete_years','law_phi_a','law_phi_r']}
    for label,names in variants.items():
        altered=c.copy();changed=np.zeros(len(c),bool)
        for name in names:
            lo=float(support.loc[name,'source_min']);hi=float(support.loc[name,'source_max']);v=altered[name].to_numpy(float)
            z=np.where(v<lo,lo,np.where(v>hi,hi,v));changed|=np.isfinite(v)&(v!=z);altered[name]=z
        raw2,leaf2,q2,s2,cl2=booster_evaluate(altered,bundle,cal['D2_offsets'])
        rawdelta=np.abs(raw2-raw);qdelta=np.abs(q2-q);pointdelta=np.abs(q2[:,3]-q[:,3]);scoredelta=np.abs(s2-score)
        checks={'cases':len(c),'cases_with_clipped_inputs':changed.sum(),
          'cases_raw_quantile_changed_gt_1e_10':(np.max(rawdelta,axis=1)>1e-10).sum(),
          'cases_postcal_quantile_changed_gt_1e_10':(np.max(qdelta,axis=1)>1e-10).sum(),
          'cases_point_changed_gt_1e_10':(pointdelta>1e-10).sum(),'cases_score_changed_gt_1e_10':(scoredelta>1e-10).sum(),
          'max_raw_quantile_change_c':np.max(rawdelta),'max_postcal_quantile_change_c':np.max(qdelta),
          'max_point_change_c':np.max(pointdelta),'max_classifier_score_change':np.max(scoredelta)}
        for key,value in checks.items():
            if not np.isclose(value,saved.loc[label,key],atol=1e-10,rtol=0):raise AssertionError('Mismatch '+label+' '+key)
        rows.append({'scenario':label,'cases_with_quantile_leaf_changes':int(np.any(leaf2!=leaves,axis=(1,2)).sum()),
                     'cases_with_classifier_leaf_changes':int(np.any(cl2!=cleaves,axis=1).sum())})
    df=pd.DataFrame(rows);df.to_csv(OUT/'partial_history_clipping_leaf_audit.csv',index=False)
    result={'status':'passed','cases':len(c),'scenarios':len(rows),'manual_calibration_reproduced':True,
      'cases_with_any_quantile_leaf_changes':int(df.cases_with_quantile_leaf_changes.max()),
      'cases_with_any_classifier_leaf_changes':int(df.cases_with_classifier_leaf_changes.max()),
      'scope':'Direct LightGBM Booster predictions and leaf IDs; independently applies quantile sorting, source offsets and observed lower-bound projection.',
      'limits':'Same frozen models and feature-design routine reused. Feature clipping is artificial and neither proves transfer nor validates accuracy, calibration, data quality or independent climates.'}
    (OUT/'partial_history_clipping_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(df.to_string(index=False));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
