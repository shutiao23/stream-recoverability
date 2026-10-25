#!/usr/bin/env python3
"""Same-roster, same-span regional trends and hottest-year ranking sensitivity.

All new numbers are exploratory on the already opened archive. Bootstrap plus
imputation frequencies describe this finite panel, not an independently
verified change in river warming or calibrated probability of a hottest year.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]


def slope(matrix,years):
    x=(np.asarray(years)-2000)/10;good=np.isfinite(matrix);n=good.sum(axis=0);y=np.where(good,matrix,0)
    sx=(good*x[:,None]).sum(axis=0);sy=y.sum(axis=0);xx=(good*x[:,None]**2).sum(axis=0)-sx*sx/np.maximum(n,1)
    xy=(y*x[:,None]).sum(axis=0)-sx*sy/np.maximum(n,1)
    return np.divide(xy,xx,out=np.full_like(xx,np.nan),where=(n>=15)&(xx>0))


def analyse_region(label,panel,real,draws,seed):
    panel=panel.loc[panel.year.between(1981,2025)].copy()
    complete=panel.loc[panel.complete_year&panel.truth_h30.notna()]
    roster=complete.groupby("station_key").agg(n=("year","nunique"),first=("year","min"),last=("year","max"))
    roster=roster.loc[roster.n.ge(15)]
    if len(roster)<5:return [],[],dict(region=label,status="fewer_than_five_complete-qualified_stations",n_stations=len(roster))
    panel=panel.loc[panel.station_key.isin(roster.index)].copy()
    panel=panel.loc[(panel.year>=panel.station_key.map(roster["first"]))&(panel.year<=panel.station_key.map(roster["last"]))]
    sites=sorted(roster.index);years=np.arange(int(panel.year.min()),int(panel.year.max())+1)
    C=panel.assign(value=panel.truth_h30.where(panel.complete_year)).pivot(index="year",columns="station_key",values="value").reindex(index=years,columns=sites).to_numpy()
    R=panel.pivot(index="year",columns="station_key",values="retained_estimate").reindex(index=years,columns=sites).to_numpy()
    cg=panel.drop_duplicates("station_key").set_index("station_key").independence_group.reindex(sites)
    groups=np.array(sorted(cg.unique()));columns=[np.flatnonzero(cg.to_numpy()==g) for g in groups]
    center=np.nanmean(C,axis=0);q90=np.nanquantile(C,.9,axis=0)
    c_slope=slope(C,years);r_slope=slope(R,years)
    ensemble=np.repeat(R[None,:,:],20,axis=0)
    index_year={y:i for i,y in enumerate(years)};index_site={s:i for i,s in enumerate(sites)}
    for row in real.loc[real.station_key.isin(sites)].itertuples():
        if row.year in index_year:
            j=index_site[row.station_key];i=index_year[row.year]
            if np.isfinite(R[i,j]) and not np.isfinite(C[i,j]):
                ensemble[:,i,j]=np.asarray(row.revised_draws,float)
    nC=np.isfinite(C).sum(axis=1);nR=np.isfinite(R).sum(axis=1)
    eligibleC=nC>=np.ceil(.8*len(sites));eligibleR=nR>=np.ceil(.8*len(sites));common=eligibleC&eligibleR
    with np.errstate(invalid="ignore"):
        meanC=np.nanmean(C-center,axis=1);meanR=np.nanmean(R-center,axis=1)
        hotC=np.divide(np.sum((C>q90)&np.isfinite(C),axis=1),nC,out=np.full(len(years),np.nan),where=nC>0)
        hotR=np.divide(np.sum((R>q90)&np.isfinite(R),axis=1),nR,out=np.full(len(years),np.nan),where=nR>0)
    annual=pd.DataFrame(dict(region=label,year=years,n_stations=len(sites),n_groups=len(groups),n_complete=nC,n_retained=nR,mean_anomaly_complete=meanC,mean_anomaly_retained=meanR,hot_fraction_complete=hotC,hot_fraction_retained=hotR,
                             complete_80pct_roster_supported=eligibleC,retained_80pct_roster_supported=eligibleR,common_year=common))
    for name,values,keep in [("complete",meanC,eligibleC),("retained",meanR,eligibleR),("complete_common",meanC,common),("retained_common",meanR,common)]:
        annual["rank_"+name]=pd.Series(np.where(keep,values,np.nan)).rank(ascending=False,method="min")
    def top(values,keep):
        return int(years[np.argmax(np.where(keep,values,-np.inf))]) if keep.any() else None
    summary=dict(region=label,status="computed",n_stations=len(sites),n_groups=len(groups),window="1981-2025; each station restricted to its first-last complete year for both policies",common_years=int(common.sum()),
                 n_years_complete=int(eligibleC.sum()),n_years_retained=int(eligibleR.sum()),
                 top_complete=top(meanC,eligibleC),top_retained=top(meanR,eligibleR),top_complete_common=top(meanC,common),top_retained_common=top(meanR,common),
                 median_slope_complete=float(np.nanmedian(c_slope)),median_slope_retained=float(np.nanmedian(r_slope)),
                 difference_of_regional_medians=float(np.nanmedian(r_slope)-np.nanmedian(c_slope)),
                 median_paired_station_difference=float(np.nanmedian(r_slope-c_slope)))
    rng=np.random.default_rng(seed);differences=[];top_counts={"complete":np.zeros(len(years),int),"retained":np.zeros(len(years),int)}
    if len(groups)>=3:
        for _ in range(draws):
            chosen=rng.integers(0,len(groups),len(groups));idx=np.concatenate([columns[g] for g in chosen])
            imputation=rng.integers(0,20,R.shape);sample=ensemble[imputation,np.arange(len(years))[:,None],np.arange(len(sites))[None,:]]
            differences.append(float(np.nanmedian(slope(sample[:,idx],years))-np.nanmedian(c_slope[idx])))
            for method,matrix,eligible in [("complete",C,eligibleC),("retained",sample,eligibleR)]:
                values=np.nanmean(matrix[:,idx]-center[idx],axis=1);keep=eligible&np.isfinite(values)
                if keep.any():top_counts[method][np.argmax(np.where(keep,values,-np.inf))]+=1
        summary.update(contrast_group_bootstrap_lower=float(np.nanquantile(differences,.025)),contrast_group_bootstrap_upper=float(np.nanquantile(differences,.975)))
    else:summary.update(contrast_group_bootstrap_lower=np.nan,contrast_group_bootstrap_upper=np.nan)
    rankings=[]
    for method,count in top_counts.items():
        for i,n in enumerate(count):
            if n:rankings.append(dict(region=label,method=method,year=int(years[i]),bootstrap_top_frequency=n/count.sum(),n_valid_bootstrap=int(count.sum()),n_groups=len(groups),interpretation="fixed-panel group-composition and independent-year imputation sensitivity; not a calibrated hottest-year probability"))
    return annual.to_dict("records"),rankings,summary


def main():
    p=argparse.ArgumentParser();p.add_argument("--draws",type=int,default=2000);a=p.parse_args()
    source=T.load_script("r4_rank_meaning",T.ROOT/"scripts/471_review_completion_meaning.py")
    real=pd.read_parquet(OUT/"meaning/real_deliveries.parquet");panel=source.annual_panel(real)
    maps=pd.read_parquet(OUT/"cases/leave_one_year_out/seed_00.parquet",columns=["station_key","region"]).drop_duplicates()
    assert maps.groupby("station_key").region.nunique().le(1).all()
    panel["region"]=panel.station_key.map(maps.set_index("station_key").region)
    collections={"provider:"+str(name):b for name,b in panel.groupby("provider")}
    collections.update({"region:"+str(name):b for name,b in panel.loc[panel.provider.eq("usgs")].groupby("region")})
    annual=[];ranks=[];summaries=[]
    for i,(name,b) in enumerate(sorted(collections.items())):
        ar,ra,s=analyse_region(name,b,real,a.draws,plain_seed(89,i));annual.extend(ar);ranks.extend(ra);summaries.append(s)
    dest=OUT/"regional_rankings";dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(annual).to_csv(dest/"same_roster_annual_rankings.csv",index=False)
    pd.DataFrame(ranks).to_csv(dest/"hottest_year_bootstrap_frequency.csv",index=False)
    pd.DataFrame(summaries).to_csv(dest/"same_roster_same_span_summary.csv",index=False)
    T.write_json(dest/"design.json",{"source":"already opened archive only","roster":">=15 complete observed years in 1981-2025; identical stations under both policies","period":"each station's first through last complete year, identically for both policies","regional_annual_mean":"equal-station anomaly relative to that station's complete-year mean; require >=80% fixed-roster support","rankings":"method-eligible year sets and common eligible years reported separately","uncertainty":"connected-group bootstrap, independently selecting one of 20 stored imputations per station-year; no imputation before complete-year edges; does not model cross-station missing-error dependence or all estimator-training variation","caveat":"panel sensitivity; estimated incomplete-year H30 lacks natural-gap truth and hot-year calibration may fail; no confirmed new physical trend"})
    print(pd.DataFrame(summaries).loc[lambda d:d.status.eq("computed")].to_string(index=False),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
