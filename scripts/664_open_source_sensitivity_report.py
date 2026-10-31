#!/usr/bin/env python3
"""Render the completed post-hoc candidate-source archive sensitivity."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
PAPER = ROOT / 'paper/wrr_tr'


def main():
    status = json.loads((OUT / 'archive_summary_status.json').read_text())
    if status['status'] != 'passed_complete_posthoc_sensitivity' or status['planned_models'] != 13 or status['archive_settings'] != 3320:
        raise ValueError('Complete, checked candidate-source sensitivity required')
    roles = json.loads((OUT / 'candidate_source_role_audit.json').read_text())
    if roles['status'] != 'passed' or roles['models_checked'] != 13 or roles['positive_target_region_rows'] or roles['post_2009_forward_source_rows']:
        raise ValueError('Independent candidate source-role audit failed')
    summary_audit = json.loads((OUT / 'independent_summary_audit.json').read_text())
    if (summary_audit['status'] != 'passed' or summary_audit['four_way_cells_checked'] != 4 or
        summary_audit['factorial_cells_checked'] != 8 or summary_audit['group_bootstrap_cells_checked'] != 4):
        raise ValueError('Independent paired summary audit failed')
    comparison = pd.read_csv(OUT / 'archive_four_way_comparison.csv')
    factor = pd.read_csv(OUT / 'archive_factorial_paired.csv')
    paired = pd.read_csv(OUT / 'archive_paired_summary.csv')
    if len(comparison) != 4 or comparison.duplicated(['family', 'mode']).any() or len(factor) != 8:
        raise ValueError('Missing or duplicate comparisons')
    coverage = paired.loc[paired.estimator.eq('D2') & paired.retention.eq('all') & paired.dependence.eq('independent')]
    if len(coverage) != 4 or coverage.duplicated(['family', 'mode']).any():
        raise ValueError('Missing D2 trend coverage cells')
    required = ['D2_original_rmse', 'stochastic_calibrated_original_rmse', 'D2_candidate_rmse', 'stochastic_calibrated_candidate_rmse']
    if not np.isfinite(comparison[required].to_numpy()).all():
        raise ValueError('Four-way comparison is not estimable')
    reference = pd.read_csv(ROOT / 'results/wrr_review_response_20261027/whole_archive/paired_trend_estimators.csv')
    reference = reference.loc[reference.left.eq('D2') & reference.right.eq('stochastic_calibrated')]
    checked = comparison.merge(reference, on=['family', 'mode'], validate='one_to_one')
    if (len(checked) != 4 or not checked.common_four_way_cases.eq(checked.n_common).all() or
        not np.allclose(checked.D2_original_rmse, checked.left_rmse, rtol=0, atol=1e-10) or
        not np.allclose(checked.stochastic_calibrated_original_rmse, checked.right_rmse, rtol=0, atol=1e-10)):
        raise ValueError('Four-way common original comparator does not reproduce published summary')
    original_factor = pd.read_csv(ROOT / 'results/wrr_review_response_20261027/whole_archive/factorial_paired_summary.csv')
    checked_factor = factor.merge(original_factor, on=['family', 'mode', 'estimator'], validate='one_to_one')
    if (len(checked_factor) != 8 or not checked_factor.n_common.eq(checked_factor.n_paired).all() or
        not np.allclose(checked_factor.original_symmetric_retention, checked_factor.retention, atol=1e-10, rtol=0) or
        not np.allclose(checked_factor.original_total_gain, checked_factor.total_gain, atol=1e-10, rtol=0)):
        raise ValueError('Original paired factorial does not reproduce published summary')
    cross = comparison.loc[comparison.family.eq('crossed') & comparison['mode'].eq('forward')].iloc[0]
    cross_factor = factor.loc[factor.family.eq('crossed') & factor['mode'].eq('forward') & factor.estimator.eq('D2')].iloc[0]
    cross_coverage = coverage.loc[coverage.family.eq('crossed') & coverage['mode'].eq('forward')].iloc[0]
    values = {'OpenSourcePairs': str(int(cross.common_four_way_cases)),
              'OpenSourceGroups': str(int(cross.common_groups)),
              'OpenSourceOldDTwo': f'{cross.D2_original_rmse:.5f}',
              'OpenSourceOldClassic': f'{cross.stochastic_calibrated_original_rmse:.5f}',
              'OpenSourceNewDTwo': f'{cross.D2_candidate_rmse:.5f}',
              'OpenSourceNewClassic': f'{cross.stochastic_calibrated_candidate_rmse:.5f}',
              'OpenSourceFactorCases': str(int(cross_factor.n_common)),
              'OpenSourceOldRetention': f'{100*cross_factor.original_retention_fraction:.1f}',
              'OpenSourceNewRetention': f'{100*cross_factor.candidate_retention_fraction:.1f}',
              'OpenSourceCoverageCases': str(int(cross_coverage.n_common)),
              'OpenSourceOldCoverage': f'{100*cross_coverage.original_missing_coverage95:.1f}',
              'OpenSourceNewCoverage': f'{100*cross_coverage.candidate_missing_coverage95:.1f}'}
    (PAPER / 'open_source_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k, v in values.items()))
    lines = [r'\section{Candidate-provider, strict-region source sensitivity}',
        ('After observing the original results and LUBW source dependence, we refitted all '
         '13 whole-archive source models on seven candidate providers with recorded reuse paths. '
         'Role assignments and bootstrap draws were recomputed using the filtered data, and every group '
         'occurring in the target region was excluded from source roles. An independent role recount '
         'found no positive-weight target-region source case or post-2009 forward source case. Original target masks and '
         'daily features were reused. All 3,320 archive settings, masks and the unchanged plug-in '
         'baselines were checked. Removing providers, changing source assignments and strict regional '
         'exclusion jointly change the analysis; the result is not a causal attribution to one of them. '
         'The filtered inputs remain processed study data, not provider-native raw records. This '
         'after-the-fact sensitivity neither establishes legal redistribution rights nor independent '
         'climate transfer, and it does not replace the original analysis.'),
        r'\begin{table}[p]\centering\footnotesize',
        r'\caption{Trend RMSE in $^{\circ}$C per decade on the four-way common cases: both methods and both source-model versions must be available. Repetitions are not independent climates.}\label{tab:source-filter-comparison}',
        r'\begin{tabular}{llrrrrrr}\toprule',
        r'Family & Mode & Cases & Groups & D2 orig. & Class. orig. & D2 cand. & Class. cand.\\\midrule']
    for row in comparison.sort_values(['family','mode']).itertuples():
        lines.append(f'{row.family} & {row.mode} & {int(row.common_four_way_cases)} & {int(row.common_groups)} & {row.D2_original_rmse:.5f} & {row.stochastic_calibrated_original_rmse:.5f} & {row.D2_candidate_rmse:.5f} & {row.stochastic_calibrated_candidate_rmse:.5f}' + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}',
        r'\begin{table}[p]\centering\footnotesize',
        r'\caption{Nominal 95\% D2 trend-interval results on cases where both versions are available. Width is in $^{\circ}$C per decade; this comparison is descriptive and the selected cases may differ from the four-way point cohort.}\label{tab:source-filter-coverage}',
        r'\begin{tabular}{llrrrrr}\toprule',
        r'Family & Mode & Cases & Cover orig. & Cover cand. & Width orig. & Width cand.\\\midrule']
    for row in coverage.sort_values(['family','mode']).itertuples():
        lines.append(f'{row.family} & {row.mode} & {int(row.n_common)} & {100*row.original_missing_coverage95:.1f}\\% & {100*row.candidate_missing_coverage95:.1f}\\% & {row.original_width95:.3f} & {row.candidate_width95:.3f}' + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}',
              ('A descriptive connected-group bootstrap resamples the same groups for both source '
               'versions and both estimators. It does not establish independent climates or a '
               'population transfer guarantee. The corresponding paired MSE differences and '
               'bootstrap intervals are supplied with the candidate-source summary.'),
              r'\begin{table}[p]\centering\small',
              r'\caption{Symmetric MSE decomposition on cases with all four retention-by-estimator cells available under both versions. Fractions divide the mean retention contribution by mean total improvement; they are not causal or universal.}\label{tab:source-filter-factorial}',
              r'\begin{tabular}{lllrrrr}\toprule',
              r'Family & Mode & Estimator & Cases & Groups & Original fraction & Candidate fraction\\\midrule']
    for row in factor.sort_values(['family','mode','estimator']).itertuples():
        original = f'{row.original_retention_fraction:.3f}' if np.isfinite(row.original_retention_fraction) else '--'
        candidate = f'{row.candidate_retention_fraction:.3f}' if np.isfinite(row.candidate_retention_fraction) else '--'
        estimator = 'classical' if row.estimator == 'stochastic_calibrated' else row.estimator
        lines.append(f'{row.family} & {row.mode} & {estimator} & {int(row.n_common)} & {int(row.n_groups)} & {original} & {candidate}' + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}']
    (PAPER / 'open_source_sensitivity_supporting.tex').write_text('\n'.join(lines) + '\n')
    report = {'status': 'passed', 'models': status['planned_models'], 'archive_settings': status['archive_settings'],
              'four_way_cells': len(comparison), 'factorial_cells': len(factor), 'coverage_cells': len(coverage),
              'source_role_audit': roles['status'], 'independent_summary_audit': summary_audit['status'],
              'original_point_and_factorial_summaries_reproduced': True,
              'limitations': status['limitations'], 'rights_status': status['rights_status']}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
