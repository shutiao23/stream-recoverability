#!/usr/bin/env python3
"""Freeze exploratory annual expansion from group-disjoint single-year cases.

Source eligibility and support are fixed without examining calibration residuals
or target outcomes. The experiment is retrospective and not registered.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
import joblib
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026'
ALPHA=.1

def main():
    target=OUT/'single_year_calibration_plan.json'
    if target.exists():raise RuntimeError('Preserve the existing frozen plan')
    role=json.loads((OUT/'candidate_source_role_audit.json').read_text())
    annual=json.loads((OUT/'annual_sensitivity_status.json').read_text())
    if role['status']!='passed' or role['models_checked']!=13 or annual['status']!='passed':
        raise ValueError('Complete source role and target annual audits first')
    original=json.loads((OUT/'plan.json').read_text()); receipts=json.loads((PRIVATE/'refit_receipts.json').read_text())
    models=[];hashes={}
    for item in original['target_mode_region_stations']:
        mode,region=item['mode'],item['region'];split='before_2010' if mode=='forward' else 'leave_one_year_out'; key=mode+'|'+region
        source=PRIVATE/'candidate_cases'/split/'seed_00.parquet'
        model=PRIVATE/'refits'/split/'seed_00'/(region+'.joblib');cal=PRIVATE/'calibrations'/mode/(region+'.json')
        bundle=joblib.load(model);roles=bundle['roles'];rule=set(roles['rule_calibration'])
        if any(rule & set(roles[name]) for name in ['estimator','interval_calibration','risk_learning']):
            raise ValueError('Rule calibration role overlaps source fitting roles')
        # This is an upper bound: groups with no usable cases cannot calibrate.
        models.append({'mode':mode,'region':region,'assigned_rule_groups':len(rule),
                       'finite_90pct_group_max_possible':len(rule)>=9})
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc_frozen_before_single_year_source_residuals',
          'model_roles':models,
          'source':'Every valid calendar or controlled-gap single-year source case assigned to the disjoint rule-calibration role. For forward source cases require training_partition=train and year<2010. Exclude any target-region group; no target outcome is used to choose cases, residuals or radii.',
          'adjustment':'For each mode, region, family and estimator, use equal-group weighted empirical 90th percentile of nonnegative interval miss distance. Require at least three observed groups and a strictly positive correction; otherwise mark unsupported. Preserve the observed lower bound. A separate one-maximum-per-group finite-rank threshold is reported only if at least nine groups contribute; it is not applied.',
          'evaluation':'Compare original and adjusted annual 90% intervals on the identical four-way common target cases, report supported fraction and paired coverage, width and interval score alongside all-case baseline, including outcome-defined peak visibility strata.',
          'limitations':'Source cases hide one year at a time whereas the target has jointly degraded archives; source and target difficulty and climatology need not match. The empirical correction has no finite-sample or climate-transfer guarantee. This follow-up was designed after earlier results, does not create a new joint trend distribution, and does not resolve source rights.'}
    target.write_text(json.dumps(plan,indent=2)+'\n')
    print(pd.DataFrame(models).to_string(index=False));print(json.dumps({k:v for k,v in plan.items() if k not in ['source_and_code_hashes','model_roles']},indent=2))

if __name__=='__main__':main()
