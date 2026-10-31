#!/usr/bin/env python3
"""Render reproducible reported-season and completeness-rule comparisons."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/summer_window_comparison'
PAPER=ROOT/'paper/wrr_tr'


def main():
    summary=json.loads((OUT/'summary.json').read_text());audit=json.loads((OUT/'independent_audit.json').read_text())
    influence=json.loads((OUT/'influence_independent_audit.json').read_text())
    if audit['status']!='passed' or influence['status']!='passed' or audit['complete_station_years_checked']!=summary['complete_station_years']:
        raise ValueError('Summer-window independent audits incomplete')
    rules=pd.read_csv(OUT/'screening_counts.csv').set_index('rule')
    strata=pd.read_csv(OUT/'influence_summary.csv').set_index('cohort')
    warm=rules.loc['warm_90_station_specific'];annual=rules.loc['annual_95'];excluded=strata.loc['excluding_two_posthoc_stations']
    vals={'SWStations':str(summary['stations']),'SWGroups':str(summary['connected_groups']),
          'SWComplete':f"{summary['complete_station_years']:,}",'SWAbove':str(summary['different_above_tolerance_years']),
          'SWAboveHalf':str(summary['above_0p5_c_years']),'SWMean':f"{summary['mean_gap_c']:.3f}",
          'SWExclYears':f"{int(excluded.complete_station_years):,}",'SWExclAbove':str(int(excluded.years_above_tolerance)),
          'SWExclMean':f"{excluded.mean_gap_c:.3f}",'SWWitness':str(summary['witnesses_full_above_summer']),
          'SWRuleYears':f"{int(warm.station_years):,}",'SWWarmRejected':str(int(warm.rejected)),
          'SWWarmBounds':str(int(warm.rejected_with_observed_30day_bound)),
          'SWAnnualRejected':str(int(annual.rejected)),'SWAnnualBounds':str(int(annual.rejected_with_observed_30day_bound))}
    (PAPER/'summer_window_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    names={'complete_100':'Complete year','annual_95':'Annual 95\\%','warm_90_station_specific':'Station warm season 90\\%',
           'july_aug_complete':'Complete July--August'}
    rule_rows=[]
    for name in names:
        row=rules.loc[name]
        rule_rows.append(f"{names[name]} & {int(row.accepted):,} & {int(row.rejected)} & {int(row.unknown)} & {int(row.rejected_with_observed_30day_bound)} & {int(row.stations_with_rejected_bound)} \\\\")
    names2={'all_95_stations':'All stations','excluding_two_posthoc_stations':'Exclude two selected sites',
            'label_regulated':'Label: regulated','label_unmatched_gages':'Label: unmatched gages','label_unknown':'Label: unknown'}
    influence_rows=[]
    for name in names2:
        row=strata.loc[name]
        influence_rows.append(f"{names2[name]} & {int(row.stations)} & {int(row.complete_station_years):,} & {int(row.years_above_tolerance)} & {int(row.years_above_0p5_c)} & {row.mean_gap_c:.3f} \\\\")
    text=r'''\section{Seasonal-window and screening-rule diagnostics}
The previously selected source sample contains 96 eligible long-record stations; this calculation uses the 95-station project-processed subset with a documented candidate redistribution path. None of the 35 recorded witnesses is at the excluded LUBW station, although it remains part of the original eligible-station denominator. The subset comprises \SWComplete{} complete station-years at \SWStations{} stations and \SWGroups{} connected groups. For each complete year, we compare the full-year reported H30 with the largest 30-day mean whose every day lies from 1 July through 31 August. Of those years, \SWAbove{} exceed the summer-window value by more than the numerical tolerance $5\times10^{-6}$ $^{\circ}$C, and \SWAboveHalf{} exceed it by more than 0.5 $^{\circ}$C. The mean difference is \SWMean{} $^{\circ}$C. These are complete recorded years, not simulated reconstruction errors; neither the tolerance nor the 0.5 $^{\circ}$C threshold is an estimate of sensor error.

The comparison was specified after the original witnesses and literature had been examined. It is not a reproduction of Beaufort et al.'s multiyear thermal peak or their summer air-temperature climate correction; that study also excluded sites with strong human influence. The present sample contains regulated and incompletely characterized sites, covers different locations and years, and the fully-contained July--August window differs from a peak-center criterion. Consequently our fraction must not be compared directly with their reported fraction. The incomplete-year comparison is also conditional on the 35 already selected record witnesses: all have a fully observed July--August 30-day window, and \SWWitness{} have a larger fully observed 30-day window elsewhere in the year. This does not establish the full H30 of an incomplete year or a population prevalence.

Table~\ref{tab:summer-rules} counts previously eligible station-years rejected by four explicit study rules, including how many still supply at least one fully observed 30-day window. A lower bound is information about the reported record, not a complete annual estimate or a guarantee of better trends. The 90\% station-specific warm-season rule uses a leave-target-year-out climatology; the complete July--August row is a contextual comparator rather than the full published climate-correction procedure. The records are not an independent validation sample and no sensor error has been estimated.

\begin{table}[ht]\caption{Study screening rules on \SWRuleYears{} eligible station-years in the 95-station candidate subset. Rejected-with-bound means the rejected incomplete year contains at least one complete observed 30-day window.}\label{tab:summer-rules}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrrr}\toprule
Rule & Accepted & Rejected & Unknown & Rejected with bound & Stations \\
\midrule
'''+'\n'.join(rule_rows)+r'''
\bottomrule\end{tabular}}\end{table}

After inspecting the largest annual gaps, we separately summarized existing project regulation labels and removed the two sites with the largest individual gaps (Table~\ref{tab:summer-influence}). The 2010 USGS analysis identified Blue River and Fall Creek as dam-affected monitoring sites in 2001--2002; it does not establish the cause or measurement quality of every year examined here. The existing \emph{unmatched gages} label does not mean unregulated, and labels and sites were not randomized. Removing these two post-hoc sites leaves \SWExclAbove{} of \SWExclYears{} complete station-years above the numerical tolerance, with mean difference \SWExclMean{} $^{\circ}$C. These summaries do not identify causal dam effects or transfer to streams absent from the sample.

\begin{table}[ht]\caption{Post-hoc seasonal-window influence by existing project label and after removing two selected sites. ``Above'' is greater than $5\times10^{-6}$ $^{\circ}$C; the second count exceeds 0.5 $^{\circ}$C. Labels are observational metadata, not independently verified treatments.}\label{tab:summer-influence}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrrr}\toprule
Cohort & Stations & Years & Above & $>0.5$ & Mean ($^{\circ}$C) \\
\midrule
'''+'\n'.join(influence_rows)+r'''
\bottomrule\end{tabular}}\end{table}

The comparison and screening totals were independently reconstructed using pandas rolling windows on the same snapshot. The post-hoc influence totals and 36 selected-site peak-window dates were independently checked using NumPy convolution; the stored regulation labels were checked against the project's source metadata. Neither audit verifies the original provider's measurements or whether each project regulation label is accurate. The supplied 95-station snapshot permits the window and screening arithmetic to be rerun, subject to its attribution and reuse conditions.
'''
    (PAPER/'summer_window_supporting.tex').write_text(text)
    print('Rendered seasonal-window and screening comparisons')


if __name__=='__main__':main()
