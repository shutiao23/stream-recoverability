#!/usr/bin/env python3
"""Retrospectively stratify annual skill by whether a reported peak is visible.

The stratum uses complete-reference H30 and cannot be known prospectively.
This analysis is descriptive and must not be used as a decision-time feature.
Only aggregate summaries leave the restricted local evidence directory.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'private/wrr_review_case_evidence_20261027'
OUTPUT=ROOT/'results/wrr_review_response_20261027/whole_archive'
TOL=1e-8
LEVELS=[5,10,25,50,75,90,95]
METHODS=['D2','stochastic_cal']
METRICS=['mae','bias','coverage90','width90','interval_score90','crps','zero90']


def classify(reference, bound, tolerance=TOL):
    reference=np.asarray(reference,float);bound=np.asarray(bound,float)
    if not np.isfinite(reference).all() or not np.isfinite(bound).all():raise ValueError('finite reference and bound required')
    if (reference<bound-tolerance).any():raise ValueError('reference below observed bound')
    return np.where(reference-bound<=tolerance,'bound_matches_reference','unobserved_peak_excess')


def case_metrics(q,y,bound,scoring):
    if np.any(np.diff(q,axis=1)<-TOL):raise ValueError('quantile order violated')
    low,med,high=q[:,0],q[:,3],q[:,-1]
    residual=med-y
    scores=[]
    for start in range(0,len(q),8192):
        stop=min(start+8192,len(q))
        samples,_=scoring.quadrature(q[start:stop],bound[start:stop])
        scores.append(scoring.crps(samples,y[start:stop]))
    return pd.DataFrame({'mae':abs(residual),'bias':residual,
        'coverage90':((y>=low-TOL)&(y<=high+TOL)).astype(float),
        'width90':high-low,'interval_score90':high-low+20*(np.maximum(low-y,0)+np.maximum(y-high,0)),
        'crps':np.concatenate(scores),'zero90':(abs(high-low)<=TOL).astype(float)})


def cluster_bootstrap(groups, values, draws, seed):
    """Pooled case-weighted means after resampling entire connected groups."""
    groups=np.asarray(groups);values=np.asarray(values,float)
    if len(groups)!=len(values) or not len(groups) or not np.isfinite(values).all():raise ValueError('invalid cluster bootstrap data')
    _,inv=np.unique(groups,return_inverse=True)
    count=np.bincount(inv).astype(float);total=np.bincount(inv,weights=values)
    rng=np.random.default_rng(seed)
    selected=rng.integers(0,len(count),size=(draws,len(count)))
    sample=total[selected].sum(axis=1)/count[selected].sum(axis=1)
    return np.quantile(sample,[.025,.975]),float(np.mean(total/count))


def load_cases(evidence):
    path=evidence/'results/wrr_review_response_20261027/whole_archive/annual_case_evidence.parquet'
    f=pd.read_parquet(path)
    keys=['family','mode','replicate','station_key','year']
    if f.duplicated(keys).any():raise ValueError('duplicate annual case keys')
    roster=pd.read_parquet(evidence/'annual_source_cases/seed_00.parquet',columns=['station_key','region','independence_group']).drop_duplicates()
    if roster.station_key.duplicated().any():raise ValueError('station assigned multiple regions or groups')
    f=f.merge(roster,on=['station_key','independence_group'],validate='many_to_one',how='left')
    if f.region.isna().any():raise ValueError('missing or inconsistent station region/group')
    return f


def load_workspace_cases():
    """Read the original saved predictions without creating private copies."""
    chunks=[]
    cols=['station_key','independence_group','year','observed_lower_bound__observed_days','D2']
    cols += [f'{name}_q{q:02d}' for name in METHODS for q in LEVELS]
    for family in ('calendar','crossed'):
        for mode in ('offline','forward'):
            for path in sorted((OUTPUT/family/mode).glob('replicate_*/*/annual_predictions.parquet')):
                if pq.ParquetFile(path).metadata.num_rows==0:continue
                c=pd.read_parquet(path,columns=cols)
                c['family']=family;c['mode']=mode;c['replicate']=int(path.parent.parent.name.split('_')[-1])
                chunks.append(c)
    if not chunks:raise ValueError('no saved annual predictions')
    f=pd.concat(chunks,ignore_index=True)
    keys=['family','mode','replicate','station_key','year']
    if f.duplicated(keys).any():raise ValueError('duplicate annual case keys')
    source=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',
                           columns=['station_key','region','independence_group','year','design_family','eval_truth_h30'])
    roster=source[['station_key','region','independence_group']].drop_duplicates()
    if roster.station_key.duplicated().any():raise ValueError('station assigned multiple regions or groups')
    f=f.merge(roster,on=['station_key','independence_group'],validate='many_to_one',how='left')
    if f.region.isna().any():raise ValueError('missing or inconsistent station region/group')
    ref=source.groupby(['station_key','year','design_family'],dropna=False).eval_truth_h30.agg(['min','max','count'])
    if ref['count'].eq(0).any() or (ref['max']-ref['min']).gt(TOL).any():raise ValueError('inconsistent reference')
    ref=ref['min'].rename('reference_h30').reset_index().rename(columns={'design_family':'family'})
    f=f.merge(ref,on=['station_key','year','family'],validate='many_to_one',how='left')
    if f.reference_h30.isna().any():raise ValueError('missing complete reference')
    return f


def evaluate(frame,scoring,draws=2000):
    rows=[];pairs=[];cohorts=[]
    quantile_names=[f'{method}_q{level:02d}' for method in METHODS for level in LEVELS]
    for (family,mode),f in frame.groupby(['family','mode'],sort=True):
        qfinite=np.isfinite(f[quantile_names].to_numpy(float)).all(axis=1)
        ref=np.isfinite(f.reference_h30.to_numpy(float));bound=np.isfinite(f.observed_lower_bound__observed_days.to_numpy(float))
        common=qfinite&ref&bound;g=f.loc[common].copy().reset_index(drop=True)
        if g.empty:raise ValueError('empty common cohort')
        cohorts.append(dict(family=family,mode=mode,eligible=len(f),reference_finite=int(ref.sum()),
                            bound_finite=int(bound.sum()),both_quantile_sets_finite=int(qfinite.sum()),common=len(g)))
        g['stratum']=classify(g.reference_h30,g.observed_lower_bound__observed_days)
        y=g.reference_h30.to_numpy(float);b=g.observed_lower_bound__observed_days.to_numpy(float)
        for method in METHODS:
            q=g[[f'{method}_q{level:02d}' for level in LEVELS]].to_numpy(float)
            if np.any(q<b[:,None]-TOL):raise ValueError('predicted quantile below bound')
            vals=case_metrics(q,y,b,scoring)
            for m in METRICS:g[method+'_'+m]=vals[m].to_numpy()
        for stratum in ['all','bound_matches_reference','unobserved_peak_excess']:
            sub=g if stratum=='all' else g.loc[g.stratum.eq(stratum)]
            if sub.empty:continue
            counts=dict(family=family,mode=mode,stratum=stratum,n=len(sub),
                stations=int(sub.station_key.nunique()),station_years=len(sub[['station_key','year']].drop_duplicates()),
                groups=int(sub.independence_group.nunique()),regions=int(sub.region.nunique()))
            group=sub.independence_group.to_numpy()
            for method in METHODS:
                result=counts|{'estimator':'stochastic_calibrated' if method=='stochastic_cal' else method}
                for i,m in enumerate(METRICS):
                    val=sub[method+'_'+m].to_numpy(float)
                    ci,group_equal=cluster_bootstrap(group,val,draws,seed=123456+i)
                    result[m]=float(val.mean());result[m+'_group_equal']=group_equal
                    result[m+'_bootstrap_low']=float(ci[0]);result[m+'_bootstrap_high']=float(ci[1])
                rows.append(result)
            paired=counts.copy()
            for i,m in enumerate(['mae','coverage90','width90','interval_score90','crps']):
                diff=sub['D2_'+m].to_numpy(float)-sub['stochastic_cal_'+m].to_numpy(float)
                ci,group_equal=cluster_bootstrap(group,diff,draws,seed=812345+i)
                paired[m+'_D2_minus_stochastic']=float(diff.mean())
                paired[m+'_group_equal']=group_equal
                paired[m+'_bootstrap_low']=float(ci[0]);paired[m+'_bootstrap_high']=float(ci[1])
            pairs.append(paired)
    return pd.DataFrame(rows),pd.DataFrame(pairs),pd.DataFrame(cohorts)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=PRIVATE);p.add_argument('--workspace',action='store_true',help='read original saved predictions and reference rather than private case subset');p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--draws',type=int,default=2000);a=p.parse_args()
    if a.draws<100:raise ValueError('at least 100 bootstrap draws required')
    spec=importlib.util.spec_from_file_location('local_annual_scoring',ROOT/'scripts/576_verify_private_annual_predictions.py')
    scoring=importlib.util.module_from_spec(spec);spec.loader.exec_module(scoring)
    f=load_workspace_cases() if a.workspace else load_cases(a.evidence)
    rows,pairs,cohorts=evaluate(f,scoring,a.draws)
    support_path=OUTPUT/'support_projection_summary.csv' if a.workspace else a.evidence/'results/wrr_review_response_20261027/whole_archive/support_projection_summary.csv'
    support=pd.read_csv(support_path)
    all_rows=rows.loc[rows.stratum.eq('all')]
    matched=all_rows.merge(support,on=['family','mode','estimator'],validate='one_to_one')
    if len(matched)!=8 or not matched.n.eq(matched.paired_rows).all():raise ValueError('common cohort differs from support audit')
    if not np.allclose(matched.zero90*matched.n,matched.zero_width90,atol=TOL,rtol=0):raise ValueError('zero-width counts differ from support audit')
    truth_equal=rows.loc[rows.stratum.eq('bound_matches_reference')].merge(support,on=['family','mode','estimator'],validate='one_to_one')
    if not truth_equal.n.eq(truth_equal.truth_equal_bound).all():raise ValueError('reference-bound strata differ from support audit')
    a.output.mkdir(parents=True,exist_ok=True)
    rows.to_csv(a.output/'peak_visibility_annual.csv',index=False)
    pairs.to_csv(a.output/'peak_visibility_paired.csv',index=False)
    cohorts.to_csv(a.output/'peak_visibility_cohorts.csv',index=False)
    report={'status':'passed','annual_rows':len(f),'cohorts':len(cohorts),'bootstrap_draws':a.draws,
            'benchmark':'same two-estimator common finite-bound cases as the prior support audit',
            'strata':'reference H30 equals observed lower bound within 1e-8 C, or exceeds it by more than that tolerance',
            'bootstrap':'case-weighted means after resampling connected groups; repeated masks and regions remain dependent',
            'crps':'128 stratified quantile draws, linear interior and adjacent-normal tail continuation with observed support; tail law is an assumption',
            'limitation':'stratum requires complete hidden reference and is unavailable for deployment or model selection; finite reported records and mask designs are not independent climates; source sensor error is not evaluated'}
    (a.output/'peak_visibility_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(rows[['family','mode','stratum','estimator','n','stations','station_years','groups','coverage90','mae','width90','crps','zero90']].to_string(index=False))
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # A prior aggregate CSV can remain, so invalidate its status on failure.
        fallback=argparse.ArgumentParser(add_help=False)
        fallback.add_argument('--output',type=Path,default=OUTPUT)
        location,_=fallback.parse_known_args()
        location.output.mkdir(parents=True,exist_ok=True)
        (location.output/'peak_visibility_status.json').write_text(json.dumps({
            'status':'failed','error':f'{type(exc).__name__}: {exc}',
            'limitation':'a previous aggregate CSV may remain and must not be treated as a successful current analysis'
        },indent=2)+'\n')
        raise
