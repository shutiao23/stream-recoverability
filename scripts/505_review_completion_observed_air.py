#!/usr/bin/env python3
"""Nearby observed-air sensitivity on the prespecified opened USGS sites.

Select the nearest TAVG station using coordinates and inventory span alone.
GHCN source S reports UTC-ending days; other source conventions vary. This is
an observational sensitivity, not a perfect riverbank-air oracle or a pure
test of spatial resolution.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.observed_air import parse_tavg,distance_km
from stream_recoverability.experiments.v17_fitness.estimators import StationModels

OUT=T.ROOT/"results/wrr_review_completion_20261024/inputs/observed_air"
META=OUT.parent/"noaa_metadata"
BASE="https://www.ncei.noaa.gov/pub/data/ghcn/daily/"


def download(url,path):
    if path.exists():return
    response=requests.get(url,timeout=180);response.raise_for_status();path.write_bytes(response.content)
    T.write_json(path.with_suffix(path.suffix+".request.json"),{"url":url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),
        "last_modified":response.headers.get("Last-Modified"),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"river_temperature_requested":False})


def metadata(all_source=False):
    OUT.mkdir(parents=True,exist_ok=True);META.mkdir(parents=True,exist_ok=True)
    for name in ["readme.txt","ghcnd-stations.txt","ghcnd-inventory.txt"]:download(BASE+name,META/name)
    sites=pd.read_csv(T.E1/"usgs_site_metadata.csv" if all_source else OUT.parent/"forcing_roster.csv",dtype={"site_no":str})
    if all_source:
        cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet",columns=["provider","station_id"])
        sites=sites.loc[sites.site_no.isin(cases.loc[cases.provider.eq("usgs"),"station_id"].unique())].sort_values("site_no")
    stations=pd.read_fwf(META/"ghcnd-stations.txt",colspecs=[(0,11),(12,20),(21,30),(31,37),(41,71)],names=["met_station","latitude","longitude","elevation_m","name"],dtype={"met_station":str})
    inventory=pd.read_fwf(META/"ghcnd-inventory.txt",colspecs=[(0,11),(31,35),(36,40),(41,45)],names=["met_station","element","first_year","last_year"],dtype={"met_station":str})
    inventory=inventory.loc[inventory.element.eq("TAVG")].copy()
    inventory["overlap_span"]=np.minimum(inventory.last_year,2025)-np.maximum(inventory.first_year,1981)+1
    eligible=stations.merge(inventory.loc[inventory.overlap_span.ge(15)],on="met_station",validate="one_to_one")
    rows=[]
    for site in sites.itertuples(index=False):
        near=eligible.loc[eligible.latitude.sub(site.dec_lat_va).abs().le(.3)&eligible.longitude.sub(site.dec_long_va).abs().le(2)].copy()
        near["distance_km"]=[distance_km(site.dec_lat_va,site.dec_long_va,r.latitude,r.longitude) for r in near.itertuples(index=False)]
        near=near.loc[near.distance_km.le(25)].sort_values(["distance_km","met_station"])
        if near.empty:rows.append({"site_no":site.site_no,"status":"no_metadata_eligible_TAVG_station_within25km"})
        else:
            met=near.iloc[0]
            rows.append({"site_no":site.site_no,"status":"selected_by_metadata","met_station":met.met_station,
                "distance_km":float(met.distance_km),"met_latitude":float(met.latitude),"met_longitude":float(met.longitude),
                "met_elevation_m":float(met.elevation_m),"name":met['name'],"first_year":int(met.first_year),"last_year":int(met.last_year)})
    frame=pd.DataFrame(rows);frame.to_csv(OUT/"metadata_roster.csv",index=False)
    T.write_json(OUT/"design.json",{"population":"all opened source USGS sites" if all_source else "same35 prespecified opened USGS source sites as the Daymet/flow ablation","n_target_sites":len(sites),
        "selection":"nearest GHCN TAVG station within25km with at least15 metadata-overlap years in1981--2025; no water-error ranking, no second-station substitution after scoring",
        "quality":"TAVG tenths Celsius divided by10; -9999 missing; nonblank QFLAG excluded; contradictory dates unavailable",
        "time_convention":"provider-reported daily dates; source S is a24-hour average ending2400UTC, other sources vary. No invented UTC-to-local shift. Time aggregation and point/product changes are confounded.",
        "scope":"nearby observational sensitivity, not a perfect co-located riverbank-air upper bound or an independent river-temperature test",
        "new_NZ_temperature_requested":False})
    return frame


def run(frame,exact_source=False):
    folder=OUT/"raw";folder.mkdir(exist_ok=True)
    records=[];series={}
    for station in sorted(frame.met_station.dropna().unique()):
        path=folder/(station+".dly")
        try:
            for previous in ["observed_air_full_source","observed_air"]:
                original=OUT.parent/previous/"raw"/(station+".dly")
                if not path.exists() and original.exists():
                    shutil.copy2(original,path)
                    source_request=original.with_suffix(".dly.request.json")
                    if source_request.exists():shutil.copy2(source_request,path.with_suffix(".dly.request.json"))
            download(BASE+"all/"+station+".dly",path)
            values=parse_tavg(path.read_text())
            series[station]=values.set_index("date").air_c
            records.append({"met_station":station,"status":"available","n_qualified_days":int(values.air_c.notna().sum()),
                            "source_flags":values.source_flag.value_counts().to_dict(),"n_source_S_UTC_ending_days":int(values.source_flag.eq("S").sum())})
        except (requests.RequestException,ValueError) as error:records.append({"met_station":station,"status":"unavailable","error":str(error)})
    T.write_json(OUT/"acquisition.json",{"selected_stations":int(frame.met_station.nunique()),"retrieved_stations":len(series),"records":records,"river_temperature_requested":False})
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet")
    cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    helper=T.load_script("observed_air_matching_source_design",T.ROOT/"scripts/469_review_completion_inputs.py")
    source_recipe=T.load_script("observed_air_original_source_inputs",T.ROOT/"scripts/431_tr_cases.py") if exact_source else None
    source_jobs={(j["network_id"],j["station_id"]):j for j in source_recipe.jobs_for("source")} if exact_source else {}
    rows=[];daily_pairs=[]
    studies=[]
    for site in frame.itertuples(index=False):
        networks=cases.loc[cases.station_key.eq("usgs|"+site.site_no),"network_id"].unique() if exact_source else [None]
        studies.extend({**site._asdict(),"source_network":network} for network in networks)
    for site in pd.DataFrame(studies).itertuples(index=False):
        station="usgs|"+site.site_no
        cohort=cases.loc[cases.station_key.eq(station)&cases.year.between(1981,2025)]
        if exact_source:cohort=cohort.loc[cohort.network_id.eq(site.source_network)]
        shift=0
        if exact_source:
            if cohort.network_id.nunique()!=1:raise RuntimeError("Multiple source networks require an explicit station/input identity")
            source_job=source_jobs[(cohort.network_id.iloc[0],site.site_no)]
            panel=source_recipe.read_temperature_panel(source_job["input_path"]);panel.columns=panel.columns.astype(str);panel=panel.asfreq("D")
            air=source_recipe.station_air_series(Path(source_job["air_input_path"]),source_job["network_id"],site.site_no,panel.index)
            d=pd.DataFrame({"water_c":panel[site.site_no],"air_c":air if air is not None else np.nan},index=panel.index)
            shift=T.hemisphere_shift_days(source_job.get("latitude"))
            if shift:d.index=d.index+pd.Timedelta(days=shift)
        else:d=daily.loc[daily.station_key.eq(station)].sort_values("date").set_index("date").asfreq("D")
        observation=series.get(site.met_station)
        if shift and observation is not None:
            observation=observation.copy();observation.index+=pd.Timedelta(days=shift)
        for year,block in cohort.groupby("year"):
            held=d.index.year==year
            predictions={}
            for arm,air in [("POWER",d.air_c),("observed_TAVG",observation)]:
                x=helper.design(air.reindex(d.index),d.index) if air is not None else pd.DataFrame(index=d.index)
                train=(~held)&d.water_c.notna().to_numpy()&np.isfinite(x).all(axis=1).to_numpy() if len(x.columns) else np.zeros(len(d),bool)
                prediction=np.full(held.sum(),np.nan)
                if exact_source and air is not None:
                    local=StationModels(target=d.water_c,donors=pd.DataFrame(index=d.index),air=air.reindex(d.index),train_mask=pd.Series(~held,index=d.index))
                    prediction=local.air_predict(d.index[held])
                elif train.sum()>=365:
                    mean=x.loc[train].mean();sd=x.loc[train].std().replace(0,1);z=(x-mean)/sd
                    model=Ridge(alpha=1).fit(z.loc[train],d.loc[train,"water_c"])
                    good=np.isfinite(z.loc[held]).all(axis=1).to_numpy()
                    if good.any():prediction[good]=model.predict(z.loc[held].iloc[np.flatnonzero(good)])
                truth=d.loc[held,"water_c"].to_numpy()
                predictions[arm]=prediction.copy()
                for _,r in block.iterrows():
                    mask=T.mask_from_runs(r.mask_runs,len(truth));completed=truth.copy();completed[mask]=prediction[mask]
                    valid=np.isfinite(completed).all();estimate=float(T.window_means(completed,30).max()) if valid else np.nan
                    rows.append({**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},
                        "arm":arm,"available":bool(valid),"truth":r.eval_truth_h30,"point":estimate,"error":estimate-r.eval_truth_h30,
                        "met_station":site.met_station,"distance_km":site.distance_km,"n_daily_training_observations":int(train.sum()),
                        "hidden_daily_mae":float(np.mean(np.abs(prediction[mask]-truth[mask]))) if valid else np.nan,
                        "held_year_daily_r2":float(1-np.sum((prediction[np.isfinite(prediction)]-truth[np.isfinite(prediction)])**2)/np.sum((truth[np.isfinite(prediction)]-truth[np.isfinite(prediction)].mean())**2)) if np.isfinite(prediction).sum()>=30 and np.std(truth[np.isfinite(prediction)])>0 else np.nan})
            common=np.isfinite(truth)&np.isfinite(predictions["POWER"])&np.isfinite(predictions["observed_TAVG"])
            record={"station_key":station,"network_id":site.source_network,"year":int(year),"n_common_days":int(common.sum())}
            for arm in ["POWER","observed_TAVG"]:
                record[arm+"_daily_mae"]=float(np.mean(np.abs(predictions[arm][common]-truth[common]))) if common.any() else np.nan
                record[arm+"_daily_r2"]=float(1-np.sum((predictions[arm][common]-truth[common])**2)/np.sum((truth[common]-truth[common].mean())**2)) if common.sum()>=30 and np.std(truth[common])>0 else np.nan
            daily_pairs.append(record)
    result=pd.DataFrame(rows);result.to_parquet(OUT/"cases.parquet",index=False)
    keys=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]
    if exact_source:
        control=result.loc[result.arm.eq("POWER")].merge(cases[keys+["h30__air_ridge"]],on=keys,validate="one_to_one")
        common=control.point.notna()&control.h30__air_ridge.notna()
        audit={"case_rows":len(control),"n_both_available":int(common.sum()),"availability_disagreements":int((control.point.notna()!=control.h30__air_ridge.notna()).sum()),
               "maximum_point_difference":float((control.point-control.h30__air_ridge).abs()[common].max()),"input_identity":"network and station-specific original water panel/forcing; full precision and original input window"}
        audit["exact_source_verified"]=audit["availability_disagreements"]==0 and audit["maximum_point_difference"]<1e-9
        T.write_json(OUT/"original_core_control_audit.json",audit)
        if not audit["exact_source_verified"]:raise RuntimeError("Observed-air source control does not reproduce the original completion")
    wide=result.pivot(index=keys,columns="arm",values="error").reset_index();summary=[]
    daily_wide=result.pivot(index=keys,columns="arm",values="hidden_daily_mae").reset_index().rename(columns={"POWER":"POWER_hidden_daily_mae","observed_TAVG":"observed_hidden_daily_mae"})
    wide=wide.merge(daily_wide,on=keys,validate="one_to_one")
    for name,chosen in [("all",np.ones(len(wide),bool)),("danger",wide.peak_overlap.ge(.5)),("air_layer_danger",wide.peak_overlap.ge(.5)&wide.policy_choice.eq("air_ridge"))]:
        eligible=wide.loc[chosen];paired=eligible.dropna(subset=["POWER","observed_TAVG"])
        station_difference=paired.assign(difference=paired.observed_TAVG.abs()-paired.POWER.abs()).groupby("station_key").difference.mean()
        summary.append({"stratum":name,"n_eligible":len(eligible),"n_paired":len(paired),"n_paired_stations":paired.station_key.nunique(),"POWER_mae":float(paired.POWER.abs().mean()),
                        "observed_TAVG_mae":float(paired.observed_TAVG.abs().mean()),"POWER_bias":float(paired.POWER.mean()),"observed_TAVG_bias":float(paired.observed_TAVG.mean()),
                        "POWER_hidden_daily_mae":float(paired.POWER_hidden_daily_mae.mean()),"observed_hidden_daily_mae":float(paired.observed_hidden_daily_mae.mean()),
                        "median_station_mae_difference":float(station_difference.median()),"fraction_stations_observed_no_worse":float(station_difference.le(0).mean())})
    pd.DataFrame(summary).to_csv(OUT/"paired_summary.csv",index=False)
    pd.DataFrame(daily_pairs).to_csv(OUT/"paired_daily_station_years.csv",index=False)
    return 0


def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument("--metadata-only",action="store_true");p.add_argument("--all-source",action="store_true");p.add_argument("--exact-source-ridge",action="store_true");a=p.parse_args()
    if a.all_source:OUT=OUT.parent/"observed_air_full_source"
    if a.exact_source_ridge:OUT=OUT.with_name(OUT.name+"_exact")
    frame=metadata(a.all_source)
    design=json.loads((OUT/"design.json").read_text());design["daily_model"]="exact source StationModels.air_ridge: unstandardized Ridge alpha1, original minimum training rows and same lags/harmonics" if a.exact_source_ridge else "matched standardized Ridge alpha1 sensitivity"
    T.write_json(OUT/"design.json",design)
    return 0 if a.metadata_only else run(frame,a.exact_source_ridge)


if __name__=="__main__":raise SystemExit(main())
