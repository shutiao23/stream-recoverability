#!/usr/bin/env python3
"""Repeat masking for annual 7-day average DAILY MAXIMUM temperatures.

Only already-opened source station identifiers are requested. Daily maxima
are never substituted for daily means in the H30 analysis.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import json
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"daily_max"


def acquire(site):
    path=OUT/"raw"/f"{site}.rdb"
    params={"format":"rdb","sites":site,"parameterCd":"00010","statCd":"00001","startDT":"1980-01-01","endDT":"2025-12-31"}
    if not path.exists():
        try:
            response=requests.get("https://waterservices.usgs.gov/nwis/dv/",params=params,timeout=90)
            response.raise_for_status();path.write_text(response.text)
            T.write_json(path.with_suffix(".request.json"),{"url":response.url,"statistic":"00001 maximum","opened_station_only":True})
        except requests.RequestException as error:
            return site,None,str(error)
    lines=[line for line in path.read_text().splitlines() if line and not line.startswith("#")]
    if len(lines)<3:
        return site,None,"no published daily maxima"
    f=pd.read_csv(StringIO("\n".join([lines[0]]+lines[2:])),sep="\t",dtype=str)
    columns=[col for col in f if col.endswith("_00010_00001")]
    if not columns:
        return site,None,"no statistic 00001 channel"
    col=max(columns,key=lambda col:pd.to_numeric(f[col],errors="coerce").notna().sum())
    values=pd.to_numeric(f[col],errors="coerce")
    if col+"_cd" in f:
        values=values.where(f[col+"_cd"].fillna("").str.contains("A"))
    return site,pd.Series(values.to_numpy(),index=pd.to_datetime(f.datetime)),None


def main():
    (OUT/"raw").mkdir(parents=True,exist_ok=True)
    roster_path=OUT.parent/"inputs/forcing_roster.csv"
    if not roster_path.exists():
        raise RuntimeError("Run the prespecified opened-station forcing roster first")
    sites=pd.read_csv(roster_path,dtype={"site_no":str}).site_no.tolist()
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(acquire,sites))
    c=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet")
    rows=[];qualification=[]
    for site,series,error in records:
        if series is None:
            qualification.append({"station":site,"eligible":False,"reason":error});continue
        series=series.sort_index().groupby(level=0).mean().asfreq("D")
        water=series.to_numpy()
        complete=[int(y) for y,b in series.groupby(series.index.year) if len(b)>=365 and b.notna().all()]
        qualification.append({"station":site,"eligible":len(complete)>=4,"complete_years":len(complete),"reason":"" if len(complete)>=4 else "fewer than four complete daily-maximum years"})
        if len(complete)<4:
            continue
        station=f"usgs|{site}"
        forcing=daily.loc[daily.station_key.eq(station)].set_index("date").air_c
        x=pd.DataFrame({f"air_{lag}":forcing.shift(lag).reindex(series.index) for lag in [0,1,2,3,5,7,14]})
        x["sin"]=np.sin(2*np.pi*series.index.dayofyear/365.25);x["cos"]=np.cos(2*np.pi*series.index.dayofyear/365.25)
        for year in complete:
            held=series.index.year==year;train=~held&np.isfinite(water)&np.isfinite(x).all(axis=1).to_numpy()
            if train.sum()<365:
                continue
            mean=x.loc[train].mean();sd=x.loc[train].std().replace(0,1)
            z=(x-mean)/sd;model=Ridge(alpha=1).fit(z.loc[train],water[train])
            prediction=np.full(held.sum(),np.nan);good=np.isfinite(z.loc[held]).all(axis=1).to_numpy()
            if good.any():
                prediction[good]=model.predict(z.loc[held].iloc[np.flatnonzero(good)])
            truth=water[held];index=series.index[held]
            climate=series.loc[~held].groupby(series.index[~held].dayofyear).mean().reindex(range(1,367)).interpolate(limit_direction="both")
            climate=climate.reindex(index.dayofyear).to_numpy();peak=int(np.argmax(T.window_means(climate,7)))
            actual=float(T.window_means(truth,7).max())
            for _,r in c.loc[c.station_key.eq(station)&c.year.eq(year)].iterrows():
                mask=T.mask_from_runs(r.mask_runs,len(truth));completed=truth.copy();completed[mask]=prediction[mask]
                if not np.isfinite(completed).all():
                    continue
                estimate=float(T.window_means(completed,7).max());overlap=float(mask[peak:peak+7].mean())
                rows.append({"station":site,"year":year,"family":r.design_family,"realization_id":r.realization_id,"truth_7DADM":actual,"estimate":estimate,"error":estimate-actual,"decision_peak7_overlap":overlap,"admit_single_feature":overlap<.5,"admit_warm90":r.warm_observed_fraction>=.9})
    pd.DataFrame(qualification).to_csv(OUT/"qualification.csv",index=False)
    results=pd.DataFrame(rows);results.to_parquet(OUT/"cases.parquet",index=False)
    summaries=[]
    if len(results):
        for family,b in results.groupby("family"):
            for name,admit in [("all",np.ones(len(b),bool)),("one_feature_peak7",b.admit_single_feature),("warm90",b.admit_warm90)]:
                selected=b.loc[admit]
                summaries.append(dict(family=family,rule=name,n=len(selected),retention=len(selected)/len(b),bias=float(selected.error.mean()),mae=float(selected.error.abs().mean()),risk=float(selected.error.abs().gt(.5).mean())))
    pd.DataFrame(summaries).to_csv(OUT/"summary.csv",index=False)
    T.write_json(OUT/"status.json",{"selected_opened_stations":len(sites),"published_daily_max":sum(s is not None for _,s,_ in records),"qualified_stations":sum(q["eligible"] for q in qualification),"cases":len(rows),"metric":"annual maximum 7-day average of approved daily maxima (7DADM), degrees C","tolerance_c":.5,"evidence_role":"exploratory daily-max sensitivity on a prespecified limited roster, not a regulatory validation or national census"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
