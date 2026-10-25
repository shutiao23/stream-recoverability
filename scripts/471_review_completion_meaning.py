#!/usr/bin/env python3
"""Archive station selection, field significance, real deliveries and hot years."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import joblib
import numpy as np
import pandas as pd
from scipy.stats import linregress,t
import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.experiments.tr_revision.statistics import quantile_samples

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]
LEVELS=np.asarray(F.QUANTILES)


def real_deliveries():
    cases=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e9_application/real_year_estimates.parquet")
    refit=T.load_script("r4_meaning_refit",T.ROOT/"scripts/466_review_completion_refit.py")
    parts=[]
    for region,b in cases.groupby("region"):
        path=OUT/"refits/leave_one_year_out/seed_00"/f"{region}.joblib"
        if not path.exists():
            raise RuntimeError(f"Missing new cross-fitted delivery model for {region}")
        bundle=joblib.load(path)
        x=F.design_matrix(b,simulation=True).reindex(columns=bundle["features"])
        point=b.h30__policy.to_numpy()
        q=np.sort(np.column_stack([m.predict(x) for m in bundle["quantile_models"]])+point[:,None],axis=1)
        group=refit.difficulty(b)
        for label in group.unique():
            if label in bundle["offsets"]:
                q[group.eq(label)]+=bundle["offsets"][label]
        q=np.sort(q,axis=1)
        out=b.copy()
        out["revised_d2"]=q[:,3]
        model=bundle["classifier"]
        out["revised_score"]=model.predict_proba(x)[:,1] if model is not None else bundle["constant_probability"]
        out["revised_individual_admit"]=out.revised_score.le(.1)
        out["revised_d2_lower90"]=q[:,0];out["revised_d2_upper90"]=q[:,-1]
        out["revised_draws"]=list(quantile_samples(q,LEVELS,20))
        parts.append(out)
    return pd.concat(parts,ignore_index=True)


def bh(pvalues,alpha=.05):
    p=np.asarray(pvalues);order=np.argsort(p)
    good=np.flatnonzero(p[order]<=alpha*np.arange(1,len(p)+1)/len(p))
    threshold=p[order[good[-1]]] if len(good) else -np.inf
    return p<=threshold


def annual_panel(real,point="revised_d2"):
    """Only complete observations or explicitly supported estimates are values."""
    years=pd.read_parquet(T.E1/"station_years.parquet")
    years=years.loc[~years.edge_year&years.fully_active].drop_duplicates(["station_key","year"]).copy()
    observed=real.set_index(["station_key","year"])
    years=years.set_index(["station_key","year"])
    years["retained_estimate"]=years.truth_h30.where(years.complete_year)
    years["plug_in"]=years.truth_h30.where(years.complete_year)
    common=years.index.intersection(observed.index)
    years.loc[common,"retained_estimate"]=observed.loc[common,point]
    years.loc[common,"plug_in"]=observed.loc[common,"h30__policy"]
    years["supported_delivery"]=years.complete_year|years.index.isin(common)
    return years.reset_index()


def field_test(year_values,group_map,draws=2000,seed=0):
    """Synchronized year permutations retain cross-station residual dependence.

    Circular shifts of the common calendar (shared by all stations) give a
    temporal-dependence sensitivity. Neither treats stations as independent.
    This tests the count of positive significant slopes under a no-trend null.
    """
    rng=np.random.default_rng(seed)
    years=np.asarray(sorted(year_values.index))
    matrix=year_values.reindex(years).to_numpy()
    def count(values):
        good=np.isfinite(values);n=good.sum(axis=0)
        yy=np.where(good,values,0);xx=years[:,None]
        sx=(good*xx).sum(axis=0);sy=yy.sum(axis=0)
        sxx=(good*xx**2).sum(axis=0)-sx**2/np.maximum(n,1)
        syy=(yy**2).sum(axis=0)-sy**2/np.maximum(n,1)
        sxy=(xx*yy).sum(axis=0)-sx*sy/np.maximum(n,1)
        r=np.clip(sxy/np.sqrt(np.maximum(sxx*syy,1e-30)),-1+1e-15,1-1e-15)
        statistic=np.abs(r)*np.sqrt(np.maximum(n-2,1)/np.maximum(1-r**2,1e-30))
        pvalue=2*t.sf(statistic,np.maximum(n-2,1))
        return int(np.sum((n>=15)&(sxy>0)&(pvalue<.05)))
    observed=count(matrix)
    # Residualize each series around its fitted linear mean before resampling.
    residual=matrix.copy()
    for j in range(matrix.shape[1]):
        good=np.isfinite(matrix[:,j])
        if good.sum()>=3:
            fit=linregress(years[good],matrix[good,j])
            residual[good,j]-=fit.slope*(years[good]-years.mean())
    exceed=0;shift_exceed=0
    for _ in range(draws):
        exceed+=count(residual[rng.permutation(len(years))])>=observed
        shift_exceed+=count(np.roll(residual,int(rng.integers(len(years))),axis=0))>=observed
    return dict(observed_positive_significant=observed,year_permutation_p=(1+exceed)/(1+draws),synchronized_circular_shift_p=(1+shift_exceed)/(1+draws),draws=draws)


def main():
    p=argparse.ArgumentParser();p.add_argument("--field-draws",type=int,default=2000);p.add_argument("--historical-only",action="store_true");a=p.parse_args()
    folder=OUT/"meaning";folder.mkdir(parents=True,exist_ok=True)
    real=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e9_application/real_year_estimates.parquet") if a.historical_only else real_deliveries()
    point="d2_point" if a.historical_only else "revised_d2"
    real.to_parquet(folder/("historical_real_deliveries.parquet" if a.historical_only else "real_deliveries.parquet"),index=False)
    years=annual_panel(real,point)
    years.to_parquet(folder/"annual_panel.parquet",index=False)
    rows=[]
    for station,b in years.groupby("station_key"):
        for rule,keep,col in [("complete_year",b.complete_year,"truth_h30"),("warm_90",b.warm_observed_fraction.ge(.9),"retained_estimate"),("coverage_75",b.observed_fraction.ge(.75),"retained_estimate"),("retain_and_estimate",pd.Series(True,index=b.index),"retained_estimate")]:
            selected=b.loc[keep&b[col].notna()]
            if len(selected)<15 or selected.year.nunique()<15:
                continue
            result=linregress((selected.year-2000)/10,selected[col])
            rows.append(dict(station_key=station,provider=b.provider.iloc[0],group=b.independence_group.iloc[0],rule=rule,n_years=len(selected),slope=result.slope,se=result.stderr,pvalue=result.pvalue,hot_q90=float(selected[col].quantile(.9)),period_start=int(selected.year.min()),period_end=int(selected.year.max())))
    stations=pd.DataFrame(rows)
    stations["significant_bh"]=False
    for _,idx in stations.groupby(["provider","rule"]).groups.items():
        stations.loc[idx,"significant_bh"]=bh(stations.loc[idx,"pvalue"])
    stations.to_csv(folder/"station_selection_trends.csv",index=False)
    summaries=[]
    rng=np.random.default_rng(0)
    for (provider,rule),b in stations.groupby(["provider","rule"]):
        group_values=[v.slope.to_numpy() for _,v in b.groupby("group")]
        units=np.arange(len(group_values));boot=[]
        for _ in range(2000):
            choice=rng.choice(units,len(units),replace=True)
            boot.append(np.median(np.concatenate([group_values[g] for g in choice])))
        summaries.append(dict(provider=provider,rule=rule,n_stations=len(b),n_groups=len(units),median_slope=float(b.slope.median()),group_bootstrap_lower=float(np.quantile(boot,.025)),group_bootstrap_upper=float(np.quantile(boot,.975)),n_positive_bh=int((b.significant_bh&b.slope.gt(0)).sum())))
    pd.DataFrame(summaries).to_csv(folder/"regional_selection_summary.csv",index=False)
    fields=[]
    for provider in sorted(stations.provider.unique()):
        for rule in ["complete_year","retain_and_estimate"]:
            sites=stations.loc[stations.provider.eq(provider)&stations.rule.eq(rule),"station_key"]
            if len(sites)<5:
                continue
            eligible=years.loc[years.station_key.isin(sites)].copy()
            if rule=="complete_year":
                eligible=eligible.loc[eligible.complete_year]
            matrix=eligible.pivot(index="year",columns="station_key",values="truth_h30" if rule=="complete_year" else "retained_estimate")
            fields.append(dict(provider=provider,rule=rule,**field_test(matrix,None,a.field_draws)))
    pd.DataFrame(fields).to_csv(folder/"field_significance.csv",index=False)
    # Within the SAME stations, compare conclusions as a paired sensitivity.
    paired=stations.pivot(index="station_key",columns="rule",values="slope")
    paired["retain_minus_complete"]=paired.retain_and_estimate-paired.complete_year
    paired.to_csv(folder/"same_station_trend_contrasts.csv")
    T.write_json(folder/"summary.json",{"n_stations_by_rule":stations.groupby("rule").station_key.nunique().to_dict(),"historical_models_only":a.historical_only,"inference":"station BH within agency/rule; synchronized temporal null resampling; group bootstrap for regional medians","limitation":"archive is an assembled panel, not a census of all USGS water-temperature stations; inference is descriptive for this panel; incomplete-year outcomes are unknown","period_comparability":"same-station slope contrasts and individual record spans reported; changing station roster and changing year support are distinct"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
