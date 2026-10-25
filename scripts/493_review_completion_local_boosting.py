#!/usr/bin/env python3
"""Locally fitted nonlinear MSE controls with the ridge model's exact air lags.

Global neural comparison and local daily reconstruction use different fitting
scope. This control matches the latter, with no held-year water in fitting or
preprocessing. It reuses every saved neural test mask and information stratum.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.v17_fitness.estimators import AIR_LAGS,MIN_TRAIN_ROWS

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]


def local_prediction(daily,held_year,seed,flow=None):
    index=daily.index;air=daily.air_c
    columns=[air.shift(lag).to_numpy(float) for lag in AIR_LAGS]
    doy=index.dayofyear.to_numpy();columns.extend([np.sin(2*np.pi*doy/365.25),np.cos(2*np.pi*doy/365.25)])
    if flow is not None:
        log=np.log1p(flow.clip(lower=0)).reindex(index)
        columns.extend(log.shift(lag).to_numpy(float) for lag in [0,1,3,7])
    x=np.column_stack(columns);y=daily.water_c.to_numpy(float);held=index.year==held_year
    train=~held&np.isfinite(y)&np.isfinite(x).all(axis=1)
    prediction=np.full(held.sum(),np.nan)
    if train.sum()<MIN_TRAIN_ROWS:return prediction,int(train.sum())
    model=HistGradientBoostingRegressor(loss="squared_error",max_iter=200,max_leaf_nodes=31,l2_regularization=1,random_state=seed)
    model.fit(x[train],y[train]);good=np.isfinite(x[held]).all(axis=1)
    if good.any():prediction[good]=model.predict(x[held][good])
    return prediction,int(train.sum())


def one(seed):
    reference=pd.read_parquet(OUT/f"deep/seed_{seed:02d}/saits_cases.parquet")
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet",columns=["station_key","date","water_c","air_c"])
    flow=pd.read_parquet(T.E1/"usgs_flow.parquet")
    q={str(site):b.set_index("date").flow_cms.groupby(level=0).mean() for site,b in flow.groupby("site")}
    rows={"boosting_local_air":[],"boosting_local_flow":[]}
    cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet",columns=["network_id","station_key","year","design_family","realization_id","policy_choice","mask_runs"])
    for si,(station,b) in enumerate(reference.groupby("station_key")):
        d=daily.loc[daily.station_key.eq(station)].set_index("date").sort_index().asfreq("D")
        site=station.split("|",1)[1];available_flow=q.get(site) if station.startswith("usgs|") else None
        keys=["network_id","station_key","year","design_family","realization_id","policy_choice"]
        b=b.merge(cases,on=keys,how="left",validate="one_to_one")
        for year,block in b.groupby("year"):
            held=d.index.year==year;truth=d.loc[held,"water_c"].to_numpy(float)
            for name in rows:
                if name=="boosting_local_flow" and available_flow is None:
                    center=np.full(len(truth),np.nan);n_train=0
                else:center,n_train=local_prediction(d,int(year),plain_seed(93,seed,si,int(year)),available_flow if name.endswith("flow") else None)
                for r in block.itertuples():
                    mask=T.mask_from_runs(r.mask_runs,len(truth));valid=np.isfinite(center[mask]).all()
                    completed=truth.copy();completed[mask]=center[mask]
                    actual=float(T.window_means(truth,30).max());point=float(T.window_means(completed,30).max()) if valid else np.nan
                    assert abs(actual-r.truth_h30)<5e-6,"Matched neural reference differs from local daily observations"
                    rows[name].append(dict(model=name,seed=seed,network_id=r.network_id,station_key=station,year=int(year),design_family=r.design_family,realization_id=r.realization_id,policy_choice=r.policy_choice,peak_overlap=r.peak_overlap,
                                           group=r.group,truth_h30=actual,h30_estimate=point,h30_error=point-actual,daily_mae=float(np.mean(np.abs(center[mask]-truth[mask]))) if valid else np.nan,
                                           available=bool(valid),n_draws=1,n_local_training_days=n_train,plug_in_error=r.plug_in_error))
    folder=OUT/f"deep/seed_{seed:02d}"
    for name,values in rows.items():pd.DataFrame(values).to_parquet(folder/f"{name}_cases.parquet",index=False)
    T.write_json(folder/"local_boosting_design.json",{"seed":seed,"model":"MSE HistGradientBoosting, 200 iterations, 31 leaves, L2=1; fixed budget, no target tuning","scope":"same target-station history as local ridge, except the complete held year is excluded from all training labels","air_features":"exact ridge raw air lags 0/1/2/3/5/7/14 and annual sine/cosine","flow_features":"log1p discharge lags 0/1/3/7; missing on any hidden day means unavailable","test":"identical saved neural test cases and masks; air-tier is the fair information comparison","neural_scope":"global models use local climatology but no local water-air coefficient refit; this local nonlinear comparator is separate"})
    print(f"local nonlinear controls seed {seed}: {len(reference)} matched cases",flush=True)
    return seed


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=[0,1,2]);p.add_argument("--workers",type=int,default=3);a=p.parse_args()
    Parallel(n_jobs=a.workers,verbose=10)(delayed(one)(seed) for seed in a.seeds)
    return 0


if __name__=="__main__":raise SystemExit(main())
