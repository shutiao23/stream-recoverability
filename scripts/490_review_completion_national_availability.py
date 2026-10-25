#!/usr/bin/env python3
"""National USGS stream-temperature availability, without requesting values.

Use the existing nationwide metadata snapshot, select one primary daily-mean
series per stream site by metadata alone, and request dates/approval status.
This closes the national availability denominator, not national H30 trends.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import gzip
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs,urlencode,urlsplit,urlunsplit
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]/"national_availability"
CATALOG=T.ROOT/"data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json"
OLD=T.ROOT/"data/external/wrr_target_recovery_20261022/usgs_new/availability"
API="https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"
START,END=1981,2025
HALT=threading.Event()
REQUEST_LOCK=threading.Lock()
REQUEST_AFTER=0.
LAST_REQUEST=0.
WAIT_FOR_QUOTA=False
ZONES={"EST":"America/New_York","CST":"America/Chicago","MST":"America/Denver","PST":"America/Los_Angeles","AKST":"America/Anchorage","HST":"Pacific/Honolulu","AST":"America/Puerto_Rico","SST":"Pacific/Pago_Pago","GST":"Pacific/Guam","ChST":"Pacific/Guam"}
STANDARD={"EST":"Etc/GMT+5","CST":"Etc/GMT+6","MST":"Etc/GMT+7","PST":"Etc/GMT+8","AKST":"Etc/GMT+9","HST":"Etc/GMT+10"}


def native_zone(row):
    abbreviation=row.get("time_zone_abbreviation")
    return ZONES.get(abbreviation) if str(row.get("uses_daylight_savings")).upper()=="Y" else STANDARD.get(abbreviation,ZONES.get(abbreviation))


def roster():
    document=json.loads(CATALOG.read_text());rows=[]
    for feature in document["features"]:
        r=dict(feature["properties"])
        if r.get("agency_code")!="USGS" or not str(r.get("site_type_code","")).startswith("ST") or r.get("parameter_code")!="00010" or r.get("statistic_id")!="00003":continue
        if r.get("primary")!="Primary" or r.get("data_type")!="Daily values":continue
        coordinate=feature.get("geometry",{}).get("coordinates",[np.nan,np.nan]) if feature.get("geometry") else [np.nan,np.nan]
        r.update(series_id=r["id"],station_id=r["monitoring_location_number"],latitude=coordinate[1],longitude=coordinate[0])
        zone=native_zone(r);r["native_zone"]=zone
        if zone and r.get("begin") and r.get("end"):
            begin=pd.Timestamp(r["begin"]).tz_convert(zone).date();end=pd.Timestamp(r["end"]).tz_convert(zone).date()
            first=max(START,begin.year+int(begin>datetime(begin.year,1,1).date()))
            last=min(END,end.year-int(end<datetime(end.year,12,31).date()))
            r.update(first_full_year=first,last_full_year=last,maximum_full_years=max(0,last-first+1))
        else:r.update(first_full_year=np.nan,last_full_year=np.nan,maximum_full_years=np.nan)
        r["default_sublocation"]=r.get("sublocation_identifier") in [None,""]
        rows.append(r)
    frame=pd.DataFrame(rows)
    # One series per physical site; no union of overlapping sensors or approval
    # versions. The longest metadata-supported window wins, with an ID tie-break.
    frame=frame.sort_values(["station_id","maximum_full_years","default_sublocation","series_id"],ascending=[True,False,False,True])
    return frame.drop_duplicates("station_id").reset_index(drop=True)


def load_cache(row):
    own=OUT/"raw"/f"{row['series_id']}.json.gz";old=OLD/f"{row['series_id']}.json"
    for path in [own,old]:
        if path.exists():
            document=json.loads(gzip.open(path,"rt").read() if path.suffix==".gz" else path.read_text())
            features=document["features"]
            if any(set(item)-{"time","approval_status"} for item in features):
                raise RuntimeError("Availability cache unexpectedly contains fields beyond dates and approval")
            return features,str(path.relative_to(T.ROOT))
    return None,None


def request_slot():
    global LAST_REQUEST
    while True:
        with REQUEST_LOCK:
            delay=max(REQUEST_AFTER-time.monotonic(),LAST_REQUEST+1.1-time.monotonic())
            if delay<=0:
                LAST_REQUEST=time.monotonic();return
        time.sleep(min(delay,30.))


def save_checkpoint(path,document):
    temporary=path.with_suffix(path.suffix+".tmp")
    with gzip.open(temporary,"wt") as stream:json.dump(document,stream)
    temporary.replace(path)


def fetch_dates(row):
    global REQUEST_AFTER
    features,source=load_cache(row)
    if features is not None:return features,source,None
    if HALT.is_set():return None,None,"deferred_after_service_quota"
    params={"f":"json","time_series_id":row["series_id"],"properties":"time,approval_status","skipGeometry":"true","limit":10000,"datetime":f"{START}-01-01T00:00:00Z/{END+1}-01-02T00:00:00Z"}
    url=API+"?"+urlencode(params);pages=[];features=[]
    partial=OUT/"raw"/f"{row['series_id']}.partial.json.gz"
    if partial.exists():
        state=json.load(gzip.open(partial,"rt"));features=state["features"];pages=state["requests"];url=state["next_url"]
    while url:
        if HALT.is_set():return None,None,"deferred_after_service_quota"
        request_slot()
        headers={"User-Agent":"stream-recoverability national dates-only availability audit"}
        credential=next((os.environ.get(name) for name in ["USGS_WATERDATA_API_KEY","USGS_API_KEY"] if os.environ.get(name)),None)
        if credential:headers["X-Api-Key"]=credential
        response=requests.get(url,headers=headers,timeout=45)
        if response.status_code==429:
            raw=response.headers.get("Retry-After","60")
            try:delay=max(1,int(raw))
            except ValueError:delay=60
            with REQUEST_LOCK:
                REQUEST_AFTER=max(REQUEST_AFTER,time.monotonic()+delay+1)
                T.write_json(OUT/"quota_status.json",{"observed_utc":datetime.now(timezone.utc).isoformat(),"retry_after_seconds":delay,"rate_limit":response.headers.get("X-RateLimit-Limit"),"remaining":response.headers.get("X-RateLimit-Remaining"),"api_key_supplied":credential is not None,"temperature_values_requested":False})
            if WAIT_FOR_QUOTA:
                print(f"USGS dates-only service quota: waiting {delay+1}s before resuming the same page",flush=True)
                continue
            HALT.set();return None,None,"HTTP429 Retry-After="+raw
        response.raise_for_status();document=response.json();page=[]
        for item in document.get("features",[]):
            props=item.get("properties",{})
            if set(props)-{"time","approval_status"}:
                HALT.set()
                raise RuntimeError("Provider ignored dates-only projection; do not ingest or use this series for a blind outcome study")
            page.append({"time":props["time"],"approval_status":props.get("approval_status")})
        features.extend(page);pages.append(response.url)
        if len(page)<10000:break
        next_url=next((x["href"] for x in document.get("links",[]) if x.get("rel")=="next"),None)
        if not next_url:break
        parts=urlsplit(next_url);query=parse_qs(parts.query)
        query["properties"]=["time,approval_status"];query["skipGeometry"]=["true"]
        url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query,doseq=True),parts.fragment))
        if url in pages:raise RuntimeError("Repeated pagination link")
        save_checkpoint(partial,{"series_id":row["series_id"],"requests":pages,"features":features,"next_url":url,"temperature_values_requested":False})
    path=OUT/"raw"/f"{row['series_id']}.json.gz"
    save_checkpoint(path,{"series_id":row["series_id"],"requests":pages,"features":features,"temperature_values_requested":False,"retrieved_utc":datetime.now(timezone.utc).isoformat()})
    partial.unlink(missing_ok=True)
    return features,str(path.relative_to(T.ROOT)),None


def native_dates(values,zone):
    # The daily API normally returns an already native YYYY-MM-DD date. Such
    # dates must never be localized to UTC and shifted to the preceding day.
    if all(len(str(value))==10 for value in values):
        return pd.DatetimeIndex(pd.to_datetime(values,format="%Y-%m-%d"))
    result=[]
    for value in values:
        stamp=pd.Timestamp(value)
        if stamp.tzinfo is not None:stamp=stamp.tz_convert(zone).tz_localize(None)
        result.append(stamp.normalize())
    return pd.DatetimeIndex(result)


def calendar_counts(row,features):
    if not features:return []
    dates=native_dates([x["time"] for x in features],row["native_zone"])
    approved=np.array([str(x.get("approval_status","")).lower()=="approved" for x in features])
    all_dates=pd.DatetimeIndex(dates.unique());approved_dates=pd.DatetimeIndex(dates[approved].unique())
    rows=[]
    first,last=row["first_full_year"],row["last_full_year"]
    if not np.isfinite(first+last):
        begin,end=dates.min(),dates.max()
        first=max(START,begin.year+int(begin>pd.Timestamp(begin.year,1,1)))
        last=min(END,end.year-int(end<pd.Timestamp(end.year,12,31)))
    for year in range(int(first),int(last)+1):
        start,end=pd.Timestamp(year,1,1),pd.Timestamp(year,12,31);n_days=(end-start).days+1
        present=all_dates[(all_dates>=start)&(all_dates<=end)];valid=approved_dates[(approved_dates>=start)&(approved_dates<=end)]
        unapproved=present.difference(valid)
        rows.append(dict(station_id=row["station_id"],series_id=row["series_id"],year=year,n_days=n_days,n_reported_dates=len(present),n_approved_dates=len(valid),n_unapproved_dates=len(unapproved),n_actual_absent_dates=n_days-len(present),complete_approved=len(valid)==n_days,
                         annual90_approved=len(unapproved)==0 and len(valid)>=.9*n_days,annual75_approved=len(unapproved)==0 and len(valid)>=.75*n_days,
                         approved_observations_available=len(valid)>0 and len(unapproved)==0))
    return rows


def one(row):
    try:
        features,source,error=fetch_dates(row)
        if error:return {"station_id":row["station_id"],"series_id":row["series_id"],"status":error},[]
        if not features:return {"station_id":row["station_id"],"series_id":row["series_id"],"status":"no_date_records_returned; metadata_only_eligibility_unresolved"},[]
        years=calendar_counts(row,features)
        n_complete=sum(y["complete_approved"] for y in years)
        n_retained=sum(y["complete_approved"] or (y["approved_observations_available"] and n_complete>=4) for y in years)
        return dict(station_id=row["station_id"],series_id=row["series_id"],status="dates_and_approval_only",source=source,n_complete_years=n_complete,n_annual90_years=sum(y["annual90_approved"] for y in years),n_annual75_years=sum(y["annual75_approved"] for y in years),n_potential_retained_years=n_retained,
                    eligible_complete15=n_complete>=15,eligible_annual90_15=sum(y["annual90_approved"] for y in years)>=15,eligible_annual75_15=sum(y["annual75_approved"] for y in years)>=15,eligible_retain15=n_retained>=15),years
    except (requests.RequestException,ValueError,KeyError,RuntimeError) as error:
        return {"station_id":row["station_id"],"series_id":row["series_id"],"status":"unavailable:"+str(error)},[]


def main():
    global WAIT_FOR_QUOTA
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=2);p.add_argument("--max-sites",type=int);p.add_argument("--metadata-only",action="store_true");p.add_argument("--wait-for-quota",action="store_true");a=p.parse_args()
    WAIT_FOR_QUOTA=a.wait_for_quota
    (OUT/"raw").mkdir(parents=True,exist_ok=True)
    full=roster();full.to_csv(OUT/"national_stream_site_roster.csv",index=False)
    candidates=full.loc[full.maximum_full_years.ge(15)|full.maximum_full_years.isna()].copy()
    chosen=candidates if a.max_sites is None else candidates.head(a.max_sites)
    T.write_json(OUT/"design.json",{"population":"all primary USGS daily-mean water-temperature stream site types in existing national combined metadata snapshot; one metadata-selected series per site","metadata_snapshot":str(CATALOG.relative_to(T.ROOT)),"analysis_years":[START,END],"value_fields_requested":False,"native_dates":"date-only API fields already identify provider-native calendar days; timestamp fields use site zone; whole calendar years inside metadata series window","screen":"cannot reach 15 fully supported calendar years is a metadata exclusion; unknown spans queried and never silently excluded","unapproved":"observed provisional values are never recoded as true missing; any unapproved dates exclude that year from strict approved-data eligibility","retain_opportunity":">=4 approved date-complete historical years and >=15 supported years with some approved observation; conditional on future numeric QC and predictor availability","scientific_scope":"national availability census; no new water values, H30 trends or natural-gap validation"})
    if a.metadata_only:return 0
    results=[];calendars=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for i,(result,years) in enumerate(pool.map(one,chosen.to_dict("records")),1):
            results.append(result);calendars.extend(years)
            if i%25==0:
                print(f"national dates-only availability {i}/{len(chosen)}; fetched or cached {sum(x['status']=='dates_and_approval_only' for x in results)}",flush=True)
                T.write_json(OUT/"progress.json",{"updated_utc":datetime.now(timezone.utc).isoformat(),"processed_sites":i,"requested_sites":len(chosen),"date_calendars_resolved":sum(x['status']=='dates_and_approval_only' for x in results),"temperature_values_requested":False,"running_process_id":os.getpid()})
    station=pd.DataFrame(results);station.to_csv(OUT/"station_availability.csv",index=False);pd.DataFrame(calendars).to_parquet(OUT/"annual_availability.parquet",index=False)
    good=station.loc[station.status.eq("dates_and_approval_only")]
    counts={rule:int(good[rule].fillna(False).astype(bool).sum()) if rule in good else 0 for rule in ["eligible_complete15","eligible_annual90_15","eligible_annual75_15","eligible_retain15"]}
    T.write_json(OUT/"summary.json",{"national_stream_sites":len(full),"metadata_possible_15year_sites":len(candidates),"requested_sites":len(chosen),"availability_resolved_sites":len(good),"unresolved_sites":len(chosen)-len(good),"exclusion_short_metadata_span":int(full.maximum_full_years.lt(15).sum()),"unknown_metadata_span":int(full.maximum_full_years.isna().sum()),"eligibility_counts":counts,"temperature_values_requested":False,"all_metadata_possible_sites_resolved":len(chosen)==len(candidates) and len(good)==len(candidates),"actual_national_H30_trends_computed":False})
    print(json.dumps({"complete":len(good),"unresolved":len(chosen)-len(good),"eligible":counts}),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
