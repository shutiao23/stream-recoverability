#!/usr/bin/env python3
"""Acquire a registered Hilltop cohort and aggregate strict native daily means.

No --acquire: check the gate only. Every observation request, including resume,
requires the exact public registration archive and frozen acquisition plan.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import time
from urllib.parse import quote,urlencode

import pandas as pd
import requests
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.independent import require_acquisition_plan,sha256
from stream_recoverability.experiments.tr_revision.native_temperature import native_series,strict_daily_mean

STUDY=T.ROOT/"results/wrr_review_completion_20261024/independent_study"
ENDPOINT="https://hilltop.gw.govt.nz/Data.hts"
QC_SPEC={"accepted_quality_codes":[600],"daily_completeness":1.0,
         "cadence":"monthly timestamp mode up to 60 minutes, shorter tie, must divide 24 hours",
         "aggregation":"mean of a full regular native day; no interpolation or synthetic records",
         "native_clock":"NZST fixed UTC+12"}


def main():
    p=argparse.ArgumentParser();p.add_argument("--study",type=Path,default=STUDY);p.add_argument("--acquire",action="store_true");a=p.parse_args()
    status=json.loads((a.study/"public_registration_status.json").read_text())
    plan=require_acquisition_plan(a.study,status,runtime_root=T.ROOT,runtime_config=T.CONFIG)
    if plan.get("provider")!="greater_wellington" or plan.get("endpoint")!=ENDPOINT:
        raise RuntimeError("This adapter implements only the reviewed Greater Wellington endpoint")
    if plan.get("qc_specification")!=QC_SPEC:
        raise RuntimeError("This adapter requires the exact registered native-clock and strict QC specification")
    if not a.acquire:
        print("Registration and strict measurement plan verified; no observations requested.");return 0
    roster=pd.read_csv(a.study/plan["metadata_roster_file"],dtype={"station_id":str,"station_key":str,"independence_group":str})
    required={"site","station_id","station_key","independence_group","measurement","from","to"}
    if required-set(roster) or roster.empty:raise RuntimeError("Frozen acquisition roster is incomplete")
    receipt_path=a.study/"acquisition_receipt.json"
    receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else {
        "registration_id":status["registration_id"],"first_temperature_request_utc":None,
        "native_daily_qc_passed":False,"requests":[],"daily_files":[]}
    if receipt["registration_id"]!=status["registration_id"]:raise RuntimeError("An older cohort cannot be reopened as a new registration")
    directory=a.study/"acquired";directory.mkdir(exist_ok=True)

    def fetch(row,kind,start,end):
        key=f"{row.station_id}__{kind}__{start[:10]}__{end[:10]}"
        path=directory/(key+".xml.gz");provenance=path.with_suffix(".request.json")
        if path.exists():
            if not provenance.exists():raise RuntimeError("Cached observation lacks its original request receipt")
            record=json.loads(provenance.read_text())
            if record["registration_id"]!=status["registration_id"] or sha256(path)!=record["sha256"]:
                raise RuntimeError("Cached observation does not match the registered acquisition")
            return gzip.decompress(path.read_bytes())
        url=ENDPOINT+'?'+urlencode({"Service":"Hilltop","Request":"GetData","Site":row.site,
             "Measurement":row.measurement,"TSType":kind,"From":start,"To":end},quote_via=quote)
        stamp=datetime.now(timezone.utc).isoformat()
        if pd.Timestamp(stamp)<=pd.Timestamp(status["registered_utc"]):raise RuntimeError("Registration must precede observation request")
        if receipt["first_temperature_request_utc"] is None:
            receipt["first_temperature_request_utc"]=stamp;T.write_json(receipt_path,receipt)
            status["water_temperature_values_requested"]=True
            status["first_temperature_request_utc"]=stamp
            T.write_json(a.study/"public_registration_status.json",status)
        response=requests.get(url,timeout=180)
        response.raise_for_status()
        # Validate the schema before caching; a 200 HTML error is not a series.
        native_series(response.content,site=row.site,series_type=kind)
        path.write_bytes(gzip.compress(response.content))
        record={"registration_id":status["registration_id"],"requested_utc":stamp,"url":url,
                "sha256":sha256(path),"bytes":path.stat().st_size}
        T.write_json(provenance,record);receipt["requests"].append(record);T.write_json(receipt_path,receipt)
        time.sleep(.5)
        return response.content

    cutoff=pd.Timestamp(plan["observation_end_exclusive"])
    for _,row in roster.sort_values("station_key").iterrows():
        beginning=pd.Timestamp(row["from"])
        end=min(pd.Timestamp(row["to"]),cutoff)
        if end.tzinfo is not None:raise RuntimeError("Frozen roster ranges must use explicit native calendar strings without mixed offsets")
        quality=native_series(fetch(row,"StdQualSeries","1900-01-01T00:00:00",end.isoformat()),site=row.site,series_type="StdQualSeries")
        months=pd.date_range(beginning.to_period('M').start_time,end,freq='MS')
        chunks=[]
        for start in months:
            stop=min(start+pd.offsets.MonthBegin(1),end)
            if stop<=start:continue
            chunks.append(native_series(fetch(row,"StdSeries",start.isoformat(),stop.isoformat()),site=row.site,series_type="StdSeries"))
        if not chunks:continue
        raw=pd.concat(chunks).sort_index()
        # Month boundaries are returned by both adjacent closed API requests.
        # Identical duplicates collapse; conflicting duplicates stay unknown.
        raw=raw.groupby(level=0).agg(lambda s:s.iloc[0] if len(s.unique())==1 else float('nan'))
        daily=strict_daily_mean(raw,quality,start=beginning.normalize().isoformat(),end_exclusive=end.ceil('D').isoformat())
        path=directory/(str(row.station_id)+"__daily.csv")
        daily.to_csv(path,index=False)
        receipt["daily_files"]=[f for f in receipt["daily_files"] if f["station_key"]!=row.station_key]
        receipt["daily_files"].append({"station_key":row.station_key,"file":str(path.relative_to(a.study)),
            "sha256":sha256(path),"accepted_days":int(daily.complete_native_day.sum()),"n_days":len(daily)})
        T.write_json(receipt_path,receipt)
    receipt["native_daily_qc_passed"]=True
    receipt["qc_specification"]=QC_SPEC
    receipt["qc_interpretation"]="Fixed procedure applied, not all observations accepted and not proof of measurement-error-free water temperature"
    T.write_json(receipt_path,receipt)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
