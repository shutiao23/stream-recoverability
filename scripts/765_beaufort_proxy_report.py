#!/usr/bin/env python3
"""Render checked, post-hoc literature-inspired summer-peak comparison."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/beaufort_proxy';PAPER=ROOT/'paper/wrr_tr'


def one(frame,**conditions):
    for k,v in conditions.items():frame=frame[frame[k].eq(v)]
    if len(frame)!=1:raise ValueError('Expected unique proxy result: '+str(conditions))
    return frame.iloc[0]


def main():
    status=json.loads((OUT/'status.json').read_text());audit=json.loads((OUT/'independent_audit.json').read_text())
    air=json.loads((OUT/'air_snapshot_status.json').read_text());remote=json.loads((OUT/'power_vintage_status.json').read_text())
    remote_audit=json.loads((OUT/'power_vintage_independent_audit.json').read_text())
    if (status['status']!='computed_posthoc' or audit['status']!='passed' or audit['case_masks_recomputed']!=11220
            or status['unavailable_records']!=0 or air['stations_complete_for_all_lags']!=22
            or remote['status']!='completed' or remote_audit['status']!='passed'):
        raise ValueError('Literature-proxy checks incomplete')
    summary=pd.read_csv(OUT/'summary.csv');vintage=pd.read_csv(OUT/'power_vintage_summary.csv')
    roster=pd.read_csv(OUT/'roster.csv')
    if roster.regulation_status.value_counts().to_dict()!={'unmatched_gages':21,'regulated':1}:
        raise ValueError('Reassess regulation-inventory description')
    total=one(vintage,provider='all')
    if int(total.responses_available)!=15 or int(total.both_finite_days)!=9585 or int(total.matching_days_at_1e_5_c)!=9585:
        raise ValueError('Reassess source-vintage description')
    summer1=one(summary,missing_years=1,target='summer');calendar1=one(summary,missing_years=1,target='calendar')
    vals={'BFStations':str(status['available_stations']),'BFGroups':str(status['planned_groups']),
          'BFCases':f"{status['station_case_rows']:,}",'BFOneCases':str(int(summer1.n_available)),
          'BFSummerObs':f'{summer1.observed_mae:.3f}','BFSummerFill':f'{summer1.filled_mae:.3f}',
          'BFCalendarObs':f'{calendar1.observed_mae:.3f}','BFCalendarFill':f'{calendar1.filled_mae:.3f}',
          'BFVintageDays':f'{int(total.both_finite_days):,}','BFVintageRequests':str(int(total.responses_available))}
    (PAPER/'beaufort_proxy_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    table=[]
    for target,label in [('summer','Summer'),('calendar','Full-year')]:
        for k in [1,2,4,6,8]:
            r=one(summary,missing_years=k,target=target)
            table.append(f'{label} & {k} & {int(r.n_available)} & {r.observed_mae:.3f} & {r.filled_mae:.3f} & '
                         f'{r.mean_abs_error_difference:.3f} & [{r.bootstrap_low:.3f}, {r.bootstrap_high:.3f}] '+r'\\')
    text=r'''\section{Literature-inspired interannual thermal-peak comparison}
After inspecting earlier results and data availability, we selected all \BFStations{} of the previously eligible 95 stations with complete reported water years from 2009 through 2017. They belong to \BFGroups{} connected groups; project labels mark one as regulated and leave the others unmatched to the regulation inventory, not necessarily natural. Following the structure described by Beaufort et al. (\url{https://doi.org/10.5194/hess-26-3477-2022}), we examine a nine-year mean of annual 30-day peaks and fill missing summer daily water with station-specific regressions on right-aligned 2--10-day air-temperature means. In each synthetic experiment, we hide 1--8 whole years in every possible combination, select the lag with the highest in-sample $R^2$ using retained summers only, and fit the regression without withheld-year water. We calculate the 30-day maximum wholly contained in July--August for observed and predicted years. All nine years hidden is unavailable because no local fitting data remain. The 11,220 station--mask cases reuse only 22 stations and are not independent climate replicates.

The primary reference is the mean of the nine observed July--August 30-day maxima. A separately reported reference is the mean of the nine full-calendar-year H30 values; this changes the target, so any summer-only estimator may omit a peak outside July--August. The unfilled comparison averages only the retained years; the filled comparison averages retained observed peaks and reconstructed missing-year summer peaks. Both methods are evaluated on the same cases. These are point estimates of interannual averages, not annual H30 recovery, trend, interval calibration or release-rule validation. The observed-only mean bias across the exhaustive symmetric masks is zero for the summer reference by construction; this does not establish unbiasedness under real missingness.

Table~\ref{tab:beaufort-proxy} reports station-equal MAE and 4,000 connected-group bootstrap intervals for the filled-minus-observed absolute-error difference, with one row per station in the group resample. The comparison is post-hoc and uses ten project connected groups; the resampling interval is descriptive and depends on those groups. Other missing-year counts and leave-one-provider-out results are in the aggregate output. Removing a provider does not refit models or establish independent climates.

\begin{table}[ht]\caption{Adapted summer-regression proxy against two distinct nine-year targets. MAE and filled-minus-observed MAE differences are $^{\circ}$C; cases are repeated year masks.}\label{tab:beaufort-proxy}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrrrr}\toprule
Reference & Hidden years & Cases & Observed MAE & Filled MAE & Difference & Group interval \\
\midrule
'''+ '\n'.join(table)+r'''
\bottomrule\end{tabular}}\end{table}

This is an adaptation, not a reproduction of the French study: it uses a different station population, processed water records, NASA POWER-based daily air instead of SAFRAN, explicit train-only fitting, all combinations of hidden years, and a July--August-contained peak definition. The published article does not establish all of our implementation choices. NASA POWER's gridded local-solar air days may not align with provider water days; the original API version and raw response for these 22 cached stations were not retained. After viewing the proxy results, we requested current NASA POWER responses for \BFVintageRequests{} representatives of distinct stored air series. All \BFVintageDays{} comparable summer and lag-input days matched within $10^{-5}$ $^{\circ}$C. This does not establish historical version, unrequested stations, air or water accuracy, clock alignment or independent-climate generality. A separate implementation recomputed \BFCases{} masks and all 16 summary cells from the same processed inputs; it did not reproduce the original authors' datasets or code.
'''
    (PAPER/'beaufort_proxy_supporting.tex').write_text(text)
    print('Rendered literature-inspired interannual thermal-peak comparison')


if __name__=='__main__':main()
