#!/usr/bin/env python3
"""Re-evaluate HUC17 stress scenarios with the stricter forward source model."""
from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
os.umask(0o077)
import argparse
import json
import importlib.metadata
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'strict_region_holdout';PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
STUDIES={'synchronized_donors':REV/'scenario_donors/pilot_7','heat_associated':REV/'scenario_heat/pilot_7'}
KEY=['family','mode','station_key','replicate','estimator','retention','dependence']

def require_matching_inputs(receipt, expected):
 if receipt.get('inputs')!=expected:raise ValueError('strict scenario cached input dependencies differ')

def work(scenario,job,ref,family,rep,cal,common_inputs):
 original=STUDIES[scenario]/family/'forward'/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')
 root=PRIVATE/'scenario_sensitivity_v3'/scenario;target=root/family/'forward'/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')
 source=original/'annual_predictions.parquet';design=original/'design.json';target.mkdir(parents=True,exist_ok=True,mode=0o700)
 receipt=target/'strict_receipt.json';staged=target/'annual_predictions.parquet'
 inputs=common_inputs|{'scenario':scenario,'family':family,'replicate':rep,}
 if receipt.exists():
  r=json.loads(receipt.read_text());require_matching_inputs(r,inputs)
  return str(target)
 if staged.exists():
  pass
 else:shutil.copyfile(source,staged);staged.chmod(0o600)
 module=T.load_script('strict_scenario_worker',ROOT/'scripts/521_whole_archive.py');module.SOURCE=PRIVATE
 module.one(job,ref,rep,'forward',family,cal,root,256,False,True,scenario)
 a=json.loads(design.read_text());b=json.loads((target/'design.json').read_text())
 if a['masks']!=b['masks'] or a['station_key']!=b['station_key'] or b['hidden_values_present_in_visible_archive']!=0:raise ValueError('strict scenario changed masks or exposed hidden values')
 if scenario=='synchronized_donors' and b['hidden_donor_values_present']!=0:raise ValueError('strict donor masks expose observations')
 receipt.write_text(json.dumps({'inputs':inputs,'same_masks':True,'hidden_target_values':0,'hidden_donor_values':b['hidden_donor_values_present']},indent=2)+'\n')
 return str(target)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=2);parser.add_argument('--limit',type=int);args=parser.parse_args()
 source=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',columns=['station_key','region','independence_group','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
 matched=pd.read_csv(REV/'scenarios/matched_trends.csv'); affected=matched.loc[matched['mode'].eq('forward')&matched.region_baseline.eq('usgs_huc17')]
 stations=affected.station_key.unique()
 if len(stations)!=1:raise ValueError('unexpected affected stress-station roster')
 core=T.load_script('strict_scenario_jobs',ROOT/'scripts/431_tr_cases.py');jobs=[j for j in core.jobs_for('source') if j['station_key'] in stations]
 if len(jobs)!=1:raise ValueError('affected station not uniquely located')
 calpath=PRIVATE/'strict_archive_calibration.json';cal=json.loads(calpath.read_text())
 modelpath=PRIVATE/'refits/before_2010/seed_00/usgs_huc17.joblib'
 receipt=json.loads((PRIVATE/'refit_receipts.json').read_text())['usgs_huc17']
 codepaths=[ROOT/'scripts'/p for p in ['621_strict_region_scenario_sensitivity.py','521_whole_archive.py','495_review_completion_independent_analysis.py','431_tr_cases.py','wrr_tr_common.py']]
 codepaths+=sorted((ROOT/'scripts').glob('wrr*.py'))
 codepaths+=sorted((ROOT/'src').rglob('*.py'))
 for path in sorted(codepaths):codehash.update(str(path.relative_to(ROOT)).encode()+b'\0'+bytes.fromhex())
 refpath=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
 common_inputs={'job':jobs[0],
   'package_versions':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-learn','lightgbm','joblib']}}
 tasks=[(scenario,jobs[0],source.loc[source.station_key.eq(stations[0])&source.design_family.eq(family)],family,rep,cal,common_inputs)
        for scenario in STUDIES for family in ['calendar','crossed'] for rep in range(5)]
 if args.limit is not None:tasks=tasks[:args.limit]
 print('Reanalyzing affected stress settings:',len(tasks),flush=True)
 paths=Parallel(n_jobs=args.workers,verbose=10)(delayed(work)(*t) for t in tasks)
 old_stress=[];new_stress=[];old_base=[];new_base=[]
 for task,path in zip(tasks,paths):
  scenario,job,ref,family,rep,_,_=task;rel=Path(family)/'forward'/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')
  for seq,p in [(old_stress,STUDIES[scenario]/rel/'trends.csv'),(new_stress,Path(path)/'trends.csv'),(old_base,REV/'whole_archive'/rel/'trends.csv'),(new_base,PRIVATE/'whole_archive'/rel/'trends.csv')]:
   t=pd.read_csv(p);t['scenario_comparison']=scenario;seq.append(t)
 frames=[pd.concat(x,ignore_index=True) for x in [old_base,new_base,old_stress,new_stress]]
 keys=['scenario_comparison']+KEY
 joined=frames[0].merge(frames[1],on=keys,suffixes=('_baseline_original','_baseline_strict'),validate='one_to_one')
 joined=joined.merge(frames[2],on=keys,validate='one_to_one').rename(columns={c:c+'_stress_original' for c in frames[2].columns if c not in keys})
 last=frames[3].rename(columns={c:c+'_stress_strict' for c in frames[3].columns if c not in keys})
 joined=joined.merge(last,on=keys,validate='one_to_one')
 if len(joined)!=sum(len(x) for x in old_base):raise ValueError('scenario keys differ')
 for metric in ['truth_slope','n_years']:
  arr=[joined[metric+'_'+k] for k in ['baseline_original','baseline_strict','stress_original','stress_strict']]
  for item in arr[1:]:
   if not np.allclose(arr[0],item,atol=1e-8,rtol=0,equal_nan=True):raise ValueError('scenario target truth differs')
 plug=joined.loc[joined.estimator.eq('plug_in')&joined.dependence.eq('point')]
 for side in ['baseline','stress']:
  if not np.allclose(plug['error_'+side+'_original'],plug['error_'+side+'_strict'],atol=1e-8,rtol=0,equal_nan=True):raise ValueError('unchanged plug-in predictions differ')
 if args.limit is not None:
  print('Pilot completed',len(paths),'settings and',len(joined),'paired rows');return
 # Replace only affected HUC17 rows in the archived all-station matched table.
 old=matched.loc[matched['mode'].eq('forward')].copy();old['scenario_comparison']=old.scenario
 replay=old.loc[old.region_baseline.eq('usgs_huc17')].merge(joined,on=keys,how='outer',suffixes=('_saved','_replayed'),indicator=True,validate='one_to_one')
 if not replay._merge.eq('both').all():raise ValueError('saved affected scenario keys differ from original outputs')
 for side in ['baseline','stress']:
  if not replay['available_'+side].eq(replay['available_'+side+'_original']).all():raise ValueError('saved scenario availability does not reproduce')
  for metric in ['squared_error','truth_slope','n_incomplete']:
   if not np.allclose(replay[metric+'_'+side],replay[metric+'_'+side+'_original'],atol=1e-8,rtol=0,equal_nan=True):raise ValueError('saved scenario metrics do not reproduce: '+metric)
 update=joined[keys+['squared_error_baseline_strict','squared_error_stress_strict','available_baseline_strict','available_stress_strict']]
 pooled=old.merge(update,on=keys,how='left',validate='one_to_one',indicator=True)
 flag=pooled.region_baseline.eq('usgs_huc17')
 if not pooled.loc[flag,'_merge'].eq('both').all() or not pooled.loc[~flag,'_merge'].eq('left_only').all():raise ValueError('scenario replacement scope differs')
 for name in ['squared_error','available']:
  for side in ['baseline','stress']:
   pooled[name+'_'+side+'_strict']=pooled[name+'_'+side].where(~flag,pooled[name+'_'+side+'_strict'])
 rows=[]
 for values,g in pooled.groupby(['scenario_comparison','family','estimator','retention','dependence'],sort=True):
  valid=g.available_baseline&g.available_stress&g.available_baseline_strict&g.available_stress_strict
  x=g.loc[valid];row=dict(zip(['scenario','family','estimator','retention','dependence'],values))
  row.update(n_eligible=len(g),n_common=len(x),n_stations=x.station_key.nunique(),n_groups=x.independence_group_baseline.nunique())
  for side in ['baseline','stress']:
   for ver in ['original','strict']:
    col='squared_error_'+side+('' if ver=='original' else '_strict')
    row[ver+'_'+side+'_rmse']=float(np.sqrt(pd.to_numeric(x[col],errors='coerce').mean())) if len(x) else np.nan
  rows.append(row)
 summary=pd.DataFrame(rows);summary.to_csv(OUT/'scenario_paired_sensitivity.csv',index=False)
 status={'status':'passed','strict_scenario_settings':len(paths),'affected_stations':len(stations),'paired_trend_rows':len(joined),
  'source_model_calibration_data_and_code_bound_to_receipts':True,'original_scenario_case_metrics_reproduced':True,'same_masks_hidden_target_checked':True,'synchronized_hidden_donors_checked':True,'unchanged_plugin_checked':True,
  'scope':'both forward scenario families, five masks; one affected HUC17 station; other original sites retained; compare both source versions on four-way common baseline/stress cases',
  'limitation':'post-hoc exploratory sensitivity; seven stations are not independent climates, and heat-associated missingness also changes masks and rates; this is not a causal attribution or group-safety guarantee'}
 (OUT/'scenario_sensitivity_status.json').write_text(json.dumps(status,indent=2)+'\n')
 print(summary.query("family == 'crossed' and estimator == 'D2' and retention == 'all' and dependence == 'point'").to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
