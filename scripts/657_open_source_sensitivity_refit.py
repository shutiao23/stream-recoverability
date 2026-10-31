#!/usr/bin/env python3
"""Fit strictly held-region source models on candidate permissible providers.

All artifacts remain local pending source/derivative permission review. This is
a post-hoc sensitivity, not a replacement for the original primary analysis.
"""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
os.umask(0o077)
import argparse
import json
from pathlib import Path
import subprocess
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

ROOT = T.ROOT
SOURCE = ROOT / 'results/wrr_review_completion_20261024'
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['forward', 'offline', 'both'], default='both')
    parser.add_argument('--region', help='Optional pilot region; default processes every target region')
    args = parser.parse_args()
    check = subprocess.run(['git', 'check-ignore', '-q', str(PRIVATE.relative_to(ROOT)) + '/probe'], cwd=ROOT)
    if check.returncode:
        raise RuntimeError('Local sensitivity directory must be git-ignored')
    plan = json.loads((OUT / 'plan.json').read_text())
    if plan.get('status') != 'posthoc_design_frozen_before_new_predictions':
        raise ValueError('Sensitivity design is not frozen')
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    receipt_path = PRIVATE / 'refit_receipts.json'
    receipts = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    module = T.load_script('open_strict_module_factory', ROOT / 'scripts/610_strict_region_refit.py').strict_module()
    module.OUT = PRIVATE
    modes = ['offline', 'forward'] if args.mode == 'both' else [args.mode]
    allowed = set(plan['allowed_providers'])
    for mode in modes:
        split = 'before_2010' if mode == 'forward' else 'leave_one_year_out'
        original_path = SOURCE / 'cases' / split / 'seed_00.parquet'
        dest = PRIVATE / 'candidate_cases' / split / 'seed_00.parquet'
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not dest.exists():
            source = pd.read_parquet(original_path)
            source = source.loc[source.provider.isin(allowed)].copy()
            if source.groupby('network_id').provider.nunique().gt(1).any() or source.groupby('independence_group').provider.nunique().gt(1).any():
                raise ValueError('Filtered source mixes provider in network/group')
            source.to_parquet(dest, index=False)
            dest.chmod(0o600)
        c = pd.read_parquet(dest)
        c = c.loc[c.policy_choice.ne('unavailable') & c.eval_truth_h30.notna()].reset_index(drop=True)
        if set(c.provider) - allowed or len(c) != plan['splits'][split]['candidate_case_rows_after_filter']:
            raise ValueError('Filtered source rows do not match plan')
        source_regions = sorted(c.region.unique())
        region_plan = [item['region'] for item in plan['target_mode_region_stations'] if item['mode'] == mode]
        if args.region:
            if args.region not in region_plan:
                raise ValueError('Pilot region absent from mode')
            region_plan = [args.region]
        for region in region_plan:
            seed = plain_seed(7, 0, source_regions.index(region))
            held, roles, weights = module.roles(c, region, seed)
            same_region = c.region.eq(region).to_numpy()
            if not np.any(held):
                raise ValueError('Target region has no held cases')
            for name, weight in weights.items():
                if np.any(np.asarray(weight)[same_region] > 0) or not np.any(np.asarray(weight) > 0):
                    raise ValueError('Invalid strict-region source role: ' + name)
            key = mode + '|' + region
            model = PRIVATE / 'refits' / split / 'seed_00' / (region + '.joblib')
            if model.exists():
                if key not in receipts:
                    raise ValueError('Existing model has no matching source receipt')
            print('Refitting', mode, region, 'source cases', len(c), flush=True)
            module.fit_region(0, region, split, str(dest))
            if not model.is_file():
                raise RuntimeError('Expected model was not saved')
            bundle = joblib.load(model)
            if bundle['roles'] != roles:
                raise ValueError('Saved role assignments differ')
            receipts[key] = {'held_case_rows': int(np.asarray(held).sum()),
                             'source_positive_case_rows': {k: int((np.asarray(w) > 0).sum()) for k, w in weights.items()},
                             'source_positive_groups': {k: int(c.loc[np.asarray(w) > 0, 'independence_group'].nunique()) for k, w in weights.items()},
                             'strict_target_region_positive_rows': 0, 'excluded_providers_present': False}
            receipt_path.write_text(json.dumps(receipts, indent=2) + '\n')
            receipt_path.chmod(0o600)
            print('Saved verified model', key, flush=True)
    print(json.dumps({'local_models_ready': len(receipts), 'planned_models': len(plan['target_mode_region_stations']),
                      'status': 'refits_in_progress' if len(receipts) < len(plan['target_mode_region_stations']) else 'refits_complete'}, indent=2))

if __name__ == '__main__':
    main()
