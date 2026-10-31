#!/usr/bin/env python3
"""Post-hoc replay of the 20 annual exports with and without bridge repairs.

The cached inputs and all per-case predictions stay local. This is not a new
fit, a provider-data validation, or evidence that the post-hoc hashes were
registered before the historical analysis.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
SOURCE=ROOT/'results/wrr_review_completion_20261024'
SAVED=ROOT/'private/wrr_review_case_evidence_20261027/annual_source_cases'
OUT=ROOT/'results/wrr_review_response_20261027/audit/annual_bridge_dependency'
KEY=['network_id','station_key','year','design_family','realization_id','policy_choice','mask_runs']
LEVELS=[5,10,25,50,75,90,95]

def replay(seed):
    repair=SOURCE/'repairs/leave_one_year_out'/f'seed_{seed:02d}.parquet'
    evidence=SAVED/f'seed_{seed:02d}.parquet'
    if not repair.is_file() or not evidence.is_file():raise FileNotFoundError(f'Missing repair or saved evidence for seed {seed}')
    pinned=[repair,evidence,Path(__file__).resolve()]
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in pinned}
    m=T.load_script(f'annual_bridge_dependency_{seed}',ROOT/'scripts/467_review_completion_analysis.py')
    repaired=m.calibrate_classical(m.load(seed,'leave_one_year_out'),seed,'leave_one_year_out')
    saved=pd.read_parquet(evidence)
    if repaired.duplicated(KEY).any() or saved.duplicated(KEY).any():raise ValueError('Duplicate annual case keys')
    saved=saved.set_index(KEY);repaired=repaired.set_index(KEY)
    if len(saved)!=len(repaired) or not saved.index.equals(repaired.index):raise ValueError('Saved annual case order or identities differ')
    for column in ['D2']+[f'{prefix}_q{q:02d}' for prefix in ('D2','stochastic_cal') for q in LEVELS]:
        if not np.allclose(saved[column],repaired[column],atol=1e-10,rtol=0,equal_nan=True):
            raise ValueError(f'Repaired prediction differs from saved evidence: seed {seed}, {column}')
    m.apply_bridge_repairs=lambda frame,seed,split:frame
    omitted=m.calibrate_classical(m.load(seed,'leave_one_year_out'),seed,'leave_one_year_out').set_index(KEY)
    if not omitted.index.equals(repaired.index):raise ValueError('Repair omission changed annual case keys')
    cols=[f'stochastic_cal_q{q:02d}' for q in LEVELS]
    a=repaired[cols].to_numpy(float);b=omitted[cols].to_numpy(float)
    av=np.isfinite(a).all(axis=1);bv=np.isfinite(b).all(axis=1);both=av&bv
    changed=(np.max(np.abs(a[both]-b[both]),axis=1)>1e-10)
    if any(hashlib.sha256(path.read_bytes()).hexdigest()!=hashes[str(path.relative_to(ROOT))] for path in pinned):
        raise ValueError('Annual bridge dependency changed during replay')
    return {'seed':seed,'rows':len(saved),'with_repair_valid':int(av.sum()),'without_repair_valid':int(bv.sum()),
            'became_valid_with_repair':int((av&~bv).sum()),'became_invalid_with_repair':int((~av&bv).sum()),
            'both_valid_changed_quantiles':int(changed.sum()),
            'max_both_valid_quantile_change':float(np.max(np.abs(a[both]-b[both]))) if both.any() else None,
            'input_sha256':hashes,
            }

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seeds',type=int,nargs='+',default=list(range(20)))
    args=p.parse_args()
    if len(set(args.seeds))!=len(args.seeds) or any(x not in range(20) for x in args.seeds):raise ValueError('Invalid seeds')
    OUT.mkdir(parents=True,exist_ok=True)
    for seed in args.seeds:
        result=replay(seed)
        (OUT/f'seed_{seed:02d}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
