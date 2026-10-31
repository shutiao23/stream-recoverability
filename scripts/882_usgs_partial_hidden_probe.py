#!/usr/bin/env python3
"""Paired hidden target perturbation on the first frozen USGS target case."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,importlib.util,json,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
from stream_recoverability.seeds import position_index
SOURCE=ROOT/'results/wrr_review_completion_20261024';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';DATA=ROOT/'data/external/additional_usgs_observed';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def module(path):
 s=importlib.util.spec_from_file_location('usgs_probe_runner',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def freeze():
 path=STAGE/'hidden_probe_plan.json'
 if path.exists():raise FileExistsError('Preserve probe plan')
 r=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str}).sort_values(['station_id','year']).iloc[0];d=STAGE/'predictions'/r.station_id/str(int(r.year));rec=d/'receipt.json'
 if not rec.exists():raise ValueError('First target prediction missing')
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc; first sorted target and first saved mask, selected without target error scoring',
    'procedure':'Increase all daily target values hidden by this saved synthetic mask by 10 C; rerun in same numerical environment and compare mask, 68 model features and 17 prediction outputs.',
    'limitations':'One target case is not an exhaustive leakage test; this check does not prove sensor quality, clock convention, independent climate or model calibration.',
    'station_id':r.station_id,'year':int(r.year),}
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen one-target hidden-day perturbation')
def run():
 p=json.loads((STAGE/'hidden_probe_plan.json').read_text());d=STAGE/'predictions'/p['station_id']/str(p['year'])
 path=STAGE/'880_usgs_partial_predict.py';runner=module(path);runner.verify();roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});row=next(roster[roster.station_id.eq(p['station_id'])&roster.year.eq(p['year'])].itertuples(index=False))
 original=pd.read_parquet(d/'predictions.parquet');first=original.iloc[0];idx=pd.date_range(f"{p['year']}-01-01",f"{p['year']}-12-31");mask=np.zeros(len(idx),bool)
 for piece in first.mask_runs.split(';'):
  start,length=map(int,piece.split(':'));mask[start:start+length]=True
 parser=T.load_script('usgs_hidden_parser',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');daily=parser.valid_daily(pd.read_parquet(DATA/'daily'/(p['station_id']+'.parquet')));changed=daily.copy();selected=idx[mask];changed.loc[selected]+=10
 settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usgs_partial_daily_posthoc_20261027';settings['calendar_year_only']=True
 generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
 engine=T.load_script('usgs_hidden_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usgs_hidden_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usgs_hidden_features',ROOT/'scripts/wrr_tr_features.py');indices=position_index(['usgs_partial_'+x+'|'+x for x in sorted(roster.station_id.unique())])
 with tempfile.TemporaryDirectory(prefix='usgs_hidden_',dir='/dev/shm') as temp:
  runner.make_one(row,changed,settings,generator,bundle,cal,engine,inference,indices,Path(temp));changed_pred=pd.read_parquet(Path(temp)/row.station_id/str(row.year)/'predictions.parquet')
 match=changed_pred[changed_pred.realization_id.eq(first.realization_id)]
 if len(match)!=1 or match.iloc[0].mask_runs!=first.mask_runs:raise AssertionError('Mask changed')
 a=features.design_matrix(original.iloc[[0]],simulation=True).reindex(columns=bundle['features']).to_numpy();b=features.design_matrix(match,simulation=True).reindex(columns=bundle['features']).to_numpy()
 cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in [5,10,25,50,75,90,95]]+[f'stochastic_cal_q{q:02d}' for q in [5,10,25,50,75,90,95]]
 features_ok=bool(np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True));outputs_ok=bool(np.allclose(original.iloc[[0]][cols].to_numpy(float),match[cols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True))
 out={'status':'passed' if features_ok and outputs_ok else 'failed','target_cases':1,'hidden_days_perturbed':int(mask.sum()),'feature_columns':len(bundle['features']),'output_columns':len(cols),'features_unchanged':features_ok,'outputs_unchanged':outputs_ok,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'hidden_probe_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
