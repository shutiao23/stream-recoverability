#!/usr/bin/env python3
"""Replay all partial-history cases with single-thread numerical settings."""
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

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'
DATA=ROOT/'data/external/wrr_usace_reservoir_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def freeze():
    runner=T.load_script('usace_replay_plan_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    p=OUT/'partial_history_prediction_replay_plan.json'
    if p.exists():raise FileExistsError('Preserve replay plan')
    score=json.loads((OUT/'partial_history_score_independent_audit.json').read_text());probe=json.loads((OUT/'partial_history_paired_hidden_observed_status.json').read_text())
    if score['status']!='passed' or probe['status']!='passed_paired_perturbation':raise ValueError('Previous checks incomplete')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after aggregate score and thread-sensitivity findings were examined',
      'scope':'Regenerate all fixed 17 target years and all masks in one process, with OMP, OpenBLAS, MKL and NumExpr thread counts set to 1 before numerical imports. Compare saved case identity/masks, all model features and 17 point/quantile outputs with absolute tolerance 1e-10.',
      'limitations':'Same implementation and fixed model are reused. This does not refit source models, establish data rights, validate partial-history extrapolation or provide independent climate evidence. Other thread configurations previously gave output drift.',
      }
    p.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen single-thread all-case replay')

def run():
    runner=T.load_script('usace_replay_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    p=json.loads((OUT/'partial_history_prediction_replay_plan.json').read_text())
    receipts=json.loads((PRIVATE/'partial_history_hidden_all_inputs.json').read_text());roster=pd.read_csv(PRIVATE/'partial_history_roster.csv').sort_values(['resource_id','year'])
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usace_partial_history_posthoc_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    engine=T.load_script('usace_replay_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usace_replay_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usace_replay_features',ROOT/'scripts/wrr_tr_features.py')
    indices=position_index(['usace_'+x+'|'+x for x in sorted(roster.resource_id.unique())]);cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{q:02d}' for q in (5,10,25,50,75,90,95)]
    records=[]
    with tempfile.TemporaryDirectory(prefix='usace_prediction_replay_') as tmp:
        for n,row in enumerate(roster.itertuples(index=False),1):
            path=PRIVATE/'partial_history_predictions'/row.resource_id/str(row.year)/'predictions.parquet'
            saved=pd.read_parquet(path).sort_values('realization_id').reset_index(drop=True)
            runner.make_one(row,daily,settings,generator,bundle,cal,engine,inference,indices,Path(tmp))
            replay=pd.read_parquet(Path(tmp)/row.resource_id/str(row.year)/'predictions.parquet').sort_values('realization_id').reset_index(drop=True)
            identity=saved[['realization_id','mask_runs']].equals(replay[['realization_id','mask_runs']])
            a=features.design_matrix(saved,simulation=True).reindex(columns=bundle['features']).to_numpy();b=features.design_matrix(replay,simulation=True).reindex(columns=bundle['features']).to_numpy()
            x=saved[cols].to_numpy(float);y=replay[cols].to_numpy(float)
            records.append({'resource_id':row.resource_id,'year':row.year,'cases':len(saved),'mask_identity':identity,
              'feature_match':bool(np.allclose(a,b,rtol=0,atol=1e-10,equal_nan=True)),'prediction_match':bool(np.allclose(x,y,rtol=0,atol=1e-10,equal_nan=True)),
              'max_output_abs_difference':float(np.nanmax(np.abs(x-y)))})
            print('Replayed target',n,'of',len(roster),'cases',len(saved),flush=True)
    frame=pd.DataFrame(records);dest=PRIVATE/'partial_history_prediction_replay_cases.csv';frame.to_csv(dest,index=False);dest.chmod(0o600)
    ok=frame.mask_identity.all() and frame.feature_match.all() and frame.prediction_match.all()
    result={'status':'passed' if ok else 'failed','target_years':len(frame),'cases':int(frame.cases.sum()),
       'matching_mask_target_years':int(frame.mask_identity.sum()),'matching_feature_target_years':int(frame.feature_match.sum()),
       'matching_prediction_target_years':int(frame.prediction_match.sum()),'maximum_output_difference_c':float(frame.max_output_abs_difference.max()),
       'thread_environment':{k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
       'limitations':p['limitations']}
    (OUT/'partial_history_prediction_replay_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
