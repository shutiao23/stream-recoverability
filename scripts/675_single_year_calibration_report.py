#!/usr/bin/env python3
"""Render independently audited, source-only exploratory annual expansion."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity';PAPER=ROOT/'paper/wrr_tr'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/single_year_calibration'

def main():
    plan=json.loads((OUT/'single_year_calibration_plan.json').read_text());freeze=json.loads((OUT/'single_year_source_freeze.json').read_text())
    status=json.loads((OUT/'single_year_calibration_status.json').read_text());audit=json.loads((OUT/'single_year_independent_audit.json').read_text());alignment=json.loads((OUT/'single_year_support_alignment.json').read_text())
    if status['status']!='passed' or audit['status']!='passed' or alignment['status']!='passed' or audit['source_support_rows_checked']!=52 or status['forward_finite_group_max_corrections']!=0:
        raise ValueError('Source correction, target scoring or independent support audit incomplete')
    support=pd.read_csv(OUT/'single_year_source_support.csv');summary=pd.read_csv(OUT/'single_year_target_summary.csv')
    groups=pd.read_csv(OUT/'single_year_group_sensitivity.csv');loo=pd.read_csv(OUT/'single_year_leave_region_out.csv')
    if len(support)!=52 or len(summary)!=48 or audit['target_summary_rows_checked']!=48 or audit['paired_group_sensitivity_rows']!=len(groups) or audit['leave_region_out_rows']!=len(loo):
        raise ValueError('Calibration summary denominators differ')
    target=summary.loc[summary.family.eq('crossed')&summary['mode'].eq('forward')&summary.scope.eq('both_methods_supported')]
    def get(est,stratum):
        f=target.loc[target.estimator.eq(est)&target.stratum.eq(stratum)]
        if len(f)!=1:raise ValueError('Expected target cell missing')
        return f.iloc[0]
    d,c=get('D2','all'),get('stochastic_calibrated','all');dh,ch=get('D2','unobserved_peak_excess'),get('stochastic_calibrated','unobserved_peak_excess')
    if d.n_supported!=c.n_supported or dh.n_supported!=ch.n_supported or d.n_eligible!=c.n_eligible or dh.n_eligible!=ch.n_eligible:
        raise ValueError('Two-method support cohorts differ')
    def pct(v):return f'{100*float(v):.1f}'
    values={'SYAllEligible':str(int(d.n_eligible)),'SYAllSupported':str(int(d.n_supported)), 'SYAllAvailability':pct(d.availability),
            'SYAllStations':str(int(d.supported_stations)),'SYAllGroups':str(int(d.supported_groups)),
            'SYDTwoBase':pct(d.paired_baseline_coverage90),'SYDTwoExpanded':pct(d.paired_expanded_coverage90),
            'SYClassicBase':pct(c.paired_baseline_coverage90),'SYClassicExpanded':pct(c.paired_expanded_coverage90),
            'SYDTwoWidthBase':f'{d.paired_baseline_width90:.3f}','SYDTwoWidthExpanded':f'{d.paired_expanded_width90:.3f}',
            'SYClassicWidthBase':f'{c.paired_baseline_width90:.3f}','SYClassicWidthExpanded':f'{c.paired_expanded_width90:.3f}',
            'SYDTwoScoreBase':f'{d.paired_baseline_interval_score90:.4f}','SYDTwoScoreExpanded':f'{d.paired_expanded_interval_score90:.4f}',
            'SYClassicScoreBase':f'{c.paired_baseline_interval_score90:.4f}','SYClassicScoreExpanded':f'{c.paired_expanded_interval_score90:.4f}',
            'SYHiddenEligible':str(int(dh.n_eligible)),'SYHiddenSupported':str(int(dh.n_supported)),
            'SYHiddenDTwoBase':pct(dh.paired_baseline_coverage90),'SYHiddenDTwoExpanded':pct(dh.paired_expanded_coverage90),
            'SYHiddenClassicBase':pct(ch.paired_baseline_coverage90),'SYHiddenClassicExpanded':pct(ch.paired_expanded_coverage90)}
    (PAPER/'single_year_calibration_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    lines=[r'\section{Single-year source expansion for annual intervals}',
      ('After reviewing prior annual and trend results, we used single-year masked source cases from the candidate models\' rule-calibration groups. These groups do not enter the estimators, original interval calibration or risk-learning roles; every target-region group is excluded. Some groups contributed to the separate risk-rule component; the pool is not an unopened independent dataset. Forward source cases are from before 2010. For each family, mode, region and estimator we estimate an equal-group-weighted empirical 90th percentile of nonnegative interval misses. A correction is applied only with at least three available source groups and a positive radius. This rule is exploratory, and the source cases hide a single year rather than an entire degraded archive. It neither establishes group exchangeability nor identifies a calibrated joint trend distribution. At most eight forward groups are assigned to this role, below the nine needed for a finite one-maximum-per-group 90\% rank; the group-maximum diagnostic was not applied.'),
      r'\begin{table}[p]\centering\footnotesize',
      r'\caption{Exploratory interval expansion: same target cases must be supported for both methods. Baseline and expanded scores use the identical supported subset; all-case baselines are retained separately in the supplied CSV. Hidden-peak strata depend on the complete reference. Widths are in $^{\circ}$C.}\label{tab:single-year-calibration}',
      r'\resizebox{\linewidth}{!}{\begin{tabular}{lllrrrrrrr}\toprule',
      r'Family / mode & Stratum & Method & Eligible & Supported & Groups & Cover before & Cover after & Width before & Width after\\\midrule']
    subset=summary.loc[summary.scope.eq('both_methods_supported')&summary.stratum.isin(['all','unobserved_peak_excess'])].sort_values(['family','mode','stratum','estimator'])
    for r in subset.itertuples():
        st='hidden' if r.stratum=='unobserved_peak_excess' else 'all';name='classical' if r.estimator=='stochastic_calibrated' else r.estimator
        def p(v):return '--' if not np.isfinite(v) else f'{100*v:.1f}\\%'
        def q(v):return '--' if not np.isfinite(v) else f'{v:.3f}'
        lines.append(f'{r.family} / {r.mode} & {st} & {name} & {int(r.n_eligible)} & {int(r.n_supported)} & {int(r.supported_groups)} & {p(r.paired_baseline_coverage90)} & {p(r.paired_expanded_coverage90)} & {q(r.paired_baseline_width90)} & {q(r.paired_expanded_width90)}' + r'\\')
    lines += [r'\bottomrule\end{tabular}}',r'\end{table}',
              ('Re-prediction of the 52 source support cells, verification of individual target intervals and a separate two-method support-intersection check passed. Group-resampling and leave-region-out summaries are supplied; they do not prove independent climates. Unsupported cells and unchanged all-case baselines remain visible. The source group-mass empirical percentile is not a finite-sample coverage guarantee.')]
    (PAPER/'single_year_calibration_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','source_support_cells':len(support),'source_prediction_rows_rechecked':audit['source_prediction_rows_checked'],
            'target_common_cases':status['target_common_cases'],'target_estimator_rows_rechecked':audit['target_estimator_rows_checked'],
            'target_summary_cells':len(summary),'group_sensitivity_cells':len(groups),'leave_region_out_cells':len(loo),
            'forward_crossed_eligible':int(d.n_eligible),'forward_crossed_supported_both':int(d.n_supported),'forward_crossed_support_fraction':float(d.availability),
            'forward_crossed_supported_stations':int(d.supported_stations),'forward_crossed_supported_groups':int(d.supported_groups),
            'D2_before90':float(d.paired_baseline_coverage90),'D2_after90':float(d.paired_expanded_coverage90),
            'classic_before90':float(c.paired_baseline_coverage90),'classic_after90':float(c.paired_expanded_coverage90),
            'hidden_eligible':int(dh.n_eligible),'hidden_supported':int(dh.n_supported),
            'hidden_D2_before90':float(dh.paired_baseline_coverage90),'hidden_D2_after90':float(dh.paired_expanded_coverage90),
            'hidden_classic_before90':float(ch.paired_baseline_coverage90),'hidden_classic_after90':float(ch.paired_expanded_coverage90),
            'forward_finite_group_max':status['forward_finite_group_max_corrections'],
            'limitations':plan['limitations']}
    (OUT/'single_year_calibration_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
