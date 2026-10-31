#!/usr/bin/env python3
"""Freeze a post-hoc projection-aware risk-score comparison before fitting."""
from datetime import datetime, timezone
import json
from pathlib import Path
import joblib
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'projected_risk_sensitivity'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026'
PRIVATE=ROOT/'private/wrr_projected_risk_sensitivity_20261027'

def main():
    if (OUT/'plan.json').exists():raise FileExistsError('Risk sensitivity already frozen')
    audit=json.loads((REV/'open_source_sensitivity/candidate_source_role_audit.json').read_text())
    if audit['status']!='passed' or audit['positive_target_region_rows']!=0 or audit['post_2009_forward_source_rows']!=0:
        raise ValueError('Candidate source-role audit incomplete')
    frames=pd.read_csv(REV/'whole_archive/trends.csv')
    roster=frames[(frames['mode']=='forward') & frames.estimator.eq('D2') & frames.retention.eq('all') & frames.dependence.eq('point')][['station_key','region','independence_group']].drop_duplicates().sort_values('station_key')
    if len(roster)!=41 or roster.station_key.duplicated().any():raise ValueError('Forward archive roster differs')
    regions=sorted(roster.region.unique());roles=[]
    files=[Path(__file__), ROOT/'scripts/701_projected_risk_fit.py',ROOT/'scripts/466_review_completion_refit.py',ROOT/'scripts/495_review_completion_independent_analysis.py',
           ROOT/'scripts/467_review_completion_analysis.py',ROOT/'scripts/wrr_tr_features.py',
           ROOT/'scripts/558_source_calibrated_release.py',
           ROOT/'src/stream_recoverability/experiments/tr_revision/archive.py',
           INPUT/'candidate_cases/before_2010/seed_00.parquet',INPUT/'refit_receipts.json',
           REV/'open_source_sensitivity/candidate_source_role_audit.json',REV/'whole_archive/trends.csv']
    for region in regions:
        model=INPUT/'refits/before_2010/seed_00'/f'{region}.joblib'
        calibration=INPUT/'calibrations/forward'/f'{region}.json'
        bundle=joblib.load(model);r={k:set(v) for k,v in bundle['roles'].items()}
        if any(r[a]&r[b] for i,a in enumerate(r) for b in list(r)[i+1:]):raise ValueError('Source roles overlap')
        roles.append({'region':region,'assigned_risk_groups':len(r['risk_learning']),
                      'assigned_rule_groups':len(r['rule_calibration'])})
        files.extend([model,calibration])
    paths=sorted(p for family in ('calendar','crossed') for p in (INPUT/'whole_archive'/family/'forward').glob('replicate_*/*/annual_predictions.parquet'))
    if len(paths)!=1640:raise ValueError(f'Expected 1,640 archive prediction files, found {len(paths)}')
    for p in paths:
        relative=p.relative_to(INPUT/'whole_archive')
        files.extend([p,p.parent/'design.json',p.parent/'open_source_receipt.json',
                      REV/'whole_archive'/relative])
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.mkdir(parents=True,exist_ok=True)
    roster.to_csv(PRIVATE/'roster.csv',index=False)
    manifest=[{'path':str(p.relative_to(ROOT)),} for p in files]
    manifest_path=PRIVATE/'input_manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc design following inspection of original risk, projection and target results; not prospective registration',
          'goal':'exploratory detection of absolute error >0.5 C for the support-projected D2 point, using only decision-time predictors',
          'source':'candidate-provider strictly held-region before-2010 source models; source case group assignments, source and target data already used in earlier analyses',
          'training':'train one fixed low-complexity LightGBM binary classifier per target region on assigned risk-learning source groups; group-weight each equally; exclude all target-region connected groups, require >=4 contributing groups and both classes; source D2 predictions are fitted on separate estimator and interval-calibration roles',
          'features':'the source model decision-time design matrix plus projected D2 90% interval width and projected D2 minus the visible observed lower bound; exclude source raw risk score, reference values, target truth and source outcome labels',
          'model_parameters':{'n_estimators':120,'learning_rate':0.04,'num_leaves':7,'min_child_samples':100,'reg_lambda':5,'subsample':1.0,'colsample_bytree':1.0,'n_jobs':1,'objective':'binary','verbosity':-1,'random_seed':'700 + sorted region position'},
          'threshold':'For each family, determine a score cutoff on disjoint assigned rule-calibration source groups before evaluating target scores; choose the attainable group-equal-weight source release rate nearest 80%, ties included together. Apply the same procedure to original raw score and projected-risk score; no outcome labels enter cutoff selection.',
          'target':'both original forward archive mask families, 41 stations, 20 repeated masks each, six target regions; predictions and annual reference values already available from previous work; target group held out from candidate source roles',
          'comparisons':'(1) frozen source-derived thresholds, report full cohort support, numerical retention, >0.5 C conditional failure and detection; (2) descriptive target-distribution exact-count matching to original threshold releases, deterministic label-free tie break. Equal numerical counts do not guarantee equal information as bounds.',
          'uncertainty':'4000 connected-group resamples of paired conditional error differences and retention differences; report per-region and leave-one-region-out fixed-prediction results; no finite-sample risk guarantee',
          'limitations':'posthoc and motivated by previously seen outcomes, no unopened independent reference, one source model seed, source single-year masks vs target multi-year archives, risk role groups may share source histories and climates; projected scores are not certified or necessarily calibrated probabilities, equal source retention need not give equal target retention',
          'privacy':'source cases, per-case targets, fitted risk classifiers and receipts remain local private; only aggregate results in review package',
          'target_prediction_files':len(paths),'roles':roles,}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen 6 source classifiers, 12 family cutoffs, and 1,640 target archive files',flush=True)

if __name__=='__main__':main()
