#!/usr/bin/env python3
"""Check shared reconstruction residuals before invoking triple collocation."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import json
import numpy as np
import pandas as pd
from scipy.stats import norm
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels,usable_donors
from stream_recoverability.experiments.v19_revision.data import station_air_series

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"inputs"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    c=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    selected=sorted(c.loc[c.n_visible_donors.gt(0)&c.air_available,"station_key"].unique())[:12]
    cases=T.load_script("r4_reference_jobs",T.ROOT/"scripts/431_tr_cases.py")
    jobs={job["station_key"]:job for job in cases.jobs_for("source")}
    rows=[]
    for station in selected:
        job=jobs[station];panel=read_temperature_panel(job["input_path"]).asfreq("D");panel.columns=panel.columns.astype(str)
        target=panel[job["station_id"]];donors=panel.drop(columns=job["station_id"])
        air=station_air_series(T.AIR,job["network_id"],job["station_id"],panel.index)
        years=cases.CORE.complete_years(target)
        for year in years[:2]:
            held=panel.index.year==year;allowed=pd.Series(~held,index=panel.index);index=panel.index[held]
            visible=usable_donors(donors,index,np.ones(len(index),bool))
            model=StationModels(target,donors,air,allowed)
            fit=model.donor_ridge(visible)
            if fit is None:
                continue
            donor=model.donor_predict(fit,index);airpred=model.air_predict(index);truth=target.loc[held].to_numpy()
            valid=np.isfinite(donor)&np.isfinite(airpred)&np.isfinite(truth)&index.month.isin([5,6,7,8,9])
            if valid.sum()<60:
                continue
            ed,ea=donor[valid]-truth[valid],airpred[valid]-truth[valid]
            rows.append(dict(station_key=station,year=int(year),group=job["independence_group"],n_common_warm_days=int(valid.sum()),residual_correlation=float(np.corrcoef(ed,ea)[0,1]),donor_daily_rmse=float(np.sqrt(np.mean(ed**2))),air_daily_rmse=float(np.sqrt(np.mean(ea**2))),reference="operational primary record; its own measurement error is not separated"))
    pd.DataFrame(rows).to_csv(OUT/"triple_collocation_assumption_diagnostic.csv",index=False)
    scenarios=[]
    for daily_sd in [.05,.1,.2,.5,1.]:
        for phi in [0.,.5,.9,.98]:
            n=30;j=np.arange(1,n);v=(n+2*np.sum((n-j)*phi**j))/n**2
            sd_window=daily_sd*np.sqrt(v)
            # Gaussian union bound over 336 overlapping windows; independence
            # of window means is unnecessary, but marginal normality is assumed.
            simultaneous=norm.ppf(1-.05/(2*336))*sd_window
            scenarios.append(dict(assumed_reference_daily_error_sd=daily_sd,assumed_AR1_phi=phi,window30_sd=float(sd_window),annual_max_absolute_error_95_union_bound=float(simultaneous),fits_point5_resolution=bool(simultaneous<=.5)))
    pd.DataFrame(scenarios).to_csv(OUT/"reference_precision_scenarios.csv",index=False)
    T.write_json(OUT/"reference_diagnostic_status.json",{"common_period_station_years":len(rows),"median_air_donor_residual_correlation":float(pd.DataFrame(rows).residual_correlation.median()) if rows else None,"triple_collocation_accuracy_estimated":False,"reason":"three independent error channels and a calibrated reference have not been established; observed primary error also induces shared residual correlation","precision_scenario":"assumed Gaussian AR1 daily reference error; bound on annual maximum from simultaneous bounds on linear window means; neither sensor-error parameters nor real-gap accuracy are inferred"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
