#!/usr/bin/env python3
"""Registered native-day forcing and exact source-generator target cases."""
from __future__ import annotations
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ["TR_CONFIG"]=str(ROOT/"configs/wrr_target_recovery_20261022.json")
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
from datetime import datetime,timezone
import gzip
import json
import time
import numpy as np
import pandas as pd
import requests
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.independent import require_acquisition_plan,sha256
from stream_recoverability.experiments.tr_revision.native_temperature import NZST
from stream_recoverability.seeds import position_index

STUDY=ROOT/"results/wrr_review_completion_20261024/independent_study"
AIR_SPEC={"provider":"Open-Meteo ERA5-Land","model":"era5_land","variable":"hourly temperature_2m",
          "aggregation":"24 finite hourly temperatures per fixed NZST day; no interpolation"}


def native_air_daily(document):
    if document.get("hourly_units",{}).get("temperature_2m")!="°C":
        raise ValueError("Unexpected forcing units")
    hourly=document["hourly"]
    dates=pd.to_datetime(hourly["time"],utc=True).tz_convert(NZST).tz_localize(None)
    values=pd.to_numeric(pd.Series(hourly["temperature_2m"]),errors="coerce").to_numpy()
    series=pd.Series(values,index=dates)
    if series.index.has_duplicates:raise ValueError("Duplicate forcing hours")
    group=series.groupby(series.index.normalize())
    return group.mean().where(group.count().eq(24))


def weather_parameters(row,year,end_exclusive):
    end=min(pd.Timestamp(row["to"]),pd.Timestamp(end_exclusive))
    utc_end=end.tz_localize(NZST).tz_convert("UTC").normalize().tz_localize(None)
    return {"latitude":float(row.latitude),"longitude":float(row.longitude),
            "start_date":f"{year-1}-12-31","end_date":min(pd.Timestamp(f"{year}-12-31"),utc_end).date().isoformat(),
            "hourly":"temperature_2m","models":"era5_land","timezone":"UTC","temperature_unit":"celsius"}


def weather(study,roster,plan):
    if plan.get("air_forcing")!=AIR_SPEC:raise RuntimeError("Freeze the exact forcing product, clock and aggregation before values")
    folder=study/"acquired/air";folder.mkdir(parents=True,exist_ok=True)
    parts=[]
    for _,row in roster.iterrows():
        first=pd.Timestamp(row["from"]).year
        last=min(pd.Timestamp(row["to"]),pd.Timestamp(plan["observation_end_exclusive"])).year
        for year in range(first,last+1):
            path=folder/f"{row.station_id}__{year}.json.gz"
            provenance=path.with_suffix(".request.json")
            if path.exists():
                if not provenance.exists() or sha256(path)!=json.loads(provenance.read_text())["sha256"]:
                    raise RuntimeError("Forcing cache differs from its raw request")
                document=json.loads(gzip.decompress(path.read_bytes()))
            else:
                parameters=weather_parameters(row,year,plan["observation_end_exclusive"])
                response=requests.get("https://archive-api.open-meteo.com/v1/archive",params=parameters,timeout=180)
                response.raise_for_status();document=response.json()
                native_air_daily(document)
                path.write_bytes(gzip.compress(response.content))
                T.write_json(provenance,{"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"sha256":sha256(path),"river_temperature_requested":False})
                time.sleep(.5)
            daily=native_air_daily(document)
            daily=daily.loc[(daily.index.year==year)&(daily.index<pd.Timestamp(plan["observation_end_exclusive"]).normalize())]
            parts.append(pd.DataFrame({"date":daily.index,"air_temperature_c":daily.to_numpy(),
                                       "station_id":str(row.station_id),"network_id":str(row.network_id)}))
    result=pd.concat(parts,ignore_index=True)
    result.to_parquet(study/"acquired/air_forcing.parquet",index=False)


def worker(job,settings,generator,pool,resume):
    module=T.load_script("registered_independent_case_worker",ROOT/"scripts/431_tr_cases.py")
    return module.station_cases(job,settings,generator,pool,resume)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--study",type=Path,default=STUDY)
    parser.add_argument("--prepare-cases",action="store_true");parser.add_argument("--workers",type=int,default=8)
    parser.add_argument("--resume",action="store_true");args=parser.parse_args()
    status=json.loads((args.study/"public_registration_status.json").read_text())
    plan=require_acquisition_plan(args.study,status,runtime_root=ROOT,runtime_config=T.CONFIG)
    if not args.prepare_cases:
        print("Registered preparation gate passed; no observations opened.");return 0
    receipt_path=args.study/"acquisition_receipt.json"
    receipt=json.loads(receipt_path.read_text())
    if receipt.get("registration_id")!=status["registration_id"] or not receipt.get("native_daily_qc_passed"):
        raise RuntimeError("Registered native water acquisition and QC must finish first")
    if pd.Timestamp(receipt["first_temperature_request_utc"])<=pd.Timestamp(status["registered_utc"]):
        raise RuntimeError("Temperature was accessed before registration")
    for name,field in [("source_case_settings.json","source_case_settings_sha256"),("source_missingness_generator.json","source_generator_sha256")]:
        if sha256(args.study/name)!=plan.get(field):raise RuntimeError("Source generation inputs differ from the frozen plan")
    roster=pd.read_csv(args.study/plan["metadata_roster_file"],dtype={"station_id":str,"station_key":str,"network_id":str,"independence_group":str})
    if {"station_id","station_key","network_id","provider","independence_group","latitude","longitude"}-set(roster):
        raise RuntimeError("Incomplete registered station and network roster")
    weather(args.study,roster,plan)
    daily={}
    for item in receipt["daily_files"]:
        path=args.study/item["file"]
        if not path.resolve().is_relative_to(args.study.resolve()) or sha256(path)!=item["sha256"]:
            raise RuntimeError("Native-day QC output differs from the acquisition receipt")
        block=pd.read_csv(path,parse_dates=["date"]).set_index("date").water_c
        daily[item["station_key"]]=block
    panel_dir=args.study/"acquired/panels";panel_dir.mkdir(exist_ok=True)
    jobs=[]
    for network,block in roster.groupby("network_id"):
        panel=pd.concat([daily[row.station_key].rename(row.station_id) for row in block.itertuples(index=False)],axis=1)
        panel.index.name="date";path=panel_dir/(str(network)+".csv");panel.to_csv(path)
        for row in block.itertuples(index=False):
            jobs.append({"network_id":str(network),"station_id":str(row.station_id),"station_key":row.station_key,
                         "provider":row.provider,"independence_group":row.independence_group,"latitude":float(row.latitude),
                         "input_path":str(path),"air_input_path":str(args.study/"acquired/air_forcing.parquet"),
                         "statistic_class":"daily_mean","regulation_status":"unknown","region":"registered_greater_wellington","roster":"independent"})
    positions=position_index(f"{job['network_id']}|{job['station_id']}" for job in jobs)
    for job in jobs:job["station_index"]=positions[f"{job['network_id']}|{job['station_id']}"]
    settings=json.loads((args.study/"source_case_settings.json").read_text())
    settings["version"]="review_completion_registered_"+status["registration_id"]
    generator=json.loads((args.study/"source_missingness_generator.json").read_text())
    core=T.load_script("registered_independent_case_parent",ROOT/"scripts/431_tr_cases.py")
    pools=core.calendar_pool("independent",jobs)
    results=Parallel(n_jobs=args.workers)(delayed(worker)(job,settings,generator,core.pool_for(job,pools),args.resume) for job in jobs)
    parts=[pd.read_parquet(r["cache"]) for r in results if r.get("cache")]
    empty_columns=["station_key","independence_group","design_family","h30__policy","eval_truth_h30","peak_overlap"]
    cases=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame(columns=empty_columns)
    path=args.study/"acquired/registered_cases.parquet";cases.to_parquet(path,index=False)
    receipt["prepared_cases_sha256"]=sha256(path);receipt["source_generator_settings"]=settings
    receipt["station_qualification_and_outputs"]=results
    receipt["n_registered_stations"]=len(roster);receipt["n_cases"]=len(cases)
    T.write_json(receipt_path,receipt)
    print(f"Prepared {len(cases)} registered cases; local daily history fits follow the fixed recipe, with no annual-model or failure-score recalibration.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
