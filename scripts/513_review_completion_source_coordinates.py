#!/usr/bin/env python3
"""Recover missing French source coordinates from exact official station IDs.

Only metadata is read. The source case roster and fitted models are unchanged.
Fresh longitude/latitude fields must agree with the geographic Point geometry
and with the previously cached public station catalog.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024/inputs"


def main():
    source=T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet"
    cases=pd.read_parquet(source,columns=["provider","station_id"])
    required=set(cases.loc[cases.provider.eq("hubeau"),"station_id"].astype(str))
    folder=OUT/"hubeau_coordinate_metadata"
    folder.mkdir(parents=True,exist_ok=True)
    if not (folder/"stations.json").exists():
        params={"code_station":','.join(sorted(required)),"size":max(100,len(required)),"format":"json"}
        response=requests.get("https://hubeau.eaufrance.fr/api/v1/temperature/station",params=params,timeout=90)
        response.raise_for_status();document=response.json()
        T.write_json(folder/"stations.json",document)
        T.write_json(folder/"request.json",{"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"role":"station metadata only; no river temperature values requested"})
    document=json.loads((folder/"stations.json").read_text())
    request=json.loads((folder/"request.json").read_text())
    if document.get("next") or int(document["count"])!=len(required):raise RuntimeError("Incomplete exact-station metadata query")
    records=document["data"]
    if len(records)!=len(required) or {r["code_station"] for r in records}!=required:raise RuntimeError("Official station codes do not match the source roster")
    cached_path=T.ROOT/"results/framework/public_catalog/hubeau_all_stations.csv"
    cached=pd.read_csv(cached_path,dtype={"site_id":str}).set_index("site_id")
    if not cached.index.is_unique:raise RuntimeError("Ambiguous cached station identity")
    sha=hashlib.sha256((folder/"stations.json").read_bytes()).hexdigest()
    rows=[];differences=[]
    for item in sorted(records,key=lambda r:r["code_station"]):
        code=item["code_station"];latitude=float(item["latitude"]);longitude=float(item["longitude"])
        if not (-90<=latitude<=90 and -180<=longitude<=180):raise ValueError("Invalid geographic coordinate")
        geometry=item["geometry"]
        if geometry["type"]!="Point" or not geometry.get("crs",{}).get("properties",{}).get("name","").endswith("CRS84"):
            raise ValueError("Expected geographic CRS84 point; projected Lambert coordinates are not longitude/latitude")
        np.testing.assert_allclose(geometry["coordinates"],[longitude,latitude],rtol=0,atol=1e-7)
        previous=cached.loc[code,["latitude","longitude"]].to_numpy(float)
        np.testing.assert_allclose(previous,[latitude,longitude],rtol=0,atol=1e-9)
        differences.extend(np.abs(previous-[latitude,longitude]))
        rows.append({"provider":"hubeau","station_id":code,"station_key":"hubeau|"+code,"latitude":latitude,"longitude":longitude,
            "station_name":item["libelle_station"],"station_uri":item["uri_station"],"coordinate_source":"Hub'Eau official temperature station metadata, exact code_station",
            "metadata_sha256":sha,"metadata_request_url":request["url"]})
    frame=pd.DataFrame(rows)
    model=T.ROOT/"results/wrr_review_completion_20261024/deployment/global_source_candidate.joblib"
    model_sha=hashlib.sha256(model.read_bytes()).hexdigest() if model.exists() else None
    plan_paths=[OUT.parent/"national_meaning/plan.json",OUT.parent/"independent_study/acquisition_plan.json"]
    existing_plans=[p for p in plan_paths if p.exists()]
    if model_sha and any(json.loads(p.read_text())["source_model_sha256"]!=model_sha for p in existing_plans):
        raise RuntimeError("The frozen annual source model differs from its existing study plans")
    frame.to_csv(OUT/"source_coordinate_supplement.csv",index=False)
    T.write_json(OUT/"source_coordinate_supplement_audit.json",{"passed":True,"n_source_stations":len(frame),"provider":"hubeau",
        "join":"exact provider and original eight-character station code; no nearest-site or performance selection",
        "fresh_metadata":str((folder/"stations.json").relative_to(T.ROOT)),"fresh_metadata_sha256":sha,
        "cached_catalog":str(cached_path.relative_to(T.ROOT)),"cached_catalog_sha256":hashlib.sha256(cached_path.read_bytes()).hexdigest(),
        "maximum_catalog_coordinate_difference":float(max(differences)),"geographic_geometry_tolerance_degrees":1e-7,
        "frozen_source_model_sha256":model_sha,"matched_existing_plan_hashes":[str(p.relative_to(T.ROOT)) for p in existing_plans] if model_sha else [],
        "source_case_roster_changed":False,"source_model_changed":False,"river_temperature_values_requested":False})
    print(f"Verified exact official coordinates for {len(frame)} existing French source stations",flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
