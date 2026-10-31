#!/usr/bin/env python3
"""Recompute all summer-proxy cases using rolling means and least squares.

This independently reimplements arithmetic on the same processed water and
air records; it is not an independent watershed or sensor-quality validation.
"""
from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'beaufort_proxy'
PRIVATE=ROOT/'private/wrr_beaufort_proxy_20261027';SNAP=REV/'open_observed_record_snapshot'

def close(a,b,label):
    if not np.isclose(float(a),float(b),atol=1e-8,rtol=1e-10,equal_nan=True):raise ValueError('Mismatch: '+label)

def naive_fit(water,air,hidden):
    keep=[i for i in range(9) if i not in hidden];y=np.concatenate([water[i] for i in keep]);fitted=[]
    for j in range(9):
        x=np.concatenate([air[i,j] for i in keep]);design=np.column_stack([np.ones(len(x)),x])
        if np.var(x)<=0 or np.var(y)<=0:continue
        coef=np.linalg.lstsq(design,y,rcond=None)[0];resid=y-design@coef
        r2=1-float(resid@resid)/float(((y-y.mean())**2).sum())
        fitted.append((r2,j+2,coef))
    if not fitted:return None
    r2,lag,coef=max(fitted,key=lambda z:(z[0],-z[1]))
    maxima=[]
    for i in sorted(hidden):
        pred=coef[0]+coef[1]*air[i,lag-2]
        maxima.append(float(pd.Series(pred).rolling(30,min_periods=30).mean().max()))
    obs=[float(pd.Series(water[i]).rolling(30,min_periods=30).mean().max()) for i in keep]
    return lag,r2,len(y),float(np.mean(obs)),float((sum(obs)+sum(maxima))/9)

def summarize(cases,roster):
    expected=pd.read_csv(OUT/'summary.csv');leave=pd.read_csv(OUT/'leave_provider_out.csv');checked=removed=0
    for k in range(1,9):
        for target in ['summer','calendar']:
            rows=cases[cases.missing_years.eq(k)].copy();diff_obs=rows.observed_mean-rows['target_'+target];diff_fill=rows.filled_mean-rows['target_'+target]
            rows['oa']=abs(diff_obs);rows['fa']=abs(diff_fill);rows['delta']=rows.fa-rows.oa
            rows['ob']=diff_obs;rows['fb']=diff_fill;rows['os']=diff_obs**2;rows['fs']=diff_fill**2
            site=rows.groupby(['station_key','independence_group','provider'],sort=True)[['oa','fa','delta','ob','fb','os','fs']].mean().reset_index()
            q=expected[(expected.missing_years==k)&expected.target.eq(target)]
            if len(q)!=1:raise ValueError('Summary identity missing')
            q=q.iloc[0]
            if int(q.n_expected)!=len(roster)*math.comb(9,k) or int(q.n_available)!=len(rows) or int(q.stations)!=len(site):raise ValueError('Summary denominator differs')
            stats={'observed_mae':site.oa.mean(),'filled_mae':site.fa.mean(),'mean_abs_error_difference':site.delta.mean(),
                   'observed_bias':site.ob.mean(),'filled_bias':site.fb.mean(),'observed_rmse':np.sqrt(site.os.mean()),'filled_rmse':np.sqrt(site.fs.mean())}
            for key,value in stats.items():close(value,q[key],key)
            labels=sorted(site.independence_group.unique());sums=np.array([site.loc[site.independence_group.eq(g),'delta'].sum() for g in labels])
            sizes=np.array([site.independence_group.eq(g).sum() for g in labels])
            if int(q.groups)!=len(labels):raise ValueError('Group denominator differs')
            draws=np.random.default_rng(75900+100*k+(target=='calendar')).integers(len(labels),size=(4000,len(labels)))
            boot=sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)
            close((sums/sizes).mean(),q.equal_group_abs_error_difference,'equal-group difference')
            close(np.quantile(boot,.025),q.bootstrap_low,'bootstrap lower');close(np.quantile(boot,.975),q.bootstrap_high,'bootstrap upper')
            for field,value in [('filled_better_cases',rows.delta.lt(-1e-10).sum()),('observed_better_cases',rows.delta.gt(1e-10).sum()),('ties',rows.delta.abs().le(1e-10).sum())]:
                if int(q[field])!=int(value):raise ValueError('Case comparison count differs: '+field)
            for provider in sorted(site.provider.unique()):
                one=leave[(leave.missing_years==k)&leave.target.eq(target)&leave.removed_provider.eq(provider)]
                if len(one)!=1:raise ValueError('Provider sensitivity row missing')
                z=site[site.provider.ne(provider)]
                if int(one.iloc[0].stations)!=len(z):raise ValueError('Provider sensitivity denominator differs')
                close(z.oa.mean(),one.iloc[0].observed_mae,'provider observed MAE')
                close(z.fa.mean(),one.iloc[0].filled_mae,'provider filled MAE');removed+=1
            checked+=1
    if checked!=len(expected) or removed!=len(leave):raise ValueError('Unchecked summary rows')
    return checked,removed

def main():
    plan=json.loads((OUT/'plan.json').read_text());air_status=json.loads((OUT/'air_snapshot_status.json').read_text())
    saved=pd.read_parquet(PRIVATE/'cases.parquet');roster=pd.read_csv(OUT/'roster.csv')
    if saved.duplicated(['station_key','mask_bits']).any():raise ValueError('Duplicate saved cases')
    water=pd.read_parquet(SNAP/'daily_temperature.parquet');water['date']=pd.to_datetime(water.date)
    air=pd.read_parquet(OUT/'air_snapshot.parquet');air['date']=pd.to_datetime(air.date)
    recomputed=[];maxdiff=0.
    for site in roster.itertuples(index=False):
        part=saved[saved.station_key.eq(site.station_key)]
        if part.empty:continue
        w_series=water[water.station_key.eq(site.station_key)].set_index('date').water_c
        a_series=air[air.station_key.eq(site.station_key)].set_index('date').air_temperature_c
        w=[];a=[];annual=[]
        for year in range(2009,2018):
            summer=pd.date_range(f'{year}-07-01',f'{year}-08-31');indices=pd.date_range(f'{year}-06-22',f'{year}-08-31')
            w.append(w_series.reindex(summer).to_numpy(float));series=pd.Series(a_series.reindex(indices).to_numpy(float))
            a.append(np.asarray([series.rolling(lag,min_periods=lag).mean().iloc[9:].to_numpy() for lag in range(2,11)]))
            full=w_series.reindex(pd.date_range(f'{year}-01-01',f'{year}-12-31')).to_numpy(float)
            annual.append(float(pd.Series(full).rolling(30,min_periods=30).mean().max()))
        w=np.asarray(w);a=np.asarray(a);summer=float(np.mean([pd.Series(x).rolling(30,min_periods=30).mean().max() for x in w]));calendar=float(np.mean(annual))
        for item in part.itertuples(index=False):
            hidden={i for i in range(9) if int(item.mask_bits)&(1<<i)}
            if len(hidden)!=item.missing_years:raise ValueError('Mask bit count differs')
            result=naive_fit(w,a,hidden)
            if result is None:raise ValueError('Saved fitting case unavailable')
            lag,r2,n,obs,fill=result
            if lag!=item.lag or n!=item.train_days:raise ValueError('Fitted lag or sample count differs')
            for name,value in [('training_r2',r2),('observed_mean',obs),('filled_mean',fill),('target_summer',summer),('target_calendar',calendar)]:
                close(value,getattr(item,name),name);maxdiff=max(maxdiff,abs(value-getattr(item,name)))
            recomputed.append({'station_key':site.station_key,'independence_group':site.independence_group,'provider':site.provider,
                               'missing_years':item.missing_years,'target_summer':summer,'target_calendar':calendar,
                               'observed_mean':obs,'filled_mean':fill})
        print('Rechecked station',site.provider,flush=True)
    c=pd.DataFrame(recomputed)
    if len(c)!=len(saved):raise ValueError('Some saved cases not checked')
    summary,removed=summarize(c,roster)
    report={'status':'passed','source_stations_checked':int(c.station_key.nunique()),'case_masks_recomputed':len(c),
            'summary_rows_recomputed':summary,'leave_provider_rows_recomputed':removed,
            'group_resamples_per_cell':4000,'max_absolute_numeric_difference':maxdiff,
            'scope':'Independent rolling-window and ordinary least-squares implementation using the same processed air and water, year masks and station roster. It does not establish source rights, independent climate, sensor accuracy or the original authors\' precise implementation.'}
    (OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
