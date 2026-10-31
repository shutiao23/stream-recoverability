#!/usr/bin/env python3
"""Render audited, fixed-rank trend sensitivity to annual interval expansion."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity';PAPER=ROOT/'paper/wrr_tr'

def main():
    plan=json.loads((OUT/'single_year_trend_plan.json').read_text());run=json.loads((OUT/'single_year_trend_execution.json').read_text());audit=json.loads((OUT/'single_year_trend_independent_audit.json').read_text())
    if run['status']!='complete' or audit['status']!='passed' or run['archive_settings']!=760 or audit['source_supported_archive_settings']!=760 or run['status_counts']!=audit['status_counts'] or not audit['baseline_reproduced'] or not audit['same_marginals_and_ranks_checked']:
        raise ValueError('Complete audited trend propagation is required')
    if run['status_counts']!={'passed':685,'one_or_both_annual_distributions_unavailable':73,'no_incomplete_years':2}:
        raise ValueError('Trend exclusion counts differ from the described cohort')
    mainplan=json.loads((OUT/'plan.json').read_text())
    if sum(x['stations'] for x in mainplan['target_mode_region_stations'] if x['mode']=='forward')*20!=820:
        raise ValueError('Original forward archive denominator differs')
    summary=pd.read_csv(OUT/'single_year_trend_summary.csv');contrasts=pd.read_csv(OUT/'single_year_trend_paired_contrasts.csv');loo=pd.read_csv(OUT/'single_year_trend_leave_region_out.csv')
    if len(summary)!=18 or len(contrasts)!=54 or not summary.n.eq(audit['matched_nontrivial_archives']).all() or summary.duplicated(['estimator','dependence','scheme']).any():
        raise ValueError('Trend treatment table is incomplete or has mismatched denominators')
    def row(est,dep,scheme):
        x=summary.loc[summary.estimator.eq(est)&summary.dependence.eq(dep)&summary.scheme.eq(scheme)]
        if len(x)!=1:raise ValueError('Trend treatment missing')
        return x.iloc[0]
    d0,d1,d2=(row('D2','independent',s) for s in ['baseline','endpoint_only','tapered'])
    c0,c1,c2=(row('stochastic_calibrated','independent',s) for s in ['baseline','endpoint_only','tapered'])
    values={'SYTrendAll':'820','SYTrendSupported':str(run['archive_settings']),'SYTrendCommon':str(audit['matched_nontrivial_archives']),
            'SYTrendStations':str(audit['stations']),'SYTrendGroups':str(audit['groups']),
            'SYTrendDTwoBase':f'{100*d0.missing_coverage95:.1f}','SYTrendDTwoEnd':f'{100*d1.missing_coverage95:.1f}','SYTrendDTwoTaper':f'{100*d2.missing_coverage95:.1f}',
            'SYTrendClassicBase':f'{100*c0.missing_coverage95:.1f}','SYTrendClassicEnd':f'{100*c1.missing_coverage95:.1f}','SYTrendClassicTaper':f'{100*c2.missing_coverage95:.1f}',
            'SYTrendDTwoWidthBase':f'{d0.width95:.3f}','SYTrendDTwoWidthEnd':f'{d1.width95:.3f}','SYTrendDTwoWidthTaper':f'{d2.width95:.3f}',
            'SYTrendClassicWidthBase':f'{c0.width95:.3f}','SYTrendClassicWidthEnd':f'{c1.width95:.3f}','SYTrendClassicWidthTaper':f'{c2.width95:.3f}',
            'SYTrendDTwoScoreBase':f'{d0.interval_score95:.3f}','SYTrendDTwoScoreEnd':f'{d1.interval_score95:.3f}','SYTrendDTwoScoreTaper':f'{d2.interval_score95:.3f}',
            'SYTrendClassicScoreBase':f'{c0.interval_score95:.3f}','SYTrendClassicScoreEnd':f'{c1.interval_score95:.3f}','SYTrendClassicScoreTaper':f'{c2.interval_score95:.3f}'}
    (PAPER/'single_year_trend_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    lines=[r'\section{Trend sensitivity to annual interval expansion}',
      ('After examining the source-only annual correction and the earlier trend results, we propagated it '
       'through the original 256-draw normal-spacing quantile representation. The endpoint-only scheme '
       'moves the 5th and 95th quantiles while holding the five interior quantiles fixed. The tapered scheme '
       'also shifts the 10th, 25th, 75th and 90th quantiles by 0.8, 0.4, 0.4 and 0.8 times the radius, '
       'respectively; the median and complete-year values are unchanged. Both schemes use the same '
       'adjusted 90\% endpoints and respect observed lower bounds. Their interior and normal-spacing '
       'outer tails differ. The same independent, auxiliary shared-parameter and residual-block rank '
       'matrices are reused within each scheme; no calibrated joint distribution is implied. '
       'Among 820 forward controlled-gap station--repetition settings, 760 belong to regions with source '
       'support for both methods. Seventy-three of these lack at least one annual distribution, and two '
       'have no incomplete year, leaving 685 common nontrivial settings. Original saved trend intervals '
       'are reproduced before adjustment. The target selection and calibration remain retrospective.'),
      r'\begin{table}[p]\centering\footnotesize',
      r'\caption{Nominal 95\% finite-record trend interval comparison on the same 685 station--repetition cases, 38 stations and 14 connected groups. Width and interval score are in $^{\circ}$C per decade; repeated masks are not independent climates.}\label{tab:single-year-trend}',
      r'\begin{tabular}{lllrrr}\toprule',
      r'Method & Rank construction & Marginal scheme & Coverage & Width & Interval score\\\midrule']
    label={'independent':'independent','shared_parameters':'shared parameter','residual_blocks':'residual blocks'}
    for method in ['D2','stochastic_calibrated']:
        for dep in ['independent','shared_parameters','residual_blocks']:
            for scheme in ['baseline','endpoint_only','tapered']:
                r=row(method,dep,scheme);m='classical' if method=='stochastic_calibrated' else method;s={'baseline':'baseline','endpoint_only':'endpoints','tapered':'tapered'}[scheme]
                lines.append(f'{m} & {label[dep]} & {s} & {100*r.missing_coverage95:.1f}\\% & {r.width95:.3f} & {r.interval_score95:.3f}' + r'\\')
    lines += [r'\bottomrule\end{tabular}',r'\end{table}',
       ('Connected-group paired bootstrap and fixed-prediction leave-one-region-out summaries '
        'are supplied. They are descriptive, use only 14 target groups and do not establish '
        'independent climates. Annual 90\% endpoint correction does not identify the inner or '
        'outer distribution, cure annual undercoverage, guarantee trend coverage, or resolve source '
        'rights. The underlying case records and rank arrays remain local pending permission.')]
    (PAPER/'single_year_trend_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','all_forward_crossed_archives':820,'source_supported_archives':run['archive_settings'],
        'common_nontrivial_archives':audit['matched_nontrivial_archives'],'stations':audit['stations'],'groups':audit['groups'],
        'source_supported_exclusions':audit['status_counts'],'treatment_rows':audit['per_case_treatment_rows_checked'],
        'D2_independent_coverage':[float(x.missing_coverage95) for x in [d0,d1,d2]],
        'classic_independent_coverage':[float(x.missing_coverage95) for x in [c0,c1,c2]],
        'D2_independent_width':[float(x.width95) for x in [d0,d1,d2]],
        'classic_independent_width':[float(x.width95) for x in [c0,c1,c2]],
        'audit_scope':audit['audit_scope'],'limitations':plan['limitations']}
    (OUT/'single_year_trend_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
