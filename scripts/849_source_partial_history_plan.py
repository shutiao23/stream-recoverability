#!/usr/bin/env python3
"""Freeze a matched source-history degradation experiment before its scores."""
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.v19_revision.data import station_air_series

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial';OPEN=REV/'open_observed_record_snapshot'
SOURCE=ROOT/'results/wrr_review_completion_20261024';MODELS=ROOT/'private/wrr_open_source_sensitivity_20261026'

def main():
    worker=T.load_script('source_history_plan_worker',ROOT/'scripts/850_source_partial_history_factorial.py')
    OUT.mkdir(parents=True,exist_ok=True);dest=OUT/'plan.json'
    if dest.exists():raise FileExistsError('Preserve factorial plan')
    prev=json.loads((REV/'beaufort_proxy/plan.json').read_text())
    roster_path=REV/'beaufort_proxy/roster.csv'
    r=pd.read_csv(roster_path,dtype={'station_id':str});r=r[r.provider.isin(['foen','gkd_bayern'])].copy()
    if len(r)!=15 or r.independence_group.nunique()!=6 or r.station_key.duplicated().any():raise ValueError('Prior roster changed')
    available=pd.read_parquet(OPEN/'station_years.parquet',columns=['station_key','year','complete_year'])
    q=available[available.station_key.isin(r.station_key)&available.year.between(2009,2017)]
    if len(q)!=15*9 or not q.complete_year.all() or q.duplicated(['station_key','year']).any():raise ValueError('Expected complete water years absent')
    lat=T.station_latitudes();r['latitude']=r.station_key.map(lat)
    if r.latitude.isna().any():raise ValueError('Station latitude missing')
    dates=pd.date_range('2009-01-01','2017-12-31');frames=[];availability=[]
    for i,row in enumerate(r.itertuples(index=False),1):
        s=station_air_series(T.AIR,row.network_id,row.station_id,dates)
        if s is None:s=pd.Series(np.nan,index=dates)
        frames.append(pd.DataFrame({'date':dates,'station_id':row.station_id,'network_id':row.network_id,'air_temperature_c':s.to_numpy()}))
        availability.append({'station_key':row.station_key,'days':len(dates),'finite_air_days':int(np.isfinite(s).sum())})
        print('Captured existing processed air for',i,'of',len(r),'stations',flush=True)
    r.to_csv(OUT/'roster.csv',index=False);pd.concat(frames,ignore_index=True).to_parquet(OUT/'air_snapshot.parquet',index=False)
    pd.DataFrame(availability).to_csv(OUT/'air_availability.csv',index=False)
    files=[roster_path,OPEN/'daily_temperature.parquet',OPEN/'station_years.parquet',T.AIR,
      SOURCE/'independent_study/source_case_settings.json',SOURCE/'independent_study/source_missingness_generator.json',
      ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/wrr_tr_features.py',
      ROOT/'scripts/835_usace_partial_history_engine.py',ROOT/'scripts/850_source_partial_history_factorial.py',Path(__file__),
      OUT/'roster.csv',OUT/'air_snapshot.parquet',OUT/'air_availability.csv']
    for region in ['foen','gkd_bayern']:
        files += [MODELS/'refits/leave_one_year_out/seed_00'/f'{region}.joblib',MODELS/'calibrations/offline'/f'{region}.json']
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after the USACE partial-history outcomes and earlier source comparisons have been inspected; before this factorial target predictions or scores',
      'cohort':'All 15 FOEN and Bavarian stations in the previously defined 22-station processed-data cohort, with nine complete 2009-2017 water years; six recorded connected groups. Selection is inherited from previous availability and source-result inspection, not random or independently sampled.',
      'target':'2017 calendar-year H30 from processed complete daily series, treated as the reference reported-series statistic. Target daily observations are hidden by identical synthetic masks and excluded from local history fitting.',
      'history':'Eight complete historical years 2009-2016. Full history retains all days. Partial history hides July 1-30 of every history year, then linearly interpolates those 240 missing days separately within each year, never using the hidden values. This fixed warm-season loss is a synthetic mechanism, not a sampled operational outage.',
      'target_masks':'Fixed starts at zero-based day indices 75, 165 and 255, each combined with lengths 30, 60 and 90 days; nine masks per station, identical across both history modes. Overlap with a training-derived climatological peak may differ between modes.',
      'estimators':'Fixed candidate-provider strict-held-region source model and source calibration for each provider; no same-target-region source role and no target donor. Compare original plug-in and calibrated stochastic across history modes, and D2 in four combinations of history mode and n_complete_years feature (0 or 8).',
      'counterfactual':'For the full-history mode count 8 and partial mode count 0 are the truthful inputs. Setting 0 for full or 8 for partial misstates the actual data and is used solely to diagnose feature sensitivity, never recommended for deployment.',
      'score':'Per-case and paired absolute error, 90% interval coverage, width and interval score on common available samples. Report station, region and six-group dependence, station-equal and group-equal summaries, and all results including degradations. A 2x2 comparison describes combined interventions, not a universal causal decomposition.',
      'limitations':'This is an in-source, posthoc mechanism experiment, one target year, six connected groups and two regions; not independent-climate validation. Target calendar and source models reuse earlier analyses, source water quality and NASA POWER vintage/day alignment remain unresolved, and source-model rights remain restricted.',
      'stations':len(r),'groups':int(r.independence_group.nunique()),'target_cases_expected':len(r)*9,
      'finite_air_days':int(sum(x['finite_air_days'] for x in availability)),'air_days':len(dates)*len(r),
      }
    dest.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({'stations':len(r),'groups':plan['groups'],'target_cases_expected':plan['target_cases_expected'],'finite_air_days':plan['finite_air_days'],'air_days':plan['air_days']},indent=2))

if __name__=='__main__':main()
