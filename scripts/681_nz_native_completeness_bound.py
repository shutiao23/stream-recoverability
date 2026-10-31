#!/usr/bin/env python3
"""Post-hoc, quality-blind upper bound on the existing NZ cohort's coverage.

This is a feasibility screen, not reference qualification or a model evaluation.
It reads existing cached measurements and writes only counts, never temperatures.
"""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.tr_revision.native_temperature import (
    NZST,
    native_series,
    strict_daily_mean,
)

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "results/wrr_review_completion_20261024/independent_study"
OUTPUT = ROOT / "results/wrr_review_response_20261027/external_nz_quality_bounds"

def source_files(row, cutoff):
    beginning = pd.Timestamp(row['from'])
    end = min(pd.Timestamp(row['to']), cutoff)
    chunks = []
    for start in pd.date_range(f'{beginning.year}-01-01', end, freq='YS'):
        stop = min(start + pd.offsets.YearBegin(1), end)
        if stop > start:
            chunks.append(STUDY / 'acquired' / f"{row['station_id']}__StdSeries__{start.date()}__{stop.date()}.xml.gz")
    return chunks

def inputs():
    original = json.loads((STUDY / 'acquisition_plan.json').read_text())
    roster = pd.read_csv(STUDY / original['metadata_roster_file'], dtype=str)
    return original, roster, pd.Timestamp(original['observation_end_exclusive'])

def freeze():
    plan_path = OUTPUT / 'plan.json'
    if plan_path.exists():
        raise FileExistsError('Screen already frozen; do not overwrite its plan')
    original, roster, cutoff = inputs()
    files = [STUDY / 'acquisition_plan.json', STUDY / original['metadata_roster_file'], STUDY / 'acquisition_receipt.json', Path(__file__), ROOT / 'src/stream_recoverability/experiments/tr_revision/native_temperature.py']
    for _, row in roster.iterrows():
        files.extend(source_files(row, cutoff))
    missing = [str(p.relative_to(ROOT)) for p in files if not p.is_file()]
    if missing:
        raise FileNotFoundError(f'Missing cached inputs: {missing}')
    plan = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'post-hoc feasibility screen; original observations and prior quality failure were already inspected',
        'cohort_size': len(roster),
        'method': 'Original fixed NZST monthly-cadence complete-day algorithm, finite values only, all quality flags ignored; count complete July-June years, requiring four.',
        'limits': 'Optimistic for this cached cohort and finite-value rule only. Quality and physical accuracy remain unknown. No model scores or temperature values saved. This is not prospective registration.',
        
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
    print(f"Frozen {len(roster)} sites and {len(files)} cached inputs")

def hot_year_counts(daily):
    indexed = daily.set_index('date')['complete_native_day']
    if indexed.empty:
        return []
    records = []
    for year in range(indexed.index.min().year, indexed.index.max().year):
        dates = pd.date_range(f'{year}-07-01', f'{year+1}-06-30')
        n = int(indexed.reindex(dates, fill_value=False).sum())
        records.append({'hot_year': year, 'expected_days': len(dates), 'possible_complete_days': n, 'possibly_complete_year': n == len(dates)})
    return records

def run():
    plan = json.loads((OUTPUT / 'plan.json').read_text())
    _, roster, cutoff = inputs()
    years, sites = [], []
    for _, row in roster.sort_values('station_key').iterrows():
        chunks = [native_series(gzip.decompress(p.read_bytes()), site=row.site, series_type='StdSeries') for p in source_files(row, cutoff)]
        if not chunks:
            raise ValueError(f'No cached native chunks for {row.station_key}')
        raw = pd.concat(chunks).sort_index()
        raw = raw.groupby(level=0).agg(lambda s: s.iloc[0] if len(s.unique()) == 1 else float('nan'))
        raw = raw.where(np.isfinite(raw))
        quality = pd.Series([600.], index=pd.DatetimeIndex([pd.Timestamp('1900-01-01', tz=NZST)]))
        beginning = pd.Timestamp(row['from'])
        end = min(pd.Timestamp(row['to']), cutoff)
        daily = strict_daily_mean(raw, quality, accepted_codes=(600,), start=beginning.normalize().isoformat(), end_exclusive=end.ceil('D').isoformat())
        records = hot_year_counts(daily)
        years.extend([{'station_key': row.station_key, **item} for item in records])
        count = sum(item['possibly_complete_year'] for item in records)
        sites.append({'station_key': row.station_key, 'site': row.site, 'possible_complete_hot_years': count, 'possible_four_year_support': count >= 4})
        print(f'{row.site}: {count} possible complete years', flush=True)
    pd.DataFrame(years).to_csv(OUTPUT / 'year_counts.csv', index=False)
    pd.DataFrame(sites).to_csv(OUTPUT / 'site_counts.csv', index=False)
    summary = {'n_sites': len(sites), 'n_sites_possibly_four_years': sum(x['possible_four_year_support'] for x in sites), 'n_possible_complete_hot_years': sum(x['possible_complete_hot_years'] for x in sites), 'strictly_qualified_sites': 0, 'status': 'time-and-finite-value feasibility only; unresolved agency quality codes'}
    (OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('freeze', 'run'))
    args = p.parse_args()
    freeze() if args.action == 'freeze' else run()
