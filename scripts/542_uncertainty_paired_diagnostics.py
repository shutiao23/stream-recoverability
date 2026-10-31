#!/usr/bin/env python3
"""Put annual fit, tail, and coupling sensitivities on a common archive cohort.

This is an evaluation diagnostic, not a causal decomposition of miscoverage.
The tail contrast and coupling contrast use different randomized draw sequences;
comparisons are paired within each contrast, not between these experiments.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/whole_archive'
KEY = ['family', 'mode', 'estimator', 'station_key', 'replicate']
METRICS = ['coverage95', 'width95', 'interval_score95']


def summarize_common(annual, trends, tails):
    a = annual.loc[annual.estimator.isin(['D2', 'stochastic_calibrated'])].copy()
    if a.duplicated(KEY).any():
        raise ValueError('Annual keys are not unique')
    t = trends.loc[trends.retention.eq('all') & trends.dependence.isin(
        ['independent', 'shared_parameters', 'residual_blocks'])].copy()
    t['coverage95'] = t.missing_coverage95
    if t.duplicated(KEY + ['dependence']).any() or tails.duplicated(KEY + ['tails']).any():
        raise ValueError('Treatment keys are not unique')
    total = a.groupby(['family', 'mode', 'estimator']).size().rename('n_all').reset_index()
    common = a.copy()
    for dep in ['independent', 'shared_parameters', 'residual_blocks']:
        x = t.loc[t.dependence.eq(dep) & t.available, KEY + METRICS].rename(
            columns={m: f'{dep}_{m}' for m in METRICS})
        common = common.merge(x, on=KEY, how='inner', validate='one_to_one')
    for tail in ['constant', 'normal']:
        x = tails.loc[tails.tails.eq(tail), KEY + METRICS].rename(
            columns={m: f'{tail}_{m}' for m in METRICS})
        common = common.merge(x, on=KEY, how='inner', validate='one_to_one')
    required = [f'{method}_{metric}' for method in
                ['independent', 'shared_parameters', 'residual_blocks', 'constant', 'normal'] for metric in METRICS]
    common = common.loc[common[required + ['coverage90', 'width90', 'mae']].notna().all(axis=1)
                        & common.n_eligible.gt(0) & common.n_available.eq(common.n_eligible)].copy()
    for c in required:
        common[c] = pd.to_numeric(common[c], errors='raise').astype(float)
    records, contrasts = [], []
    for group_key, group in common.groupby(['family', 'mode', 'estimator'], sort=True):
        family, mode, estimator = group_key
        n = int(total.loc[total.family.eq(family) & total['mode'].eq(mode) & total.estimator.eq(estimator), 'n_all'].iloc[0])
        base = dict(family=family, mode=mode, estimator=estimator, n_all=n, n_common=len(group),
                    fraction_common=len(group)/n, stations=group.station_key.nunique(),
                    groups=group.independence_group.nunique(), incomplete_years=int(group.n_eligible.sum()))
        records.append(base | dict(
            annual_coverage90_weighted=float(np.average(group.coverage90, weights=group.n_eligible)),
            annual_coverage90_station_replicate=float(group.coverage90.mean()),
            annual_mae_weighted=float(np.average(group.mae, weights=group.n_eligible)),
            annual_width90_weighted=float(np.average(group.width90, weights=group.n_eligible)),
            **{f'{method}_{metric}': float(group[f'{method}_{metric}'].mean())
               for method in ['independent', 'shared_parameters', 'residual_blocks', 'constant', 'normal']
               for metric in METRICS}))
        rng = np.random.default_rng(542)
        clusters = group.independence_group.drop_duplicates().to_numpy()
        # Sample connected groups with replacement; pooled mean gives each case
        # its observed weight, while preserving within-group dependence.
        for contrast, left, right in [('normal_minus_constant', 'normal', 'constant'),
                                      ('shared_minus_independent', 'shared_parameters', 'independent'),
                                      ('blocks_minus_independent', 'residual_blocks', 'independent')]:
            for metric in METRICS:
                diffs = group[f'{left}_{metric}'] - group[f'{right}_{metric}']
                sums = pd.DataFrame({'group': group.independence_group, 'difference': diffs}).groupby('group').difference.agg(['sum', 'size']).reindex(clusters)
                draws = rng.integers(0, len(clusters), size=(2000, len(clusters)))
                boot = sums['sum'].to_numpy()[draws].sum(axis=1) / sums['size'].to_numpy()[draws].sum(axis=1)
                lo, hi = np.quantile(boot, [.025, .975])
                contrasts.append(base | dict(contrast=contrast, metric=metric, difference=float(diffs.mean()),
                                              cluster_bootstrap_lower=float(lo), cluster_bootstrap_upper=float(hi)))
    return common, pd.DataFrame(records), pd.DataFrame(contrasts), total


def main():
    annual = pd.read_csv(OUT / 'annual.csv')
    trends = pd.read_csv(OUT / 'trends.csv')
    tails = pd.read_csv(OUT / 'quantile_tail_sensitivity.csv')
    common, summary, contrasts, total = summarize_common(annual, trends, tails)
    common.to_csv(OUT / 'uncertainty_common_cases.csv', index=False)
    summary.to_csv(OUT / 'uncertainty_paired_summary.csv', index=False)
    contrasts.to_csv(OUT / 'uncertainty_paired_contrasts.csv', index=False)
    represented = summary[['family', 'mode', 'estimator', 'n_common']]
    total = total.merge(represented, on=['family','mode','estimator'], how='left').fillna({'n_common': 0})
    total.to_csv(OUT / 'uncertainty_cohort_availability.csv', index=False)
    (OUT / 'uncertainty_paired_design.json').write_text(json.dumps({
      'unit': 'station and masked-archive repetition',
      'common_cohort': 'all annual values and all three coupling and both tail sensitivity outputs available',
      'annual_weighting': 'weighted by number of incomplete reference years; also report station-repetition mean',
      'tail_contrast': 'constant vs normal spacing with identical marginals except outside observed quantile levels, same random order within tail experiment',
      'coupling_contrast': 'same normal-tailed marginal draws re-ranked by independent, auxiliary shared-parameter, or residual-block ranks',
      'caution': 'tail experiment and coupling experiment use distinct random draws; annual fit is not experimentally corrected; these are not additive causal contributions',
      'bootstrap': '2000 resamples of connected groups, pooled-case mean, descriptive and not a guarantee; 18 groups at most',
      'scope': 'retrospective finite archive, repeated masks within stations; full source models and observed data are needed for reproduction'
    }, indent=2) + '\n')
    row = summary.loc[summary.family.eq('crossed') & summary['mode'].eq('forward') & summary.estimator.eq('D2')].iloc[0]
    tex = {
        'UCCommon': str(int(row.n_common)), 'UCAll': str(int(row.n_all)),
        'UCStations': str(int(row.stations)), 'UCGroups': str(int(row.groups)),
        'UCAnnual': f"{100*row.annual_coverage90_weighted:.1f}",
        'UCAnnualEqual': f"{100*row.annual_coverage90_station_replicate:.1f}",
        'UCTailConstant': f"{100*row.constant_coverage95:.1f}",
        'UCTailNormal': f"{100*row.normal_coverage95:.1f}",
        'UCTailWidthConstant': f"{row.constant_width95:.3f}",
        'UCTailWidthNormal': f"{row.normal_width95:.3f}",
        'UCTailScoreConstant': f"{row.constant_interval_score95:.3f}",
        'UCTailScoreNormal': f"{row.normal_interval_score95:.3f}",
        'UCIndependent': f"{100*row.independent_coverage95:.1f}",
        'UCShared': f"{100*row.shared_parameters_coverage95:.1f}",
        'UCBlocks': f"{100*row.residual_blocks_coverage95:.1f}",
        'UCIndependentScore': f"{row.independent_interval_score95:.3f}",
        'UCSharedScore': f"{row.shared_parameters_interval_score95:.3f}",
        'UCBlocksScore': f"{row.residual_blocks_interval_score95:.3f}",
    }
    (ROOT / 'paper/wrr_tr/uncertainty_paired_values.tex').write_text(
        ''.join('\\newcommand{\\' + name + '}{' + value + '}\n' for name, value in tex.items()))
    print(summary.to_string(index=False))
    print(contrasts.query("family == 'crossed' and mode == 'forward' and estimator == 'D2'").to_string(index=False))

if __name__ == '__main__':
    main()
