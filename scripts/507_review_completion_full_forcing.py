#!/usr/bin/env python3
"""Full opened USGS source forcing comparisons with exact original controls.

The water panel, input window, lag calendar and unscaled Ridge recipe are the
original ones. Daymet changes both product and aggregation (tmin/tmax midpoint),
so its effect cannot be attributed to spatial resolution alone. These source
comparisons do not request independent NZ water-temperature outcomes.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import threading
import time
import numpy as np
import pandas as pd
import requests
from joblib import Parallel,delayed
from sklearn.linear_model import Ridge
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels,MIN_TRAIN_ROWS

OUT=T.ROOT/"results/wrr_review_completion_20261024/inputs/forcing_full_source_exact"
RAW=OUT.parent/"daymet_raw"
LOCK=threading.Lock();LAST_REQUEST=0.;SERVICE_STOP=threading.Event()
KEYS=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]


def slot():
    global LAST_REQUEST
    while True:
        if SERVICE_STOP.is_set():raise RuntimeError("stopped_after_service_error")
        with LOCK:
            path=OUT/"quota_status.json";deadline=0.
            if path.exists():
                q=json.loads(path.read_text())
                deadline=(pd.Timestamp(q["observed_utc"])+pd.Timedelta(seconds=q["retry_after_seconds"]+1)).timestamp()
            delay=max(deadline,LAST_REQUEST+2.)-time.time()
            if delay<=0:LAST_REQUEST=time.time();return
        time.sleep(min(delay,30.))


def acquire_one(row):
    path=RAW/(str(row["site_no"])+".csv")
    try:
        if not path.exists():
            params={"lat":float(row["dec_lat_va"]),"lon":float(row["dec_long_va"]),"vars":"tmin,tmax",
                    "start":"1980-01-01","end":"2025-12-31","format":"csv"}
            while True:
                slot();r=requests.get("https://daymet.ornl.gov/single-pixel/api/data",params=params,timeout=120)
                if r.status_code==429:
                    try:delay=max(1,int(r.headers.get("Retry-After","60")))
                    except ValueError:delay=60
                    with LOCK:T.write_json(OUT/"quota_status.json",{"observed_utc":datetime.now(timezone.utc).isoformat(),"retry_after_seconds":delay})
                    continue
                if r.status_code in [400,401,403,404,410,422]:SERVICE_STOP.set()
                r.raise_for_status()
                if not any(line.startswith("year,yday") for line in r.text.splitlines()):raise ValueError("no Daymet CSV header")
                temporary=path.with_suffix(".csv.tmp");temporary.write_text(r.text);temporary.replace(path)
                T.write_json(path.with_suffix(".request.json"),{"url":r.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),
                    "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"data_role":"forcing at already opened USGS source site","NZ_water_values_requested":False})
                break
        helper=T.load_script("full_forcing_daymet_parser",T.ROOT/"scripts/469_review_completion_inputs.py")
        _,series,error=helper.daymet(type("Site",(),row)(),RAW)
        if series is None:raise ValueError(error)
        return {"station_id":str(row["site_no"]),"status":"available","n_days":int(series.notna().sum())}
    except (requests.RequestException,ValueError,RuntimeError) as error:
        return {"station_id":str(row["site_no"]),"status":"unavailable","reason":str(error)}


def station(job,cohort,driver=None,driver_name="Daymet",flow_enabled=True):
    core=T.load_script("full_forcing_source_recipe",T.ROOT/"scripts/431_tr_cases.py")
    helper=T.load_script("full_forcing_covariate_recipe",T.ROOT/"scripts/469_review_completion_inputs.py")
    site=job["station_id"]
    highres=driver
    if driver_name=="Daymet" and driver is None and (RAW/(site+".csv")).exists():
        metadata=pd.read_csv(OUT/"roster.csv",dtype={"site_no":str}).set_index("site_no").loc[site]
        _,highres,_=helper.daymet(type("Site",(),metadata.to_dict()|{"site_no":site})(),RAW)
    panel=core.read_temperature_panel(job["input_path"]);panel.columns=panel.columns.astype(str);panel=panel.asfreq("D")
    air=core.station_air_series(Path(job["air_input_path"]),job["network_id"],site,panel.index)
    d=pd.DataFrame({"water_c":panel[site],"air_c":air if air is not None else np.nan},index=panel.index)
    flow=pd.read_parquet(T.E1/"usgs_flow.parquet",filters=[("site","==",site)]) if flow_enabled else pd.DataFrame()
    # Keep contradictions unavailable instead of averaging distinct daily values.
    q=None
    if len(flow):
        q=flow.groupby("date").flow_cms.agg(lambda s:s.dropna().iloc[0] if s.dropna().nunique()==1 else np.nan)
        q=q.where(q.ge(0)).sort_index().asfreq("D")
    shift=T.hemisphere_shift_days(job.get("latitude"))
    if shift:
        d.index+=pd.Timedelta(days=shift)
        for series in [highres,q]:
            if series is not None:series.index+=pd.Timedelta(days=shift)
    rows=[]
    for year,block in cohort.groupby("year"):
        held=d.index.year==year;truth=d.water_c.to_numpy()[held]
        arms=[("POWER",d.air_c),(driver_name,highres)]+([("POWER_flow",d.air_c)] if flow_enabled else [])
        for arm,driver in arms:
            prediction=np.full(held.sum(),np.nan);n_train=0
            if driver is not None and (arm!="POWER_flow" or q is not None):
                driver=driver.reindex(d.index)
                local=StationModels(target=d.water_c,donors=pd.DataFrame(index=d.index),air=driver,train_mask=pd.Series(~held,index=d.index))
                x=local._air_design(d.index)
                if arm=="POWER_flow":
                    log=np.log1p(q.reindex(d.index))
                    x=np.column_stack([x]+[log.shift(lag).to_numpy() for lag in [0,1,3,7]])
                train=(~held)&np.isfinite(d.water_c.to_numpy())&np.isfinite(x).all(axis=1)
                n_train=int(train.sum())
                if arm!="POWER_flow":prediction=local.air_predict(d.index[held])
                elif n_train>=MIN_TRAIN_ROWS:
                    model=Ridge(alpha=1).fit(x[train],d.water_c.to_numpy()[train]);good=np.isfinite(x[held]).all(axis=1)
                    if good.any():prediction[good]=model.predict(x[held][good])
            for _,r in block.iterrows():
                mask=T.mask_from_runs(r.mask_runs,len(truth));completed=truth.copy();completed[mask]=prediction[mask]
                available=bool(np.isfinite(completed).all());point=float(T.window_means(completed,30).max()) if available else np.nan
                rows.append({**{k:r[k] for k in KEYS},"arm":arm,"available":available,"truth":r.eval_truth_h30,"point":point,
                    "error":point-r.eval_truth_h30,"hidden_daily_mae":float(np.mean(np.abs(prediction[mask]-truth[mask]))) if available else np.nan,
                    "n_daily_training_observations":n_train})
    return pd.DataFrame(rows)


def summarize(frame,cases,alternatives=("Daymet","POWER_flow")):
    control=frame.loc[frame.arm.eq("POWER")].merge(cases[KEYS+["h30__air_ridge"]],on=KEYS,validate="one_to_one")
    common=control.point.notna()&control.h30__air_ridge.notna()
    audit={"case_rows":len(control),"n_both_available":int(common.sum()),
           "availability_disagreements":int((control.point.notna()!=control.h30__air_ridge.notna()).sum()),
           "maximum_point_difference":float((control.point-control.h30__air_ridge).abs()[common].max())}
    audit["exact_source_verified"]=audit["availability_disagreements"]==0 and audit["maximum_point_difference"]<1e-9
    T.write_json(OUT/"original_core_control_audit.json",audit)
    if not audit["exact_source_verified"]:raise RuntimeError("Full forcing POWER control differs from original source")
    summaries=[];intervals=[]
    membership=pd.read_parquet(T.ROOT/"results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",columns=["station_key","independence_group"]).drop_duplicates()
    if membership.station_key.duplicated().any():raise RuntimeError("A physical station must not cross connected bootstrap groups")
    group_map=membership.set_index("station_key").independence_group
    for arm in alternatives:
        left=frame.loc[frame.arm.eq("POWER")];right=frame.loc[frame.arm.eq(arm)]
        pairs=left.merge(right,on=KEYS,suffixes=("_POWER","_alternative"),validate="one_to_one")
        for name,keep in [("all",np.ones(len(pairs),bool)),("danger",pairs.peak_overlap.ge(.5)),("air_layer_danger",pairs.peak_overlap.ge(.5)&pairs.policy_choice.eq("air_ridge"))]:
            eligible=pairs.loc[keep];b=eligible.loc[eligible.available_POWER&eligible.available_alternative]
            difference=b.assign(difference=b.error_alternative.abs()-b.error_POWER.abs()).groupby("station_key").difference.mean()
            summaries.append({"arm":arm,"stratum":name,"n_eligible":len(eligible),"n_paired":len(b),"n_paired_stations":b.station_key.nunique(),
                "n_reference_available":int(eligible.available_POWER.sum()),"n_alternative_available":int(eligible.available_alternative.sum()),
                "n_alternative_only":int((~eligible.available_POWER&eligible.available_alternative).sum()),
                "POWER_bias":float(b.error_POWER.mean()),"alternative_bias":float(b.error_alternative.mean()),
                "POWER_mae":float(b.error_POWER.abs().mean()),"alternative_mae":float(b.error_alternative.abs().mean()),
                "POWER_failure_rate":float(b.error_POWER.abs().gt(.5).mean()),"alternative_failure_rate":float(b.error_alternative.abs().gt(.5).mean()),
                "POWER_hidden_daily_mae":float(b.hidden_daily_mae_POWER.mean()),"alternative_hidden_daily_mae":float(b.hidden_daily_mae_alternative.mean()),
                "median_station_mae_change":float(difference.median()),"fraction_stations_no_worse":float(difference.le(0).mean())})
            if len(b):
                units=pd.DataFrame({"group":b.station_key.map(group_map),"n":1,"reference":b.error_POWER.abs(),
                    "alternative":b.error_alternative.abs(),"failure_difference":b.error_alternative.abs().gt(.5).astype(int)-b.error_POWER.abs().gt(.5).astype(int)})
                if units.group.isna().any():raise RuntimeError("Unknown source bootstrap group")
                units=units.groupby("group").sum(numeric_only=True)
                rng=np.random.default_rng(507+len(intervals))
                multiplicity=rng.multinomial(len(units),np.full(len(units),1/len(units)),size=2000)
                n=multiplicity@units.n.to_numpy();ref=multiplicity@units.reference.to_numpy();alt=multiplicity@units.alternative.to_numpy()
                values={"relative_mae_reduction":(1-units.alternative.sum()/units.reference.sum(),1-alt/ref),
                    "absolute_mae_change":((units.alternative.sum()-units.reference.sum())/units.n.sum(),(alt-ref)/n),
                    "failure_rate_change":(units.failure_difference.sum()/units.n.sum(),multiplicity@units.failure_difference.to_numpy()/n)}
                for metric,(point,draws) in values.items():
                    intervals.append({"arm":arm,"stratum":name,"metric":metric,"n_groups":len(units),"n_bootstrap":2000,
                        "point":float(point),"lower":float(np.quantile(draws,.025)),"upper":float(np.quantile(draws,.975)),
                        "scope":"connected-group resampling of fixed available source cases; no mask/model repetition or new-climate guarantee"})
    pd.DataFrame(summaries).to_csv(OUT/"paired_summary.csv",index=False)
    pd.DataFrame(intervals).to_csv(OUT/"paired_group_bootstrap.csv",index=False)


def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument("--stage",choices=["acquire","analyse","all"],default="all")
    p.add_argument("--workers",type=int,default=2);p.add_argument("--analysis-workers",type=int,default=16);p.add_argument("--limit",type=int,default=0);a=p.parse_args()
    if a.limit:OUT=OUT.with_name(OUT.name+f"_smoke_{a.limit}")
    OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(parents=True,exist_ok=True)
    cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    sites=pd.read_csv(T.E1/"usgs_site_metadata.csv",dtype={"site_no":str})
    sites=sites.loc[sites.site_no.isin(cases.loc[cases.provider.eq("usgs"),"station_id"].unique())].sort_values("site_no")
    if a.limit:sites=sites.head(a.limit)
    sites.to_csv(OUT/"roster.csv",index=False)
    T.write_json(OUT/"design.json",{"n_physical_stations":len(sites),"partial":bool(a.limit),
        "selection":"all benchmarkable opened USGS source sites with metadata; sorted by ID, no selection by error",
        "inputs":"network-specific original full-precision water panel and forcing; original input window",
        "model":"unstandardized Ridge alpha1, source air lags/harmonics and minimum120 training rows, complete held year excluded",
        "flow":"log1p flow lags0/1/3/7, calendar days, contradictory daily values unavailable; no flow means unavailable arm",
        "Daymet":"1km tmin/tmax midpoint, not daily mean; omitted leap-year December31 and affected lags remain unavailable",
        "interpretation":"point reconstruction sensitivity; product, timing and aggregation change together; no refitted annual distribution or transfer guarantee",
        "NZ_water_values_requested":False})
    if a.stage in ["acquire","all"]:
        records=[]
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            futures=[pool.submit(acquire_one,row) for row in sites.to_dict("records")]
            for future in as_completed(futures):
                records.append(future.result())
                T.write_json(OUT/"acquisition_progress.json",{"processed":len(records),"requested":len(sites),"updated_utc":datetime.now(timezone.utc).isoformat()})
        T.write_json(OUT/"acquisition.json",{"n_requested":len(sites),"n_available":sum(r["status"]=="available" for r in records),"records":records,"service_stop":SERVICE_STOP.is_set()})
    if a.stage in ["analyse","all"]:
        core=T.load_script("full_forcing_parent",T.ROOT/"scripts/431_tr_cases.py")
        jobs=[j for j in core.jobs_for("source") if j["provider"]=="usgs" and j["station_id"] in set(sites.site_no)]
        parts=Parallel(n_jobs=a.analysis_workers,verbose=10)(delayed(station)(j,cases.loc[cases.network_id.eq(j["network_id"])&cases.station_id.eq(j["station_id"])&cases.year.between(1981,2025)]) for j in jobs)
        frame=pd.concat(parts,ignore_index=True);frame.to_parquet(OUT/"cases.parquet",index=False)
        summarize(frame,cases)
        T.write_json(OUT/"analysis_summary.json",{"complete":True,"partial":bool(a.limit),"n_station_input_jobs":len(jobs),"rows":len(frame),"arms":sorted(frame.arm.unique())})
    return 0


if __name__=="__main__":raise SystemExit(main())
