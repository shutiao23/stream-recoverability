#!/usr/bin/env python3
"""Annual estimators on the neural models' exact cases and group partitions."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.experiments.tr_revision.statistics import quantile_samples,ensemble_crps,interval_score

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"deep"
KEYS=["network_id","station_key","year","design_family","realization_id","policy_choice"]
PARAMS=dict(n_estimators=300,learning_rate=.05,num_leaves=31,min_child_samples=50,subsample=.8,subsample_freq=1,colsample_bytree=.8,reg_lambda=1,verbose=-1,n_jobs=1)


def one(seed):
    folder=OUT/f"seed_{seed:02d}"
    metadata=pd.read_csv(folder/"group_split.csv")
    c=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    partition=metadata[["station_key","year","role"]].drop_duplicates(["station_key","year"])
    c=c.merge(partition,on=["station_key","year"],how="inner",validate="many_to_one")
    train=c.role.eq("train").to_numpy();cal=c.role.eq("validation").to_numpy()
    reference=pd.read_parquet(folder/"saits_cases.parquet")
    if c.duplicated(KEYS).any() or reference.duplicated(KEYS).any():
        raise RuntimeError("Neural comparison identity is not unique")
    target=reference[KEYS].merge(c,on=KEYS,how="left",validate="one_to_one")
    if target.eval_truth_h30.isna().any():
        raise RuntimeError("Some neural cases have no matching original mask cohort")
    x=F.design_matrix(c,simulation=True);xt=F.design_matrix(target,simulation=True).reindex(columns=x.columns)
    xp=F.design_matrix(c,simulation=False);xpt=F.design_matrix(target,simulation=False).reindex(columns=xp.columns)
    y=c.eval_truth_h30.to_numpy()-c.h30__policy.to_numpy()
    quantile_train=[];quantile_test=[]
    for level in F.QUANTILES:
        model=lgb.LGBMRegressor(objective="quantile",alpha=level,random_state=seed,**PARAMS).fit(x.loc[train],y[train])
        quantile_train.append(model.predict(x.loc[cal])+c.loc[cal,"h30__policy"].to_numpy())
        quantile_test.append(model.predict(xt)+target.h30__policy.to_numpy())
    raw=np.sort(np.column_stack(quantile_test),axis=1)
    cal_q=np.sort(np.column_stack(quantile_train),axis=1)
    offset=np.array([np.quantile(c.loc[cal,"eval_truth_h30"].to_numpy()-cal_q[:,j],level) for j,level in enumerate(F.QUANTILES)])
    calibrated=np.sort(raw+offset,axis=1)
    point_model=lgb.LGBMRegressor(objective="l2",random_state=seed,**PARAMS).fit(xp.loc[train],y[train])
    point=point_model.predict(xpt)+target.h30__policy.to_numpy()
    for name,q,estimate in [("distribution_regression_raw",raw,raw[:,3]),("distribution_regression_calibrated",calibrated,calibrated[:,3]),("functional_debias",None,point)]:
        result=reference[KEYS+["peak_overlap","group","plug_in_error"]].copy()
        truth=target.eval_truth_h30.to_numpy()
        result["model"]=name;result["seed"]=seed;result["truth_h30"]=truth;result["h30_estimate"]=estimate;result["h30_error"]=estimate-truth;result["daily_mae"]=np.nan
        if q is not None:
            samples=quantile_samples(q,F.QUANTILES)
            result["n_draws"]=samples.shape[1];result["h30_draws"]=list(samples)
            result["crps"]=ensemble_crps(samples,truth)
            result["twcrps"]=ensemble_crps(samples,truth,target.train_h30_q90.to_numpy())
            result["coverage90"]=(truth>=q[:,0])&(truth<=q[:,-1]);result["interval_score90"]=interval_score(q[:,0],q[:,-1],truth)
        else:
            result["n_draws"]=1
        result.to_parquet(folder/f"{name}_cases.parquet",index=False)
    T.write_json(folder/"annual_match.json",{"source_case_version":"20261022, exactly the neural masks","training":"neural training independence groups only","calibrated_variant":"uses neural validation groups for a pooled quantile-offset correction; raw variant uses no validation outcome correction","test_cases":len(target),"test_group_disjoint":not set(target.independence_group).intersection(c.loc[train|cal,"independence_group"]),"draw_convention":"128 midpoint quantile integration; CSDI retains its sampled 20-member ensemble; integration approximation and finite ensemble size differ"})
    return seed


def append_classical(seed):
    helper=T.load_script("r4_deep_classical_overlay",T.ROOT/"scripts/467_review_completion_analysis.py")
    source=helper.load(0,"leave_one_year_out")
    old=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet",columns=KEYS+["mask_runs"])
    matched=old.merge(source[KEYS+["mask_runs"]],on=KEYS,suffixes=("_old","_new"),validate="one_to_one")
    if len(matched)!=len(old) or not matched.mask_runs_old.eq(matched.mask_runs_new).all():
        raise RuntimeError("Seed-zero masks are not identical to the neural masks; do not join by realization name alone")
    folder=OUT/f"seed_{seed:02d}";metadata=pd.read_csv(folder/"group_split.csv")
    source=source.merge(metadata[["station_key","year","role"]],on=["station_key","year"],how="inner",validate="many_to_one")
    reference=pd.read_parquet(folder/"saits_cases.parquet")
    target=reference[KEYS].merge(source,on=KEYS,how="left",validate="one_to_one")
    raw_q=target[[f"stochastic_h30_q{int(level*100):02d}" for level in F.QUANTILES]].to_numpy(float)
    cal=source.role.eq("validation").to_numpy()
    qcal=source[[f"stochastic_h30_q{int(level*100):02d}" for level in F.QUANTILES]].to_numpy(float)
    cal&=np.isfinite(qcal).all(axis=1)
    residual=source.loc[cal,"eval_truth_h30"].to_numpy()[:,None]-qcal[cal]
    offsets=np.array([np.quantile(residual[:,j],level) for j,level in enumerate(F.QUANTILES)])
    calibrated=np.sort(raw_q+offsets,axis=1)
    raw_samples=np.vstack([np.asarray(v,float) if np.ndim(v)==1 and len(v)==20 else np.full(20,np.nan) for v in target.stochastic_h30_draws])
    for name,q,samples,point in [("stochastic_regression_local",raw_q,raw_samples,target.h30__stochastic_regression.to_numpy()),("stochastic_regression_calibrated_local",calibrated,quantile_samples(calibrated,F.QUANTILES),calibrated[:,3])]:
        result=reference[KEYS+["peak_overlap","group","plug_in_error"]].copy();truth=target.eval_truth_h30.to_numpy()
        result["model"]=name;result["seed"]=seed;result["truth_h30"]=truth;result["h30_estimate"]=point;result["h30_error"]=point-truth;result["daily_mae"]=np.nan;result["available"]=np.isfinite(point);result["n_draws"]=samples.shape[1];result["h30_draws"]=list(samples)
        result["crps"]=ensemble_crps(samples,truth);result["twcrps"]=ensemble_crps(samples,truth,target.train_h30_q90.to_numpy());result["coverage90"]=np.where(np.isfinite(point),(truth>=q[:,0])&(truth<=q[:,-1]),np.nan);result["interval_score90"]=interval_score(q[:,0],q[:,-1],truth)
        destination=folder/f"{name}_cases.parquet";temporary=destination.with_suffix(".partial");result.to_parquet(temporary,index=False);temporary.replace(destination)
    T.write_json(folder/"classical_match.json",{"exact_mask_identity_verified":True,"baseline_case_seed":0,"case_version":"seed zero is identical to all 145684 original neural-cohort masks","calibration":"same neural validation station-years and pooled quantile-offset convention as the matched D2 calibration","test_outcomes_used_for_calibration":False,"baseline_model":"local residual AR1 bridge uses each station's other-year history, also available to the neural climatology; no global failure labels used"})
    return seed


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=[0,1,2]);p.add_argument("--classical-only",action="store_true");a=p.parse_args()
    if not a.classical_only:
        Parallel(n_jobs=3,verbose=10)(delayed(one)(seed) for seed in a.seeds)
    Parallel(n_jobs=3,verbose=10)(delayed(append_classical)(seed) for seed in a.seeds)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
