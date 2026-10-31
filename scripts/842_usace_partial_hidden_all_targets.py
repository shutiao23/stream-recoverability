#!/usr/bin/env python3
"""Repeat a frozen first-mask hidden-value perturbation across all target years."""
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
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def freeze():
    runner=T.load_script('usace_all_probe_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    score=json.loads((OUT/'partial_history_score_independent_audit.json').read_text())
    if score['status']!='passed':raise ValueError('Score audit incomplete')
    dest=OUT/'partial_history_hidden_all_plan.json'
    if dest.exists():raise FileExistsError('Preserve all-target probe plan')
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv').sort_values(['resource_id','year']);receipts={}
    for r in roster.itertuples(index=False):
        d=PRIVATE/'partial_history_predictions'/r.resource_id/str(r.year);info=json.loads((d/'receipt.json').read_text())
    receipt=PRIVATE/'partial_history_hidden_all_inputs.json';receipt.write_text(json.dumps(receipts,indent=2,sort_keys=True)+'\n');receipt.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after target score summaries were examined; all cohort years and first saved mask per year fixed before this probe',
          'procedure':'For each fixed target, add 10 C to all finite water days hidden by its first mask, replace target natural-gap placeholders by 432.1 C, rerun case generation and inference. Compare the same mask, all source-model features, plug-in, D2, risk score and stochastic quantiles.',
          'limitations':'17 deterministic masks, not every mask; shared source model and generator are reused. Does not establish complete absence of leakage, independence, calibration or sensor accuracy.',
          'targets':len(roster),}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen all-target hidden-value probe')

def run():
    runner=T.load_script('usace_all_probe_runner2',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    p=json.loads((OUT/'partial_history_hidden_all_plan.json').read_text())
    receipts=json.loads((PRIVATE/'partial_history_hidden_all_inputs.json').read_text());roster=pd.read_csv(PRIVATE/'partial_history_roster.csv').sort_values(['resource_id','year'])
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usace_partial_history_posthoc_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    engine=T.load_script('usace_all_probe_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usace_all_probe_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usace_all_probe_features',ROOT/'scripts/wrr_tr_features.py')
    indices=position_index(['usace_'+x+'|'+x for x in sorted(roster.resource_id.unique())]);changed_days=0
    cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{q:02d}' for q in (5,10,25,50,75,90,95)]
    with tempfile.TemporaryDirectory(prefix='usace_all_hidden_probe_') as tmp:
        for n,row in enumerate(roster.itertuples(index=False),1):
            path=PRIVATE/'partial_history_predictions'/row.resource_id/str(row.year)/'predictions.parquet'
            saved=pd.read_parquet(path);first=saved.iloc[0];dates=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31');mask=np.zeros(len(dates),dtype=bool)
            for item in first.mask_runs.split(';'):
                start,length=map(int,item.split(':'));mask[start:start+length]=True
            changed=daily.copy();m=changed.resource_id.eq(row.resource_id)&changed.day.isin(set(dates[mask]));count=int(m.sum())
            if not count:raise ValueError('No observed hidden values to perturb')
            changed.loc[m,'mean_c']+=10;changed_days+=count
            runner.make_one(row,changed,settings,generator,bundle,cal,engine,inference,indices,Path(tmp),placeholder=432.1)
            alt=pd.read_parquet(Path(tmp)/row.resource_id/str(row.year)/'predictions.parquet');selected=alt.loc[alt.realization_id.eq(first.realization_id)]
            if len(selected)!=1 or selected.iloc[0].mask_runs!=first.mask_runs:raise AssertionError('Mask changed')
            x=features.design_matrix(saved.iloc[[0]],simulation=True).reindex(columns=bundle['features']).to_numpy()
            y=features.design_matrix(selected,simulation=True).reindex(columns=bundle['features']).to_numpy()
            if not np.allclose(x,y,atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Hidden input changed features')
            if not np.allclose(saved.iloc[[0]][cols].to_numpy(float),selected[cols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Hidden input changed predictions')
            print('Probed target',n,'of',len(roster),flush=True)
    result={'status':'passed','target_station_years':len(roster),'target_resources':int(roster.resource_id.nunique()),'masks_probed':len(roster),
       'observed_hidden_days_perturbed':changed_days,'features_compared_per_mask':len(bundle['features']),'outputs_compared_per_mask':len(cols),
       'limitations':p['limitations']}
    (OUT/'partial_history_hidden_all_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
