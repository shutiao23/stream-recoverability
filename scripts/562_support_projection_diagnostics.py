#!/usr/bin/env python3
"""Quantify boundary contacts and check quantiles in whole-archive outputs.

A boundary contact is not necessarily an error: a completely observed warm
window can already determine the annual maximum. The truth of censored years
is not read here. Equal endpoints describe the saved distribution only; they
are not a proof that physical temperature uncertainty is zero.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/whole_archive'
QS=[5,10,25,50,75,90,95]
COLUMNS=['station_key','independence_group','year','observed_lower_bound__observed_days','D2']+[
    f'{prefix}_q{q:02d}' for prefix in ['D2','stochastic_cal'] for q in QS]


def summarize(frame, atol=1e-8):
    rows=[]
    for (family,mode),g in frame.groupby(['family','mode'],sort=True):
        bound=g.observed_lower_bound__observed_days.to_numpy(float)
        truth=g.reference_h30.to_numpy(float)
        d=g[[f'D2_q{q:02d}' for q in QS]].to_numpy(float)
        s=g[[f'stochastic_cal_q{q:02d}' for q in QS]].to_numpy(float)
        dvalid=np.isfinite(d).all(axis=1);svalid=np.isfinite(s).all(axis=1)
        common=np.isfinite(bound)&dvalid&svalid
        for name,q,valid in [('D2',d,dvalid),('stochastic_calibrated',s,svalid)]:
            qb=q[common];b=bound[common];y=truth[common]
            if not np.isfinite(y).all():raise ValueError('Missing complete-year reference')
            width_zero=abs(qb[:,-1]-qb[:,0])<=atol
            common_cases=g.loc[common]
            covered=(y>=qb[:,0]-atol)&(y<=qb[:,-1]+atol)
            below=valid & np.isfinite(bound) & np.any(q<bound[:,None]-atol,axis=1)
            crossings=valid & np.any(np.diff(q,axis=1)<-atol,axis=1)
            nonfinite_point=int((~np.isfinite(q[:,3])).sum())
            rows.append(dict(family=family,mode=mode,estimator=name,annual_rows=len(g),
                             complete_quantile_rows=int(valid.sum()),nonfinite_median_rows=nonfinite_point,
                             bound_finite_rows=int(np.isfinite(bound).sum()),paired_rows=int(common.sum()),
                             stations=int(g.loc[common,'station_key'].nunique()),
                             groups=int(g.loc[common,'independence_group'].nunique()),
                             below_bound=int(below.sum()),quantile_crossings=int(crossings.sum()),
                             lower_endpoint_at_bound=int(np.sum(abs(qb[:,0]-b)<=atol)),
                             median_at_bound=int(np.sum(abs(qb[:,3]-b)<=atol)),
                             median_at_bound_truth_equal=int(np.sum((abs(qb[:,3]-b)<=atol)&(abs(y-b)<=atol))),
                             median_at_bound_truth_above=int(np.sum((abs(qb[:,3]-b)<=atol)&(y>b+atol))),
                             truth_below_bound=int(np.sum(y<b-atol)),
                             truth_equal_bound=int(np.sum(abs(y-b)<=atol)),
                             zero_width90=int(width_zero.sum()),
                             zero_width90_at_bound=int(np.sum(width_zero&(abs(qb[:,3]-b)<=atol))),
                             zero_width90_covered=int(np.sum(width_zero&covered)),
                             zero_width90_missed=int(np.sum(width_zero&~covered)),
                             zero_width90_missed_stations=int(common_cases.loc[width_zero&~covered,'station_key'].nunique()),
                             zero_width90_missed_station_years=int(len(common_cases.loc[width_zero&~covered,['station_key','year']].drop_duplicates())),
                             zero_width90_truth_above_bound=int(np.sum(width_zero&(y>b+atol))),
                             zero_width90_missed_max_abs_error=float(np.max(abs(y[width_zero&~covered]-qb[width_zero&~covered,3]))) if np.any(width_zero&~covered) else 0.,
                             zero_width90_missed_error_over_half_c=int(np.sum(width_zero&~covered&(abs(y-qb[:,3])>.5))),
                             mean_width90=float(np.mean(qb[:,-1]-qb[:,0])) if len(qb) else np.nan))
    return pd.DataFrame(rows)


def main():
    frames=[];catalog=[]
    for family in ['calendar','crossed']:
        for mode in ['offline','forward']:
            paths=sorted((OUT/family/mode).glob('replicate_*/*/annual_predictions.parquet'))
            for path in paths:
                if pq.ParquetFile(path).metadata.num_rows == 0:
                    continue
                df=pd.read_parquet(path,columns=COLUMNS)
                if df.year.duplicated().any():raise ValueError(f'Nonunique annual year in {path}')
                df['family']=family;df['mode']=mode;df['replicate']=int(path.parent.parent.name.split('_')[-1])
                frames.append(df)
            catalog.append(dict(family=family,mode=mode,n_archive_files=len(paths)))
    all_cases=pd.concat(frames,ignore_index=True)
    reference=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',
                              columns=['station_key','year','design_family','eval_truth_h30'])
    keys=['station_key','year','design_family']
    consistency=reference.groupby(keys,dropna=False).eval_truth_h30.agg(['min','max','count'])
    if consistency['count'].eq(0).any() or (consistency['max']-consistency['min']).gt(1e-8).any():
        raise ValueError('Reference truth missing or inconsistent across designs')
    reference=consistency['min'].rename('reference_h30').reset_index().rename(columns={'design_family':'family'})
    all_cases=all_cases.merge(reference,on=['station_key','year','family'],how='left',validate='many_to_one')
    if all_cases.reference_h30.isna().any():raise ValueError('An evaluation year has no complete reference')
    key=['family','mode','replicate','station_key','year']
    if all_cases.duplicated(key).any():raise ValueError('Nonunique archive/year keys')
    summary=summarize(all_cases)
    prior=pd.read_csv(OUT/'annual.csv').groupby(['family','mode','estimator'],as_index=False)[['n_eligible','n_available']].sum()
    merged=summary.merge(prior,on=['family','mode','estimator'],how='left',validate='one_to_one')
    if merged.n_eligible.isna().any() or not merged.annual_rows.eq(merged.n_eligible).all() or not merged.complete_quantile_rows.eq(merged.n_available).all():
        raise ValueError('Saved year-level data disagree with annual availability denominators')
    if merged.below_bound.any() or merged.quantile_crossings.any() or merged.truth_below_bound.any():raise ValueError('Quantile, reference or support contradiction')
    merged.to_csv(OUT/'support_projection_summary.csv',index=False)
    audit={'archive_files':catalog,'total_annual_rows':len(all_cases),'duplicate_keys':0,
           'max_quantile_below_bound':int(merged.below_bound.sum()),'quantile_crossings':int(merged.quantile_crossings.sum()),
           'denominators_match_annual_summary':True,'tolerance_c':1e-8,
           'scope':'same masked archive rows; both seven-quantile estimators compared on their shared finite-bound cohort',
           'interpretation':'Zero-width intervals and observed bounds are checked against the finite complete reference; matches do not prove zero measurement uncertainty and no pre-projection counterfactual is computed.',
           'passed':True}
    (OUT/'support_projection_status.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(merged.to_string(index=False));print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
