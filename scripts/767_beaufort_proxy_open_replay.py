#!/usr/bin/env python3
"""Reproduce the proxy summary from the included processed water/air subset.

This uses the independent least-squares implementation, but the data are the
same processed observations and meteorological inputs as the primary analysis.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'beaufort_proxy'
SNAP=REV/'open_observed_record_snapshot';DEFAULT=REV/'audit/beaufort_proxy_open_replay.json'
UNBUNDLED='data/interim/tr_air_forcing.parquet'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,default=DEFAULT);a=p.parse_args()
    plan=json.loads((OUT/'plan.json').read_text());airinfo=json.loads((OUT/'air_snapshot_status.json').read_text())
    spec=importlib.util.spec_from_file_location('beaufort_open_independent',ROOT/'scripts/762_beaufort_proxy_independent_audit.py')
    independent=importlib.util.module_from_spec(spec);spec.loader.exec_module(independent)
    roster=pd.read_csv(OUT/'roster.csv');water=pd.read_parquet(SNAP/'daily_temperature.parquet');air=pd.read_parquet(OUT/'air_snapshot.parquet')
    water['date']=pd.to_datetime(water.date);air['date']=pd.to_datetime(air.date)
    if water.duplicated(['station_key','date']).any() or air.duplicated(['station_key','date']).any():raise ValueError('Duplicate daily input')
    rows=[]
    for site in roster.itertuples(index=False):
        w_series=water[water.station_key.eq(site.station_key)].set_index('date').water_c
        a_series=air[air.station_key.eq(site.station_key)].set_index('date').air_temperature_c
        water_years=[];air_years=[];annual=[]
        for year in range(2009,2018):
            summer=pd.date_range(f'{year}-07-01',f'{year}-08-31');air_index=pd.date_range(f'{year}-06-22',f'{year}-08-31')
            water_years.append(w_series.reindex(summer).to_numpy(float));x=pd.Series(a_series.reindex(air_index).to_numpy(float))
            if not np.isfinite(x.to_numpy()).all():raise ValueError('Missing curated air value')
            air_years.append(np.asarray([x.rolling(lag,min_periods=lag).mean().iloc[9:].to_numpy() for lag in range(2,11)]))
            full=w_series.reindex(pd.date_range(f'{year}-01-01',f'{year}-12-31')).to_numpy(float)
            if not np.isfinite(full).all():raise ValueError('Missing planned complete-year water value')
            annual.append(float(pd.Series(full).rolling(30,min_periods=30).mean().max()))
        water_years=np.asarray(water_years);air_years=np.asarray(air_years)
        target_summer=float(np.mean([pd.Series(w).rolling(30,min_periods=30).mean().max() for w in water_years]));target_calendar=float(np.mean(annual))
        for k in range(1,9):
            for indices in itertools.combinations(range(9),k):
                result=independent.naive_fit(water_years,air_years,set(indices))
                if result is None:raise ValueError('Saved proxy cohort unexpectedly unsupported')
                _,_,_,obs,filled=result
                rows.append({'station_key':site.station_key,'independence_group':site.independence_group,'provider':site.provider,
                             'missing_years':k,'target_summer':target_summer,'target_calendar':target_calendar,
                             'observed_mean':obs,'filled_mean':filled})
        print('Replayed station',site.provider,flush=True)
    frame=pd.DataFrame(rows)
    n_summary,n_region=independent.summarize(frame,roster)
    if len(frame)!=11220 or n_summary!=16:raise ValueError('Proxy replay denominator differs')
    report={'status':'passed','stations':len(roster),'case_masks':len(frame),'summary_rows':n_summary,
            'leave_provider_rows':n_region,'source_air_table_included':False,
            'scope':'Recomputes fixed proxy regressions and summaries using bundled processed water and the small processed-air snapshot; original full air table is not included or checked.',
            'limitations':'Same underlying data and post-hoc cohort, not the authors\' original code, raw-provider rebuild, independent climate, sensor validation or model-training replay.'}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
