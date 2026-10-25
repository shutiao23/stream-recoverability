#!/usr/bin/env python3
"""Audit native H7 targets against source daily inputs and summarize full refits."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels,usable_donors

OUT=T.ROOT/"results/wrr_review_completion_20261024"
NATIVE=OUT/"target_windows/h7/full"


def audit():
    core=T.load_script("native_h7_independent_audit",T.ROOT/"scripts/431_tr_cases.py")
    cases=pd.read_parquet(NATIVE/"seed_00.parquet")
    jobs={(j["network_id"],j["station_id"]):j for j in core.jobs_for("source")}
    sample=cases.loc[cases.policy_choice.ne("unavailable")].sort_values(["provider","policy_choice","network_id","station_id","year"])
    sample=sample.drop_duplicates(["provider","policy_choice"]).head(16)
    rows=[]
    for _,r in sample.iterrows():
        job=jobs[(r.network_id,r.station_id)]
        panel=core.read_temperature_panel(job["input_path"]);panel.columns=panel.columns.astype(str);panel=panel.asfreq("D")
        air=core.station_air_series(Path(job["air_input_path"]),job["network_id"],job["station_id"],panel.index)
        shift=T.hemisphere_shift_days(job.get("latitude"))
        if shift:
            panel.index+=pd.Timedelta(days=shift)
            if air is not None:air.index=panel.index
        target=panel[job["station_id"]];donors=panel.drop(columns=job["station_id"])
        held=panel.index.year==r.year;index=panel.index[held];truth=target.to_numpy()[held]
        assert len(truth) in [365,366] and np.isfinite(truth).all()
        mask=T.mask_from_runs(r.mask_runs,len(truth));observed=truth.copy();observed[mask]=np.nan
        years=[y for y in core.CORE.complete_years(target) if y!=r.year]
        peaks=[float(T.window_means(target.loc[target.index.year==y].to_numpy(),7).max()) for y in years]
        model=StationModels(target=target,donors=donors,air=air,train_mask=pd.Series(~held,index=target.index))
        visible=usable_donors(donors,index,mask)
        fills=core.CORE.predictions(model,observed,index,visible)
        completed=observed.copy();completed[mask]=fills[r.policy_choice][mask]
        support=core.climatological_peak_window(target.loc[~held],window=7)
        lower=pd.Series(observed).rolling(7,min_periods=7).mean().max()
        expected={"eval_truth_h7":float(T.window_means(truth,7).max()),"eval_truth_h30":float(T.window_means(truth,30).max()),
            "h7__policy":float(T.window_means(completed,7).max()),"train_h7_mean":float(np.mean(peaks)),
            "train_h7_sd":float(np.std(peaks,ddof=1)),"train_h7_q90":float(np.quantile(peaks,.9)),
            "clim_peak":float(T.window_means(model.smooth_climatology(index),7).max()),
            "peak_overlap":float(mask[np.isin(index.dayofyear,support)].mean()),"observed_lower_bound__observed_days":float(lower)}
        for name,value in expected.items():np.testing.assert_allclose(r[name],value,rtol=1e-10,atol=1e-10,equal_nan=True,err_msg=f"{r.station_key}/{r.year}/{name}")
        rows.append({"network_id":r.network_id,"station_key":r.station_key,"year":int(r.year),"policy":r.policy_choice,
                     "checked_columns":list(expected),"maximum_difference":float(max(abs(r[k]-v) for k,v in expected.items() if np.isfinite(v)))})
    if len(rows)<8:raise RuntimeError("Insufficient distinct native-H7 source audit cases")
    T.write_json(NATIVE/"daily_input_audit.json",{"passed":True,"n_distinct_provider_policy_cases":len(rows),"rows":rows,
        "audit":"independent reconstruction from original network-specific daily inputs, held year excluded from all training",
        "core_script_sha256":hashlib.sha256((T.ROOT/"scripts/431_tr_cases.py").read_bytes()).hexdigest()})


def summarize():
    reporting=T.load_script("h7_summary_statistics",T.ROOT/"scripts/473_review_completion_evidence.py")
    paths=[OUT/f"analyses/h7_spec_refit/seed_{seed:02d}" for seed in range(20)]
    identities=[]
    for path in paths:
        meta=json.loads((path/"summary.json").read_text())
        if not meta.get("complete") or meta["trend_replicates"]!=200:raise RuntimeError(f"Incomplete full-H7 analysis: {path}")
        refs=sorted((OUT/"refits/h7_spec_refit"/path.name).glob("*.json"))
        if len(refs)!=27:raise RuntimeError("Full H7 requires all27 outer-region fits per seed")
        for p in refs:
            d=json.loads(p.read_text());roles=[set(v) for v in d["roles"].values()];held=set(d["held_groups"])
            for i,role in enumerate(roles):
                assert not role&held and all(not role&other for other in roles[:i]),p
        keys=["network_id","station_key","year","design_family","realization_id","policy_choice","mask_runs"]
        seed=int(path.name.removeprefix("seed_"))
        expected=pd.read_parquet(NATIVE/f"seed_{seed:02d}.parquet",columns=keys+["eval_truth_h7","h7__policy"])
        expected=expected.loc[expected.policy_choice.ne("unavailable")&expected.eval_truth_h7.notna()]
        expected=expected.rename(columns={"eval_truth_h7":"eval_truth_h30","h7__policy":"h30__policy"}).sort_values(keys).reset_index(drop=True)
        actual=pd.concat([pd.read_parquet(p.with_suffix(".parquet"),columns=list(expected)) for p in refs],ignore_index=True).sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(actual,expected,check_dtype=False,rtol=1e-11,atol=1e-11)
        identities.append({"seed":seed,"case_rows":len(actual),"native_target_and_point_match":True})
    T.write_json(NATIVE/"outer_prediction_identity_audit.json",{"passed":True,"rows":identities})
    specifications={
        "scorecard":(["family","stratum","estimator"],["n","mae","bias","failure_rate","coverage90","crps","twcrps","interval_score90","availability"]),
        "rules":(["family","rule","delivery"],["retention","risk","fraction_groups_above_10","worst_group_risk"]),
        "recovery":(["family","scope","model"],["auc","brier","brier_skill","diagnostic_retention_at_5"]),
        "paired_effects":(["family","reference","unit"],["fraction_D2_no_worse","case_relative_reduction","case_mae_D2","case_mae_reference"]),
        "distribution_paired_effects":(["family","reference"],["crps_difference","twcrps_difference"])}
    for name,(keys,values) in specifications.items():
        frame=pd.concat([pd.read_csv(p/(name+".csv")) for p in paths],ignore_index=True)
        if "estimator" in frame:frame["estimator"]=frame.estimator.replace({"MOVE1_H30":"MOVE1_H7"})
        frame["primary_window_days"]=7
        frame.to_csv(NATIVE/(name+"_all_seeds.csv"),index=False)
        reporting.aggregate(frame,keys,values).to_csv(NATIVE/(name+"_summary.csv"),index=False)
    trend=[]
    for path in paths:
        frame=pd.read_parquet(path/"trends.parquet")
        for (seed,scenario,method),b in frame.groupby(["seed","scenario","pipeline"]):
            trend.append({"seed":seed,"scenario":scenario,"pipeline":method,"rmse":float(np.sqrt(np.mean(b.error**2))),
                          "bias":float(b.error.mean()),"coverage":float(b.coverage.mean()),
                          "missing_component_coverage":float(b.missing_component_coverage.mean()),"n_stations":b.station.nunique()})
    trend=pd.DataFrame(trend);trend.to_csv(NATIVE/"trends_per_seed.csv",index=False)
    reporting.aggregate(trend,["scenario","pipeline"],["rmse","bias","coverage","missing_component_coverage"]).to_csv(NATIVE/"trends_summary.csv",index=False)
    pairs=pd.read_csv(NATIVE/"paired_effects_all_seeds.csv")
    scores=pd.read_csv(NATIVE/"distribution_paired_effects_all_seeds.csv")
    stability=[]
    for (family,reference),b in pairs.loc[pairs.unit.eq("station")].groupby(["family","reference"]):
        stability.append({"family":family,"reference":reference,"endpoint":"danger_MAE_gain_positive","passing":int(b.case_relative_reduction.gt(0).sum()),"n_seeds":b.seed.nunique(),"median_gain":float(b.case_relative_reduction.median())})
    for (family,reference),b in scores.groupby(["family","reference"]):
        for metric in ["crps_difference","twcrps_difference"]:
            gain=-b[metric]
            stability.append({"family":family,"reference":reference,"endpoint":metric.replace("difference","gain_positive"),"passing":int(gain.gt(0).sum()),"n_seeds":b.seed.nunique(),"median_gain":float(gain.median())})
    pd.DataFrame(stability).to_csv(NATIVE/"direction_stability.csv",index=False)
    T.write_json(NATIVE/"completion.json",{"complete":True,"target":"H7","seeds":list(range(20)),"outer_fits":540,
        "trend_replicates":200,"deep_models_refitted":False,"historical_registered_H30_verdicts":"unchanged",
        "scope":"native target-specific classical and annual/risk model refits, not every window/deep-model/tolerance combination"})


def main():
    p=argparse.ArgumentParser();p.add_argument("--audit-only",action="store_true");p.add_argument("--summary-only",action="store_true");a=p.parse_args()
    if not a.summary_only:audit()
    if not a.audit_only:summarize()
    return 0


if __name__=="__main__":raise SystemExit(main())
