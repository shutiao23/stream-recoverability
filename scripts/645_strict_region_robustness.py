#!/usr/bin/env python3
"""Paired group and leave-region-out robustness for strict forward refits."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'strict_region_holdout';PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
KEY=['family','mode','station_key','independence_group','region','replicate']


def bootstrap_pairs(block,draws=4000,seed=645):
    """Resample groups once for both models and both source versions."""
    if block.independence_group.isna().any() or not np.isfinite(block[['old_difference','strict_difference']].to_numpy(float)).all():raise ValueError('invalid paired group values')
    groups=block.groupby('independence_group',sort=True).agg(old_sum=('old_difference','sum'),strict_sum=('strict_difference','sum'),count=('old_difference','size'),old_equal=('old_difference','mean'),strict_equal=('strict_difference','mean'))
    if groups.empty:raise ValueError('empty paired group cohort')
    rng=np.random.default_rng(seed);index=rng.integers(len(groups),size=(draws,len(groups)))
    counts=groups['count'].to_numpy()[index].sum(axis=1)
    old=groups.old_sum.to_numpy()[index].sum(axis=1)/counts;strict=groups.strict_sum.to_numpy()[index].sum(axis=1)/counts
    oldeq=groups.old_equal.to_numpy()[index].mean(axis=1);stricteq=groups.strict_equal.to_numpy()[index].mean(axis=1)
    result={}
    for label,v in [('old_pooled',old),('strict_pooled',strict),('strict_minus_old',strict-old),('old_equal',oldeq),('strict_equal',stricteq)]:
        result[label+'_low'],result[label+'_high']=map(float,np.quantile(v,[.025,.975]))
    return result


def main():
    check=json.loads((OUT/'archive_pooled_status.json').read_text())
    if check['status']!='passed' or check['strict_archive_settings']!=120:raise ValueError('strict archive settings incomplete')
    old=pd.read_csv(REV/'whole_archive/trends.csv');old=old.loc[old['mode'].eq('forward')&old.retention.eq('all')&old.dependence.eq('point')].copy()
    paths=sorted((PRIVATE/'whole_archive').glob('*/forward/replicate_*/*/trends.csv'))
    if len(paths)!=120:raise ValueError('strict trend files incomplete')
    change=pd.concat([pd.read_csv(p) for p in paths],ignore_index=True);change=change.loc[change.retention.eq('all')&change.dependence.eq('point')]
    keys=KEY+['estimator'];old_subset=old.loc[old.region.eq('usgs_huc17')]
    joined=old_subset.merge(change,on=keys,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
    if not joined._merge.eq('both').all():raise ValueError('strict original trend keys differ')
    if not np.allclose(joined.truth_slope_original,joined.truth_slope_strict,rtol=0,atol=1e-8,equal_nan=True):raise ValueError('strict target slope differs')
    new=pd.concat([old.loc[~old.region.eq('usgs_huc17')],change.reindex(columns=old.columns)],ignore_index=True)
    if old.duplicated(keys).any() or new.duplicated(keys).any():raise ValueError('duplicate station-repetition estimator keys')
    wide_old=old.pivot(index=KEY,columns='estimator',values='squared_error');wide_new=new.pivot(index=KEY,columns='estimator',values='squared_error')
    combined=wide_old.join(wide_new,how='outer',lsuffix='_original',rsuffix='_strict').reset_index()
    prior=pd.read_csv(REV/'robustness/paired_cluster_bootstrap.csv');prior=prior.loc[prior['mode'].eq('forward')]
    pairs=[];loo=[]
    for family,group in combined.groupby('family',sort=True):
        for right in ['stochastic_calibrated','plug_in']:
            required=['D2_original',right+'_original','D2_strict',right+'_strict']
            g=group.dropna(subset=required).copy()
            g['old_difference']=g.D2_original-g[right+'_original'];g['strict_difference']=g.D2_strict-g[right+'_strict']
            oldprior=prior.loc[prior.family.eq(family)&prior.left.eq('D2')&prior.right.eq(right)]
            if len(oldprior)!=1:raise ValueError('old baseline not unique')
            q=oldprior.iloc[0]
            # The current strict and original four-way common set must reproduce
            # the earlier two-arm denominator; otherwise report a cohort change.
            if len(g)!=q.n_common or not np.isclose(g.old_difference.mean(),q.pooled_mse_difference,atol=1e-10):raise ValueError('four-way cohort differs from original comparator')
            by=g.groupby('independence_group').agg(old=('old_difference','mean'),strict=('strict_difference','mean'))
            row={'family':family,'mode':'forward','left':'D2','right':right,'n_common':len(g),'n_stations':g.station_key.nunique(),'n_groups':g.independence_group.nunique(),
               'original_pooled_mse_difference':float(g.old_difference.mean()),'strict_pooled_mse_difference':float(g.strict_difference.mean()),
               'original_group_equal_mse_difference':float(by.old.mean()),'strict_group_equal_mse_difference':float(by.strict.mean())}|bootstrap_pairs(g)
            pairs.append(row)
            for region in sorted(g.region.unique()):
                h=g.loc[g.region.ne(region)]
                loo.append({'family':family,'mode':'forward','left':'D2','right':right,'excluded_region':region,'n_remaining':len(h),'n_groups':h.independence_group.nunique(),
                  'original_pooled_mse_difference':float(h.old_difference.mean()),'strict_pooled_mse_difference':float(h.strict_difference.mean())})
    pairs=pd.DataFrame(pairs);loo=pd.DataFrame(loo)
    prior_loo=pd.read_csv(REV/'robustness/leave_one_region_out.csv');prior_loo=prior_loo.loc[prior_loo['mode'].eq('forward')]
    verify=loo.merge(prior_loo,on=['family','mode','left','right','excluded_region'],validate='one_to_one')
    if len(verify)!=len(loo) or not verify.n_remaining_x.eq(verify.n_remaining_y).all() or not np.allclose(verify.original_pooled_mse_difference,verify.pooled_mse_difference,atol=1e-10,rtol=0):raise ValueError('original leave-region-out result not reproduced')
    pairs.to_csv(OUT/'robustness_paired_bootstrap.csv',index=False);loo.to_csv(OUT/'robustness_leave_one_region_out.csv',index=False)
    status={'status':'passed','original_pooled_and_leave_region_out_reproduced':True,'bootstrap_resamples':4000,
      'cohort':'same station and mask repetition cases available for D2 and comparator in both original and strict source versions',
      'resampling':'resample recorded connected groups jointly across versions and estimators; report case-weighted and equal-group contrasts',
      'limitation':'post-hoc descriptive sensitivity, 17 forward connected groups maximum; region removal is not refitting and group/climate exchangeability is not established'}
    (OUT/'robustness_status.json').write_text(json.dumps(status,indent=2)+'\n');print(pairs.to_string(index=False));print(loo.loc[loo.excluded_region.eq('gkd_bayern')].to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
