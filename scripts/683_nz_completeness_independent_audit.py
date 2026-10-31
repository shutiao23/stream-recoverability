#!/usr/bin/env python3
"""Independently recompute the frozen NZ quality-blind annual day counts.

Uses the same native XML reader but independently constructs monthly cadence
and day support from NumPy arrays. This does not validate original sensors,
provider quality flags or the shared XML reader.
"""
from __future__ import annotations
import gzip
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('screen', ROOT / 'scripts/681_nz_native_completeness_bound.py')
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)

def independently_count(raw, beginning, end):
    raw = raw.sort_index()
    duplicate = raw.index.duplicated(keep=False)
    if duplicate.any():
        def resolve(group):
            return group.iloc[0] if len(group.unique()) == 1 else np.nan
        raw = pd.concat([raw[~duplicate], raw[duplicate].groupby(level=0).agg(resolve)]).sort_index()
    begin = beginning.normalize().tz_localize(screen.NZST)
    finish = end.ceil('D').tz_localize(screen.NZST)
    raw = raw[(raw.index >= begin) & (raw.index < finish)]
    index = raw.index
    finite = np.isfinite(raw.to_numpy())
    ns = index.asi8
    month = index.strftime('%Y-%m').to_numpy()
    day = index.normalize().asi8
    # The provider's monthly mode uses only positive intervals up to an hour,
    # including intervals across days within the same month.
    cadence = {}
    for name in np.unique(month):
        stamps = ns[month == name]
        delta = np.diff(stamps) / 1e9
        delta = delta[(delta > 0) & (delta <= 3600)]
        if len(delta) < 3:
            continue
        values, counts = np.unique(delta, return_counts=True)
        step = values[np.argmax(counts)]
        if np.isclose(86400 / step, round(86400 / step)):
            cadence[name] = step
    days, first, counts = np.unique(day, return_index=True, return_counts=True)
    good = set()
    for start_day, start, n in zip(days, first, counts):
        step = cadence.get(month[start])
        if step is None or n != round(86400 / step) or not finite[start:start+n].all():
            continue
        edges = np.r_[start_day, ns[start:start+n], start_day + 86400 * 10**9]
        if np.all(np.diff(edges) / 1e9 <= step + 1e-6):
            good.add(pd.Timestamp(start_day, tz='UTC').tz_convert(screen.NZST).tz_localize(None))
    rows = []
    for year in range(begin.year, (finish - pd.Timedelta(days=1)).year):
        expected = pd.date_range(f'{year}-07-01', f'{year+1}-06-30')
        count = sum(d in good for d in expected)
        rows.append((year, len(expected), count))
    return rows

def main():
    plan = json.loads((screen.OUTPUT / 'plan.json').read_text())
    _, roster, cutoff = screen.inputs()
    saved = pd.read_csv(screen.OUTPUT / 'year_counts.csv')
    compared = 0
    for _, row in roster.sort_values('station_key').iterrows():
        chunks = [screen.native_series(gzip.decompress(p.read_bytes()), site=row.site, series_type='StdSeries') for p in screen.source_files(row, cutoff)]
        actual = independently_count(pd.concat(chunks), pd.Timestamp(row['from']), min(pd.Timestamp(row['to']), cutoff))
        wanted = saved[saved.station_key.eq(row.station_key)]
        expected = list(wanted[['hot_year', 'expected_days', 'possible_complete_days']].itertuples(index=False, name=None))
        if actual != expected:
            raise AssertionError(f'Independent count mismatch for {row.station_key}')
        compared += len(actual)
        print(f'{row.site}: {len(actual)} years match', flush=True)
    result = {'sites_compared': len(roster), 'station_years_compared': compared, 'all_counts_match': True, 'limits': 'Shared XML parser and cached source; independent day and year calculation, not independent data or quality confirmation.'}
    (screen.OUTPUT / 'independent_count_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
