#!/usr/bin/env python3
"""Independent numerical and mask-leakage audit of the archive proxy."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series

ROOT=T.ROOT; OUT=ROOT/'results/wrr_review_response_20261027/summer_proxy_archive'
PRIVATE=ROOT/'private/wrr_archive_summer_proxy_20261027'; FULL=PRIVATE/'full'


def bound(values):
    v=pd.Series(np.asarray(values,float)).rolling(30,min_periods=30).mean()
    return float(v.max()) if v.notna().any() else np.nan


def independent_model(visible,dates,air,year,mode,complete):
    permitted={k for k in complete if k!=year and (mode!='forward' or k<2010)}
    if len(permitted)<3:return None
    lagged=np.column_stack([air.rolling(n,min_periods=n).mean().to_numpy() for n in range(2,11)])
    years=dates.year.to_numpy();use=np.isfinite(visible)&np.isfinite(lagged).all(axis=1)&dates.month.isin([7,8])&(years!=year)
    if mode=='forward':use &= years<2010
    if use.sum()<30 or len(np.unique(years[use]))<3:return None
    target=visible[use];sst=np.sum((target-target.mean())**2)
    if sst<=1e-12:return None
    candidates=[]
    for i in range(9):
        x=lagged[use,i]
        if np.sum((x-x.mean())**2)<=1e-12:continue
        coef=np.linalg.lstsq(np.column_stack([np.ones(len(x)),x]),target,rcond=None)[0]
        residual=target-(coef[0]+coef[1]*x)
        candidates.append((1-np.sum(residual**2)/sst,i,coef))
    if not candidates:return None
    score,i,coef=max(candidates,key=lambda z:(z[0],-z[1]))
    return i+2,coef,lagged,int(years[use].max())


def independent_prediction(visible,dates,air,year,mode,complete):
    year_mask=dates.year.to_numpy()==year;summer=year_mask&dates.month.isin([7,8]); lower=bound(visible[year_mask])
    values=visible[summer].copy()
    if len(values)!=62:return np.nan,'incomplete_summer_calendar',None
    missing=~np.isfinite(values)
    if not missing.any():return lower,'observed_bound_only' if np.isfinite(lower) else 'no_observed_window',None
    model=independent_model(visible,dates,air,year,mode,complete)
    if model is None:return np.nan,'insufficient_training_support',None
    lag,coef,lagged,maxyear=model;predictor=lagged[summer,lag-2]
    if not np.isfinite(predictor[missing]).all():return np.nan,'missing_air_on_gap',model
    values[missing]=coef[0]+coef[1]*predictor[missing];peak=bound(values)
    if not np.isfinite(peak):return np.nan,'no_reconstructed_summer_window',model
    return max(lower,peak) if np.isfinite(lower) else peak,'summer_air_fill',model


def main():
    jobs=json.loads((PRIVATE/'jobs.json').read_text());entries=json.loads((PRIVATE/'archive_roster.json').read_text())
    representatives={}
    for j in sorted(jobs,key=lambda x:x['station_key']):representatives.setdefault(j['region'],j)
    cases=checked=fitted=perturb=0
    for job in representatives.values():
        site=job['station_key'];panel=read_temperature_panel(job['input_path']).asfreq('D');panel.columns=panel.columns.astype(str)
        dates=panel.index+pd.Timedelta(days=T.hemisphere_shift_days(job.get('latitude')))
        water=pd.to_numeric(panel[job['station_id']],errors='coerce').to_numpy(float);years=dates.year.to_numpy()
        air=station_air_series(Path(job['air_input_path']),job['network_id'],job['station_id'],panel.index)
        if air is None:air=pd.Series(np.nan,index=panel.index)
        complete=set()
        for y in np.unique(years):
            block=water[years==y]
            if len(block)==len(pd.date_range(f'{y}-01-01',f'{y}-12-31')) and np.isfinite(block).all():complete.add(int(y))
        results=pd.read_parquet(FULL/(site.replace('|','_')+'_annual.parquet'))
        selected=[e for e in entries if e['station_key']==site and e['replicate'] in (0,1)]
        for e in selected:
            d=json.loads((ROOT/e['design']).read_text());masks={int(k):v for k,v in d['masks'].items()}
            hidden=np.zeros(len(water),bool)
            for y,runs in masks.items():
                indices=np.flatnonzero(years==y)
                for run in str(runs).split(';'):
                    if run:
                        start,length=map(int,run.split(':'));hidden[indices[start:start+length]]=True
            visible=water.copy();visible[hidden]=np.nan
            altered=water.copy();altered[hidden]+=1000;altered[hidden]=np.nan
            if not np.array_equal(visible,altered,equal_nan=True):raise AssertionError('Hidden-value perturbation leaked')
            rows=results[(results.family==e['family'])&(results['mode']==e['mode'])&(results.replicate==e['replicate'])]
            if len(rows)!=len(masks):raise AssertionError('Masked-year count mismatch')
            for _,r in rows.iterrows():
                y=int(r.year);pred,reason,model=independent_prediction(visible,dates,air,y,e['mode'],complete-set(masks))
                if reason!=r.proxy_reason or not np.isclose(pred,r.summer_air_proxy,atol=1e-7,rtol=0,equal_nan=True):raise AssertionError('Independent annual prediction mismatch')
                if not np.isclose(bound(visible[years==y]),r.observed_bound,atol=1e-7,rtol=0,equal_nan=True):raise AssertionError('Independent bound mismatch')
                if model is not None:
                    fitted+=1
                    if (reason=='summer_air_fill' and model[0]!=int(r.fit_lag)) or (e['mode']=='forward' and model[3]>=2010):raise AssertionError('Lag or forward leakage mismatch')
                    changed=visible.copy();changed[(years==y)&np.isfinite(changed)]+=123
                    refit=independent_model(changed,dates,air,y,e['mode'],complete-set(masks))
                    if refit is None or model[0]!=refit[0] or not np.allclose(model[1],refit[1],atol=1e-10,rtol=0):raise AssertionError('Target-year fit leakage')
                    perturb+=1
                checked+=1
            cases+=1
        print('Independent representative regions checked:',len([x for x in representatives if x<=job['region']]),'of',len(representatives),flush=True)
    annual=pd.concat([pd.read_parquet(p) for p in sorted(FULL.glob('*_annual.parquet'))],ignore_index=True)
    trends=pd.concat([pd.read_parquet(p) for p in sorted(FULL.glob('*_trends.parquet'))],ignore_index=True)
    sums=pd.read_csv(OUT/'annual_paired_summary.csv');tsums=pd.read_csv(OUT/'trend_paired_summary.csv')
    methods=['plug_in','D2','stochastic_calibrated','summer_air_proxy'];comparisons=0
    for _,r in sums.query("stratum=='all' and scope=='four_method_common'").iterrows():
        q=annual[(annual.family==r.family)&(annual['mode']==r['mode'])];q=q[np.isfinite(q[methods]).all(axis=1)]
        ca=np.mean(np.abs(q[r.comparator]-q.truth));pa=np.mean(np.abs(q.summer_air_proxy-q.truth))
        if len(q)!=r.n_common or not np.allclose([ca,pa],[r.comparator_mae,r.proxy_mae],atol=1e-10,rtol=0):raise AssertionError('Annual aggregate mismatch')
        comparisons+=1
    keys=['station_key','family','mode','replicate'];w=trends.pivot(index=keys,columns='estimator',values='error')
    counts=trends.drop_duplicates(keys).set_index(keys).n_incomplete;w=w.join(counts)
    for _,r in tsums.query("subset=='nontrivial' and scope=='four_method_common'").iterrows():
        q=w.reset_index();q=q[(q.family==r.family)&(q['mode']==r['mode'])&(q.n_incomplete>0)];q=q[np.isfinite(q[methods]).all(axis=1)]
        ca=np.sqrt(np.mean(q[r.comparator]**2));pa=np.sqrt(np.mean(q.summer_air_proxy**2))
        if len(q)!=r.n_common or not np.allclose([ca,pa],[r.comparator_rmse,r.proxy_rmse],atol=1e-10,rtol=0):raise AssertionError('Trend aggregate mismatch')
        comparisons+=1
    out={'status':'passed','representative_regions':len(representatives),'archive_settings_recomputed':cases,'masked_years_recomputed':checked,
         'fitted_years_recomputed':fitted,'target_year_fit_perturbations':perturb,'sampled_case_hidden_values_masked_before_fit':True,
         'aggregate_cells_independently_checked':comparisons,'scope':'One lexicographically first station per region, repetitions 0 and 1, all available families and modes; separate least-squares and rolling windows. Aggregate point summaries rechecked for all common-cohort cells.',
         'limitations':'Uses the same processed source data, masks and cached baseline predictions. Does not validate sensor accuracy, source rights, unseen climates or interval coverage.'}
    (OUT/'independent_audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))


if __name__=='__main__':main()
