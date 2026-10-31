#!/usr/bin/env python3
"""Perturb a fixed mask's hidden target observations and test inference isolation."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import position_index

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'
SOURCE=ROOT/'results/wrr_review_completion_20261024'

def freeze():
    runner=T.load_script('usace_probe_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    path=OUT/'partial_history_hidden_probe_plan.json'
    if path.exists():raise FileExistsError('Preserve hidden probe plan')
    row=pd.read_csv(PRIVATE/'partial_history_roster.csv').sort_values(['resource_id','year']).iloc[0]
    prediction=PRIVATE/'partial_history_predictions'/row.resource_id/str(int(row.year))/'predictions.parquet'
    receipt=prediction.parent/'receipt.json'
    if not receipt.is_file():raise ValueError('First frozen target must have generated predictions')
    p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc before perturbation; first sorted target and first mask, selected without scoring model error',
       'procedure':'Add 10 C to every finite target-day observation hidden by the first saved mask. Replace placeholders for naturally missing target days with 432.1 C. Regenerate all cases, and compare the first mask inference features, plug-in, D2 and classical interval; no target score is computed.',
       'limitations':'One deterministic post-hoc probe cannot establish absence of leakage in every target, history year, mask, source model or forcing input.',
       'resource_id':row.resource_id,'year':int(row.year),}
    path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen one-mask hidden-value perturbation')

def probe():
    runner=T.load_script('usace_probe_runner_check',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    p=json.loads((OUT/'partial_history_hidden_probe_plan.json').read_text());base=PRIVATE/'partial_history_predictions'/p['resource_id']/str(p['year'])
    original=pd.read_parquet(base/'predictions.parquet');first=original.iloc[0];mask=np.zeros(366 if pd.Timestamp(p['year'],12,31).is_leap_year else 365,dtype=bool)
    for item in first.mask_runs.split(';'):
        start,length=map(int,item.split(':'));mask[start:start+length]=True
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    dates=pd.date_range(f"{p['year']}-01-01",f"{p['year']}-12-31");hidden=set(dates[mask])
    sel=daily.resource_id.eq(p['resource_id'])&daily.day.isin(hidden)
    n=int(sel.sum());daily.loc[sel,'mean_c']+=10
    if n==0:raise ValueError('Probe did not change an observed hidden day')
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');row=next(roster[(roster.resource_id==p['resource_id'])&(roster.year==p['year'])].itertuples(index=False))
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usace_partial_history_posthoc_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    engine=T.load_script('usace_probe_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usace_probe_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    indices=position_index(['usace_'+x+'|'+x for x in sorted(roster.resource_id.unique())])
    with tempfile.TemporaryDirectory(prefix='usace_hidden_probe_') as temp:
        runner.make_one(row,daily,settings,generator,bundle,cal,engine,inference,indices,Path(temp),placeholder=432.1)
        changed=pd.read_parquet(Path(temp)/p['resource_id']/str(p['year'])/'predictions.parquet')
    other=changed.loc[changed.realization_id.eq(first.realization_id)]
    if len(other)!=1 or other.iloc[0].mask_runs!=first.mask_runs:raise AssertionError('Probe mask changed')
    f=T.load_script('usace_probe_features',ROOT/'scripts/wrr_tr_features.py')
    features=list(bundle['features']);x=f.design_matrix(original.iloc[[0]],simulation=True).reindex(columns=features).to_numpy();y=f.design_matrix(other,simulation=True).reindex(columns=features).to_numpy()
    if not np.allclose(x,y,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Hidden values altered inference features')
    cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{q:02d}' for q in (5,10,25,50,75,90,95)]
    if not np.allclose(original.iloc[[0]][cols].to_numpy(float),other[cols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Hidden values altered inference output')
    out={'status':'passed','target_cases_probed':1,'observed_hidden_days_perturbed':n,'missing_placeholder_changed':True,
         'feature_columns_compared':len(features),'output_columns_compared':len(cols),'mask_unchanged':True,
         'scope':p['procedure'],'limitations':p['limitations']}
    (OUT/'partial_history_hidden_probe_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','probe']);a=p.parse_args();freeze() if a.action=='freeze' else probe()
