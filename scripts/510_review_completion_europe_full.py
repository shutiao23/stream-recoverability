#!/usr/bin/env python3
"""ERA5-Land at every opened European source site, with exact source controls."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
import numpy as np
import pandas as pd
import requests
from joblib import Parallel,delayed
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024/europe_full_source_exact"
QUOTA=T.load_script("europe_full_forcing_service",T.ROOT/"scripts/507_review_completion_full_forcing.py")
QUOTA.OUT=OUT


def quota_delay(response,observed_at=None):
    """Use the provider's header or explicit minute/hour/day message."""
    observed=observed_at or datetime.now(timezone.utc)
    header=response.headers.get("Retry-After")
    if header:
        try:return max(1,int(header)),"Retry-After header"
        except ValueError:
            try:
                until=parsedate_to_datetime(header)
                if until.tzinfo is None:until=until.replace(tzinfo=timezone.utc)
                return max(1,math.ceil(until.timestamp()-observed.timestamp())),"Retry-After HTTP-date header"
            except (ValueError,TypeError,OverflowError):pass
    message=response.text.lower()
    if "minutely" in message:return 60,"provider minutely-limit response"
    # Official RateLimiter.swift clears these counters during the first60s
    # of each UTC hour/day. Keep the entire reset minute. An actual numeric
    # Retry-After above always takes precedence over this body interpretation.
    # https://github.com/open-meteo/open-meteo/blob/main/Sources/App/Helper/Vapor/RateLimiter.swift
    for kind,period in [("hourly",3600),("daily",86400)]:
        if kind in message:
            epoch=observed.timestamp()
            start=math.floor(epoch/period)*period
            reset=start+60 if epoch-start<60 else start+period+60
            return max(1,math.ceil(reset-epoch)),f"inferred documented UTC {kind} reset plus60s"
    return 3600,"conservative fallback; no specific provider delay"


def weather_slot():
    """Separate long historical requests, including across resumed runs."""
    while True:
        if QUOTA.SERVICE_STOP.is_set():raise RuntimeError("stopped_after_service_error")
        with QUOTA.LOCK:
            path=OUT/"request_clock.json";last=json.loads(path.read_text()).get("last_request_epoch",0.) if path.exists() else 0.
            delay=last+15.-time.time()
            qpath=OUT/"quota_status.json"
            if qpath.exists():
                q=json.loads(qpath.read_text())
                delay=max(delay,(pd.Timestamp(q["observed_utc"])+pd.Timedelta(seconds=q["retry_after_seconds"]+1)).timestamp()-time.time())
            if delay<=0:
                T.write_json(path,{"last_request_epoch":time.time()});return
        time.sleep(min(delay,30.))


def fetch(row):
    path=OUT/"raw"/(row["provider"]+'__'+row["station_id"]+'.json')
    previous=OUT.parent/"europe_forcing/raw"/path.name
    try:
        if not path.exists() and previous.exists():
            shutil.copy2(previous,path)
            if previous.with_suffix(".request.json").exists():shutil.copy2(previous.with_suffix(".request.json"),path.with_suffix(".request.json"))
        if not path.exists():
            if not np.isfinite(float(row["latitude"])+float(row["longitude"])):raise ValueError("source_coordinates_unavailable")
            params={"latitude":float(row["latitude"]),"longitude":float(row["longitude"]),"start_date":row["weather_start"],"end_date":row["weather_end"],
                "daily":"temperature_2m_mean","models":"era5_land","timezone":"UTC"}
            while True:
                weather_slot();r=requests.get("https://archive-api.open-meteo.com/v1/archive",params=params,timeout=120)
                if r.status_code!=429:break
                delay,source=quota_delay(r)
                with QUOTA.LOCK:T.write_json(OUT/"quota_status.json",{"observed_utc":datetime.now(timezone.utc).isoformat(),"retry_after_seconds":delay,
                    "delay_source":source,"provider_message":r.text[:600]})
                print(f"European historical weather quota: resume same request after {delay}s",flush=True)
            if r.status_code in [400,401,403,404,410,422]:QUOTA.SERVICE_STOP.set()
            r.raise_for_status();d=r.json()
            if "daily" not in d or d.get("daily_units",{}).get("temperature_2m_mean")!="°C":raise ValueError("unrecognized meteorological response")
            temporary=path.with_suffix(".json.tmp");temporary.write_bytes(r.content);temporary.replace(path)
            T.write_json(path.with_suffix(".request.json"),{"url":r.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"role":"meteorological covariate at already opened source station; no NZ water request"})
        d=json.loads(path.read_text());series=pd.Series(d["daily"]["temperature_2m_mean"],index=pd.to_datetime(d["daily"]["time"]),dtype=float)
        return row["station_key"],series,{"station_key":row["station_key"],"status":"available","n_days":int(series.notna().sum())}
    except (requests.RequestException,ValueError,KeyError,RuntimeError) as error:
        return row["station_key"],None,{"station_key":row["station_key"],"status":"unavailable","reason":str(error)}


def one(job,cohort,driver,folder):
    helper=T.load_script("europe_full_exact_daily_model",T.ROOT/"scripts/507_review_completion_full_forcing.py")
    helper.OUT=Path(folder)
    return helper.station(job,cohort,driver=driver,driver_name="ERA5_Land",flow_enabled=False)


def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=2);p.add_argument("--analysis-workers",type=int,default=16);p.add_argument("--limit",type=int,default=0);a=p.parse_args()
    if a.limit:OUT=OUT.with_name(OUT.name+f"_smoke_{a.limit}")
    QUOTA.OUT=OUT;OUT.mkdir(parents=True,exist_ok=True);(OUT/"raw").mkdir(exist_ok=True)
    cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    core=T.load_script("europe_full_exact_source",T.ROOT/"scripts/431_tr_cases.py")
    jobs=[j for j in core.jobs_for("source") if j["provider"]!="usgs" and j["station_key"] in set(cases.station_key)]
    fields=["provider","station_id","station_key","latitude","longitude"]
    roster=pd.DataFrame([{k:j.get(k,np.nan) for k in fields} for j in jobs]).drop_duplicates("station_key").sort_values(["provider","station_id"])
    coordinates=pd.read_csv(T.ROOT/"data/interim/v18_station_coordinates.csv",dtype={"station_id":str})
    coordinates["station_key"]=coordinates.provider+"|"+coordinates.station_id
    coordinates=coordinates.drop_duplicates("station_key").set_index("station_key")
    for name in ["latitude","longitude"]:
        roster[name]=roster[name].fillna(roster.station_key.map(coordinates[name]))
    supplement_path=OUT.parent/"inputs/source_coordinate_supplement.csv"
    if supplement_path.exists():
        supplement=pd.read_csv(supplement_path,dtype={"station_id":str}).set_index("station_key")
        if not supplement.index.is_unique:raise RuntimeError("Ambiguous supplementary station coordinates")
        for name in ["latitude","longitude"]:
            roster[name]=roster[name].fillna(roster.station_key.map(supplement[name]))
    # Request only the source station's observed-history range plus the full
    # fourteen-day lag support. No target outcome/error selects this interval.
    ranges={}
    for path,b in pd.DataFrame(jobs).groupby("input_path"):
        panel=core.read_temperature_panel(path);panel.columns=panel.columns.astype(str)
        for j in b.to_dict("records"):
            present=panel[j["station_id"]].dropna().index
            if len(present):
                start=max(pd.Timestamp("1980-01-01"),present.min()-pd.Timedelta(days=14))
                end=min(pd.Timestamp("2025-12-31"),present.max())
                old=ranges.get(j["station_key"],(start,end));ranges[j["station_key"]]=(min(start,old[0]),max(end,old[1]))
    roster["weather_start"]=roster.station_key.map({k:str(v[0].date()) for k,v in ranges.items()})
    roster["weather_end"]=roster.station_key.map({k:str(v[1].date()) for k,v in ranges.items()})
    if a.limit:roster=roster.head(a.limit)
    jobs=[j for j in jobs if j["station_key"] in set(roster.station_key)]
    roster.to_csv(OUT/"roster.csv",index=False)
    T.write_json(OUT/"design.json",{"population":"all benchmarkable non-USGS European opened source sites", "partial":bool(a.limit),"n_physical_sites":len(roster),
        "selection":"source roster with coordinates fixed before scoring; no error-based selection or substitutions","provider":"Open-Meteo ERA5-Land daily mean2m air; UTC; original POWER follows original source date convention",
        "control":"original network-specific full-precision water and POWER panels, input window, unscaled Ridge alpha1 and held-year exclusion",
        "weather_range":"station water-history date support plus14 preceding lag days; reused longer cached responses remain valid",
        "coordinate_supplement":str(supplement_path.relative_to(T.ROOT)) if supplement_path.exists() else None,
        "coordinate_supplement_sha256":hashlib.sha256(supplement_path.read_bytes()).hexdigest() if supplement_path.exists() else None,
        "interpretation":"product and time convention sensitivity, not pure spatial resolution or perfect observed local forcing; no new annual distribution/risk refit",
        "NZ_water_values_requested":False})
    series={};records=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(fetch,row) for row in roster.to_dict("records")]
        for future in as_completed(futures):
            key,values,record=future.result();records.append(record)
            if values is not None:series[key]=values
            T.write_json(OUT/"acquisition_progress.json",{"processed":len(records),"requested":len(roster),"retrieved":len(series),"updated_utc":datetime.now(timezone.utc).isoformat()})
    T.write_json(OUT/"acquisition.json",{"requested":len(roster),"retrieved":len(series),"records":records,"service_stop":QUOTA.SERVICE_STOP.is_set()})
    parts=Parallel(n_jobs=a.analysis_workers,verbose=10)(delayed(one)(j,cases.loc[cases.network_id.eq(j["network_id"])&cases.station_id.eq(j["station_id"])&cases.year.between(1981,2025)],series.get(j["station_key"]),str(OUT)) for j in jobs)
    frame=pd.concat(parts,ignore_index=True);frame.to_parquet(OUT/"cases.parquet",index=False)
    QUOTA.summarize(frame,cases,alternatives=["ERA5_Land"])
    coordinates_available=int(np.isfinite(roster.latitude+roster.longitude).sum())
    T.write_json(OUT/"analysis_summary.json",{"complete":True,"partial":bool(a.limit) or len(series)!=coordinates_available,
        "requested":len(roster),"coordinates_available":coordinates_available,"coordinates_unavailable":len(roster)-coordinates_available,
        "retrieved":len(series),"n_station_input_jobs":len(jobs),"rows":len(frame)})
    return 0


if __name__=="__main__":raise SystemExit(main())
