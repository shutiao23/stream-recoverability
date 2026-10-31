#!/usr/bin/env python3
"""Generate fixed-source USGS partial-history predictions without truth scoring."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import argparse,json,sys
from pathlib import Path
import joblib,numpy as np,pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');sys.path.insert(0,str(ROOT/'scripts'))
import wrr_tr_common as T
from stream_recoverability.seeds import position_index
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027');POWER=STAGE/'power'
def verify():
 p=json.loads((STAGE/'scoring_plan.json').read_text())
 s=json.loads((STAGE/'forcing_status.json').read_text())
 if s['status']!='completed':raise ValueError('Forcing not available')
 return p
def prepare(row,daily,placeholder=0):
 hist=[int(x) for x in row.history_years.split(';')];years=hist+[int(row.year)];idx=pd.date_range(f'{min(years)}-01-01',f'{max(years)}-12-31');raw=daily.reindex(idx);out=pd.Series(np.nan,index=idx,dtype=float);details=[];complete=0
 for year in hist:
  s=raw[raw.index.year==year];missing=s.isna().to_numpy();edges=np.diff(np.r_[False,missing,False].astype(int));lengths=np.flatnonzero(edges==-1)-np.flatnonzero(edges==1)
  if s.notna().mean()<.75 or missing[0] or missing[-1] or len(lengths) and int(lengths.max())>45:raise ValueError('History no longer meets frozen rule')
  filled=s.interpolate(method='time',limit_area='inside')
  if filled.isna().any():raise ValueError('History interpolation failed')
  out.loc[s.index]=filled;complete+=int(s.notna().all());details.append({'year':year,'observed_days':int(s.notna().sum()),'interpolated_days':int(s.isna().sum())})
 target=raw[raw.index.year==int(row.year)]
 if target.isna().any() or len(target) not in (365,366):raise ValueError('Target is not fully observed under fixed daily rule')
 if complete!=int(row.complete_history_years):raise ValueError('Actual history count differs')
 out.loc[target.index]=target
 return pd.DataFrame({'date':idx,row.station_id:out.to_numpy()}),details

def make_one(row,daily,settings,generator,bundle,cal,engine,inference,indices,stage):
 panel,details=prepare(row,daily);target=stage/row.station_id/str(row.year);target.mkdir(parents=True,exist_ok=True);file=target/'panel.csv';panel.to_csv(file,index=False)
 n=366 if pd.Timestamp(int(row.year),12,31).is_leap_year else 365
 job={'network_id':'usgs_partial_'+row.station_id,'station_id':row.station_id,'station_key':'usgs_partial|'+row.station_id,'provider':'usgs',
      'independence_group':'usgs_partial_'+row.station_id,'latitude':float(row.latitude),'input_path':str(file),'air_input_path':str(POWER/'daily_air.parquet'),
      'statistic_class':'approved_usgs_reported_daily_no_detected_estimate','regulation_status':'unknown','region':'usgs_partial','roster':'partial_exploratory',
      'station_index':indices['usgs_partial_'+row.station_id+'|'+row.station_id],'partial_target_year':int(row.year),'partial_natural_missing':[False]*n,
      'actual_complete_training_years':int(row.complete_history_years)}
 core=engine.adapted_generator(target/'cache');result=core.station_cases(job,settings,generator,[],resume=False)
 if not result.get('cache'):raise RuntimeError('Case generation unavailable: '+str(result))
 cases=pd.read_parquet(result['cache'])
 if len(cases)!=18 or set(cases.year)!={int(row.year)} or not cases.design_family.eq('crossed').all() or not cases.n_complete_years.eq(int(row.complete_history_years)).all():raise ValueError('Case roster changed')
 c=cases.drop(columns=[x for x in cases if x.startswith('eval_')],errors='ignore').copy()
 if 'h30__policy' not in c:c['h30__policy']=np.nan
 if 'observed_lower_bound__observed_days' not in c:c['observed_lower_bound__observed_days']=np.nan
 pred=inference.classical_predictions(inference.predict(c,bundle),cal)
 if any(x.startswith('eval_') for x in pred):raise ValueError('Target outcome entered inference table')
 out=target/'predictions.parquet';pred.to_parquet(out,index=False);receipt={'station_id':row.station_id,'year':int(row.year),'history':details,'actual_complete_history_years':int(row.complete_history_years),'cases':len(pred),'target_outcome_fields_removed':True}
 (target/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

def main():
 a=argparse.ArgumentParser();a.add_argument('--station-id');a.add_argument('--year',type=int);args=a.parse_args();plan=verify()
 roster=pd.read_csv(PRIVATE/'continuous_target_roster.csv',dtype={'station_id':str});chosen=roster.copy()
 if args.station_id:chosen=chosen[chosen.station_id.eq(args.station_id)]
 if args.year:chosen=chosen[chosen.year.eq(args.year)]
 if chosen.empty:raise ValueError('No frozen cases selected')
 helper=T.load_script('usgs_partial_reference_parser',ROOT/'scripts/871_usgs_partial_daily_feasibility.py');engine=T.load_script('usgs_partial_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usgs_partial_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
 settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usgs_partial_daily_posthoc_20261027';settings['calendar_year_only']=True
 gen=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text())
 if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('Source calibration differs')
 bundle['offsets']=cal['D2_offsets'];indices=position_index(['usgs_partial_'+x+'|'+x for x in sorted(roster.station_id.unique())]);stage=STAGE/'predictions';stage.mkdir(exist_ok=True)
 for n,row in enumerate(chosen.itertuples(index=False),1):
  d=stage/row.station_id/str(row.year);receipt=d/'receipt.json'
  if receipt.exists():
   x=json.loads(receipt.read_text())
   print('Verified target',n,'of',len(chosen),flush=True);continue
  if d.exists() and any(d.iterdir()):raise FileExistsError('Preserve unreceipted partial target')
  daily=helper.valid_daily(pd.read_parquet(DATA/'daily'/(row.station_id+'.parquet')));x=make_one(row,daily,settings,gen,bundle,cal,engine,inference,indices,stage)
  print('Generated target',n,'of',len(chosen),'cases',x['cases'],flush=True)
 receipts=list(stage.glob('*/*/receipt.json'))
 if len(receipts)==len(roster):
  s={'status':'predictions_complete_not_scored','sites':int(roster.station_id.nunique()),'target_years':len(roster),'cases':sum(json.loads(f.read_text())['cases'] for f in receipts),
     'target_truth_or_error_scored':False,'source_model_refitted_on_target':False,'limitations':plan['limitations'],'storage':'temporary RAM filesystem; not durable'}
  (STAGE/'predictions_status.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s,indent=2))
if __name__=='__main__':main()
