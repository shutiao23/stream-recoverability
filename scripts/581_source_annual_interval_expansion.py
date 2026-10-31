#!/usr/bin/env python3
"""Explore annual interval expansion using source-only, held-group residuals.

The equal-group empirical correction has no conformal guarantee. A separate
finite-group rank diagnostic is reported but is not applied. This experiment
uses no held target outcomes when estimating source corrections, and reports
unavailable regions rather than manufacturing a zero-width guarantee.
"""
from __future__ import annotations
import os
for v in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[v]='1'
import argparse
import importlib.util
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/wrr_review_completion_20261024'
ARCHIVE=ROOT/'results/wrr_review_response_20261027/whole_archive'
OUT=ROOT/'results/wrr_review_response_20261027/annual_interval_expansion'
PRIVATE=ROOT/'private/wrr_review_case_evidence_20261027'
LEVELS=[5,10,25,50,75,90,95]
METHODS={'D2':'D2','stochastic_calibrated':'stochastic_cal'}
TOL=1e-8


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def correction(y,lo,hi,groups,alpha=.1,min_groups=3):
    """Equal-group empirical quantile of nonnegative interval nonconformity."""
    y,lo,hi=map(lambda x:np.asarray(x,float),(y,lo,hi));groups=np.asarray(groups)
    valid=np.isfinite(y)&np.isfinite(lo)&np.isfinite(hi)&pd.notna(groups)
    y,lo,hi,groups=y[valid],lo[valid],hi[valid],groups[valid]
    if (hi<lo-TOL).any():raise ValueError('source interval is reversed')
    if not len(y):return {'status':'no_source_cases','n_source_cases':0,'n_source_groups':0}
    score=np.maximum.reduce([lo-y,y-hi,np.zeros(len(y))])
    names,inv,counts=np.unique(groups,return_inverse=True,return_counts=True)
    weight=1/counts[inv];order=np.argsort(score,kind='mergesort')
    index=np.searchsorted(np.cumsum(weight[order]),(1-alpha)*weight.sum(),side='left')
    radius=float(score[order[min(index,len(order)-1)]])
    max_by_group=np.array([score[inv==i].max() for i in range(len(names))])
    rank=math.ceil((len(names)+1)*(1-alpha))
    group_max=float(np.sort(max_by_group)[rank-1]) if rank<=len(names) else None
    status='insufficient_source_groups' if len(names)<min_groups else ('zero_source_correction' if radius<=TOL else 'supported_exploratory')
    return dict(status=status,n_source_cases=len(y),n_source_groups=len(names),empirical_radius=radius,
                group_max_rank=rank,group_max_radius=group_max)


def intervals(lo,hi,bound,radius):
    lo=np.asarray(lo,float);hi=np.asarray(hi,float);bound=np.asarray(bound,float)
    lower=lo-radius;upper=hi+radius
    lower=np.where(np.isfinite(bound),np.maximum(lower,bound),lower)
    upper=np.where(np.isfinite(bound),np.maximum(upper,bound),upper)
    return lower,upper


def scores(y,lo,hi):
    return {'coverage90':((y>=lo-TOL)&(y<=hi+TOL)).astype(float),
            'width90':hi-lo,'interval_score90':hi-lo+20*(np.maximum(lo-y,0)+np.maximum(y-hi,0)),
            'zero90':(abs(hi-lo)<=TOL).astype(float)}


def read_source(family,mode):
    rows=[];folder=ARCHIVE/family/('calibration' if mode=='forward' else 'offline')
    for p in sorted(folder.glob('replicate_*/*/annual_predictions.parquet')):
        if pq.ParquetFile(p).metadata.num_rows==0:continue
        c=pd.read_parquet(p);c['_replicate']=int(p.parent.parent.name.split('_')[-1]);rows.append(c)
    if not rows:return pd.DataFrame()
    f=pd.concat(rows,ignore_index=True)
    if f.duplicated(['station_key','year','_replicate']).any():raise ValueError('duplicate source archive case')
    if mode=='forward' and f.year.ge(2010).any():raise ValueError('forward source case after 2009')
    return f


def reference():
    f=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','eval_truth_h30'])
    g=f.groupby(['station_key','year','design_family'],dropna=False).eval_truth_h30.agg(['min','max','count'])
    if g['count'].eq(0).any() or (g['max']-g['min']).gt(TOL).any():raise ValueError('reference values inconsistent')
    return g['min'].rename('_truth').reset_index().rename(columns={'design_family':'_family'})


def summarize(cases,plans):
    cols=['coverage90','width90','interval_score90','zero90']
    keys=['family','mode','region','station_key','year','replicate']
    flags=cases.loc[cases.stratum.eq('all')].groupby(keys,dropna=False).agg(
        methods=('estimator','nunique'),common_eligible=('baseline_available','all'),common_supported=('supported','all')).reset_index()
    if not flags.methods.eq(2).all():raise ValueError('each target case must have both estimators')
    cases=cases.merge(flags.drop(columns='methods'),on=keys,how='left',validate='many_to_one')
    rows=[]
    for scope in ['estimator_available','both_methods_common']:
      for (family,mode,estimator,stratum),g in cases.groupby(['family','mode','estimator','stratum'],sort=True):
        eligible=g.baseline_available if scope=='estimator_available' else g.common_eligible
        selected=eligible&(g.supported if scope=='estimator_available' else g.common_supported)
        row=dict(family=family,mode=mode,estimator=estimator,stratum=stratum,scope=scope,n_eligible=int(eligible.sum()),
                 n_supported=int(selected.sum()),availability=float(selected.sum()/eligible.sum()) if eligible.sum() else np.nan,
                 stations=int(g.loc[selected,'station_key'].nunique()),groups=int(g.loc[selected,'independence_group'].nunique()))
        for metric in cols:
            row['baseline_all_'+metric]=float(g.loc[eligible,'base_'+metric].mean()) if eligible.any() else np.nan
            row['baseline_paired_'+metric]=float(g.loc[selected,'base_'+metric].mean()) if selected.any() else np.nan
            row['expanded_paired_'+metric]=float(g.loc[selected,'new_'+metric].mean()) if selected.any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--families',nargs='+',choices=['calendar','crossed'],default=['calendar','crossed'])
    p.add_argument('--modes',nargs='+',choices=['offline','forward'],default=['offline','forward'])
    p.add_argument('--regions',nargs='+');p.add_argument('--evidence',type=Path,help='use the verified local case subset for target scoring')
    p.add_argument('--output',type=Path,default=OUT);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    annual=module('visibility_annual',ROOT/'scripts/578_peak_visibility_diagnostics.py')
    inference=module('expansion_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    target=annual.load_cases(args.evidence) if args.evidence else annual.load_workspace_cases()
    target=target.loc[target.family.isin(args.families)&target['mode'].isin(args.modes)]
    if args.regions:target=target.loc[target.region.isin(args.regions)]
    if target.empty:raise ValueError('no target cases')
    reference_data=reference();calibrations=json.loads((ARCHIVE/'classical_calibration.json').read_text())
    plans=[];records=[]
    for (family,mode),targets in target.groupby(['family','mode'],sort=True):
        src=read_source(family,mode)
        ref=reference_data.loc[reference_data._family.eq(family)].drop(columns='_family')
        src=src.merge(ref,on=['station_key','year'],how='left',validate='many_to_one') if len(src) else src
        if len(src) and src._truth.isna().any():raise ValueError('source masked year has no complete reference')
        for region,held in targets.groupby('region',sort=True):
            split='before_2010' if mode=='forward' else 'leave_one_year_out'
            bundle=joblib.load(SOURCE/'refits'/split/'seed_00'/f'{region}.joblib')
            cal=calibrations[mode][region];bundle['offsets']=cal['D2_offsets']
            roles={name:set(groups) for name,groups in bundle['roles'].items()}
            rule=roles['rule_calibration']
            if any(rule&roles[x] for x in ['estimator','interval_calibration','risk_learning']):raise ValueError('source calibration roles overlap')
            if rule&set(held.independence_group):raise ValueError('target connected groups overlap source calibration groups')
            sub=src.loc[src.independence_group.isin(rule)].copy() if len(src) else pd.DataFrame()
            if len(sub):
                if sub.region.eq(region).any():raise ValueError('source calibration includes held region')
                predicted=inference.classical_predictions(inference.predict(sub,bundle),cal)
            else:predicted=pd.DataFrame()
            region_plans={}
            for estimator,prefix in METHODS.items():
                if len(predicted):
                    c=correction(predicted._truth,predicted[f'{prefix}_q05'],predicted[f'{prefix}_q95'],predicted.independence_group)
                    valid=np.isfinite(predicted._truth)&np.isfinite(predicted[f'{prefix}_q05'])&np.isfinite(predicted[f'{prefix}_q95'])&predicted.independence_group.notna()
                    c['n_source_stations']=int(predicted.loc[valid,'station_key'].nunique())
                    c['last_source_year']=int(predicted.loc[valid,'year'].max()) if valid.any() else None
                else:c={'status':'no_source_cases','n_source_cases':0,'n_source_groups':0,'n_source_stations':0,'last_source_year':None}
                region_plans[estimator]=c
                plans.append(dict(family=family,mode=mode,region=region,estimator=estimator,**c))
                h=held.copy();lo=h[f'{prefix}_q05'].to_numpy(float);hi=h[f'{prefix}_q95'].to_numpy(float);y=h.reference_h30.to_numpy(float);bound=h.observed_lower_bound__observed_days.to_numpy(float)
                eligible=np.isfinite(lo)&np.isfinite(hi)&np.isfinite(y)
                if (hi[eligible]<lo[eligible]-TOL).any() or (np.isfinite(bound)&eligible&(y<bound-TOL)).any():raise ValueError('target interval or bound inconsistent')
                supported=np.repeat(c['status']=='supported_exploratory',len(h))
                newlo,newhi=intervals(lo,hi,bound,c.get('empirical_radius',0.))
                base=scores(y,lo,hi);new=scores(y,newlo,newhi)
                valid_b=np.isfinite(bound)&eligible
                outcome=np.where(valid_b,np.where(y-bound<=TOL,'bound_matches_reference','unobserved_peak_excess'),'no_finite_bound')
                for stratum,select in [('all',np.ones(len(h),bool)),('bound_matches_reference',outcome=='bound_matches_reference'),('unobserved_peak_excess',outcome=='unobserved_peak_excess'),('no_finite_bound',outcome=='no_finite_bound')]:
                    part=pd.DataFrame({'family':family,'mode':mode,'region':region,'estimator':estimator,'stratum':stratum,
                        'station_key':h.station_key.to_numpy(),'year':h.year.to_numpy(),'replicate':h.replicate.to_numpy(),
                        'independence_group':h.independence_group.to_numpy(),
                        'baseline_available':eligible,'supported':supported})
                    for k in base:part['base_'+k]=base[k];part['new_'+k]=new[k]
                    records.append(part.loc[select])
            print(f'{family}/{mode}/{region}: '+', '.join(f"{m}={x['status']}({x['n_source_groups']} groups)" for m,x in region_plans.items()),flush=True)
    plan=pd.DataFrame(plans);case=pd.concat(records,ignore_index=True);summary=summarize(case,plan)
    for metric in ['coverage90','width90']:
        pair=summary.loc[summary.n_supported.gt(0)]
        if (pair['expanded_paired_'+metric]<pair['baseline_paired_'+metric]-TOL).any():raise ValueError('expansion shrank interval or decreased coverage')
    plan.to_csv(args.output/'source_support.csv',index=False);summary.to_csv(args.output/'paired_summary.csv',index=False)
    report={'status':'passed','families':args.families,'modes':args.modes,'target_rows':len(target),
            'source_role':'rule-calibration groups disjoint from estimator, interval calibration, risk learning and held-region groups',
            'forward_source_years':'strictly before 2010','source_calibration':'equal connected-group mass; empirical 90th percentile of nonnegative annual interval misses; at least three groups and positive radius',
            'scope':'coverage, width and interval score of supported target cases before/after; baseline all-case results and outcome-defined retrospective strata retained',
            'limitation':'exploratory analysis selected after prior results; group-weighted empirical quantile has no conformal or climate-transfer guarantee; group-max finite-rank diagnostic is not applied; no new joint trend distribution'}
    (args.output/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(summary.to_string(index=False));print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--output',type=Path,default=OUT);args,_=parser.parse_known_args()
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'status.json').write_text(json.dumps({'status':'failed','error':f'{type(exc).__name__}: {exc}'},indent=2)+'\n')
        raise
