#!/usr/bin/env python3
"""Render the checked post-hoc common-archive point comparison."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/summer_proxy_archive';PAPER=ROOT/'paper/wrr_tr'


def one(frame,**conditions):
    for key,value in conditions.items():frame=frame[frame[key].eq(value)]
    if len(frame)!=1:raise ValueError('Expected one comparison row')
    return frame.iloc[0]


def main():
    status=json.loads((OUT/'status.json').read_text());audit=json.loads((OUT/'independent_audit.json').read_text())
    if status['status']!='computed_posthoc' or status['archive_settings']!=3320 or audit['status']!='passed':raise ValueError('Proxy audit incomplete')
    a=pd.read_csv(OUT/'annual_paired_summary.csv');t=pd.read_csv(OUT/'trend_paired_summary.csv');s=pd.read_csv(OUT/'proxy_support_summary.csv')
    if int(s.n.sum())!=21446:raise ValueError('Proxy support cohort differs')
    values={}
    rows=[]
    for family,mode,label in [('calendar','offline','Calendar, offline'),('calendar','forward','Calendar, forward'),('crossed','offline','Long gap, offline'),('crossed','forward','Long gap, forward')]:
        ar=one(a,family=family,mode=mode,stratum='all',scope='four_method_common',comparator='D2')
        tr=one(t,family=family,mode=mode,subset='nontrivial',scope='four_method_common',comparator='D2')
        rows.append(f'{label} & {int(ar.n_common):,} & {ar.comparator_mae:.3f} & {ar.proxy_mae:.3f} & {int(tr.n_common):,} & {tr.comparator_rmse:.3f} & {tr.proxy_rmse:.3f} '+r'\\')
        if family=='crossed' and mode=='forward':
            values={'SAAnnualN':f'{int(ar.n_common):,}','SADTwoAnnual':f'{ar.comparator_mae:.3f}','SAProxyAnnual':f'{ar.proxy_mae:.3f}',
                    'SATrendN':f'{int(tr.n_common):,}','SADTwoTrend':f'{tr.comparator_rmse:.3f}','SAProxyTrend':f'{tr.proxy_rmse:.3f}'}
    (PAPER/'summer_proxy_archive_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    doc=r'''\section{Direct archive comparison with a literature-inspired summer air proxy}
After viewing the original archive and interannual-proxy results, we evaluated a different, deterministic adaptation on the same 3,320 jointly masked archives. For each target year, all target-archive gaps are hidden before fitting, the entire target year is excluded from the local summer water--air fit, and forward fits exclude water from 2010 onward. We require at least three complete eligible training years, 30 usable summer days from at least three years, and common finite predictors for all 2--10-day right-aligned air averages; the lag maximizing in-sample $R^2$ is selected. We fill missing July--August water days and take the maximum of the reconstructed summer 30-day peak and the fully observed full-year 30-day bound. When summer contains no gaps, the result is the observed full-year bound alone. Missing air and unsupported fits remain unavailable. This differs in data, target and implementation from Beaufort et al. (\url{https://doi.org/10.5194/hess-26-3477-2022}); it is not their code or a test of their original multiyear thermal-peak estimator.

There are 21,446 masked station-year records in the repeated archive settings; 21,278 proxy outputs are available. Of all records, 11,334 have no summer gaps and return only the observed bound; 14,784 available outputs equal that bound, including cases where a regression was fitted. A bound can remain below the true annual maximum when the missing peak is outside July--August. These are repeated synthetic masks, not independent site-years or climates. The source roles, pre-existing fixed models, air-day alignment and restricted-data access limitations remain. The proxy supplies no predictive interval. Annual retrospective strata and pairwise availability are reported in the aggregate output; the bound-equals-reference stratum uses the hidden reference and cannot be selected at deployment.

Table~\ref{tab:summer-archive-proxy} uses cases where all four point methods are finite. Trend rows exclude archives with no masked year and use the same finite-record OLS target. Differences are descriptive after selecting this analysis; resampling connected groups and fixed-prediction leave-one-region-out summaries do not establish out-of-region prediction or causal superiority. Independent least-squares and rolling-window code checked 52 selected archives in seven regions, 310 masked years and target-year fit perturbations, plus the reported aggregate cells. It used the same processed sources and fixed baseline predictions.

\begin{table}[ht]\caption{Common-cohort annual and nontrivial-archive point comparisons. Annual MAE is $^{\circ}$C; trend RMSE is $^{\circ}$C per decade. Counts are repeated mask records or archives.}\label{tab:summer-archive-proxy}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrrrr}\toprule
Setting & Annual $n$ & D2 MAE & Proxy MAE & Archive $n$ & D2 RMSE & Proxy RMSE \\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule\end{tabular}}\end{table}
'''
    (PAPER/'summer_proxy_archive_supporting.tex').write_text(doc);print('Rendered direct archive proxy comparison')


if __name__=='__main__':main()
