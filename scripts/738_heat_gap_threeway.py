#!/usr/bin/env python3
"""Compare all three masking designs on the same available archive settings.

This comparison was added after the pairwise results were observed. The three
scenarios reuse the same source fits, data, stations and model assumptions.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'heat_gap_matched'
PRIVATE=ROOT/'private/wrr_heat_gap_matched_20261027'
FOLDERS={'baseline':REV/'whole_archive',
         'previous_heat':ROOT/'private/wrr_expanded_stress_20261027/heat_associated_matched',
         'matched_heat':PRIVATE/'run'}
METHODS=['D2','stochastic_calibrated'];DEPS=['point','independent','shared_parameters','residual_blocks']
KEY=['station_key','replicate','estimator','retention','dependence']
FIELDS=['available','truth_slope','squared_error','missing_coverage95','width95','interval_score95','region','independence_group']


def load(folder,label):
    f=pd.read_csv(folder/'trends.csv')
    f=f[(f.family=='crossed')&(f['mode']=='forward')&(f.replicate<5)&(f.retention=='all')
        &f.estimator.isin(METHODS)&f.dependence.isin(DEPS)]
    if len(f)!=1640 or f.duplicated(KEY).any():raise ValueError('Unexpected scenario cohort')
    return f[KEY+FIELDS].rename(columns={col:label+'_'+col for col in FIELDS})


def main():
    merged=load(FOLDERS['baseline'],'baseline')
    for label in ['previous_heat','matched_heat']:
        merged=merged.merge(load(FOLDERS[label],label),on=KEY,validate='one_to_one')
    if len(merged)!=1640:raise ValueError('Three-way identities changed')
    rows=[];contrasts=[]
    for di,dep in enumerate(DEPS):
        x=merged[merged.dependence.eq(dep)].copy()
        x['all_available']=x[[k+'_available' for k in FOLDERS]].all(axis=1)
        flags=x.groupby(['station_key','replicate']).all_available.agg(['all','size'])
        if not flags['size'].eq(2).all():raise ValueError('Missing method')
        keys=set(flags.index[flags['all']])
        for mi,method in enumerate(METHODS):
            q=x[x.estimator.eq(method)]
            q=q[pd.MultiIndex.from_frame(q[['station_key','replicate']]).isin(keys)].copy()
            for label in ['previous_heat','matched_heat']:
                if not np.allclose(q.baseline_truth_slope,q[label+'_truth_slope'],atol=1e-9,rtol=0):
                    raise ValueError('Reference slope changed')
                if not q.baseline_independence_group.equals(q[label+'_independence_group']):raise ValueError('Connected group changed')
            for label in FOLDERS:
                r={'scenario':label,'estimator':method,'dependence':dep,'n_common':len(q),
                   'stations':q.station_key.nunique(),'groups':q.baseline_independence_group.nunique(),
                   'rmse':float(np.sqrt(q[label+'_squared_error'].mean())) if len(q) else np.nan}
                if dep!='point':
                    for field in ['missing_coverage95','width95','interval_score95']:r[field]=float(q[label+'_'+field].mean())
                rows.append(r)
            for ci,left in enumerate(['baseline','previous_heat']):
                delta=q.matched_heat_squared_error-q[left+'_squared_error']
                groups=q.assign(delta=delta).groupby('baseline_independence_group').delta.agg(['sum','count','mean'])
                rng=np.random.default_rng(73800+100*di+10*mi+ci)
                draws=rng.integers(len(groups),size=(4000,len(groups)))
                boot=groups['sum'].to_numpy()[draws].sum(axis=1)/groups['count'].to_numpy()[draws].sum(axis=1)
                contrasts.append({'left':left,'right':'matched_heat','estimator':method,'dependence':dep,
                                  'n_common':len(q),'groups':len(groups),'mse_difference':float(delta.mean()),
                                  'equal_group_mse_difference':float(groups['mean'].mean()),
                                  'bootstrap_low':float(np.quantile(boot,.025)), 'bootstrap_high':float(np.quantile(boot,.975))})
    pd.DataFrame(rows).to_csv(OUT/'threeway_summary.csv',index=False)
    pd.DataFrame(contrasts).to_csv(OUT/'threeway_contrasts.csv',index=False)
    status={'status':'computed_posthoc_after_pairwise_results','summary_rows':len(rows),'contrast_rows':len(contrasts),
            'scope':'All three scenario predictions and both methods available on same station-replicate, separately for each dependence construction.',
            'limitations':'Post-hoc intersection after pairwise results. Retained repeated masks are not independent climates; selected years and gap placement change together. Reuses same source models and observed target reference.'}
    (OUT/'threeway_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(pd.DataFrame(rows).query("dependence == 'independent'").to_string(index=False),flush=True)
    print(json.dumps(status,indent=2),flush=True)


if __name__=='__main__':main()
