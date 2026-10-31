#!/usr/bin/env python3
"""Compare complete-year annual vs July--August reported 30-day maxima.

This diagnostic is not a reproduction of Beaufort et al.'s interannual
climate-corrected workflow, and does not validate physical sensor accuracy.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
SNAPSHOT=REV/'open_observed_record_snapshot'
OUT=REV/'summer_window_comparison'
TOL=5e-6

def max_window(values):
    v=np.asarray(values,dtype=float)
    if len(v)<30:return np.nan
    ok=np.isfinite(v)
    n=np.convolve(ok.astype(int),np.ones(30,dtype=int),mode='valid')
    totals=np.convolve(np.where(ok,v,0.),np.ones(30),mode='valid')
    return float(np.max(totals[n==30]/30)) if (n==30).any() else np.nan

def windows(values,dates):
    dates=pd.DatetimeIndex(dates)
    if len(values)!=len(dates):raise ValueError('Daily values and dates differ')
    summer=dates.month.isin([7,8])
    return max_window(values),max_window(np.asarray(values)[summer])

def summarize_complete(c,draws=4000):
    if c.empty or c.independence_group.isna().any():raise ValueError('No complete years or missing group')
    d=c.full_h30-c.summer_h30
    if (d < -1e-10).any():raise ValueError('Summer maximum exceeds annual maximum')
    by=c.assign(gap=d).groupby('independence_group',sort=True).gap.agg(['sum','count','mean'])
    rng=np.random.default_rng(705);ix=rng.integers(len(by),size=(draws,len(by)))
    boot=by['sum'].to_numpy()[ix].sum(axis=1)/by['count'].to_numpy()[ix].sum(axis=1)
    station=c.assign(gap=d).groupby(['station_key','independence_group'],sort=True).gap.agg(['mean','count']).reset_index()
    result={'complete_station_years':len(c),'stations':c.station_key.nunique(),'connected_groups':len(by),
            'different_above_tolerance_years':int(d.gt(TOL).sum()),
            'different_above_tolerance_stations':c.loc[d.gt(TOL),'station_key'].nunique(),
            'different_above_tolerance_groups':c.loc[d.gt(TOL),'independence_group'].nunique(),
            'above_0p1_c_years':int(d.gt(.1).sum()),'above_0p1_c_stations':c.loc[d.gt(.1),'station_key'].nunique(),
            'above_0p5_c_years':int(d.gt(.5).sum()),'above_0p5_c_stations':c.loc[d.gt(.5),'station_key'].nunique(),
            'mean_gap_c':float(d.mean()),'median_gap_c':float(d.median()),'max_gap_c':float(d.max()),
            'equal_group_mean_gap_c':float(by['mean'].mean()),
            'group_bootstrap_low_c':float(np.quantile(boot,.025)),'group_bootstrap_high_c':float(np.quantile(boot,.975)),
            'stations_mean_gap_above_0p1_c':int(station['mean'].gt(.1).sum()),
            'stations_mean_gap_above_0p5_c':int(station['mean'].gt(.5).sum())}
    return result,station

def screening_counts(years,groups):
    frame=years.merge(groups,on='station_key',how='left',validate='many_to_one')
    if frame.independence_group.isna().any():raise ValueError('Missing station group')
    def numeric_rule(column,threshold):
        value=pd.to_numeric(frame[column],errors='coerce')
        return value.notna().to_numpy(),value.ge(threshold).to_numpy()
    def boolean_rule(column):
        values=frame[column]
        return values.notna().to_numpy(),values.fillna(False).astype(bool).to_numpy()
    rules={'complete_100':boolean_rule('complete_year'),'annual_95':numeric_rule('observed_fraction',.95),
           'warm_90_station_specific':numeric_rule('train_warm_fraction',.9),'july_aug_complete':boolean_rule('julaug_complete')}
    observed=np.isfinite(pd.to_numeric(frame.reported_window,errors='coerce').to_numpy(float))
    rows=[]
    for name,(known,passes) in rules.items():
        excluded=known&~passes
        bound=excluded&observed
        rows.append({'rule':name,'station_years':len(frame),'known':int(known.sum()),'accepted':int((known&passes).sum()),
                     'rejected':int(excluded.sum()),'unknown':int((~known).sum()),
                     'rejected_with_observed_30day_bound':int(bound.sum()),
                     'stations_with_rejected_bound':frame.loc[bound,'station_key'].nunique(),
                     'groups_with_rejected_bound':frame.loc[bound,'independence_group'].nunique()})
    return pd.DataFrame(rows)

def run(output):
    plan=json.loads((OUT/'plan.json').read_text())
    roster=pd.read_csv(SNAPSHOT/'source_roster.csv');groups=pd.read_csv(OUT/'station_groups.csv')
    years=pd.read_parquet(SNAPSHOT/'station_years.parquet')
    if years.duplicated(['station_key','year']).any():raise ValueError('Duplicate station-year')
    complete=years[years.complete_year & years.truth_h30.notna()].merge(groups,on='station_key',validate='many_to_one').merge(roster[['station_key','provider']],on='station_key',validate='many_to_one')
    daily=pd.read_parquet(SNAPSHOT/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    if daily.duplicated(['station_key','date']).any():raise ValueError('Duplicate station-date')
    station_daily={key:g.set_index('date').water_c.sort_index() for key,g in daily.groupby('station_key',sort=False)}
    result=[]
    for r in complete.itertuples(index=False):
        index=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
        values=station_daily[r.station_key].reindex(index).to_numpy(float)
        if not np.isfinite(values).all():raise ValueError('Flagged complete year has missing values')
        full,summer=windows(values,index)
        if not np.isclose(full,r.truth_h30,atol=TOL,rtol=0):raise ValueError('Annual reference differs from snapshot')
        result.append({'station_key':r.station_key,'year':int(r.year),
                       'independence_group':r.independence_group,'provider':r.provider,
                       'full_h30':full,'summer_h30':summer,'full_minus_summer':full-summer})
    c=pd.DataFrame(result)
    summary,station=summarize_complete(c)
    witness=pd.read_csv(SNAPSHOT/'observed_record_certificates.csv');details=[]
    if len(witness)!=35 or witness.duplicated(['station_key','incomplete_year']).any():raise ValueError('Witness roster changed')
    for r in witness.itertuples(index=False):
        index=pd.date_range(f'{r.incomplete_year}-01-01',f'{r.incomplete_year}-12-31')
        values=station_daily[r.station_key].reindex(index).to_numpy(float)
        full,summer=windows(values,index)
        if not np.isclose(full,r.observed_window_mean,atol=TOL,rtol=0):raise ValueError('Witness full-year window differs')
        gap=full-summer if np.isfinite(summer) else np.nan
        if np.isfinite(gap) and gap < -1e-10:raise ValueError('Witness summer maximum exceeds full-year maximum')
        details.append({'station_key':r.station_key,'incomplete_year':int(r.incomplete_year),'group':r.group,
                        'observed_full_window':full,'observed_summer_window':summer,'full_minus_summer':gap,
                        'summer_window_available':bool(np.isfinite(summer)),
                        'observed_full_exceeds_summer':bool(gap>TOL) if np.isfinite(gap) else None})
    w=pd.DataFrame(details)
    summary.update(witness_station_years=len(w),witness_summer_window_available=int(w.summer_window_available.sum()),
                   witness_summer_window_unavailable=int((~w.summer_window_available).sum()),
                   witnesses_full_above_summer=int(w.observed_full_exceeds_summer.fillna(False).sum()),
                   witness_stations_full_above_summer=w.loc[w.observed_full_exceeds_summer.fillna(False),'station_key'].nunique(),
                   scope='95 of 96 previously eligible source stations; reported daily values, not independently verified physical measurements; summer restriction does not replicate full published climate correction')
    rules=screening_counts(pd.read_csv(SNAPSHOT/'eligible_station_years.csv'),groups)
    providers=[]
    for provider,b in c.groupby('provider',sort=True):
        gap=b.full_minus_summer
        providers.append({'provider':provider,'stations':b.station_key.nunique(),'connected_groups':b.independence_group.nunique(),
                          'complete_station_years':len(b),'years_above_tolerance':int(gap.gt(TOL).sum()),
                          'mean_gap_c':float(gap.mean()),'years_above_0p5_c':int(gap.gt(.5).sum())})
    output.mkdir(parents=True,exist_ok=True)
    c.to_csv(output/'complete_year_windows.csv',index=False)
    station.to_csv(output/'station_mean_gaps.csv',index=False)
    w.to_csv(output/'witness_comparison.csv',index=False)
    rules.to_csv(output/'screening_counts.csv',index=False)
    pd.DataFrame(providers).to_csv(output/'provider_summary.csv',index=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
    print(rules.to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT);a=p.parse_args()
    run(a.output)
