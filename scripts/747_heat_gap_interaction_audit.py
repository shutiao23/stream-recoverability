#!/usr/bin/env python3
"""Independently recount matched-gap source-by-stress MSE interactions."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;S=T.load_script('gap_interaction_audit_inputs',ROOT/'scripts/742_heat_gap_source_sensitivity.py')
METHODS=['D2','stochastic_calibrated'];DEPS=['point','independent','shared_parameters','residual_blocks']
KEY=['station_key','replicate']


def equal(a,b,name):
    if not np.isclose(float(a),float(b),atol=1e-10,rtol=0,equal_nan=True):raise ValueError('Interaction mismatch: '+name)


def main():
    S.verify_plan()
    f=pd.read_parquet(S.STAGE/'six_way_trends.parquet');saved=pd.read_csv(S.OUT/'source_interactions.csv')
    if len(f)!=9840 or len(saved)!=16:raise ValueError('Input or output interaction cohort differs')
    checked=0
    for di,dep in enumerate(DEPS):
        x=f[f.dependence.eq(dep)];counts=x.groupby(KEY).size();good=x.groupby(KEY).available.all()
        if len(counts)!=205 or not counts.eq(12).all():raise ValueError('Both-method source cells missing')
        selected=set(good[good].index)
        for mi,method in enumerate(METHODS):
            block=x[x.estimator.eq(method)&pd.MultiIndex.from_frame(x[KEY]).isin(selected)]
            cells={}
            for version in ['original','strict_original','candidate']:
                for side in ['baseline','stress']:
                    z=block[block.version.eq(version)&block.side.eq(side)].set_index(KEY).sort_index()
                    if len(z)!=len(selected) or not z.index.is_unique:raise ValueError('Paired version cells differ')
                    cells[version,side]=z
            ref=cells['original','baseline'];labels=ref.independence_group.to_numpy()
            d0=cells['original','stress'].squared_error.to_numpy()-ref.squared_error.to_numpy()
            for vi,version in enumerate(['strict_original','candidate']):
                a=cells[version,'baseline'];b=cells[version,'stress']
                if not a.index.equals(ref.index) or not b.index.equals(ref.index):raise ValueError('Source interaction identity differs')
                delta=b.squared_error.to_numpy()-a.squared_error.to_numpy()-d0
                names=sorted(set(labels));sums=np.array([delta[labels==g].sum() for g in names]);sizes=np.array([(labels==g).sum() for g in names])
                draws=np.random.default_rng(74600+10*mi+vi).integers(len(names),size=(40000,len(names)))
                boot=sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)
                row=saved[(saved.estimator==method)&(saved.dependence==dep)&(saved.comparison==version+'_minus_original')]
                if len(row)!=1 or int(row.iloc[0].n_common)!=len(ref):raise ValueError('Interaction denominator differs')
                r=row.iloc[0]
                for name,value in [('interaction_mean',delta.mean()),('interaction_group_equal',(sums/sizes).mean()),
                                   ('bootstrap_low',np.quantile(boot,.025)),('bootstrap_high',np.quantile(boot,.975)),
                                   ('nonzero_cases',np.count_nonzero(abs(delta)>1e-10)),
                                   ('nonzero_groups',len(set(labels[abs(delta)>1e-10])))]:equal(value,r[name],name)
                checked+=1
    if checked!=len(saved):raise ValueError('Unchecked interaction cells remain')
    report={'status':'passed','interaction_rows_checked':checked,'bootstrap_draws_per_cell':40000,
            'scope':'Recomputes paired source-by-stress MSE differences and seeded group resampling from the same saved predictions; not a new fit, independent climate or causal attribution.'}
    (S.OUT/'source_interactions_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
