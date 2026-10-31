#!/usr/bin/env python3
"""Aggregate the post-hoc, private archive proxy comparison."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/summer_proxy_archive'
PRIVATE=ROOT/'private/wrr_archive_summer_proxy_20261027/full'
METHODS=['plug_in','D2','stochastic_calibrated','summer_air_proxy']

def paired_stats(frame, comparator, target, kind, seed):
    eligible=len(frame)
    a=pd.to_numeric(frame[comparator],errors='coerce').to_numpy(float)
    b=pd.to_numeric(frame[target],errors='coerce').to_numpy(float)
    truth=pd.to_numeric(frame.truth,errors='coerce').to_numpy(float)
    va=np.isfinite(a)&np.isfinite(truth);vb=np.isfinite(b)&np.isfinite(truth);ok=va&vb
    row={'n_eligible':eligible,'n_comparator_available':int(va.sum()),'n_proxy_available':int(vb.sum()),'n_common':int(ok.sum())}
    if not ok.any():return row
    f=frame.loc[ok]; ea=a[ok]-truth[ok];eb=b[ok]-truth[ok]
    diff=np.abs(eb)-np.abs(ea) if kind=='annual' else eb**2-ea**2
    groups=pd.DataFrame({'group':f.independence_group.to_numpy(),'d':diff}).groupby('group',sort=True).d.agg(['sum','count','mean'])
    rng=np.random.default_rng(seed); idx=rng.integers(0,len(groups),size=(4000,len(groups)))
    boot=groups['sum'].to_numpy()[idx].sum(axis=1)/groups['count'].to_numpy()[idx].sum(axis=1)
    row.update({'n_stations':int(f.station_key.nunique()),'n_groups':len(groups),
                'mean_paired_difference':float(diff.mean()),'equal_group_difference':float(groups['mean'].mean()),
                'bootstrap_low':float(np.quantile(boot,.025)),'bootstrap_high':float(np.quantile(boot,.975)),
                'comparator_bias':float(ea.mean()),'proxy_bias':float(eb.mean())})
    if kind=='annual':
        row.update({'n_station_years':int(f[['station_key','year']].drop_duplicates().shape[0]),
                    'comparator_mae':float(np.abs(ea).mean()),'proxy_mae':float(np.abs(eb).mean()),
                    'comparator_failure_gt_0_5':float((np.abs(ea)>.5).mean()),'proxy_failure_gt_0_5':float((np.abs(eb)>.5).mean())})
    else:row.update({'comparator_rmse':float(np.sqrt(np.mean(ea**2))),'proxy_rmse':float(np.sqrt(np.mean(eb**2)))})
    return row

def main():
    plan=json.loads((OUT/'analysis_plan.json').read_text());execution=json.loads((OUT/'execution.json').read_text())
    if execution['status']!='completed':raise ValueError('Missing frozen plan or execution')
    annual_files=sorted(PRIVATE.glob('*_annual.parquet'));trend_files=sorted(PRIVATE.glob('*_trends.parquet'))
    if len(annual_files)!=42 or len(trend_files)!=42:raise ValueError('Missing station files')
    annual=pd.concat([pd.read_parquet(p) for p in annual_files],ignore_index=True)
    tr=pd.concat([pd.read_parquet(p) for p in trend_files],ignore_index=True)
    if len(annual)!=21446 or len(tr)!=13280:raise ValueError('Unexpected cohort size')
    key=['station_key','independence_group','region','family','mode','replicate']
    if annual.duplicated(key+['year']).any() or tr.duplicated(key+['estimator']).any():raise ValueError('Duplicate cases')
    if ((annual.truth-annual.observed_bound)<-1e-5).any():raise ValueError('Observed bound exceeds reference')
    if (annual.loc[(annual['mode']=='forward')&annual.fit_max_year.notna(),'fit_max_year']>=2010).any():raise ValueError('Future leakage')
    if ((annual[METHODS].sub(annual.observed_bound,axis=0)<-1e-8)&annual[METHODS].notna()).any().any():raise ValueError('Estimate violates bound')
    meta=tr.groupby(key,dropna=False).agg(n_years=('n_years','first'),n_incomplete=('n_incomplete','first'),truth=('truth_slope','first'))
    if tr.groupby(key,dropna=False).truth_slope.nunique().ne(1).any():raise ValueError('Truth mismatch across methods')
    wide=tr.pivot(index=key,columns='estimator',values='slope').join(meta).reset_index()
    if len(wide)!=3320 or set(METHODS)-set(wide.columns):raise ValueError('Incomplete archive methods')
    strata={'all':lambda f:np.ones(len(f),bool),
            'bound_matches_reference':lambda f:f.observed_bound.notna() & (f.truth-f.observed_bound<=1e-5),
            'reference_above_bound':lambda f:f.observed_bound.notna() & (f.truth-f.observed_bound>1e-5),
            'missing_bound':lambda f:f.observed_bound.isna()}
    annual_out=[];trend_out=[];leave=[];support=[];seed=81000
    for (family,mode),f in annual.groupby(['family','mode'],sort=True):
        for reason,g in f.groupby('proxy_reason',dropna=False):
            ok=np.isfinite(g.summer_air_proxy);same=ok&np.isfinite(g.observed_bound)&np.isclose(g.summer_air_proxy,g.observed_bound,atol=1e-8,rtol=0)
            support.append({'family':family,'mode':mode,'reason':reason,'n':len(g),'available':int(ok.sum()),'equal_bound':int(same.sum()),'n_stations':g.station_key.nunique(),'n_groups':g.independence_group.nunique()})
        for stratum,select in strata.items():
            z=f.loc[select(f)]
            for scope in ['pairwise','four_method_common']:
                q=z if scope=='pairwise' else z.loc[np.isfinite(z[METHODS]).all(axis=1)]
                for method in METHODS[:-1]:
                    seed+=1;row={'family':family,'mode':mode,'stratum':stratum,'scope':scope,'comparator':method}
                    row.update(paired_stats(q,method,'summer_air_proxy','annual',seed));annual_out.append(row)
    for (family,mode),f in wide.groupby(['family','mode'],sort=True):
        for subset in ['all','nontrivial']:
            z=f if subset=='all' else f.loc[f.n_incomplete>0]
            for scope in ['pairwise','four_method_common']:
                q=z if scope=='pairwise' else z.loc[np.isfinite(z[METHODS]).all(axis=1)]
                for method in METHODS[:-1]:
                    seed+=1;row={'family':family,'mode':mode,'subset':subset,'scope':scope,'comparator':method}
                    row.update(paired_stats(q,method,'summer_air_proxy','trend',seed));trend_out.append(row)
                    if subset=='nontrivial' and scope=='four_method_common':
                        for region in sorted(q.region.dropna().unique()):
                            seed+=1;r={'family':family,'mode':mode,'excluded_region':region,'comparator':method}
                            r.update(paired_stats(q.loc[q.region!=region],method,'summer_air_proxy','trend',seed));leave.append(r)
    for name,rows in [('annual_paired_summary.csv',annual_out),('trend_paired_summary.csv',trend_out),('proxy_support_summary.csv',support),('leave_region_out.csv',leave)]:
        pd.DataFrame(rows).to_csv(OUT/name,index=False)
    status={'status':'computed_posthoc','annual_rows':len(annual),'archive_settings':len(wide),'stations':annual.station_key.nunique(),
            'groups':annual.independence_group.nunique(),'interpretation':'Repeated synthetic masks are not independent climates. The proxy is a point-only literature-inspired adaptation; outcome-defined annual strata are retrospective. Original fixed models and source data rights remain unresolved.'}
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':main()
