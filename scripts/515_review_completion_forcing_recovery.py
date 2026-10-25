#!/usr/bin/env python3
"""Recompute recovery-model inputs for each source meteorological/flow arm.

Both the target year and each residual-validation year are excluded. New
drivers change residual moments and recovery probabilities, while source water
climatology/mask geometry stay fixed. Annual D2/risk weights are not retrained.
"""
from __future__ import annotations
import os
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[name]="1"
import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels,MIN_TRAIN_ROWS
from stream_recoverability.experiments.tr_revision.observed_air import parse_tavg
from stream_recoverability.experiments.tr_revision.ridge_history import YearExcludedRidge

OUT=T.ROOT/"results/wrr_review_completion_20261024"
KEYS=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]


def one(job,cohort,region):
    core=T.load_script("forcing_recovery_core",T.ROOT/"scripts/431_tr_cases.py")
    helper=T.load_script("forcing_recovery_daymet",T.ROOT/"scripts/469_review_completion_inputs.py")
    law=T.load_script("forcing_recovery_model",T.ROOT/"scripts/wrr_tr_law.py")
    site=job["station_id"]
    panel=core.read_temperature_panel(job["input_path"]);panel.columns=panel.columns.astype(str);panel=panel.asfreq("D")
    air=core.station_air_series(Path(job["air_input_path"]),job["network_id"],site,panel.index)
    d=pd.DataFrame({"water":panel[site],"air":air if air is not None else np.nan},index=panel.index)
    drivers={"POWER":d.air};flow=None
    if region=="usgs":
        metadata=pd.read_csv(OUT/"inputs/forcing_full_source_exact/roster.csv",dtype={"site_no":str}).set_index("site_no").loc[site]
        _,drivers["Daymet"],_=helper.daymet(SimpleNamespace(**metadata.to_dict(),site_no=site),OUT/"inputs/daymet_raw")
        drivers["POWER_flow"]=d.air
        q=pd.read_parquet(T.E1/"usgs_flow.parquet",filters=[("site","==",site)])
        if len(q):
            flow=q.groupby("date").flow_cms.agg(lambda s:s.dropna().iloc[0] if s.dropna().nunique()==1 else np.nan)
            flow=flow.where(flow.ge(0)).sort_index().asfreq("D")
        matches=pd.read_csv(OUT/"inputs/observed_air_full_source_exact/metadata_roster.csv",dtype={"site_no":str}).set_index("site_no")
        met=matches.loc[site,"met_station"]
        path=OUT/"inputs/observed_air_full_source_exact/raw"/(str(met)+".dly")
        drivers["observed_TAVG"]=parse_tavg(path.read_text()).set_index("date").air_c if path.exists() else None
    else:
        path=OUT/"europe_full_source_exact/raw"/(job["provider"]+'__'+site+'.json')
        doc=json.loads(path.read_text())
        drivers["ERA5_Land"]=pd.Series(doc["daily"]["temperature_2m_mean"],index=pd.to_datetime(doc["daily"]["time"]),dtype=float)
    shift=T.hemisphere_shift_days(job.get("latitude"))
    if shift:
        d.index+=pd.Timedelta(days=shift)
        for name,series in drivers.items():
            if series is not None and name not in ["POWER","POWER_flow"]:series.index+=pd.Timedelta(days=shift)
        drivers["POWER"]=d.air
        if "POWER_flow" in drivers:drivers["POWER_flow"]=d.air
        if flow is not None:flow.index+=pd.Timedelta(days=shift)
    all_years=core.CORE.complete_years(d.water);y=d.water.to_numpy(float);year_labels=d.index.year.to_numpy()
    rows=[];audits=[]
    for arm,driver in drivers.items():
        local=StationModels(target=d.water,donors=pd.DataFrame(index=d.index),air=driver.reindex(d.index) if driver is not None else None,train_mask=pd.Series(True,index=d.index))
        x=local._air_design(d.index)
        if x is None:x=np.full((len(d),9),np.nan)
        if arm=="POWER_flow":
            log=np.log1p(flow.reindex(d.index)) if flow is not None else pd.Series(np.nan,index=d.index)
            x=np.column_stack([x]+[log.shift(lag).to_numpy() for lag in [0,1,3,7]])
        history=YearExcludedRidge(x,y,year_labels,min_rows=MIN_TRAIN_ROWS)
        checked=False
        for year,block in cohort.groupby("year"):
            held=year_labels==year;truth=y[held];train=(~held)&history.valid
            np.testing.assert_allclose(block.eval_truth_h30.to_numpy(),T.window_means(truth,30).max(),rtol=1e-10,atol=1e-10)
            prediction=np.full(held.sum(),np.nan)
            if train.sum()>=MIN_TRAIN_ROWS:
                fit=Ridge(alpha=1).fit(x[train],y[train]);good=np.isfinite(x[held]).all(axis=1)
                if good.any():prediction[good]=fit.predict(x[held][good])
            train_years=[v for v in all_years if v!=year]
            residual=history.residual_history(year,train_years)
            assert np.isnan(residual[held]).all(),"Target-year labels entered residual diagnostics"
            if not checked:
                for validation_year in train_years:
                    val=year_labels==validation_year;allowed=history.valid&~held&~val;good=val&np.isfinite(x).all(axis=1)
                    if allowed.sum()>=MIN_TRAIN_ROWS and good.any():
                        reference=Ridge(alpha=1).fit(x[allowed],y[allowed]).predict(x[good])
                        actual=history.predict(good,[year,validation_year])
                        np.testing.assert_allclose(actual,reference,rtol=1e-7,atol=1e-7)
                        audits.append({"network_id":job["network_id"],"station_key":job["station_key"],"arm":arm,
                            "target_year":int(year),"validation_year":int(validation_year),"n_training_rows":int(allowed.sum()),
                            "maximum_prediction_difference":float(np.max(np.abs(actual-reference)))})
                        checked=True;break
            peak_starts=[int(np.argmax(T.window_means(y[year_labels==v],30))) for v in train_years]
            warm=tuple(int(v) for v in block.warm_months.iloc[0].split(';'))
            moments=core.residual_moments(residual,d.index,warm)|core.peak_residual_moments(residual,d.index,train_years,peak_starts)
            for _,r in block.iterrows():
                mask=T.mask_from_runs(r.mask_runs,len(truth));completed=truth.copy();completed[mask]=prediction[mask]
                point=float(T.window_means(completed,30).max()) if np.isfinite(completed).all() else np.nan
                current=r.copy();current.update(pd.Series(moments));current["h30__policy"]=point
                if np.isfinite(point):
                    modeled=law.case_law(current,version="v2")
                else:modeled={"law_bias":np.nan,"law_sd":np.nan,"law_pfail":np.nan,"law_r2":np.nan}
                rows.append({**{k:r[k] for k in KEYS},"arm":arm,"point":point,"error":point-r.eval_truth_h30,
                    "recovery_probability":modeled["law_pfail"],"recovery_bias":modeled["law_bias"],"recovery_sd":modeled["law_sd"],
                    "residual_sigma":moments["law_sigma_r_warm"],"residual_phi":moments["law_phi_r"],
                    "n_oof_residual_days":int(np.isfinite(residual).sum()),"point_available":bool(np.isfinite(point))})
    return pd.DataFrame(rows),audits


def summarize(frame):
    rows=[];calibration=[]
    for (arm,family),b in frame.groupby(["arm","design_family"]):
        strata={"all":np.ones(len(b),bool),"danger":b.peak_overlap.ge(.5),"air_layer":b.policy_choice.eq("air_ridge"),
            "air_layer_danger":b.policy_choice.eq("air_ridge")&b.peak_overlap.ge(.5)}
        for name,selected in strata.items():
            eligible=b.loc[selected];valid=eligible.loc[eligible.point_available&eligible.recovery_probability.notna()]
            p=valid.recovery_probability.to_numpy();fail=valid.error.abs().gt(.5).to_numpy();rate=float(fail.mean()) if len(fail) else np.nan
            brier=float(np.mean((p-fail)**2)) if len(p) else np.nan
            rows.append({"arm":arm,"family":family,"stratum":name,"n_eligible":len(eligible),"n_valid":len(valid),
                "mae":float(valid.error.abs().mean()),"actual_failure_rate":rate,"mean_predicted_failure":float(p.mean()) if len(p) else np.nan,
                "auc":float(roc_auc_score(fail,p)) if len(np.unique(fail))==2 else np.nan,"brier":brier,
                "brier_skill":1-brier/(rate*(1-rate)) if 0<rate<1 else np.nan,"observed_bias":float(valid.error.mean()),"predicted_bias":float(valid.recovery_bias.mean())})
            bins=pd.cut(valid.recovery_probability,[-1e-12,.01,.025,.05,.1,.25,.5,1.],include_lowest=True)
            for label,block in valid.groupby(bins,observed=True):
                calibration.append({"arm":arm,"family":family,"stratum":name,"probability_bin":str(label),"n":len(block),
                    "predicted":float(block.recovery_probability.mean()),"actual":float(block.error.abs().gt(.5).mean())})
    return pd.DataFrame(rows),pd.DataFrame(calibration)


def main():
    p=argparse.ArgumentParser();p.add_argument("--region",choices=["usgs","europe"],required=True);p.add_argument("--workers",type=int,default=16);p.add_argument("--limit",type=int,default=0);p.add_argument("--after-pid",type=int);a=p.parse_args()
    folder=OUT/"inputs/forcing_recovery"/a.region
    if a.limit:folder=folder/f"smoke_{a.limit}"
    folder.mkdir(parents=True,exist_ok=True)
    if a.after_pid:
        proc=Path(f"/proc/{a.after_pid}")
        while proc.exists():
            try:command=(proc/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")
            except FileNotFoundError:break
            if "514_review_completion_europe_finish.py" not in command:
                if not command:break
                raise RuntimeError("The watched PID is no longer the source-weather completion helper")
            T.write_json(folder/"waiting.json",{"stage":"waiting_for_exact_source_weather","producer_pid":a.after_pid})
            time.sleep(30)
    if a.region=="europe":
        from wrr_review_forcing_reporting import europe_evidence
        if not europe_evidence(OUT)["full_source"]:raise RuntimeError("Full European weather comparison must finish first")
    cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    cases=cases.loc[cases.year.between(1981,2025)&(cases.provider.eq("usgs") if a.region=="usgs" else cases.provider.ne("usgs"))]
    core=T.load_script("forcing_recovery_parent",T.ROOT/"scripts/431_tr_cases.py")
    jobs=[j for j in core.jobs_for("source") if j["station_key"] in set(cases.station_key)]
    if a.limit:jobs=jobs[:a.limit]
    parts=Parallel(n_jobs=a.workers,verbose=10)(delayed(one)(j,cases.loc[cases.network_id.eq(j["network_id"])&cases.station_id.eq(j["station_id"])],a.region) for j in jobs)
    frame=pd.concat([part[0] for part in parts],ignore_index=True);audit=[row for part in parts for row in part[1]]
    expected=pd.read_parquet(OUT/("inputs/forcing_full_source_exact/cases.parquet" if a.region=="usgs" else "europe_full_source_exact/cases.parquet"))
    if a.region=="usgs":
        observed=pd.read_parquet(OUT/"inputs/observed_air_full_source_exact/cases.parquet")
        expected=pd.concat([expected,observed.loc[observed.arm.eq("observed_TAVG")]],ignore_index=True)
    merged=frame.merge(expected[KEYS+["arm","point"]],on=KEYS+["arm"],suffixes=("","_reference"),validate="one_to_one")
    if len(merged)!=len(frame):raise RuntimeError("Recovery case identities differ from input comparison")
    np.testing.assert_allclose(merged.point,merged.point_reference,atol=1e-9,rtol=1e-9,equal_nan=True)
    valid=merged.point.notna()&merged.point_reference.notna()
    summary,calibration=summarize(frame)
    frame.to_parquet(folder/"cases.parquet",index=False);summary.to_csv(folder/"summary.csv",index=False);calibration.to_csv(folder/"calibration.csv",index=False)
    T.write_json(folder/"numerical_audit.json",{"passed":True,"case_rows":len(frame),"maximum_point_difference":float((merged.point-merged.point_reference).abs()[valid].max()),
        "independent_sklearn_OOF_checks":audit,"residual_target_year_excluded":True})
    T.write_json(folder/"status.json",{"complete":True,"partial":bool(a.limit),"region":a.region,"n_station_input_jobs":len(jobs),"case_rows":len(frame),
        "recovery_model":"same Gaussian AR1 window-scale v2 used in source recovery analysis; recalculated driver-specific OOF residual moments",
        "OOF":"exclude target and residual validation years, using all other finite daily training rows",
        "annual_distribution_and_risk_weights_refitted":False,"new_NZ_water_values_requested":False})
    return 0


if __name__=="__main__":raise SystemExit(main())
