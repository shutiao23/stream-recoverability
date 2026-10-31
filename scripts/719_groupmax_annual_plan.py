#!/usr/bin/env python3
"""Freeze post-hoc source group-maximum annual interval sensitivity."""
from datetime import datetime,timezone
import json
from pathlib import Path
import joblib
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
OLD=REV/'open_source_sensitivity'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026'
OUT=REV/'groupmax_annual_calibration'
ROSTER=ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv'

def main():
    path=OUT/'plan.json'
    if path.exists():raise FileExistsError('Group-maximum sensitivity already frozen')
    audit=json.loads((OLD/'candidate_source_role_audit.json').read_text())
    if audit['status']!='passed' or audit['positive_target_region_rows']!=0 or audit['post_2009_forward_source_rows']!=0:
        raise ValueError('Candidate source role audit is unavailable')
    roster=pd.read_csv(ROSTER);regions=sorted(roster.region.unique());metadata=[]
    files=[Path(__file__),ROOT/'scripts/720_groupmax_annual_calibration.py',
           ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/467_review_completion_analysis.py',
           ROOT/'scripts/672_single_year_source_calibration.py',ROOT/'scripts/668_open_source_annual_diagnostics.py',
           ROOT/'scripts/578_peak_visibility_diagnostics.py',ROOT/'scripts/581_source_annual_interval_expansion.py',
           ROOT/'scripts/wrr_tr_features.py',ROOT/'src/stream_recoverability/experiments/tr_revision/archive.py',
           INPUT/'candidate_cases/before_2010/seed_00.parquet',OLD/'candidate_source_role_audit.json',
           OLD/'single_year_source_support.csv',OLD/'single_year_source_freeze.json',
           OLD/'single_year_calibration_status.json',OLD/'annual_sensitivity_status.json',ROSTER]
    for region in regions:
        model=INPUT/'refits/before_2010/seed_00'/f'{region}.joblib';cal=INPUT/'calibrations/forward'/f'{region}.json'
        bundle=joblib.load(model);roles={name:set(group) for name,group in bundle['roles'].items()}
        pool=roles['risk_learning']|roles['rule_calibration'];held=set(roster.loc[roster.region.eq(region),'independence_group'])
        if any(roles[a]&roles[b] for i,a in enumerate(roles) for b in list(roles)[i+1:]) or pool&(roles['estimator']|roles['interval_calibration']|held):
            raise ValueError('Source group assignments overlap numeric-fit or target groups')
        metadata.append({'region':region,'assigned_risk_groups':len(roles['risk_learning']),
                         'assigned_rule_groups':len(roles['rule_calibration']),'assigned_union_groups':len(pool)})
        files.extend([model,cal])
    paths=sorted(p for family in ['calendar','crossed'] for p in (INPUT/'whole_archive'/family/'forward').glob('replicate_*/*/open_source_receipt.json'))
    if len(paths)!=1640:raise ValueError('Forward candidate archive receipts are incomplete')
    files.extend(paths)
    if len(regions)!=6:raise ValueError('Unexpected forward region cohort')
    OUT.mkdir(parents=True,exist_ok=True)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc design after earlier source, target, risk and interval results have been examined; not a prospective registration',
          'source':'Use source single-year masked cases in the union of assigned risk-learning and rule-calibration connected groups, for each strict-held-region candidate model and mask family. Exclude all target-region and target connected groups, and require pre-2010 source observations. Numeric quantiles and their offsets use disjoint estimator and interval-calibration roles.',
          'classifier_independence':'Risk-learning groups trained an individual failure classifier in the existing model and may have trained the later exploratory classifier, but this sensitivity uses no risk score or publication selection. Explicitly perturb the stored classifier and check that annual quantiles remain unchanged.',
          'group_score':'For each source connected group, take the maximum of max(q05 - truth, truth - q95, 0) across its valid single-year masks. Require finite observed bound and finite projected interval.',
          'radius':'For G source groups, choose the ceil(0.9*(G+1))-th ordered group maximum; if that index exceeds G or radius is <=1e-8 C, report unsupported rather than a zero-width guarantee.',
          'application':'For both D2 and calibrated stochastic methods, expand q05 and q95 by the source radius and clamp the lower endpoint to the observed window bound. Compare on the same forward target cases with both methods and both original/candidate quantiles available; report a separate overlap with the earlier rule-only empirical correction.',
          'evaluation':'Report target annual coverage, width and 90% interval score, support/availability, case-weighted and equal-group changes, 4000 connected-group bootstrap draws, fixed-prediction leave-region-out sensitivity and counts of target groups whose every evaluated case is covered. Report outcome-defined hidden-peak strata only as retrospective.',
          'group_counts':metadata,'receipt_files':len(paths),
          'limitations':'Groups and target climates are not shown exchangeable; source cases use one-year masks while target archives are jointly degraded and group sizes differ. Prior target/source outcomes and other classifier analyses were already examined. Candidate provider roles and rights remain uncertain. The finite rank does not establish 90% group coverage or a validated joint trend distribution.',
          'privacy':'source group scores and individual target scores remain local; aggregate output only in candidate package',
          }
    path.write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen source union group-max sensitivity for six forward regions',flush=True)

if __name__=='__main__':main()
