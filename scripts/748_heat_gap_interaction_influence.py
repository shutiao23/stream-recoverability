#!/usr/bin/env python3
"""Post-hoc leave-one-group influence on matched-gap source interactions.

This uses fixed saved predictions and was designed after seeing a near-zero
bootstrap endpoint. Station/group identities in intermediate rows stay local.
"""
import os
os.umask(0o077)
import json
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;S=T.load_script('gap_influence_inputs',ROOT/'scripts/742_heat_gap_source_sensitivity.py')
KEY=['station_key','replicate'];METHODS=['D2','stochastic_calibrated'];VERSIONS=['strict_original','candidate']


def main():
    S.verify_plan()
    if json.loads((S.OUT/'source_interactions_independent_audit.json').read_text())['status']!='passed':
        raise ValueError('Source interaction audit incomplete')
    f=pd.read_parquet(S.STAGE/'six_way_trends.parquet');f=f[f.dependence.eq('independent')]
    counts=f.groupby(KEY).size();available=f.groupby(KEY).available.all()
    if len(counts)!=205 or not counts.eq(12).all():raise ValueError('Unexpected source cohort')
    keys=set(available[available].index);details=[]
    for mi,method in enumerate(METHODS):
        x=f[f.estimator.eq(method)&pd.MultiIndex.from_frame(f[KEY]).isin(keys)].copy();x['cell']=x.version+'_'+x.side
        wide=x.pivot(index=KEY+['region','independence_group'],columns='cell',values='squared_error').reset_index()
        if len(wide)!=len(keys):raise ValueError('Paired interaction cohort differs')
        original=wide.original_stress-wide.original_baseline
        for vi,version in enumerate(VERSIONS):
            delta=(wide[version+'_stress']-wide[version+'_baseline'])-original
            clusters=wide.assign(delta=delta).groupby('independence_group').delta.agg(['sum','count','mean'])
            for gi,group in enumerate(clusters.index):
                kept=clusters.drop(index=group)
                draws=np.random.default_rng(74800+1000*mi+100*vi+gi).integers(len(kept),size=(40000,len(kept)))
                boot=kept['sum'].to_numpy()[draws].sum(axis=1)/kept['count'].to_numpy()[draws].sum(axis=1)
                details.append({'estimator':method,'comparison':version+'_minus_original','excluded_group':group,
                                'n_retained':int(kept['count'].sum()),'groups_retained':len(kept),
                                'mean':float(kept['sum'].sum()/kept['count'].sum()),
                                'group_equal_mean':float(kept['mean'].mean()),
                                'bootstrap_low':float(np.quantile(boot,.025)),'bootstrap_high':float(np.quantile(boot,.975))})
    d=pd.DataFrame(details)
    if len(d)!=68 or d.duplicated(['estimator','comparison','excluded_group']).any():raise ValueError('Influence cohort differs')
    path=S.STAGE/'source_interaction_leave_group.parquet';d.to_parquet(path,index=False);path.chmod(0o600)
    rows=[]
    for (method,comparison),g in d.groupby(['estimator','comparison'],sort=True):
        rows.append({'estimator':method,'comparison':comparison,'excluded_groups_tested':len(g),
                     'intervals_crossing_or_touching_zero':int(((g.bootstrap_low<=0)&(g.bootstrap_high>=0)).sum()),
                     'intervals_entirely_below_zero':int((g.bootstrap_high<0).sum()),
                     'intervals_entirely_above_zero':int((g.bootstrap_low>0).sum()),
                     'minimum_mean':float(g['mean'].min()),'maximum_mean':float(g['mean'].max()),
                     'minimum_upper':float(g.bootstrap_high.min()),'maximum_upper':float(g.bootstrap_high.max())})
    result=pd.DataFrame(rows);result.to_csv(S.OUT/'source_interaction_influence_summary.csv',index=False)
    report={'status':'computed_posthoc_after_near_zero_interval','leave_group_cases':len(d),'summary_rows':len(result),
            'bootstrap_draws_per_exclusion':40000,
            'scope':'Remove one connected group and recompute a fixed-prediction source-by-stress contrast and cluster-resampled interval. Per-group identities remain local.',
            'limitations':'Selected after observing a near-zero endpoint. Resampling depends on the remaining groups; source models and target cases are not refitted, and this is not an independent climate or a causal test.'}
    (S.OUT/'source_interaction_influence_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(result.to_string(index=False),flush=True)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
