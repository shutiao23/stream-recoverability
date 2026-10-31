#!/usr/bin/env python3
"""Probe hidden-value noninterference for two selected NS masked cases.

The probes are diagnostic and selected after scoring, not exhaustive evidence
of no leakage in all cases, models, data paths or future settings.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import position_index

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
SOURCE=ROOT/'results/wrr_review_completion_20261024'
PRIVATE=ROOT/'private/wrr_nova_scotia_exploratory_20261026'
LEVELS=[5,10,25,50,75,90,95]

def max_difference(a,b):
    x=np.asarray(a,float);y=np.asarray(b,float)
    if x.shape!=y.shape or not np.array_equal(np.isfinite(x),np.isfinite(y)):
        raise ValueError('probe changed missingness or shape')
    finite=np.isfinite(x)
    return float(np.max(np.abs(x[finite]-y[finite]))) if finite.any() else 0.

def main():
    status=json.loads((OUT/'score_status.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    if status['status']!='exploratory_scored':raise RuntimeError('base experiment was not scored')
    inputs=json.loads((PRIVATE/'score_inputs.json').read_text());cal_lock=json.loads((OUT/'source_calibration_lock.json').read_text())
    settings_path=SOURCE/'independent_study/source_case_settings.json';generator_path=SOURCE/'independent_study/source_missingness_generator.json'
    model=ROOT/plan['source_model'];calpath=ROOT/cal_lock['calibration_path'];air=OUT/'air_forcing.parquet'
    roster=pd.read_csv(OUT/'reference_year_roster.csv',dtype={'station_id':str})
    base=pd.read_parquet(PRIVATE/'predictions.parquet')
    settings=json.loads(settings_path.read_text());settings['version']='review_ns_reported_clock_exploratory_20261026';settings['calendar_year_only']=True
    generator=json.loads(generator_path.read_text())
    indices=position_index(f'ns_{site}|{site}' for site in roster.station_id.unique())
    core=T.load_script('ns_probe_cases',ROOT/'scripts/431_tr_cases.py')
    inference=T.load_script('ns_probe_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    bundle=joblib.load(model);cal=json.loads(calpath.read_text());bundle['offsets']=cal['D2_offsets']
    checks=[]
    for site,g in roster.groupby('station_id',sort=True):
        available=base.loc[base.station_id.eq(site)&base.gap_length.eq(90)&base.eval_true_peak_hidden_fraction.gt(0)].copy()
        if available.empty:raise ValueError(f'no eligible 90-day diagnostic probe for {site}')
        # This is an after-the-fact leakage stress selection, not a predictive feature.
        chosen=available.sort_values(['eval_true_peak_hidden_fraction','year','realization_id'],ascending=[False,True,True]).iloc[0]
        panel_path=OUT/'panels'/f'{site}.csv'
        panel=pd.read_csv(panel_path,parse_dates=['date']).set_index('date').sort_index()
        year=int(chosen.year);idx=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left')
        mask=np.zeros(len(idx),bool)
        for run in str(chosen.mask_runs).split(';'):
            start,length=map(int,run.split(':'))
            if start<0 or length<=0 or start+length>len(idx) or mask[start:start+length].any():raise ValueError('invalid diagnostic mask')
            mask[start:start+length]=True
        if int(mask.sum())!=int(chosen.total_missing):raise ValueError('mask length mismatch')
        perturbed=panel.copy();days=idx[mask]
        if not np.isfinite(perturbed.loc[days,site].to_numpy(float)).all():raise ValueError('hidden days not finite')
        perturbed.loc[days,site]+=5.
        visible_idx=panel.index.difference(days)
        if not np.array_equal(panel.loc[visible_idx,site],perturbed.loc[visible_idx,site],equal_nan=True):raise ValueError('visible input changed')
        with TemporaryDirectory(prefix='ns_hidden_probe_',dir=PRIVATE) as tmp:
            tmp=Path(tmp);generated={}
            for variant,panel_data in [('control',panel),('perturbed',perturbed)]:
                path=tmp/f'{variant}.csv';panel_data.to_csv(path,index_label='date')
                job={'network_id':'ns_'+site,'station_id':site,'station_key':'ns_exploratory|'+site,
                  'provider':'ns_exploratory','independence_group':'nova_scotia_shared_climate','latitude':float(g.iloc[0].latitude),
                  'input_path':str(path),'air_input_path':str(air),'statistic_class':'reported_clock_24_hour_mean_QC_unknown',
                  'regulation_status':'unknown','region':'nova_scotia','roster':'independent',
                  'station_index':indices[f'ns_{site}|{site}']}
                core.CACHE=tmp/variant/'cache';result=core.station_cases(job,settings,generator,[],resume=False)
                if not result.get('cache'):raise RuntimeError(f'probe case generation unavailable: {site}/{variant}')
                altered=pd.read_parquet(result['cache'])
                matched=altered.loc[altered.year.eq(year)&altered.design_family.eq(chosen.design_family)
                   &altered.realization_id.eq(chosen.realization_id)&altered.mask_runs.eq(chosen.mask_runs)]
                if len(matched)!=1:raise ValueError('probe mask or case identity changed')
                generated[variant]=matched
        original=base.loc[[chosen.name]].copy();control=generated['control'];matched=generated['perturbed']
        x=F.design_matrix(control,simulation=True).reindex(columns=bundle['features'])
        z=F.design_matrix(matched,simulation=True).reindex(columns=bundle['features'])
        reference_x=F.design_matrix(original,simulation=True).reindex(columns=bundle['features'])
        feature_diff=max_difference(x.to_numpy(),z.to_numpy());replay_feature_diff=max_difference(reference_x.to_numpy(),x.to_numpy())
        control_pred=inference.classical_predictions(inference.predict(control,bundle),cal)
        new=inference.classical_predictions(inference.predict(matched,bundle),cal)
        columns=['h30__policy','observed_lower_bound__observed_days','D2','risk_score']+[f'{name}_q{q:02d}' for name in ['D2','stochastic_cal'] for q in LEVELS]
        prediction_diff=max_difference(control_pred[columns].to_numpy(),new[columns].to_numpy())
        replay_prediction_diff=max_difference(original[columns].to_numpy(),control_pred[columns].to_numpy())
        truth_change=abs(float(matched.eval_truth_h30.iloc[0])-float(control.eval_truth_h30.iloc[0]))
        if replay_feature_diff>1e-7 or replay_prediction_diff>1e-8:
            raise ValueError(f'control replay differs materially: feature={replay_feature_diff}, prediction={replay_prediction_diff}')
        if feature_diff>1e-9 or prediction_diff>1e-9 or truth_change<=1e-8:
            fdelta=np.abs(x.to_numpy(float)-z.to_numpy(float))[0]
            pdelta=np.abs(control_pred[columns].to_numpy(float)-new[columns].to_numpy(float))[0]
            changed_features=[str(x.columns[i]) for i in np.flatnonzero(np.nan_to_num(fdelta,nan=0)>1e-9)]
            changed_predictions=[columns[i] for i in np.flatnonzero(np.nan_to_num(pdelta,nan=0)>1e-9)]
            raise ValueError(f'probe failed: feature_max={feature_diff}, prediction_max={prediction_diff}, truth_change={truth_change}, '
                             f'changed_features={changed_features}, changed_predictions={changed_predictions}')
        checks.append({'station_id':site,'year':year,'hidden_days_perturbed':int(mask.sum()),
                       'true_h30_change_c':truth_change,'max_feature_difference':feature_diff,
                       'max_prediction_difference':prediction_diff,'control_replay_feature_difference':replay_feature_diff,
                       'control_replay_prediction_difference':replay_prediction_diff,'passed':True})
        print('Passed hidden-value perturbation probe for',site,flush=True)
    report={'status':'passed','probes':len(checks),'all_truths_changed':all(x['true_h30_change_c']>1e-8 for x in checks),
            'max_feature_difference':max(x['max_feature_difference'] for x in checks),
            'max_prediction_difference':max(x['max_prediction_difference'] for x in checks),
            'max_control_replay_feature_difference':max(x['control_replay_feature_difference'] for x in checks),
            'max_control_replay_prediction_difference':max(x['control_replay_prediction_difference'] for x in checks),
            'selection':'one 90-day case per site, post-hoc chosen for largest fraction of the reference peak hidden; compare identically serialized control and input with +5 C only on masked daily values',
            'limitation':'two selected cases on one source path, not an exhaustive leakage proof; reference QC, time basis and climate independence remain unresolved'}
    (OUT/'hidden_value_probe.json').write_text(json.dumps(report,indent=2)+'\n')
    (PRIVATE/'hidden_value_probe_details.json').write_text(json.dumps(checks,indent=2)+'\n');(PRIVATE/'hidden_value_probe_details.json').chmod(0o600)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
