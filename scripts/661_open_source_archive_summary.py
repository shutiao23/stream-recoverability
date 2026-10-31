#!/usr/bin/env python3
"""Summarize a complete candidate-provider strict-region archive reanalysis.

Refuses to summarize until all planned model and archive receipts exist. All
comparisons are retrospective and paired; no independent validation or new
source-specific causal effect is implied.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.archive import factorial_contrasts

ROOT = T.ROOT
REV = ROOT / 'results/wrr_review_response_20261027'
OUT = REV / 'open_source_sensitivity'
BASE = REV / 'whole_archive'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026'
KEY = ['family', 'mode', 'region', 'station_key', 'replicate', 'estimator', 'retention', 'dependence']

def main():
    plan = json.loads((OUT / 'plan.json').read_text())
    inputs = json.loads((OUT / 'candidate_input_integrity.json').read_text())
    if inputs['status'] != 'passed':
        raise ValueError('Both filtered source files require independent all-column verification')
    model_receipts = json.loads((PRIVATE / 'refit_receipts.json').read_text())
    expected_models = {x['mode']+'|'+x['region'] for x in plan['target_mode_region_stations']}
    if set(model_receipts) != expected_models:
        raise ValueError('All planned mode-region models must be refitted before pooled summary')
    archive = T.load_script('open_full_archive_verify', ROOT / 'scripts/658_open_source_archive_sensitivity.py')
    stage = PRIVATE / 'whole_archive'
    receipts = sorted(stage.glob('*/?*/replicate_*/*/open_source_receipt.json'))
    expected_settings = sum(x['stations'] for x in plan['target_mode_region_stations']) * 2 * 20
    if len(receipts) != expected_settings:
        raise ValueError(f'Only {len(receipts)} of {expected_settings} planned settings available')
    revised = []
    for p in receipts:
        rel = p.relative_to(stage)
        family, mode, replicate, station_folder = rel.parts[:4]
        original = BASE / family / mode / replicate / station_folder
        receipt = json.loads(p.read_text())
        current = p.parent
        old_design = json.loads((original / 'design.json').read_text())
        new_design = json.loads((current / 'design.json').read_text())
        if (old_design['masks'] != new_design['masks'] or
            old_design['station_key'] != new_design['station_key'] or
            new_design['hidden_values_present_in_visible_archive'] != 0):
            raise ValueError('Archive masks or hidden-target invariant changed: ' + str(rel))
        region = new_design['region']
        model_key = mode + '|' + region
        if model_key not in model_receipts:
            raise ValueError('Archive has no matching source model')
        split = 'before_2010' if mode == 'forward' else 'leave_one_year_out'
        model_path = PRIVATE / 'refits' / split / 'seed_00' / (region + '.joblib')
        calibration_path = PRIVATE / 'calibrations' / mode / (region + '.json')
        checks = {}
        if any(receipt.get(key) != value for key, value in checks.items()) or not receipt.get('same_masks') or receipt.get('hidden_target_values_present') != 0:
            raise ValueError('Archive receipt does not match input/output: ' + str(rel))
        archive.verify_plugin(original, current)
        revised.append(pd.read_csv(current / 'trends.csv'))
    new = pd.concat(revised, ignore_index=True)
    old = pd.read_csv(BASE / 'trends.csv')
    pair = old.merge(new, on=KEY, how='outer', suffixes=('_original', '_candidate'), indicator=True, validate='one_to_one')
    if not pair._merge.eq('both').all():
        raise ValueError('Pooled target trend identities differ')
    if not pair.independence_group_original.eq(pair.independence_group_candidate).all():
        raise ValueError('Connected-group identities differ between versions')
    plugin = pair.loc[pair.estimator.eq('plug_in') & pair.dependence.eq('point')]
    if not plugin.available_original.eq(plugin.available_candidate).all():
        raise ValueError('Unchanged plug-in availability differs')
    for col in ['n_retained', 'truth_slope', 'slope', 'error', 'squared_error']:
        if not np.allclose(plugin[col+'_original'], plugin[col+'_candidate'], atol=1e-8, rtol=0, equal_nan=True):
            raise ValueError('Unchanged plug-in field differs: ' + col)
    rows = []
    for keys, block in pair.groupby(['family', 'mode', 'estimator', 'retention', 'dependence'], sort=True):
        common = block.loc[block.available_original & block.available_candidate]
        row = dict(zip(['family', 'mode', 'estimator', 'retention', 'dependence'], keys))
        row |= {'n_eligible': len(block), 'n_original_available': int(block.available_original.sum()),
                'n_candidate_available': int(block.available_candidate.sum()), 'n_common': len(common),
                'n_common_stations': common.station_key.nunique(), 'n_common_groups': common.independence_group_original.nunique()}
        for col in ['error', 'squared_error', 'missing_coverage95', 'width95', 'interval_score95']:
            for version in ['original', 'candidate']:
                name = col+'_'+version
                row[version+'_'+col] = float(pd.to_numeric(common[name], errors='coerce').mean()) if len(common) else np.nan
        for version in ['original', 'candidate']:
            row[version+'_rmse'] = float(np.sqrt(row[version+'_squared_error'])) if np.isfinite(row[version+'_squared_error']) else np.nan
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / 'archive_paired_summary.csv', index=False)
    point = pair.loc[pair.retention.eq('all') & pair.dependence.eq('point')]
    index = ['family', 'mode', 'region', 'station_key', 'replicate']
    a = point.pivot(index=index, columns='estimator', values='squared_error_original')
    b = point.pivot(index=index, columns='estimator', values='squared_error_candidate')
    combined = a.join(b, lsuffix='_original', rsuffix='_candidate').reset_index()
    groups = point[index + ['independence_group_original']].drop_duplicates()
    if groups.duplicated(index).any():
        raise ValueError('Multiple connected groups for a paired target case')
    combined = combined.merge(groups, on=index, how='left', validate='one_to_one')
    comparison = []
    for offset, ((family, mode), block) in enumerate(combined.groupby(['family', 'mode'], sort=True)):
        cols = ['D2_original', 'stochastic_calibrated_original', 'D2_candidate', 'stochastic_calibrated_candidate']
        same = block.dropna(subset=cols)
        row = {'family': family, 'mode': mode, 'common_four_way_cases': len(same),
               'common_stations': same.station_key.nunique(), 'common_groups': same.independence_group_original.nunique()}
        for col in cols:
            row[col+'_rmse'] = float(np.sqrt(same[col].mean())) if len(same) else np.nan
        if len(same):
            cohort = same.assign(old_gap=same.D2_original-same.stochastic_calibrated_original,
                                 new_gap=same.D2_candidate-same.stochastic_calibrated_candidate)
            by_group = cohort.groupby('independence_group_original', sort=True).agg(
                old_sum=('old_gap', 'sum'), new_sum=('new_gap', 'sum'), n=('old_gap', 'size'))
            rng = np.random.default_rng(661 + offset)
            draws = rng.integers(len(by_group), size=(4000, len(by_group)))
            denominator = by_group.n.to_numpy()[draws].sum(axis=1)
            original_gap = by_group.old_sum.to_numpy()[draws].sum(axis=1) / denominator
            candidate_gap = by_group.new_sum.to_numpy()[draws].sum(axis=1) / denominator
            row['original_d2_minus_classical_mse'] = float(cohort.old_gap.mean())
            row['candidate_d2_minus_classical_mse'] = float(cohort.new_gap.mean())
            row['gap_change_bootstrap_low'], row['gap_change_bootstrap_high'] = map(float, np.quantile(candidate_gap-original_gap, [.025, .975]))
        comparison.append(row)
    pd.DataFrame(comparison).to_csv(OUT / 'archive_four_way_comparison.csv', index=False)
    # Compare factorial decompositions only when every cell is available in
    # both versions; ratios are ratios of aggregate mean contributions.
    fields = ['symmetric_retention', 'symmetric_estimator', 'total_gain', 'interaction']
    factorial_key = ['family', 'mode', 'station_key', 'replicate', 'estimator']
    def factorial(frame):
        point_rows = frame.loc[frame.dependence.eq('point') &
                               frame.estimator.isin(['plug_in', 'D2', 'stochastic_calibrated'])]
        return factorial_contrasts(point_rows)
    left, right = factorial(old), factorial(new)
    factors = left.merge(right, on=factorial_key, how='outer', suffixes=('_original', '_candidate'),
                         indicator=True, validate='one_to_one')
    if not factors._merge.eq('both').all():
        raise ValueError('Original and candidate factorial case identities differ')
    complete = factors.dropna(subset=[f'{field}_{version}' for field in fields for version in ['original', 'candidate']])
    factor_index = ['family', 'mode', 'station_key', 'replicate']
    factor_groups = groups.drop(columns='region')
    if factor_groups.duplicated(factor_index).any():
        raise ValueError('Factorial case has multiple connected-group identities')
    complete = complete.merge(factor_groups, on=factor_index, how='left', validate='many_to_one')
    factor_rows = []
    for (family, mode, estimator), block in complete.groupby(['family', 'mode', 'estimator'], sort=True):
        row = {'family': family, 'mode': mode, 'estimator': estimator, 'n_common': len(block),
               'n_stations': block.station_key.nunique(), 'n_groups': block.independence_group_original.nunique()}
        for version in ['original', 'candidate']:
            for field in fields:
                row[version+'_'+field] = float(block[field+'_'+version].mean())
            total = row[version+'_total_gain']
            row[version+'_retention_fraction'] = row[version+'_symmetric_retention']/total if abs(total) > 1e-12 else np.nan
        factor_rows.append(row)
    pd.DataFrame(factor_rows, columns=['family', 'mode', 'estimator', 'n_common', 'n_stations', 'n_groups'] +
        [version+'_'+name for version in ['original', 'candidate'] for name in fields + ['retention_fraction']]
    ).to_csv(OUT / 'archive_factorial_paired.csv', index=False)
    status = {'status': 'passed_complete_posthoc_sensitivity', 'planned_models': len(expected_models),
              'archive_settings': len(receipts), 'paired_trend_rows': len(pair),
              'same_masks_and_plugin_checked': True, 'hidden_target_values_present': 0,
              'connected_group_bootstrap_resamples': 4000,
              'limitations': plan['limitations'],
              'rights_status': 'Candidate provider licensing and all derived source, mask and model rights remain to be confirmed; case-level outputs and models remain local.'}
    (OUT / 'archive_summary_status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(pd.DataFrame(comparison).to_string(index=False))
    print(json.dumps(status, indent=2))

if __name__ == '__main__':
    main()
