#!/usr/bin/env python3
"""Recount six-way stress comparisons and group resampling independently.

This uses the same saved six-way case predictions. It checks arithmetic and
source-model assignment, not model training, sensor accuracy or data rights.
"""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('stress_source_independent_inputs',ROOT/'scripts/694_stress_source_sensitivity.py')
SCENARIOS=['synchronized_donors','heat_associated_matched']
VERSIONS=['original','strict_original','candidate']
SIDES=['baseline','stress']


def close(actual,expected,field):
    if not np.isclose(float(actual),float(expected),rtol=0,atol=1e-10,equal_nan=True):
        raise ValueError('Independent summary mismatch: '+field)


def main():
    M.verify_plan()
    raw=pd.read_parquet(M.STAGE/'six_way_trends.parquet')
    published=pd.read_csv(M.OUT/'six_way_summary.csv')
    leave=pd.read_csv(M.OUT/'leave_one_region_out.csv')
    indices=['scenario','station_key','replicate','estimator','dependence','version','side']
    if raw.duplicated(indices).any() or len(raw)!=9840:raise ValueError('Six-way saved case set differs')
    original=raw[raw.version.eq('original')&raw.region.ne('usgs_huc17')]
    strict=raw[raw.version.eq('strict_original')&raw.region.ne('usgs_huc17')]
    identity=['scenario','station_key','replicate','estimator','dependence','side']
    test=original.merge(strict,on=identity,suffixes=('_original','_strict'),validate='one_to_one')
    if len(test)!=len(original) or not test.available_original.eq(test.available_strict).all():
        raise ValueError('Unaffected region availability differs')
    for field in ['error','squared_error','truth_slope','missing_coverage95','width95','interval_score95']:
        a=pd.to_numeric(test[field+'_original'],errors='coerce').to_numpy(float)
        b=pd.to_numeric(test[field+'_strict'],errors='coerce').to_numpy(float)
        if not np.allclose(a,b,rtol=0,atol=1e-12,equal_nan=True):raise ValueError('Unaffected region result changed: '+field)
    rng=np.random.default_rng(694);cells=leave_cells=0
    for scenario in SCENARIOS:
        for estimator in ['D2','stochastic_calibrated']:
            for dependence in ['point','independent']:
                block=raw[raw.scenario.eq(scenario)&raw.estimator.eq(estimator)&raw.dependence.eq(dependence)]
                archive_keys=['station_key','replicate']
                counts=block.groupby(archive_keys).size()
                if len(counts)!=205 or not counts.eq(6).all():raise ValueError('Six-way cohort membership differs')
                availability=block.groupby(archive_keys).available.all()
                selected=set(availability[availability].index)
                common=block[[tuple(x) in selected for x in block[archive_keys].itertuples(index=False,name=None)]].copy()
                if len(common)!=len(selected)*6:raise ValueError('Common membership differs')
                group_keys=sorted(common.independence_group.unique())
                draws=rng.integers(len(group_keys),size=(4000,len(group_keys))) if group_keys else np.empty((0,0),int)
                summary=published[(published.scenario==scenario)&(published.estimator==estimator)&(published.dependence==dependence)]
                for version in VERSIONS:
                    row=summary[summary.version.eq(version)]
                    if len(row)!=1:raise ValueError('Summary cell missing')
                    row=row.iloc[0]
                    if int(row.n_common_six_way)!=len(selected) or int(row.n_groups)!=len(group_keys):raise ValueError('Common denominator mismatch')
                    a=common[common.version.eq(version)&common.side.eq('baseline')].set_index(archive_keys).sort_index()
                    b=common[common.version.eq(version)&common.side.eq('stress')].set_index(archive_keys).sort_index()
                    if not a.index.equals(b.index):raise ValueError('Paired cases differ')
                    close(np.sqrt(np.mean(a.squared_error)),row.baseline_rmse,'baseline RMSE')
                    close(np.sqrt(np.mean(b.squared_error)),row.stress_rmse,'stress RMSE')
                    diff=b.squared_error.to_numpy(float)-a.squared_error.to_numpy(float)
                    close(np.mean(diff),row.mse_stress_minus_baseline,'paired MSE')
                    aggregates=[]
                    for group in group_keys:
                        mask=a.independence_group.eq(group).to_numpy()
                        aggregates.append((float(diff[mask].sum()),int(mask.sum())))
                    totals=np.array([g[0] for g in aggregates]);sizes=np.array([g[1] for g in aggregates])
                    samples=totals[draws].sum(axis=1)/sizes[draws].sum(axis=1)
                    close(np.quantile(samples,.025),row.bootstrap_low,'bootstrap lower')
                    close(np.quantile(samples,.975),row.bootstrap_high,'bootstrap upper')
                    close(np.mean(totals/sizes),row.equal_group_mse_difference,'equal group MSE')
                    if dependence=='independent':
                        metrics=['missing_coverage95','width95','interval_score95']
                        valid=common.groupby(archive_keys)[metrics].apply(lambda g:bool(np.isfinite(g.to_numpy(float)).all()))
                        interval_keys=set(valid[valid].index)
                        if len(interval_keys)!=row.n_common_intervals:raise ValueError('Interval denominator mismatch')
                        for side,data in [('baseline',a),('stress',b)]:
                            item=data.loc[[idx for idx in data.index if idx in interval_keys]]
                            for metric in metrics:close(item[metric].mean(),row[side+'_'+metric],'interval '+metric)
                    for region in sorted(a.region.unique()):
                        lr=leave[(leave.scenario==scenario)&(leave.estimator==estimator)&(leave.dependence==dependence)&(leave.version==version)&(leave.removed_region==region)]
                        if len(lr)!=1:raise ValueError('Region deletion missing')
                        lr=lr.iloc[0];keep=a.region.ne(region).to_numpy()
                        if int(lr.n_common)!=int(keep.sum()):raise ValueError('Region deletion denominator mismatch')
                        close(np.mean(diff[keep]),lr.mse_difference,'region deletion MSE');leave_cells+=1
                    cells+=1
    status={'status':'passed','saved_case_rows_checked':len(raw),'unaffected_region_rows_compared':len(test),
            'summary_cells_checked':cells,'leave_region_cells_checked':leave_cells,'group_resamples_per_cell':4000,
            'scope':'Recomputes common cohorts, paired RMSE, interval summaries, group bootstrap and fixed-prediction leave-region comparisons from the same saved model outputs. Confirms strict-original versions equal original outside HUC17; no independent model refitting, source measurement validation or climate-transfer guarantee.'}
    (M.OUT/'independent_audit.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2),flush=True)


if __name__=='__main__':main()
