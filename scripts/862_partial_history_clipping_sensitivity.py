#!/usr/bin/env python3
"""Compare fixed tree predictions under explicitly artificial input clipping."""
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
LEVELS=[5,10,25,50,75,90,95]

def raw_predictions(c,bundle):
    x=F.design_matrix(c,simulation=True).reindex(columns=bundle['features'])
    return np.column_stack([model.predict(x) for model in bundle['quantile_models']])

def main():
    helper=T.load_script('usace_clip_helper',ROOT/'scripts/856_partial_history_feature_support_plan.py');plan=json.loads((OUT/'partial_history_clipping_plan.json').read_text())
    support=pd.read_csv(PRIVATE/'partial_history_feature_support.csv').set_index('feature');cases=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet');bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text())
    if bundle['roles']['interval_calibration']!=cal['D2_calibration_groups']:raise ValueError('Calibration role mismatch')
    bundle['offsets']=cal['D2_offsets'];inference=T.load_script('usace_clip_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    qcols=[f'D2_q{q:02d}' for q in LEVELS];base=inference.predict(cases,bundle)
    check=['D2','risk_score']+qcols
    if not np.allclose(base[check].to_numpy(float),cases[check].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Original inference does not reproduce saved case predictions')
    raw=raw_predictions(cases,bundle);results=[];private=[]
    variants={'count_only':['n_complete_years'],'anomaly_autocorrelation_only':['law_phi_a'],
              'residual_autocorrelation_only':['law_phi_r'],'all_three':['n_complete_years','law_phi_a','law_phi_r']}
    for name,features in variants.items():
        altered=cases.copy();changed_input=np.zeros(len(cases),bool)
        for feature in features:
            lo=float(support.loc[feature,'source_min']);hi=float(support.loc[feature,'source_max']);old=pd.to_numeric(altered[feature],errors='coerce').to_numpy(float)
            if not np.isfinite(lo) or not np.isfinite(hi):raise ValueError('Training edge unavailable')
            new=np.clip(old,lo,hi);changed_input|=np.isfinite(old)&(old!=new);altered[feature]=new
        y=inference.predict(altered,bundle);raw_new=raw_predictions(altered,bundle)
        raw_delta=np.abs(raw_new-raw);post_delta=np.abs(y[qcols].to_numpy(float)-base[qcols].to_numpy(float))
        point_delta=np.abs(y.D2.to_numpy(float)-base.D2.to_numpy(float));risk_delta=np.abs(y.risk_score.to_numpy(float)-base.risk_score.to_numpy(float))
        rows={'scenario':name,'cases':len(cases),'cases_with_clipped_inputs':int(changed_input.sum()),
              'cases_raw_quantile_changed_gt_1e_10':int((np.nanmax(raw_delta,axis=1)>1e-10).sum()),
              'cases_postcal_quantile_changed_gt_1e_10':int((np.nanmax(post_delta,axis=1)>1e-10).sum()),
              'cases_point_changed_gt_1e_10':int((point_delta>1e-10).sum()),'cases_score_changed_gt_1e_10':int((risk_delta>1e-10).sum()),
              'max_raw_quantile_change_c':float(np.nanmax(raw_delta)),'max_postcal_quantile_change_c':float(np.nanmax(post_delta)),
              'max_point_change_c':float(np.nanmax(point_delta)),'max_classifier_score_change':float(np.nanmax(risk_delta))}
        results.append(rows)
        private.append(pd.DataFrame({'resource_id':cases.resource_id,'year':cases.year,'realization_id':cases.realization_id,'scenario':name,'inputs_clipped':changed_input,
          'max_raw_quantile_change':np.nanmax(raw_delta,axis=1),'max_postcal_quantile_change':np.nanmax(post_delta,axis=1),'point_change':point_delta,'risk_score_change':risk_delta}))
    table=pd.DataFrame(results);table.to_csv(OUT/'partial_history_clipping_summary.csv',index=False)
    detail=PRIVATE/'partial_history_clipping_cases.parquet';pd.concat(private,ignore_index=True).to_parquet(detail,index=False);detail.chmod(0o600)
    status={'status':'completed_posthoc_clipping_diagnostic','cases':len(cases),'scenarios':len(variants),'baseline_predictions_reproduced':True,
      'limits':plan['limits']+' '+plan['meaning']}
    (OUT/'partial_history_clipping_status.json').write_text(json.dumps(status,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()
