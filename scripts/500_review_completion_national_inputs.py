#!/usr/bin/env python3
"""Metadata-fixed national USGS source acquisition, separate from NZ testing.

Full numeric records consolidate the remaining availability audit with the
H30 source application. Old dates-only files stay unchanged and identifiable.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlencode,urlsplit,parse_qs,urlunsplit
import requests
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.national import clean_native_features,annual_source_panel

OUT=T.ROOT/"results/wrr_review_completion_20261024/national_meaning"
DATA=T.ROOT/"data/external/wrr_review_national_20261024"
AVAIL=OUT.parent/"national_availability"
API="https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"
OLD=T.ROOT/"data/external/wrr_target_recovery_20261022/usgs_new/values_raw"
LIMIT=50000
LOCK=threading.Lock();LAST_REQUEST=0.;NEXT_REQUEST=0.
SERVICE_STOP=threading.Event()


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


HELPER_PATH=T.ROOT/"src/stream_recoverability/experiments/tr_revision/national.py"
HELPER_BYTES=HELPER_PATH.read_bytes()
HELPER_SHA=hashlib.sha256(HELPER_BYTES).hexdigest()


def atomic_gzip(path,document):
    temp=path.with_suffix(path.suffix+".tmp")
    with gzip.open(temp,"wt") as stream:json.dump(document,stream)
    temp.replace(path)


def prepare():
    OUT.mkdir(parents=True,exist_ok=True);DATA.mkdir(parents=True,exist_ok=True)
    source=AVAIL/"national_stream_site_roster.csv"
    roster=pd.read_csv(source,dtype={"station_id":str,"series_id":str,"hydrologic_unit_code":str})
    roster.to_csv(OUT/"national_roster.csv",index=False)
    selected=roster.loc[roster.maximum_full_years.ge(15)|roster.maximum_full_years.isna()]
    selected.to_csv(OUT/"candidate_roster.csv",index=False)
    plan={"role":"exploratory national source application; not independent validation or public preregistration",
          "metadata_roster":str(source.relative_to(T.ROOT)),"metadata_roster_sha256":digest(source),
          "n_catalog_stream_sites":len(roster),"n_metadata_candidates":len(selected),"years":[1981,2025],
          "acquisition_padding":["1980-01-01","2026-01-02"],"one_series":"same longest-metadata-support primary daily mean per physical site as the dates-only census; no sensor unions",
          "eligibility":"at least fifteen eligible years per rule; complete, annual90, annual75, published May-September90, and supported retained years reported separately",
          "reference":"same source station ingest gate: approved finite Celsius, explicit sentinel/range flags, station rejection retained in denominator; provisional is reported but never called an absent date",
          "imputation":"at least four complete historical years; at least thirty usable observed days and no provisional/ambiguous observations in a delivered year; no unsupported success",
          "application":"source-fixed global annual distribution/P2 weights and interval offsets; local other-year history fits daily models. This does not verify natural-gap truth or population trend accuracy.",
          "field_inference":"same-roster and expanded-roster comparisons, conservative merged HUC2 basin blocks, BH and synchronized year nulls; exchangeability remains an assumption",
          "old_dates_only_files":"preserved; this separate value-bearing source phase must never be labeled dates-only or blind",
          "NZ_independent_temperature_access":False,"source_model_sha256":digest(OUT.parent/"deployment/global_source_candidate.joblib"),
          "classical_calibration_sha256":digest(OUT.parent/"deployment/classical_calibration.json")}
    path=OUT/"plan.json"
    if path.exists() and json.loads(path.read_text())!=plan:raise RuntimeError("Existing national plan differs; preserve it and explicitly version a changed analysis")
    T.write_json(path,plan)
    return selected


def quota_deadline():
    deadlines=[]
    for path in [AVAIL/"quota_status.json",OUT/"quota_status.json"]:
        if path.exists():
            d=json.loads(path.read_text());deadlines.append(pd.Timestamp(d["observed_utc"])+pd.Timedelta(seconds=d["retry_after_seconds"]+1))
    return max(deadlines).timestamp() if deadlines else 0.


def request_slot():
    global LAST_REQUEST
    while True:
        if SERVICE_STOP.is_set():raise RuntimeError("deferred_after_service_error")
        with LOCK:
            delay=max(NEXT_REQUEST,quota_deadline(),LAST_REQUEST+3.7)-time.time()
            if delay<=0:LAST_REQUEST=time.time();return
        time.sleep(min(delay,30.))


def fetch(row):
    global NEXT_REQUEST
    path=DATA/"raw"/(row["series_id"]+".json.gz")
    if path.exists():return json.load(gzip.open(path,"rt")),str(path.relative_to(T.ROOT))
    old=OLD/(row["series_id"]+".json")
    if old.exists():
        d=json.loads(old.read_text())
        if d.get("series_id")==row["series_id"] and all("value" in f for f in d["features"]):
            return d,str(old.relative_to(T.ROOT))
    params={"f":"json","time_series_id":row["series_id"],"properties":"time,value,approval_status,qualifier",
            "skipGeometry":"true","limit":LIMIT,"datetime":"1980-01-01T00:00:00Z/2026-01-02T00:00:00Z"}
    url=API+'?'+urlencode(params);features=[];pages=[]
    while url:
        request_slot()
        headers={"User-Agent":"stream-recoverability national opened-source H30 application"}
        key=next((os.environ.get(n) for n in ["USGS_WATERDATA_API_KEY","USGS_API_KEY"] if os.environ.get(n)),None)
        if key:headers["X-Api-Key"]=key
        response=requests.get(url,headers=headers,timeout=90)
        if response.status_code==429:
            try:delay=max(1,int(response.headers.get("Retry-After","60")))
            except ValueError:delay=60
            with LOCK:
                NEXT_REQUEST=max(NEXT_REQUEST,time.time()+delay+1)
                T.write_json(OUT/"quota_status.json",{"observed_utc":datetime.now(timezone.utc).isoformat(),"retry_after_seconds":delay,
                    "rate_limit":response.headers.get("X-RateLimit-Limit"),"remaining":response.headers.get("X-RateLimit-Remaining"),"api_key_supplied":key is not None})
            print(f"National source service quota: resume same page in {delay+1}s",flush=True);continue
        if response.status_code in [400,401,403,404,410,422]:SERVICE_STOP.set()
        response.raise_for_status();d=response.json()
        page=[]
        for feature in d.get("features",[]):
            props=feature.get("properties",{})
            if set(props)-{"time","value","approval_status","qualifier"}:
                SERVICE_STOP.set();raise RuntimeError("Unexpected value projection")
            if "time" not in props or "value" not in props:
                SERVICE_STOP.set();raise RuntimeError("Daily response omitted required numeric fields")
            page.append(props)
        features.extend(page);pages.append({"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"n_records":len(page)})
        # v0 installations may enforce a 10k cap even when the documented
        # modern limit is 50k. Never truncate a full legacy-sized page.
        if not page or (len(page)<LIMIT and len(page)!=10000):break
        next_url=next((x["href"] for x in d.get("links",[]) if x.get("rel")=="next"),None)
        if not next_url:break
        parts=urlsplit(next_url);query=parse_qs(parts.query)
        query["properties"]=["time,value,approval_status,qualifier"];query["limit"]=[str(LIMIT)]
        url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query,doseq=True),parts.fragment))
        if any(x["url"]==url for x in pages):raise RuntimeError("Repeated page link")
    d={"series_id":row["series_id"],"station_id":row["station_id"],"features":features,"requests":pages,
       "role":"opened national source data; not NZ independent cohort","value_fields_requested":True}
    atomic_gzip(path,d)
    return d,str(path.relative_to(T.ROOT))


def one(row):
    try:
        result_path=OUT/"site_results"/(row["station_id"]+".json")
        if result_path.exists():
            saved=json.loads(result_path.read_text())
            origin=T.ROOT/saved.get("source","")
            if (saved.get("helper_sha256")==HELPER_SHA and origin.is_file() and saved.get("raw_source_sha256")==digest(origin)
                and all((DATA/folder/(row["station_id"]+".parquet")).exists() for folder in ["daily","annual"])):
                return saved
        raw,origin=fetch(row)
        daily,qc=clean_native_features(row,raw["features"])
        path=DATA/"daily"/(row["station_id"]+".parquet");temporary=path.with_suffix(".parquet.tmp")
        daily.to_parquet(temporary,index=False);temporary.replace(path)
        annual=annual_source_panel(row,daily)
        path=DATA/"annual"/(row["station_id"]+".parquet");temporary=path.with_suffix(".parquet.tmp")
        annual.to_parquet(temporary,index=False);temporary.replace(path)
        result={"station_id":row["station_id"],"series_id":row["series_id"],"status":"processed" if len(raw["features"]) else "no_public_daily_records",
                "source":origin,"raw_source_sha256":digest(T.ROOT/origin),"helper_sha256":HELPER_SHA,
                "n_raw":len(raw["features"]),"n_annual_rows":len(annual),"qc":qc}
    except (requests.RequestException,ValueError,KeyError,RuntimeError) as error:
        result={"station_id":row["station_id"],"series_id":row["series_id"],"status":"deferred_after_service_error" if SERVICE_STOP.is_set() else "unavailable","error":str(error)}
    T.write_json(OUT/"site_results"/(row["station_id"]+".json"),result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument("--prepare-only",action="store_true");p.add_argument("--cached-only",action="store_true");p.add_argument("--workers",type=int,default=2);p.add_argument("--max-sites",type=int);a=p.parse_args()
    selected=prepare()
    if a.prepare_only:return 0
    for path in [DATA/"raw",DATA/"daily",DATA/"annual",OUT/"site_results"]:path.mkdir(parents=True,exist_ok=True)
    (OUT/"processing_code").mkdir(exist_ok=True)
    (OUT/"processing_code"/(HELPER_SHA+".py")).write_bytes(HELPER_BYTES)
    total_candidates=len(selected)
    selected["cached"]=[(DATA/"raw"/(s+".json.gz")).exists() or (OLD/(s+".json")).exists() for s in selected.series_id]
    selected=selected.sort_values(["cached","station_id"],ascending=[False,True])
    if a.cached_only:selected=selected.loc[selected.cached]
    if a.max_sites is not None:selected=selected.head(a.max_sites)
    results=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(one,row):row for row in selected.to_dict("records")}
        for future in as_completed(futures):
            results.append(future.result())
            if len(results)%25==0:
                print(f"national source inputs {len(results)}/{len(selected)}",flush=True)
                T.write_json(OUT/"progress.json",{"updated_utc":datetime.now(timezone.utc).isoformat(),"processed_sites":len(results),"requested_sites":len(selected),"pid":os.getpid(),"source_values_requested":True,"NZ_independent_values_requested":False})
    T.write_json(OUT/"progress.json",{"updated_utc":datetime.now(timezone.utc).isoformat(),
        "processed_sites":len(results),"requested_sites":len(selected),"pid":os.getpid(),"stage":"finished",
        "all_planned_attempted":len(selected)==total_candidates and not SERVICE_STOP.is_set(),
        "source_values_requested":not a.cached_only,"NZ_independent_values_requested":False})
    T.write_json(OUT/"acquisition.json",{"n_requested":len(selected),"all_planned_attempted":len(selected)==total_candidates and not SERVICE_STOP.is_set(),"service_stop":SERVICE_STOP.is_set(),"cache_only":a.cached_only,"statuses":pd.Series([r["status"] for r in results]).value_counts().to_dict(),"new_NZ_values_requested":False,"source_values_requested":not a.cached_only})
    return 0


if __name__=="__main__":raise SystemExit(main())
