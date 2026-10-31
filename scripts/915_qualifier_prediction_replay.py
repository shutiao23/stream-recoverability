#!/usr/bin/env python3
"""Replay all USGS partial-history predictions in an isolated environment."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,importlib.util,json,sys,tempfile
from datetime import datetime,timezone
from types import SimpleNamespace
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
from stream_recoverability.seeds import position_index
DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def module(path):
 s=importlib.util.spec_from_file_location('usgs_replay_runner',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def freeze():
 path=STAGE/'qualifier_replay_plan.json'
 if path.exists():raise FileExistsError('Preserve replay plan')
 for name in ['qualifier_aware_score_independent_audit.json','qualifier_hidden_status.json']:
  if json.loads((STAGE/name).read_text())['status']!='passed':raise ValueError('Prior audit incomplete')
 files=[STAGE/'scoring_plan.json',STAGE/'qualifier_aware_prediction_status.json',STAGE/'qualifier_aware_score_independent_audit.json',STAGE/'qualifier_hidden_status.json',STAGE/'880_usgs_partial_predict.py',STAGE/'qualifier_hidden_receipts.json',Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after scores, qualification and hidden probes',
 'scope':'Regenerate all eight target years and 144 masks with one numerical thread. Compare case identities/masks, 68 design features and 17 point/quantile/classifier outputs against saved results.',
 'limitations':'Same source model, source calibration, qualifier-aware daily inputs and fixed masks are reused; this is not a model refit, raw-service reconstruction or independent climate validation.',
 }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen complete qualifier-aware partial-history prediction replay')
def run():
 p=json.loads((STAGE/'qualifier_replay_plan.json').read_text())
 runner=module(STAGE/'880_usgs_partial_predict.py');runner.verify();roster=pd.read_csv(STAGE/'qualifier_aware_roster_v2.csv',dtype={'station_id':str,'huc2':str}).sort_values(['station_id','year']);receipts=json.loads((STAGE/'qualifier_hidden_receipts.json').read_text());qualifier_daily=pd.read_parquet(STAGE/'qualifier_aware_daily.parquet');qualifier_daily.date=pd.to_datetime(qualifier_daily.date)
 settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usgs_partial_daily_posthoc_20261027';settings['calendar_year_only']=True;generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text())
 bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets'];engine=T.load_script('usgs_replay_engine',ROOT/'scripts/835_usace_partial_history_engine.py');infer=T.load_script('usgs_replay_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usgs_replay_features',ROOT/'scripts/wrr_tr_features.py');indices=position_index(['usgs_partial_'+x+'|'+x for x in sorted(roster.station_id.unique())])
 cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in [5,10,25,50,75,90,95]]+[f'stochastic_cal_q{q:02d}' for q in [5,10,25,50,75,90,95]];rows=[]
 with tempfile.TemporaryDirectory(prefix='usgs_prediction_replay_',dir='/dev/shm') as tmp:
  for i,r in enumerate(roster.itertuples(index=False),1):
   source=STAGE/'qualifier_aware_predictions'/r.station_id/str(r.year)/'predictions.parquet'
   original=pd.read_parquet(source);designs=[];n=366 if pd.Timestamp(int(r.year),12,31).is_leap_year else 365
   for item in original.itertuples(index=False):
    mask=np.zeros(n,bool)
    for part in item.mask_runs.split(';'):
     start,length=map(int,part.split(':'));mask[start:start+length]=True
    designs.append({'family':'crossed','key':item.realization_id,'length':int(item.gap_length),'overlap_class':item.overlap_class,'mask':mask,'source':''})
   def adapted(cache):
    core=engine.adapted_generator(cache)
    def fixed(support,seed,lengths,replicates):
     if len(support)!=n:raise ValueError('Mask length mismatch')
     return [dict(x,mask=x['mask'].copy()) for x in designs]
    core.crossed_designs=fixed;return core
   proxy=SimpleNamespace(adapted_generator=adapted);saved=original.sort_values('realization_id').reset_index(drop=True);daily=qualifier_daily[qualifier_daily.station_id.eq(r.station_id)].set_index('date').water_c.sort_index();runner.make_one(r,daily,settings,generator,bundle,cal,proxy,infer,indices,Path(tmp));actual=pd.read_parquet(Path(tmp)/r.station_id/str(r.year)/'predictions.parquet').sort_values('realization_id').reset_index(drop=True)
   identity=saved[['realization_id','mask_runs']].equals(actual[['realization_id','mask_runs']]);a=features.design_matrix(saved,simulation=True).reindex(columns=bundle['features']).to_numpy();b=features.design_matrix(actual,simulation=True).reindex(columns=bundle['features']).to_numpy();x=saved[cols].to_numpy(float);y=actual[cols].to_numpy(float)
   rows.append({'station_id':r.station_id,'year':r.year,'cases':len(saved),'mask_equal':identity,'features_equal':bool(np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True)),'outputs_equal':bool(np.allclose(x,y,atol=1e-10,rtol=0,equal_nan=True)),'max_abs_difference':float(np.nanmax(np.abs(x-y)))})
   print('Replayed USGS target',i,'of',len(roster),flush=True)
 frame=pd.DataFrame(rows);path=STAGE/'qualifier_replay_cases.csv';frame.to_csv(path,index=False);ok=frame.mask_equal.all() and frame.features_equal.all() and frame.outputs_equal.all()
 out={'status':'passed' if ok else 'failed','sites':int(frame.station_id.nunique()),'target_years':len(frame),'cases':int(frame.cases.sum()),'matching_mask_years':int(frame.mask_equal.sum()),'matching_feature_years':int(frame.features_equal.sum()),'matching_output_years':int(frame.outputs_equal.sum()),'max_output_difference':float(frame.max_abs_difference.max()),'threads':1,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'qualifier_replay_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
