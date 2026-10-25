#!/usr/bin/env python3
"""MSE boosting with the ridge air lags and optional observed discharge.

Use the neural cohort's unchanged train/test groups and exact masks. Missing
flow is reported as unavailable for the flow arm, never a zero-error prediction.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from joblib import Parallel,delayed
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"deep"


def one(seed):
    helper=T.load_script("r4_boost_input_data",T.ROOT/"scripts/468_review_completion_deep.py")
    x,meta,tests=helper.prepare(seed)
    train=meta.role.eq("train").to_numpy()
    air=x[:,:,1];features=[]
    for lag in [0,1,2,3,5,7,14]:
        values=np.full_like(air,np.nan)
        if lag==0:values[:]=air
        else:values[:,lag:]=air[:,:-lag]
        features.append(values)
    features.extend([x[:,:,2],x[:,:,3]])
    design=np.stack(features,axis=-1)
    flow=pd.read_parquet(T.E1/"usgs_flow.parquet")
    lookup={str(site):b.set_index("date").flow_cms.groupby(level=0).mean() for site,b in flow.groupby("site")}
    flow_feature=np.full(x.shape[:2],np.nan,dtype=np.float32)
    for i,m in meta.iterrows():
        if not str(m.station_key).startswith("usgs|"):
            continue
        site=m.station_key.split("|",1)[1]
        if site not in lookup:
            continue
        series=np.log1p(lookup[site].clip(lower=0))
        allowed=series.index.year!=m.year
        mu=series.loc[allowed].mean();sd=max(float(series.loc[allowed].std()),.1)
        dates=pd.date_range(f"{m.year}-01-01",f"{m.year}-12-31")
        values=((series.reindex(dates)-mu)/sd).to_numpy(dtype=np.float32)
        flow_feature[i,:len(values)]=values
        if len(values)==365:flow_feature[i,-1]=values[-1]
    flow_design=np.concatenate([design,flow_feature[:,:,None]],axis=2)
    folder=OUT/f"seed_{seed:02d}"
    for name,z in [("boosting_lagged_air",design),("boosting_with_flow",flow_design)]:
        model=HistGradientBoostingRegressor(max_iter=200,max_leaf_nodes=31,l2_regularization=1,random_state=seed).fit(z[train].reshape(-1,z.shape[-1]),x[train,:,0].ravel())
        test_index=np.array([i for i,_,_ in tests]);prediction=model.predict(z[test_index].reshape(-1,z.shape[-1])).reshape(len(tests),366)
        rows=[]
        for j,(i,mask,r) in enumerate(tests):
            m=meta.loc[i];n=int(m.n_days);eligible=name!="boosting_with_flow" or np.isfinite(flow_feature[i,:n][mask]).all()
            completed=np.asarray(m.truth).copy()
            predicted=prediction[j,:n]*5+np.asarray(m.climate)
            completed[mask]=predicted[mask]
            truth=float(T.window_means(np.asarray(m.truth),30).max())
            estimate=float(T.window_means(completed,30).max()) if eligible else np.nan
            rows.append({"model":name,"seed":seed,**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},"group":m.group,"truth_h30":truth,"h30_estimate":estimate,"h30_error":estimate-truth,"daily_mae":float(np.mean(np.abs(predicted[mask]-np.asarray(m.truth)[mask]))) if eligible else np.nan,"n_draws":1,"flow_input_available":bool(np.isfinite(flow_feature[i,:n][mask]).all()),"available":eligible,"plug_in_error":r["h30__policy"]-truth})
        target=folder/f"{name}_cases.parquet";temporary=target.with_suffix(".partial");pd.DataFrame(rows).to_parquet(temporary,index=False);temporary.replace(target)
    T.write_json(folder/"nonlinear_input_design.json",{"air_lags_days":[0,1,2,3,5,7,14],"discharge_feature":"station-standardized log1p daily flow, reference excludes target year","groups_and_masks":"identical to saved neural comparison","neural_information_boundary":"neural models receive air and observed target water, without neighboring-water covariates; compare algorithm performance primarily within the air-ridge tier","missing_discharge":"flow arm unavailable where any hidden-day flow is absent; no success imputed","original_boosting_arm":"current-air-only comparator retained as an exploratory development specification"})
    return seed


def main():
    Parallel(n_jobs=3,verbose=10)(delayed(one)(seed) for seed in [0,1,2])
    return 0


if __name__=="__main__":
    raise SystemExit(main())
