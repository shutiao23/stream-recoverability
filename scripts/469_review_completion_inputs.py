#!/usr/bin/env python3
"""Opened-station forcing/discharge ablation and reference-sensor qualification.

Requests here concern covariates or already-opened stations only. No proposed
independent-test water temperature is requested before public registration.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
from io import StringIO
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.statistics import removal_count

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"inputs"


def daymet(site,folder):
    cache=folder/f"{site.site_no}.csv"
    url="https://daymet.ornl.gov/single-pixel/api/data"
    params={"lat":float(site.dec_lat_va),"lon":float(site.dec_long_va),"vars":"tmin,tmax","start":"1980-01-01","end":"2025-12-31","format":"csv"}
    if not cache.exists():
        try:
            response=requests.get(url,params=params,timeout=120)
            response.raise_for_status()
            cache.write_text(response.text)
            T.write_json(cache.with_suffix(".request.json"),{"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"data_role":"forcing at opened station, not independent outcomes"})
        except requests.RequestException as e:
            return str(site.site_no),None,str(e)
    text=cache.read_text();lines=text.splitlines()
    header=next((i for i,line in enumerate(lines) if line.startswith("year,yday")),None)
    if header is None:
        return str(site.site_no),None,"no Daymet CSV header"
    f=pd.read_csv(StringIO("\n".join(lines[header:])))
    tmin=next(col for col in f if col.startswith("tmin"));tmax=next(col for col in f if col.startswith("tmax"))
    date=pd.to_datetime(f.year.astype(str))+pd.to_timedelta(f.yday-1,unit="D")
    # Daymet omits Dec 31 in leap years; retain missing rather than invent a day.
    return str(site.site_no),pd.Series((f[tmin].to_numpy()+f[tmax].to_numpy())/2,index=date),None


def design(air,index,flow=None):
    air=air.sort_index().asfreq("D")
    if flow is not None:flow=flow.sort_index().asfreq("D")
    frame=pd.DataFrame(index=index)
    for lag in [0,1,2,3,5,7,14]:
        frame[f"air_{lag}"]=air.shift(lag).reindex(index)
    d=index.dayofyear.to_numpy()
    frame["sin"]=np.sin(2*np.pi*d/365.25);frame["cos"]=np.cos(2*np.pi*d/365.25)
    if flow is not None:
        for lag in [0,1,3,7]:
            frame[f"log_flow_{lag}"]=np.log1p(flow.clip(lower=0)).shift(lag).reindex(index)
    return frame


def ablation(max_per_huc=2):
    OUT.mkdir(parents=True,exist_ok=True)
    folder=OUT/"daymet_raw";folder.mkdir(exist_ok=True)
    c=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    sites=pd.read_csv(T.E1/"usgs_site_metadata.csv",dtype={"site_no":str,"huc2":str})
    sites=sites.loc[sites.site_no.isin(c.loc[c.provider.eq("usgs"),"station_id"].unique())].sort_values(["huc2","site_no"]).groupby("huc2",group_keys=False).head(max_per_huc)
    sites.to_csv(OUT/"forcing_roster.csv",index=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda site:daymet(site,folder),sites.itertuples(index=False)))
    highres={site:series for site,series,error in responses if series is not None}
    T.write_json(OUT/"forcing_acquisition.json",{"selected_stations":len(sites),"downloaded":len(highres),"failures":[{"station":site,"reason":error} for site,_,error in responses if error],"selection":"first two opened source stations per HUC2 sorted by site number, without performance selection","product":"Daymet tmin/tmax midpoint; not a daily mean, product and temporal-aggregation changes are confounded"})
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet")
    flow=pd.read_parquet(T.E1/"usgs_flow.parquet")
    rows=[]
    for site in sites.site_no:
        station=f"usgs|{site}"
        d=daily.loc[daily.station_key.eq(station)].sort_values("date").set_index("date").asfreq("D")
        if d.empty:
            continue
        f=flow.loc[flow.site.eq(site)].set_index("date").flow_cms
        if f.index.duplicated().any():
            f=f.groupby(level=0).mean()
        candidates=c.loc[c.station_key.eq(station)&c.year.between(1981,2025)]
        for year,b in candidates.groupby("year"):
            held=d.index.year==year
            for arm,air,fl in [("POWER",d.air_c,None),("POWER_flow",d.air_c,f if len(f) else None),("Daymet",highres.get(site),None)]:
                if air is None or arm=="POWER_flow" and not len(f):
                    rows.extend({**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},
                        "arm":arm,"available":False,"reason":"forcing_or_discharge_unavailable","truth":r.eval_truth_h30,"point":np.nan,"error":np.nan,"daily_mae":np.nan} for _,r in b.iterrows())
                    continue
                x=design(air,d.index,fl)
                train=~held&d.water_c.notna().to_numpy()&np.isfinite(x).all(axis=1).to_numpy()
                if train.sum()<365:
                    rows.extend({**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},
                        "arm":arm,"available":False,"reason":"insufficient_training_inputs","truth":r.eval_truth_h30,"point":np.nan,"error":np.nan,"daily_mae":np.nan} for _,r in b.iterrows())
                    continue
                mean=x.loc[train].mean();sd=x.loc[train].std().replace(0,1)
                z=(x-mean)/sd
                model=Ridge(alpha=1).fit(z.loc[train],d.loc[train,"water_c"])
                prediction=np.full(held.sum(),np.nan)
                good=np.isfinite(z.loc[held]).all(axis=1).to_numpy()
                if good.any():
                    prediction[good]=model.predict(z.loc[held].iloc[np.flatnonzero(good)])
                truth=d.loc[held,"water_c"].to_numpy()
                for _,r in b.iterrows():
                    mask=T.mask_from_runs(r.mask_runs,len(truth))
                    completed=truth.copy();completed[mask]=prediction[mask]
                    valid=np.isfinite(completed).all()
                    estimate=float(T.window_means(completed,30).max()) if valid else np.nan
                    rows.append({**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},"arm":arm,"available":bool(valid),"truth":r.eval_truth_h30,"point":estimate,"error":estimate-r.eval_truth_h30,"daily_mae":float(np.mean(np.abs(prediction[mask]-truth[mask]))) if valid else np.nan})
        print(f"forcing ablation {site}: {len(rows)} cumulative cases",flush=True)
    result=pd.DataFrame(rows)
    result.to_parquet(OUT/"forcing_ablation_cases.parquet",index=False)
    result["failure"]=result.error.abs()>.5
    result.loc[result.available].groupby(["arm","design_family"]).agg(n=("error","size"),bias=("error","mean"),mae=("error",lambda s:s.abs().mean()),failure_rate=("failure","mean")).to_csv(OUT/"forcing_ablation_summary.csv")
    paired_forcing(result)


def paired_forcing(result):
    key=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]
    wide=result.loc[result.available&result.error.notna()].pivot(index=key,columns="arm",values="error")
    rows=[]
    for arm in ["Daymet","POWER_flow"]:
        if arm not in wide:
            continue
        b=wide.dropna(subset=["POWER",arm])
        for label,selected in [("all",np.ones(len(b),bool)),("danger",b.index.get_level_values("peak_overlap")>=.5),("air_layer_danger",(b.index.get_level_values("peak_overlap")>=.5)&(b.index.get_level_values("policy_choice")=="air_ridge"))]:
            s=b.loc[selected]
            rows.append(dict(arm=arm,stratum=label,n=len(s),POWER_mae=float(s.POWER.abs().mean()),alternative_mae=float(s[arm].abs().mean()),paired_mae_change=float((s[arm].abs()-s.POWER.abs()).mean()),POWER_bias=float(s.POWER.mean()),alternative_bias=float(s[arm].mean())))
    pd.DataFrame(rows).to_csv(OUT/"forcing_paired_common_cases.csv",index=False)


def natural_and_domain():
    OUT.mkdir(parents=True,exist_ok=True)
    base=T.ROOT/"results/wrr_submission_ready/followup_20261021"
    paths=[base/"natural_backup/qualification_summary.json",base/"public_backup_search/usgs_qualification_summary.json",base/"natural_backup/short_history/gap_sampling_audit.csv"]
    status={str(p.relative_to(T.ROOT)):json.loads(p.read_text()) if p.suffix==".json" else pd.read_csv(p).to_dict("records") for p in paths if p.exists()}
    # Unit: independent natural gaps, not dependent daily values.
    requirements=[]
    for risk in [.01,.025,.05,.1]:
        n=int(np.ceil(np.log(.05)/np.log(1-risk)))
        requirements.append(dict(failure_risk_to_exclude=risk,independent_zero_failure_gaps_for_one_sided_95=n))
    pd.DataFrame(requirements).to_csv(OUT/"natural_gap_sample_size.csv",index=False)
    T.write_json(OUT/"natural_gap_status.json",{"evidence":status,"interpretation":"No qualified natural outage with sufficient history and accurate independent peak-window reference established by the opened public search. Existing short-history winter pairs are exploratory and do not close the H30 claim.","triple_collocation":"Not identified from only paired logger data. Air and donor residual correlation must be measured on common complete days before assuming uncorrelated errors; no triple-collocation H30 accuracy claim is made.","minimum_reference":"paired-bias correction estimated on a separate overlap period; uncertainty in the reference propagated; effective independent outages, not daily n","completion":"qualification and minimum-sample calculation complete; independent natural-gap validation unavailable"})
    flow=pd.read_parquet(T.E1/"usgs_flow.parquet")
    nonpositive=flow.assign(zero=flow.flow_cms.le(0)).groupby("site").agg(n=("flow_cms","count"),zero_days=("zero","sum"))
    nonpositive.to_csv(OUT/"intermittency_proxy.csv")
    years=pd.read_parquet(T.E1/"station_years.parquet")
    characteristics=years.groupby("station_key").agg(n_years=("year","size"),n_complete=("complete_year","sum"),warm_completeness=("warm_observed_fraction","mean"),median_longest_gap=("longest_run","median"),provider=("provider","first"),regulation_status=("regulation_status","first"))
    characteristics["intermittency_zero_flow_days"]=characteristics.index.to_series().str.replace("usgs|","",regex=False).map(nonpositive.zero_days)
    characteristics.to_csv(OUT/"station_characteristics.csv")
    largest=[s for s in ["usgs|13342500","usgs|06054500"] if s in characteristics.index]
    characteristics.loc[largest].to_csv(OUT/"influential_station_profiles.csv")
    # Opened new-USGS data remain development. Never tune a boundary to force
    # a named failure outside: record the diagnosis rather than guarantee it.
    source=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    targetpath=T.ROOT/"results/wrr_target_recovery_20261022/e10_sealed_usgs/cases.parquet"
    if targetpath.exists():
        target=pd.read_parquet(targetpath)
        features=["peak_overlap","missing_fraction","train_h30_mean","train_h30_sd","air_warm_z_mean"]
        from sklearn.neighbors import NearestNeighbors
        source=source.groupby("station_key").first().dropna(subset=features)
        target=target.groupby("station_key").first().dropna(subset=features)
        mu=source[features].mean();sd=source[features].std().replace(0,1)
        x=((source[features]-mu)/sd).to_numpy();z=((target[features]-mu)/sd).to_numpy()
        nn=NearestNeighbors(n_neighbors=2).fit(x)
        # LORO calibration of distance avoids classifying training copies as in-domain.
        cv=[]
        for region,b in source.groupby("region"):
            other=source.region.ne(region).to_numpy()
            if other.sum():
                n=NearestNeighbors(n_neighbors=1).fit(x[other])
                cv.extend(n.kneighbors(((b[features]-mu)/sd).to_numpy())[0].ravel())
        boundary=float(np.quantile(cv,.95))
        distance=nn.kneighbors(z,n_neighbors=1)[0].ravel()
        target["dissimilarity"]=distance;target["outside_source_cv_95"]=distance>boundary
        target[["region","train_h30_mean","dissimilarity","outside_source_cv_95"]].to_csv(OUT/"opened_new_station_domain.csv")
        T.write_json(OUT/"domain_rule.json",{"features":features,"source_grouping":"one record per station; conservative independence still determined separately","boundary":boundary,"method":"standardized nearest-neighbor distance; cutoff from leave-one-region-out source distances","warning":"first available mask features are a screening sensitivity, not Meyer-Pebesma area-of-applicability validation or a physical river-type classification","new_data_status":"already opened; exploratory diagnosis only"})


def main():
    p=argparse.ArgumentParser();p.add_argument("--forcing",action="store_true");p.add_argument("--per-huc",type=int,default=2);a=p.parse_args()
    natural_and_domain()
    if a.forcing:
        ablation(a.per_huc)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
