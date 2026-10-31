#!/usr/bin/env python3
"""Render source group-maximum annual and trend sensitivities."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/groupmax_annual_calibration'
PAPER=ROOT/'paper/wrr_tr'


def only(frame,**filters):
    for key,value in filters.items():frame=frame[frame[key].eq(value)]
    if len(frame)!=1:raise ValueError('Unexpected group-max summary cell: '+str(filters))
    return frame.iloc[0]


def main():
    annual_audit=json.loads((OUT/'independent_audit.json').read_text())
    trend_audit=json.loads((OUT/'trend_independent_audit.json').read_text())
    repair=json.loads((OUT/'source_repair_dependency.json').read_text())
    status=json.loads((OUT/'status.json').read_text());execution=json.loads((OUT/'trend_execution.json').read_text())
    if annual_audit['status']!='passed' or trend_audit['status']!='passed' or repair['status']!='passed' or not status['summary_denominator_corrected']:
        raise ValueError('Annual or trend group-max audit incomplete')
    a=pd.read_csv(OUT/'summary.csv');t=pd.read_csv(OUT/'trend_summary.csv');overlap=pd.read_csv(OUT/'trend_empirical_overlap.csv')
    annual={m:only(a,family='crossed',estimator=m,stratum='all',scope='both_groupmax_supported') for m in ['D2','stochastic_calibrated']}
    trend={(m,s):only(t,estimator=m,dependence='independent',scheme=s) for m in ['D2','stochastic_calibrated'] for s in ['baseline','endpoint_only','tapered']}
    old={m:only(overlap,estimator=m,dependence='independent',scheme='tapered') for m in ['D2','stochastic_calibrated']}
    d=annual['D2'];c=annual['stochastic_calibrated'];db=trend['D2','baseline'];de=trend['D2','endpoint_only'];dt=trend['D2','tapered']
    cb=trend['stochastic_calibrated','baseline'];ce=trend['stochastic_calibrated','endpoint_only'];ct=trend['stochastic_calibrated','tapered']
    vals={'GMAnnualCases':f'{int(d.n_supported):,}','GMAnnualGroups':str(int(d.groups)),
          'GMAnnualDBase':f'{100*d.baseline_coverage90:.1f}','GMAnnualDNew':f'{100*d.groupmax_coverage90:.1f}',
          'GMAnnualDWidthBase':f'{d.baseline_width90:.3f}','GMAnnualDWidthNew':f'{d.groupmax_width90:.3f}',
          'GMAnnualDScoreBase':f'{d.baseline_interval_score90:.3f}','GMAnnualDScoreNew':f'{d.groupmax_interval_score90:.3f}',
          'GMAnnualCBase':f'{100*c.baseline_coverage90:.1f}','GMAnnualCNew':f'{100*c.groupmax_coverage90:.1f}',
          'GMAnnualCWidthBase':f'{c.baseline_width90:.3f}','GMAnnualCWidthNew':f'{c.groupmax_width90:.3f}',
          'GMAnnualCScoreBase':f'{c.baseline_interval_score90:.3f}','GMAnnualCScoreNew':f'{c.groupmax_interval_score90:.3f}',
          'GMAllArchives':str(execution['archive_settings']),'GMTrendCases':str(trend_audit['matched_nontrivial_archives']),
          'GMTrendGroups':str(trend_audit['groups']),'GMNoAnnual':str(execution['status_counts']['one_or_both_annual_distributions_unavailable']),
          'GMNoGap':str(execution['status_counts']['no_incomplete_years']),
          'GMTrendDBaseCov':f'{100*db.missing_coverage95:.1f}','GMTrendDNewCov':f'{100*dt.missing_coverage95:.1f}',
          'GMTrendDBaseWidth':f'{db.width95:.3f}','GMTrendDEndWidth':f'{de.width95:.3f}','GMTrendDTaperWidth':f'{dt.width95:.3f}',
          'GMTrendDBaseScore':f'{db.interval_score95:.3f}','GMTrendDNewScore':f'{dt.interval_score95:.3f}',
          'GMTrendCBaseCov':f'{100*cb.missing_coverage95:.1f}','GMTrendCNewCov':f'{100*ct.missing_coverage95:.1f}',
          'GMTrendCBaseWidth':f'{cb.width95:.3f}','GMTrendCEndWidth':f'{ce.width95:.3f}','GMTrendCTaperWidth':f'{ct.width95:.3f}',
          'GMTrendCBaseScore':f'{cb.interval_score95:.3f}','GMTrendCNewScore':f'{ct.interval_score95:.3f}',
          'GMOverlapCases':str(trend_audit['previous_empirical_overlap_archives']),
          'GMOverlapDOldWidth':f"{old['D2'].empirical_width95:.3f}",'GMOverlapDNewWidth':f"{old['D2'].groupmax_width95:.3f}",
          'GMOverlapCOldWidth':f"{old['stochastic_calibrated'].empirical_width95:.3f}",'GMOverlapCNewWidth':f"{old['stochastic_calibrated'].groupmax_width95:.3f}"}
    (PAPER/'groupmax_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    annual_rows=[]
    for method,label in [('D2','D2'),('stochastic_calibrated','Stochastic')]:
        for stratum,slabel in [('all','All'),('unobserved_peak_excess','Hidden peak')]:
            r=only(a,family='crossed',estimator=method,stratum=stratum,scope='both_groupmax_supported')
            annual_rows.append(f"{label} & {slabel} & {int(r.n_supported):,} & {100*r.baseline_coverage90:.1f} / {100*r.groupmax_coverage90:.1f} & {r.baseline_width90:.3f} / {r.groupmax_width90:.3f} & {r.baseline_interval_score90:.3f} / {r.groupmax_interval_score90:.3f} \\\\")
    trend_rows=[]
    for method,label in [('D2','D2'),('stochastic_calibrated','Stochastic')]:
      for dep,dlabel in [('independent','Independent'),('shared_parameters','Shared parameter'),('residual_blocks','Residual blocks')]:
        cells=[only(t,estimator=method,dependence=dep,scheme=s) for s in ['baseline','endpoint_only','tapered']]
        coverage=' / '.join(f'{100*x.missing_coverage95:.1f}' for x in cells)
        width=' / '.join(f'{x.width95:.3f}' for x in cells)
        score=' / '.join(f'{x.interval_score95:.3f}' for x in cells)
        trend_rows.append(f'{label} & {dlabel} & {coverage} & {width} & {score} \\\\')
    text=r'''\section{Conservative source-group maximum sensitivity}
After earlier annual, trend and classifier results had been inspected, we combined the candidate source model's assigned risk-learning and rule-calibration connected groups for each target region. These groups are disjoint from the numeric quantile estimator and its interval-offset groups and exclude groups in the held target region. The risk-learning groups trained a separate failure classifier, but no classifier score or selection is used in this interval analysis. Replacing the stored classifier with a constant score in 300 source-case probes left both methods' seven annual quantiles unchanged. Source cases are before 2010 and use single-year masks. The source and target observations were already opened; this is a post-hoc sensitivity, not a new prospective experiment.

For each valid source group, we calculate the maximum of the nonnegative distances by which a reference falls outside its projected 90\% interval. With $G$ groups, the expansion is the $\lceil0.9(G+1)\rceil$-th ordered group maximum if that rank exists and is positive; otherwise expansion is unsupported. The six forward regions have 12--16 contributing groups per method and family, so the chosen rank is the maximum among the available group maxima. This finite order statistic does not establish a 90\% group-coverage guarantee: exchangeability is not demonstrated, source cases use individual-year masks, target archives have joint multiyear gaps, and groups have different sizes and climates. Both methods' lower endpoints are constrained to the visible observed window. Table~\ref{tab:groupmax-annual} compares the same target cases; the hidden-peak subset uses the complete reference and cannot be selected at decision time. All evaluated cases in each of the 17 target groups happen to be covered after expansion in the controlled-gap cohort, but those groups are not independent-climate replications.

\begin{table}[ht]\caption{Nominal 90\% annual intervals in common forward controlled-gap cases, baseline / source-group-maximum expansion. Width and interval score are $^{\circ}$C; lower score is better.}\label{tab:groupmax-annual}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{llrrrr}\toprule
Method & Stratum & Cases & Coverage (\%) & Width & Score \\
\midrule
'''+'\n'.join(annual_rows)+r'''
\bottomrule\end{tabular}}\end{table}

We then propagated the same fixed source radii through the original masked archives and three rank constructions. Of \GMAllArchives{} settings, \GMNoAnnual{} lack at least one annual distribution and \GMNoGap{} have no masked year; \GMTrendCases{} nontrivial settings in \GMTrendGroups{} connected groups support both methods and all rank constructions. Two hypothetical quantile representations share the same expanded 5th and 95th percentiles: one changes only endpoints, and the other also tapers changes through interior quantiles. They preserve the same point median and use identical ranks, but their interpolated interior and normal-spacing tails differ. Table~\ref{tab:groupmax-trend} shows empirical nominal 95\% trend coverage, width and interval score. On the \GMOverlapCases{} archives with the earlier narrow source correction and all ranks, the independent-rank tapered D2 interval width is \GMOverlapDOldWidth{} with that earlier correction and \GMOverlapDNewWidth{} $^{\circ}$C per decade with group maxima; the corresponding stochastic widths are \GMOverlapCOldWidth{} and \GMOverlapCNewWidth{}. Matching the annual endpoints does not identify the trend distribution, and observed coverage on these selected masks does not certify coverage for future archives.

\begin{table}[ht]\caption{Nominal 95\% forward trend intervals on \GMTrendCases{} common nontrivial archives. Each entry is baseline / endpoint-only / tapered; widths and interval scores are $^{\circ}$C per decade.}\label{tab:groupmax-trend}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{llrrr}\toprule
Method & Ranks & Coverage (\%) & Width & Score \\
\midrule
'''+'\n'.join(trend_rows)+r'''
\bottomrule\end{tabular}}\end{table}

The independent annual audit reconstructed 88,053 source case--method predictions, 352 source group maxima, 14,714 target case--method scores and the annual summary cells. An isolation check identified a previously implicit pre-2010 bridge-repair table needed for the stochastic source cases. The original source plan did not list this file: applying the saved table reproduces all source group maxima, while omitting it changes source-case availability and three of the twelve stochastic region--family radii; D2 radii are unchanged. The audit now requires the table explicitly and fails if it is absent or changed. A separate calculation reconstructs 13,248 trend treatment rows from saved quantiles and rank arrays and checks all 685 overlapping earlier rank snapshots. These numerical audits use the same source and target observations and do not validate exchangeability, physical sensors, provider rights or an independent climate.

Further post-hoc replay identified bridge-repair dependencies in the twenty historical source-seed exports and in the candidate-provider archive calibration. Reapplying the twenty saved repairs reproduced the stored D2 and stochastic quantiles on all 2,914,470 seed--case records. Without those repairs, 1,081,252 records lost complete stochastic quantiles and 1,018,696 records with complete quantiles in both replays had at least one changed quantile. These counts include repeated masks and are not independent station-years. In the archive calibration, applying the two saved repairs reproduced all 26 mode--region--method offset sets; omitting repairs changed offsets in all 13 stochastic sets and none of the 13 state sets. The original candidate-provider archive plan did not list these repairs; the later single-year plan did record their hashes. These dependency checks reuse saved cases and model roles and were assembled after the earlier analyses, not prospectively registered.
'''
    (PAPER/'groupmax_supporting.tex').write_text(text)
    print('Rendered group-maximum annual and trend sensitivity')


if __name__=='__main__':main()
