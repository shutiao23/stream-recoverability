#!/usr/bin/env python3
"""Recover stochastic baselines unnecessarily refused outside the hidden gap.

The daily center is needed only on missing days and any conditioned boundary.
This repairs a baseline availability bug; none of these columns is a feature
or label of the fitted D2/P2/failure models, which therefore need no refit.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels,usable_donors,linear_interp_fill
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.tr_revision.baselines import ar1_bridge
from stream_recoverability.seeds import plain_seed

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]
KEYS=["network_id","station_key","year","design_family","realization_id","policy_choice","mask_runs"]
LEVELS=(.05,.1,.25,.5,.75,.9,.95)


def one(split,job,settings):
    module=T.load_script("r4_bridge_repair_case",T.ROOT/"scripts/431_tr_cases.py")
    path=module.cache_path(job,settings)
    folder=OUT/"repairs"/split/"station_parts";folder.mkdir(parents=True,exist_ok=True)
    destination=folder/f"{job['network_id']}__{job['station_id']}.parquet"
    if destination.exists():
        return str(destination)
    if not path.exists():
        return None
    frame=pd.read_parquet(path)
    if frame.empty or "stochastic_h30_draws" not in frame:
        return None
    invalid=frame.stochastic_h30_draws.map(lambda x:not (np.ndim(x)==1 and np.isfinite(x).all()))&frame.policy_choice.ne("unavailable")
    if not invalid.any():
        pd.DataFrame(columns=KEYS+["replication_seed"]).to_parquet(destination,index=False)
        return str(destination)
    panel=read_temperature_panel(job["input_path"]).asfreq("D");panel.columns=panel.columns.astype(str)
    real_index=panel.index
    shift=T.hemisphere_shift_days(job.get("latitude"))
    if shift:
        panel.index+=pd.Timedelta(days=shift)
    if settings.get("synthetic_water_trend_c_decade",0):
        panel=panel.add(float(settings["synthetic_water_trend_c_decade"])*(panel.index.year.to_numpy()-2000)/10,axis=0)
    target=panel[job["station_id"]];donors=panel.drop(columns=job["station_id"])
    years=module.CORE.complete_years(target)
    air=station_air_series(T.AIR,job["network_id"],job["station_id"],real_index)
    if air is not None:
        air.index=target.index
    water=target.to_numpy(float);rows=[]
    for year,year_block in frame.groupby("year",sort=False):
        if not invalid.loc[year_block.index].any():
            continue
        held=target.index.year==year;allowed=pd.Series(~held,index=target.index)
        if split=="before_2010":
            allowed&=target.index.year<2010
        elif split=="cold_to_hot":
            annual={y:float(T.window_means(water[target.index.year==y],30).max()) for y in years}
            cutoff=float(np.quantile(list(annual.values()),.8))
            excluded=[y for y,v in annual.items() if v>=cutoff]
            allowed&=~target.index.year.isin(excluded)
        train_years=[y for y in years if y!=year and allowed.loc[target.index.year==y].any()]
        index=target.index[held];truth=water[held];model=StationModels(target,donors,air,allowed)
        residual_cache={}
        for seed,b in year_block.groupby("replication_seed",sort=False):
            for local_position,(i,r) in enumerate(b.iterrows()):
                if not invalid.loc[i]:
                    continue
                mask=T.mask_from_runs(r.mask_runs,len(index));observed=truth.copy();observed[mask]=np.nan
                visible=usable_donors(donors,index,mask);choice=r.policy_choice
                if choice=="air_ridge":
                    center=model.air_predict(index)
                elif choice=="donor_ridge":
                    fitted=model.donor_ridge(visible)
                    center=model.donor_predict(fitted,index) if fitted is not None else np.full(len(index),np.nan)
                elif choice=="linear_interp":
                    center=linear_interp_fill(observed)
                elif choice=="doy_climatology":
                    center=model.doy_climatology(index)
                else:
                    center=model.smooth_climatology(index)
                missing_doy=tuple(index.dayofyear.to_numpy()[mask]) if choice=="linear_interp" else ()
                key=(choice,tuple(visible) if choice=="donor_ridge" else (),missing_doy)
                if key not in residual_cache:
                    residual_cache[key]=module.CORE.residual_history(target,donors,air,allowed,train_years,choice,tuple(visible),missing_doy)
                seed_value=plain_seed(9,int(seed),job["station_index"],int(year),local_position)
                draws=ar1_bridge(observed,center,residual_cache[key],seed_value,settings["multiple_imputations"])
                if not np.isfinite(draws).all():
                    continue
                h30=T.window_means(draws,30).max(axis=1)
                result={k:r[k] for k in KEYS};result["replication_seed"]=int(seed);result["h30__stochastic_regression"]=float(np.median(h30));result["stochastic_h30_draws"]=h30.tolist()
                result.update({f"stochastic_h30_q{int(q*100):02d}":float(v) for q,v in zip(LEVELS,np.quantile(h30,LEVELS))})
                rows.append(result)
    pd.DataFrame(rows,columns=KEYS+["replication_seed","h30__stochastic_regression","stochastic_h30_draws"]+[f"stochastic_h30_q{int(q*100):02d}" for q in LEVELS]).to_parquet(destination,index=False)
    return str(destination)


def main():
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=24);p.add_argument("--splits",nargs="+",default=["leave_one_year_out","cold_to_hot","before_2010","non_air_refit"]);a=p.parse_args()
    module=T.load_script("r4_bridge_repair_parent",T.ROOT/"scripts/431_tr_cases.py")
    jobs=module.jobs_for("source")
    for split in a.splits:
        settings=json.loads((OUT/"cases"/split/"generation_settings.json").read_text())
        results=Parallel(n_jobs=a.workers,verbose=10)(delayed(one)(split,job,settings) for job in jobs)
        folder=OUT/"repairs"/split;folder.mkdir(parents=True,exist_ok=True)
        parts=[pd.read_parquet(path) for path in results if path]
        parts=[f for f in parts if len(f)]
        frame=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
        for seed in settings["replication_seeds"]:
            b=frame.loc[frame.replication_seed.eq(seed)] if len(frame) else pd.DataFrame(columns=KEYS)
            b.to_parquet(folder/f"seed_{seed:02d}.parquet",index=False)
        T.write_json(folder/"summary.json",{"repaired_rows":len(frame),"reason":"daily mean required only on hidden days; unavailable visible-day center no longer rejects a bridge","features_unchanged":True,"D2_P2_classifier_refit_required":False,"seeds":settings["replication_seeds"]})
        print(f"repaired {len(frame)} stochastic baselines in {split}",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
