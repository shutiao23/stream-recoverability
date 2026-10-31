#!/usr/bin/env python3
"""Bound annual H30 from incomplete author-level observations, without imputation."""
from __future__ import annotations
import argparse
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import json
import math
import os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/external_usace_reservoir'
DATA = ROOT / 'data/external/wrr_usace_reservoir_20261027'
PRIVATE = ROOT / 'private/wrr_usace_reservoir_reference_20261027'
YEARS = range(2021, 2026)
LOW, HIGH = -5.0, 50.0
WIDTHS = (0.01, 0.1, 0.5, 1.0)

def time_mst(raw):
    t = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    return t.astimezone(timezone(timedelta(hours=-7))).replace(tzinfo=None) if t.tzinfo else t

def day_bounds(slots):
    """Each missing or ambiguous slot can be any number within fixed bounds."""
    good = np.isfinite(slots)
    n = int(good.sum())
    s = float(slots[good].sum())
    return (s + (96-n)*LOW)/96, (s + (96-n)*HIGH)/96, n

def yearly_bounds(days, year):
    start = date(year, 1, 1)
    n = 366 if calendar.isleap(year) else 365
    lo, hi, counts = [], [], []
    for i in range(n):
        slots = days.get(start + timedelta(days=i))
        l, u, count = day_bounds(slots if slots is not None else np.full(96, np.nan))
        lo.append(l); hi.append(u); counts.append(count)
    lower = np.convolve(lo, np.ones(30)/30, mode='valid')
    upper = np.convolve(hi, np.ones(30)/30, mode='valid')
    return {'h30_lower_c': float(np.max(lower)), 'h30_upper_c': float(np.max(upper)),
            'complete_days': sum(x == 96 for x in counts), 'expected_days': n,
            'missing_or_ambiguous_slots': 96*n-sum(counts)}

def freeze():
    path = OUT / 'partial_year_bounds_plan.json'
    if path.exists():
        raise FileExistsError('Preserve existing bounds plan')
    m = json.loads((DATA / 'manifest.json').read_text())
    if len(m['records']) != 10 or len({r['resource_id'] for r in m['records']}) != 10:
        raise ValueError('The fixed ten-resource cohort changed')
    prior = json.loads((OUT / 'finite_reference_independent_audit.json').read_text())
    if prior['status'] != 'passed' or prior['complete_years_recomputed'] != 0:
        raise ValueError('Previous finite reference screen not confirmed')
    plan = {'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'posthoc after timestamp and finite-completeness results; before computing H30 bounds or model errors',
        'cohort': 'All ten previously screened source files and all calendar years 2021-2025; retain years with any number of missing days.',
        'estimand': 'Maximum arithmetic mean over all 30 consecutive daily means wholly within each calendar year. Each day is the mean of its 96 quarter-hour slots in reported fixed MST.',
        'interval': 'Each finite, unique, on-grid reported temperature in [-5,50] is fixed. Every missing, nonfinite, nonnumeric, duplicate or otherwise ambiguous quarter-hour slot is bounded by [-5,50] C. If any off-grid row is present on a day, treat that entire day as unknown. Construct each day lower/upper mean and then separately maximize its 30-day rolling mean.',
        'range_basis': 'EXO sensor specified operating range is used as an explicit assumed bound on all unknown values, not proof the physical water was in range or that readings were accurate. Violating the assumption invalidates the enclosure.',
        'width_thresholds_c': list(WIDTHS), 'threshold_interpretation': 'Descriptive resolution thresholds, not an accuracy or qualification criterion; reported for all years and no threshold chosen from outcomes.',
        'quality_and_independence': 'Published level-1 readings can be corrected; flags, sensor errors, actual time convention, physical bounds, network overlap and independent climates remain unresolved.',
        'no_scoring': 'No model prediction, model error or mask outcome is requested in this analysis. Bounded data are not strict complete nonestimated references.',
        }
    path.write_text(json.dumps(plan, indent=2)+'\n')
    print('Recorded post-hoc bounded-H30 design for 50 station-years')

def run():
    p = json.loads((OUT/'partial_year_bounds_plan.json').read_text())
    expected = pd.read_csv(OUT/'finite_reference_years.csv').set_index(['resource_id','year'])
    rows = []
    for record in json.loads((DATA/'manifest.json').read_text())['records']:
        path = (DATA/record['file']).resolve()
        if not path.is_relative_to(DATA.resolve()):
            raise ValueError('Input snapshot changed')
        days = {}; offgrid = set(); seen = {}; duplicates = set()
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                t = time_mst(row['timestamp'])
                if t.year not in YEARS:
                    continue
                day = t.date()
                if t.minute % 15 or t.second or t.microsecond:
                    offgrid.add(day); continue
                slot = t.hour*4 + t.minute//15
                key = (day,slot)
                if key in seen:
                    duplicates.add(key)
                    days[day][slot] = np.nan
                    continue
                seen[key] = True
                if day not in days:
                    days[day] = np.full(96,np.nan)
                try:
                    v = float(row['temp_degC'])
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(v):
                    continue
                if not LOW <= v <= HIGH:
                    raise ValueError('Observed finite value violates assumed range')
                days[day][slot] = v
        for day in offgrid:
            days[day] = np.full(96,np.nan)
        for year in YEARS:
            x = yearly_bounds(days, year)
            earlier = expected.loc[(record['resource_id'], year)]
            if x['complete_days'] != int(earlier['complete_finite_days']) or x['expected_days'] != int(earlier['expected_days']):
                raise ValueError('Complete finite day count differs from prior screen')
            if x['h30_lower_c'] > x['h30_upper_c'] + 1e-10:
                raise AssertionError('Invalid interval')
            rows.append({'resource_id':record['resource_id'], 'year':year, **x,
                         'h30_interval_width_c':x['h30_upper_c']-x['h30_lower_c']})
        print('Computed bounded H30 for',len(rows)//5,'of 10 resources',flush=True)
    frame = pd.DataFrame(rows)
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = PRIVATE/'partial_year_h30_bounds.csv'
    frame.to_csv(dest,index=False); dest.chmod(0o600)
    summary = {'status':'completed_bounds_only', 'resources':frame.resource_id.nunique(), 'station_years':len(frame),
        'years':list(YEARS), 'interval_width_min_c':float(frame.h30_interval_width_c.min()),
        'interval_width_median_c':float(frame.h30_interval_width_c.median()),
        'interval_width_max_c':float(frame.h30_interval_width_c.max()),
        'year_counts_width_at_most_c':{str(t):int((frame.h30_interval_width_c <= t+1e-12).sum()) for t in WIDTHS},
        'site_counts_four_years_width_at_most_c':{str(t):int((frame.assign(ok=frame.h30_interval_width_c.le(t+1e-12)).groupby('resource_id').ok.sum()>=4).sum()) for t in WIDTHS},
        'model_errors_calculated':False,
        'limitations':p['range_basis']+' '+p['quality_and_independence']}
    (OUT/'partial_year_bounds_status.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args()
    freeze() if a.action=='freeze' else run()
