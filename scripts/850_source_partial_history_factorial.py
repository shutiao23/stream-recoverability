#!/usr/bin/env python3
"""Paired source experiment: local history degradation versus count feature."""
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

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'source_partial_history_factorial'
PRIVATE=ROOT/'private/wrr_source_partial_history_factorial_20261027';OPEN=REV/'open_observed_record_snapshot'
SOURCE=ROOT/'results/wrr_review_completion_20261024';MODELS=ROOT/'private/wrr_open_source_sensitivity_20261026'

def verify():
    plan=json.loads((OUT/'plan.json').read_text())
    return plan

def fixed_designs(support,seed,lengths,replicates):
    if list(lengths)!=[30,60,90]:raise ValueError('Unexpected lengths')
    designs=[]
    for length in lengths:
        for name,start in [('spring',75),('summer',165),('autumn',255)]:
            mask=np.zeros(len(support),dtype=bool)
            if start+length>len(mask):raise ValueError('Target mask crosses calendar year')
            mask[start:start+length]=True
            designs.append({'family':'crossed','key':f'fixed_{length}_{name}','length':int(length),
                            'overlap_class':name,'mask':mask,'source':''})
    return designs

def panel_for(daily,row,history_mode):
    x=daily.loc[daily.station_key.eq(row.station_key)].set_index('date').water_c
    if x.index.has_duplicates:raise ValueError('Duplicate source date')
    dates=pd.date_range('2009-01-01','2017-12-31');original=x.reindex(dates).astype(float)
    if not np.isfinite(original).all():raise ValueError('Source cohort incomplete')
    out=original.copy();masked=0
    if history_mode=='partial':
        for year in range(2009,2017):
            block=out.loc[out.index.year==year].copy();gap=(block.index.month==7)&(block.index.day<=30)
            masked+=int(gap.sum());block.loc[gap]=np.nan;out.loc[block.index]=block.interpolate(method='time',limit_area='inside')
        if masked!=8*30 or out.isna().any():raise ValueError('Unexpected history mask or interpolation')
    return pd.DataFrame({'date':dates,row.station_id:out.to_numpy()}),masked

def run_station(row,daily,settings,generator,engine,inference,indices,stage):
    path=MODELS/'refits/leave_one_year_out/seed_00'/f'{row.provider}.joblib'
    calpath=MODELS/'calibrations/offline'/f'{row.provider}.json';bundle=joblib.load(path);cal=json.loads(calpath.read_text())
    if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('Calibration role mismatch')
    if any(row.independence_group in x for x in bundle['roles'].values()):raise ValueError('Held source group appears in model role')
    bundle['offsets']=cal['D2_offsets'];results=[]
    for mode in ['full','partial']:
        dest=stage/row.station_key.replace('|','_')/mode;dest.mkdir(parents=True,exist_ok=True,mode=0o700)
        panel,masked=panel_for(daily,row,mode);panel_path=dest/'panel.csv';panel.to_csv(panel_path,index=False)
        job={'network_id':row.network_id,'station_id':row.station_id,'station_key':row.station_key,'provider':row.provider,
          'independence_group':row.independence_group,'latitude':float(row.latitude),'input_path':str(panel_path),
          'air_input_path':str(OUT/'air_snapshot.parquet'),'statistic_class':'source_processed_daily','regulation_status':'unknown_or_managed',
          'region':row.provider,'roster':'source_partial_factorial','station_index':indices[row.station_key],
          'partial_target_year':2017,'partial_natural_missing':[False]*365,'actual_complete_training_years':8 if mode=='full' else 0}
        core=engine.adapted_generator(dest/'case_cache');core.crossed_designs=fixed_designs
        result=core.station_cases(job,settings,generator,[],resume=False)
        if not result.get('cache'):raise RuntimeError('Case creation unavailable: '+str(result))
        cases=pd.read_parquet(result['cache'])
        cases=cases.drop(columns=[x for x in cases if x.startswith('eval_')],errors='ignore')
        if len(cases)!=9 or cases.year.nunique()!=1 or int(cases.year.iloc[0])!=2017:raise ValueError('Incorrect case roster')
        actual_count=8 if mode=='full' else 0
        if not cases.n_complete_years.eq(actual_count).all():raise ValueError('Incorrect actual history count')
        if 'h30__policy' not in cases:cases['h30__policy']=np.nan
        for feature_count in [0,8]:
            case=cases.copy();case['n_complete_years']=feature_count
            predicted=inference.classical_predictions(inference.predict(case,bundle),cal)
            predicted['history_mode']=mode;predicted['counterfactual_complete_count']=feature_count
            predicted['actual_complete_training_years']=actual_count;predicted['history_masked_days']=masked
            results.append(predicted)
    out=pd.concat(results,ignore_index=True)
    if out.duplicated(['station_key','realization_id','history_mode','counterfactual_complete_count']).any():raise ValueError('Duplicate factorial case')
    return out

def main():
    a=argparse.ArgumentParser();a.add_argument('--station-key');x=a.parse_args();plan=verify()
    roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str});selected=roster if x.station_key is None else roster[roster.station_key.eq(x.station_key)]
    if selected.empty:raise ValueError('Station not in cohort')
    daily=pd.read_parquet(OPEN/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='source_partial_factorial_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text())
    engine=T.load_script('source_partial_factorial_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('source_partial_factorial_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    indices=position_index(sorted(roster.station_key.tolist()));PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    stage=PRIVATE/'cases';stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    for n,row in enumerate(selected.itertuples(index=False),1):
        dest=stage/(row.station_key.replace('|','_')+'.parquet');receipt=dest.with_suffix('.json')
        if receipt.exists():
            print('Verified fixed station',n,'of',len(selected),flush=True);continue
        if dest.exists():raise FileExistsError('Preserve unreceipted output')
        result=run_station(row,daily,settings,generator,engine,inference,indices,stage);result.to_parquet(dest,index=False);dest.chmod(0o600)
        receipt.write_text(json.dumps({'rows':len(result),'station_key':row.station_key},indent=2)+'\n');receipt.chmod(0o600)
        print('Generated station',n,'of',len(selected),'rows',len(result),flush=True)
    receipts=list(stage.glob('*.json'))
    if len(receipts)==len(roster):
        result={'status':'factorial_predictions_complete_not_scored','stations':len(roster),'groups':roster.independence_group.nunique(),
          'rows':sum(json.loads(p.read_text())['rows'] for p in receipts),'scored':False,'limitations':plan['limitations']}
        (OUT/'prediction_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
