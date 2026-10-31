#!/usr/bin/env python3
"""Freeze a post-hoc comparison of annual and July--August 30-day windows."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
SNAPSHOT=REV/'open_observed_record_snapshot'
OUT=REV/'summer_window_comparison'

def main():
    if (OUT/'plan.json').exists():raise FileExistsError('Summer-window plan already frozen')
    manifest=json.loads((SNAPSHOT/'manifest.json').read_text())
    roster=pd.read_csv(SNAPSHOT/'source_roster.csv')
    years=pd.read_csv(REV/'rules/eligible_station_years.csv',usecols=['station_key','independence_group'])
    mapping=years[years.station_key.isin(roster.station_key)].drop_duplicates().sort_values('station_key')
    if len(roster)!=95 or len(mapping)!=95 or mapping.station_key.duplicated().any() or set(mapping.station_key)!=set(roster.station_key):
        raise ValueError('Open subset roster or connected-group mapping differs')
    OUT.mkdir(parents=True,exist_ok=True)
    mapping.to_csv(OUT/'station_groups.csv',index=False)
    inputs=[SNAPSHOT/'manifest.json', SNAPSHOT/'daily_temperature.parquet', SNAPSHOT/'station_years.parquet',
            SNAPSHOT/'eligible_station_years.csv',SNAPSHOT/'source_roster.csv',SNAPSHOT/'observed_record_certificates.csv',
            OUT/'station_groups.csv',ROOT/'scripts/706_summer_window_compare.py']
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc diagnostic after examining previously selected observation witnesses and literature; not a prospective or independent reference',
          'population':'95 of the 96 original eligible stations with a documented candidate redistribution path; project-processed float32 daily series. One LUBW station remains excluded pending permission.',
          'complete_years':'among previously eligible 1981--2025 station-years with complete daily coverage, compare maximum 30-day means within the calendar year with maximum 30-day means whose every day lies in July--August of that same year.',
          'witnesses':'for the 35 preselected incomplete-year observations, compare the certified full-year observed-window maximum against the maximum of fully observed July--August 30-day windows; missing summer window is unavailable, not zero.',
          'rule_information':'for complete-year, 95% annual, station-specific 90% warm-season and complete July--August study criteria, count excluded, retained and unknown station-years and how many excluded years still have a finite observed 30-day lower bound.',
          'scoring':'differences on the reported series, 5e-6 C numerical tolerance, additional 0.1 and 0.5 C margins; by-station means over the same complete years; 4000 connected-group bootstrap resamples of case-weighted mean difference, seed 705.',
          'literature':'Beaufort et al. (2022), https://doi.org/10.5194/hess-26-3477-2022, study an interannual thermal peak and summer climate correction; the Jul--Aug fully-contained-window calculation is an explicit diagnostic, not a reconstruction or evaluation of their full workflow. Johnson et al. (2021), https://doi.org/10.1016/j.ecolind.2020.107229, study annual sine-wave parameters, not H30.',
          'limitations':'not provider-native data or sensor validation; sites were selected for long complete records, not representative of all streams; station-years and groups are not independent climates. Seasonal window restriction is a counterfactual choice and does not by itself establish quality or compare estimation methods.',
          }
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen 95-station open-source subset and explicit summer-window comparison',flush=True)

if __name__=='__main__':main()
