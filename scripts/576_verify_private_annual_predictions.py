#!/usr/bin/env python3
"""Recompute saved source annual scores from local per-case model outputs.

This checks scored predictions, not original model fitting, raw input
observations, 20 independent climates or the validity of the outer tails.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import ndtri

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'private/wrr_review_case_evidence_20261027'
Q=np.array([.05,.10,.25,.50,.75,.90,.95])
LEVELS=[5,10,25,50,75,90,95]
METHODS={'plug_in':'h30__policy','functional_debias':'P2','distribution_regression':'D2',
         'stochastic_regression_calibrated':'stochastic_cal_q50'}
KEY=['network_id','station_key','year','design_family','realization_id','policy_choice','mask_runs']


def quadrature(q,lower,draws=128):
    """Linear interior, adjacent-normal outer slopes and support projection."""
    q=np.asarray(q,float);lower=np.asarray(lower,float)
    q=np.where(np.isfinite(lower[:,None]),np.maximum(q,lower[:,None]),q)
    u=(np.arange(draws)+.5)/draws
    j=np.clip(np.searchsorted(Q,u)-1,0,len(Q)-2)
    ratio=np.clip((u-Q[j])/(Q[j+1]-Q[j]),0,1)
    x=q[:,j]+(q[:,j+1]-q[:,j])*ratio[None,:]
    z=ndtri(Q);zu=ndtri(u);lo=u<Q[0];hi=u>Q[-1]
    x[:,lo]=q[:,[0]]+(q[:,[1]]-q[:,[0]])/(z[1]-z[0])*(zu[lo]-z[0])[None,:]
    x[:,hi]=q[:,[-1]]+(q[:,[-1]]-q[:,[-2]])/(z[-1]-z[-2])*(zu[hi]-z[-1])[None,:]
    return np.where(np.isfinite(lower[:,None]),np.maximum(x,lower[:,None]),x),q


def crps(x,y,threshold=None):
    x=np.asarray(x,float);y=np.asarray(y,float)
    if threshold is not None:
        threshold=np.asarray(threshold,float);x=np.maximum(x,threshold[:,None]);y=np.maximum(y,threshold)
    x=np.sort(x,axis=1);n=x.shape[1]
    coeff=(2*np.arange(n)+1-n).astype(float)
    return np.abs(x-y[:,None]).mean(axis=1)-np.sum(x*coeff[None,:],axis=1)/(n*n)


def distribution_scores(q,bound,truth,threshold,chunk=8192):
    values=[];tail=[]
    for start in range(0,len(q),chunk):
        end=min(start+chunk,len(q));x,_=quadrature(q[start:end],bound[start:end])
        values.append(crps(x,truth[start:end]));tail.append(crps(x,truth[start:end],threshold[start:end]))
    return np.concatenate(values),np.concatenate(tail)


def score_seed(frame,seed):
    truth=frame.eval_truth_h30.to_numpy(float);bound=frame.observed_lower_bound__observed_days.to_numpy(float)
    records=[];pairs=[]
    for family in ['calendar','crossed']:
        for stratum in ['all','danger']:
            mask=frame.design_family.eq(family).to_numpy()
            if stratum=='danger':mask &= frame.peak_overlap.ge(.5).to_numpy()
            b=frame.loc[mask];y=truth[mask];l=bound[mask];scored={}
            for method,column in METHODS.items():
                point=b[column].to_numpy(float);point=np.where(np.isfinite(l),np.maximum(point,l),point)
                valid=np.isfinite(point)&np.isfinite(y);error=point[valid]-y[valid]
                row=dict(seed=seed,family=family,stratum=stratum,estimator=method,n=int(valid.sum()),eligible=len(b),
                         availability=float(valid.mean()),mae=float(np.mean(abs(error))),bias=float(np.mean(error)),
                         failure_rate=float(np.mean(abs(error)>.5)))
                prefix={'distribution_regression':'D2','stochastic_regression_calibrated':'stochastic_cal'}.get(method)
                if prefix:
                    q=b[[f'{prefix}_q{i:02d}' for i in LEVELS]].to_numpy(float)
                    good=valid&np.isfinite(q).all(axis=1)
                    if good.any():
                        cs,ts=distribution_scores(q[good],l[good],y[good],b.train_h30_q90.to_numpy(float)[good])
                        clipped=np.where(np.isfinite(l[good,None]),np.maximum(q[good],l[good,None]),q[good])
                        low,high=clipped[:,0],clipped[:,-1]
                        interval=high-low+20*(np.maximum(low-y[good],0)+np.maximum(y[good]-high,0))
                        row.update(crps=float(cs.mean()),twcrps=float(ts.mean()),
                            coverage90=float(np.mean((y[good]>=low-1e-8)&(y[good]<=high+1e-8))),
                            width90=float(np.mean(high-low)),interval_score90=float(interval.mean()))
                        c_all=np.full(len(b),np.nan);t_all=np.full(len(b),np.nan);c_all[good]=cs;t_all[good]=ts
                        scored[method]=(point,good,c_all,t_all)
                records.append(row)
            a=scored['distribution_regression'];z=scored['stochastic_regression_calibrated'];common=a[1]&z[1]
            pairs.append(dict(seed=seed,family=family,stratum=stratum,n_common=int(common.sum()),
                D2_mae=float(np.mean(abs(a[0][common]-y[common]))),stochastic_mae=float(np.mean(abs(z[0][common]-y[common]))),
                D2_crps=float(np.mean(a[2][common])),stochastic_crps=float(np.mean(z[2][common])),
                D2_twcrps=float(np.mean(a[3][common])),stochastic_twcrps=float(np.mean(z[3][common]))))
    return pd.DataFrame(records),pd.DataFrame(pairs)


def compare(a,b,keys,columns):
    m=a.merge(b,on=keys,how='outer',suffixes=('_new','_saved'),indicator=True,validate='one_to_one')
    if not m._merge.eq('both').all():raise ValueError('scorecard keys differ')
    for c in columns:
        left=pd.to_numeric(m[c+'_new'],errors='raise').to_numpy(float);right=pd.to_numeric(m[c+'_saved'],errors='raise').to_numpy(float)
        if not np.isclose(left,right,rtol=1e-8,atol=1e-8,equal_nan=True).all():
            delta=np.nanmax(abs(left-right));raise ValueError(f'{c} score differs, max difference {delta}')
    return len(m)*len(columns)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=DEFAULT);p.add_argument('--seeds',nargs='+',type=int,default=list(range(20)));p.add_argument('--report',type=Path,help='alternate report path');args=p.parse_args()
    if len(set(args.seeds)) != len(args.seeds) or any(seed not in range(20) for seed in args.seeds):
        p.error('seeds must be distinct integers in 0..19')
    folder=args.evidence/'annual_source_cases';rev=args.evidence/'results/wrr_review_response_20261027/annual'
    scores=pd.read_csv(rev/'source_scorecard.csv');pairs=pd.read_csv(rev/'source_paired.csv');details=[]
    cols=['n','eligible','availability','mae','bias','failure_rate','crps','twcrps','coverage90','width90','interval_score90']
    pc=['n_common','D2_mae','stochastic_mae','D2_crps','stochastic_crps','D2_twcrps','stochastic_twcrps']
    try:
        for seed in sorted(args.seeds):
            frame=pd.read_parquet(folder/f'seed_{seed:02d}.parquet')
            if frame.empty or frame.duplicated(KEY).any():raise ValueError(f'invalid or duplicate cases in seed {seed}')
            truth=frame.eval_truth_h30.to_numpy(float);bound=frame.observed_lower_bound__observed_days.to_numpy(float)
            if np.any(np.isfinite(truth)&np.isfinite(bound)&(truth<bound-1e-8)):
                raise ValueError(f'reference below observed bound in seed {seed}')
            a,b=score_seed(frame,seed)
            x=compare(a,scores.loc[scores.seed.eq(seed)],['seed','family','stratum','estimator'],cols)
            y=compare(b,pairs.loc[pairs.seed.eq(seed)],['seed','family','stratum'],pc)
            details.append(dict(seed=seed,cases=len(frame),scorecard_cells=x,paired_cells=y))
            print(f'Verified seed {seed}: {len(frame)} cases',flush=True)
        report=dict(status='passed',seeds=len(details),cases=sum(x['cases'] for x in details),details=details,
                    scope='per-case scores from saved held-region outputs with re-applied historical calibration, not refitted models or provider-native data',
                    limitations='case IDs and reference values remain restricted; seed repetitions share the same archive and outer-tail shape is assumed')
    except Exception as exc:
        report=dict(status='failed',error=f'{type(exc).__name__}: {exc}',details=details)
    path=args.report or args.evidence/'annual_source_case_audit.json';path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps(report,indent=2),flush=True)
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
