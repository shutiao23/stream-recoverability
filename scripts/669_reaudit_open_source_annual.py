#!/usr/bin/env python3
"""Independently recount paired annual metrics and group resampling locally."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.special import ndtri
import wrr_tr_common as T

ROOT=T.ROOT; REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'open_source_sensitivity'
STAGE=ROOT/'private/wrr_open_source_sensitivity_20261026/whole_archive'
PRIVATE=ROOT/'private/wrr_review_case_evidence_20261027'
KEY=['family','mode','replicate','station_key','year'];METHODS=['D2','stochastic_cal'];LEVELS=[5,10,25,50,75,90,95]
METRICS=['mae','bias','coverage90','width90','interval_score90','crps','zero90']

def independent_scores(q,y,bound):
    low,med,high=q[:,0],q[:,3],q[:,-1]
    u=(np.arange(128)+0.5)/128;levels=np.array([.05,.1,.25,.5,.75,.9,.95]);j=np.clip(np.searchsorted(levels,u)-1,0,5)
    weights=np.clip((u-levels[j])/(levels[j+1]-levels[j]),0,1)
    x=q[:,j]+(q[:,j+1]-q[:,j])*weights[None,:]
    z,zu=ndtri(levels),ndtri(u);lo=u<levels[0];hi=u>levels[-1]
    x[:,lo]=q[:,[0]]+(q[:,[1]]-q[:,[0]])/(z[1]-z[0])*(zu[lo]-z[0])[None,:]
    x[:,hi]=q[:,[-1]]+(q[:,[-1]]-q[:,[-2]])/(z[-1]-z[-2])*(zu[hi]-z[-1])[None,:]
    x=np.maximum(x,bound[:,None]);x=np.sort(x,axis=1);n=x.shape[1]
    crps=np.abs(x-y[:,None]).mean(axis=1)-np.sum(x*(2*np.arange(n)+1-n),axis=1)/(n*n)
    error=med-y
    return {'mae':abs(error),'bias':error,'coverage90':((y>=low-1e-8)&(y<=high+1e-8)).astype(float),
            'width90':high-low,'interval_score90':high-low+20*(np.maximum(low-y,0)+np.maximum(y-high,0)),
            'crps':crps,'zero90':(abs(high-low)<=1e-8).astype(float)}

def read_candidate():
    files=sorted(STAGE.glob('*/?*/replicate_*/*/annual_predictions.parquet'))
    if len(files)!=3320:raise ValueError('Archive setting count changed')
    cols=['station_key','independence_group','year','observed_lower_bound__observed_days']+[f'{m}_q{i:02d}' for m in METHODS for i in LEVELS]
    chunks=[]
    for p in files:
        if pq.ParquetFile(p).metadata.num_rows==0:continue
        a=pd.read_parquet(p,columns=cols);a['family']=p.parents[3].name;a['mode']=p.parents[2].name;a['replicate']=int(p.parents[1].name.split('_')[-1]);chunks.append(a)
    result=pd.concat(chunks,ignore_index=True)
    if result.duplicated(KEY).any():raise ValueError('Duplicate candidate identities')
    return result

def main():
    status=json.loads((OUT/'annual_sensitivity_status.json').read_text())
    if status['status']!='passed':
        raise ValueError('Annual sensitivity incomplete or implementation changed')
    annual=T.load_script('independent_visibility_source',ROOT/'scripts/578_peak_visibility_diagnostics.py')
    old=annual.load_cases(PRIVATE);new=read_candidate()
    combined=old.merge(new,on=KEY,how='outer',suffixes=('_old','_candidate'),indicator=True,validate='one_to_one')
    if not combined._merge.eq('both').all() or not combined.independence_group_old.eq(combined.independence_group_candidate).all():
        raise ValueError('Annual identities or connected groups differ')
    bound='observed_lower_bound__observed_days'
    if not np.allclose(combined[bound+'_old'],combined[bound+'_candidate'],atol=1e-8,rtol=0,equal_nan=True):raise ValueError('Visible bound changed')
    scores=pd.read_csv(OUT/'annual_sensitivity_scores.csv');pairs=pd.read_csv(OUT/'annual_sensitivity_paired.csv');loo=pd.read_csv(OUT/'annual_sensitivity_leave_region_out.csv')
    cohorts=pd.read_csv(OUT/'annual_sensitivity_cohorts.csv');names=[f'{m}_q{i:02d}' for m in METHODS for i in LEVELS]
    nscore=npair=nloo=0
    for offset,((family,mode),block) in enumerate(combined.groupby(['family','mode'],sort=True)):
        oldvalid=np.isfinite(block[[x+'_old' for x in names]].to_numpy(float)).all(axis=1)
        newvalid=np.isfinite(block[[x+'_candidate' for x in names]].to_numpy(float)).all(axis=1)
        good=np.isfinite(block.reference_h30.to_numpy(float))&np.isfinite(block[bound+'_old'].to_numpy(float))
        same=oldvalid&newvalid&good;g=block.loc[same].copy().reset_index(drop=True)
        record=cohorts.loc[cohorts.family.eq(family)&cohorts['mode'].eq(mode)]
        if len(record)!=1 or int(record.iloc[0].common_four_way)!=len(g) or int(record.iloc[0].original_only)!=int((oldvalid&~newvalid&good).sum()):
            raise ValueError('Common-cohort availability differs')
        delta=g.reference_h30.to_numpy(float)-g[bound+'_old'].to_numpy(float)
        if (delta < -1e-8).any():raise ValueError('Reference is below lower bound')
        g['stratum']=np.where(delta<=1e-8,'bound_matches_reference','unobserved_peak_excess')
        y=g.reference_h30.to_numpy(float);lower=g[bound+'_old'].to_numpy(float)
        for method in METHODS:
            for version in ['old','candidate']:
                q=g[[f'{method}_q{i:02d}_{version}' for i in LEVELS]].to_numpy(float)
                values=independent_scores(q,y,lower)
                for metric in METRICS:g[version+'_'+method+'_'+metric]=values[metric]
        for stratum in ['all','bound_matches_reference','unobserved_peak_excess']:
            sub=g if stratum=='all' else g.loc[g.stratum.eq(stratum)]
            if sub.empty:continue
            labels=sub.independence_group_old.to_numpy();groups=sorted(set(labels))
            for method in METHODS:
                estimator='stochastic_calibrated' if method=='stochastic_cal' else method
                for version in ['old','candidate']:
                    row=scores.loc[scores.family.eq(family)&scores['mode'].eq(mode)&scores.stratum.eq(stratum)&scores.estimator.eq(estimator)&scores.version.eq(version)]
                    if len(row)!=1 or int(row.iloc[0].n_common)!=len(sub):raise ValueError('Annual summary denominator differs')
                    for metric in METRICS:
                        if not np.isclose(sub[version+'_'+method+'_'+metric].mean(),row.iloc[0][metric],atol=1e-9,rtol=0):raise ValueError('Annual score differs: '+metric)
                    nscore+=1
                row=pairs.loc[pairs.family.eq(family)&pairs['mode'].eq(mode)&pairs.stratum.eq(stratum)&pairs.estimator.eq(estimator)]
                if len(row)!=1:raise ValueError('Paired score missing')
                for i,metric in enumerate(METRICS):
                    differences=(sub['candidate_'+method+'_'+metric]-sub['old_'+method+'_'+metric]).to_numpy(float)
                    sums=np.array([differences[labels==group].sum() for group in groups]);sizes=np.array([(labels==group).sum() for group in groups])
                    if not np.isclose(differences.mean(),row.iloc[0][metric+'_difference'],atol=1e-9,rtol=0):raise ValueError('Paired score difference differs')
                    if not np.isclose(np.mean(sums/sizes),row.iloc[0][metric+'_group_equal_difference'],atol=1e-9,rtol=0):raise ValueError('Equal-group difference differs')
                    rng=np.random.default_rng(668000+100*offset+i);draws=[]
                    for _ in range(4000):
                        index=rng.integers(len(groups),size=len(groups));draws.append(sums[index].sum()/sizes[index].sum())
                    ci=np.quantile(draws,[.025,.975])
                    if not np.allclose(ci,[row.iloc[0][metric+'_bootstrap_low'],row.iloc[0][metric+'_bootstrap_high']],atol=1e-9,rtol=0):raise ValueError('Group bootstrap differs')
                npair+=1
                for region in sorted(sub.region.unique()):
                    kept=sub.loc[sub.region.ne(region)]
                    if kept.empty:continue
                    rec=loo.loc[loo.family.eq(family)&loo['mode'].eq(mode)&loo.stratum.eq(stratum)&loo.estimator.eq(estimator)&loo.excluded_region.eq(region)]
                    if len(rec)!=1 or int(rec.iloc[0].n_remaining)!=len(kept):raise ValueError('Leave-region-out denominator differs')
                    for metric in ['coverage90','mae','width90','interval_score90','crps']:
                        diff=(kept['candidate_'+method+'_'+metric]-kept['old_'+method+'_'+metric]).mean()
                        if not np.isclose(diff,rec.iloc[0][metric+'_difference'],atol=1e-9,rtol=0):raise ValueError('Leave-region-out difference differs')
                    nloo+=1
    if nscore!=len(scores) or npair!=len(pairs) or nloo!=len(loo):raise ValueError('Summary row counts differ')
    report={'status':'passed','matched_annual_cases':len(combined),'version_score_rows_checked':nscore,
            'paired_rows_with_all_bootstrap_metrics':npair,'leave_region_out_rows':nloo,
            'bootstrap_draws_per_metric':4000,'limit':'Recounts saved predictions and outcomes; does not refit models, independently validate sensor quality or calibrate new intervals.'}
    (OUT/'annual_sensitivity_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'annual_sensitivity_independent_audit.json').write_text(json.dumps({
            'status':'failed','error':f'{type(exc).__name__}: {exc}'
        },indent=2)+'\n')
        raise
