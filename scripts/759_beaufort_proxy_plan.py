#!/usr/bin/env python3
"""Record a post-hoc, published-method-inspired summer-peak comparison.

This is not a reproduction of the original study or an independent climate
test. It fixes decisions after previous water-temperature results were seen.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'beaufort_proxy';PRIVATE=ROOT/'private/wrr_beaufort_proxy_20261027'
SNAP=REV/'open_observed_record_snapshot';SUMMER=REV/'summer_window_comparison'
AIR=ROOT/'data/interim/tr_air_forcing.parquet'

def main():
    destination=OUT/'plan.json'
    if destination.exists():raise FileExistsError('Preserve existing published-method proxy plan')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Case-level output is not Git-ignored')
    windows=pd.read_csv(SUMMER/'complete_year_windows.csv',usecols=['station_key','year'])
    years=windows[windows.year.between(2009,2017)];counts=years.groupby('station_key').year.nunique()
    sites=set(counts.index[counts.eq(9)])
    roster=pd.read_csv(SNAP/'source_roster.csv',usecols=['station_key','network_id','provider'])
    groups=pd.read_csv(SUMMER/'station_groups.csv');reg=pd.read_csv(SUMMER/'station_regulation_labels.csv')
    roster=roster[roster.station_key.isin(sites)].merge(groups,on='station_key',validate='one_to_one').merge(reg,on='station_key',validate='one_to_one')
    roster['station_id']=roster.station_key.str.split('|',n=1).str[-1]
    roster=roster.sort_values('station_key').reset_index(drop=True)
    if len(roster)!=22 or roster.station_key.duplicated().any() or roster.independence_group.nunique()!=10:
        raise ValueError('Unexpected nine-year source cohort')
    sources=[SNAP/'manifest.json',SNAP/'daily_temperature.parquet',SNAP/'source_roster.csv',
             SUMMER/'complete_year_windows.csv',SUMMER/'station_groups.csv',SUMMER/'station_regulation_labels.csv',
             AIR,ROOT/'scripts/218_v18_air_forcing.py',ROOT/'scripts/429_tr_air_extension.py',
             ROOT/'scripts/759_beaufort_proxy_plan.py',ROOT/'scripts/760_beaufort_air_snapshot.py',
             ROOT/'scripts/761_beaufort_proxy_experiment.py',ROOT/'scripts/762_beaufort_proxy_independent_audit.py']
    if any(not p.is_file() for p in sources):raise FileNotFoundError('Required fixed source missing')
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    roster.to_csv(OUT/'roster.csv',index=False)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc after original results, literature and source-availability screen; not preregistered',
          'published_method':'Beaufort et al. (2022), https://doi.org/10.5194/hess-26-3477-2022: interannual mean of annual 30-day thermal peaks, summer water-air regressions with 2–10-day right-aligned air means, and a climate-correction gap experiment.',
          'adaptation_not_replication':'Published authors used French stations, SAFRAN forcing and their own QC and permutation details. We use previously assembled reported daily water data, NASA POWER-based local-solar daily air and an explicit train-only implementation; its values, source population, timestamp conventions, processing and permutation details are not the authors\' original ones.',
          'cohort':'22 of the earlier 95 candidate-reuse-path stations with all nine calendar years 2009–2017 complete, 10 project connected groups; one recorded regulated and 21 unmatched-gage labels, which do not establish natural conditions.',
          'target':'Primary: nine-year mean of per-year maxima of fully contained July–August 30-day water means. Additional distinct target: nine-year mean of complete calendar-year H30; neither is a trend or annual full-year H30.',
          'masks':'Exhaustively withhold each possible combination of 1 through 8 full years; no water data from a withheld year may fit or select the model. Withholding all nine years is unsupported, not a numerical prediction.',
          'models':'For each mask and each lag 2 through 10, regress retained summer daily water on the same-day right-aligned lag-length air average using intercept and slope; select largest in-sample R-squared with ties favoring the shortest lag. If retained data or predictor variance cannot support fitting, report unavailable.',
          'comparison':'Compare the retained-years-only mean of observed summer 30-day maxima with the mean after predicting all withheld summer days and recomputing their maxima; score both against each of the two fixed targets on the same cases.',
          'statistics':'Mean absolute error, signed bias, RMSE, paired absolute-error difference and fraction lower; per-station balanced aggregation and 4,000 connected-group resamples. Exclusions, provider and known regulation labels reported; masks and years are not independent climates.',
          'air_provenance':'Previously assembled float32 daily T2M table documented by project scripts as NASA POWER. Raw historical API responses and service version for these 22 original sites were not retained; gridded local-solar air days may not match reported water days.',
          'restrictions':'Air snapshot is derived from the prior NASA POWER-based table with attribution; raw water and case-level result permissions are not strengthened by this comparison.',
          'limitations':'Analyses and station availability seen before design, not independent validation or a causal comparison. Some sites have human influences and others unknown. Year-missing patterns are exhaustive synthetic masks, not observed outages. In-sample lag selection, daily air errors and timing, water QC, and natural climate representativeness remain unresolved. No guarantee for annual H30, trend, tail coverage or source selection.',
          }
    destination.write_text(json.dumps(plan,indent=2)+'\n')
    print('Recorded 22-station post-hoc summer-peak proxy plan; no new model scores computed.')

if __name__=='__main__':main()
