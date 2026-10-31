#!/usr/bin/env python3
"""Freeze a post-hoc source-role evaluation of the marginal support warning."""
from datetime import datetime,timezone
import json
from pathlib import Path
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_ood_release';EXTERNAL=REV/'external_usace_reservoir';SOURCE=ROOT/'results/wrr_review_completion_20261024';USACE=ROOT/'private/wrr_usace_reservoir_reference_20261027';PRIVATE=ROOT/'private/wrr_source_ood_release_20261027'

def main():
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);path=OUT/'plan.json'
    if path.exists():raise FileExistsError('Preserve support-warning plan')
    helper=T.load_script('source_ood_plan_roles',ROOT/'scripts/866_source_support_rule_evaluation.py');h,source,groups,weights,bundle,hold=helper.source_data()
    for name in ['partial_history_feature_support_independent_audit.json','partial_history_clipping_independent_audit.json']:
        if json.loads((EXTERNAL/name).read_text())['status']!='passed':raise ValueError('Previous support audit incomplete')
    files=[SOURCE/'cases/leave_one_year_out/seed_00.parquet',SOURCE/'deployment/global_source_candidate.joblib',
      ROOT/'configs/wrr_review_completion_20261024.json',ROOT/'scripts/466_review_completion_refit.py',ROOT/'scripts/wrr_tr_features.py',
      ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'src/stream_recoverability/experiments/tr_revision/outputs.py',
      REV/'external_bc_air2stream/source_calibration.json',USACE/'partial_history_feature_support.csv',
      EXTERNAL/'partial_history_feature_support_independent_audit.json',EXTERNAL/'partial_history_clipping_independent_audit.json',
      ROOT/'scripts/856_partial_history_feature_support_plan.py',ROOT/'scripts/866_source_support_rule_evaluation.py',Path(__file__)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after the global model, source calibration, external scores and training-range audit were examined; before this fixed-role warning evaluation',
      'source_cohort':'All source crossed-mask cases with positive bootstrap weight in the global candidate rule-calibration role. The role is disjoint from estimator, interval-calibration and risk-learning groups, but source outcomes and other source analyses were previously seen and the rule role participated in threshold calibration. This is not new independent climate validation.',
      'eligible':'A finite D2 estimate and individual score, finite reported H30 and observed lower bound, and at least four observed complete training years. Quality flags and optional operating-range limits are not evaluated, so policies are hypothetical and do not reproduce the full three-output release rule.',
      'warning':'Without using outcomes, flag any feature other than n_complete_years that is outside its global estimator-role finite min/max, or has a nonfinite category never present in that role. This fixed marginal detector was developed after seeing external support results; one-dimensional support is not a reliable multivariate distribution test.',
      'outcomes':'Failure = abs(D2 - reported reference H30) >0.5 C. For warning alone report confusion counts, recall and false-positive rate. Repeated masks are not independent years; source sensor accuracy is not independently established.',
      'policies':'Compare individual score <=0.1 alone, score <=0.1 plus no support warning, and a posthoc score-only ranking that retains exactly the same number of numeric cases as the combined rule. The matched cutoff uses this target cohort score distribution, not outcomes, and is transductive rather than a prospective policy.',
      'scoring':'Report retention and conditional failure, both case-equal and equal-group-weighted; compare errors among equally many numeric outputs. Use 4000 group bootstrap resamples for the difference in conditional failure rate, retaining only draws with both policies selecting a case. Group bootstrap does not establish independent-climate safety.',
      'limitations':'Source rule groups and model scores are previously opened, and the warning was chosen after external outputs were inspected. Excluding different cases changes the meaning of retained outputs. There is no causal or calibration guarantee and the same warning flags every external case; source results cannot validate it as a universal failure detector.',
      'source_rule_crossed_cases':int(hold.sum()),'source_rule_positive_groups':int(source.loc[hold,'independence_group'].nunique()),
      'source_estimator_positive_groups':int(source.loc[weights['estimator']>0,'independence_group'].nunique()),'model_features':len(bundle['features']),
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({k:plan[k] for k in ['source_rule_crossed_cases','source_rule_positive_groups','source_estimator_positive_groups','model_features']},indent=2))

if __name__=='__main__':main()
