#!/usr/bin/env python3
"""Perturb hidden target days and test unchanged BC case features/predictions.

Four chosen stress cases are probes, not proof for all possible masks, training
splits, data sets, or software paths. This reads the existing frozen source
model; it does not refit that global model or inspect unpublished labels.
"""
import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import json
import tempfile
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import position_index

ROOT=T.ROOT/'results/wrr_review_response_20261027'
OUT=ROOT/'external_bc_air2stream'
SOURCE=T.ROOT/'results/wrr_review_completion_20261024'


def main():
    orig=pd.read_parquet(OUT/'predictions.parquet')
    sites=sorted(orig.station_id.astype(str).unique())
    positions=position_index(f'bc_{s}|{s}' for s in sites)
    meta=pd.read_csv(OUT/'qualification.csv',dtype={'station_number':str}).set_index('station_number')
    jobs=[]
    for site in sites:
        r=meta.loc[site]
        jobs.append(dict(network_id='bc_'+site,station_id=site,station_key='bc_published|'+site,provider='bc_published',
                         independence_group='british_columbia',latitude=float(r.latitude),input_path=str(OUT/'panels'/f'{site}.csv'),
                         air_input_path=str(OUT/'air_forcing.parquet'),statistic_class='published_mean_min20hours',
                         regulation_status=str(r.regulation),region='british_columbia',roster='independent',
                         station_index=positions[f'bc_{site}|{site}']))
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text())
    settings['version']='hidden_value_audit'
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text())
    core=T.load_script('bc_probe_cases',T.ROOT/'scripts/431_tr_cases.py')
    inference=T.load_script('bc_probe_prediction',T.ROOT/'scripts/495_review_completion_independent_analysis.py')
    pool=core.calendar_pool('independent',jobs)
    bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((OUT/'source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    results=[]
    with tempfile.TemporaryDirectory(prefix='bc_hidden_value_audit_') as tmp:
        core.CACHE=Path(tmp)/'cache'
        for job in jobs:
            subset=orig.loc[orig.station_id.eq(job['station_id']) & orig.design_family.eq('crossed') & orig.realization_id.eq('cross_90_full_0')].sort_values('year')
            if subset.empty:raise RuntimeError(f'No fixed stress case for {job["station_id"]}')
            old=subset.iloc[[0]].copy(); rec=old.iloc[0];year=int(rec.year)
            panel=pd.read_csv(job['input_path'],parse_dates=['date']).set_index('date')
            idx=np.flatnonzero(panel.index.year==year)
            for run in str(rec.mask_runs).split(';'):
                start,length=map(int,run.split(':'))
                panel.iloc[idx[start:start+length],panel.columns.get_loc(job['station_id'])]+=5.0
            altered_path=Path(tmp)/(job['station_id']+'.csv');panel.to_csv(altered_path)
            changed_job=job | {'input_path':str(altered_path)}
            case_result=core.station_cases(changed_job,settings,generator,core.pool_for(job,pool),False)
            if not case_result.get('cache'):raise RuntimeError(f'Case generator failed: {case_result}')
            new_cases=pd.read_parquet(case_result['cache'])
            select=new_cases.loc[new_cases.year.eq(year) & new_cases.design_family.eq('crossed') & new_cases.realization_id.eq(rec.realization_id)]
            if len(select)!=1:raise RuntimeError('Altered case is absent or nonunique')
            if select.iloc[0].mask_runs!=rec.mask_runs:raise RuntimeError('Alteration changed chosen mask')
            old_features=F.design_matrix(old,simulation=True).reindex(columns=bundle['features']).to_numpy(float)
            new_features=F.design_matrix(select,simulation=True).reindex(columns=bundle['features']).to_numpy(float)
            feature_equal=np.isclose(old_features,new_features,rtol=1e-10,atol=1e-9,equal_nan=True)
            predicted=inference.classical_predictions(inference.predict(select,bundle),cal)
            cols=['D2']+[f'D2_q{i:02d}' for i in [5,10,25,50,75,90,95]]+['stochastic_cal_q50']+[f'stochastic_cal_q{i:02d}' for i in [5,10,25,75,90,95]]
            x=old[cols].to_numpy(float);y=predicted[cols].to_numpy(float)
            pred_equal=np.isclose(x,y,rtol=1e-10,atol=1e-9,equal_nan=True)
            truth_delta=float(select.iloc[0].eval_truth_h30-rec.eval_truth_h30)
            results.append(dict(station=job['station_id'],year=year,mask_runs=rec.mask_runs,hidden_added_c=5.0,
                                altered_truth_delta_c=truth_delta,features_equal=bool(feature_equal.all()),
                                predictions_equal=bool(pred_equal.all()),n_features_changed=int((~feature_equal).sum()),
                                n_prediction_fields_changed=int((~pred_equal).sum())))
    report=dict(cases=results,n_cases=len(results),passed=all(r['features_equal'] and r['predictions_equal'] and r['altered_truth_delta_c']>1 for r in results),
                limitations='Four chosen BC retrospective cases, one masked-year path; finite perturbation of hidden values only. Does not establish independence of all experiments or reference measurement quality.')
    (OUT/'hidden_value_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
