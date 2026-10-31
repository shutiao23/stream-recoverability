#!/usr/bin/env python3
"""Generate exploratory partial-history predictions without scoring targets."""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import position_index

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'
SOURCE=ROOT/'results/wrr_review_completion_20261024';POWER=DATA/'partial_history_power'

def verified():
    p=json.loads((OUT/'partial_history_evaluation_plan.json').read_text());roster=PRIVATE/'partial_history_roster.csv'
    forcing=json.loads((OUT/'partial_history_forcing_status.json').read_text())
    if forcing['status']!='completed':
        raise ValueError('Frozen cohort weather unavailable or changed')
    return p

def make_one(row,daily,settings,generator,bundle,cal,engine,inference,station_indices,stage,placeholder=0.):
    rid=row.resource_id;year=int(row.year);hist=[int(x) for x in row.history_years.split(';')]
    panel,natural,details=engine.prepare_panel(daily,rid,year,hist,placeholder)
    target=stage/rid/str(year);target.mkdir(parents=True,exist_ok=True,mode=0o700)
    panel_path=target/'panel.csv';panel.to_csv(panel_path,index=False);panel_path.chmod(0o600)
    job={'network_id':'usace_'+rid,'station_id':rid,'station_key':'usace_partial|'+rid,
         'provider':'usace_reservoir','independence_group':'unknown_'+rid,'latitude':float(row.latitude),
         'input_path':str(panel_path),'air_input_path':str(POWER/'daily_air.parquet'),
         'statistic_class':'level1_qaqc_fixed_mst_partial_daily_history_interpolated','regulation_status':'reservoir_related',
         'region':'usace_reservoir','roster':'partial_exploratory','station_index':station_indices['usace_'+rid+'|'+rid],
         'partial_target_year':year,'partial_natural_missing':natural.tolist(),
         'actual_complete_training_years':int(row.actual_complete_history_years)}
    core=engine.adapted_generator(target/'case_cache')
    result=core.station_cases(job,settings,generator,[],resume=False)
    if not result.get('cache'):raise RuntimeError('Case generation failed: '+str(result))
    cases=pd.read_parquet(result['cache'])
    if cases.empty or set(cases.year)!= {year} or not cases.design_family.eq('crossed').all() or not cases.n_complete_years.eq(row.actual_complete_history_years).all():
        raise ValueError('Wrong target year, design or actual history count')
    for runs in cases.mask_runs:
        hidden=np.zeros(len(natural),dtype=bool)
        for run in runs.split(';'):
            if run:
                start,length=map(int,run.split(':'));hidden[start:start+length]=True
        if np.any(natural&~hidden):raise ValueError('Natural target gap exposed')
    # All fields explicitly labelled as outcome-derived are excluded before inference.
    c=cases.drop(columns=[x for x in cases if x.startswith('eval_')],errors='ignore').copy()
    if 'h30__policy' not in c:c['h30__policy']=np.nan
    if 'observed_lower_bound__observed_days' not in c:c['observed_lower_bound__observed_days']=np.nan
    predictions=inference.classical_predictions(inference.predict(c,bundle),cal)
    if any(col.startswith('eval_') for col in predictions):raise ValueError('Target truth leaked into inference table')
    path=target/'predictions.parquet';predictions.to_parquet(path,index=False);path.chmod(0o600)
    info={'resource_id':rid,'year':year,'history':details,'natural_missing_days':int(natural.sum()),
          'actual_complete_training_years':int(row.actual_complete_history_years),'cases':len(cases),
          'natural_missing_all_hidden':True,
          'no_outcome_columns_before_prediction':True}
    receipt=target/'receipt.json';receipt.write_text(json.dumps(info,indent=2)+'\n');receipt.chmod(0o600)
    return info

def main():
    a=argparse.ArgumentParser();a.add_argument('--resource');a.add_argument('--year',type=int);args=a.parse_args()
    p=verified();stage=PRIVATE/'partial_history_predictions';stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');selected=roster.copy()
    if args.resource:selected=selected[selected.resource_id.eq(args.resource)]
    if args.year:selected=selected[selected.year.eq(args.year)]
    if selected.empty:raise ValueError('No fixed target selected')
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usace_partial_history_posthoc_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text())
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib');cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text())
    if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('Source calibration roles differ')
    bundle['offsets']=cal['D2_offsets'];engine=T.load_script('usace_partial_history_engine',ROOT/'scripts/835_usace_partial_history_engine.py')
    inference=T.load_script('usace_partial_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    station_indices=position_index(['usace_'+x+'|'+x for x in sorted(roster.resource_id.unique())])
    for n,row in enumerate(selected.itertuples(index=False),1):
        dest=stage/row.resource_id/str(row.year)
        if (dest/'receipt.json').exists():
            old=json.loads((dest/'receipt.json').read_text())
            print('Verified existing target',n,'of',len(selected),flush=True);continue
        if dest.exists() and any(dest.iterdir()):raise FileExistsError('Preserve partial target output: '+str(dest))
        info=make_one(row,daily,settings,generator,bundle,cal,engine,inference,station_indices,stage)
        print('Generated fixed target',n,'of',len(selected),'cases',info['cases'],flush=True)
    receipts=list(stage.glob('*/*/receipt.json'))
    if len(receipts)==len(roster):
        result={'status':'predictions_complete_not_scored','resources':int(roster.resource_id.nunique()),'target_years':len(roster),
                'cases':sum(json.loads(x.read_text())['cases'] for x in receipts),
                'target_outcome_or_error_scored':False,'source_model_refitted_on_target':False,'limitations':p['dependencies']+' '+p['source']}
        (OUT/'partial_history_predictions_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
