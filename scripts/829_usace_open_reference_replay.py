#!/usr/bin/env python3
"""Recompute reservoir reference-year eligibility from attributed extracts."""
import calendar
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import gzip
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/external/wrr_usace_reservoir_20261027'
REV = ROOT / 'results/wrr_review_response_20261027'

def main():
    manifest = json.loads((DATA / 'manifest.json').read_text())
    expected_path = REV / 'external_usace_reservoir/finite_reference_years.csv'
    with expected_path.open(newline='') as f:
        expected = {(r['resource_id'], int(r['year'])): (int(r['reported_days']), int(r['complete_finite_days']), int(r['expected_days']), r['finite_reference_year'] == 'True') for r in csv.DictReader(f)}
    result = {}
    complete_days = 0
    for item in manifest['records']:
        path = (DATA / item['file']).resolve()
        if not path.is_relative_to(DATA.resolve()):
            raise ValueError('Missing or changed input extract')
        days = defaultdict(lambda: [0, set(), 0, 0])
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != ['timestamp', 'temp_degC']:
                raise ValueError('Unexpected extract columns')
            for row in reader:
                t = datetime.fromisoformat(row['timestamp'].strip().replace('Z', '+00:00'))
                if t.tzinfo:
                    t = t.astimezone(timezone(timedelta(hours=-7))).replace(tzinfo=None)
                d = days[t.date()]
                d[0] += 1
                d[1].add((t.hour, t.minute, t.second, t.microsecond))
                d[2] += int(t.minute % 15 == 0 and t.second == 0 and t.microsecond == 0)
                try:
                    v = float(row['temp_degC'])
                    d[3] += int(math.isfinite(v) and -5 <= v <= 50)
                except (TypeError, ValueError):
                    pass
        years = defaultdict(lambda: [0, 0])
        for date, (count, slots, grid, finite) in days.items():
            valid = count == len(slots) == grid == finite == 96
            years[date.year][0] += 1
            years[date.year][1] += valid
            complete_days += valid
        for year, (reported, valid) in years.items():
            n = 366 if calendar.isleap(year) else 365
            result[(item['resource_id'], year)] = (reported, valid, n, reported == valid == n)
        print('Replayed', len({key[0] for key in result}), 'of', len(manifest['records']), flush=True)
    if result != expected:
        raise AssertionError('Extracted station-year eligibility differs from saved results')
    output = {'status': 'passed', 'resources': len(manifest['records']), 'station_years': len(result),
        'complete_finite_days': complete_days, 'complete_finite_years': sum(v[3] for v in result.values()),
        'scope': 'Recomputed all station-year qualification from public two-column snapshots. No H30, model scoring, cross-site sensor independence or measurement accuracy checked.',
        'limits': 'Source level-1 values may include corrections; no quality-code or network-independence guarantee.'}
    out = REV / 'audit/usace_open_reference_replay.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
