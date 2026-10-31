#!/usr/bin/env python3
"""Train-only summer air-regression proxy inspired by Beaufort et al. (2022).

The primary target is a nine-year summer peak mean, not yearly H30 or trend.
The study is post-hoc, uses different source data and is not a paper replication.
"""
from __future__ import annotations
import itertools
import json
import math
import os
from pathlib import Path
import numpy as np
import pandas as pd

os.umask(0o077)
ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'beaufort_proxy';PRIVATE=ROOT/'private/wrr_beaufort_proxy_20261027';SNAP=REV/'open_observed_record_snapshot'
YEARS=np.arange(2009,2018);LAGS=np.arange(2,11);TOL=5e-6

def summer_peak(values):
    x=np.asarray(values,dtype=float)
    if x.shape!=(62,) or not np.isfinite(x).all():return np.nan
    return float(np.max(np.convolve(x,np.ones(30)/30,mode='valid')))

def lagged_air(air):
    """Nine June22--August31 series to 2--10-day right-aligned summer means."""
    a=np.asarray(air,float)
    if a.shape!=(9,71):raise ValueError('Expected nine complete 71-day air blocks')
    out=np.empty((9,len(LAGS),62),float)
    for i in range(9):
        for j,lag in enumerate(LAGS):
            out[i,j]=np.convolve(a[i],np.ones(lag)/lag,mode='valid')[10-lag:72-lag]
    return out

def fit_and_estimate(water,air,hidden):
    """Select lag and fit only retained years; hidden water is never accessed."""
    w=np.asarray(water,float);a=np.asarray(air,float);hidden=np.asarray(hidden,bool)
    if w.shape!=(9,62) or a.shape!=(9,9,62) or hidden.shape!=(9,):raise ValueError('Unexpected model dimensions')
    if not hidden.any() or hidden.all():return None
    keep=~hidden;yy=w[keep].reshape(-1)
    if not np.isfinite(yy).all() or not np.isfinite(a).all():return None
    centered_y=yy-yy.mean();syy=float(centered_y@centered_y)
    if syy<=0:return None
    fits=[]
    for j,lag in enumerate(LAGS):
        xx=a[keep,j,:].reshape(-1);centered_x=xx-xx.mean();sxx=float(centered_x@centered_x)
        if sxx<=0:continue
        sxy=float(centered_x@centered_y);slope=sxy/sxx;intercept=float(yy.mean()-slope*xx.mean())
        fits.append((float((sxy*sxy)/(sxx*syy)),int(lag),intercept,float(slope),j))
    if not fits:return None
    best=max(fits,key=lambda v:(v[0],-v[1]));r2,lag,intercept,slope,j=best
    pred=[summer_peak(intercept+slope*a[i,j]) for i in np.flatnonzero(hidden)]
    visible=[summer_peak(w[i]) for i in np.flatnonzero(keep)]
    if not np.isfinite(pred+visible).all():return None
    return {'lag':lag,'train_days':len(yy),'training_r2':r2,
            'observed_mean':float(np.mean(visible)),'filled_mean':float((sum(visible)+sum(pred))/9)}

def summarize(cases,roster):
    rows=[];regional=[]
    for k in range(1,9):
        for target in ['summer','calendar']:
            c=cases[cases.missing_years.eq(k)].copy();truth=c['target_'+target]
            c['obs_error']=c.observed_mean-truth;c['fill_error']=c.filled_mean-truth
            c['obs_abs']=abs(c.obs_error);c['fill_abs']=abs(c.fill_error);c['difference']=c.fill_abs-c.obs_abs
            site=c.groupby(['station_key','independence_group','provider'],as_index=False).agg(
                obs_abs=('obs_abs','mean'),fill_abs=('fill_abs','mean'),difference=('difference','mean'),
                obs_bias=('obs_error','mean'),fill_bias=('fill_error','mean'),
                obs_sq=('obs_error',lambda x:float(np.mean(x*x))),fill_sq=('fill_error',lambda x:float(np.mean(x*x))))
            by=site.groupby('independence_group').difference.agg(['sum','count','mean'])
            rng=np.random.default_rng(75900+100*k+(target=='calendar'))
            draws=rng.integers(len(by),size=(4000,len(by))) if len(by) else np.empty((0,0),int)
            boot=by['sum'].to_numpy()[draws].sum(axis=1)/by['count'].to_numpy()[draws].sum(axis=1) if len(by) else np.array([])
            rows.append({'missing_years':k,'target':target,'n_expected':len(roster)*math.comb(9,k),'n_available':len(c),
                'stations':len(site),'groups':len(by),'observed_mae':float(site.obs_abs.mean()) if len(site) else np.nan,
                'filled_mae':float(site.fill_abs.mean()) if len(site) else np.nan,
                'observed_bias':float(site.obs_bias.mean()) if len(site) else np.nan,'filled_bias':float(site.fill_bias.mean()) if len(site) else np.nan,
                'observed_rmse':float(np.sqrt(site.obs_sq.mean())) if len(site) else np.nan,'filled_rmse':float(np.sqrt(site.fill_sq.mean())) if len(site) else np.nan,
                'mean_abs_error_difference':float(site.difference.mean()) if len(site) else np.nan,
                'equal_group_abs_error_difference':float(by['mean'].mean()) if len(by) else np.nan,
                'bootstrap_low':float(np.quantile(boot,.025)) if len(boot) else np.nan,
                'bootstrap_high':float(np.quantile(boot,.975)) if len(boot) else np.nan,
                'filled_better_cases':int(c.difference.lt(-1e-10).sum()),'observed_better_cases':int(c.difference.gt(1e-10).sum()),
                'ties':int(c.difference.abs().le(1e-10).sum())})
            for provider in sorted(site.provider.unique()):
                q=site[site.provider.ne(provider)]
                regional.append({'missing_years':k,'target':target,'removed_provider':provider,'stations':len(q),
                                 'groups':q.independence_group.nunique(),
                                 'observed_mae':float(q.obs_abs.mean()) if len(q) else np.nan,
                                 'filled_mae':float(q.fill_abs.mean()) if len(q) else np.nan,
                                 'mean_abs_error_difference':float(q.difference.mean()) if len(q) else np.nan})
    return pd.DataFrame(rows),pd.DataFrame(regional)

def main():
    plan=json.loads((OUT/'plan.json').read_text())
    snapshot=json.loads((OUT/'air_snapshot_status.json').read_text())
    roster=pd.read_csv(OUT/'roster.csv',dtype={'station_id':str,'network_id':str});air=pd.read_parquet(OUT/'air_snapshot.parquet')
    water=pd.read_parquet(SNAP/'daily_temperature.parquet');water['date']=pd.to_datetime(water.date);air['date']=pd.to_datetime(air.date)
    references=pd.read_csv(REV/'summer_window_comparison/complete_year_windows.csv');availability=pd.read_csv(OUT/'air_availability.csv').set_index('station_key')
    if water.duplicated(['station_key','date']).any() or air.duplicated(['station_key','date']).any():raise ValueError('Duplicate processed daily source')
    cases=[];unavailable=[]
    for site in roster.itertuples(index=False):
        if not bool(availability.loc[site.station_key,'complete_for_lags']):
            unavailable.append({'station_key':site.station_key,'reason':'air_incomplete'});continue
        water_daily=water[water.station_key.eq(site.station_key)].set_index('date').water_c
        air_daily=air[air.station_key.eq(site.station_key)].set_index('date').air_temperature_c
        w=[];a=[];annual=[]
        for year in YEARS:
            summer=pd.date_range(f'{year}-07-01',f'{year}-08-31');air_index=pd.date_range(f'{year}-06-22',f'{year}-08-31')
            w.append(water_daily.reindex(summer).to_numpy(float));a.append(air_daily.reindex(air_index).to_numpy(float))
            full=pd.date_range(f'{year}-01-01',f'{year}-12-31');values=water_daily.reindex(full).to_numpy(float)
            if not np.isfinite(values).all():raise ValueError('Planned reference year is incomplete')
            annual.append(float(np.max(np.convolve(values,np.ones(30)/30,mode='valid'))))
            row=references[references.station_key.eq(site.station_key)&references.year.eq(year)]
            if len(row)!=1 or not np.isclose(annual[-1],row.iloc[0].full_h30,rtol=0,atol=TOL) or not np.isclose(summer_peak(w[-1]),row.iloc[0].summer_h30,rtol=0,atol=TOL):
                raise ValueError('Computed annual or summer reference differs from earlier source')
        w=np.asarray(w);predictors=lagged_air(np.asarray(a));target_summer=float(np.mean([summer_peak(v) for v in w]));target_calendar=float(np.mean(annual))
        for k in range(1,9):
            for missing in itertools.combinations(range(9),k):
                hidden=np.zeros(9,dtype=bool);hidden[list(missing)]=True
                result=fit_and_estimate(w,predictors,hidden)
                if result is None:
                    unavailable.append({'station_key':site.station_key,'reason':'fit_unavailable','mask_bits':sum(1<<x for x in missing)});continue
                cases.append({'station_key':site.station_key,'independence_group':site.independence_group,'provider':site.provider,
                    'missing_years':k,'mask_bits':sum(1<<x for x in missing),'target_summer':target_summer,'target_calendar':target_calendar,**result})
        print('Completed station',site.provider,flush=True)
    data=pd.DataFrame(cases)
    if data.empty or data.duplicated(['station_key','mask_bits']).any():raise ValueError('No valid cases or duplicated masks')
    target=PRIVATE/'cases.parquet'
    if target.exists():pd.testing.assert_frame_equal(pd.read_parquet(target),data,check_dtype=False,atol=1e-10,rtol=0)
    else:data.to_parquet(target,index=False);target.chmod(0o600)
    summary,regional=summarize(data,roster)
    summary.to_csv(OUT/'summary.csv',index=False);regional.to_csv(OUT/'leave_provider_out.csv',index=False)
    reasons=pd.DataFrame(unavailable)
    report={'status':'computed_posthoc','planned_stations':len(roster),'planned_groups':int(roster.independence_group.nunique()),
            'station_case_rows':len(data),'available_stations':int(data.station_key.nunique()),'unavailable_records':len(unavailable),
            'unavailable_reasons':reasons.reason.value_counts().to_dict() if len(reasons) else {},
            'all_nine_years_missing':'unsupported_no_visible_training_data',
            'privacy':'per-station mask and result records remain local private',
            'limitations':plan['limitations']}
    (OUT/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(summary.query("target == 'summer'").to_string(index=False),flush=True)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
