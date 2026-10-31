#!/usr/bin/env python3
"""Replay saved whole-archive annual models and isolate projection stages.

This holds the fitted models and projection-aware calibration offsets fixed.
It is a computational attribution of the final projection, not a re-fit under
an alternative calibration protocol. Only aggregate results are exported.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from stream_recoverability.experiments.tr_revision.archive import apply_observed_lower_bound

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/wrr_review_completion_20261024'
OUT=ROOT/'results/wrr_review_response_20261027/whole_archive'
LEVELS=[5,10,25,50,75,90,95]
TOL=1e-8


def stages(raw, bound, difficulty, offsets, fallback=None, supported=None):
    """Model output, first projection, fixed-offset correction, final projection."""
    raw=np.asarray(raw,float)
    first=apply_observed_lower_bound(raw, bound)
    corrected=first.copy()
    for label in np.unique(difficulty):
        correction=offsets.get(label, fallback)
        if correction is None:
            corrected[difficulty==label]=np.nan
        else:
            corrected[difficulty==label]+=np.asarray(correction)
    corrected=np.sort(corrected,axis=1)
    final=apply_observed_lower_bound(corrected,bound)
    if supported is not None:
        raw=raw.copy();first=first.copy()
        for array in (raw,first,corrected,final):array[~supported]=np.nan
    return raw,first,corrected,final


def stage_summary(pre, final, bound, truth):
    valid=np.isfinite(pre).all(axis=1)&np.isfinite(final).all(axis=1)&np.isfinite(bound)&np.isfinite(truth)
    p,f,b,y=pre[valid],final[valid],bound[valid],truth[valid]
    width_pre=p[:,-1]-p[:,0];width_final=f[:,-1]-f[:,0]
    zp=abs(width_pre)<=TOL;zf=abs(width_final)<=TOL
    precovered=(y>=p[:,0]-TOL)&(y<=p[:,-1]+TOL)
    covered=(y>=f[:,0]-TOL)&(y<=f[:,-1]+TOL)
    changed=np.any(abs(p-f)>TOL,axis=1)
    return dict(n=len(p),pre_zero=int(zp.sum()),final_zero=int(zf.sum()),
                zero_created=int((~zp&zf).sum()),zero_retained=int((zp&zf).sum()),
                zero_lost=int((zp&~zf).sum()),final_zero_missed=int((zf&~covered).sum()),
                created_zero_missed=int((~zp&zf&~covered).sum()),
                pre_below_bound=int(np.any(p<b[:,None]-TOL,axis=1).sum()),
                final_projection_changed=int(changed.sum()),
                pre_covered=int(precovered.sum()),final_covered=int(covered.sum()),
                pre_width_sum=float(width_pre.sum()),final_width_sum=float(width_final.sum()))


def load_cases():
    chunks=[];files=0
    for family in ('calendar','crossed'):
        for mode in ('offline','forward'):
            for path in sorted((OUT/family/mode).glob('replicate_*/*/annual_predictions.parquet')):
                files+=1
                if pq.ParquetFile(path).metadata.num_rows==0:continue
                c=pd.read_parquet(path)
                c['_family']=family;c['_mode']=mode;c['_replicate']=int(path.parent.parent.name.split('_')[-1])
                chunks.append(c)
    frame=pd.concat(chunks,ignore_index=True)
    keys=['_family','_mode','_replicate','station_key','year']
    if frame.duplicated(keys).any():raise ValueError('duplicate annual case identifiers')
    ref=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','eval_truth_h30'])
    grouped=ref.groupby(['station_key','year','design_family'],dropna=False).eval_truth_h30.agg(['min','max','count'])
    if grouped['count'].eq(0).any() or (grouped['max']-grouped['min']).gt(TOL).any():raise ValueError('inconsistent reference')
    ref=grouped['min'].rename('_reference').reset_index().rename(columns={'design_family':'_family'})
    frame=frame.merge(ref,on=['station_key','year','_family'],how='left',validate='many_to_one')
    if frame._reference.isna().any():raise ValueError('missing annual reference')
    return frame,files


def main():
    import wrr_tr_features as features
    cases,files=load_cases()
    calibrations=json.loads((OUT/'classical_calibration.json').read_text())
    # Last-stage quantiles remain local; the exported table consists of aggregates.
    for name in ('D2','stochastic_cal'):
        for stage in ('raw','first','pre','final'):
            for q in LEVELS:cases[f'_{name}_{stage}_{q:02d}']=np.nan
    for (mode,region),indices in cases.groupby(['_mode','region']).groups.items():
        c=cases.loc[indices];cal=calibrations[mode][region]
        split='before_2010' if mode=='forward' else 'leave_one_year_out'
        bundle=joblib.load(SOURCE/'refits'/split/'seed_00'/f'{region}.joblib')
        x=features.design_matrix(c,simulation=True).reindex(columns=bundle['features'])
        point=c.h30__policy.to_numpy(float)
        d_raw=np.sort(np.column_stack([model.predict(x) for model in bundle['quantile_models']])+point[:,None],axis=1)
        labels=c.difficulty.to_numpy(str);bound=c.observed_lower_bound__observed_days.to_numpy(float)
        supported=np.isfinite(point)&c.policy_choice.ne('unavailable').to_numpy()&np.isin(labels,list(cal['D2_offsets']))
        s_raw=c[[f'stochastic_h30_q{i:02d}' for i in LEVELS]].to_numpy(float)
        streams={'D2':stages(d_raw,bound,labels,cal['D2_offsets'],supported=supported),
                 'stochastic_cal':stages(s_raw,bound,labels,cal['offsets']['stochastic'],cal['offsets']['stochastic']['__pooled__'])}
        for name,arrays in streams.items():
            saved=c[[f'{name}_q{i:02d}' for i in LEVELS]].to_numpy(float)
            if not np.allclose(arrays[-1],saved,atol=TOL,rtol=0,equal_nan=True):
                mismatch=~np.isclose(arrays[-1],saved,atol=TOL,rtol=0,equal_nan=True)
                raise ValueError(f'replay differs from saved output for {mode}/{region}/{name}: {int(mismatch.sum())} cells')
            for stage,array in zip(('raw','first','pre','final'),arrays):
                cases.loc[indices,[f'_{name}_{stage}_{q:02d}' for q in LEVELS]]=array
        print(f'Replayed {mode}/{region}: {len(c)} rows',flush=True)
    rows=[]
    for (family,mode),c in cases.groupby(['_family','_mode']):
        bound=c.observed_lower_bound__observed_days.to_numpy(float);truth=c._reference.to_numpy(float)
        valid=np.isfinite(bound)&np.isfinite(truth)
        for name in ('D2','stochastic_cal'):
            valid &= np.isfinite(c[[f'_{name}_final_{q:02d}' for q in LEVELS]].to_numpy(float)).all(axis=1)
        for name in ('D2','stochastic_cal'):
            get=lambda stage:c.loc[valid,[f'_{name}_{stage}_{q:02d}' for q in LEVELS]].to_numpy(float)
            raw,first,pre,final=(get(stage) for stage in ('raw','first','pre','final'))
            if any(np.any(np.diff(array,axis=1)<-TOL) for array in (raw,first,pre,final)):
                raise ValueError(f'crossed stage quantiles in {family}/{mode}/{name}')
            v=stage_summary(pre,final,bound[valid],truth[valid])
            first_zero=abs(first[:,-1]-first[:,0])<=TOL
            calibrated_zero=abs(pre[:,-1]-pre[:,0])<=TOL
            v.update(family=family,mode=mode,estimator='stochastic_calibrated' if name=='stochastic_cal' else name,
                     raw_zero=int((abs(raw[:,-1]-raw[:,0])<=TOL).sum()),
                     first_projection_zero=int(first_zero.sum()),
                     first_projection_created_zero=int(((abs(raw[:,-1]-raw[:,0])>TOL)&first_zero).sum()),
                     offset_correction_created_zero=int((~first_zero&calibrated_zero).sum()),
                     offset_correction_lost_zero=int((first_zero&~calibrated_zero).sum()),
                     stations=int(c.loc[valid,'station_key'].nunique()),groups=int(c.loc[valid,'independence_group'].nunique()))
            rows.append(v)
    summary=pd.DataFrame(rows).sort_values(['family','mode','estimator'])
    previous=pd.read_csv(OUT/'support_projection_summary.csv')
    joined=summary.merge(previous,on=['family','mode','estimator'],validate='one_to_one')
    if not joined.n.eq(joined.paired_rows).all() or not joined.final_zero.eq(joined.zero_width90).all():
        raise ValueError('replay denominator or final zero counts differ from existing audit')
    summary.to_csv(OUT/'projection_stage_summary.csv',index=False)
    report={'status':'passed','annual_rows':len(cases),'archive_files':files,'estimator_groups':len(summary),
            'saved_quantile_replay':'all values and missingness matched within absolute tolerance 1e-8 C',
            'stage_quantile_order':'all common finite-bound cases checked within absolute tolerance 1e-8 C',
            'scope':'common finite-bound cases for two estimators; same fitted models and same projection-aware calibration offsets',
            'limitation':'the pre-final stage retains the first projection and offsets learned with that projection; no alternative model or calibration is fitted; quantiles do not establish physical sensor uncertainty'}
    (OUT/'projection_stage_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(summary.to_string(index=False));print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        (OUT/'projection_stage_status.json').write_text(json.dumps({
            'status':'failed','error':f'{type(exc).__name__}: {exc}',
            'limitation':'a previous summary CSV may remain and must not be treated as a successful current replay'
        },indent=2)+'\n')
        raise
