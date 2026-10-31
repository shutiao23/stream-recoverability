#!/usr/bin/env python3
"""Score fixed source models on the one-station Truckee exploratory cohort."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import position_index

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'
SOURCE=ROOT/'results/wrr_review_completion_20261024';CAL=ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json'

def verify_plan():
    p=json.loads((OUT/'exploratory_score_plan.json').read_text());roster=PRIVATE/'exploratory_roster.csv'
    return p

def freeze():
    p=verify_plan();dest=OUT/'exploratory_run_plan.json'
    if dest.exists() or (OUT/'exploratory_score_status.json').exists():raise FileExistsError('Preserve existing run or scores')
    forcing=json.loads((OUT/'exploratory_forcing_status.json').read_text());air=PRIVATE/'exploratory_air_forcing.parquet'
    if forcing['status']!='forcing_complete':raise ValueError('Weather forcing unavailable')
    roster=pd.read_csv(PRIVATE/'exploratory_roster.csv');site=roster.station_code.iloc[0];daily=pd.read_parquet(PRIVATE/'finite_reported_daily.parquet')
    daily=daily[daily.station_code.eq(site)&pd.to_datetime(daily.day).dt.year.isin(roster.year)].copy();daily['date']=pd.to_datetime(daily.day)
    if daily.date.duplicated().any() or len(daily)!=1461 or not np.isfinite(daily.mean_c).all():raise ValueError('Reference days differ from fixed cohort')
    frame=daily[['date','mean_c']].rename(columns={'mean_c':site}).sort_values('date');panel=PRIVATE/'exploratory_panel.csv';frame.to_csv(panel,index=False);panel.chmod(0o600)
    run={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc scoring inputs fixed after weather retrieval but before model predictions or H30 scoring',
         'limitations':p['limitations']}
    dest.write_text(json.dumps(run,indent=2)+'\n');print('Recorded fixed scoring inputs without inspecting H30')

def run():
    plan=verify_plan();run=json.loads((OUT/'exploratory_run_plan.json').read_text());roster=pd.read_csv(PRIVATE/'exploratory_roster.csv')
    if (OUT/'exploratory_score_status.json').exists() or (PRIVATE/'exploratory_predictions.parquet').exists():raise FileExistsError('Preserve existing target scores')
    site=roster.station_code.iloc[0];job={'network_id':'truckee_'+site,'station_id':site,'station_key':'truckee_exploratory|'+site,
         'provider':'truckee_dwr','independence_group':'truckee_shared_watershed','latitude':float(roster.latitude.iloc[0]),
         'input_path':str(PRIVATE/'exploratory_panel.csv'),'air_input_path':str(PRIVATE/'exploratory_air_forcing.parquet'),
         'statistic_class':'reported_pst_96_finite_quarter_hours_qc_validated_flags_unknown','regulation_status':'managed_watershed',
         'region':'truckee','roster':'independent'}
    job['station_index']=position_index([job['network_id']+'|'+site])[job['network_id']+'|'+site]
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='truckee_reported_pst_exploratory_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text())
    core=T.load_script('truckee_exploratory_cases',ROOT/'scripts/431_tr_cases.py');core.CACHE=PRIVATE/'exploratory_case_cache'
    result=core.station_cases(job,settings,generator,[],resume=False)
    if not result.get('cache'):raise RuntimeError('Case generation unavailable: '+str(result.get('reason')))
    path=Path(result['cache']);path.chmod(0o600);cases=pd.read_parquet(path)
    if set(cases.year.unique())!=set(roster.year) or not cases.design_family.eq('crossed').all() or cases.duplicated(['station_key','year','design_family','realization_id','mask_runs']).any():
        raise ValueError('Evaluated cases differ from fixed cohort')
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads(CAL.read_text())
    if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('Source calibration roles differ')
    bundle['offsets']=cal['D2_offsets'];inference=T.load_script('truckee_exploratory_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    predicted=inference.classical_predictions(inference.predict(cases,bundle),cal)
    lower=predicted.observed_lower_bound__observed_days.to_numpy(float);truth=predicted.eval_truth_h30.to_numpy(float)
    if np.any(np.isfinite(lower)&np.isfinite(truth)&(truth<lower-1e-8)):raise ValueError('Reference contradicts observed bound')
    score=T.load_script('truckee_exploratory_scoring',ROOT/'scripts/598_nova_scotia_exploratory_score.py');samples=T.load_script('truckee_quantile_samples',ROOT/'scripts/528_review_response_annual.py')
    summary,paired,by_year=score.score_tables(predicted,samples.quantile_samples)
    for name,data in [('exploratory_cases.parquet',cases),('exploratory_predictions.parquet',predicted)]:
        q=PRIVATE/name;data.to_parquet(q,index=False);q.chmod(0o600)
    y=PRIVATE/'exploratory_year_scores.csv';by_year.to_csv(y,index=False);y.chmod(0o600)
    summary.to_csv(OUT/'exploratory_score_summary.csv',index=False);paired.to_csv(OUT/'exploratory_paired_summary.csv',index=False)
    status={'status':'exploratory_scored','stations':int(predicted.station_key.nunique()),'reference_years':int(predicted.year.nunique()),'cases':len(predicted),
         'mask_family':'controlled gaps only','strict_reference_qualified':False,'trend_scored':False,
         'source_model':'previously fixed global model and source-only calibration; no new model fit using target outcomes',
         'reference':'daily reported-PST means from 96 finite source readings; pointwise correction/estimation status unknown',
         'limitations':plan['limitations']}
    (OUT/'exploratory_score_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
