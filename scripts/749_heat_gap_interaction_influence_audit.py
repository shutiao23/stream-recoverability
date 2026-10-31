#!/usr/bin/env python3
"""Recount post-hoc leave-one-group source interaction sensitivity."""
import json
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;S=T.load_script('gap_influence_audit_inputs',ROOT/'scripts/742_heat_gap_source_sensitivity.py')
KEY=['station_key','replicate'];METHODS=['D2','stochastic_calibrated'];VERSIONS=['strict_original','candidate']


def close(a,b,name):
    if not np.isclose(float(a),float(b),rtol=0,atol=1e-10,equal_nan=True):raise ValueError('Influence mismatch: '+name)


def main():
    S.verify_plan();f=pd.read_parquet(S.STAGE/'six_way_trends.parquet');f=f[f.dependence.eq('independent')]
    details=pd.read_parquet(S.STAGE/'source_interaction_leave_group.parquet')
    summary=pd.read_csv(S.OUT/'source_interaction_influence_summary.csv')
    size=f.groupby(KEY).size();available=f.groupby(KEY).available.all()
    if len(size)!=205 or not size.eq(12).all():raise ValueError('Unexpected source cohort')
    selected=set(available[available].index);verified=0
    for mi,method in enumerate(METHODS):
        x=f[f.estimator.eq(method)&pd.MultiIndex.from_frame(f[KEY]).isin(selected)]
        cells={}
        for version in ['original']+VERSIONS:
            for side in ['baseline','stress']:
                cells[version,side]=x[x.version.eq(version)&x.side.eq(side)].set_index(KEY).sort_index()
        ref=cells['original','baseline'];labels=ref.independence_group.to_numpy()
        d0=cells['original','stress'].squared_error.to_numpy()-ref.squared_error.to_numpy()
        for vi,version in enumerate(VERSIONS):
            a=cells[version,'baseline'];b=cells[version,'stress']
            if not a.index.equals(ref.index) or not b.index.equals(ref.index):raise ValueError('Case identities differ')
            delta=b.squared_error.to_numpy()-a.squared_error.to_numpy()-d0;names=sorted(set(labels));recount=[]
            for gi,excluded in enumerate(names):
                remain=[g for g in names if g!=excluded]
                sums=np.array([delta[labels==g].sum() for g in remain]);counts=np.array([(labels==g).sum() for g in remain])
                draw=np.random.default_rng(74800+1000*mi+100*vi+gi).integers(len(remain),size=(40000,len(remain)))
                boot=sums[draw].sum(axis=1)/counts[draw].sum(axis=1)
                low,high=np.quantile(boot,[.025,.975]);row=details[(details.estimator==method)&(details.comparison==version+'_minus_original')&details.excluded_group.eq(excluded)]
                if len(row)!=1 or int(row.iloc[0].n_retained)!=int(counts.sum()):raise ValueError('Influence denominator differs')
                r=row.iloc[0]
                for name,value in [('mean',sums.sum()/counts.sum()),('group_equal_mean',(sums/counts).mean()),('bootstrap_low',low),('bootstrap_high',high)]:close(value,r[name],name)
                recount.append((low,high));verified+=1
            q=summary[(summary.estimator==method)&(summary.comparison==version+'_minus_original')]
            if len(q)!=1 or int(q.iloc[0].excluded_groups_tested)!=len(names):raise ValueError('Influence summary missing')
            low=np.array([v[0] for v in recount]);high=np.array([v[1] for v in recount])
            for field,value in [('intervals_crossing_or_touching_zero',((low<=0)&(high>=0)).sum()),
                                ('intervals_entirely_below_zero',(high<0).sum()),('intervals_entirely_above_zero',(low>0).sum())]:
                if int(q.iloc[0][field])!=int(value):raise ValueError('Influence category differs')
    if verified!=len(details) or len(summary)!=4:raise ValueError('Unchecked influence outputs')
    report={'status':'passed','leave_group_rows_checked':verified,'aggregate_rows_checked':len(summary),'bootstrap_draws_per_exclusion':40000,
            'scope':'Recounts fixed-prediction group exclusions and seeded resampling using the same underlying observations and saved source predictions. Does not refit models or validate a new climate.'}
    (S.OUT/'source_interaction_influence_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
