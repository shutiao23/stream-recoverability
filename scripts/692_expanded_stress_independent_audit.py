#!/usr/bin/env python3
"""Rebuild fixed-count scenario masks and verify aggregate paired results.

Uses the same cached panels, air forcing and original model predictions; this
is a reproducibility audit, not an independent climate or physical-data test.
"""
from __future__ import annotations
import os
for var in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[var]='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT; REV=ROOT/'results/wrr_review_response_20261027'; OUT=REV/'expanded_stress'
PRIVATE=ROOT/'private/wrr_expanded_stress_20261027'; BASE=REV/'whole_archive'


def rebuild(job,ref,rep):
    years=np.sort(ref.year.unique())
    rng=np.random.default_rng(plain_seed(521,job['station_index'],rep))
    # Advance and reproduce the same within-year selection as the archive code.
    chosen={int(year):group.iloc[int(rng.integers(len(group)))].mask_runs for year,group in ref.groupby('year',sort=True)}
    draws=rng.random(len(years))
    eligible=(np.arange(len(years))>=7)&(years>=2010)
    baseline={str(int(y)):str(chosen[int(y)]) for y,keep in zip(years,(draws<.35)&eligible) if keep}
    panel=read_temperature_panel(job['input_path']).asfreq('D')
    panel.columns=panel.columns.astype(str)
    air=station_air_series(Path(job['air_input_path']),job['network_id'],job['station_id'],panel.index)
    panel.index+=pd.Timedelta(days=T.hemisphere_shift_days(job.get('latitude')))
    if air is None:return baseline,None,panel
    air.index=panel.index
    annual=[]
    for year in years:
        values=air.loc[air.index.year==year].to_numpy(float)
        if len(values)<30 or not np.isfinite(values).all():annual.append(np.nan)
        else:annual.append(float(pd.Series(values).rolling(30,min_periods=30).mean().max()))
    annual=np.asarray(annual)
    if np.isfinite(annual[:7]).sum()<4 or not np.isfinite(annual).all():return baseline,None,panel
    cutoff=np.nanquantile(annual[:7],.8)
    u=np.random.default_rng(plain_seed(689,job['station_index'],rep)).random(len(years))
    items=sorted(((-np.log(max(float(u[i]),np.finfo(float).tiny)) / (5. if annual[i]>=cutoff else 1.)),i)
                 for i in range(len(years)) if eligible[i])
    heat={str(int(years[i])):str(chosen[int(years[i])]) for _,i in items[:len(baseline)]}
    return baseline,heat,panel


def donor_count(panel,station,masks):
    total=0;days=0;donors=set()
    for year,runs in masks.items():
        block=panel.loc[panel.index.year==int(year)]
        for run in str(runs).split(';'):
            if not run:continue
            start,length=map(int,run.split(':'))
            for pos in range(start,min(start+length,len(block))):
                days+=1
                row=block.iloc[pos]
                for column,value in row.items():
                    if column!=station and np.isfinite(value):
                        total+=1;donors.add(column)
    return days,total,len(donors)


def compare_aggregate(summary):
    n=0
    for row in summary.itertuples(index=False):
        p=pd.read_parquet(PRIVATE/(row.scenario+'_paired_trends.parquet'))
        p=p[(p.estimator==row.estimator)&(p.retention=='all')&(p.dependence==row.dependence)]
        valid=p[p.available_baseline & p.available_stress]
        if len(valid)!=row.n_common or len(p)!=row.n_expected:raise ValueError('Summary denominator mismatch')
        for side in ['baseline','stress']:
            rmse=float(np.sqrt(valid['squared_error_'+side].mean()))
            if not np.isclose(rmse,getattr(row,side+'_rmse'),atol=1e-12,rtol=0):raise ValueError('Summary RMSE mismatch')
        delta=valid.squared_error_stress-valid.squared_error_baseline
        if not np.isclose(delta.mean(),row.mean_mse_difference,atol=1e-12,rtol=0):raise ValueError('Paired MSE mismatch')
        n+=1
    return n


def main():
    plan=json.loads((OUT/'plan.json').read_text())
    roster=pd.read_csv(PRIVATE/'roster.csv')
    saved=pd.read_parquet(PRIVATE/'mask_audit.parquet').set_index(['scenario','station_key','replicate'])
    core=T.load_script('stress_independent_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    ref=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','mask_runs'])
    baseline_checked=heat_checked=donor_checked=0
    for station in roster.station_key:
        subset=ref[(ref.station_key==station)&(ref.design_family=='crossed')]
        for rep in plan['replicates']:
            baseline,heat,panel=rebuild(jobs[station],subset,rep)
            suffix=Path('crossed')/'forward'/f'replicate_{rep:02d}'/station.replace('|','_')
            design=json.loads((BASE/suffix/'design.json').read_text())
            if baseline!=design['masks']:raise ValueError(f'Baseline RNG reconstruction failed: {station}/{rep}')
            baseline_checked+=1
            values=donor_count(panel,jobs[station]['station_id'],baseline)
            for scenario in ['synchronized_donors','heat_associated_matched']:
                row=saved.loc[(scenario,station,rep)]
                if tuple(map(int,[row.baseline_hidden_days,row.donor_observations_removed,row.affected_donors]))!=values:
                    raise ValueError(f'Donor observation count differs: {station}/{rep}')
                if not row.available:continue
                actual=json.loads((PRIVATE/scenario/suffix/'design.json').read_text())
                expected=baseline if scenario=='synchronized_donors' else heat
                if actual['masks']!=expected:raise ValueError(f'Scenario mask differs: {scenario}/{station}/{rep}')
                if scenario=='synchronized_donors':donor_checked+=1
                else:heat_checked+=1
    cells=compare_aggregate(pd.read_csv(OUT/'paired_summary.csv'))
    report={'status':'passed','baseline_masks_checked':baseline_checked,'synchronized_masks_checked':donor_checked,
            'matched_heat_masks_checked':heat_checked,'aggregate_cells_checked':cells,
            'scope':'Independently reconstructs random mask selections and counts finite donor observations using cached panels; independently recomputes paired RMSE and MSE summary. Uses the same underlying data, RNG seeds and fitted-model results. Does not independently refit models, bootstrap, confidence intervals, or assess sensor quality and data rights.'}
    (OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
