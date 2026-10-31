#!/usr/bin/env python3
"""Render past-only warm-season screening results without prospective claims."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/past_season_screening'
PAPER=ROOT/'paper/wrr_tr'


def main():
    audit=json.loads((OUT/'independent_audit.json').read_text())
    if audit['status']!='passed' or audit['station_years_independently_reconstructed']!=2656 or audit['changed_season_probes']!=0:
        raise ValueError('Past-only screening audit incomplete')
    summary=pd.read_csv(OUT/'summary.csv').set_index('rule')
    before=summary.loc['warm90_leave_year_out'];past=summary.loc['warm90_past'];strict=summary.loc['warm90_past_four_complete']
    transitions=pd.read_csv(OUT/'transitions.csv')
    changed=transitions[(transitions.method=='warm90_past')&(transitions.leave_year_out!=transitions.past)].station_years.sum()
    data=pd.read_csv(OUT/'station_year_decisions.csv')
    incomplete=data[data.rule.eq('warm90_past_four_complete') & ~data.complete_year]
    unknown_bounds=int(incomplete[incomplete.state.eq('unknown')].reported_window.notna().sum())
    if unknown_bounds!=audit['four_complete_unknown_with_observed_window']:raise ValueError('Unknown bound count differs')
    past_incomplete=data[data.rule.eq('warm90_past') & ~data.complete_year]
    minimum_days=int(past_incomplete.prior_finite_days.min())
    vals={'PWYears':f'{int(strict.station_years):,}','PWChange':str(int(changed)),'PWMinimumDays':str(minimum_days),
          'PWUnknown':str(int(strict.unknown)),'PWUnknownBounds':str(unknown_bounds),
          'PWWitnessAccepted':str(int(strict.witness_accepted)),'PWWitnessRejected':str(int(strict.witness_rejected)),
          'PWWitnessUnknown':str(int(strict.witness_unknown)),'PWWitnessPrior':str(int(strict.witness_rejected_above_prior_record))}
    (PAPER/'past_season_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    names={'complete_100':'Complete year','annual_95':'Annual 95\\%','warm90_leave_year_out':'Warm 90\\%, leave year out',
           'warm90_past':'Warm 90\\%, past data','warm90_past_four_complete':'Warm 90\\%, past + 4 complete'}
    rows=[]
    for key in names:
        r=summary.loc[key]
        rows.append(f"{names[key]} & {int(r.accepted):,} & {int(r.rejected)} & {int(r.unknown)} & {int(r.rejected_with_bound)} & {int(r.rejected_above_prior_reported_record)} & {int(r.witness_accepted)} / {int(r.witness_rejected)} / {int(r.witness_unknown)} \\\\")
    text=r'''\section{Past-only warm-season sensitivity}
The original station-specific warm season leaves out the evaluated year but can use observations from later years. After inspecting that comparison and the 35 selected witnesses, we recomputed the same 15-day-smoothed day-of-year climatology and five-month selection with only daily values from years strictly before each evaluated year. The source is the current processed archive, not a historically timestamped data vintage. The 95 stations and 35 witnesses were themselves selected using records available after some evaluated years, so this is a retrospective information-separation sensitivity, not a prospective site recruitment or field performance test.

Two past-only variants are reported. One uses any earlier finite water observation, which can amount to only \PWMinimumDays{} day for an incomplete year; climatological interpolation with so little data is not evidence of adequate support. The other requires at least four fully observed prior calendar years before classifying an incomplete year. Complete years are accepted even if the climatology is unavailable, because every possible warm season is fully observed. The four-year threshold is an exploratory study choice, not a published standard. Unsupported incomplete years remain unknown rather than being counted as rejections. On \PWYears{} eligible station-years, the past-only variant without a minimum changes \PWChange{} decision relative to the original leave-year-out rule; the four-year version leaves \PWUnknown{} years unknown, \PWUnknownBounds{} of which still have an observed 30-day lower bound.

Table~\ref{tab:past-season} also compares the reported observed-window maximum in each rejected year to the greatest reported window from earlier years accepted by that same rule. A rejected year contributes only if both its observed bound and an earlier accepted reported window exist. Earlier accepted incomplete years can have an unobserved higher H30, and these are not comparisons with physical sensor truth. The leave-year-out rule's earlier classifications may use years later than their evaluation year; only the past-only rules enforce the stated temporal information boundary. Among the 35 retrospectively selected witnesses, the four-prior-complete-years variant accepts \PWWitnessAccepted{}, rejects \PWWitnessRejected{} and leaves \PWWitnessUnknown{} unknown; \PWWitnessPrior{} rejected witnesses exceed the earlier accepted reported-window maximum. These counts are not an incidence estimate.

\begin{table}[ht]\caption{Retrospective screening in the 95-station candidate subset. ``Above prior'' counts rejected years whose observed 30-day window exceeds all earlier accepted reported windows. Witness column gives accepted / rejected / unknown among 35 previously selected incomplete years.}\label{tab:past-season}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrrrr}\toprule
Rule & Accepted & Rejected & Unknown & Rejected with bound & Above prior & Witnesses \\
\midrule
'''+'\n'.join(rows)+r'''
\bottomrule\end{tabular}}\end{table}

An independent implementation rebuilt all 2,656 earlier-only climatologies, 13,280 rule states and prior-record comparisons on the same processed daily records. In 35 witness-year probes, shifting the target and all later observations by 5 $^{\circ}$C did not change the earlier-only warm season. These checks do not verify historical data vintages, station selection, provider quality control or physical measurement accuracy.
'''
    (PAPER/'past_season_supporting.tex').write_text(text)
    print('Rendered past-only warm-season sensitivity')


if __name__=='__main__':main()
