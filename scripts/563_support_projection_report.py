#!/usr/bin/env python3
"""Summarize saved annual support contacts against complete reference H30."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/whole_archive'


def main():
    status=json.loads((OUT/'support_projection_status.json').read_text())
    if not status['passed']:raise RuntimeError('Support audit has not passed')
    f=pd.read_csv(OUT/'support_projection_summary.csv')
    def row(family,estimator):
        x=f.loc[f.family.eq(family)&f['mode'].eq('forward')&f.estimator.eq(estimator)]
        if len(x)!=1:raise ValueError('Nonunique support summary')
        return x.iloc[0]
    d=row('calendar','D2');s=row('calendar','stochastic_calibrated');dc=row('crossed','D2');sc=row('crossed','stochastic_calibrated')
    if d.paired_rows!=s.paired_rows or dc.paired_rows!=sc.paired_rows:raise ValueError('Estimator comparison is not on shared cases')
    stage_status=json.loads((OUT/'projection_stage_status.json').read_text())
    if stage_status['status']!='passed':raise RuntimeError('Projection stage replay has not passed')
    stage=pd.read_csv(OUT/'projection_stage_summary.csv')
    def stage_row(estimator):
        x=stage.loc[stage.family.eq('calendar')&stage['mode'].eq('forward')&stage.estimator.eq(estimator)]
        if len(x)!=1:raise ValueError('Nonunique projection-stage summary')
        return x.iloc[0]
    sd=stage_row('D2');ss=stage_row('stochastic_calibrated')
    if sd.n!=d.paired_rows or ss.n!=s.paired_rows or sd.final_zero!=d.zero_width90 or ss.final_zero!=s.zero_width90:
        raise ValueError('Projection stage and previous support audit disagree')
    values={'SPCalendarCommon':f'{int(d.paired_rows):,}',
            'SPCalendarDTwoZero':f'{int(d.zero_width90):,}', 'SPCalendarDTwoPercent':f'{100*d.zero_width90/d.paired_rows:.1f}',
            'SPCalendarClassicZero':f'{int(s.zero_width90):,}', 'SPCalendarClassicPercent':f'{100*s.zero_width90/s.paired_rows:.1f}',
            'SPCalendarDTwoMiss':str(int(d.zero_width90_missed)), 'SPCalendarClassicMiss':str(int(s.zero_width90_missed)),
            'SPCrossCommon':f'{int(sc.paired_rows):,}',
            'SPCrossDTwoZero':f'{int(dc.zero_width90):,}', 'SPCrossClassicZero':f'{int(sc.zero_width90):,}',
            'SPCrossClassicMiss':str(int(sc.zero_width90_missed)),
            'SPCrossDTwoMedian':f'{int(dc.median_at_bound):,}', 'SPCrossDTwoMedianAbove':str(int(dc.median_at_bound_truth_above)),
            'SPCrossClassicMedian':f'{int(sc.median_at_bound):,}', 'SPCrossClassicMedianAbove':str(int(sc.median_at_bound_truth_above)),
            'SPCrossClassicMissStations':str(int(sc.zero_width90_missed_stations)),
            'SPCrossClassicMaxMiss':f'{sc.zero_width90_missed_max_abs_error:.3f}',
            'SPCalendarDTwoCreatedLast':str(int(sd.zero_created)),
            'SPCalendarDTwoBeforeLast':f'{int(sd.pre_zero):,}',
            'SPCalendarClassicCreatedLast':str(int(ss.zero_created)),
            'SPCalendarClassicRawZero':f'{int(ss.raw_zero):,}'}
    (ROOT/'paper/wrr_tr/support_projection_values.tex').write_text(''.join(
        '\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    table=[r'\begin{table}[p]\centering\scriptsize',
           r'\caption{Replay of annual interval stages on common finite-bound cases. Raw is the original model output; stochastic raw quantiles use a finite set of imputations that retain observed days. First applies the first explicit bound projection; Pre-final applies the fixed projection-aware offsets and sorts; Final applies the bound again. New is the count first becoming zero-width at the final projection. Zero widths use $10^{-8}$ $^{\circ}$C tolerance. These are repeated mask cases, and no alternative calibration was fitted.}\label{tab:projection-stage-replay}',
           r'\begin{tabular}{lllrrrrrr}\toprule',
           r'Family & Setting & Estimator & $n$ & Raw & First & Pre-final & Final & New\\\midrule']
    for _,r in stage.iterrows():
        method='D2' if r.estimator=='D2' else 'Stochastic'
        vals=[r.family,r['mode'],method,*[str(int(r[k])) for k in ('n','raw_zero','first_projection_zero','pre_zero','final_zero','zero_created')]]
        table.append(' & '.join(vals)+r'\\')
    table.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (ROOT/'paper/wrr_tr/projection_stage_table.tex').write_text('\n'.join(table)+'\n')
    report={'forward_calendar_common_cases':int(d.paired_rows),
            'D2_zero_width':int(d.zero_width90),'stochastic_zero_width':int(s.zero_width90),
            'D2_zero_width_uncovered':int(d.zero_width90_missed),'stochastic_zero_width_uncovered':int(s.zero_width90_missed),
            'forward_controlled_common_cases':int(sc.paired_rows),'controlled_stochastic_zero_width':int(sc.zero_width90),
            'controlled_stochastic_zero_width_missed':int(sc.zero_width90_missed),
            'controlled_stochastic_miss_stations':int(sc.zero_width90_missed_stations),
            'controlled_stochastic_miss_station_years':int(sc.zero_width90_missed_station_years),
            'forward_calendar_D2_zero_created_last_projection':int(sd.zero_created),
            'forward_calendar_D2_zero_before_last_projection':int(sd.pre_zero),
            'forward_calendar_stochastic_zero_created_last_projection':int(ss.zero_created),
            'forward_calendar_stochastic_raw_zero':int(ss.raw_zero),
            'limitation':'case counts include repeated masks; coverage is against finite complete reported records, not the error-free physical water temperature; pre-final results retain the first projection and offsets calibrated with projection'}
    (OUT/'support_projection_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
