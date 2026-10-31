#!/usr/bin/env python3
"""Audit one-dimensional source training support for partial-history inputs."""
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def weighted_quantile(values,weights,p):
    if not len(values) or (weights<=0).any():raise ValueError('No positive finite weighted sample')
    order=np.argsort(values,kind='mergesort');v=values[order];w=weights[order]
    return float(v[np.searchsorted(np.cumsum(w),p*float(w.sum()),side='left')])

def flags(x,lo,hi,qlo,qhi,has_nan,has_posinf,has_neginf):
    x=np.asarray(x,float);finite=np.isfinite(x)
    out=finite & ((x<lo)|(x>hi)) if np.isfinite(lo) and np.isfinite(hi) else finite
    tail=finite & ((x<qlo)|(x>qhi)) if np.isfinite(qlo) and np.isfinite(qhi) else finite
    unseen=(np.isnan(x)&(not has_nan))|(np.isposinf(x)&(not has_posinf))|(np.isneginf(x)&(not has_neginf))
    return out,tail,unseen

def summarize(a,case,feature_names):
    names=np.asarray(feature_names);keep=names!='n_complete_years'
    out,tail,unseen=a
    return {'cases':len(case),'outside_minmax_cases':int(out.any(axis=1).sum()),
      'outside_minmax_excluding_complete_count_cases':int(out[:,keep].any(axis=1).sum()),
      'unseen_nonfinite_cases':int(unseen.any(axis=1).sum()),
      'any_minmax_or_unseen_cases':int((out|unseen).any(axis=1).sum()),
      'any_minmax_or_unseen_excluding_complete_count_cases':int((out|unseen)[:,keep].any(axis=1).sum()),
      'weighted_tail_cases':int(tail.any(axis=1).sum()),
      'median_features_outside_minmax':float(np.median(out.sum(axis=1))),
      'max_features_outside_minmax':int(out.sum(axis=1).max())}

def main():
    helper=T.load_script('usace_feature_support_plan',ROOT/'scripts/856_partial_history_feature_support_plan.py');p=json.loads((OUT/'partial_history_feature_support_plan.json').read_text())
    source,groups,weights,bundle=helper.roles();fit=weights['estimator']>0
    other=((weights['interval_calibration']>0)|(weights['risk_learning']>0)|(weights['rule_calibration']>0))&source.design_family.eq('crossed').to_numpy()
    if int(fit.sum())!=p['source_estimator_positive_rows'] or (fit&other).any():raise ValueError('Estimator-role reconstruction changed')
    target=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet')
    if len(target)!=306 or not target.n_complete_years.eq(0).all():raise ValueError('External input cohort changed')
    features=bundle['features'];x=F.design_matrix(source,simulation=True).reindex(columns=features)
    y=F.design_matrix(target,simulation=True).reindex(columns=features)
    # Source model weights are integer bootstrap multiplicities; positive
    # weights define the exact estimator fit population.
    w=np.asarray(weights['estimator'][fit],float)
    if not np.all(w==np.round(w)):raise ValueError('Expected bootstrap multiplicities')
    train=x.loc[fit];hold=x.loc[other];m=len(features)
    target_flags=[np.zeros((len(target),m),bool) for _ in range(3)]
    hold_flags=[np.zeros((len(hold),m),bool) for _ in range(3)]
    rows=[]
    for j,name in enumerate(features):
        values=train[name].to_numpy(float);finite=np.isfinite(values);nan=np.isnan(values);pos=np.isposinf(values);neg=np.isneginf(values)
        if finite.any():
            low=float(values[finite].min());high=float(values[finite].max())
            qlow=weighted_quantile(values[finite],w[finite],.01);qhigh=weighted_quantile(values[finite],w[finite],.99)
        else:low=high=qlow=qhigh=float('nan')
        ft=flags(y[name].to_numpy(float),low,high,qlow,qhigh,nan.any(),pos.any(),neg.any())
        fh=flags(hold[name].to_numpy(float),low,high,qlow,qhigh,nan.any(),pos.any(),neg.any())
        for k in range(3):target_flags[k][:,j]=ft[k];hold_flags[k][:,j]=fh[k]
        rows.append({'feature':name,'source_estimator_finite_rows':int(finite.sum()),'source_estimator_finite_weight':float(w[finite].sum()),
          'source_estimator_nan_rows':int(nan.sum()),'source_estimator_posinf_rows':int(pos.sum()),'source_estimator_neginf_rows':int(neg.sum()),
          'source_min':low,'source_max':high,'source_weighted_q01':qlow,'source_weighted_q99':qhigh,
          'target_finite_cases':int(np.isfinite(y[name].to_numpy(float)).sum()),'target_outside_minmax':int(ft[0].sum()),
          'target_outside_weighted_q01_q99':int(ft[1].sum()),'target_unseen_nonfinite':int(ft[2].sum()),
          'source_other_crossed_cases':len(hold),'source_other_outside_minmax':int(fh[0].sum()),
          'source_other_outside_weighted_q01_q99':int(fh[1].sum()),'source_other_unseen_nonfinite':int(fh[2].sum())})
    table=pd.DataFrame(rows);dest=PRIVATE/'partial_history_feature_support.csv';table.to_csv(dest,index=False);dest.chmod(0o600)
    names=np.asarray(features);keep=names!='n_complete_years';case=target[['resource_id','year','realization_id']].copy()
    case['outside_minmax_count']=target_flags[0].sum(axis=1);case['outside_minmax_excluding_complete_count']=target_flags[0][:,keep].sum(axis=1)
    case['unseen_nonfinite_count']=target_flags[2].sum(axis=1);case['flagged_feature_names']=[';'.join(names[target_flags[0][i]|target_flags[2][i]]) for i in range(len(target))]
    cpath=PRIVATE/'partial_history_feature_support_cases.csv';case.to_csv(cpath,index=False);cpath.chmod(0o600)
    # Results without raw training bounds can be shared as a local review
    # candidate; feature values and case-level outputs remain restricted.
    report=table.drop(columns=['source_min','source_max','source_weighted_q01','source_weighted_q99'])
    report.to_csv(OUT/'partial_history_feature_support_summary.csv',index=False)
    target_sum=summarize(target_flags,target,features);hold_sum=summarize(hold_flags,hold,features)
    target_sum.update(station_years=len(target[['resource_id','year']].drop_duplicates()),sites=target.resource_id.nunique(),
       station_years_any_excluding_complete_count=len(case.loc[case.outside_minmax_excluding_complete_count.gt(0),['resource_id','year']].drop_duplicates()),
       sites_any_excluding_complete_count=case.loc[case.outside_minmax_excluding_complete_count.gt(0),'resource_id'].nunique())
    result={'status':'completed_posthoc_feature_support','features':m,'source_fit_rows':len(train),'source_fit_total_weight':float(w.sum()),
      'source_fit_groups':int(source.loc[fit,'independence_group'].nunique()),'source_non_estimator_crossed_rows':len(hold),
      'target':target_sum,'source_non_estimator_crossed':hold_sum,
      'limits':p['limits']}
    (OUT/'partial_history_feature_support_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));print(report.sort_values('target_outside_minmax',ascending=False).head(15).to_string(index=False))

if __name__=='__main__':main()
