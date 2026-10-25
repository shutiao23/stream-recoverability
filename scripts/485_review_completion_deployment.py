#!/usr/bin/env python3
"""Fit a reviewable source-only deployment candidate before public registration."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import wrr_tr_common as T
import argparse
import json
import hashlib
import numpy as np
import pandas as pd
from stream_recoverability.seeds import plain_seed


def classical_calibration(m,source):
    helper=T.load_script("r4_global_classical_repairs",T.ROOT/"scripts/467_review_completion_analysis.py")
    c=pd.read_parquet(source);c=c.loc[c.policy_choice.ne("unavailable")&c.eval_truth_h30.notna()].reset_index(drop=True)
    c=helper.apply_bridge_repairs(c,0,"leave_one_year_out")
    region="global_source_candidate";number=sorted(set(c.region.unique())|{region}).index(region)
    _,roles,weights=m.roles(c,region,plain_seed(7,0,number))
    candidate=json.loads((m.OUT/"deployment/candidate.json").read_text());assert roles==candidate["roles"]
    difficulty=m.difficulty(c);w=weights["interval_calibration"];levels=m.LEVELS
    result={"levels":levels.tolist(),"source_role":"exactly the global candidate's interval-calibration role and bootstrap multiplicities","cell_minimum":50,"offsets":{},"risk_classifier_scope":"the D2 classifier is not reused as a stochastic-regression failure classifier"}
    for prefix in ["stochastic","state"]:
        q=c[[f"{prefix}_h30_q{int(level*100):02d}" for level in levels]].to_numpy(float);valid=np.isfinite(q).all(axis=1)
        offsets={}
        for cell in ["__pooled__",*sorted(difficulty.unique())]:
            pool=(w>0)&valid if cell=="__pooled__" else (w>0)&valid&difficulty.eq(cell).to_numpy()
            if pool.sum()<50:pool=(w>0)&valid
            if pool.sum()<2:raise RuntimeError("Insufficient source calibration data for a frozen classical comparator")
            residual=np.repeat(c.loc[pool,"eval_truth_h30"].to_numpy()[:,None]-q[pool],w[pool].astype(int),axis=0)
            offsets[cell]=[float(np.quantile(residual[:,j],level,method="higher" if level>=.5 else "lower")) for j,level in enumerate(levels)]
        result["offsets"][prefix]=offsets
    result["source_case_sha256"]=hashlib.sha256(source.read_bytes()).hexdigest()
    repair=m.OUT/"repairs/leave_one_year_out/seed_00.parquet"
    result["bridge_repair_sha256"]=hashlib.sha256(repair.read_bytes()).hexdigest() if repair.exists() else None
    T.write_json(m.OUT/"deployment/classical_calibration.json",result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--refit",action="store_true");args=parser.parse_args()
    m=T.load_script("r4_global_deployment_fit",T.ROOT/"scripts/466_review_completion_refit.py")
    source=m.OUT/"cases/leave_one_year_out/seed_00.parquet"
    if args.refit or not (m.OUT/"deployment/global_source_candidate.joblib").exists():
        result=m.fit_region(0,"global_source_candidate","deployment_source",str(source),True)
    else:result={"deployment_candidate":"reused frozen source candidate; weights unchanged"}
    classical_calibration(m,source)
    print(result)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
