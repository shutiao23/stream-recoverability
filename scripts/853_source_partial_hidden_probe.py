#!/usr/bin/env python3
"""Perturb hidden target and hidden training-history values for one source case."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
import joblib
import wrr_tr_common as T
from stream_recoverability.seeds import position_index

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial';OPEN=REV/'open_observed_record_snapshot';SOURCE=ROOT/'results/wrr_review_completion_20261024';MODELS=ROOT/'private/wrr_open_source_sensitivity_20261026'

def freeze():
    worker=T.load_script('source_history_probe_worker',ROOT/'scripts/850_source_partial_history_factorial.py');worker.verify()
    if json.loads((OUT/'independent_audit.json').read_text())['status']!='passed':raise ValueError('Scoring audit incomplete')
    path=OUT/'hidden_probe_plan.json'
    if path.exists():raise FileExistsError('Preserve hidden probe plan')
    roster=pd.read_csv(OUT/'roster.csv').sort_values('station_key');row=roster.iloc[0]
    p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after factorial scores; first sorted station and fixed spring 30-day mask chosen before perturbation',
      'target_probe':'Add 10 C to the 30 target days hidden by the fixed spring mask. Compare both history modes and both count settings for that mask using same-process controls.',
      'history_probe':'Add 1000 C to all 240 target-station historical July 1-30 values that are deliberately hidden in the partial-history treatment. Compare all nine target masks and both count settings under partial history.',
      'limitations':'One selected station and target mask are not an exhaustive proof of leakage absence. Same code and models are reused; calibration, data quality and climate independence are not evaluated.',
      'station_key':row.station_key,}
    path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen source target/history perturbation probe')

def run():
    worker=T.load_script('source_history_probe_worker2',ROOT/'scripts/850_source_partial_history_factorial.py');worker.verify();p=json.loads((OUT/'hidden_probe_plan.json').read_text())
    roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str});row=next(roster[roster.station_key.eq(p['station_key'])].itertuples(index=False))
    daily=pd.read_parquet(OPEN/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    target_changed=daily.copy();dates=pd.date_range('2017-01-01','2017-12-31');mask=set(dates[75:105]);target_sel=target_changed.station_key.eq(row.station_key)&target_changed.date.isin(mask);target_changed.loc[target_sel,'water_c']+=10
    history_changed=daily.copy();x=history_changed.date;history_sel=history_changed.station_key.eq(row.station_key)&x.dt.year.between(2009,2016)&x.dt.month.eq(7)&x.dt.day.le(30);history_changed.loc[history_sel,'water_c']+=1000
    if int(target_sel.sum())!=30 or int(history_sel.sum())!=240:raise ValueError('Unexpected probe masks')
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='source_partial_factorial_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());engine=T.load_script('source_history_probe_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('source_history_probe_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('source_history_probe_features',ROOT/'scripts/wrr_tr_features.py')
    indices=position_index(sorted(roster.station_key.tolist()));bundle=joblib.load(MODELS/'refits/leave_one_year_out/seed_00'/f'{row.provider}.joblib')
    with tempfile.TemporaryDirectory(prefix='source_history_probe_') as tmp:
        base=worker.run_station(row,daily,settings,generator,engine,inference,indices,Path(tmp)/'base')
        changed_target=worker.run_station(row,target_changed,settings,generator,engine,inference,indices,Path(tmp)/'target')
        changed_history=worker.run_station(row,history_changed,settings,generator,engine,inference,indices,Path(tmp)/'history')
    keys=['realization_id','history_mode','counterfactual_complete_count'];cols=['h30__policy','D2','risk_score']+[f'D2_q{x:02d}' for x in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{x:02d}' for x in (5,10,25,50,75,90,95)]
    def compare(a,b):
        a=a.sort_values(keys).reset_index(drop=True);b=b.sort_values(keys).reset_index(drop=True)
        if not a[keys+['mask_runs']].equals(b[keys+['mask_runs']]):return False,False
        x=features.design_matrix(a,simulation=True).reindex(columns=bundle['features']).to_numpy();y=features.design_matrix(b,simulation=True).reindex(columns=bundle['features']).to_numpy()
        return bool(np.allclose(x,y,atol=1e-10,rtol=0,equal_nan=True)),bool(np.allclose(a[cols].to_numpy(float),b[cols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True))
    target_result=compare(base[base.realization_id.eq('fixed_30_spring')],changed_target[changed_target.realization_id.eq('fixed_30_spring')])
    history_result=compare(base[base.history_mode.eq('partial')],changed_history[changed_history.history_mode.eq('partial')])
    ok=all(target_result+history_result)
    result={'status':'passed' if ok else 'failed','target_hidden_days_changed':int(target_sel.sum()),'historical_hidden_days_changed':int(history_sel.sum()),
      'target_variants_compared':4,'partial_history_variant_rows_compared':18,'model_features_compared':len(bundle['features']),
      'target_features_equal':target_result[0],'target_outputs_equal':target_result[1],'history_features_equal':history_result[0],'history_outputs_equal':history_result[1],
      'limitations':p['limitations']}
    (OUT/'hidden_probe_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
