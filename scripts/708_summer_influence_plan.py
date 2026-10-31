#!/usr/bin/env python3
"""Freeze a post-hoc influence check after observing largest seasonal gaps."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'summer_window_comparison'

def main():
    amendment=OUT/'influence_plan.json'
    if amendment.exists():raise FileExistsError('Influence sensitivity is already frozen')
    original=json.loads((OUT/'summary.json').read_text());audit=json.loads((OUT/'independent_audit.json').read_text())
    if audit['status']!='passed' or audit['complete_station_years_checked']!=original['complete_station_years']:
        raise ValueError('Prior comparison has not passed independent arithmetic audit')
    group=pd.read_csv(OUT/'station_groups.csv')
    source=pd.read_csv(REV/'rules/eligible_station_years.csv',usecols=['station_key','regulation_status']).drop_duplicates()
    mapping=group[['station_key']].merge(source,on='station_key',validate='one_to_one')
    if mapping.regulation_status.isna().any():raise ValueError('Regulation label absent from original metadata')
    chosen=['usgs|14151000','usgs|14162200']
    if len(mapping)!=95 or not set(chosen).issubset(set(mapping.station_key)) or not mapping[mapping.station_key.isin(chosen)].regulation_status.eq('regulated').all():
        raise ValueError('Documented station cohort or regulation labels differ')
    mapping.to_csv(OUT/'station_regulation_labels.csv',index=False)
    inputs=[OUT/'plan.json',OUT/'summary.json',OUT/'complete_year_windows.csv',OUT/'station_groups.csv',
            OUT/'station_regulation_labels.csv',OUT/'independent_audit.json',
            REV/'open_observed_record_snapshot/daily_temperature.parquet',ROOT/'scripts/709_summer_influence.py']
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc diagnostic specified only after seeing the largest individual annual gaps; not a prespecified or independent-climate comparison',
          'question':'Describe sensitivity of annual full-year vs July--August window differences to existing project regulation labels and to the two stations whose records produced the largest gaps.',
          'labels':'Use stored project station-level labels regulated, unmatched_gages and unknown. Unmatched gages do not establish that a station is unregulated, and labels are not randomized.',
          'influence_excluded_stations':chosen,
          'localization':'For the two selected sites, report the first maximizing complete annual 30-day window for each year using the same daily series; ties are not evidence of a unique physical peak.',
          'reference':'USGS documented thermal effects at both stations for specific 2001--2002 measurements: https://pubs.usgs.gov/sir/2010/5153/table4.html ; that report does not explain every year of this later sample.',
          'summaries':'Report full and two-station-excluded complete-year counts, station/group counts, mean/median/max difference and fraction >0.1 and >0.5 C, plus descriptive existing-label strata. Do not infer a causal reservoir effect.',
          }
    amendment.write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen regulation-stratified and two-station influence check',flush=True)

if __name__=='__main__':main()
