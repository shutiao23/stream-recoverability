#!/usr/bin/env python3
"""Exploratory adaptation of existing case generator for incomplete histories.

The original generator remains untouched. The adapter keeps natural gaps hidden,
emits no target truth, and reports the actual count of fully observed histories.
Caller supplies explicitly interpolated other-year history and a target panel
whose natural missing days are placeholders; those days must be masked.
"""
import inspect
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT


def adapted_generator(cache):
    core=T.load_script('usace_partial_original_cases',ROOT/'scripts/431_tr_cases.py')
    core.CACHE=Path(cache)
    source=inspect.getsource(core.station_cases)
    replacements=[
        ('    plan = [(year, "complete") for year in years]',
         '    plan = [(int(job["partial_target_year"]), "partial")]'),
        ('        if kind == "complete":\n            designs = []',
         '        if kind in ("complete", "partial"):\n            designs = []'),
        ('            mask = design["mask"]\n',
         '            mask = design["mask"] | np.asarray(job["partial_natural_missing"], dtype=bool)\n'),
        ('"n_complete_years": len(train_years), "clim_peak":',
         '"n_complete_years": int(job["actual_complete_training_years"]), "clim_peak":'),
    ]
    for original,changed in replacements:
        if source.count(original)!=1:raise ValueError('Original case generator no longer matches adaptation')
        source=source.replace(original,changed,1)
    namespace=core.__dict__
    exec(compile(source,'<USACE partial-history case adaptation>','exec'),namespace)
    return core


def history_qualifies(s):
    """Availability rule chosen after previous completeness inspections."""
    a=s.isna().to_numpy();edges=np.diff(np.r_[False,a,False].astype(int))
    lengths=np.flatnonzero(edges==-1)-np.flatnonzero(edges==1)
    return bool(len(s) in (365,366) and s.notna().mean()>=.75 and not a[0] and not a[-1]
                and (len(lengths)==0 or int(lengths.max())<=45))


def prepare_panel(daily,resource_id,target_year,history_years,placeholder=0.):
    data=daily.loc[daily.resource_id.eq(resource_id)].set_index('day').mean_c
    if data.index.has_duplicates:raise ValueError('Duplicate daily inputs')
    idx=pd.date_range('2021-01-01','2025-12-31')
    raw=data.reindex(idx)
    panel=pd.Series(np.nan,index=idx,dtype=float)
    details=[]
    for year in history_years:
        x=raw.loc[raw.index.year==year]
        if not history_qualifies(x):raise ValueError('Frozen training year is ineligible')
        completed=x.interpolate(method='time',limit_area='inside')
        if completed.isna().any():raise ValueError('History interpolation failed')
        panel.loc[x.index]=completed
        details.append({'year':int(year),'reported_complete_days':int(x.notna().sum()),'interpolated_days':int(x.isna().sum())})
    target=raw.loc[raw.index.year==target_year]
    if len(target) not in (365,366) or target.notna().sum()<30:raise ValueError('Insufficient target days')
    panel.loc[target.index]=target.fillna(placeholder)
    return pd.DataFrame({'date':idx,resource_id:panel.to_numpy()}),target.isna().to_numpy(),details
