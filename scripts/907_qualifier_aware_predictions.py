#!/usr/bin/env python3
"""Replay exact original USGS target masks after stricter history qualifier handling."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
from stream_recoverability.seeds import position_index
PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def inputs():
 s=json.loads((STAGE/'qualifier_aware_history_status.json').read_text());fix=json.loads((STAGE/'qualifier_aware_roster_correction.json').read_text())
 if s['status']!='completed_qualifier_aware_feasibility' or fix['status']!='corrected_before_qualifier_aware_predictions':raise ValueError('History or metadata correction missing')
 roster=pd.read_csv(STAGE/'qualifier_aware_roster_v2.csv',dtype={'station_id':str,'huc2':str});baseline=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});receipts={}
 for r in baseline.itertuples(index=False):
  d=STAGE/'predictions'/r.station_id/str(r.year);info=json.loads((d/'receipt.json').read_text())
 if len(roster)!=8 or set(zip(roster.station_id,roster.year))!=set(zip(baseline.station_id,baseline.year)):raise ValueError('Target roster changed')
 return roster,baseline,receipts
def freeze():
 path=STAGE/'qualifier_aware_prediction_plan.json'
 if path.exists():raise FileExistsError('Preserve prediction plan')
 roster,base,receipts=inputs();dest=STAGE/'qualifier_aware_baseline_receipts.json';dest.write_text(json.dumps(receipts,indent=2,sort_keys=True)+'\n')
 files=[STAGE/'qualifier_aware_history_plan.json',STAGE/'qualifier_aware_history_status.json',STAGE/'qualifier_aware_roster_correction.json',STAGE/'qualifier_aware_roster_v2.csv',STAGE/'qualifier_aware_daily.parquet',
   STAGE/'expansion_ice_raw_daily_status.json',STAGE/'scoring_plan.json',STAGE/'880_usgs_partial_predict.py',ROOT/'scripts/835_usace_partial_history_engine.py',ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/495_review_completion_independent_analysis.py',dest,Path(__file__)]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after earlier target outcomes, model scores and ICE flags were examined; before alternative predictions',
    'target':'All eight original target years, reporting unsupported targets if fewer than three qualifier-aware histories remain. Use the exact original target mask IDs and positions, in original order; no replacement of missing cases.',
    'history':'Remove any source daily row with nonempty qualifier, reapply prior history eligibility and interpolate only missing values in retained history years. All target years remain complete and unflagged. Actual complete history count remains factual.',
    'interpretation':'The sensitivity changes available history years and training input simultaneously. Nonempty qualifier removal is a conservative policy, not evidence values are false. Original training and scoring were already opened, so this is not an independent or prospective test.',
    'checks':'For stations with unchanged eligible history and no removed qualifiers in those histories, require all 18 masks, 68 model inputs and 17 outputs to match the saved baseline within 1e-10. Retain the original overlap label but recompute overlap fraction from each history climatology.',
    'limitations':'One Rio Mora site has excluded ICE-marked histories, all target years were previously inspected, and sensor truth, clock convention, weather alignment, source overlap, climate independence and output quality remain unresolved.',
    }
 path.write_text(json.dumps(p,indent=2)+'\n');print('Frozen qualifier-aware fixed-mask prediction plan')
def run():
 p=json.loads((STAGE/'qualifier_aware_prediction_plan.json').read_text())
 roster,baseline,receipts=inputs();ids=json.loads((STAGE/'qualifier_aware_baseline_receipts.json').read_text())
 if receipts!=ids:raise ValueError('Original prediction receipts changed')
 runner=module('usgs_qualifier_runner',STAGE/'880_usgs_partial_predict.py');runner.verify();engine=T.load_script('usgs_qualifier_base_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usgs_qualifier_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usgs_qualifier_features',ROOT/'scripts/wrr_tr_features.py')
 settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usgs_partial_daily_posthoc_20261027';settings['calendar_year_only']=True;generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
 indices=position_index(['usgs_partial_'+x+'|'+x for x in sorted(roster.station_id.unique())]);daily=pd.read_parquet(STAGE/'qualifier_aware_daily.parquet');daily['date']=pd.to_datetime(daily.date);stage=STAGE/'qualifier_aware_predictions';stage.mkdir(exist_ok=True);rows=[];outcols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{q:02d}' for q in (5,10,25,50,75,90,95)]
 for i,row in enumerate(roster.itertuples(index=False),1):
  dest=stage/row.station_id/str(row.year);item={'station_id':row.station_id,'year':int(row.year),'eligible':bool(row.eligible_partial_history),'status':'unknown'}
  if not row.eligible_partial_history:item['status']='unsupported_insufficient_history';rows.append(item);continue
  if (dest/'receipt.json').exists():
   rec=json.loads((dest/'receipt.json').read_text())
  else:
   if dest.exists() and any(dest.iterdir()):raise FileExistsError('Preserve unreceipted target')
   orig=STAGE/'predictions'/row.station_id/str(row.year)/'predictions.parquet';saved=pd.read_parquet(orig);designs=[]
   for x in saved.itertuples(index=False):
    n=366 if pd.Timestamp(int(row.year),12,31).is_leap_year else 365;mask=np.zeros(n,bool)
    for part in x.mask_runs.split(';'):
     start,length=map(int,part.split(':'));mask[start:start+length]=True
    designs.append({'family':'crossed','key':x.realization_id,'length':int(x.gap_length),'overlap_class':x.overlap_class,'mask':mask,'source':''})
   if len(designs)!=18:raise ValueError('Unexpected fixed masks')
   def adapted(cache):
    core=engine.adapted_generator(cache)
    def fixed(support,seed,lengths,replicates):
     if len(support)!=len(designs[0]['mask']):raise ValueError('Mask year length changed')
     return [dict(x,mask=x['mask'].copy()) for x in designs]
    core.crossed_designs=fixed;return core
   proxy=SimpleNamespace(adapted_generator=adapted);series=daily[daily.station_id.eq(row.station_id)].set_index('date').water_c.sort_index();rec=runner.make_one(row,series,settings,generator,bundle,cal,proxy,inference,indices,stage)
  saved=pd.read_parquet(STAGE/'predictions'/row.station_id/str(row.year)/'predictions.parquet');new=pd.read_parquet(dest/'predictions.parquet')
  if not saved[['realization_id','mask_runs']].equals(new[['realization_id','mask_runs']]):raise AssertionError('Target mask geometry changed')
  unchanged=str(row.history_years)==str(row.original_history_years)
  if unchanged:
   a=features.design_matrix(saved,simulation=True).reindex(columns=bundle['features']).to_numpy();b=features.design_matrix(new,simulation=True).reindex(columns=bundle['features']).to_numpy()
   if not np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True) or not np.allclose(saved[outcols].to_numpy(float),new[outcols].to_numpy(float),atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Unchanged clean history failed replay')
  item.update(status='completed',cases=len(new),same_target_masks=True,history_unchanged=unchanged,unchanged_history_exact_replay=unchanged,)
  rows.append(item);print('Qualifier-aware target',i,'of',len(roster),'unchanged history',unchanged,flush=True)
 f=STAGE/'qualifier_aware_prediction_receipts.json';f.write_text(json.dumps(rows,indent=2)+'\n')
 out={'status':'completed_predictions_not_scored' if all(x['status'] in ('completed','unsupported_insufficient_history') for x in rows) else 'partial_unknown','target_years':len(rows),
      'completed_years':sum(x['status']=='completed' for x in rows),'unsupported_years':sum(x['status']=='unsupported_insufficient_history' for x in rows),
      'unchanged_history_replayed_years':sum(x.get('unchanged_history_exact_replay',False) for x in rows),'target_error_scored':False,'limitations':p['limitations'],'storage':'temporary RAM filesystem; not durable'}
 (STAGE/'qualifier_aware_prediction_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
