#!/usr/bin/env python3
"""Recalculate three-way common-cohort scores from separate trend tables."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'heat_gap_matched'
FOLDERS={'baseline':REV/'whole_archive',
         'previous_heat':ROOT/'private/wrr_expanded_stress_20261027/heat_associated_matched',
         'matched_heat':ROOT/'private/wrr_heat_gap_matched_20261027/run'}
METHODS=['D2','stochastic_calibrated'];DEPS=['point','independent','shared_parameters','residual_blocks']
IDENTITY=['station_key','replicate','estimator','retention','dependence']


def close(a,b,name):
    if not np.isclose(a,b,atol=1e-10,rtol=1e-10,equal_nan=True):raise ValueError('Mismatch '+name)


def main():
    tables={}
    for name,folder in FOLDERS.items():
        f=pd.read_csv(folder/'trends.csv')
        f=f[(f.family=='crossed')&(f['mode']=='forward')&(f.replicate<5)&(f.retention=='all')
            &f.estimator.isin(METHODS)&f.dependence.isin(DEPS)].set_index(IDENTITY)
        if len(f)!=1640 or not f.index.is_unique:raise ValueError('Unexpected scenario roster')
        tables[name]=f
    if not all(t.index.sort_values().equals(tables['baseline'].index.sort_values()) for t in tables.values()):
        raise ValueError('Scenario identities differ')
    saved=pd.read_csv(OUT/'threeway_summary.csv');contrasts=pd.read_csv(OUT/'threeway_contrasts.csv');nc=nr=0
    for di,dep in enumerate(DEPS):
        baseline=tables['baseline'];base=baseline[baseline.index.get_level_values('dependence')==dep]
        candidates=[]
        for station,rep in sorted(set(zip(base.index.get_level_values('station_key'),base.index.get_level_values('replicate')))):
            ids=[(station,rep,method,'all',dep) for method in METHODS]
            if all(bool(t.loc[key,'available']) for t in tables.values() for key in ids):candidates.append((station,rep))
        for mi,method in enumerate(METHODS):
            ids=[(station,rep,method,'all',dep) for station,rep in candidates]
            values={name:t.loc[ids] for name,t in tables.items()}
            for name,v in values.items():
                row=saved[(saved.scenario==name)&(saved.estimator==method)&(saved.dependence==dep)]
                if len(row)!=1 or int(row.iloc[0].n_common)!=len(ids):raise ValueError('Three-way denominator differs')
                close(np.sqrt(v.squared_error.mean()),row.iloc[0].rmse,'three-way RMSE')
                if dep!='point':
                    for metric in ['missing_coverage95','width95','interval_score95']:close(v[metric].mean(),row.iloc[0][metric],metric)
                nr+=1
            target=values['matched_heat'];labels=values['baseline'].independence_group.to_numpy()
            for ci,left in enumerate(['baseline','previous_heat']):
                d=target.squared_error.to_numpy()-values[left].squared_error.to_numpy();groups=sorted(set(labels))
                sums=np.array([d[labels==g].sum() for g in groups]);counts=np.array([(labels==g).sum() for g in groups])
                rng=np.random.default_rng(73800+100*di+10*mi+ci);draws=rng.integers(len(groups),size=(4000,len(groups)))
                boot=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
                row=contrasts[(contrasts.left==left)&(contrasts.estimator==method)&(contrasts.dependence==dep)]
                if len(row)!=1 or int(row.iloc[0].n_common)!=len(ids):raise ValueError('Three-way contrast count differs')
                for key,val in [('mse_difference',d.mean()),('equal_group_mse_difference',(sums/counts).mean()),
                                ('bootstrap_low',np.quantile(boot,.025)),('bootstrap_high',np.quantile(boot,.975))]:
                    close(val,row.iloc[0][key],key)
                nc+=1
    if nr!=len(saved) or nc!=len(contrasts):raise ValueError('Not all three-way rows checked')
    result={'status':'passed','threeway_summary_rows_checked':nr,'threeway_contrast_rows_checked':nc,
            'scope':'Independently selects the same three-way shared cases and recalculates means and seeded group resampling. This shares all prediction and input data; it is not a new fit or an external validation.'}
    (OUT/'threeway_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
