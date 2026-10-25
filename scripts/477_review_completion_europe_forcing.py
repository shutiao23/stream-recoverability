#!/usr/bin/env python3
"""ERA5-Land/POWER matched sensitivity at opened European source stations."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"europe_forcing"


def fetch(row):
    path=OUT/"raw"/f"{row.provider}__{row.station_id}.json"
    params={"latitude":float(row.latitude),"longitude":float(row.longitude),"start_date":"1980-01-01","end_date":"2025-12-31","daily":"temperature_2m_mean","models":"era5_land","timezone":"UTC"}
    try:
        if not path.exists():
            response=requests.get("https://archive-api.open-meteo.com/v1/archive",params=params,timeout=90)
            response.raise_for_status()
            document=response.json()
            if "daily" not in document:
                raise ValueError("No daily meteorology returned")
            path.write_text(response.text)
            T.write_json(path.with_suffix(".request.json"),{"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"data_role":"meteorological covariate at an opened station","water_temperature_values":False})
        document=json.loads(path.read_text())
        return f"{row.provider}|{row.station_id}",pd.Series(document["daily"]["temperature_2m_mean"],index=pd.to_datetime(document["daily"]["time"])),None
    except (requests.RequestException,ValueError,KeyError) as error:
        return f"{row.provider}|{row.station_id}",None,str(error)


def main():
    (OUT/"raw").mkdir(parents=True,exist_ok=True)
    c=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    coordinates=pd.read_csv(T.ROOT/"data/interim/v18_station_coordinates.csv",dtype={"station_id":str})
    coordinates["station_key"]=coordinates.provider+"|"+coordinates.station_id
    roster=coordinates.loc[coordinates.station_key.isin(c.station_key)&coordinates.provider.ne("usgs")].drop_duplicates("station_key").sort_values(["provider","station_id"]).groupby("provider",group_keys=False).head(2)
    roster.to_csv(OUT/"roster.csv",index=False)
    # Three requests at a time; report access or quota failure without evasion.
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(fetch,roster.itertuples(index=False)))
    errors=[{"station":key,"error":error} for key,series,error in results if series is None]
    T.write_json(OUT/"acquisition.json",{"selected":len(roster),"retrieved":sum(series is not None for _,series,_ in results),"errors":errors,"model":"ERA5-Land via Open-Meteo, daily mean 2m air temperature, UTC","selection":"two opened stations per European provider sorted by identifier; no performance-based selection","local_meteorological_station_upper_bound":"not available; reanalysis is not a station observation"})
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet")
    helper=T.load_script("r4_europe_design",T.ROOT/"scripts/469_review_completion_inputs.py")
    rows=[]
    for station,highres,error in results:
        if highres is None:
            continue
        d=daily.loc[daily.station_key.eq(station)].sort_values("date").set_index("date").asfreq("D")
        candidates=c.loc[c.station_key.eq(station)&c.year.between(1981,2025)]
        for year,b in candidates.groupby("year"):
            held=d.index.year==year
            for arm,air in [("POWER",d.air_c),("ERA5_Land",highres)]:
                x=helper.design(air,d.index)
                train=~held&d.water_c.notna().to_numpy()&np.isfinite(x).all(axis=1).to_numpy()
                if train.sum()<365:
                    continue
                mu=x.loc[train].mean();sd=x.loc[train].std().replace(0,1);z=(x-mu)/sd
                model=Ridge(alpha=1).fit(z.loc[train],d.loc[train,"water_c"])
                prediction=np.full(held.sum(),np.nan);good=np.isfinite(z.loc[held]).all(axis=1).to_numpy()
                if good.any():
                    prediction[good]=model.predict(z.loc[held].iloc[np.flatnonzero(good)])
                truth=d.loc[held,"water_c"].to_numpy()
                for _,r in b.iterrows():
                    mask=T.mask_from_runs(r.mask_runs,len(truth));completed=truth.copy();completed[mask]=prediction[mask]
                    valid=np.isfinite(completed).all()
                    value=float(T.window_means(completed,30).max()) if valid else np.nan
                    rows.append({**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},"arm":arm,"available":bool(valid),"point":value,"error":value-r.eval_truth_h30})
    frame=pd.DataFrame(rows);frame.to_parquet(OUT/"cases.parquet",index=False)
    if len(frame):
        wide=frame.loc[frame.available].pivot(index=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"],columns="arm",values="error").dropna()
        summaries=[]
        for stratum,keep in [("all",np.ones(len(wide),bool)),("danger",wide.index.get_level_values("peak_overlap")>=.5),("air_layer_danger",(wide.index.get_level_values("peak_overlap")>=.5)&(wide.index.get_level_values("policy_choice")=="air_ridge"))]:
            b=wide.loc[keep]
            summaries.append(dict(stratum=stratum,n=len(b),POWER_mae=float(b.POWER.abs().mean()),ERA5_Land_mae=float(b.ERA5_Land.abs().mean()),paired_mae_change=float((b.ERA5_Land.abs()-b.POWER.abs()).mean())))
        pd.DataFrame(summaries).to_csv(OUT/"paired_summary.csv",index=False)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
