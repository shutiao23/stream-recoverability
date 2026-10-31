#!/usr/bin/env python3
"""Summarize the BC published-daily exploratory comparison and its limits."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/external_bc_air2stream'


def main():
    status = json.loads((OUT/'status.json').read_text())
    if not status.get('reconstruction_accuracy_evaluated'):
        raise RuntimeError('No BC results to summarize')
    data = pd.read_parquet(OUT/'predictions.parquet')
    truth = data.eval_truth_h30.to_numpy(float)
    lower = data.observed_lower_bound__observed_days.to_numpy(float)
    violations = {}
    for method, col in [('D2','D2'), ('stochastic','stochastic_cal_q50')]:
        pred = data[col].to_numpy(float)
        violations[method] = int(np.sum(np.isfinite(lower) & np.isfinite(pred) & (pred < lower-1e-8)))
    if any(violations.values()):
        raise ValueError(f'Published-day lower-bound contradictions: {violations}')
    by_site = []
    for (site, family), group in data.groupby(['station_key','design_family']):
        truth = group.eval_truth_h30.to_numpy(float)
        row = dict(station_key=site, family=family, cases=len(group), years=group.year.nunique())
        for name, col in [('plugin','h30__policy'), ('D2','D2'), ('stochastic','stochastic_cal_q50')]:
            p=group[col].to_numpy(float); valid=np.isfinite(p)&np.isfinite(truth)
            row[name+'_available'] = int(valid.sum())
            row[name+'_mae'] = float(np.mean(abs(p[valid]-truth[valid]))) if valid.any() else np.nan
        by_site.append(row)
    pd.DataFrame(by_site).to_csv(OUT/'site_scorecard.csv',index=False)
    status.update(n_station_years=int(data[['station_key','year']].drop_duplicates().shape[0]),
                  n_families=data.design_family.value_counts().to_dict(),
                  lower_bound_violations=violations,
                  bound_interpretation='bound applies to published daily-mean series; 24h physical-day bound not established',
                  network_dependence='three sites lie in the Fraser River basin (Nechako, Thompson and Fraser); all share British Columbia climate and are not four independent regions')
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    scores=pd.read_csv(OUT/'annual_scorecard.csv')
    f=scores.loc[scores.family.eq('crossed') & scores.stratum.eq('all')].set_index('estimator')
    vals = {'BCStations':str(status['n_scored_stations']), 'BCYears':str(status['n_station_years']),
            'BCCases':str(int(f.loc['D2','n_eligible'])),
            'BCPluginMAE':f"{f.loc['plug_in','mae']:.3f}",
            'BCDTwoMAE':f"{f.loc['D2','mae']:.3f}",
            'BCStochasticMAE':f"{f.loc['stochastic_calibrated','mae']:.3f}",
            'BCDTwoCoverage':f"{100*f.loc['D2','coverage90']:.1f}",
            'BCStochasticCoverage':f"{100*f.loc['stochastic_calibrated','coverage90']:.1f}"}
    (ROOT/'paper/wrr_tr/bc_exploratory_values.tex').write_text(''.join(
        '\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    reference_integrity=json.loads((OUT/'reference_integrity.json').read_text())
    hidden_audit=json.loads((OUT/'hidden_value_audit.json').read_text())
    if not reference_integrity['passed'] or not hidden_audit['passed']:
        raise RuntimeError('BC reference integrity or hidden-value probe failed')
    table = pd.DataFrame(by_site)
    table = table.loc[table.family.eq('crossed')].sort_values('station_key')
    lines = [r'\section{Exploratory British Columbia daily-reference comparison}',
             r'All 23 author-selected published stations were retained for qualification. Four stations each have four complete calendar years in the published daily series. The original study accepted daily means based on at least 20 hourly values after researcher quality checks; hourly counts, original flags and the day convention are not available in this derivative. The source-water cleaning used water--air comparisons. A complete published year is not equivalent to 24 independently quality-checked hours per day. The 23-station author cohort was selected for data availability and these results are unregistered.',
             r'The fixed global source model and independent source-role recalibration are used; local reconstruction models are refit after holding out the scored year. Each year is masked separately, with 30-, 60- and 90-day controlled gaps. NASA POWER air forcing uses coordinates rounded to 0.01 degree from the source article; there are no same-panel donor stations. The score treats the published daily mean as reference, not as error-free physical truth. Repeated gaps in a station-year and the four stations are dependent; three stations lie in the Fraser River basin (Nechako, Thompson and Fraser). These are descriptive results, without population uncertainty or a natural-outage validation.',
             r'\begin{table}[h]\centering\caption{Controlled-gap annual H30 mean absolute errors in degrees Celsius. Each row has four published-daily reference years; mask counts are not independent observations.}\begin{tabular}{lrrrr}\toprule Station & Masks & Plug-in & D2 & Stochastic \\ \midrule']
    for row in table.itertuples(index=False):
        lines.append(f"{row.station_key.split('|')[-1]} & {row.cases} & {row.plugin_mae:.3f} & {row.D2_mae:.3f} & {row.stochastic_mae:.3f} \\\\")
    lines += [r'\bottomrule\end{tabular}\end{table}',
              f"Across {reference_integrity['cases']} masked cases, independently recomputed 30-day reference maxima, observed-window bounds, missing counts, and {reference_integrity['scorecard_metrics_checked']} point and interval summary metrics agree with stored results within numerical tolerance. As a limited noninterference probe, one 90-day case per station was regenerated after adding 5 degrees C to hidden target values. All {hidden_audit['n_cases']} probes retained the same decision-time model features and numerical predictions, while the evaluation reference changed. These probes do not establish noninterference for every case, model path, or experiment.",
              r'The attribution, candidate roster, year-level qualification, individual station summaries and code are included in the local evidence package. Prior-identifier and geographic proximity checks are best effort and cannot prove independence from every previously opened record.']
    (ROOT/'paper/wrr_tr/bc_exploratory_supporting.tex').write_text('\n'.join(lines)+'\n')
    print(pd.DataFrame(by_site).to_string(index=False))
    print(json.dumps(status,indent=2))

if __name__ == '__main__':
    main()
