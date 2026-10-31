#!/usr/bin/env python3
"""Recreate and retain source-seed scoring inputs in a local private directory.

Each seed loads saved held-region outputs and redoes its historical disjoint
classical quantile calibration. No global model weights are refitted. The
result includes third-party-derived targets and is not for distribution until
source permissions and reviewer access are resolved.
"""
from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T

OUT=T.ROOT/'private/wrr_review_case_evidence_20261027/annual_source_cases'
LEVELS=[5,10,25,50,75,90,95]
KEY=['network_id','station_key','year','design_family','realization_id','policy_choice','mask_runs']
COLUMNS=KEY+['independence_group','region','peak_overlap','eval_truth_h30',
             'observed_lower_bound__observed_days','train_h30_q90','h30__policy','P2','D2'] + [
             f'{prefix}_q{q:02d}' for prefix in ['D2','stochastic_cal'] for q in LEVELS]

def verify_bridge_repair(seed):
    report_path=T.ROOT/'results/wrr_review_response_20261027/audit/annual_bridge_repair_dependency.json'
    report=json.loads(report_path.read_text())
    effect=report_path.parent/'annual_bridge_repair_effect.csv'
    audit=T.ROOT/'scripts/730_annual_bridge_dependency.py'
    if report.get('status')!='passed' or report.get('seeds_checked')!=20 or not effect.is_file() or not audit.is_file():
        raise ValueError('Post-hoc annual bridge dependency audit is incomplete')
    repair=T.ROOT/'results/wrr_review_completion_20261024/repairs/leave_one_year_out'/f'seed_{seed:02d}.parquet'
    for path in (repair,effect,audit):
        expected=report.get('input_sha256',{}).get(str(path.relative_to(T.ROOT)))
        if not path.is_file() or path.is_symlink() or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Required annual bridge repair is missing or changed for seed {seed}: {path}')

def one(seed,resume):
    verify_bridge_repair(seed)
    path=OUT/f'seed_{seed:02d}.parquet'
    if path.exists():
        if resume:
            existing=pd.read_parquet(path,columns=KEY)
            if existing.duplicated(KEY).any() or existing.empty:raise RuntimeError(f'Invalid existing seed {seed}')
            return {'seed':seed,'rows':len(existing),'status':'existing_not_replaced','bytes':path.stat().st_size}
        raise RuntimeError(f'Existing restricted output will not be overwritten: {path}')
    analysis=T.load_script(f'private_source_{seed}',T.ROOT/'scripts/467_review_completion_analysis.py')
    c=analysis.load(seed,'leave_one_year_out')
    c=analysis.calibrate_classical(c,seed,'leave_one_year_out')
    missing=set(COLUMNS)-set(c.columns)
    if missing:raise ValueError(f'seed {seed} missing columns {missing}')
    if c.duplicated(KEY).any():raise ValueError(f'duplicate case identifiers in seed {seed}')
    x=c[COLUMNS].copy()
    y=x.eval_truth_h30.to_numpy(float);bound=x.observed_lower_bound__observed_days.to_numpy(float)
    if np.any(np.isfinite(y)&np.isfinite(bound)&(y<bound-1e-8)):raise ValueError('reference below observed bound')
    temp=path.with_suffix('.parquet.partial')
    if temp.exists():raise RuntimeError(f'Partial output exists and must be reviewed: {temp}')
    x.to_parquet(temp,index=False);temp.chmod(0o600);os.replace(temp,path)
    return {'seed':seed,'rows':len(x),'status':'created','bytes':path.stat().st_size}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,default=list(range(20)))
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    if any(s<0 or s>=20 for s in args.seeds) or len(set(args.seeds))!=len(args.seeds):raise ValueError('invalid or duplicate seed list')
    if not (OUT.parent/'README.txt').is_file():raise RuntimeError('Prepare local-only evidence directory first')
    OUT.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.chmod(0o700)
    done=Parallel(n_jobs=args.workers,verbose=10)(delayed(one)(s,args.resume) for s in sorted(args.seeds))
    print(json.dumps({'seeds':done,'local_only':True,'scope':'saved source outputs plus re-applied classical quantile calibration; no model refitting'},indent=2),flush=True)

if __name__=='__main__':main()
