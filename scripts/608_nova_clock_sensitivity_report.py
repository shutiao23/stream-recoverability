#!/usr/bin/env python3
"""Cross-check and render the post-hoc NS day-boundary sensitivity."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_clock_sensitivity'
BASE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
PAPER=ROOT/'paper/wrr_tr'


def main():
    plan=json.loads((OUT/'plan.json').read_text());ref=json.loads((OUT/'reference_status.json').read_text())
    score=json.loads((OUT/'score_status.json').read_text());integrity=json.loads((OUT/'integrity_status.json').read_text())
    movement=json.loads((OUT/'prediction_movement_status.json').read_text())
    if plan['status']!='frozen_posthoc_sensitivity' or ref['status']!='boundary_inputs_checked' or not ref['model_scoring_performed'] or score['status']!='scored_sensitivity' or integrity['status']!='passed' or movement['status']!='passed':
        raise RuntimeError('one or more sensitivity stages are incomplete')
    if score['strict_reference_qualified'] or ref['strict_reference_qualified']:raise ValueError('sensitivity is not strict qualification')
    if score['all_shift_common_cases']!=integrity['common_masks'] or integrity['case_rows']!=3*score['all_shift_common_cases']:
        raise ValueError('sensitivity case accounting differs')
    pairs=pd.read_csv(OUT/'paired_summary.csv');change=pd.read_csv(OUT/'prediction_movement.csv')
    a=pairs.loc[pairs.stratum.eq('all')].sort_values('shift_hours')
    if a.shift_hours.tolist()!=[-1,0,1] or not a.n_common.eq(score['all_shift_common_cases']).all():raise ValueError('paired shift cohort differs')
    old=pd.read_csv(BASE/'paired_summary.csv').query("stratum == 'all'")
    if len(old)!=1:raise ValueError('base comparison is not unique')
    zero=a.loc[a.shift_hours.eq(0)].iloc[0];original=old.iloc[0]
    for col in ['n_common','D2_mae','stochastic_mae','D2_coverage90','stochastic_coverage90','D2_width90','stochastic_width90','D2_interval_score90','stochastic_interval_score90']:
        if not np.isclose(zero[col],original[col],atol=1e-8,rtol=0):raise ValueError('zero-shift metric differs from original: '+col)
    d2=change.loc[change.variable.eq('D2')]
    if len(d2)!=2 or not d2.n_common.eq(score['all_shift_common_cases']).all():raise ValueError('prediction movement cohort differs')
    max_d2=float(d2.max_abs_change.max())
    macros={'NSClockCases':str(int(score['all_shift_common_cases'])),
      'NSClockHMax':f"{score['max_abs_reference_h30_change_c']:.4f}",
      'NSClockDTwoMax':f'{max_d2:.3f}',
      'NSClockDTwoMinus':f"{a.loc[a.shift_hours.eq(-1),'D2_mae'].iloc[0]:.3f}",
      'NSClockDTwoZero':f'{zero.D2_mae:.3f}',
      'NSClockDTwoPlus':f"{a.loc[a.shift_hours.eq(1),'D2_mae'].iloc[0]:.3f}",
      'NSClockClassicMinus':f"{a.loc[a.shift_hours.eq(-1),'stochastic_mae'].iloc[0]:.3f}",
      'NSClockClassicZero':f'{zero.stochastic_mae:.3f}',
      'NSClockClassicPlus':f"{a.loc[a.shift_hours.eq(1),'stochastic_mae'].iloc[0]:.3f}"}
    (PAPER/'nova_clock_sensitivity_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items()))
    lines=[r'\section{Nova Scotia reported-day boundary sensitivity}',
      ('After inspecting the exploratory results, we tested hypothetical daily bins shifted by $-1$, 0 and $+1$ hour '
       'relative to the recorded clock labels. We required all original eight station-years and the adjacent boundary hours to be '
       'unique, finite and equal within $10^{-6}$ $^{\circ}$C across the two releases; missing or disputed hours were not filled. '
       'Daily water inputs and local leave-one-year-out models were rebuilt for each shift, with the original masks, '
       'global source model, source calibration and NASA POWER local-solar-time forcing held fixed. '
       'All '+str(int(score['all_shift_common_cases']))+' masks are available across all three shifts for both methods; '
       'the zero-shift replay agrees with the original outputs. Across the eight reported reference years the largest H30 change '
       'is '+f"{score['max_abs_reference_h30_change_c']:.4f}"+' $^{\circ}$C, while a post-hoc casewise diagnostic finds a largest '
       'D2 point-prediction change of '+f'{max_d2:.3f}'+' $^{\circ}$C. This does not identify the true timezone or explain the '
       'cause of prediction changes; hourly values, quality and meteorological day alignment remain uncertain. '
       'The two sites and repeated masks do not justify a population-level ranking or independent-climate inference.'),
      r'\begin{table}[p]\centering\small',
      r'\caption{Paired exploratory reported-day boundary sensitivity with identical original masks. Coverage is percent and error, width and interval score are in $^{\circ}$C. Local stages are refit; source model, source calibration and forcing are held fixed. Two sites and eight station-years are not independent climatic replications.}\label{tab:ns-clock-sensitivity}',
      r'\begin{tabular}{rlrrrrr}\toprule',
      r'Shift (h) & Method & Cases & MAE & 90\% coverage & Width & Interval score\\\midrule']
    for r in a.itertuples(index=False):
        for name,label in [('D2','D2'),('stochastic','Stochastic')]:
            lines.append(' & '.join([str(int(r.shift_hours)),label,str(int(r.n_common)),f'{getattr(r,name+"_mae"):.3f}',
              f'{100*getattr(r,name+"_coverage90"):.1f}',f'{getattr(r,name+"_width90"):.3f}',f'{getattr(r,name+"_interval_score90"):.3f}'])+r'\\')
    lines.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'nova_clock_sensitivity_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','common_cases':int(score['all_shift_common_cases']),'stations':int(score['sites']),
      'station_years':int(score['station_years']),'max_reference_h30_change_c':float(score['max_abs_reference_h30_change_c']),
      'max_d2_point_change_c':max_d2,'zero_shift_replay_max_difference':float(score['max_zero_shift_replay_difference']),
      'paired_scores':a[['shift_hours','D2_mae','stochastic_mae','D2_coverage90','stochastic_coverage90','D2_width90','stochastic_width90','D2_interval_score90','stochastic_interval_score90']].to_dict('records'),
      'integrity_case_rows':integrity['case_rows'],'strict_reference_qualified':False,'limitation':score['limitation']}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
