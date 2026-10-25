#!/usr/bin/env python3
"""Verify record-attribution reversals using observed windows alone.

For an incomplete year, any fully observed 30-day mean is a lower bound on
H30. If that bound exceeds every complete year's H30 at the same station,
the complete-only record cannot be the full-record maximum. No imputation,
failure score, seed or unobserved target temperature is needed for this fact.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]


def observed_window(values):
    windows=sliding_window_view(np.asarray(values,float),30)
    good=np.isfinite(windows).all(axis=1)
    if not good.any():return np.nan,None
    means=np.full(len(windows),-np.inf);means[good]=windows[good].mean(axis=1)
    start=int(np.argmax(means));return float(means[start]),start


def main():
    y=pd.read_parquet(T.E1/"station_years.parquet")
    y=y.loc[~y.edge_year&y.fully_active&y.year.between(1981,2025)].drop_duplicates(["station_key","year"])
    complete=y.loc[y.complete_year&y.truth_h30.notna()]
    eligible=complete.groupby("station_key").size();eligible=eligible.index[eligible.ge(15)]
    y=y.loc[y.station_key.isin(eligible)].copy()
    daily=pd.read_parquet(T.SCRATCH/"archive_daily.parquet",columns=["station_key","date","water_c"],filters=[("station_key","in",list(eligible))])
    if daily.duplicated(["station_key","date"]).any():raise RuntimeError("Observed daily reference is not unique")
    maps=pd.read_parquet(OUT/"cases/leave_one_year_out/seed_00.parquet",columns=["station_key","region"]).drop_duplicates().set_index("station_key").region
    certificates=[];checks=[];epsilon=5e-6
    for station,b in y.groupby("station_key"):
        d=daily.loc[daily.station_key.eq(station)].set_index("date").water_c
        records=[];incomplete=[]
        for row in b.itertuples():
            index=pd.date_range(f"{row.year}-01-01",f"{row.year}-12-31")
            values=d.reindex(index).to_numpy(float);bound,start=observed_window(values)
            missing=int((~np.isfinite(values)).sum())
            if row.complete_year:
                if missing or not np.isfinite(bound) or abs(bound-row.truth_h30)>epsilon:
                    raise RuntimeError(f"Complete-year reference mismatch at {station}/{row.year}")
                records.append((bound,int(row.year),start))
            elif missing and np.isfinite(bound):
                incomplete.append((row,values,bound,start))
        maximum,reference_year,reference_start=max(records,key=lambda r:(r[0],-r[1]))
        for row,values,bound,start in incomplete:
            margin=bound-maximum
            checks.append(dict(station_key=station,year=int(row.year),observed_lower_bound=bound,maximum_complete_H30=maximum,margin=margin))
            if margin<=epsilon:continue
            dates=pd.date_range(f"{row.year}-01-01",f"{row.year}-12-31")
            window=values[start:start+30]
            assert np.isfinite(window).all()
            certificates.append(dict(station_key=station,provider=row.provider,region=maps.get(station),group=row.independence_group,
                                     incomplete_year=int(row.year),warmest_complete_year=reference_year,n_complete_years=len(records),
                                     observed_window_start=str(dates[start].date()),observed_window_end=str(dates[start+29].date()),
                                     observed_window_mean=bound,maximum_complete_year_H30=maximum,record_excess_lower_bound=margin,
                                     n_missing_days=int(np.isnan(values).sum()),statistic_class=row.statistic_class,
                                     verified_daily_values=";".join(f"{x:.12g}" for x in window)))
    dest=OUT/"observed_records";dest.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame(certificates);frame.to_csv(dest/"observed_record_certificates.csv",index=False)
    pd.DataFrame(checks).to_csv(dest/"all_incomplete_year_bounds.csv",index=False)
    summaries=[]
    for threshold in [0.,.5,1.]:
        b=frame.loc[frame.record_excess_lower_bound>max(epsilon,threshold)]
        summaries.append(dict(margin_c=threshold,n_station_years=len(b),n_stations=b.station_key.nunique(),n_groups=b.group.nunique()))
    pd.DataFrame(summaries).to_csv(dest/"summary.csv",index=False)
    T.write_json(dest/"design.json",{"period":[1981,2025],"eligible_stations":len(eligible),"minimum_complete_observed_years":15,"comparison":"same station and analysis window; incomplete-year observed-window lower bound versus maximum over every complete observed year","verified":"all complete-year H30 references recomputed from observed daily water_c; every lower-bound witness contains 30 finite original daily observations","not_claimed":"the incomplete candidate is necessarily the unique hottest year; other incomplete years might be hotter; reported daily values are not error-free physical truth","imputation_used":False,"random_seeds_used":False,"floating_tolerance_c":epsilon,"scientific_scope":"a complete-only record attribution is contradicted for these finite observed station histories; no new-region or population-sampling inference"})
    print(json.dumps({"eligible_stations":len(eligible),"observational_record_reversals":summaries}),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
