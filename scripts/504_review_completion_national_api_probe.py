#!/usr/bin/env python3
"""Check v0-empty series against the documented current v1 API.

This is transport/availability evidence, not selection by prediction errors.
Preserve both versions; never overwrite the v0 audit or call empty data proof
that a river was never observed. All requests concern the USGS source frame.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import requests
import pandas as pd
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024/national_meaning"
AVAIL=OUT.parent/"national_availability"


def main():
    p=argparse.ArgumentParser();p.add_argument("--max-series",type=int,default=4);p.add_argument("--positive-control",action="store_true");a=p.parse_args()
    controller=T.load_script("national_source_api_probe_quota",T.ROOT/"scripts/500_review_completion_national_inputs.py")
    roster=pd.read_csv(OUT/"candidate_roster.csv",dtype={"station_id":str,"series_id":str})
    rows=[]
    for path in sorted((AVAIL/"raw").glob("*.json.gz")):
        d=json.load(gzip.open(path,"rt"))
        if d["features"]:continue
        match=roster.loc[roster.series_id.eq(d["series_id"])]
        if len(match):rows.append(match.iloc[0].to_dict())
    rows=sorted(rows,key=lambda r:(pd.isna(r["maximum_full_years"]),r["station_id"]))[:a.max_series]
    if a.positive_control:
        for path in sorted((OUT/"site_results").glob("*.json")):
            saved=json.loads(path.read_text())
            if saved.get("status")=="processed" and saved.get("n_raw",0)>0:
                control=roster.loc[roster.station_id.eq(saved["station_id"])].iloc[0].to_dict()
                control["v0_known_positive_control"]=True;rows.insert(0,control);break
    folder=OUT/"api_version_probes";folder.mkdir(parents=True,exist_ok=True)
    previous=folder/"probe_summary.json"
    if previous.exists() and not (folder/"probe_direct_id_summary.json").exists():
        (folder/"probe_direct_id_summary.json").write_bytes(previous.read_bytes())
    results=[]
    for row in rows:
        urls={"metadata_by_site":"https://api.waterdata.usgs.gov/ogcapi/v1/collections/time-series-metadata/items",
              "one_daily_record":"https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items"}
        result={"station_id":row["station_id"],"series_id":row["series_id"],"v0_known_positive_control":row.get("v0_known_positive_control",False),"unknown_original_metadata_span":pd.isna(row["maximum_full_years"]),"requests":[]}
        for kind,url in urls.items():
            path=folder/(row["series_id"]+'_'+kind+'.json')
            if path.exists():document=json.loads(path.read_text())
            else:
                controller.request_slot()
                params=({"f":"json","time_series_id":row["series_id"],"limit":1,
                         "properties":"time,time_series_id,value,approval_status,qualifier",
                         "datetime":"1980-01-01T00:00:00Z/2026-01-02T00:00:00Z"} if kind=="one_daily_record" else
                        {"f":"json","monitoring_location_id":"USGS-"+row["station_id"],"parameter_code":"00010","limit":1000,"skipGeometry":"true"})
                response=requests.get(url,params=params,timeout=90)
                result["requests"].append({"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"http_status":response.status_code})
                if response.status_code==429:
                    try:delay=int(response.headers.get("Retry-After","60"))
                    except ValueError:delay=60
                    T.write_json(OUT/"quota_status.json",{"observed_utc":datetime.now(timezone.utc).isoformat(),"retry_after_seconds":max(1,delay),"rate_limit":response.headers.get("X-RateLimit-Limit"),"remaining":response.headers.get("X-RateLimit-Remaining"),"api_key_supplied":False})
                    result["status"]="deferred_after_service_quota";break
                if not response.ok:
                    result["status"]="unavailable_http_"+str(response.status_code);result["error"]=response.text[:300];break
                document=response.json();T.write_json(path,document)
            if kind=="metadata_by_site":
                features=document.get("features",[])
                for feature in features:
                    props=feature.get("properties",{})
                    if props.get("monitoring_location_id")!="USGS-"+row["station_id"]:
                        raise RuntimeError("V1 metadata lookup ignored station identity")
                result["v1_metadata_candidates"]=[f.get("properties",{}) for f in features]
            else:
                features=document.get("features",[])
                if features:
                    props=features[0].get("properties",{})
                    if str(props.get("time_series_id","")).replace("-","")!=row["series_id"].replace("-",""):
                        raise RuntimeError("V1 probe did not identify the requested time series")
                    result["v1_has_record"]=True;result["v1_property_names"]=sorted(props)
                else:result["v1_has_record"]=False
                result["status"]="probed"
        results.append(result)
        T.write_json(folder/"probe_summary.json",{"results":results,"new_NZ_values_requested":False,"role":"USGS source API availability comparison; empty responses are not invented historical absence"})
        if result.get("status","").startswith("deferred") or result.get("status")=="unavailable_http_400":break
    return 0


if __name__=="__main__":raise SystemExit(main())
