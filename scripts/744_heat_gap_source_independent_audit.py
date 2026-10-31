#!/usr/bin/env python3
"""Independently recount six-way matched-gap source comparisons.

The saved models and target data are shared; this is not independent climate,
physical-data validation, or retraining of the source and daily estimators.
"""
from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T

ROOT=T.ROOT
S=T.load_script('gap_source_independent_inputs',ROOT/'scripts/742_heat_gap_source_sensitivity.py')
VERSIONS=['original','strict_original','candidate'];SIDES=['baseline','stress']
DEPS=['point','independent','shared_parameters','residual_blocks'];METHODS=['D2','stochastic_calibrated']
AK=['station_key','replicate'];ID=AK+['estimator','dependence','version','side']


def close(a,b,label):
    if not np.isclose(float(a),float(b),atol=1e-9,rtol=0,equal_nan=True):raise ValueError('Independent mismatch: '+label)


def verify_stored_daily_features():
    """Compare every non-source-model output column in the stored cases."""
    exclusions={'D2','P2','risk_score'}|{f'{prefix}_q{level:02d}' for prefix in ['D2','stochastic_cal','state_cal'] for level in [5,10,25,50,75,90,95]}
    roster=pd.read_csv(S.EXP/'roster.csv');files=rows=0
    for site in roster.itertuples(index=False):
        for rep in range(5):
            rel=S.M.suffix(site.station_key,rep);original=S.GAP/rel/'annual_predictions.parquet'
            versions=['candidate']+(['strict_original'] if site.region=='usgs_huc17' else [])
            for version in versions:
                target=S.STAGE/version/'heat_gap_matched'/rel/'annual_predictions.parquet'
                a=pq.read_table(original);b=pq.read_table(target)
                if a.column_names!=b.column_names or a.num_rows!=b.num_rows:raise ValueError('Saved case schema or rows changed')
                columns=[name for name in a.column_names if name not in exclusions]
                if not a.select(columns).equals(b.select(columns),check_metadata=False):
                    raise ValueError('Non-model daily feature or target metadata changed')
                files+=1;rows+=a.num_rows
    if files!=220:raise ValueError('Incomplete daily-feature replay cohort')
    return files,rows


def main():
    S.verify_plan()
    feature_files,feature_rows=verify_stored_daily_features()
    raw=pd.read_parquet(S.STAGE/'six_way_trends.parquet');saved=pd.read_csv(S.OUT/'six_way_summary.csv');leave=pd.read_csv(S.OUT/'leave_region_out.csv')
    if len(raw)!=9840 or raw.duplicated(ID).any():raise ValueError('Unexpected source-version case cohort')
    original=raw[raw.version.eq('original')&raw.region.ne('usgs_huc17')]
    strict=raw[raw.version.eq('strict_original')&raw.region.ne('usgs_huc17')]
    compare=original.merge(strict,on=AK+['estimator','dependence','side'],suffixes=('_a','_b'),validate='one_to_one')
    if len(compare)!=len(original) or not compare.available_a.eq(compare.available_b).all():raise ValueError('Unaffected source region differs')
    for metric in ['truth_slope','error','squared_error','missing_coverage95','width95','interval_score95']:
        a=pd.to_numeric(compare[metric+'_a'],errors='coerce');b=pd.to_numeric(compare[metric+'_b'],errors='coerce')
        if not np.allclose(a,b,atol=1e-12,rtol=0,equal_nan=True):raise ValueError('Unaffected source region changed '+metric)
    checked=region_checked=0
    for di,dep in enumerate(DEPS):
        d=raw[raw.dependence.eq(dep)]
        flags={}
        for method in METHODS:
            g=d[d.estimator.eq(method)]
            size=g.groupby(AK).size();available=g.groupby(AK).available.all()
            if len(size)!=205 or not size.eq(6).all():raise ValueError('Six-way source denominator differs')
            flags[method]=set(available[available].index)
        for mi,method in enumerate(METHODS):
            block=d[d.estimator.eq(method)]
            for scope in ['estimator_six_way','both_methods_six_way']:
                selected=flags[method] if scope=='estimator_six_way' else flags[METHODS[0]]&flags[METHODS[1]]
                common=block[pd.MultiIndex.from_frame(block[AK]).isin(selected)].copy()
                if len(common)!=len(selected)*6:raise ValueError('Selected source cells incomplete')
                interval_keys=set(selected)
                if dep!='point':
                    complete=np.isfinite(common[['missing_coverage95','width95','interval_score95']].to_numpy(float)).all(axis=1)
                    valid=common.assign(finite=complete).groupby(AK).finite.all()
                    interval_keys=set(valid[valid].index)
                for vi,version in enumerate(VERSIONS):
                    r=saved[(saved.estimator==method)&(saved.dependence==dep)&(saved.scope==scope)&(saved.version==version)]
                    if len(r)!=1:raise ValueError('Summary cell missing')
                    r=r.iloc[0]
                    if int(r.n_eligible)!=205 or int(r.n_common)!=len(selected):raise ValueError('Common source denominator differs')
                    for side in SIDES:
                        count=block[block.version.eq(version)&block.side.eq(side)].available.sum()
                        if int(r[side+'_available'])!=int(count):raise ValueError('Source availability differs')
                    a=common[common.version.eq(version)&common.side.eq('baseline')].set_index(AK).sort_index()
                    b=common[common.version.eq(version)&common.side.eq('stress')].set_index(AK).sort_index()
                    if not a.index.equals(b.index):raise ValueError('Paired archive identities differ')
                    if len(a):
                        close(np.sqrt(a.squared_error.mean()),r.baseline_rmse,'baseline RMSE')
                        close(np.sqrt(b.squared_error.mean()),r.stress_rmse,'stress RMSE')
                        delta=b.squared_error.to_numpy(float)-a.squared_error.to_numpy(float);labels=a.independence_group.to_numpy()
                        names=sorted(set(labels));sums=np.array([delta[labels==v].sum() for v in names]);counts=np.array([(labels==v).sum() for v in names])
                        close(delta.mean(),r.mse_difference,'mean paired MSE')
                        close((sums/counts).mean(),r.equal_group_mse_difference,'group-equal paired MSE')
                        seed=74300+1000*di+100*mi+10*vi+(scope=='both_methods_six_way')
                        draws=np.random.default_rng(seed).integers(len(names),size=(4000,len(names)))
                        boot=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
                        close(np.quantile(boot,.025),r.bootstrap_low,'bootstrap lower')
                        close(np.quantile(boot,.975),r.bootstrap_high,'bootstrap upper')
                        if dep!='point':
                            if int(r.interval_common)!=len(interval_keys):raise ValueError('Interval denominator differs')
                            for side,table in [('baseline',a),('stress',b)]:
                                item=table.loc[[idx for idx in table.index if idx in interval_keys]]
                                for metric in ['missing_coverage95','width95','interval_score95']:
                                    close(item[metric].mean(),r[side+'_'+metric],'interval '+metric)
                        if scope=='both_methods_six_way':
                            for region in sorted(a.region.unique()):
                                lr=leave[(leave.estimator==method)&(leave.dependence==dep)&(leave.version==version)&(leave.removed_region==region)]
                                if len(lr)!=1:raise ValueError('Leave-region cell missing')
                                keep=a.region.ne(region).to_numpy()
                                if int(lr.iloc[0].n_common)!=int(keep.sum()):raise ValueError('Leave-region count differs')
                                close(delta[keep].mean(),lr.iloc[0].mse_difference,'leave-region paired MSE')
                                region_checked+=1
                    checked+=1
    if checked!=len(saved) or region_checked!=len(leave):raise ValueError('Unverified output cells remain')
    report={'status':'passed','saved_trend_rows_checked':len(raw),'unaffected_region_rows_compared':len(compare),
            'summary_rows_checked':checked,'leave_region_rows_checked':region_checked,'bootstrap_draws_per_cell':4000,
            'daily_feature_files_compared':feature_files,'daily_feature_rows_compared':feature_rows,
            'scope':'Independently recounts availability, scores and seeded group resampling from shared saved model outputs; checks original and strict versions agree outside HUC17. Not an independent model fit, provider-data validation, climate test or causal interpretation.'}
    (S.OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
