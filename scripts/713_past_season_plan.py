#!/usr/bin/env python3
"""Freeze a post-hoc past-only warm-season screening sensitivity."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
SNAP=REV/'open_observed_record_snapshot'
OUT=REV/'past_season_screening'

def main():
    path=OUT/'plan.json'
    if path.exists():raise FileExistsError('Past-season sensitivity already frozen')
    summary=json.loads((REV/'summer_window_comparison/summary.json').read_text())
    audit=json.loads((REV/'summer_window_comparison/independent_audit.json').read_text())
    if summary['stations']!=95 or audit['status']!='passed':raise ValueError('Existing observation subset is incomplete')
    years=pd.read_csv(SNAP/'eligible_station_years.csv')
    if len(years)!=2656 or years.duplicated(['station_key','year']).any():raise ValueError('Unexpected station-year cohort')
    files=[ROOT/'scripts/714_past_season_screening.py',ROOT/'scripts/wrr_tr_common.py',ROOT/'scripts/wrr_r3_common.py',
           ROOT/'src/stream_recoverability/experiments/v17_fitness/estimators.py',
           ROOT/'configs/wrr_target_recovery_20261022.json', SNAP/'daily_temperature.parquet',
           SNAP/'eligible_station_years.csv',SNAP/'observed_record_certificates.csv',
           REV/'summer_window_comparison/station_groups.csv']
    OUT.mkdir(parents=True,exist_ok=True)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc observational sensitivity after the 35 witnesses and leave-year-out rules were inspected; not prospective registration',
          'cohort':'same 95-station project-processed current-vintage subset; 2,656 previously eligible 1981--2025 station-years and 35 retrospectively selected witnesses',
          'season':'same 15-day-smoothed day-of-year climatology and five consecutive warm months as the existing study comparator, but using only observed water days with calendar year strictly earlier than the target year',
          'support_variants':'past version uses any nonempty earlier observations; past-four-complete version requires at least four fully observed calendar years strictly before the target year. Complete target years are accepted without climatology because they necessarily meet any warm-season 90% threshold. Incomplete years with unavailable support are unknown, not rejected.',
          'reference':'within 1981--2025 eligible station-years, compare each rejected year\'s observed 30-day maximum with maxima of the same rule\'s earlier accepted years only; if no earlier accepted observable window exists, reference is unknown. Accepted incomplete years can hide higher annual H30.',
          'comparators':'complete-year, 95% annual coverage, original leave-target-year-out 90% warm season, past-only 90% warm season, and past-only with four earlier complete years. The leave-year-out comparator can use future observations.',
          'limits':'retrospectively selected stations and witnesses and the currently available revised data vintage, not the historical data/metadata available at the time; four-year rule is a study sensitivity rather than a published standard. No physical measurement-error validation, independent climate or prospective performance guarantee.',
          }
    path.write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen past-only season and separate four-complete-year support sensitivity',flush=True)

if __name__=='__main__':main()
