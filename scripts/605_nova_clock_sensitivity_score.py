#!/usr/bin/env python3
"""Refit NS local cases under fixed hypothetical day-boundary shifts.

Mask realizations, global source model, source calibration and NASA forcing are
held fixed. Results are post-hoc sensitivities, not a determination of timezone
or a strict independent validation. Per-case data stay in a private directory.
"""
from __future__ import annotations
import os
for variable in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[variable]='1'
os.umask(0o077)
import argparse
import importlib.util
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from stream_recoverability.seeds import plain_seed,position_index
from stream_recoverability.experiments.tr_revision.statistics import interval_score,ensemble_crps

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_clock_sensitivity'
SOURCE=ROOT/'results/wrr_review_completion_20261024'
BASE_PRIVATE=ROOT/'private/wrr_nova_scotia_exploratory_20261026'
PRIVATE=ROOT/'private/wrr_nova_scotia_clock_sensitivity_20261026'
KEY=['station_id','year','design_family','realization_id','mask_runs']
LEVELS=[5,10,25,50,75,90,95]

def mask_from_runs(n,encoding):
    mask=np.zeros(n,bool)
    for run in str(encoding).split(';'):
        start,length=map(int,run.split(':'))
        if start<0 or length<=0 or start+length>n or mask[start:start+length].any():raise ValueError('invalid original mask')
        mask[start:start+length]=True
    return mask

def score_casewise(frame,draw):
    y=frame.eval_truth_h30.to_numpy(float);lower=frame.observed_lower_bound__observed_days.to_numpy(float)
    if np.any(np.isfinite(lower)&(y<lower-1e-8)):raise ValueError('reported reference below observation bound')
    result={}
    for method,prefix,point_col in [('D2','D2','D2'),('stochastic','stochastic_cal','stochastic_cal_q50')]:
        q=frame[[f'{prefix}_q{q:02d}' for q in LEVELS]].to_numpy(float);point=frame[point_col].to_numpy(float)
        if not (np.isfinite(y)&np.isfinite(point)&np.isfinite(q).all(axis=1)).all():raise ValueError('nonfinite predictions on common cohort')
        if np.any(np.diff(q,axis=1)<-1e-8) or np.any(np.isfinite(lower)&(q[:,0]<lower-1e-8)):
            raise ValueError('quantiles violate order or observed support')
        lo=q[:,0];hi=q[:,-1]
        result[method+'_mae']=abs(point-y)
        result[method+'_coverage90']=((y>=lo-1e-8)&(y<=hi+1e-8)).astype(float)
        result[method+'_width90']=hi-lo
        result[method+'_interval_score90']=interval_score(lo,hi,y)
        result[method+'_crps']=ensemble_crps(draw(q,lower),y)
    return pd.DataFrame(result,index=frame.index)

def main():
    import wrr_tr_common as T
    plan=json.loads((OUT/'plan.json').read_text());ref=json.loads((OUT/'reference_status.json').read_text())
    original=json.loads((BASE/'plan.json').read_text());lock=json.loads((BASE/'source_calibration_lock.json').read_text())
    base_status=json.loads((BASE/'score_status.json').read_text());base_integrity=json.loads((BASE/'integrity_status.json').read_text())
    if plan['status']!='frozen_posthoc_sensitivity' or ref['status']!='boundary_inputs_checked' or base_status['status']!='exploratory_scored' or base_integrity['status']!='passed':raise RuntimeError('base or shifted input checks incomplete')
    if (OUT/'score_status.json').exists():raise RuntimeError('existing sensitivity scoring status will not be overwritten')
    model=ROOT/original['source_model'];calpath=ROOT/lock['calibration_path'];air=BASE/'air_forcing.parquet'
    settings_path=SOURCE/'independent_study/source_case_settings.json';generator_path=SOURCE/'independent_study/source_missingness_generator.json'
    base_cases=pd.read_parquet(BASE_PRIVATE/'cases.parquet');base_pred=pd.read_parquet(BASE_PRIVATE/'predictions.parquet')
    if base_cases.duplicated(KEY).any() or base_pred.duplicated(KEY).any():raise ValueError('duplicate original case identity')
    if len(base_cases)!=base_status['cases'] or len(base_pred)!=base_status['cases']:raise ValueError('base case count mismatch')
    roster=pd.read_csv(BASE/'reference_year_roster.csv',dtype={'station_id':str})
    available=pd.read_csv(OUT/'boundary_site_availability.csv',dtype={'station_id':str})
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);PRIVATE.chmod(0o700)
    settings=json.loads(settings_path.read_text());settings['version']='review_ns_reported_clock_exploratory_20261026';settings['calendar_year_only']=True
    generator=json.loads(generator_path.read_text());indices=position_index(f'ns_{site}|{site}' for site in roster.station_id.unique())
    core=T.load_script('ns_clock_fixed_masks',ROOT/'scripts/431_tr_cases.py')
    inference=T.load_script('ns_clock_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    original_crossed=core.crossed_designs
    schedules={}
    for (site,year),g in base_cases.groupby(['station_id','year'],sort=False):
        site_index=indices[f'ns_{site}|{site}'];seed=plain_seed(0,core.CROSSED_SEED,site_index,int(year))
        if seed in schedules:raise ValueError('mask seed collision')
        n=366 if pd.Timestamp(year=int(year),month=12,day=31).is_leap_year else 365
        records=[]
        for r in g.itertuples(index=False):
            mask=mask_from_runs(n,r.mask_runs)
            if int(mask.sum())!=int(r.gap_length):raise ValueError('original mask length inconsistent')
            records.append({'family':'crossed','key':r.realization_id,'length':int(r.gap_length),
                            'overlap_class':r.overlap_class,'mask':mask,'source':''})
        schedules[seed]=records
    def fixed_designs(support,seed,lengths,replicates):
        if seed not in schedules:raise ValueError('unrecognized target mask seed')
        result=schedules[seed]
        if any(len(r['mask'])!=len(support) for r in result):raise ValueError('mask calendar length changed')
        return [r.copy() for r in result]
    core.crossed_designs=fixed_designs
    bundle=joblib.load(model);cal=json.loads(calpath.read_text())
    if cal['D2_calibration_groups']!=bundle['roles']['interval_calibration']:raise ValueError('source calibration role mismatch')
    bundle['offsets']=cal['D2_offsets']
    variants=[];run_rows=[]
    input_snapshot={'panels':sorted(f'{r.station_id}|{int(r.shift_hours)}'
          for r in available.itertuples(index=False) if r.site_fully_available)}
    snapshot=PRIVATE/'score_inputs.json'
    if snapshot.exists():
        if json.loads(snapshot.read_text())!=input_snapshot:raise RuntimeError('cached sensitivity inputs changed')
    else:snapshot.write_text(json.dumps(input_snapshot,indent=2)+'\n');snapshot.chmod(0o600)
    receipts_path=PRIVATE/'case_cache_receipt.json';receipts=json.loads(receipts_path.read_text()) if receipts_path.exists() else {}
    try:
        for shift in plan['shifts_hours']:
            for site,g in roster.groupby('station_id',sort=True):
                pick=available.loc[available.station_id.eq(site)&available.shift_hours.eq(shift)]
                if len(pick)!=1:raise ValueError('site availability is not unique')
                if not bool(pick.site_fully_available.iloc[0]):
                    run_rows.append({'station_id':site,'shift_hours':shift,'status':'missing_boundary_years','cases':0});continue
                panel=OUT/'panels'/f'shift_{int(shift):+d}'/f'{site}.csv'
                job={'network_id':'ns_'+site,'station_id':site,'station_key':'ns_exploratory|'+site,
                  'provider':'ns_exploratory','independence_group':'nova_scotia_shared_climate','latitude':float(g.iloc[0].latitude),
                  'input_path':str(panel),'air_input_path':str(air),'statistic_class':'reported_clock_24_hour_mean_QC_unknown',
                  'regulation_status':'unknown','region':'nova_scotia','roster':'independent','station_index':indices[f'ns_{site}|{site}']}
                core.CACHE=PRIVATE/f'shift_{int(shift):+d}'/'case_cache';cache=core.cache_path(job,settings);key=f'{site}|{int(shift)}'
                if cache.exists() and key not in receipts:raise RuntimeError('sensitivity case cache has no matching receipt')
                result=core.station_cases(job,settings,generator,[],resume=True)
                if not result.get('cache'):raise RuntimeError(f"case generation unavailable: {site}/{shift}: {result.get('reason')}")
                path=Path(result['cache']);path.chmod(0o600);receipts_path.write_text(json.dumps(receipts,indent=2)+'\n');receipts_path.chmod(0o600)
                cases=pd.read_parquet(path)
                base_site=base_cases.loc[base_cases.station_id.eq(site)]
                check=cases[KEY].merge(base_site[KEY],on=KEY,how='outer',indicator=True,validate='one_to_one')
                if not check._merge.eq('both').all():raise ValueError('fixed masks or case keys changed')
                pred=inference.classical_predictions(inference.predict(cases,bundle),cal);pred['shift_hours']=int(shift)
                variants.append(pred);run_rows.append({'station_id':site,'shift_hours':shift,'status':'computed','cases':len(pred)})
                print('Refit fixed masks',site,'shift',shift,'cases',len(pred),flush=True)
    finally:core.crossed_designs=original_crossed
    all_data=pd.concat(variants,ignore_index=True);all_data.to_parquet(PRIVATE/'predictions.parquet',index=False);(PRIVATE/'predictions.parquet').chmod(0o600)
    runs=pd.DataFrame(run_rows);runs.to_csv(OUT/'run_availability.csv',index=False)
    # The zero-shift control must reproduce every original outcome on the same masks.
    zero=all_data.loc[all_data.shift_hours.eq(0)];z=zero.merge(base_pred,on=KEY,suffixes=('_new','_base'),validate='one_to_one',how='outer',indicator=True)
    if len(z)!=len(base_pred) or not z._merge.eq('both').all():raise ValueError('zero-shift cohort differs')
    cols=['eval_truth_h30','observed_lower_bound__observed_days','h30__policy','D2','risk_score']+[f'{prefix}_q{q:02d}' for prefix in ['D2','stochastic_cal'] for q in LEVELS]
    max_zero=0.
    for col in cols:
        a=z[col+'_new'].to_numpy(float);b=z[col+'_base'].to_numpy(float)
        if not np.allclose(a,b,atol=1e-8,rtol=0,equal_nan=True):raise ValueError(f'zero-shift replay differs: {col}')
        both=np.isfinite(a)&np.isfinite(b)
        if both.any():max_zero=max(max_zero,float(np.max(abs(a[both]-b[both]))))
    # Match across all three shifts, then demand both methods and both quantile sets.
    groups=[]
    for shift in plan['shifts_hours']:
        f=all_data.loc[all_data.shift_hours.eq(shift)].copy()
        qcols=[f'{prefix}_q{q:02d}' for prefix in ['D2','stochastic_cal'] for q in LEVELS]
        valid=np.isfinite(f[['eval_truth_h30','D2','stochastic_cal_q50']+qcols].to_numpy(float)).all(axis=1)
        groups.append(f.loc[valid,KEY])
    common=groups[0]
    for g in groups[1:]:common=common.merge(g,on=KEY,how='inner',validate='one_to_one')
    if common.empty:raise ValueError('no case available for both methods across all shifts')
    scorer=T.load_script('ns_clock_quantiles',ROOT/'scripts/528_review_response_annual.py')
    score_module=T.load_script('ns_clock_score_tables',ROOT/'scripts/598_nova_scotia_exploratory_score.py')
    baserows=base_pred[KEY+['peak_overlap']].rename(columns={'peak_overlap':'baseline_peak_overlap'})
    summaries=[];site_rows=[];casewise={};truth_rows=[]
    for shift in plan['shifts_hours']:
        g=common.merge(all_data.loc[all_data.shift_hours.eq(shift)],on=KEY,how='left',validate='one_to_one')
        g=g.merge(baserows,on=KEY,how='left',validate='one_to_one')
        anchor=g.copy();anchor['peak_overlap']=anchor.baseline_peak_overlap
        _,paired,_=score_module.score_tables(anchor,scorer.quantile_samples)
        paired['shift_hours']=int(shift);summaries.append(paired)
        for site,block in anchor.groupby('station_id'):
            _,site_pair,_=score_module.score_tables(block,scorer.quantile_samples)
            row=site_pair.loc[site_pair.stratum.eq('all')].iloc[0].to_dict();row.update(station_id=site,shift_hours=int(shift));site_rows.append(row)
        casewise[int(shift)]=score_casewise(g,scorer.quantile_samples)
        unique=g[['station_id','year','eval_truth_h30']].drop_duplicates()
        if unique.duplicated(['station_id','year']).any():raise ValueError('reference varies within station-year')
        unique['shift_hours']=int(shift);truth_rows.append(unique)
    paired=pd.concat(summaries,ignore_index=True);paired.to_csv(OUT/'paired_summary.csv',index=False)
    pd.DataFrame(site_rows).to_csv(OUT/'paired_by_station.csv',index=False)
    diffs=[]
    for shift in [-1,1]:
        for metric in casewise[0].columns:
            v=casewise[shift][metric].to_numpy(float)-casewise[0][metric].to_numpy(float)
            diffs.append({'shift_hours':shift,'metric':metric,'n_common':len(v),'mean_shift_minus_zero':float(v.mean()),'max_abs_case_change':float(abs(v).max())})
    pd.DataFrame(diffs).to_csv(OUT/'paired_differences.csv',index=False)
    truth=pd.concat(truth_rows,ignore_index=True);base_truth=truth.loc[truth.shift_hours.eq(0),['station_id','year','eval_truth_h30']].rename(columns={'eval_truth_h30':'baseline_h30'})
    truth=truth.merge(base_truth,on=['station_id','year'],validate='many_to_one');truth['h30_change_c']=truth.eval_truth_h30-truth.baseline_h30
    truth[['station_id','year','shift_hours','h30_change_c']].to_csv(OUT/'reference_h30_changes.csv',index=False)
    state={'status':'scored_sensitivity','base_cases':len(base_pred),'all_shift_common_cases':len(common),'available_case_fraction':len(common)/len(base_pred),
       'station_years':len(base_truth),'sites':int(base_truth.station_id.nunique()),'shifts_hours':plan['shifts_hours'],
       'max_zero_shift_replay_difference':max_zero,'max_abs_reference_h30_change_c':float(truth.h30_change_c.abs().max()),
       'mask_identity':'identical original station/year/realization/mask runs; danger subset fixed to baseline training-period overlap',
       'strict_reference_qualified':False,'limitation':plan['limitation']+'; annual outputs and local fits are recomputed for each shifted day definition; NASA POWER forcing is held fixed in local solar time'}
    (OUT/'score_status.json').write_text(json.dumps(state,indent=2)+'\n');ref['model_scoring_performed']=True;(OUT/'reference_status.json').write_text(json.dumps(ref,indent=2)+'\n')
    print(paired.to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()
