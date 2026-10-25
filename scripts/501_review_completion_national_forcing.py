#!/usr/bin/env python3
"""POWER forcing for metadata-fixed national source applications.

Reuse one native MERRA2 grid/solar-time cell rather than repeatedly requesting
nearby gauges. POWER's daily default is LST; make it explicit and match the
existing source product, without calling it UTC or a local weather station.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024/national_meaning"
DATA=T.ROOT/"data/external/wrr_review_national_20261024"
OLD=[T.ROOT/"data/external/wrr_target_recovery_20261021/power",T.ROOT/"data/external/wrr_target_recovery_20261022/usgs_new/power_raw"]
LOCK=threading.Lock();LAST_REQUEST=0.;NEXT_REQUEST=0.


def grid_key(latitude,longitude):
    return (int(math.floor((latitude+90)/.5+.5)),int(math.floor((longitude+180)/.625+.5))%576,
            int(math.floor((longitude+7.5)/15)))


def eligible_roster():
    roster=pd.read_csv(OUT/"candidate_roster.csv",dtype={"station_id":str,"series_id":str,"hydrologic_unit_code":str})
    rows=[]
    helper_sha=hashlib.sha256((T.ROOT/"src/stream_recoverability/experiments/tr_revision/national.py").read_bytes()).hexdigest()
    for row in roster.to_dict("records"):
        result_path=OUT/"site_results"/(row["station_id"]+".json")
        if not result_path.exists():continue
        result=json.loads(result_path.read_text())
        if result.get("status")!="processed" or result.get("helper_sha256")!=helper_sha:continue
        path=DATA/"annual"/(row["station_id"]+".parquet")
        if not path.exists():continue
        annual=pd.read_parquet(path)
        if annual.empty:continue
        usable=annual.qc_year&annual.n_usable.ge(30)
        if annual.complete.sum()>=4 and usable.sum()>=15 and (usable&~annual.complete).any():rows.append(row)
    return pd.DataFrame(rows,columns=roster.columns)


def parse(document):
    if document.get("header",{}).get("time_standard")!="LST":raise ValueError("Expected POWER daily LST product")
    if document.get("parameters",{}).get("T2M",{}).get("units")!="C":raise ValueError("Expected Celsius T2M")
    values=document["properties"]["parameter"]["T2M"]
    series=pd.Series(pd.to_numeric(pd.Series(values),errors="coerce").to_numpy(),index=pd.to_datetime(list(values),format="%Y%m%d"))
    return series.where(series>-998).loc["1981-01-01":"2025-12-31"]


def old_cells():
    cells={};comparisons=[]
    for folder in OLD:
        for path in sorted(folder.glob("*.json")):
            try:
                d=json.loads(path.read_text());lon,lat=d["geometry"]["coordinates"][:2]
                series=parse(d);key=grid_key(lat,lon)
                if key in cells:
                    previous=parse(json.loads(cells[key].read_text()));common=previous.index.intersection(series.index)
                    valid=previous.reindex(common).notna()&series.reindex(common).notna()
                    comparisons.append({"cell":str(key),"n_compared":int(valid.sum()),"maximum_difference":float((previous.reindex(common)[valid]-series.reindex(common)[valid]).abs().max()) if valid.any() else np.nan})
                else:cells[key]=path
            except (ValueError,KeyError,TypeError):continue
    return cells,comparisons


def slot():
    global LAST_REQUEST
    while True:
        with LOCK:
            delay=max(NEXT_REQUEST,LAST_REQUEST+3.)-time.time()
            if delay<=0:LAST_REQUEST=time.time();return
        time.sleep(min(delay,30.))


def fetch_cell(key,row,old):
    global NEXT_REQUEST
    path=DATA/"power"/('_'.join(map(str,key))+".json.gz")
    if path.exists():return parse(json.loads(gzip.decompress(path.read_bytes()))),str(path.relative_to(T.ROOT))
    if key in old:return parse(json.loads(old[key].read_text())),str(old[key].relative_to(T.ROOT))
    params={"parameters":"T2M","community":"AG","latitude":row["latitude"],"longitude":row["longitude"],
            "start":"19810101","end":"20251231","format":"JSON","time-standard":"LST"}
    for attempt in range(4):
        slot();r=requests.get("https://power.larc.nasa.gov/api/temporal/daily/point",params=params,timeout=180)
        if r.status_code==429:
            try:delay=int(r.headers.get("Retry-After","60"))
            except ValueError:delay=60
            with LOCK:NEXT_REQUEST=max(NEXT_REQUEST,time.time()+max(delay,1)+1)
            continue
        r.raise_for_status();d=r.json();series=parse(d)
        path.write_bytes(gzip.compress(r.content))
        T.write_json(path.with_suffix(".request.json"),{"url":r.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"grid_key":key,"river_temperature_requested":False})
        return series,str(path.relative_to(T.ROOT))
    raise RuntimeError("POWER quota remains unavailable; preserve the job for a later continuation")


def main():
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=2);p.add_argument("--cached-only",action="store_true");a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);(DATA/"power").mkdir(parents=True,exist_ok=True)
    roster=eligible_roster();old,comparison=old_cells()
    pd.DataFrame(comparison).to_csv(OUT/"power_grid_cache_comparison.csv",index=False)
    # The retained source temperatures can differ over time versions. Do not
    # claim identical old cache contents just because their geometry matches.
    T.write_json(OUT/"forcing_plan.json",{"provider":"NASA POWER daily T2M, MERRA2, explicit LST, 1981--2025",
        "native_resolution_degrees":[.5,.625],"routing":"one lowest-station-ID representative per native grid and 15-degree solar-time swath; existing source response has priority",
        "purpose":"fixed source input convention; no local weather-station upper benchmark or attribution to spatial resolution alone",
        "new_independent_NZ_values":False,"selection":"metadata-fixed USGS source roster with >=4 complete and >=15 QC/observation-supported years; no prediction-error selection"})
    grouped={}
    for row in roster.sort_values("station_id").to_dict("records"):
        if not np.isfinite(row["latitude"]+row["longitude"]):continue
        grouped.setdefault(grid_key(row["latitude"],row["longitude"]),[]).append(row)
    parts=[];log=[]
    def one(key,rows):
        path=DATA/"power"/('_'.join(map(str,key))+".json.gz")
        if a.cached_only and key not in old and not path.exists():return [],{"cell":str(key),"status":"not_requested_in_cache_only_pass"}
        try:
            series,source=fetch_cell(key,rows[0],old)
            frames=[pd.DataFrame({"date":series.index,"air_temperature_c":series.to_numpy(),"station_id":r["station_id"],"network_id":"national"}) for r in rows]
            return frames,{"cell":str(key),"status":"available","n_stations":len(rows),"source":source}
        except (requests.RequestException,ValueError,KeyError,RuntimeError) as error:
            return [],{"cell":str(key),"status":"unavailable","error":str(error),"n_stations":len(rows)}
    with ThreadPoolExecutor(max_workers=min(a.workers,5)) as pool:
        futures=[pool.submit(one,key,rows) for key,rows in grouped.items()]
        for future in as_completed(futures):
            frames,record=future.result();parts.extend(frames);log.append(record)
    frame=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame(columns=["date","air_temperature_c","station_id","network_id"])
    temporary=DATA/"air_forcing.parquet.tmp";frame.to_parquet(temporary,index=False);temporary.replace(DATA/"air_forcing.parquet")
    T.write_json(OUT/"forcing_status.json",{"eligible_targets":len(roster),"eligible_target_ids":sorted(roster.station_id.astype(str)),"native_cells":len(grouped),"n_stations_with_forcing":frame.station_id.nunique(),"jobs":log,"cached_only":a.cached_only})
    return 0


if __name__=="__main__":raise SystemExit(main())
