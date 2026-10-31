#!/usr/bin/env python3
"""Control repeatability while perturbing one mask in each target year."""
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
    runner=T.load_script('usace_paired_probe_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    d=json.loads((OUT/'partial_history_hidden_difference_status.json').read_text())
    if d['status']!='completed_diagnostic':raise ValueError('Failed-probe diagnosis incomplete')
    path=OUT/'partial_history_paired_hidden_plan.json'
    if path.exists():raise FileExistsError('Preserve paired probe plan')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after one all-target probe failed and unchanged-input control reproduced the same drift',
      'cohort':'All 17 fixed target years, first saved mask per year, including all four sites.',
      'comparison':'For each target regenerate an unchanged-input control and a hidden-target-plus-placeholder perturbation in the same Python process. Compare mask, all 68 source-model features, point and distribution outputs at 1e-10 absolute tolerance. Also compare unchanged-input controls with previously saved outputs to quantify repeatability; report both comparisons separately.',
      'perturbation':'Add 10 C to every finite target day hidden by the first mask and change all natural-gap placeholders from 0 to 432.1 C. Target missingness geometry and actual training history are fixed.',
      'limitations':'The first mask per target is not exhaustive. Same-process controls do not prove no hidden leakage across all implementations or guarantee cross-environment reproducibility. Scores are posthoc, out-of-support and reference bounds are conditional.',
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen paired-control hidden-value probe')

def run():
    runner=T.load_script('usace_paired_probe_runner2',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    p=json.loads((OUT/'partial_history_paired_hidden_plan.json').read_text())
    receipts=json.loads((PRIVATE/'partial_history_hidden_all_inputs.json').read_text());roster=pd.read_csv(PRIVATE/'partial_history_roster.csv').sort_values(['resource_id','year'])
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='usace_partial_history_posthoc_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    engine=T.load_script('usace_paired_probe_engine',ROOT/'scripts/835_usace_partial_history_engine.py');inference=T.load_script('usace_paired_probe_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');features=T.load_script('usace_paired_probe_features',ROOT/'scripts/wrr_tr_features.py')
    indices=position_index(['usace_'+x+'|'+x for x in sorted(roster.resource_id.unique())]);rows=[]
    cols=['h30__policy','D2','risk_score']+[f'D2_q{q:02d}' for q in (5,10,25,50,75,90,95)]+[f'stochastic_cal_q{q:02d}' for q in (5,10,25,50,75,90,95)]
    with tempfile.TemporaryDirectory(prefix='usace_paired_hidden_') as tmp:
        for n,row in enumerate(roster.itertuples(index=False),1):
            path=PRIVATE/'partial_history_predictions'/row.resource_id/str(row.year)/'predictions.parquet'
            saved=pd.read_parquet(path);first=saved.iloc[0];dates=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31');mask=np.zeros(len(dates),dtype=bool)
            for item in first.mask_runs.split(';'):
                start,length=map(int,item.split(':'));mask[start:start+length]=True
            changed=daily.copy();m=changed.resource_id.eq(row.resource_id)&changed.day.isin(set(dates[mask]));count=int(m.sum())
            if not count:raise ValueError('No hidden observed day')
            changed.loc[m,'mean_c']+=10;outputs=[]
            for label,source,placeholder in [('control',daily,0.),('perturbed',changed,432.1)]:
                stage=Path(tmp)/label;runner.make_one(row,source,settings,generator,bundle,cal,engine,inference,indices,stage,placeholder=placeholder)
                frame=pd.read_parquet(stage/row.resource_id/str(row.year)/'predictions.parquet');same=frame.loc[frame.realization_id.eq(first.realization_id)]
                if len(same)!=1 or same.iloc[0].mask_runs!=first.mask_runs:raise AssertionError('Mask changed')
                outputs.append((same,features.design_matrix(same,simulation=True).reindex(columns=bundle['features']).to_numpy()))
            c,fc=outputs[0];q,fq=outputs[1];a=c[cols].to_numpy(float);b=q[cols].to_numpy(float);old=saved.iloc[[0]][cols].to_numpy(float)
            feature_equal=bool(np.allclose(fc,fq,atol=1e-10,rtol=0,equal_nan=True));output_equal=bool(np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True))
            drift=np.abs(a-old);max_drift=float(np.nanmax(drift)) if np.isfinite(drift).any() else 0.
            changed_cols=[cols[i] for i in range(len(cols)) if np.isfinite(drift[0,i]) and drift[0,i]>1e-10]
            rows.append({'resource_id':row.resource_id,'year':row.year,'hidden_observed_days':count,'features_equal_control_perturbed':feature_equal,
                         'outputs_equal_control_perturbed':output_equal,'saved_vs_control_max_abs_difference':max_drift,'saved_vs_control_changed_columns':';'.join(changed_cols)})
            print('Paired hidden probe',n,'of',len(roster),'feature/output',feature_equal,output_equal,'saved drift',max_drift,flush=True)
    table=pd.DataFrame(rows);dest=PRIVATE/'partial_history_paired_hidden_cases.csv';table.to_csv(dest,index=False);dest.chmod(0o600)
    result={'status':'passed_paired_perturbation' if table.features_equal_control_perturbed.all() and table.outputs_equal_control_perturbed.all() else 'failed_paired_perturbation',
      'target_station_years':len(table),'target_resources':table.resource_id.nunique(),'masks_probed':len(table),
      'paired_feature_passes':int(table.features_equal_control_perturbed.sum()),'paired_output_passes':int(table.outputs_equal_control_perturbed.sum()),
      'saved_vs_unchanged_control_drift_cases':int(table.saved_vs_control_max_abs_difference.gt(1e-10).sum()),
      'saved_vs_unchanged_control_max_abs_difference':float(table.saved_vs_control_max_abs_difference.max()),
      'limitations':p['limitations']}
    (OUT/'partial_history_paired_hidden_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()
