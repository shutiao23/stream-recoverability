#!/usr/bin/env python3
"""Replay all fixed source-history predictions using local restricted models."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
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

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial';OPEN=REV/'open_observed_record_snapshot'
PRIVATE=ROOT/'private/wrr_source_partial_history_factorial_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';MODELS=ROOT/'private/wrr_open_source_sensitivity_20261026'

def freeze():
    worker=T.load_script('source_replay_worker',ROOT/'scripts/850_source_partial_history_factorial.py');worker.verify()
    p=OUT/'local_prediction_replay_plan.json'
    if p.exists():raise FileExistsError('Preserve replay plan')
    for f in ['independent_audit.json','hidden_probe_status.json']:
        if json.loads((OUT/f).read_text())['status']!='passed':raise ValueError('Earlier audit incomplete')
    roster=pd.read_csv(OUT/'roster.csv');receipts={}
    for row in roster.itertuples(index=False):
        path=PRIVATE/'cases'/(row.station_key.replace('|','_')+'.parquet');info=json.loads(path.with_suffix('.json').read_text())
    dest=PRIVATE/'local_prediction_replay_inputs.json';dest.write_text(json.dumps(receipts,sort_keys=True,indent=2)+'\n');dest.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc replay fixed after factorial scores and one hidden-value probe',
      'scope':'Regenerate all 15 stations, nine masks and four factorial variants with one numerical thread, compare masks, all source-model features and 17 outputs with saved cases at 1e-10 tolerance.',
      'limitations':'Same code and restricted fixed models, calibrations and processed data are reused. This is not independent model fitting, a raw-data rebuild or proof of climate independence.',
      }
    p.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen full local source-history prediction replay')

def run():
    worker=T.load_script('source_replay_worker2',ROOT/'scripts/850_source_partial_history_factorial.py');worker.verify();p=json.loads((OUT/'local_prediction_replay_plan.json').read_text())
    receipts=json.loads((PRIVATE/'local_prediction_replay_inputs.json').read_text());roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str});daily=pd.read_parquet(OPEN/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='source_partial_factorial_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());engine=T.load_script('source_replay_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('source_replay_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('source_replay_features',ROOT/'scripts/wrr_tr_features.py')
    indices=position_index(sorted(roster.station_key.tolist()));keys=['realization_id','history_mode','counterfactual_complete_count'];cols=['h30__policy','D2','risk_score']+[f'D2_q{x:02d}' for x in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{x:02d}' for x in (5,10,25,50,75,90,95)]
    rows=[]
    with tempfile.TemporaryDirectory(prefix='source_history_replay_') as tmp:
        for n,row in enumerate(roster.itertuples(index=False),1):
            path=PRIVATE/'cases'/(row.station_key.replace('|','_')+'.parquet')
            saved=pd.read_parquet(path).sort_values(keys).reset_index(drop=True);actual=worker.run_station(row,daily,settings,generator,engine,inference,indices,Path(tmp)).sort_values(keys).reset_index(drop=True)
            model=joblib.load(MODELS/'refits/leave_one_year_out/seed_00'/f'{row.provider}.joblib')
            identity=saved[keys+['mask_runs']].equals(actual[keys+['mask_runs']]);x=features.design_matrix(saved,simulation=True).reindex(columns=model['features']).to_numpy();y=features.design_matrix(actual,simulation=True).reindex(columns=model['features']).to_numpy()
            a=saved[cols].to_numpy(float);b=actual[cols].to_numpy(float);difference=np.abs(a-b)
            rows.append({'station_key':row.station_key,'rows':len(saved),'identity_match':identity,'feature_match':bool(np.allclose(x,y,atol=1e-10,rtol=0,equal_nan=True)),
              'output_match':bool(np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True)),'max_abs_difference':float(np.nanmax(difference))})
            print('Replayed source station',n,'of',len(roster),flush=True)
    frame=pd.DataFrame(rows);dest=PRIVATE/'local_prediction_replay_cases.csv';frame.to_csv(dest,index=False);dest.chmod(0o600)
    ok=frame.identity_match.all() and frame.feature_match.all() and frame.output_match.all()
    status={'status':'passed' if ok else 'failed','stations':len(frame),'factorial_rows':int(frame.rows.sum()),'matching_masks_stations':int(frame.identity_match.sum()),
      'matching_features_stations':int(frame.feature_match.sum()),'matching_outputs_stations':int(frame.output_match.sum()),
      'max_output_difference':float(frame.max_abs_difference.max()),'numerical_threads':1,'limitations':p['limitations']}
    (OUT/'local_prediction_replay_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
