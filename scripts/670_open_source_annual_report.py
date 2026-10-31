#!/usr/bin/env python3
"""Render checked annual candidate-source diagnostics and their limitations."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity';PAPER=ROOT/'paper/wrr_tr'

def main():
    status=json.loads((OUT/'annual_sensitivity_status.json').read_text())
    audit=json.loads((OUT/'annual_sensitivity_independent_audit.json').read_text())
    if status['status']!='passed' or audit['status']!='passed' or status['archive_settings']!=3320 or audit['matched_annual_cases']!=status['matched_annual_cases']:
        raise ValueError('Annual analysis or independent audit incomplete')
    scores=pd.read_csv(OUT/'annual_sensitivity_scores.csv');pairs=pd.read_csv(OUT/'annual_sensitivity_paired.csv');cohorts=pd.read_csv(OUT/'annual_sensitivity_cohorts.csv');loo=pd.read_csv(OUT/'annual_sensitivity_leave_region_out.csv')
    if len(scores)!=48 or len(pairs)!=24 or len(cohorts)!=4 or audit['version_score_rows_checked']!=len(scores) or audit['paired_rows_with_all_bootstrap_metrics']!=len(pairs) or audit['leave_region_out_rows']!=len(loo):
        raise ValueError('Annual result/audit denominator mismatch')
    keys=['family','mode','stratum','estimator'];old=scores.loc[scores.version.eq('old')];new=scores.loc[scores.version.eq('candidate')]
    f=old.merge(new,on=keys,suffixes=('_old','_candidate'),validate='one_to_one')
    if len(f)!=24 or not f.n_common_old.eq(f.n_common_candidate).all():raise ValueError('Original and candidate annual cohorts differ')
    target=f.loc[f.family.eq('crossed')&f['mode'].eq('forward')&f.stratum.eq('unobserved_peak_excess')]
    d=target.loc[target.estimator.eq('D2')].iloc[0];c=target.loc[target.estimator.eq('stochastic_calibrated')].iloc[0]
    if d.n_common_old!=c.n_common_old or d.groups_old!=c.groups_old:raise ValueError('Target estimator cohorts differ')
    classic=pairs.loc[pairs.family.eq('crossed')&pairs['mode'].eq('forward')&pairs.stratum.eq('unobserved_peak_excess')&pairs.estimator.eq('stochastic_calibrated')].iloc[0]
    drop_foen=loo.loc[loo.family.eq('crossed')&loo['mode'].eq('forward')&loo.stratum.eq('unobserved_peak_excess')&loo.estimator.eq('stochastic_calibrated')&loo.excluded_region.eq('foen')].iloc[0]
    drop_bayern=loo.loc[loo.family.eq('crossed')&loo['mode'].eq('forward')&loo.stratum.eq('unobserved_peak_excess')&loo.estimator.eq('stochastic_calibrated')&loo.excluded_region.eq('gkd_bayern')].iloc[0]
    values={'OpenAnnualCases':str(int(d.n_common_old)), 'OpenAnnualStations':str(int(d.stations_old)), 'OpenAnnualGroups':str(int(d.groups_old)),
            'OpenAnnualDTwoOld':f'{100*d.coverage90_old:.1f}', 'OpenAnnualDTwoNew':f'{100*d.coverage90_candidate:.1f}',
            'OpenAnnualClassicOld':f'{100*c.coverage90_old:.1f}', 'OpenAnnualClassicNew':f'{100*c.coverage90_candidate:.1f}',
            'OpenAnnualDTwoWidthOld':f'{d.width90_old:.3f}', 'OpenAnnualDTwoWidthNew':f'{d.width90_candidate:.3f}',
            'OpenAnnualClassicWidthOld':f'{c.width90_old:.3f}', 'OpenAnnualClassicWidthNew':f'{c.width90_candidate:.3f}',
            'OpenAnnualClassicDelta':f'{100*classic.coverage90_difference:+.1f}',
            'OpenAnnualClassicDropFoen':f'{100*drop_foen.coverage90_difference:+.1f}',
            'OpenAnnualClassicDropBayern':f'{100*drop_bayern.coverage90_difference:+.1f}'}
    (PAPER/'open_source_annual_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    lines=[r'\section{Annual uncertainty under candidate-source refits}',
       ('The follow-up compares the same target cases where both methods and both source versions have finite seven-quantile distributions and a finite observed bound. The original 24 annual summary cells were independently reproduced on their original cohorts. Target identities, bounds and connected groups agree between versions. The decomposition by whether the complete reference exceeds the visible bound uses the withheld reference and is unavailable at decision time. Candidate-versus-original differences are post hoc; changed source providers, role assignments and strict region exclusion cannot be separated. The quoted CRPS uses the stated normal-spacing tail continuation, and no new calibration or independent climate validation is established.'),
       r'\begin{table}[p]\centering\footnotesize',
       r'\caption{Annual 90\% interval comparison on the same four-way common cases. Hidden peak means that the complete reported H30 exceeds the observed bound; this is an outcome-defined stratum. Widths are in $^{\circ}$C. Repeated masks are not independent climates.}\label{tab:open-annual-visibility}',
       r'\resizebox{\linewidth}{!}{\begin{tabular}{lllrrrrrr}\toprule',
       r'Family / mode & Stratum & Method & Cases & Groups & Cover old & Cover new & Width old & Width new\\\midrule']
    selected=f.loc[f.stratum.isin(['all','unobserved_peak_excess'])].sort_values(['family','mode','stratum','estimator'])
    for r in selected.itertuples():
        label='hidden' if r.stratum=='unobserved_peak_excess' else 'all'
        name='classical' if r.estimator=='stochastic_calibrated' else r.estimator
        lines.append(f'{r.family} / {r.mode} & {label} & {name} & {int(r.n_common_old)} & {int(r.groups_old)} & {100*r.coverage90_old:.1f}\\% & {100*r.coverage90_candidate:.1f}\\% & {r.width90_old:.3f} & {r.width90_candidate:.3f}' + r'\\')
    lines += [r'\bottomrule\end{tabular}}',r'\end{table}',
      ('For forward controlled gaps with hidden peaks, the paired candidate-minus-original '
       f'classical coverage difference is {100*classic.coverage90_difference:+.1f} percentage points '
       f'with descriptive connected-group bootstrap interval [{100*classic.coverage90_bootstrap_low:.1f}, {100*classic.coverage90_bootstrap_high:.1f}]. '
       f'Removing FOEN or Bavaria from the fixed evaluation cases changes that difference to {100*drop_foen.coverage90_difference:+.1f} or {100*drop_bayern.coverage90_difference:+.1f} percentage points, respectively. '
       'Regions were not refitted in this deletion, and connected groups are not proven independent climates.')]
    (PAPER/'open_source_annual_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','annual_cases':status['matched_annual_cases'],'score_rows_checked':audit['version_score_rows_checked'],
            'paired_rows_checked':audit['paired_rows_with_all_bootstrap_metrics'],'leave_region_out_rows_checked':audit['leave_region_out_rows'],
            'hidden_forward_crossed_cases':int(d.n_common_old),'hidden_forward_crossed_stations':int(d.stations_old),'hidden_forward_crossed_groups':int(d.groups_old),
            'D2_original_coverage90':float(d.coverage90_old),'D2_candidate_coverage90':float(d.coverage90_candidate),
            'classic_original_coverage90':float(c.coverage90_old),'classic_candidate_coverage90':float(c.coverage90_candidate),
            'classic_exclude_foen_coverage_difference':float(drop_foen.coverage90_difference),
            'classic_exclude_bavaria_coverage_difference':float(drop_bayern.coverage90_difference),
            'limitations':status['limitations']}
    (OUT/'annual_sensitivity_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
