#!/usr/bin/env python3
"""Compare canonical archive with its selected local daily input panels.

The CSV input panels are processed project inputs, not provider-native raw
measurements. This detects changes, conversion differences and witness-margin
sensitivity; it cannot establish upstream instrument accuracy or data rights.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/audit'
ARCH=ROOT/'results/wrr_review_completion_20261024/observed_records'
EPS=5e-6


def compare_daily(source,canonical):
    a=np.asarray(source,float);b=np.asarray(canonical,float)
    if a.shape!=b.shape:raise ValueError('daily arrays have different sizes')
    present=np.isfinite(a);other=np.isfinite(b)
    missing_mismatch=int(np.sum(present!=other))
    common=present&other
    rounding=float(np.max(abs(a[common]-b[common]))) if common.any() else 0.
    cast_mismatch=int(np.sum(a[common].astype(np.float32).astype(float)!=b[common]))
    return missing_mismatch,rounding,cast_mismatch,int(common.sum())


def max_window(values):
    x=np.asarray(values,float);good=np.isfinite(x)
    count=np.convolve(good.astype(int),np.ones(30,dtype=int),'valid')
    values=np.convolve(np.where(good,x,0),np.ones(30)/30,'valid')
    return float(np.max(values[count==30])) if np.any(count==30) else np.nan


def audit():
    years=pd.read_parquet(ROOT/'results/wrr_target_recovery_20261021/e1_archive/station_years.parquet')
    years=years.loc[~years.edge_year&years.fully_active&years.year.between(1981,2025)].copy()
    n=years.loc[years.complete_year&years.truth_h30.notna()].groupby('station_key').size()
    eligible=n.index[n.ge(15)].tolist();years=years.loc[years.station_key.isin(eligible)].copy()
    if years.duplicated(['station_key','year']).any():raise ValueError('duplicate station years')
    roster=T.roster().drop_duplicates('station_key').set_index('station_key')
    if not set(eligible).issubset(roster.index):raise ValueError('eligible station missing from source roster')
    base=years.drop_duplicates('station_key').set_index('station_key')
    if any(str(base.loc[k,'network_id'])!=str(roster.loc[k,'network_id']) for k in eligible):raise ValueError('current source panel identity differs from archive metadata')
    daily=pd.read_parquet(ROOT/'scratch/wrr_target_recovery_20261021/archive_daily.parquet',
                          columns=['station_key','date','water_c'],filters=[('station_key','in',eligible)])
    if daily.duplicated(['station_key','date']).any():raise ValueError('duplicate canonical station-date')
    canonical={k:g.set_index('date').water_c for k,g in daily.groupby('station_key',observed=True)}
    groups={}
    for station in eligible:
        r=roster.loc[station];path=Path(r.input_path)
        groups.setdefault(path,[]).append((station,str(r.station_id)))
    panels={}
    for path,entries in groups.items():
        wanted={sid for _,sid in entries}
        f=pd.read_csv(path,usecols=lambda x:x=='date' or x in wanted,parse_dates=['date']).set_index('date').sort_index()
        if f.index.duplicated().any() or set(f.columns)!=wanted:raise ValueError(f'input panel malformed: {path}')
        for station,sid in entries:panels[station]=pd.to_numeric(f[sid],errors='coerce')
    source_bounds=[];complete_total=0;compared_days=0;max_rounding=0.;missing_diff=0;cast_diff=0;max_complete_ref_diff=0.
    for station,block in years.groupby('station_key'):
        source=panels[station];archive=canonical[station];refs=[];incomplete=[]
        for r in block.itertuples(index=False):
            idx=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31');a=source.reindex(idx).to_numpy(float);b=archive.reindex(idx).to_numpy(float)
            miss,rounding,cast,n_good=compare_daily(a,b)
            missing_diff+=miss;cast_diff+=cast;compared_days+=n_good;max_rounding=max(max_rounding,rounding)
            if miss or cast:raise ValueError(f'canonical archive differs from float32-cast panel: {station}/{r.year}')
            bound=max_window(a)
            if r.complete_year:
                if not np.isfinite(a).all():raise ValueError('missing source on complete year')
                max_complete_ref_diff=max(max_complete_ref_diff,abs(bound-r.truth_h30));refs.append(bound);complete_total+=1
            elif not np.isfinite(a).all() and np.isfinite(bound):incomplete.append((int(r.year),bound))
        if len(refs)<15:raise ValueError('too few reference years')
        ref=max(refs)
        source_bounds.extend(dict(station_key=station,year=year,bound=bound,reference=ref,margin=bound-ref) for year,bound in incomplete)
    computed=pd.DataFrame(source_bounds)
    stored=pd.read_csv(ARCH/'all_incomplete_year_bounds.csv')
    join=computed.merge(stored,on=['station_key','year'],suffixes=('_source','_archive'),how='outer',indicator=True,validate='one_to_one')
    if not join._merge.eq('both').all():raise ValueError('source and archived incomplete-year sets differ')
    max_margin=float(np.max(abs(join.margin_source-join.margin_archive))) if len(join) else 0.
    if max_margin>EPS or max_complete_ref_diff>EPS:raise ValueError('full-precision record differs beyond tolerance')
    declared=set(zip(pd.read_csv(ARCH/'observed_record_certificates.csv').station_key,
                     pd.read_csv(ARCH/'observed_record_certificates.csv').incomplete_year.astype(int)))
    observed=set(zip(computed.loc[computed.margin.gt(EPS),'station_key'],computed.loc[computed.margin.gt(EPS),'year']))
    if declared!=observed:raise ValueError('full-precision source changes witness identities')
    base_05=join.margin_archive.gt(.5);source_05=join.margin_source.gt(.5)
    return {'eligible_stations':len(eligible),'input_panel_files':len(groups),'station_years_checked':len(years),
            'complete_reference_years':complete_total,'incomplete_years_checked':len(computed),
            'finite_daily_values_compared':compared_days,'missingness_disagreements':missing_diff,
            'float32_cast_disagreements':cast_diff,'maximum_float32_rounding_c':max_rounding,
            'maximum_complete_h30_difference_c':max_complete_ref_diff,'maximum_record_margin_difference_c':max_margin,
            'witness_count':len(observed),'witness_identity_changes':0,
            'half_c_margin_classification_changes':int((base_05!=source_05).sum()),
            'tolerance_c':EPS,'passed':True,
            'scope':'selected local processed daily CSV panels compared with canonical float32 archive for 96 eligible stations; not provider-native instrument records',
            'limitations':'recomputes reported series only; no sensor uncertainty, independent external validation, or downstream model fitting assessed'}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    try:result=audit()
    except Exception as exc:result={'passed':False,'error':f'{type(exc).__name__}: {exc}'}
    (OUT/'input_panel_precision_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
