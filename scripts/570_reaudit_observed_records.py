#!/usr/bin/env python3
"""Independently recheck record witnesses using local archived daily values.

The audit is an independent arithmetic implementation on the same canonical
float32 daily archive, not a comparison with provider-native raw measurements
or evidence about physical sensor error. No imputation is performed.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/'results/wrr_review_completion_20261024/observed_records'
OUT=ROOT/'results/wrr_review_response_20261027/audit'
EPS=5e-6


def maximum_window(values,window=30):
    values=np.asarray(values,dtype=float)
    if len(values)<window:return np.nan,None
    finite=np.isfinite(values)
    count=np.convolve(finite.astype(int),np.ones(window,dtype=int),'valid')
    sums=np.convolve(np.where(finite,values,0.),np.ones(window,dtype=float),'valid')
    eligible=count==window
    if not eligible.any():return np.nan,None
    means=np.where(eligible,sums/window,-np.inf)
    loc=int(np.argmax(means))
    return float(means[loc]),loc


def audit():
    years=pd.read_parquet(ROOT/'results/wrr_target_recovery_20261021/e1_archive/station_years.parquet')
    years=years.loc[~years.edge_year & years.fully_active & years.year.between(1981,2025)].copy()
    if years.duplicated(['station_key','year']).any():raise ValueError('duplicate station-year metadata')
    complete=years.loc[years.complete_year & years.truth_h30.notna()]
    counts=complete.groupby('station_key').size();eligible=counts.index[counts.ge(15)].tolist()
    years=years.loc[years.station_key.isin(eligible)]
    daily=pd.read_parquet(ROOT/'scratch/wrr_target_recovery_20261021/archive_daily.parquet',
                          columns=['station_key','date','water_c'],filters=[('station_key','in',eligible)])
    if daily.duplicated(['station_key','date']).any():raise ValueError('duplicate station-date records')
    stations={k:g.set_index('date').water_c.sort_index() for k,g in daily.groupby('station_key',observed=True)}
    originals=pd.read_csv(S/'all_incomplete_year_bounds.csv')
    certificates=pd.read_csv(S/'observed_record_certificates.csv')
    if certificates.duplicated(['station_key','incomplete_year']).any():raise ValueError('duplicate certificate identities')
    expected={(r.station_key,int(r.incomplete_year)):r for r in certificates.itertuples(index=False)}
    reconstructed=[];observed_cert=set();complete_count=0;max_reference_discrepancy=0.;max_window_discrepancy=0.;max_values_discrepancy=0.
    for station,block in years.groupby('station_key'):
        series=stations[station];complete_refs=[];incomplete=[]
        for row in block.itertuples(index=False):
            dates=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31');v=series.reindex(dates).to_numpy(float)
            maximum,start=maximum_window(v)
            if row.complete_year:
                if not np.isfinite(v).all() or not np.isfinite(maximum):raise ValueError(f'incomplete purported reference: {station}/{row.year}')
                difference=abs(maximum-row.truth_h30);max_reference_discrepancy=max(max_reference_discrepancy,difference)
                if difference>EPS:raise ValueError(f'complete reference differs: {station}/{row.year}')
                complete_refs.append((int(row.year),maximum));complete_count+=1
            elif (~np.isfinite(v)).any() and np.isfinite(maximum):
                incomplete.append((row,v,dates,maximum,start))
        if len(complete_refs)<15:raise ValueError('reference count below eligibility threshold')
        highest=max(x[1] for x in complete_refs)
        for row,v,dates,bound,start in incomplete:
            diff=bound-highest
            reconstructed.append(dict(station_key=station,year=int(row.year),observed_lower_bound=bound,maximum_complete_H30=highest,margin=diff))
            if diff<=EPS:continue
            key=(station,int(row.year));observed_cert.add(key)
            if key not in expected:raise ValueError(f'new or missing certificate {key}')
            r=expected[key]
            if len(complete_refs)!=r.n_complete_years or abs(highest-r.maximum_complete_year_H30)>EPS:
                raise ValueError(f'certificate complete-year comparison differs {key}')
            known_years=dict(complete_refs)
            if int(r.warmest_complete_year) not in known_years or abs(known_years[int(r.warmest_complete_year)]-highest)>EPS:
                raise ValueError(f'certificate reference year differs {key}')
            window_dates=pd.date_range(r.observed_window_start,r.observed_window_end)
            original=series.reindex(window_dates).to_numpy(float)
            stored=np.fromstring(r.verified_daily_values,sep=';')
            if len(original)!=30 or len(stored)!=30 or not np.isfinite(original).all():raise ValueError(f'invalid certificate window {key}')
            delta=float(np.max(abs(original-stored)));max_values_discrepancy=max(max_values_discrepancy,delta)
            window_delta=abs(float(original.mean())-r.observed_window_mean);max_window_discrepancy=max(max_window_discrepancy,window_delta)
            if delta>EPS or window_delta>EPS or abs(bound-r.observed_window_mean)>EPS or abs(diff-r.record_excess_lower_bound)>EPS:
                raise ValueError(f'certificate window or margin differs {key}')
            if int(np.isnan(v).sum())!=int(r.n_missing_days):raise ValueError(f'missing-day count differs {key}')
    if observed_cert!=set(expected):raise ValueError('Witness set differs from stored certificates')
    new=pd.DataFrame(reconstructed)
    comp=new.merge(originals,on=['station_key','year'],how='outer',suffixes=('_new','_stored'),indicator=True,validate='one_to_one')
    if not comp._merge.eq('both').all():raise ValueError('incomplete-year denominator differs')
    for col in ['observed_lower_bound','maximum_complete_H30','margin']:
        if not np.allclose(comp[col+'_new'],comp[col+'_stored'],atol=EPS,rtol=0):raise ValueError(f'incomplete-year {col} differs')
    return {'eligible_stations':len(eligible),'reference_station_years_recomputed':complete_count,
            'incomplete_station_years_recomputed':len(new),'certificate_station_years':len(certificates),
            'certificate_stations':certificates.station_key.nunique(),'certificate_groups':certificates['group'].nunique(),
            'max_complete_year_h30_discrepancy_c':max_reference_discrepancy,
            'max_witness_mean_discrepancy_c':max_window_discrepancy,
            'max_witness_daily_value_discrepancy_c':max_values_discrepancy,
            'all_incomplete_year_bounds_match':True,'witness_identity_and_counts_match':True,
            'tolerance_c':EPS,'passed':True,
            'scope':'independent convolution and calendar arithmetic on the same canonical float32 daily archive, not provider-native raw data',
            'limitations':'finite reported series; no independent measurement error assessment, external validation, or proof about unobserved partial-year maxima'}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    try:result=audit()
    except Exception as exc:
        result={'passed':False,'error':f'{type(exc).__name__}: {exc}',
                'scope':'independent arithmetic on canonical daily archive'}
    (OUT/'observed_record_independent_reaudit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
