#!/usr/bin/env python3
"""Freeze a post-hoc audit of the deployment model's actual training support."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
from datetime import datetime,timezone
import json
from pathlib import Path
import joblib
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usace_reservoir';SOURCE=ROOT/'results/wrr_review_completion_20261024';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def roles():
    refit=T.load_script('usace_global_training_roles',ROOT/'scripts/466_review_completion_refit.py')
    source=SOURCE/'cases/leave_one_year_out/seed_00.parquet';cases=pd.read_parquet(source)
    cases=cases.loc[cases.policy_choice.ne('unavailable')&cases.eval_truth_h30.notna()].reset_index(drop=True)
    region='global_source_candidate';number=sorted(set(cases.region.unique())|{region}).index(region)
    _,groups,weights=refit.roles(cases,region,plain_seed(7,0,number))
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    if groups!=bundle['roles']:raise ValueError('Reconstructed deployment model roles differ')
    return cases,groups,weights,bundle

def main():
    path=OUT/'partial_history_feature_support_plan.json'
    if path.exists():raise FileExistsError('Preserve support-audit plan')
    status=json.loads((OUT/'partial_history_score_independent_audit.json').read_text())
    replay=json.loads((OUT/'partial_history_prediction_replay_status.json').read_text())
    if status['status']!='passed' or replay['status']!='passed':raise ValueError('External case audit not complete')
    cases,groups,weights,bundle=roles()
    fit=weights['estimator']>0;other=(weights['interval_calibration']>0)|(weights['risk_learning']>0)|(weights['rule_calibration']>0)
    if (fit&other).any() or not fit.any() or not other.any():raise ValueError('Unexpected model role overlap')
    files=[SOURCE/'cases/leave_one_year_out/seed_00.parquet',SOURCE/'deployment/global_source_candidate.joblib',
      ROOT/'configs/wrr_review_completion_20261024.json',ROOT/'scripts/466_review_completion_refit.py',ROOT/'scripts/wrr_tr_features.py',
      PRIVATE/'partial_history_scored_cases.parquet',OUT/'partial_history_score_status.json',
      OUT/'partial_history_score_independent_audit.json',OUT/'partial_history_prediction_replay_status.json',Path(__file__),
      ROOT/'scripts/857_partial_history_feature_support.py']
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after model predictions, conditional errors, source factorial sensitivity and target feature values have been examined; before this range audit',
      'training':'Reconstruct seed-zero global candidate roles and bootstrap weights from the original source cases. Use only rows with positive estimator weights and the exact feature-design function used to fit quantile models. Finite min/max and frequency-weighted 1st/99th percentile bounds are computed separately for each model feature.',
      'comparison':'Compare all fixed 306 external cases and, as a descriptive comparator, source crossed-mask cases assigned positive weight in non-estimator roles. The latter participated in other calibration or risk components and is not a new independent validation sample.',
      'definition':'A finite target value is outside if below the estimator-role minimum or above its maximum; a nonfinite target value is unsupported if no nonfinite source-training values occurred. Report finite/nonfinite cases separately. Also report values outside weighted 1st/99th percentile bounds as a descriptive tail flag, not a failure classifier.',
      'count_feature':'Report any out-of-range feature both with and without n_complete_years. The real external count remains zero and is not replaced with an artificial in-range value. Never interpret one-dimensional ranges as a complete multivariate support region.',
      'summary':'Per feature: training finite/nonfinite weighted counts and target/other-role out-of-range counts. Per case: number and identity of flagged features; aggregate across cases, target station-years and sites. All results use decision-time inputs only, but their analysis is retrospective and cannot establish risk calibration.',
      'limits':'Source masks, local-history conditions, climatology, stations and time differ. Positive weights and training source identities do not establish independent climates or eliminate source overlap. Multiple feature flags are correlated, features can lie within marginal ranges while their joint combination is unsupported, and tree models can have active behavior outside ranges.',
      'source_rows':len(cases),'source_estimator_positive_rows':int(fit.sum()),'source_estimator_positive_groups':int(cases.loc[fit,'independence_group'].nunique()),
      'source_non_estimator_positive_rows':int(other.sum()),'model_features':len(bundle['features']),
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({k:plan[k] for k in ['source_rows','source_estimator_positive_rows','source_estimator_positive_groups','source_non_estimator_positive_rows','model_features']},indent=2))

if __name__=='__main__':main()
