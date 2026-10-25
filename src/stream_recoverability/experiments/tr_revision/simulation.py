"""Cache deterministic history transforms without changing seeded draws."""
from __future__ import annotations
import numpy as np
import pandas as pd


def visible_air_exposure(observed,air,warm,*,days=7,top_fraction=.1,seed=0):
    """Synthetic unflagged logger exposure, chosen only from visible warm air.

    This contaminates a still-defined water-temperature target. It does not
    invent a physical water temperature for a genuinely dry bed.
    """
    values=np.asarray(observed,float).copy();air=np.asarray(air,float);warm=np.asarray(warm,bool)
    if values.shape!=air.shape or values.shape!=warm.shape:raise ValueError("Aligned daily vectors required")
    exposed=np.zeros(len(values),bool)
    if days<1 or len(values)<days:return values,exposed
    valid=np.isfinite(values)&np.isfinite(air)&warm
    starts=np.flatnonzero(np.convolve(valid.astype(int),np.ones(days,int),mode="valid")==days)
    if not len(starts):return values,exposed
    scores=np.array([air[i:i+days].mean() for i in starts])
    eligible=starts[scores>=np.quantile(scores,1-top_fraction)]
    start=int(np.random.default_rng(seed).choice(eligible))
    exposed[start:start+days]=True;values[exposed]=air[exposed]
    return values,exposed


def prepare_states(target_dates,residuals,history_dates,history_states=None,block_days=14):
    dates,history=pd.DatetimeIndex(target_dates),pd.DatetimeIndex(history_dates)
    residuals=np.asarray(residuals,float)
    month_day=dates.strftime("%m-%d")
    paths,states=[],[]
    high=np.full(len(history),np.nan)
    for year in sorted(set(history.year)):
        held=history.year==year;values=residuals[held]
        if np.isfinite(values).sum()<180:
            continue
        smooth=pd.Series(values).rolling(60,center=True,min_periods=15).mean().to_numpy()
        high[held]=values-smooth
        mapping=pd.Series(smooth,index=history[held].strftime("%m-%d"))
        mapped=mapping.reindex(month_day).interpolate(limit_direction="both").to_numpy()
        if not np.isfinite(mapped).all():
            continue
        paths.append(mapped)
        state=[]
        if history_states is not None:
            for old in np.asarray(history_states).T:
                state.append(pd.Series(old[held],index=history[held].strftime("%m-%d")).reindex(month_day).to_numpy())
        states.append(state)
    if len(paths)<2:
        raise ValueError("At least two usable residual years are required")
    valid=np.flatnonzero(np.convolve(np.isfinite(high).astype(int),np.ones(block_days,dtype=int),mode="valid")==block_days)
    valid=valid[history.year[valid]==history.year[valid+block_days-1]]
    if not len(valid):
        raise ValueError("No within-year residual block")
    blocks=[]
    for start in range(0,len(dates),block_days):
        distance=np.abs(history.dayofyear.to_numpy()[valid]-dates.dayofyear[start])
        seasonal=valid[np.minimum(distance,366-distance)<=30]
        blocks.append(seasonal if len(seasonal) else valid)
    return {"paths":np.asarray(paths),"states":np.asarray(states),"high":high,"blocks":blocks,"block_days":block_days,"n_days":len(dates)}


def prepared_draws(observed,center,prepared,*,seed,n_draws=128,target_states=None):
    observed,center=map(lambda x:np.asarray(x,float),(observed,center))
    missing=~np.isfinite(observed);visible=~missing&np.isfinite(center)
    if not np.isfinite(center[missing]).all():
        raise ValueError("Unavailable reconstruction center")
    current=float(np.mean(observed[visible]-center[visible])) if visible.any() else 0.
    analog=[];target_features=[current]
    state=np.asarray(target_states).T if target_states is not None else []
    for values in state:
        valid=missing&np.isfinite(values)
        target_features.append(float(values[valid].mean()) if valid.any() else np.nan)
    for i,path in enumerate(prepared["paths"]):
        entry=[float(path[visible].mean()) if visible.any() else float(path.mean())]
        for old in prepared["states"][i]:
            valid=missing&np.isfinite(old)
            entry.append(float(old[valid].mean()) if valid.any() else np.nan)
        analog.append(entry)
    analog=np.asarray(analog);target_features=np.asarray(target_features)
    distance=np.zeros(len(analog));dimensions=np.zeros(len(analog))
    for j in range(analog.shape[1]):
        values=analog[:,j];valid=np.isfinite(values)&np.isfinite(target_features[j])
        finite=values[np.isfinite(values)];scale=max(float(finite.std()),.25) if len(finite) else 1.
        distance[valid]+=((values[valid]-target_features[j])/scale)**2;dimensions[valid]+=1
    distance=np.divide(distance,dimensions,out=np.full(len(distance),4.),where=dimensions>0)
    weight=np.exp(-np.minimum(distance,50)/2);weight=.9*weight/weight.sum()+.1/len(weight)
    rng=np.random.default_rng(seed)
    paths=prepared["paths"][rng.choice(len(weight),n_draws,p=weight)]
    noise=np.zeros((n_draws,len(observed)));block_days=prepared["block_days"]
    for i,start in enumerate(range(0,len(observed),block_days)):
        length=min(block_days,len(observed)-start)
        sampled=rng.choice(prepared["blocks"][i],n_draws)
        noise[:,start:start+length]=prepared["high"][sampled[:,None]+np.arange(length)]
    draws=np.broadcast_to(observed,(n_draws,len(observed))).copy()
    draws[:,missing]=center[missing]+paths[:,missing]+noise[:,missing]
    return draws


def prepare_replay(target,residual,years,window=30):
    index=target.index;water=target.to_numpy(dtype=float);fixtures=[]
    for year in years:
        held=index.year==year;truth=water[held]
        if not np.isfinite(truth).all():
            continue
        full=np.cumsum(np.r_[0.,truth]);full30=(full[window:]-full[:-window])/window
        fixtures.append((truth,index[held].dayofyear.to_numpy(),np.asarray(residual)[held],float(full30.max())))
    return fixtures


def replay_from_prepared(fixtures,mask_days,window=30):
    days=np.zeros(367,bool);days[np.asarray(mask_days,int)]=True
    errors=[]
    for truth,doy,noise,h30 in fixtures:
        hidden=days[doy]
        if not hidden.any() or not np.isfinite(noise[hidden]).all():
            continue
        completed=truth.copy();completed[hidden]-=noise[hidden]
        sums=np.cumsum(np.r_[0.,completed]);value=((sums[window:]-sums[:-window])/window).max()
        errors.append(float(value-h30))
    return errors
