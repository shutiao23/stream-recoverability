#!/usr/bin/env python3
"""Validate and report a post-hoc USGS count-only availability screen."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/external_usgs_late_start'

def main():
    plan = json.loads((OUT / 'plan.json').read_text())
    status = json.loads((OUT / 'preflight_status.json').read_text())
    roster_path = OUT / 'candidate_roster.csv'
    roster = pd.read_csv(roster_path, dtype=str)
    summary = pd.read_csv(OUT / 'candidate_counts.csv', dtype={'station_id': str, 'series_id': str})
    counts = pd.read_csv(OUT / 'approved_counts.csv', dtype={'station_id': str})
    expected = {'station_id', 'year', 'approved_daily_count', 'expected_days', 'interval_full_year', 'count_complete'}
    if set(counts.columns) != expected or counts.duplicated(['station_id', 'year']).any():
        raise ValueError('Unexpected count fields or duplicate station-years')
    if roster.station_id.tolist() != summary.station_id.tolist() or len(roster) != plan['frozen_candidates'] or len(roster) != status['candidates']:
        raise ValueError('Roster mismatch')
    if not set(counts.station_id) <= set(roster.station_id):
        raise ValueError('Unexpected station in counts')
    observed = counts.groupby('station_id').count_complete.sum().to_dict()
    if any(int(r.count_complete_years) != int(observed.get(r.station_id, 0)) for r in summary.itertuples()):
        raise ValueError('Year counts differ from receipts')
    passes = int(summary.count_preflight_pass.sum())
    if passes != status['count_preflight_pass']:
        raise ValueError('Pass count differs from receipt')
    lines = [r'\section{Late-start USGS count-only screen}',
        ('After earlier candidate screens, we fixed an exploratory metadata-only roster of ' + str(len(roster)) +
         ' sites with series beginning in 2017--2021 and ending during or after 2025; ' + str(plan['known_prior_contacts_excluded']) +
         ' of the 24 initial candidates had known previous contact and were excluded. The 2017--2025 approved annual sample-count screen confirmed at least four complete calendar years for '
         + str(passes) + ' sites. This count does not prove that other sites lack such years: unreturned annual statistics are unknown. '
         'The roster was not prospective and was availability-selected after earlier screens. Counts may include estimated values and do not establish complete subdaily coverage, river suitability, network independence, measurement quality, or permission to reuse data. '
         'No daily temperature values or reconstruction errors were used.'),
        r'\begin{table}[p]\centering\small',
        r'\caption{Late-start USGS count-only candidates. A full year requires an approved annual interval from January 1 to December 31 and 365 or 366 approved daily observations. Missing annual statistics are not interpreted as zero. Network status and all other reference criteria remain unresolved for some or all sites.}\label{tab:usgs-late-start}',
        r'\begin{tabular}{lrrl}\toprule',
        r'Station & Confirmed full years & Returned year statistics & Full years\\\midrule']
    for r in summary.sort_values('station_id').itertuples():
        years = '--' if pd.isna(r.complete_years) else str(r.complete_years).replace(';', ', ')
        lines.append(f'{r.station_id} & {r.count_complete_years} & {r.reported_approved_years} & {years}' + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}']
    (ROOT / 'paper/wrr_tr/usgs_late_start_supporting.tex').write_text('\n'.join(lines) + '\n')
    report = {'status': 'passed', 'metadata_candidates_before_prior_exclusions': plan['initial_candidates'],
              'prior_contact_excluded': plan['known_prior_contacts_excluded'], 'candidate_sites': len(roster),
              'count_confirmed_four_years': passes, 'sites_with_no_approved_annual_statistic': int((summary.reported_approved_years == 0).sum()),
              'network_status_counts': roster.network_status.value_counts().to_dict(),
              'temperature_values_saved': False, 'new_reconstruction_errors_computed': False,
              'limitation': status['interpretation']}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
