#!/usr/bin/env python3
"""Paired change-of-MSE contrasts between source versions on common cases.

Added after source-specific results were examined; this is descriptive and
does not identify the separate effects of source region, provider or roles.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
S=T.load_script('gap_source_interaction_inputs',ROOT/'scripts/742_heat_gap_source_sensitivity.py')
METHODS=['D2','stochastic_calibrated'];DEPS=['point','independent','shared_parameters','residual_blocks']
VERSIONS=['original','strict_original','candidate'];SIDES=['baseline','stress'];KEY=['station_key','replicate']


def main():
    S.verify_plan()
    if json.loads((S.OUT/'independent_audit.json').read_text())['status']!='passed':raise ValueError('Previous source audit incomplete')
    f=pd.read_parquet(S.STAGE/'six_way_trends.parquet')
    if len(f)!=9840 or f.duplicated(KEY+['estimator','dependence','version','side']).any():raise ValueError('Unexpected source cases')
    rows=[]
    for di,dep in enumerate(DEPS):
        block=f[f.dependence.eq(dep)];size=block.groupby(KEY).size();valid=block.groupby(KEY).available.all()
        if len(size)!=205 or not size.eq(12).all():raise ValueError('Both-method source cells are incomplete')
        keys=set(valid[valid].index)
        for mi,method in enumerate(METHODS):
            x=block[block.estimator.eq(method)&pd.MultiIndex.from_frame(block[KEY]).isin(keys)].copy()
            x['cell']=x.version+'_'+x.side
            wide=x.pivot(index=KEY+['region','independence_group'],columns='cell',values='squared_error').reset_index()
            if len(wide)!=len(keys):raise ValueError('Common source identities changed')
            baseline_delta=wide.original_stress-wide.original_baseline
            for vi,version in enumerate(['strict_original','candidate']):
                delta=(wide[version+'_stress']-wide[version+'_baseline'])-baseline_delta
                groups=wide.assign(d=delta).groupby('independence_group').d.agg(['sum','count','mean'])
                # The four dependence representations share point predictions;
                # use the same random stream when their cohorts coincide.
                draws=np.random.default_rng(74600+10*mi+vi).integers(len(groups),size=(40000,len(groups)))
                boot=groups['sum'].to_numpy()[draws].sum(axis=1)/groups['count'].to_numpy()[draws].sum(axis=1)
                rows.append({'estimator':method,'dependence':dep,'comparison':version+'_minus_original',
                             'n_common':len(wide),'stations':int(wide.station_key.nunique()),'groups':len(groups),
                             'interaction_mean':float(delta.mean()),'interaction_group_equal':float(groups['mean'].mean()),
                             'bootstrap_low':float(np.quantile(boot,.025)),'bootstrap_high':float(np.quantile(boot,.975)),
                             'nonzero_cases':int(delta.abs().gt(1e-10).sum()),
                             'nonzero_groups':int(wide.loc[delta.abs().gt(1e-10),'independence_group'].nunique())})
    result=pd.DataFrame(rows)
    if len(result)!=16:raise ValueError('Incomplete interaction table')
    result.to_csv(S.OUT/'source_interactions.csv',index=False)
    report={'status':'computed_posthoc_after_source_results','rows':len(result),'bootstrap_draws':40000,
            'definition':'(stress MSE - baseline MSE) for alternate source minus the same difference for original source, per archive.',
            'limitations':'Both-method six-way available intersection; source sample, provider and roles may change together. The resampling stream and draw count were corrected after inspecting preliminary results, which are retained. Group bootstrap depends on sampled groups; not a causal attribution, new climate or independent fit.'}
    (S.OUT/'source_interactions_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(result.query("dependence == 'independent'").to_string(index=False),flush=True)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
