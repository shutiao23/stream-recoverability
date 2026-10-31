#!/usr/bin/env python3
"""Paired same-process hidden target perturbations for all USGS target years."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,importlib.util,json,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
from stream_recoverability.seeds import position_index
DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def module(path):
 s=importlib.util.spec_from_file_location('usgs_hidden_all_runner',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def freeze():
 path=STAGE/'hidden_all_plan.json'
 if path.exists():raise FileExistsError('Preserve hidden probe plan')
 if json.loads((STAGE/'score_independent_audit.json').read_text())['status']!='passed':raise ValueError('Score audit incomplete')
 roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});receipts={}
 for r in roster.itertuples(index=False):
  d=STAGE/'predictions'/r.station_id/str(r.year);info=json.loads((d/'receipt.json').read_text())
 file=STAGE/'hidden_all_receipts.json';file.write_text(json.dumps(receipts,indent=2,sort_keys=True)+'\n')
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after all eight model scores; first saved mask per target fixed before this probe',
   'procedure':'For all eight target years compare a same-process unchanged-input control with a rerun after increasing all target observations hidden by the first mask by 10 C. Check mask, 68 model inputs and 17 outputs at 1e-10 tolerance; separately compare unchanged controls to saved predictions.',
   'limitations':'One mask per target and same implementation/models; no exhaustive proof of no hidden leakage, instrument accuracy, clock agreement, independence or calibration.',
   }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen eight-target paired hidden-value probe')
def run():
 p=json.loads((STAGE/'hidden_all_plan.json').read_text())
 runner=module(STAGE/'880_usgs_partial_predict.py');runner.verify();roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str}).sort_values(['station_id','year']);receipts=json.loads((STAGE/'hidden_all_receipts.json').read_text());parser=T.load_script('usgs_all_hidden_parser',ROOT/'scripts/871_usgs_partial_daily_feasibility.py')
 settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usgs_partial_daily_posthoc_20261027';settings['calendar_year_only']=True;generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text())
 bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets'];engine=T.load_script('usgs_all_hidden_engine',ROOT/'scripts/835_usace_partial_history_engine.py');infer=T.load_script('usgs_all_hidden_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usgs_all_hidden_features',ROOT/'scripts/wrr_tr_features.py');indices=position_index(['usgs_partial_'+x+'|'+x for x in sorted(roster.station_id.unique())])
 cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in [5,10,25,50,75,90,95]]+[f'stochastic_cal_q{q:02d}' for q in [5,10,25,50,75,90,95]];rows=[]
 with tempfile.TemporaryDirectory(prefix='usgs_hidden_all_',dir='/dev/shm') as tmp:
  for i,r in enumerate(roster.itertuples(index=False),1):
   path=STAGE/'predictions'/r.station_id/str(r.year)/'predictions.parquet'
   saved=pd.read_parquet(path);first=saved.iloc[0];idx=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31');mask=np.zeros(len(idx),bool)
   for part in first.mask_runs.split(';'):
    start,length=map(int,part.split(':'));mask[start:start+length]=True
   daily=parser.valid_daily(pd.read_parquet(DATA/'daily'/(r.station_id+'.parquet')));changed=daily.copy();changed.loc[idx[mask]]+=10;out=[]
   for label,source in [('control',daily),('perturbed',changed)]:
    base=Path(tmp)/label;runner.make_one(r,source,settings,generator,bundle,cal,engine,infer,indices,base);f=pd.read_parquet(base/r.station_id/str(r.year)/'predictions.parquet');selected=f[f.realization_id.eq(first.realization_id)]
    if len(selected)!=1 or selected.iloc[0].mask_runs!=first.mask_runs:raise AssertionError('Mask differs')
    out.append((selected,features.design_matrix(selected,simulation=True).reindex(columns=bundle['features']).to_numpy()))
   c,fc=out[0];z,fz=out[1];a=c[cols].to_numpy(float);b=z[cols].to_numpy(float);old=saved.iloc[[0]][cols].to_numpy(float);delta=np.abs(a-old)
   rows.append({'station_id':r.station_id,'year':r.year,'hidden_days':int(mask.sum()),'features_equal':bool(np.allclose(fc,fz,atol=1e-10,rtol=0,equal_nan=True)),
     'outputs_equal':bool(np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True)),'saved_vs_control_max_abs':float(np.nanmax(delta))})
   print('Paired target',i,'of',len(roster),flush=True)
 df=pd.DataFrame(rows);f=STAGE/'hidden_all_cases.csv';df.to_csv(f,index=False)
 result={'status':'passed' if df.features_equal.all() and df.outputs_equal.all() else 'failed','target_years':len(df),'sites':df.station_id.nunique(),'feature_passes':int(df.features_equal.sum()),'output_passes':int(df.outputs_equal.sum()),'observed_hidden_days_perturbed':int(df.hidden_days.sum()),'saved_vs_control_drift_cases':int(df.saved_vs_control_max_abs.gt(1e-10).sum()),'saved_vs_control_max_abs':float(df.saved_vs_control_max_abs.max()),'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'hidden_all_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
