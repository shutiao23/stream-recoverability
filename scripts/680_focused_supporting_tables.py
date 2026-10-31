#!/usr/bin/env python3
"""Render core source-comparison tables for the focused supporting file."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; REV=ROOT/'results/wrr_review_response_20261027';PAPER=ROOT/'paper/wrr_tr'


def fmt(x,digits=3,percent=False):
    if pd.isna(x):return '--'
    return f'{100*x:.1f}\\%' if percent else f'{x:.{digits}f}'


def main():
    scores=pd.read_csv(REV/'annual/source_scorecard_summary.csv')
    score=scores.loc[scores.stratum.eq('danger')&scores.estimator.isin(['plug_in','functional_debias','distribution_regression','stochastic_regression_calibrated'])]
    if len(score)!=8 or not score.n_seeds.eq(20).all() or score.duplicated(['family','estimator']).any():raise ValueError('Annual scorecard scope differs')
    source=pd.read_csv(REV/'release_outputs/source_calibrated_release_summary.csv')
    if len(source)!=4 or source.duplicated(['family','method']).any():raise ValueError('Source release summary scope differs')
    matched=pd.read_csv(REV/'release_outputs/matched_numerical_retention.csv')
    selected=matched.loc[(matched.condition.eq('clean'))|(matched.condition.eq('future_years')&matched.family.eq('crossed'))|(matched.condition.eq('air_exposure')&matched.family.eq('calendar'))]
    if len(selected)!=4 or selected.duplicated(['condition','family']).any() or not selected.three_only.eq(selected.score_only).all():raise ValueError('Matched numerical cohort differs')
    uncertainty=pd.read_csv(REV/'whole_archive/uncertainty_paired_summary.csv')
    if len(uncertainty)!=8 or uncertainty.duplicated(['family','mode','estimator']).any():raise ValueError('Uncertainty common cohort differs')
    lines=[r'\section{Core source comparisons}',
      r'\begin{table}[p]\centering\footnotesize',
      r'\caption{Dangerous source-case summaries: the gap overlaps at least half the training-period peak window. Entries are medians across 20 repetitions sharing the source archive. Method-specific availability can differ; paired case comparisons are reported separately. Coverage and CRPS are not defined for point-only methods.}\label{tab:focused-annual}',
      r'\begin{tabular}{llrrrr}\toprule',
      r'Family & Method & Availability & MAE & 90\% coverage & CRPS\\\midrule']
    labels={'plug_in':'plug-in','functional_debias':'functional','distribution_regression':'D2','stochastic_regression_calibrated':'classical'}
    for r in score.sort_values(['family','estimator']).itertuples():
        lines.append(f'{r.family} & {labels[r.estimator]} & {fmt(r.availability_median,percent=True)} & {fmt(r.mae_median)} & {fmt(r.coverage90_median,percent=True)} & {fmt(r.crps_median)}' + r'\\')
    lines += [r'\bottomrule\end{tabular}',r'\end{table}',r'\begin{table}[p]\centering\footnotesize',
      r'\caption{Held-region source-calibrated comparison of the three-output and score-only rules. The score cutoff is chosen from disjoint source rule-calibration groups. Retention differs in the evaluated target cases; errors are conditional on numerical publication.}\label{tab:focused-source-release}',
      r'\begin{tabular}{llrrrr}\toprule',r'Family & Method & Eligible & Published & Retention & Error rate\\\midrule']
    for r in source.sort_values(['family','method']).itertuples():
        name='three outputs' if r.method=='three_outputs' else 'score only'
        lines.append(f'{r.family} & {name} & {int(r.n_eligible):,} & {int(r.n_published):,} & {fmt(r.retention,percent=True)} & {fmt(r.risk,percent=True)}' + r'\\')
    lines += [r'\bottomrule\end{tabular}',r'\end{table}',r'\begin{table}[p]\centering\footnotesize',
      r'\caption{Retrospective equal numerical-count comparison. The score threshold uses the evaluated feature distribution and the three-output count, so this is transductive. Equal numerical counts do not equate retained bounds or unknown states.}\label{tab:focused-matched-release}',
      r'\resizebox{\linewidth}{!}{\begin{tabular}{llrrrrr}\toprule',r'Condition & Family & Eligible & Published by each & Three failures & Score failures & Three / score error\\\midrule']
    for r in selected.sort_values(['condition','family']).itertuples():
        label={'clean':'clean','future_years':'future','air_exposure':'air substitution'}[r.condition]
        rate='--' if pd.isna(r.three_output_risk) or pd.isna(r.score_only_risk) else fmt(r.three_output_risk,percent=True)+' / '+fmt(r.score_only_risk,percent=True)
        lines.append(f'{label} & {r.family} & {int(r.n_eligible):,} & {int(r.n_equal_numerical):,} & {int(r.three_output_bad)} & {int(r.score_only_bad)} & {rate}' + r'\\')
    lines += [r'\bottomrule\end{tabular}}',r'\end{table}',r'\begin{table}[p]\centering\footnotesize',
      r"\caption{Annual and trend coverage on the common archive cohort. Annual coverage weights cases by incomplete years. Tail and rank experiments use different random draws. Within one estimator the three rank constructions share that estimator's annual marginals; the two estimators do not share one annual distribution. Repetitions share the same source archive.}\label{tab:focused-uncertainty}",
      r'\resizebox{\linewidth}{!}{\begin{tabular}{lllrrrrrrrr}\toprule',
      r'Family & Mode & Method & Cases & Groups & Annual 90\% & Constant 95\% & Normal 95\% & Independent 95\% & Shared 95\% & Blocks 95\%\\\midrule']
    for r in uncertainty.sort_values(['family','mode','estimator']).itertuples():
        method='classical' if r.estimator=='stochastic_calibrated' else r.estimator
        cells=[fmt(getattr(r,name),percent=True) for name in ['annual_coverage90_weighted','constant_coverage95','normal_coverage95','independent_coverage95','shared_parameters_coverage95','residual_blocks_coverage95']]
        lines.append(f'{r.family} & {r.mode} & {method} & {int(r.n_common)} & {int(r.groups)} & '+' & '.join(cells)+r'\\')
    lines += [r'\bottomrule\end{tabular}}',r'\end{table}']
    (PAPER/'focused_supporting_tables.tex').write_text('\n'.join(lines)+'\n')
    print('Rendered 8 annual score rows, 4 source-calibrated rule rows, and 4 matched rule rows.')


if __name__=='__main__':main()
