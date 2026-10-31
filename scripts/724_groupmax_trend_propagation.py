#!/usr/bin/env python3
"""Propagate frozen source group-max annual radii to archive trend draws.

The reused rank constructions and quantile shapes are sensitivities, not a
calibrated joint distribution, risk guarantee or new climate reference.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'groupmax_annual_calibration'
PRIVATE=ROOT/'private/wrr_groupmax_annual_calibration_20261027'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026'
PREVIOUS=INPUT/'single_year_trend_propagation/full'
STAGE=PRIVATE/'trend_propagation'
SOURCE=ROOT/'results/wrr_review_completion_20261024'

def verify_plan():
    plan=json.loads((OUT/'trend_plan.json').read_text());manifest=PRIVATE/'trend_input_manifest.json'
    for item in json.loads(manifest.read_text()):
        p=Path(item['path']);p=p if p.is_absolute() else ROOT/p
    return plan

def verify_previous(new_file,old_file):
    """Radii differ; identities, base quantiles and all rank matrices must not."""
    fields=['years','truth','bounds','mask','q_D2','q_stochastic_calibrated',
            'rank_independent','rank_shared_parameters','rank_residual_blocks']
    with np.load(new_file) as new,np.load(old_file) as old:
        for field in fields:
            if field not in new or field not in old or new[field].shape!=old[field].shape or not np.allclose(new[field],old[field],rtol=0,atol=1e-10,equal_nan=True):
                raise ValueError('Previous marginal/rank mismatch: '+field)

def work(job,reference,rep,radii,plan_hash,impl_hash):
    helper=T.load_script('groupmax_trend_existing_worker',ROOT/'scripts/677_single_year_trend_propagation.py')
    result=helper.work(job,reference,rep,radii,STAGE,plan_hash,impl_hash)
    old=PREVIOUS/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')/'marginals_and_ranks.npz'
    new=STAGE/f'replicate_{rep:02d}'/job['station_key'].replace('|','_')/'marginals_and_ranks.npz'
    checked=result['status']=='passed' and old.is_file()
    if checked:verify_previous(new,old)
    return result | {'previous_marginal_and_rank_checked':checked}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=6);a=p.parse_args()
    if a.workers<1:raise ValueError('Worker count must be positive')
    plan=verify_plan();support=pd.read_csv(OUT/'source_support.csv')
    roster=pd.read_csv(ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv')
    core=T.load_script('groupmax_trend_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    if len(roster)!=41 or not set(roster.station_key).issubset(jobs):raise ValueError('Target station cohort changed')
    radii={}
    for region in sorted(roster.region.unique()):
        s=support[support.region.eq(region)&support.family.eq('crossed')].set_index('estimator')
        if set(s.index)!={'D2','stochastic_calibrated'} or not s.status.eq('supported_exploratory').all():
            raise ValueError('Both source methods must have finite positive rank support: '+region)
        radii[region]={method:float(s.loc[method,'radius']) for method in s.index}
    reference=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
    reference=reference[reference.design_family.eq('crossed')]
    check=reference.groupby(['station_key','year']).eval_truth_h30.agg(['min','max','count'])
    if check['count'].eq(0).any() or (check['max']-check['min']).gt(1e-8).any():raise ValueError('Complete annual reference differs across masks')
    STAGE.mkdir(parents=True,exist_ok=True,mode=0o700)
    tasks=[(jobs[row.station_key],reference[reference.station_key.eq(row.station_key)],rep,radii[row.region],)
           for row in roster.itertuples(index=False) for rep in range(20)]
    if len(tasks)!=820:raise ValueError('Unexpected target archive count')
    print('Reconstructing paired trend marginals and ranks for',len(tasks),'settings',flush=True)
    result=Parallel(n_jobs=a.workers,verbose=10)(delayed(work)(*task) for task in tasks)
    counts=pd.Series([r['status'] for r in result]).value_counts().to_dict()
    report={'status':'complete','archive_settings':len(result),'status_counts':counts,
            'previous_marginal_and_rank_checks':sum(r['previous_marginal_and_rank_checked'] for r in result),
            'scope':'same masks, candidate source annual quantiles and rank matrices; hypothetical endpoint-only and tapered shapes; no joint coverage guarantee'}
    (OUT/'trend_execution.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
