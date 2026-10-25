#!/usr/bin/env python3
"""Matched opened-source SAITS, sampled CSDI, MSE LSTM and daily boosting.

An independent-group split is made before constructing training/validation
windows. This is a finite CPU-budget comparator, not a tuned state of the art
claim. Conditional draws are scored before taking any median of the daily path.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import random
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader,TensorDataset
from sklearn.ensemble import HistGradientBoostingRegressor
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps,interval_score

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"deep"


def prepare(seed):
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet")
    daily["year"]=daily.date.dt.year
    case=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet")
    groups=case[["station_key","independence_group"]].drop_duplicates().set_index("station_key").independence_group
    if groups.index.duplicated().any():
        raise RuntimeError("Station identity crosses independence groups")
    rng=np.random.default_rng(seed)
    units=np.array(sorted(groups.unique()))
    rng.shuffle(units)
    train_group,val_group,test_group=np.split(units,[int(.6*len(units)),int(.8*len(units))])
    lookup={g:role for role,gs in [("train",train_group),("validation",val_group),("test",test_group)] for g in gs}
    arrays,metadata=[],[]
    for station,b in daily.groupby("station_key"):
        if station not in groups:
            continue
        role=lookup[groups[station]]
        b=b.sort_values("date").set_index("date").asfreq("D")
        # Climatology excludes the target year for every train, validation and test record.
        for year in sorted(case.loc[case.station_key.eq(station),"year"].unique()):
            target=b.loc[b.index.year==year]
            history=b.loc[b.index.year!=year]
            if len(target)<365 or target.water_c.isna().any() or target.air_c.isna().any():
                continue
            clim=history.water_c.groupby(history.index.dayofyear).mean().reindex(range(1,367)).interpolate(limit_direction="both")
            airclim=history.air_c.groupby(history.index.dayofyear).mean().reindex(range(1,367)).interpolate(limit_direction="both")
            doy=target.index.dayofyear.to_numpy()
            climate=clim.reindex(doy).to_numpy()
            water=target.water_c.to_numpy()
            features=np.column_stack([(water-climate)/5,(target.air_c.to_numpy()-airclim.reindex(doy).to_numpy())/10,np.sin(2*np.pi*doy/365.25),np.cos(2*np.pi*doy/365.25)])
            if not np.isfinite(features).all():
                continue
            if len(features)==365:
                features=np.vstack([features,features[-1]])
            arrays.append(features.astype(np.float32))
            metadata.append(dict(station_key=station,year=int(year),group=groups[station],role=role,n_days=len(target),climate=climate,truth=water))
    x=np.stack(arrays)
    meta=pd.DataFrame(metadata)
    # At most 2 deterministically spaced test years per station, specified before
    # evaluating a model; the full group split remains available in the manifest.
    chosen=[]
    for _,b in meta.loc[meta.role.eq("test")].groupby("station_key"):
        chosen.extend(b.sort_values("year").iloc[np.unique(np.linspace(0,len(b)-1,min(2,len(b))).astype(int))].index)
    tests=[]
    for i in chosen:
        m=meta.loc[i]
        b=case.loc[case.station_key.eq(m.station_key)&case.year.eq(m.year)]
        selected=pd.concat([b.loc[b.design_family.eq("calendar")].head(1),b.loc[b.design_family.eq("crossed")&b.peak_overlap.ge(.5)].head(2)])
        for _,r in selected.iterrows():
            mask=T.mask_from_runs(r.mask_runs,int(m.n_days))
            tests.append((i,mask,r.to_dict()))
    return x,meta,tests


class MeanLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.rnn=nn.LSTM(3,32,batch_first=True,bidirectional=True)
        self.output=nn.Linear(64,1)
    def forward(self,x):
        return self.output(self.rnn(x[:,:,1:])[0]).squeeze(-1)


def train_lstm(x,train,val,epochs,seed):
    torch.manual_seed(seed)
    model=MeanLSTM()
    optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    loader=DataLoader(TensorDataset(torch.tensor(x[train])),batch_size=32,shuffle=True)
    best=np.inf
    state=None
    history=[]
    for epoch in range(epochs):
        model.train()
        losses=[]
        for (data,) in loader:
            optimizer.zero_grad()
            loss=torch.mean((model(data)-data[:,:,0])**2)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            validation=float(torch.mean((model(torch.tensor(x[val]))-torch.tensor(x[val,:,0]))**2))
        history.append(dict(epoch=epoch,train_mse=float(np.mean(losses)),validation_mse=validation))
        if validation<best:
            best=validation
            state={k:v.detach().clone() for k,v in model.state_dict().items()}
        elif epoch>=5 and all(h["validation_mse"]>best for h in history[-5:]):
            break
    model.load_state_dict(state)
    model.eval()
    return model,history


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--epochs",type=int,default=CONFIG["deep_epochs"])
    p.add_argument("--models",nargs="+",default=["boosting","lstm","saits","csdi"])
    p.add_argument("--threads",type=int,default=2)
    a=p.parse_args()
    torch.set_num_threads(a.threads)
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    folder=OUT/f"seed_{a.seed:02d}";folder.mkdir(parents=True,exist_ok=True)
    x,meta,tests=prepare(a.seed)
    train=meta.role.eq("train").to_numpy()
    # Balance early-stopping evidence over independent groups. Selection uses
    # group identity and calendar position only, never validation loss or H30.
    validation_indices=[]
    for _,block in meta.loc[meta.role.eq("validation")].groupby("group"):
        block=block.sort_values(["station_key","year"])
        count=min(CONFIG["deep_validation_years_per_group"],len(block))
        validation_indices.extend(block.iloc[np.unique(np.linspace(0,len(block)-1,count).astype(int))].index)
    val=meta.index.isin(validation_indices)
    meta["used_for_early_stopping"]=val
    rng=np.random.default_rng(a.seed)
    def mask_input(arr):
        data=arr.copy()
        for i in range(len(data)):
            length=int(rng.choice([30,60,90]))
            start=int(rng.integers(0,366-length))
            data[i,start:start+length,0]=np.nan
        return data
    masked_train=mask_input(x[train]);masked_val=mask_input(x[val])
    test_x=np.stack([x[i].copy() for i,_,_ in tests])
    for j,(_,mask,_) in enumerate(tests):
        test_x[j,np.flatnonzero(mask),0]=np.nan
    meta.drop(columns=["truth","climate"]).to_csv(folder/"group_split.csv",index=False)
    T.write_json(folder/"design.json",{"seed":a.seed,"n_train":int(train.sum()),"n_validation":int(val.sum()),"n_validation_groups":int(meta.loc[val,"group"].nunique()),"validation_selection":"at most three evenly spaced station-years per independent validation group, chosen without losses or H30 values","n_test_cases":len(tests),"n_test_groups":int(meta.loc[[i for i,_,_ in tests],"group"].nunique()),"epochs_cap":a.epochs,"annual_steps":366,"water_scale_c":5,"air_scale_c":10,"input_features":["water_anomaly","air_anomaly","season_sin","season_cos"],"test_selection":"first calendar and first two decision-time dangerous crossed cases for two evenly spaced eligible years per held-group station","budget":"CPU, small fixed architecture, validation early stopping; no test tuning","evidence_role":"opened-source mechanism comparator","csdi_diffusion_steps":20,"csdi_target_strategy":"mix: water-only contiguous patterns and random masking","development_attempt":"full case-weighted validation runs were stopped for computational cost before any CSDI test prediction; all final arms rerun with the same group-balanced rule"})
    all_rows=[]
    for name in a.models:
        destination=folder/f"{name}_cases.parquet"
        if destination.exists():
            continue
        if name=="boosting":
            model=HistGradientBoostingRegressor(max_iter=200,max_leaf_nodes=31,l2_regularization=1,random_state=a.seed).fit(x[train,:,1:].reshape(-1,3),x[train,:,0].ravel())
            prediction=model.predict(test_x[:,:,1:].reshape(-1,3)).reshape(len(test_x),366)[:,None,:]
        elif name=="lstm":
            model,history=train_lstm(x,train,val,a.epochs,a.seed)
            pd.DataFrame(history).to_csv(folder/"lstm_training.csv",index=False)
            torch.save(model.state_dict(),folder/"lstm.pt")
            with torch.no_grad():
                prediction=model(torch.tensor(np.nan_to_num(test_x))).numpy()[:,None,:]
        else:
            from pypots.imputation import SAITS,CSDI
            from pypots.nn.modules.loss import MSE
            common=dict(n_steps=366,n_features=4,n_layers=1,n_heads=2,batch_size=16,epochs=a.epochs,patience=5,device="cpu",saving_path=str(folder/name),verbose=True)
            if name=="saits":
                model=SAITS(**common,d_model=32,d_k=16,d_v=16,d_ffn=64,training_loss=MSE)
                model.fit({"X":masked_train},{"X":masked_val,"X_ori":x[val]})
                result=model.predict({"X":test_x})["imputation"]
                result=result.detach().cpu().numpy() if torch.is_tensor(result) else result
                prediction=np.asarray(result)[:,:,0][:,None,:]
            else:
                model=CSDI(**common,n_channels=16,d_time_embedding=32,d_feature_embedding=8,d_diffusion_embedding=32,n_diffusion_steps=20,target_strategy="mix")
                model.fit({"X":x[train],"for_pattern_mask":np.isfinite(masked_train).astype(np.float32)},{"X":masked_val,"X_ori":x[val]})
                result=model.predict({"X":test_x},n_sampling_times=CONFIG["deep_draws"])["imputation"]
                result=result.detach().cpu().numpy() if torch.is_tensor(result) else result
                result=np.asarray(result)
                if result.shape!=(len(test_x),CONFIG["deep_draws"],366,4):
                    raise RuntimeError(f"Unexpected CSDI draws {result.shape}; averaging paths would invalidate the H30 comparison")
                prediction=result[:,:,:,0]
            model.save(str(folder/f"{name}.pypots"))
        rows=[]
        for j,(i,mask,r) in enumerate(tests):
            m=meta.loc[i];n=int(m.n_days)
            draws=prediction[j,:,:n]*5+np.asarray(m.climate)
            draws[:,~mask]=np.asarray(m.truth)[~mask]
            h=T.window_means(draws,30).max(axis=1)
            truth=float(T.window_means(np.asarray(m.truth),30).max())
            lower,upper=np.quantile(h,[.05,.95])
            row={"model":name,"seed":a.seed,**{k:r[k] for k in ["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]},"truth_h30":truth,"h30_estimate":float(np.median(h)),"h30_error":float(np.median(h)-truth),"daily_mae":float(np.mean(np.abs(draws.mean(axis=0)[mask]-np.asarray(m.truth)[mask]))),"n_draws":len(h),"h30_draws":h.tolist(),"group":m.group}
            if len(h)>1:
                row.update(crps=float(ensemble_crps(h[None,:],np.array([truth]))[0]),twcrps=float(ensemble_crps(h[None,:],np.array([truth]),r["train_h30_q90"])[0]),coverage90=bool(lower<=truth<=upper),interval_score90=float(interval_score(lower,upper,truth)))
            # Same-case simple methods make the deep comparison auditable.
            row["plug_in_error"]=r["h30__policy"]-truth
            rows.append(row)
        pd.DataFrame(rows).to_parquet(destination,index=False)
        print(f"{name}: {len(rows)} matched cases",flush=True)
    for path in folder.glob("*_cases.parquet"):
        all_rows.append(pd.read_parquet(path))
    results=pd.concat(all_rows,ignore_index=True)
    results["failure"]=results.h30_error.abs()>.5
    results.groupby(["model","design_family"]).agg(n=("h30_error","size"),bias=("h30_error","mean"),mae=("h30_error",lambda s:s.abs().mean()),daily_mae=("daily_mae","mean"),failure_rate=("failure","mean")).to_csv(folder/"summary.csv")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
