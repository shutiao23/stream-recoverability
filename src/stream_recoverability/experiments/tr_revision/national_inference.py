"""Descriptive inference for the retrieved national monitoring network."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import linregress,t

LEVELS=np.array([.05,.1,.25,.5,.75,.9,.95])


def project_lower_bound(value,lower):
    """A finite bound constrains an estimate; it never supplies a missing one."""
    value,lower=np.broadcast_arrays(np.asarray(value,float),np.asarray(lower,float))
    return np.where(np.isfinite(value),np.maximum(value,np.where(np.isfinite(lower),lower,-np.inf)),np.nan)


def slope_summary(years,values,minimum=15):
    years,values=np.asarray(years,float),np.asarray(values,float)
    good=np.isfinite(years)&np.isfinite(values)
    if good.sum()<minimum or np.ptp(years[good])==0:return None
    fit=linregress(years[good]/10,values[good])
    critical=t.ppf(.975,int(good.sum())-2)
    return {"n_years":int(good.sum()),"first_year":int(years[good].min()),"last_year":int(years[good].max()),
            "slope":float(fit.slope),"se":float(fit.stderr),"pvalue":float(fit.pvalue),
            "nominal_lower":float(fit.slope-critical*fit.stderr),"nominal_upper":float(fit.slope+critical*fit.stderr)}


def mi_slopes(block,prefix="D2",draws=20,seed=0,project=False):
    """Conditional imputation sensitivity, with no claim of calibrated coverage."""
    exact=block.complete.to_numpy(bool)
    point=block.observed_H30.where(block.complete,block.get(prefix+"_q50",pd.Series(np.nan,index=block.index))).to_numpy(float)
    good=np.isfinite(point)
    b=block.loc[good];exact=exact[good]
    if len(b)<15:return np.full(draws,np.nan)
    q=b.reindex(columns=[f"{prefix}_q{int(q*100):02d}" for q in LEVELS]).to_numpy(float)
    if np.any(~np.isfinite(q[~exact])):return np.full(draws,np.nan)
    rng=np.random.default_rng(seed);u=rng.random((draws,len(b)))
    values=np.empty_like(u)
    for j in range(len(b)):
        values[:,j]=b.observed_H30.iloc[j] if exact[j] else np.interp(u[:,j],LEVELS,q[j])
    if project:values=project_lower_bound(values,b.observed_H30_lower_bound.to_numpy()[None,:])
    x=(b.year.to_numpy()-b.year.mean())/10
    return values@x/(x@x)


def basin_bootstrap(frame,draws=2000,seed=0,column="slope"):
    """Spatial stability of network summaries, not a risk/coverage certificate."""
    units=sorted(frame.independence_group.dropna().unique())
    if len(units)<3:return {"n_blocks":len(units),"block_lower":np.nan,"block_upper":np.nan}
    groups=[frame.loc[frame.independence_group.eq(unit),column].dropna().to_numpy() for unit in units]
    rng=np.random.default_rng(seed);values=[]
    for _ in range(draws):
        sample=np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))])
        if len(sample):values.append(np.median(sample))
    low,high=np.quantile(values,[.025,.975])
    return {"n_blocks":len(units),"block_lower":float(low),"block_upper":float(high)}
