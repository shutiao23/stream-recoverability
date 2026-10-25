#!/usr/bin/env python3
"""Unflagged visible-air exposure with CLEAN source weights held fixed.

Three mask/trajectory seeds share source-fit seed zero; this is not three new
model fits or a registered endpoint. Missing years follow the existing random
and strongly heat-associated designs, matched in marginal frequency.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

OUT=T.ROOT/"results/wrr_review_completion_20261024"
DEST=OUT/"air_exposure"


def source_calibrations():
    a=T.load_script("r4_exposure_source_analysis",T.ROOT/"scripts/467_review_completion_analysis.py")
    m=T.load_script("r4_exposure_source_roles",T.ROOT/"scripts/466_review_completion_refit.py")
    c=pd.read_parquet(OUT/"cases/leave_one_year_out/seed_00.parquet")
    c=c.loc[c.policy_choice.ne("unavailable")&c.eval_truth_h30.notna()].reset_index(drop=True)
    c=a.apply_bridge_repairs(c,0,"leave_one_year_out")
    regions=sorted(c.region.unique());d=m.difficulty(c);result={}
    for number,region in enumerate(regions):
        _,roles,weights=m.roles(c,region,plain_seed(7,0,number))
        actual=json.loads((OUT/"refits/leave_one_year_out/seed_00"/(region+".json")).read_text())
        if roles!=actual["roles"]:raise RuntimeError("Clean-source roles changed")
        w=weights["interval_calibration"]
        local={"offsets":{},"source_decision_hot_cutoff":float(c.loc[weights["estimator"]>0,"air_warm_z_mean"].quantile(.9))}
        for prefix in ["stochastic","state"]:
            q=c[[f"{prefix}_h30_q{int(level*100):02d}" for level in m.LEVELS]].to_numpy(float)
            valid=np.isfinite(q).all(axis=1);offsets={}
            for cell in ["__pooled__",*sorted(d.unique())]:
                pool=(w>0)&valid if cell=="__pooled__" else (w>0)&valid&d.eq(cell).to_numpy()
                if pool.sum()<50:pool=(w>0)&valid
                if pool.sum()<2:raise RuntimeError("Missing clean-source interval calibration")
                residual=np.repeat(c.loc[pool,"eval_truth_h30"].to_numpy()[:,None]-q[pool],w[pool].astype(int),axis=0)
                offsets[cell]=[float(np.quantile(residual[:,j],level,method="higher" if level>=.5 else "lower")) for j,level in enumerate(m.LEVELS)]
            local["offsets"][prefix]=offsets
        result[region]=local
    return result


def trend_worker(block,seed):
    scoring=T.load_script("r4_exposure_trend_worker",T.ROOT/"scripts/467_review_completion_analysis.py")
    return scoring.station_trends(block,seed,200,scenarios=["mcar","strong_heat"],include_censored=False)


def analyse(seed,calibrations):
    inference=T.load_script("r4_exposure_frozen_inference",T.ROOT/"scripts/495_review_completion_independent_analysis.py")
    scoring=T.load_script("r4_exposure_frozen_scoring",T.ROOT/"scripts/467_review_completion_analysis.py")
    folder=DEST/f"seed_{seed:02d}";folder.mkdir(parents=True,exist_ok=True)
    summaries=[];release=[];trend_rows=[]
    for condition,split in [("clean","leave_one_year_out"),("unflagged_air_exposure","air_exposure")]:
        c=pd.read_parquet(OUT/"cases"/split/f"seed_{seed:02d}.parquet")
        n_eligible=len(c);c=c.loc[c.policy_choice.ne("unavailable")&c.eval_truth_h30.notna()].copy()
        if condition=="clean":
            c=scoring.apply_bridge_repairs(c,seed,"leave_one_year_out")
            c["eval_air_exposure_days"]=0
        parts=[]
        for region,block in c.groupby("region",sort=True):
            bundle=joblib.load(OUT/"refits/leave_one_year_out/seed_00"/(region+".joblib"))
            out=inference.predict(block,bundle)
            out=inference.classical_predictions(out,calibrations[region])
            out["decision_hot"]=out.air_warm_z_mean.ge(calibrations[region]["source_decision_hot_cutoff"])
            parts.append(out)
        c=pd.concat(parts,ignore_index=True)
        score,*_=scoring.scorecard(c,seed);score["condition"]=condition
        score.to_csv(folder/(condition+"_scorecard.csv"),index=False)
        for family,block in c.groupby("design_family"):
            admit=block.risk_score.le(.1)&block.D2.notna()
            risk=(block.D2-block.eval_truth_h30).abs().gt(.5)
            groups=block.loc[admit].assign(failure=risk.loc[admit]).groupby("independence_group").failure.agg(["size","mean"])
            groups=groups.loc[groups["size"]>=20]
            release.append({"seed":seed,"source_fit_seed":0,"condition":condition,"family":family,"n_cases":len(block),
                "retention":float(admit.mean()),"risk":float(risk[admit].mean()) if admit.any() else np.nan,
                "fraction_groups_above_10":float(groups["mean"].gt(.1).mean()) if len(groups) else np.nan,
                "worst_group_risk":float(groups["mean"].max()) if len(groups) else np.nan,
                "fraction_actually_exposed":float(block.eval_air_exposure_days.gt(0).mean())})
        blocks=[block for _,block in c.loc[c.design_family.eq("calendar")].groupby("station_key") if block.year.nunique()>=20]
        for rows in Parallel(n_jobs=12,backend="loky")(delayed(trend_worker)(block,seed) for block in blocks):
            for row in rows:row["condition"]=condition
            trend_rows.extend(rows)
        summaries.append({"condition":condition,"n_generated_cases":n_eligible,"n_supported_policy_cases":len(c),
                          "n_exposed_cases":int(c.eval_air_exposure_days.gt(0).sum()),"n_stations":c.station_key.nunique()})
    trends=pd.DataFrame(trend_rows);trends.to_parquet(folder/"trends.parquet",index=False)
    for (condition,scenario,pipeline),block in trends.groupby(["condition","scenario","pipeline"]):
        error=block.error.dropna()
        summaries.append({"condition":condition,"scenario":scenario,"pipeline":pipeline,
                          "n_trend_evaluations":len(error),"rmse":float(np.sqrt(np.mean(error**2))),
                          "bias":float(error.mean()),"total_coverage":float(block.coverage.mean()),
                          "missing_component_coverage":float(block.missing_component_coverage.mean())})
    pd.DataFrame(release).to_csv(folder/"release_metrics.csv",index=False)
    pd.DataFrame(summaries).to_csv(folder/"summary.csv",index=False)
    return seed


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=[0,1,2]);p.add_argument("--workers",type=int,default=3);a=p.parse_args()
    DEST.mkdir(exist_ok=True)
    calibration=source_calibrations();T.write_json(DEST/"source_calibration.json",calibration)
    Parallel(n_jobs=a.workers)(delayed(analyse)(seed,calibration) for seed in a.seeds)
    for name in ["release_metrics","summary"]:
        parts=[]
        for seed in a.seeds:
            f=pd.read_csv(DEST/f"seed_{seed:02d}"/(name+".csv"));f["seed"]=seed;parts.append(f)
        pd.concat(parts,ignore_index=True).to_csv(DEST/(name+"_all_seeds.csv"),index=False)
    T.write_json(DEST/"design.json",{"seeds":a.seeds,"source_fit_seed":0,"exposure":"Seven consecutive visible warm-season daily sensor readings replaced by concurrent air; choose randomly among hottest 10 percent of eligible seven-day air windows, without hidden water values",
        "calibration":"all estimator weights, classifier and interval offsets remain clean-source region-held-out fits; no contaminated-label refit",
        "trend_repetitions":200,"scenarios":["mcar","strong_heat"],"target":"still-defined water temperature, not a dry-bed physical quantity",
        "censored_trend_scope":"Not rerun: contaminated visible windows no longer establish valid physical lower bounds. All original clean-source censored comparisons remain available.",
        "scope":"synthetic unflagged measurement contamination; three mask seeds with one source fit, not twenty-repeat stability or new-region evidence"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
