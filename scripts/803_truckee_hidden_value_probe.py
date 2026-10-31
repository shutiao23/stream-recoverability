#!/usr/bin/env python3
"""Post-hoc fixed-mask hidden-value perturbation on one Truckee case."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import position_index

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';LEVELS=[5,10,25,50,75,90,95]


def max_difference(a,b):
    x=np.asarray(a,float);y=np.asarray(b,float)
    if x.shape!=y.shape or not np.array_equal(np.isfinite(x),np.isfinite(y)):raise ValueError('Changed prediction availability')
    return float(np.max(np.abs(x[np.isfinite(x)]-y[np.isfinite(y)]))) if np.isfinite(x).any() else 0.


def main():
    if (OUT/'exploratory_hidden_probe.json').exists():raise FileExistsError('Preserve prior probe')
    status=json.loads((OUT/'exploratory_score_status.json').read_text());audit=json.loads((OUT/'exploratory_score_independent_audit.json').read_text())
    if status['status']!='exploratory_scored' or audit['status']!='passed':raise ValueError('Scoring or arithmetic audit incomplete')
    score=T.load_script('truckee_probe_scoring',ROOT/'scripts/801_truckee_exploratory_score.py');score.verify_plan()
    saved=pd.read_parquet(PRIVATE/'exploratory_predictions.parquet');roster=pd.read_csv(PRIVATE/'exploratory_roster.csv');site=str(roster.station_code.iloc[0])
    pool=saved[saved.gap_length.eq(90)&saved.eval_true_peak_hidden_fraction.gt(0)]
    if pool.empty:raise ValueError('No planned 90-day hidden-peak probe')
    chosen=pool.sort_values(['eval_true_peak_hidden_fraction','year','realization_id'],ascending=[False,True,True]).iloc[0]
    panel=pd.read_csv(PRIVATE/'exploratory_panel.csv',parse_dates=['date']).set_index('date').sort_index();year=int(chosen.year)
    index=pd.date_range(f'{year}-01-01',f'{year}-12-31');mask=T.mask_from_runs(chosen.mask_runs,len(index));days=index[mask]
    altered=panel.copy()
    if not np.isfinite(altered.loc[days,site]).all():raise ValueError('Hidden days not finite')
    altered.loc[days,site]+=5
    if not np.array_equal(panel.loc[panel.index.difference(days),site],altered.loc[altered.index.difference(days),site],equal_nan=True):raise ValueError('Visible water changed')
    settings=json.loads((SOURCE/'independent_study/source_case_settings.json').read_text());settings['version']='truckee_reported_pst_exploratory_20261027';settings['calendar_year_only']=True
    generator=json.loads((SOURCE/'independent_study/source_missingness_generator.json').read_text());core=T.load_script('truckee_probe_cases',ROOT/'scripts/431_tr_cases.py')
    inference=T.load_script('truckee_probe_inference',ROOT/'scripts/495_review_completion_independent_analysis.py');bundle=joblib.load(SOURCE/'deployment/global_source_candidate.joblib')
    cal=json.loads((ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json').read_text());bundle['offsets']=cal['D2_offsets']
    with TemporaryDirectory(prefix='hidden_probe_',dir=PRIVATE) as tmp:
        root=Path(tmp);generated={}
        for variant,data in [('control',panel),('perturbed',altered)]:
            path=root/(variant+'.csv');data.to_csv(path,index_label='date')
            job={'network_id':'truckee_'+site,'station_id':site,'station_key':'truckee_exploratory|'+site,'provider':'truckee_dwr',
                 'independence_group':'truckee_shared_watershed','latitude':float(roster.latitude.iloc[0]),'input_path':str(path),
                 'air_input_path':str(PRIVATE/'exploratory_air_forcing.parquet'),'statistic_class':'reported_pst_96_finite_quarter_hours_qc_validated_flags_unknown',
                 'regulation_status':'managed_watershed','region':'truckee','roster':'independent'}
            job['station_index']=position_index([job['network_id']+'|'+site])[job['network_id']+'|'+site];core.CACHE=root/variant/'cache'
            result=core.station_cases(job,settings,generator,[],resume=False)
            if not result.get('cache'):raise ValueError('Perturbed case generation unavailable')
            f=pd.read_parquet(result['cache']);match=f[f.year.eq(year)&f.design_family.eq(chosen.design_family)&f.realization_id.eq(chosen.realization_id)&f.mask_runs.eq(chosen.mask_runs)]
            if len(match)!=1:raise ValueError('Probe mask changed after perturbation')
            generated[variant]=match
        control=generated['control'];perturbed=generated['perturbed'];original=saved.loc[[chosen.name]]
        feature=F.design_matrix(control,simulation=True).reindex(columns=bundle['features']);changed=F.design_matrix(perturbed,simulation=True).reindex(columns=bundle['features'])
        old=F.design_matrix(original,simulation=True).reindex(columns=bundle['features']);fd=max_difference(feature,changed);fr=max_difference(old,feature)
        cp=inference.classical_predictions(inference.predict(control,bundle),cal);pp=inference.classical_predictions(inference.predict(perturbed,bundle),cal)
        cols=['h30__policy','observed_lower_bound__observed_days','D2','risk_score']+[f'{name}_q{q:02d}' for name in ['D2','stochastic_cal'] for q in LEVELS]
        pdiff=max_difference(cp[cols],pp[cols]);replay=max_difference(original[cols],cp[cols]);change=abs(float(control.eval_truth_h30.iloc[0])-float(perturbed.eval_truth_h30.iloc[0]))
        if fd>1e-9 or fr>1e-7 or pdiff>1e-9 or replay>1e-8 or change<=1e-8:raise ValueError('Hidden-value perturbation failed')
    result={'status':'passed','probes':1,'hidden_days':int(mask.sum()),'truth_change_c':change,'max_feature_difference':fd,
            'max_prediction_difference':pdiff,'control_replay_feature_difference':fr,'control_replay_prediction_difference':replay,
            'selection':'After scoring, choose a 90-day case with the largest fraction of the true peak hidden; add 5 C only to masked values. Recompute case generation and compare the same mask and source-model outputs.',
            'limits':'One post-hoc probe on one station; not exhaustive evidence of no leakage in all cases, input paths, climate conditions or model fits.'}
    (OUT/'exploratory_hidden_probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
