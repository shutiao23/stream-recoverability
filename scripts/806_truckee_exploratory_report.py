#!/usr/bin/env python3
"""Render the checked Truckee exploratory reference and model comparison."""
import json
import math
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PAPER=ROOT/'paper/wrr_tr'


def one(f,**k):
    for name,value in k.items():f=f[f[name].eq(value)]
    if len(f)!=1:raise ValueError('Expected unique Truckee score row')
    return f.iloc[0]


def main():
    time=json.loads((OUT/'time_upper_bound_status.json').read_text());finite=json.loads((OUT/'finite_reference_status.json').read_text())
    audit=json.loads((OUT/'exploratory_score_independent_audit.json').read_text());probe=json.loads((OUT/'exploratory_hidden_probe.json').read_text())
    replay=json.loads((ROOT/'results/wrr_review_response_20261027/audit/truckee_open_reference_replay.json').read_text())
    peak=json.loads((OUT/'peak_visibility_status.json').read_text());peak_audit=json.loads((OUT/'peak_visibility_independent_audit.json').read_text())
    clock=json.loads((OUT/'power_time_comparison.json').read_text());clock_audit=json.loads((OUT/'power_time_independent_audit.json').read_text())
    clock_replay=json.loads((ROOT/'results/wrr_review_response_20261027/audit/truckee_power_time_open_replay.json').read_text())
    field=json.loads((OUT/'wqp_field_comparison_status.json').read_text());field_audit=json.loads((OUT/'wqp_field_independent_audit.json').read_text())
    field_replay=json.loads((ROOT/'results/wrr_review_response_20261027/audit/truckee_wqp_open_replay.json').read_text())
    if (time['status']!='timestamp_upper_bound_completed' or finite['status']!='finite_published_reference_screened'
            or audit['status']!='passed' or probe['status']!='passed' or replay['status']!='passed'
            or peak['status']!='computed_posthoc' or peak_audit['status']!='passed'
            or clock['status']!='computed_posthoc' or clock_audit['status']!='passed' or clock_replay['status']!='passed'
            or field['status']!='computed_posthoc' or field_audit['status']!='passed' or field_replay['status']!='passed'):
        raise ValueError('Truckee checks incomplete')
    pairs=pd.read_csv(OUT/'exploratory_paired_summary.csv');scores=pd.read_csv(OUT/'exploratory_score_summary.csv')
    allrow=one(pairs,stratum='all');plug=one(scores,stratum='all',estimator='plug_in')
    visibility=pd.read_csv(OUT/'peak_visibility_summary.csv');hidden_d2=one(visibility,stratum='reference_above_bound',estimator='D2')
    hidden_stoch=one(visibility,stratum='reference_above_bound',estimator='stochastic_calibrated')
    field_all=one(pd.read_csv(OUT/'wqp_time_strata_summary.csv'),stratum='all')
    field_exact=one(pd.read_csv(OUT/'wqp_time_strata_summary.csv'),stratum='exact_quarter_hour')
    field_site=pd.read_csv(ROOT/'data/external/wrr_truckee_dwr_20261027/wqp_field_snapshot/station_metadata_minimal.csv').iloc[0]
    logger_site=one(pd.read_csv(OUT/'station_metadata_03.csv'),Station_Code='TRB8')
    instrument=one(pd.read_csv(OUT/'station_metadata_02.csv'),Station_Code='TRB8')
    instrument_change=pd.to_datetime(instrument.Start_Date_YSIEXO2,format='%m/%d/%Y',errors='raise')
    if instrument_change.year!=2019:raise ValueError('Reassess Truckee instrument-era interpretation')
    lat1,lon1,lat2,lon2=map(math.radians,[float(field_site.LatitudeMeasure),float(field_site.LongitudeMeasure),float(logger_site.Latitude),float(logger_site.Longitude)])
    coord_distance=12742000*math.asin(math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2))
    if int(allrow.n_common)!=72 or int(allrow.station_years)!=4 or int(allrow.stations)!=1:raise ValueError('Reassess external cohort')
    if (hidden_d2.n_common!=hidden_stoch.n_common or hidden_d2.n_common!=peak['cases_by_stratum']['reference_above_bound']
            or clock['finite_hour_pairs']!=clock['expected_hours'] or clock['hour_pairs_equal_1e_6']!=clock['finite_hour_pairs']
            or clock['complete_hourly_and_daily_pairs']!=clock['expected_days'] or len(clock_audit['hourly_api_versions'])!=1
            or field['source_years_with_wqp_rows']!=[2011,2013,2014] or field['eligible_field_rows']!=field['wqp_rows']
            or field['comparable_rows']!=int(field_all.comparable_observations)):raise ValueError('Reassess visibility, POWER or field interpretation')
    macros={'TruckeeCases':str(int(allrow.n_common)),'TruckeeDTwoMAE':f'{allrow.D2_mae:.3f}',
            'TruckeeStochasticMAE':f'{allrow.stochastic_mae:.3f}','TruckeePluginMAE':f'{plug.mae:.3f}',
            'TruckeeDTwoCoverage':f'{100*allrow.D2_coverage90:.1f}','TruckeeStochasticCoverage':f'{100*allrow.stochastic_coverage90:.1f}',
            'TruckeeVisibleN':str(peak['cases_by_stratum']['reference_equals_bound']),'TruckeeHiddenN':str(peak['cases_by_stratum']['reference_above_bound']),
            'TruckeeHiddenDTwoMAE':f'{hidden_d2.mae:.3f}','TruckeeHiddenStochasticMAE':f'{hidden_stoch.mae:.3f}',
            'TruckeeHiddenDTwoCovered':str(round(hidden_d2.coverage90*hidden_d2.n_common)),
            'TruckeeHiddenStochasticCovered':str(round(hidden_stoch.coverage90*hidden_stoch.n_common)),
            'TruckeeHiddenDTwoWidth':f'{hidden_d2.mean_width90:.3f}','TruckeeHiddenStochasticWidth':f'{hidden_stoch.mean_width90:.3f}',
            'TruckeePowerPairs':f"{clock['finite_hour_pairs']:,}",'TruckeePowerDays':f"{clock['complete_hourly_and_daily_pairs']:,}",
            'TruckeePowerMaxDifference':f"{clock['max_daily_difference_c']:.3f}",
            'TruckeeHourlyVersion':str(clock_audit['hourly_api_versions'][0]),'TruckeeDailyVersion':str(clock_audit['daily_api_version']),
            'TruckeeFieldCount':str(int(field_all.comparable_observations)),
            'TruckeeFieldExactCount':str(int(field_exact.comparable_observations)),
            'TruckeeFieldExactMAE':f'{field_exact.mae:.3f}',
            'TruckeeFieldExactBias':f'{field_exact.bias_field_minus_logger:+.3f}',
            'TruckeeFieldWithinHalf':str(int(field_all.within_0_5_c)), 'TruckeeFieldCoordinateDistance':str(round(coord_distance)),
            'TruckeeInstrumentChangeDate':instrument_change.strftime('%d %B %Y').lstrip('0')}
    (PAPER/'truckee_values.tex').write_text(''.join('\\newcommand{\\'+key+'}{'+value+'}\n' for key,value in macros.items()))
    rows=[]
    for estimator,label in [('plug_in','Plug-in'),('D2','D2'),('stochastic_calibrated','Calibrated stochastic')]:
        x=one(scores,stratum='all',estimator=estimator)
        coverage='--' if estimator=='plug_in' else f'{100*x.coverage90:.1f}'
        width='--' if estimator=='plug_in' else f'{x.width90:.3f}'
        score='--' if estimator=='plug_in' else f'{x.interval_score90:.3f}'
        rows.append(f'{label} & {int(x.n_point_available)} & {x.mae:.3f} & {x.bias:.3f} & {coverage} & {width} & {score} '+r'\\')
    text=r'''\section{Truckee River reported-clock exploratory evaluation}
After the original reference attempts, we accessed the California Department of Water Resources 12-station Truckee water-quality dataset through the public DataONE resolver (\url{https://doi.org/10.6073/pasta/aefcf302d088aeacc40459091d7e990c}). EML documents provider quality checks and labels the observation clock PST; individual estimated or corrected values are not flagged. Earlier project inventories contain downstream USGS observations from the same watershed. On the named coordinate inventory, the nearest previously known station to each DWR station is more than 10 km away, but coordinate separation does not establish distinct rivers, independent source-model groups or climates. The 12 sites are in one managed watershed.

The station list reports an impossible start after its end for one station; we retained that site for the preplanned timestamp screen instead of interpreting the inconsistency as zero observations. All 12 files have at least four years with a complete grid of unique quarter-hour labels, but this is an upper bound: after requiring all 96 reported water values per day to be finite, only 18 of 171 station-years are complete, and only one station has four such years. The selected years are 2011, 2013, 2014 and 2020 at TRB8. The finite reference consists of each reported-day arithmetic mean of 96 values; it is not a verified nonestimated, physically error-free reference. A second CSV/set implementation recomputed every day and year. The EDI EML declares CC0 while the California discovery catalog lists Creative Commons Attribution; source attribution is retained and the difference requires reconciliation before permanent release.

After observing availability and numerical reference completeness, but before calculating H30 or target prediction errors, we fixed the one-station cohort and source model. We hold each target year out, use the other three selected years as local history, hide the target gap and use no donor stations. Controlled 30-, 60- and 90-day gaps are crossed with a training-period climatological peak window, with two realizations per cell; there are 72 repeated masks, not 72 independent stations or years. The fixed global source model and source-only calibration are reused. The complete-record reference is subject to sensor and provider-processing uncertainty. No trend is estimated from four years.

After viewing these results, we tested the current NASA POWER hourly UTC and LST products at the same rounded coordinates. For January 1 through December 30 of each reference year, all \TruckeePowerPairs{} finite LST values equal UTC values eight hours later within $10^{-6}$ $^{\circ}$C; 24-hour LST means differ from the originally retrieved daily product by at most \TruckeePowerMaxDifference{} $^{\circ}$C over \TruckeePowerDays{} days. Hourly and daily API versions are \TruckeeHourlyVersion{} and \TruckeeDailyVersion{} respectively. If the provider's PST labels denote fixed UTC-8, the two day boundaries agree; the actual water sensor's daylight handling or other clock shifts remain unverified. These numerical checks do not validate either product's physical accuracy or historical version.

Table~\ref{tab:truckee-exploratory} summarizes the same 72 available cases. D2 coverage is 16/18 in 2011 and 18/18 in each of the other three years; pooling repeated masks does not establish interval calibration or generality. Independent arithmetic reconstructed all 72 references, bounds and score cells. A single post-hoc 90-day hidden-peak perturbation left model inputs and predictions unchanged while altering the hidden reference; it is a diagnostic, not exhaustive proof against leakage. No group-bootstrap interval is reported for one watershed.

In a further post-hoc stratification, the complete reference equals the observed bound in \TruckeeVisibleN{} masks and exceeds it in \TruckeeHiddenN{}. In the latter, D2 / calibrated-stochastic MAE is \TruckeeHiddenDTwoMAE{} / \TruckeeHiddenStochasticMAE{} $^{\circ}$C; their 90\% coverage is \TruckeeHiddenDTwoCovered/\TruckeeHiddenN{} / \TruckeeHiddenStochasticCovered/\TruckeeHiddenN{} and mean width is \TruckeeHiddenDTwoWidth{} / \TruckeeHiddenStochasticWidth{} $^{\circ}$C. This stratification uses the hidden complete reference and is unavailable as a decision-time rule. All masks still reuse only four years and one station; the selected comparison and apparent coverage cannot establish population or climate-transfer performance.

After the model results were viewed, a Water Quality Portal search identified a field-measurement record at the same DWR station identifier (\url{https://www.waterqualitydata.us/provider/STORET/CALWR_WQX/CALWR_WQX-G7166310/}). The published coordinates differ by approximately \TruckeeFieldCoordinateDistance{} m; the actual sampling positions are unknown. The query returned \TruckeeFieldCount{} accepted, actual field-temperature observations for 2011, 2013 and 2014, and no records for 2020. DWR metadata records an EXO2 instrument start on \TruckeeInstrumentChangeDate{}; these field records therefore do not examine the 2020 instrument period. All carry PST labels and EPA thermometric method 170.1, whose description permits different thermometer types (\url{https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=30000Q10.TXT}). Matching each to the nearest scheduled 15-minute logger time gives \TruckeeFieldWithinHalf/\TruckeeFieldCount{} differences within 0.5 $^{\circ}$C; the maximum time offset is six minutes. A further post-hoc timing stratification finds a mean absolute difference of \TruckeeFieldExactMAE{} $^{\circ}$C and a field-minus-logger mean difference of \TruckeeFieldExactBias{} $^{\circ}$C among \TruckeeFieldExactCount{} exactly coincident labels. The records are from the same agency and station, and do not identify whether a separate instrument was used. Field visits are sparse and may coincide with servicing; these instantaneous differences cannot be converted directly into uncertainty in a 30-day H30 maximum. The comparison assumes both PST labels refer to the same fixed clock and is not an independent-climate test.

\begin{table}[ht]\caption{Truckee exploratory annual H30 scores on 72 controlled masks from one station and four years. MAE, bias, width and interval score are $^{\circ}$C; coverage is percent for the nominal 90\% interval. The plug-in method supplies no interval.}\label{tab:truckee-exploratory}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrrrr}\toprule
Method & Available & MAE & Bias & Coverage & Width & Score \\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule\end{tabular}}\end{table}

The local candidate includes the public DWR source files, provider metadata, reconstructed daily values, a reduced WQP field snapshot and the retrieved POWER responses; offline replays recalculate the timestamp, finite-value, field-comparison and forcing checks. The state catalog describes a DWR discrete dataset as public domain, but a record-level crosswalk to this WQP feed was not independently established. The package does not reproduce model scores without the restricted global source-model weights and calibration. A request for access to those materials or a permitted replacement is still needed.
'''
    (PAPER/'truckee_exploratory_supporting.tex').write_text(text);print('Rendered checked single-station Truckee exploratory results')


if __name__=='__main__':main()
