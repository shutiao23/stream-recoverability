#!/usr/bin/env python3
"""Count-only preflight of the frozen, exploratory late-start USGS roster."""
import calendar
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/external_usgs_late_start'
URL = 'https://api.waterdata.usgs.gov/statistics/v0/observationIntervals'
COLUMNS = ['station_id', 'year', 'approved_daily_count', 'expected_days', 'interval_full_year', 'count_complete']

def extract_counts(doc, roster):
    index = roster.set_index('station_id', verify_integrity=True)
    if not isinstance(doc.get('features'), list):
        raise ValueError('Missing features list')
    if any(x.get('rel') == 'next' for x in doc.get('links', [])):
        raise ValueError('Paginated response')
    rows, seen = [], set()
    for feature in doc['features']:
        prop = feature['properties']
        site = prop['monitoring_location_id'].removeprefix('USGS-')
        if site not in index.index:
            raise ValueError('Unexpected site')
        for series in prop.get('data', []):
            if str(series.get('parent_time_series_id')) != str(index.loc[site, 'series_id']) or str(series.get('parent_statistic_id')) != '00003':
                continue
            for val in series.get('values', []):
                if val.get('interval_type') != 'calendar_year' or val.get('approval_status') != 'approved':
                    continue
                start, end = pd.Timestamp(val['start_date']), pd.Timestamp(val['end_date'])
                y = start.year
                if y not in range(2017, 2026):
                    continue
                if end.year != y or end < start:
                    raise ValueError('Invalid annual interval')
                key = (site, y)
                if key in seen:
                    raise ValueError(f'Duplicate annual statistic: {key}')
                seen.add(key)
                expected = 366 if calendar.isleap(y) else 365
                count = int(val['sample_count'])
                if count < 0 or count > expected:
                    raise ValueError('Invalid daily sample count')
                full = start == pd.Timestamp(y, 1, 1) and end == pd.Timestamp(y, 12, 31)
                rows.append(dict(station_id=site, year=y, approved_daily_count=count, expected_days=expected,
                                 interval_full_year=full, count_complete=full and count == expected))
    return pd.DataFrame(rows, columns=COLUMNS)

def main():
    plan = json.loads((OUT / 'plan.json').read_text())
    path = OUT / 'candidate_roster.csv'
    if (OUT / 'preflight_status.json').exists():
        raise RuntimeError('Preflight already exists; preserve current results')
    roster = pd.read_csv(path, dtype=str)
    all_counts = []
    features = 0
    for start in range(0, len(roster), 4):
        batch = roster.iloc[start:start + 4]
        params = [('monitoring_location_id', 'USGS-' + x) for x in batch.station_id] + [
            ('parameter_code', '00010'), ('start_date', '2017-01-01'), ('end_date', '2025-12-31'),
            ('interval_type', 'CY'), ('computation_type', 'arithmetic_mean'), ('page_size', '100')]
        response = requests.get(URL, params=params, timeout=90, headers={'User-Agent': 'stream-temperature reference research'})
        response.raise_for_status()
        doc = response.json()
        all_counts.append(extract_counts(doc, batch))
        features += len(doc['features'])
    counts = pd.concat(all_counts, ignore_index=True)
    # Deliberately retain only dates and sample counts, never annual temperature means.
    candidates = []
    for row in roster.itertuples():
        c = counts.loc[counts.station_id.eq(row.station_id)]
        n = int(c.count_complete.sum())
        candidates.append({'station_id': row.station_id, 'count_complete_years': n,
                           'complete_years': ';'.join(str(y) for y in c.loc[c.count_complete, 'year']),
                           'reported_approved_years': len(c), 'unreported_years_2017_2025': 9-len(c),
                           'count_preflight_pass': n >= 4})
    summary = roster.merge(pd.DataFrame(candidates), on='station_id', validate='one_to_one')
    counts.to_csv(OUT / 'approved_counts.csv', index=False)
    summary.to_csv(OUT / 'candidate_counts.csv', index=False)
    status = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'candidates': len(roster), 'features_returned': features, 'candidate_sites_with_any_approved_year': int((summary.reported_approved_years > 0).sum()),
              'count_preflight_pass': int(summary.count_preflight_pass.sum()),
              'interpretation': 'A pass requires at least four full calendar years of approved sample counts, but does not establish point-level quality, independence, river suitability or rights. Unreturned annual statistics are unknown, not zeros; candidates with fewer than four confirmed years are not definitive failures.',
              'annual_temperatures_saved_or_used': False, 'reconstruction_errors_opened': False}
    (OUT / 'preflight_status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(summary[['station_id', 'station_name', 'network_status', 'count_complete_years', 'complete_years', 'reported_approved_years', 'count_preflight_pass']].to_string(index=False))
    print(json.dumps(status, indent=2))

if __name__ == '__main__':
    main()
