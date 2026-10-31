#!/usr/bin/env python3
"""Replay fixed archive masks using candidate-provider strict-region refits.

Uses existing local daily features, masks and provider inputs. Original models
and results remain untouched. Paired results are post-hoc and cannot separate
source-provider exclusion, reassigned roles, and strict regional exclusion.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
os.umask(0o077)
import argparse
import json
import hashlib
from pathlib import Path
import shutil
import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T

ROOT = T.ROOT
SOURCE = ROOT / 'results/wrr_review_completion_20261024'
REV = ROOT / 'results/wrr_review_response_20261027'
BASE = REV / 'whole_archive'
OUT = REV / 'open_source_sensitivity'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026'
KEY = ['family', 'mode', 'region', 'station_key', 'replicate', 'estimator', 'retention', 'dependence']

def verify_bridge_dependencies(modes):
    """Require the separately reconstructed, post-hoc bridge dependencies."""
    report = json.loads((OUT / 'archive_bridge_repair_dependency.json').read_text())
    if (report.get('status') != 'passed'
            or not report.get('repaired_calibrations_match_saved')):
        raise ValueError('Post-hoc archive bridge dependency audit is missing or changed')
    required=[OUT/'plan.json',OUT/'single_year_calibration_plan.json',OUT/'archive_bridge_repair_effect.csv',
              ROOT/'scripts/731_open_archive_bridge_dependency.py']
    for mode in modes:
        split = 'before_2010' if mode == 'forward' else 'leave_one_year_out'
        path = SOURCE / 'repairs' / split / 'seed_00.parquet'
        required.append(path)
    for path in required:
        relative=str(path.relative_to(ROOT))
        expected=report.get('input_sha256',{}).get(relative)
        if not path.is_file() or path.is_symlink() or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Required archive bridge repair is missing or changed: ' + relative)

def verify_plugin(original, target):
    old = pd.read_csv(original / 'trends.csv')
    new = pd.read_csv(target / 'trends.csv')
    pair = old.merge(new, on=KEY, how='outer', suffixes=('_old', '_new'),
                     indicator=True, validate='one_to_one')
    if not pair._merge.eq('both').all():
        raise ValueError('Reanalysis trend case identities changed')
    baseline = pair.loc[pair.estimator.eq('plug_in') & pair.dependence.eq('point')]
    if (baseline.empty or
        not baseline.available_old.eq(baseline.available_new).all() or
        not np.allclose(baseline.error_old, baseline.error_new, atol=1e-8, rtol=0, equal_nan=True) or
        not np.allclose(baseline.truth_slope_old, baseline.truth_slope_new, atol=1e-8, rtol=0, equal_nan=True)):
        raise ValueError('Unchanged plug-in baseline or target reference differs')

def receipt_hashes(original,target,model_hash,calibration_hash):
    """Bind cached inputs and outputs to their actual content at generation."""
    return {'source_predictions_sha256':hashlib.sha256((original/'annual_predictions.parquet').read_bytes()).hexdigest(),
            'model_sha256':model_hash,'calibration_sha256':calibration_hash,
            'annual_predictions_sha256':hashlib.sha256((target/'annual_predictions.parquet').read_bytes()).hexdigest(),
            'trends_sha256':hashlib.sha256((target/'trends.csv').read_bytes()).hexdigest()}

def work(job, reference, replicate, mode, family, calibration, stage, model_hash, calibration_hash):
    target = stage / family / mode / f'replicate_{replicate:02d}' / job['station_key'].replace('|', '_')
    original = BASE / family / mode / f'replicate_{replicate:02d}' / job['station_key'].replace('|', '_')
    source = original / 'annual_predictions.parquet'
    if not source.is_file() or not (original / 'design.json').is_file():
        raise RuntimeError('Original daily features or mask design missing')
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = target / 'open_source_receipt.json'
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        expected = receipt_hashes(original,target,model_hash,calibration_hash)
        if (any(saved.get(k) != v for k, v in expected.items())
                or not saved.get('same_masks') or saved.get('hidden_target_values_present')!=0):
            raise ValueError('Cached reanalysis receipt mismatch')
        verify_plugin(original, target)
        return str(target)
    staged = target / 'annual_predictions.parquet'
    if staged.exists():
        pass
    else:
        shutil.copyfile(source, staged)
        staged.chmod(0o600)
    archive = T.load_script('open_archive_worker', ROOT / 'scripts/521_whole_archive.py')
    archive.SOURCE = PRIVATE
    archive.one(job, reference, replicate, mode, family, calibration, stage, 256, False, True, 'baseline')
    old = json.loads((original / 'design.json').read_text())
    new = json.loads((target / 'design.json').read_text())
    if old['masks'] != new['masks'] or old['station_key'] != new['station_key'] or new['hidden_values_present_in_visible_archive'] != 0:
        raise ValueError('Reanalysis changed masks or exposed hidden values')
    verify_plugin(original, target)
    saved = {'same_masks': True, 'hidden_target_values_present': 0}
    saved.update(receipt_hashes(original,target,model_hash,calibration_hash))
    receipt.write_text(json.dumps(saved, indent=2) + '\n')
    receipt.chmod(0o600)
    return str(target)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['forward', 'offline', 'both'], default='both')
    p.add_argument('--region', help='Optional pilot region')
    p.add_argument('--replicates', type=int, default=20)
    p.add_argument('--workers', type=int, default=2)
    args = p.parse_args()
    if not 1 <= args.replicates <= 20 or args.workers < 1:
        raise ValueError('Invalid replicate or worker count')
    plan = json.loads((OUT / 'plan.json').read_text())
    receipts = json.loads((PRIVATE / 'refit_receipts.json').read_text())
    modes = ['offline', 'forward'] if args.mode == 'both' else [args.mode]
    verify_bridge_dependencies(modes)
    planned = [x for x in plan['target_mode_region_stations'] if x['mode'] in modes and not args.region or x['region'] == args.region]
    if not planned:
        raise ValueError('No matching planned target region')
    strict = T.load_script('open_archive_roles', ROOT / 'scripts/610_strict_region_refit.py').strict_module()
    strict.OUT = PRIVATE
    analysis = T.load_script('open_archive_bridge_repair', ROOT / 'scripts/467_review_completion_analysis.py')
    archive = T.load_script('open_archive_calibration', ROOT / 'scripts/521_whole_archive.py')
    core = T.load_script('open_archive_jobs', ROOT / 'scripts/431_tr_cases.py')
    reference = pd.read_parquet(SOURCE / 'cases/leave_one_year_out/seed_00.parquet',
        columns=['station_key', 'region', 'independence_group', 'year', 'design_family', 'mask_runs', 'h30__policy', 'eval_truth_h30'])
    old = pd.read_csv(BASE / 'trends.csv')
    all_jobs = core.jobs_for('source')
    stage = PRIVATE / ('whole_archive' if args.replicates == 20 else f'whole_archive_pilot_{args.replicates}')
    stage.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in planned:
        mode, region = item['mode'], item['region']
        key = mode + '|' + region
        split = 'before_2010' if mode == 'forward' else 'leave_one_year_out'
        model = PRIVATE / 'refits' / split / 'seed_00' / (region + '.joblib')
        candidate_path = PRIVATE / 'candidate_cases' / split / 'seed_00.parquet'
        if key not in receipts:
            raise ValueError('Missing model or source receipt: ' + key)
        source = pd.read_parquet(candidate_path)
        if not set(source.provider).issubset(set(plan['allowed_providers'])):
            raise ValueError('Candidate source provider changed')
        source = analysis.apply_bridge_repairs(source, 0, split)
        bundle = joblib.load(model)
        calibration = archive.classical_calibration(source, region, strict)
        calibration['D2_offsets'], calibration['D2_calibration_groups'] = archive.recalibrate_d2(source, region, strict, bundle)
        calpath = PRIVATE / 'calibrations' / mode / (region + '.json')
        calpath.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        text = json.dumps(calibration, indent=2) + '\n'
        if calpath.exists():
            if json.loads(calpath.read_text()) != calibration:
                raise ValueError('Existing calibration differs; preserve original')
        else:
            calpath.write_text(text)
            calpath.chmod(0o600)
        stations = set(old.loc[old['mode'].eq(mode) & old.region.eq(region), 'station_key'])
        jobs = [j for j in all_jobs if j['station_key'] in stations]
        if set(j['station_key'] for j in jobs) != stations or len(stations) != item['stations']:
            raise ValueError('Target station roster differs from plan')
        model_hash=hashlib.sha256(model.read_bytes()).hexdigest()
        calibration_hash=hashlib.sha256(calpath.read_bytes()).hexdigest()
        tasks = [(job, reference.loc[reference.station_key.eq(job['station_key']) & reference.design_family.eq(family)],
                  rep, mode, family, calibration, stage,
                  model_hash,calibration_hash)
                 for job in jobs for family in ['calendar', 'crossed'] for rep in range(args.replicates)]
        print('Replaying', key, len(tasks), 'archive settings', flush=True)
        Parallel(n_jobs=args.workers, verbose=10)(delayed(work)(*task) for task in tasks)
    print('Requested archive settings complete; case outputs remain local.', flush=True)

if __name__ == '__main__':
    main()
