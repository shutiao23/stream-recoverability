#!/usr/bin/env python3
"""Post-hoc peak-visibility stratification of fixed Truckee predictions."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';LEVELS=[5,10,25,50,75,90,95];TOL=1e-8

def freeze():
    dest=OUT/'peak_visibility_plan.json'
    if dest.exists():raise FileExistsError('Preserve peak-visibility plan')
    status=json.loads((OUT/'exploratory_score_status.json').read_text());audit=json.loads((OUT/'exploratory_score_independent_audit.json').read_text())
    predictions=PRIVATE/'exploratory_predictions.parquet'
    if status['status']!='exploratory_scored' or audit['status']!='passed':
        raise ValueError('Existing score or audit incomplete')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc after viewing all 72 overall and by-year Truckee scores; not prespecified and not a prospective risk classifier',
        'cohort':'All 72 fixed controlled-gap records from the one-station four-year experiment; use one three-method common finite cohort in each stratum.',
        'strata':'All; finite observed bound equals complete reference within 1e-8 C; complete reference exceeds finite observed bound by more than 1e-8 C; observed bound unavailable. Reference-based strata are retrospective and cannot be selected at deployment.',
        'metrics':'Per-method point MAE, signed bias, 0.5 C failure frequency; D2 and stochastic nominal 90% coverage, width, interval score and CRPS; case counts and represented years. No inferential confidence interval from one station and four years.',
        'limits':'Outcome-defined and selected after main results; repeated synthetic masks share one station and four reference years. Neither population failure rate nor independent-climate calibration is established.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded post-hoc Truckee peak-visibility comparison')

def run():
    plan=json.loads((OUT/'peak_visibility_plan.json').read_text())
    frame=pd.read_parquet(PRIVATE/'exploratory_predictions.parquet');ref=frame.eval_truth_h30.to_numpy(float);bound=frame.observed_lower_bound__observed_days.to_numpy(float)
    if len(frame)!=72 or np.any(np.isfinite(bound)&(bound>ref+TOL)):raise ValueError('Reference/support cohort differs')
    q1=frame[[f'D2_q{x:02d}' for x in LEVELS]].to_numpy(float);q2=frame[[f'stochastic_cal_q{x:02d}' for x in LEVELS]].to_numpy(float)
    common=np.isfinite(ref)&np.isfinite(frame.h30__policy)&np.isfinite(frame.D2)&np.isfinite(frame.stochastic_cal_q50)&np.isfinite(q1).all(axis=1)&np.isfinite(q2).all(axis=1)
    masks={'all':np.ones(len(frame),bool),'reference_equals_bound':np.isfinite(bound)&(np.abs(ref-bound)<=TOL),
           'reference_above_bound':np.isfinite(bound)&(ref-bound>TOL),'bound_unavailable':~np.isfinite(bound)}
    methods=[('plug_in','h30__policy',None),('D2','D2','D2'),('stochastic_calibrated','stochastic_cal_q50','stochastic_cal')]
    sample=T.load_script('truckee_peak_quadrature',ROOT/'scripts/528_review_response_annual.py')
    from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps,interval_score
    rows=[]
    for label,mask in masks.items():
        b=frame.loc[mask&common];truth=b.eval_truth_h30.to_numpy(float);lower=b.observed_lower_bound__observed_days.to_numpy(float)
        for name,col,prefix in methods:
            r={'stratum':label,'estimator':name,'n_eligible':int(mask.sum()),'n_common':len(b),'represented_years':b.year.nunique()}
            if len(b):
                point=b[col].to_numpy(float);point=np.where(np.isfinite(lower),np.maximum(point,lower),point);err=point-truth
                r.update(mae=float(np.abs(err).mean()),bias=float(err.mean()),failure_gt_0_5=float((np.abs(err)>.5).mean()))
                if prefix:
                    q=b[[f'{prefix}_q{x:02d}' for x in LEVELS]].to_numpy(float);lo=q[:,0];hi=q[:,-1]
                    r.update(coverage90=float(((truth>=lo-TOL)&(truth<=hi+TOL)).mean()),mean_width90=float((hi-lo).mean()),
                             zero_width=int((abs(hi-lo)<=TOL).sum()),interval_score90=float(interval_score(lo,hi,truth).mean()),
                             crps=float(ensemble_crps(sample.quantile_samples(q,lower),truth).mean()))
            rows.append(r)
    table=pd.DataFrame(rows);path=OUT/'peak_visibility_summary.csv';table.to_csv(path,index=False)
    status={'status':'computed_posthoc','cases':len(frame),'three_method_common_cases':int(common.sum()),
            'cases_by_stratum':{k:int(v.sum()) for k,v in masks.items()},'limitations':plan['limits']}
    (OUT/'peak_visibility_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
