#!/usr/bin/env python3
"""Independently recount source roles of candidate-provider strict-region models.

Checks assignments, positive weights, held-region groups and forward source
years against local cached inputs and saved bundles. Output contains aggregate
counts only; no observation values or per-case predictions are exported.
"""
from __future__ import annotations
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

ROOT = T.ROOT
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026'

def main():
    plan = json.loads((OUT / 'plan.json').read_text())
    integrity = json.loads((OUT / 'candidate_input_integrity.json').read_text())
    if integrity['status'] != 'passed':
        raise ValueError('Candidate inputs have not passed independent all-column verification')
    receipts = json.loads((PRIVATE / 'refit_receipts.json').read_text())
    expected = {x['mode']+'|'+x['region'] for x in plan['target_mode_region_stations']}
    if set(receipts) != expected:
        raise ValueError('Not all source model receipts are present')
    base = T.load_script('open_independent_original_roles', ROOT / 'scripts/466_review_completion_refit.py')
    rows = []
    for mode, split in [('offline', 'leave_one_year_out'), ('forward', 'before_2010')]:
        path = PRIVATE / 'candidate_cases' / split / 'seed_00.parquet'
        columns = ['provider', 'station_key', 'region', 'independence_group', 'year', 'policy_choice', 'eval_truth_h30']
        if 'training_partition' in pq.ParquetFile(path).schema.names:
            columns.append('training_partition')
        cases = pd.read_parquet(path, columns=columns)
        cases = cases.loc[cases.policy_choice.ne('unavailable') & cases.eval_truth_h30.notna()].reset_index(drop=True)
        if not set(cases.provider).issubset(set(plan['allowed_providers'])):
            raise ValueError('Disallowed provider in candidate source')
        regions = sorted(cases.region.unique())
        for item in [x for x in plan['target_mode_region_stations'] if x['mode'] == mode]:
            region = item['region']; key = mode+'|'+region
            held, assigned, weights = base.roles(cases, region, plain_seed(7, 0, regions.index(region)))
            forbidden = set(cases.loc[cases.region.eq(region), 'independence_group'])
            forbidden_rows = cases.independence_group.isin(forbidden).to_numpy()
            expected_roles = {role: [group for group in groups if group not in forbidden] for role, groups in assigned.items()}
            model_path = PRIVATE / 'refits' / split / 'seed_00' / (region+'.joblib')
            model = joblib.load(model_path)
            if model['roles'] != expected_roles:
                raise ValueError('Saved model roles differ from independent recomputation: '+key)
            held_groups = set(cases.loc[np.asarray(held), 'independence_group'])
            for role, group_list in expected_roles.items():
                adjusted = np.where(forbidden_rows, 0., np.asarray(weights[role], float))
                positive = adjusted > 0
                if len(group_list) < 2 or not positive.any() or set(group_list) & forbidden or set(cases.loc[positive, 'independence_group']) & held_groups:
                    raise ValueError('Strict role or held group exclusion failed: '+key+'/'+role)
                if np.any(positive & cases.region.eq(region).to_numpy()):
                    raise ValueError('Target-region case has positive source weight')
                if mode == 'forward' and (cases.loc[positive, 'year'] >= 2010).any():
                    raise ValueError('Forward source case violates pre-2010 cutoff')
                nrows = int(positive.sum()); ngroups = int(cases.loc[positive, 'independence_group'].nunique())
                if nrows != receipts[key]['source_positive_case_rows'][role] or ngroups != receipts[key]['source_positive_groups'][role]:
                    raise ValueError('Receipt source role counts differ')
                rows.append({'mode': mode, 'region': region, 'role': role, 'positive_case_rows': nrows,
                             'positive_groups': ngroups, 'positive_target_region_rows': 0,
                             'positive_disallowed_provider_rows': 0,
                             'post_2009_forward_source_rows': 0 if mode == 'forward' else None})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / 'candidate_source_role_audit.csv', index=False)
    status = {'status': 'passed', 'models_checked': len(expected), 'roles_checked': len(frame),
              'positive_target_region_rows': 0, 'positive_disallowed_provider_rows': 0,
              'post_2009_forward_source_rows': 0,
              'limitation': 'Source input filtering, role assignment, weights, and year cutoff only; does not independently rebuild daily features, provider data quality, missingness mechanisms, or legal derivative permissions.'}
    (OUT / 'candidate_source_role_audit.json').write_text(json.dumps(status, indent=2)+'\n')
    print(json.dumps(status, indent=2))

if __name__ == '__main__':
    main()
