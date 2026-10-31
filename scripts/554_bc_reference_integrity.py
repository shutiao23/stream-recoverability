#!/usr/bin/env python3
"""Independently recompute BC published-daily H30 and masked-window bounds.

This checks arithmetic and recorded masks, not 24-hour measurement quality,
external-climate independence or whether the model fits are leak-free.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_bc_air2stream'


def compute(values, mask_runs):
    x=np.asarray(values,dtype=float)
    if len(x)<30 or not np.isfinite(x).all():raise ValueError('Reference year is not complete')
    observed=x.copy();nmask=0
    for run in str(mask_runs).split(';'):
        start,length=map(int,run.split(':'))
        if start<0 or length<=0 or start+length>len(x):raise ValueError('Mask outside year')
        if not np.isfinite(observed[start:start+length]).all():raise ValueError('Overlapping mask runs')
        observed[start:start+length]=np.nan;nmask+=length
    kernel=np.ones(30)/30
    truth=float(np.convolve(x,kernel,'valid').max())
    valid=np.convolve(np.isfinite(observed).astype(int),np.ones(30,dtype=int),'valid')==30
    windows=np.convolve(np.nan_to_num(observed),kernel,'valid')
    lower=float(windows[valid].max()) if valid.any() else np.nan
    return truth,lower,nmask


def check_scorecard(cases, scorecard):
    """Recompute point MAE, failure rate, interval coverage and width on saved cases."""
    rows=[]
    for record in scorecard.itertuples():
        block=cases.loc[cases.design_family.eq(record.family)]
        if record.stratum=='danger':block=block.loc[block.peak_overlap.ge(.5)]
        column={'plug_in':'h30__policy','D2':'D2','stochastic_calibrated':'stochastic_cal_q50'}[record.estimator]
        truth=block.eval_truth_h30.to_numpy(float);point=block[column].to_numpy(float)
        valid=np.isfinite(point)&np.isfinite(truth)
        if not valid.any():continue
        calculations={'mae':float(np.mean(abs(point[valid]-truth[valid]))),
                      'bias':float(np.mean(point[valid]-truth[valid])),
                      'failure_rate':float(np.mean(abs(point[valid]-truth[valid])>.5))}
        if record.estimator!='plug_in':
            prefix={'D2':'D2','stochastic_calibrated':'stochastic_cal'}[record.estimator]
            q=block[[f'{prefix}_q{i:02d}' for i in [5,10,25,50,75,90,95]]].to_numpy(float)
            v=valid & np.isfinite(q).all(axis=1)
            if v.any():
                calculations['coverage90']=float(np.mean((truth[v]>=q[v,0]-1e-8)&(truth[v]<=q[v,-1]+1e-8)))
                calculations['width90']=float(np.mean(q[v,-1]-q[v,0]))
        if int(record.n_eligible)!=len(block) or int(record.n_available)!=int(valid.sum()):
            raise ValueError('Scorecard denominator does not match cases')
        rows.extend(abs(value-float(getattr(record,metric))) for metric,value in calculations.items())
    return max(rows,default=float('nan')),len(rows)


def main():
    cases=pd.read_parquet(OUT/'predictions.parquet')
    daily={str(site):pd.read_parquet(OUT/'daily'/f'{site}.parquet').set_index('date').temperature_c
           for site in cases.station_id.unique()}
    rows=[]
    for row in cases.itertuples():
        idx=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31')
        truth,lower,nmask=compute(daily[str(row.station_id)].reindex(idx).to_numpy(),row.mask_runs)
        rows.append(dict(station_id=str(row.station_id),year=int(row.year),design_family=row.design_family,
                         truth_abs_difference=abs(truth-row.eval_truth_h30),
                         lower_abs_difference=abs(lower-row.observed_lower_bound__observed_days),
                         mask_count_diff=nmask-int(row.total_missing),
                         finite_expected=bool(np.isfinite(lower) and np.isfinite(row.D2) and np.isfinite(row.stochastic_cal_q50)),
                         d2_below_bound=bool(row.D2<lower-1e-8),
                         stochastic_below_bound=bool(row.stochastic_cal_q50<lower-1e-8)))
    checks=pd.DataFrame(rows)
    score_difference,n_scores=check_scorecard(cases,pd.read_csv(OUT/'annual_scorecard.csv'))
    summary=dict(scorecard_max_abs_difference=score_difference, scorecard_metrics_checked=n_scores, cases=len(checks),stations=checks.station_id.nunique(),station_years=len(checks[['station_id','year']].drop_duplicates()),
                 max_truth_abs_difference=float(checks.truth_abs_difference.max()),
                 max_lower_bound_abs_difference=float(checks.lower_abs_difference.max()),
                 mask_count_mismatch=int(checks.mask_count_diff.ne(0).sum()),
                 nonfinite_bound_or_point=int((~checks.finite_expected).sum()),
                 d2_below_bound=int(checks.d2_below_bound.sum()),
                 stochastic_below_bound=int(checks.stochastic_below_bound.sum()),
                 scope='reference is the author-published daily series; unknown hourly completeness and measurement error remain',
                 arithmetic='30-day ordinary convolution; recompute visible windows after applying stored zero-based mask runs')
    summary['passed']=bool(np.isfinite(summary['scorecard_max_abs_difference']) and summary['scorecard_max_abs_difference']<1e-8 and summary['max_truth_abs_difference']<1e-8 and summary['max_lower_bound_abs_difference']<1e-8 and not any(summary[x] for x in ['mask_count_mismatch','nonfinite_bound_or_point','d2_below_bound','stochastic_below_bound']))
    (OUT/'reference_integrity.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if not summary['passed']:raise SystemExit(1)

if __name__=='__main__':main()
