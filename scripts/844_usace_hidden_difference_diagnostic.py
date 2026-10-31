#!/usr/bin/env python3
"""Separate repeatability, placeholder and hidden-value effects for failed probe."""
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
    runner=T.load_script('usace_diag_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    failure=json.loads((OUT/'partial_history_hidden_all_status.json').read_text())
    if failure['status']!='failed_pending_investigation':raise ValueError('No recorded probe failure')
    path=OUT/'partial_history_hidden_difference_plan.json'
    if path.exists():raise FileExistsError('Preserve diagnostic plan')
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv').sort_values(['resource_id','year']);row=roster.iloc[failure['failed_target_order']-1]
    pred=PRIVATE/'partial_history_predictions'/row.resource_id/str(int(row.year))/'predictions.parquet'
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc diagnostic after observing all-target probe failure',
      'target_rule':'The first failed target, as recorded by the fixed all-target first-mask probe; use its first saved mask.',
      'conditions':['repeat unchanged input','change natural-gap placeholders only','perturb observed hidden target days only','both changes'],
      'perturbation':'Add 10 C to finite target days hidden by the first mask; replace natural-gap placeholders with 432.1 C where applicable.',
      'measure':'Compare regenerated features and all 17 output columns against saved and repeated unchanged runs; inspect LightGBM branch differences when output differs. No target error calculation.',
      'limitations':'After-the-fact diagnosis of one failing mask; even a repeatability explanation would not validate all target masks or fix the scientific distribution shift.',
      'resource_id':row.resource_id,'year':int(row.year),}
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen failed-probe repeatability diagnostic')

def run():
    runner=T.load_script('usace_diag_runner2',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    p=json.loads((OUT/'partial_history_hidden_difference_plan.json').read_text());base=PRIVATE/'partial_history_predictions'/p['resource_id']/str(p['year'])/'predictions.parquet'
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');row=next(roster[(roster.resource_id==p['resource_id'])&(roster.year==p['year'])].itertuples(index=False))
    saved=pd.read_parquet(base);first=saved.iloc[0];dates=pd.date_range(f"{p['year']}-01-01",f"{p['year']}-12-31");mask=np.zeros(len(dates),dtype=bool)
    for item in first.mask_runs.split(';'):
        start,length=map(int,item.split(':'));mask[start:start+length]=True
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day);modified=daily.copy()
    selected=modified.resource_id.eq(p['resource_id'])&modified.day.isin(set(dates[mask]));n=int(selected.sum());modified.loc[selected,'mean_c']+=10
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usace_partial_history_posthoc_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    engine=T.load_script('usace_diag_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usace_diag_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usace_diag_features',ROOT/'scripts/wrr_tr_features.py')
    indices=position_index(['usace_'+x+'|'+x for x in sorted(roster.resource_id.unique())]);outputs={}
    cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{q:02d}' for q in (5,10,25,50,75,90,95)]
    with tempfile.TemporaryDirectory(prefix='usace_hidden_diagnostic_') as temp:
        for condition,source,placeholder in [('unchanged',daily,0.),('placeholder_only',daily,432.1),('hidden_only',modified,0.),('both',modified,432.1)]:
            stage=Path(temp)/condition;runner.make_one(row,source,settings,generator,bundle,cal,engine,inference,indices,stage,placeholder=placeholder)
            table=pd.read_parquet(stage/row.resource_id/str(row.year)/'predictions.parquet');same=table.loc[table.realization_id.eq(first.realization_id)]
            if len(same)!=1 or same.iloc[0].mask_runs!=first.mask_runs:raise AssertionError('Diagnostic mask changed')
            outputs[condition]=(same,features.design_matrix(same,simulation=True).reindex(columns=bundle['features']).to_numpy())
        saved_features=features.design_matrix(saved.iloc[[0]],simulation=True).reindex(columns=bundle['features']).to_numpy()
        saved_output=saved.iloc[[0]][cols].to_numpy(float)
        records={}
        for name,(table,x) in outputs.items():
            output=table[cols].to_numpy(float);delta=output-saved_output;fdelta=x-saved_features
            records[name]={'max_abs_feature_difference':float(np.nanmax(np.abs(fdelta))),
              'max_abs_output_difference':float(np.nanmax(np.abs(delta))),
              'changed_outputs':{cols[i]:float(delta[0,i]) for i in range(len(cols)) if np.isfinite(delta[0,i]) and abs(delta[0,i])>1e-10}}
        # Distinguish threshold discontinuity from material feature change by
        # testing the same quantile models on each regenerated feature vector.
        x0=outputs['unchanged'][1];x1=outputs['both'][1]
        model_delta=[float(model.predict(x1)[0]-model.predict(x0)[0]) for model in bundle['quantile_models']]
    result={'status':'completed_diagnostic','target_years':1,'observed_hidden_days_perturbed':n,'conditions':records,
            'raw_quantile_model_prediction_differences_both_vs_unchanged_c':model_delta,
            'interpretation':'Exact outputs and near-identical features must be judged from the recorded controls; this diagnostic alone does not prove or disprove leakage.',
            'limitations':p['limitations']}
    (OUT/'partial_history_hidden_difference_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
