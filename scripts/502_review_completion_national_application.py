#!/usr/bin/env python3
"""Apply the fixed annual source model to the nationally fixed source frame.

Complete values remain observed. Supported incomplete years receive the same
offline daily recipe and fixed annual weights; unknown truth is not scored.
Partial runs live in a separate directory and cannot complete the national gate.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.national import hydrologic_blocks
from stream_recoverability.experiments.tr_revision.national_inference import project_lower_bound
from stream_recoverability.seeds import position_index

OUT=T.ROOT/"results/wrr_review_completion_20261024/national_meaning"
DATA=T.ROOT/"data/external/wrr_review_national_20261024"


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def one(job,settings,generator,resume):
    core=T.load_script("national_source_real_case_worker",T.ROOT/"scripts/431_tr_cases.py")
    return core.station_cases(job,settings,generator,[],resume)


def main():
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=24);p.add_argument("--partial",action="store_true");p.add_argument("--limit-targets",type=int);p.add_argument("--resume",action="store_true");a=p.parse_args()
    acquisition=json.loads((OUT/"acquisition.json").read_text())
    if not acquisition.get("all_planned_attempted") and not a.partial:raise RuntimeError("Finish the full fixed acquisition or explicitly request a partial pipeline check")
    destination=OUT/(f"smoke_{a.limit_targets}" if a.limit_targets else "partial_application" if a.partial else "application")
    destination.mkdir(parents=True,exist_ok=True)
    plan=json.loads((OUT/"plan.json").read_text())
    model=OUT.parent/"deployment/global_source_candidate.joblib"
    if digest(model)!=plan["source_model_sha256"]:raise RuntimeError("Annual source weights changed")
    roster=pd.read_csv(OUT/"candidate_roster.csv",dtype={"station_id":str,"series_id":str,"hydrologic_unit_code":str})
    indexed={};annual=[];available=[]
    helper_sha=digest(T.ROOT/"src/stream_recoverability/experiments/tr_revision/national.py")
    for row in roster.to_dict("records"):
        result_path=OUT/"site_results"/(row["station_id"]+".json")
        if not result_path.exists():continue
        result=json.loads(result_path.read_text())
        if result.get("status")!="processed" or result.get("helper_sha256")!=helper_sha:continue
        path=DATA/"annual"/(row["station_id"]+".parquet")
        if not path.exists():continue
        block=pd.read_parquet(path)
        if block.empty:continue
        huc2,group,network=hydrologic_blocks(row.get("hydrologic_unit_code"))
        if network=="unknown":network="nat_singleton_"+row["station_id"]
        row.update(huc2=huc2,independence_group=group,network_id=network)
        indexed[row["station_id"]]=row;available.append(row);annual.append(block)
    if not annual:raise RuntimeError("No QC-processed annual records yet")
    years=pd.concat(annual,ignore_index=True)
    targets=[]
    for station,block in years.groupby("station_id"):
        supported=block.qc_year&block.n_usable.ge(30)
        if block.complete.sum()>=4 and supported.sum()>=15 and (supported&~block.complete).any():targets.append(station)
    targets=sorted(targets)
    if not a.partial and not a.limit_targets:
        forcing_status=json.loads((OUT/"forcing_status.json").read_text())
        if forcing_status.get("cached_only") or set(forcing_status.get("eligible_target_ids",[]))!=set(targets):
            raise RuntimeError("Finish forcing acquisition for this complete eligible target roster")
    if a.limit_targets:targets=targets[:a.limit_targets]
    air_path=DATA/"air_forcing.parquet"
    forcing=pd.read_parquet(air_path) if air_path.exists() else pd.DataFrame(columns=["date","air_temperature_c","station_id","network_id"])
    forcing["station_id"]=forcing.station_id.astype(str)
    all_positions=position_index(f"{hydrologic_blocks(r.get('hydrologic_unit_code'))[2]}|{r['station_id']}" for r in roster.to_dict("records"))
    settings=json.loads((OUT.parent/"independent_study/source_case_settings.json").read_text())
    settings["calendar_year_only"]=True
    generator=json.loads((OUT.parent/"independent_study/source_missingness_generator.json").read_text())
    core_path=T.ROOT/"scripts/431_tr_cases.py"
    jobs=[];snapshot=[]
    frame=pd.DataFrame(available)
    for network,block in frame.groupby("network_id"):
        target_rows=block.loc[block.station_id.isin(targets)]
        if target_rows.empty:continue
        ids=sorted(block.station_id)
        series=[]
        for station in ids:
            d=pd.read_parquet(DATA/"daily"/(station+".parquet"))
            series.append(d.set_index("date").water_c.rename(station))
        panel=pd.concat(series,axis=1).reindex(pd.date_range("1980-01-01","2026-01-02"));panel.index.name="date"
        panel_bytes=panel.to_csv().encode()
        air=forcing.loc[forcing.station_id.isin(ids)].copy();air["network_id"]=network
        air=air.sort_values(["station_id","date"]).reset_index(drop=True)
        allowed={r.station_id:years.loc[years.station_id.eq(r.station_id)&years.qc_year&years.n_usable.ge(30)&~years.complete,"year"].astype(int).tolist() for r in target_rows.itertuples(index=False)}
        fingerprint=hashlib.sha256(panel_bytes+pd.util.hash_pandas_object(air,index=False).values.tobytes()+core_path.read_bytes()+json.dumps(allowed,sort_keys=True).encode()+json.dumps(settings,sort_keys=True).encode()+json.dumps(generator,sort_keys=True).encode()).hexdigest()
        folder=DATA/"application_inputs"/network/fingerprint[:16];folder.mkdir(parents=True,exist_ok=True)
        water=folder/"daily.csv";water.write_bytes(panel_bytes)
        air.to_parquet(folder/"air.parquet",index=False)
        snapshot.append({"network_id":network,"fingerprint":fingerprint,"stations":ids,"water_sha256":digest(water),"air_sha256":digest(folder/"air.parquet")})
        for row in target_rows.to_dict("records"):
            stable_network=hydrologic_blocks(row.get("hydrologic_unit_code"))[2]
            job={"network_id":network,"station_id":row["station_id"],"station_key":"usgs|"+row["station_id"],"provider":"usgs",
                 "independence_group":row["independence_group"],"region":"national_huc"+row["huc2"],"latitude":row["latitude"],
                 "statistic_class":"daily_mean","regulation_status":"unknown","roster":"real","real_years":allowed[row["station_id"]],
                 "station_index":all_positions[f"{stable_network}|{row['station_id']}"],"input_path":str(water),"air_input_path":str(folder/"air.parquet")}
            local=settings|{"version":"wrr_review_national_20261024/"+network+"/"+fingerprint[:16]}
            jobs.append((job,local))
    T.write_json(destination/"input_snapshot.json",{"networks":snapshot,"targets":targets,"source_model_sha256":digest(model),"partial":a.partial or bool(a.limit_targets),"n_processed_station_panels":len(indexed)})
    results=Parallel(n_jobs=a.workers,verbose=10)(delayed(one)(job,setting,generator,a.resume) for job,setting in jobs)
    parts=[]
    for (job,_),result in zip(jobs,results):
        if result.get("cache"):
            c=pd.read_parquet(result["cache"])
            if c.empty:continue
            if not set(c.year).issubset(job["real_years"]):raise RuntimeError("Case outside fixed supported analysis years")
            parts.append(c)
    cases=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    cases.to_parquet(destination/"real_cases.parquet",index=False)
    if len(cases):
        inference=T.load_script("national_source_fixed_annual_inference",T.ROOT/"scripts/495_review_completion_independent_analysis.py")
        predicted=inference.predict(cases,joblib.load(model))
        calibration=OUT.parent/"deployment/classical_calibration.json"
        if digest(calibration)!=plan["classical_calibration_sha256"]:raise RuntimeError("Source interval calibration changed")
        predicted=inference.classical_predictions(predicted,json.loads(calibration.read_text()))
        predicted.to_parquet(destination/"predictions.parquet",index=False)
        keys=["station_id","year"]
        keep=keys+["D2","risk_score","P2","h30__policy","h30__move1_warm"]+[f"D2_q{int(q*100):02d}" for q in [.05,.1,.25,.5,.75,.9,.95]]+[f"stochastic_cal_q{int(q*100):02d}" for q in [.05,.1,.25,.5,.75,.9,.95]]
        years=years.merge(predicted.reindex(columns=keep),on=keys,how="left",validate="one_to_one")
    else:
        for name in ["D2","risk_score","P2","h30__policy","h30__move1_warm"]:years[name]=np.nan
    years["retained_H30"]=years.observed_H30.where(years.complete,years.D2)
    years["individual_release"]=years.complete|(years.D2.notna()&years.risk_score.le(.1))
    years["lower_bound_coherent_D2"]=project_lower_bound(years.D2,years.observed_H30_lower_bound)
    years.to_parquet(destination/"annual_panel.parquet",index=False)
    T.write_json(destination/"status.json",{"application_complete":True,"partial":a.partial or bool(a.limit_targets),"year_definition":"calendar1981--2025, including any Southern US territories; no invented coordinate changes","n_processed_stations":len(indexed),"n_model_targets":len(targets),"n_real_cases":len(cases),"model_weights_unchanged":digest(model)==plan["source_model_sha256"],"new_NZ_temperature_values_requested":False,"truth":"Incomplete-year truth remains unknown. Raw annual estimates stay primary; hard-lower-bound projection is a separate sensitivity, not a retuned estimator."})
    return 0


if __name__=="__main__":raise SystemExit(main())
