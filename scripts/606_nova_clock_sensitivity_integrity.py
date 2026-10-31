#!/usr/bin/env python3
"""Independently recompute shifted NS references, masks and paired scores.

Requires locally held case-level predictions; it cannot prove timezone, source
quality, independent climates or exhaustive absence of hidden-value leakage.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_clock_sensitivity'
BASE_PRIVATE=ROOT/'private/wrr_nova_scotia_exploratory_20261026'
PRIVATE=ROOT/'private/wrr_nova_scotia_clock_sensitivity_20261026'
DATA=ROOT/'data/external/wrr_nova_scotia_open_20261026/clock_sensitivity_reported_daily.parquet'
KEY=['station_id','year','design_family','realization_id','mask_runs']
LEVELS=[5,10,25,50,75,90,95]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def equal(a,b,label):
    if not np.isclose(a,b,rtol=0,atol=1e-8,equal_nan=True):raise ValueError(f'{label} differs: {a} vs {b}')


def measures(frame,scorer):
    y=frame.eval_truth_h30.to_numpy(float);bound=frame.observed_lower_bound__observed_days.to_numpy(float);d={}
    for name,prefix,point_col in [('D2','D2','D2'),('stochastic','stochastic_cal','stochastic_cal_q50')]:
        q=frame[[f'{prefix}_q{x:02d}' for x in LEVELS]].to_numpy(float);point=frame[point_col].to_numpy(float)
        if np.any(np.diff(q,axis=1)<-1e-8) or np.any(np.isfinite(bound)&(q[:,0]<bound-1e-8)):raise ValueError('quantile support violation')
        if np.any(np.isfinite(bound)&(y<bound-1e-8)):raise ValueError('reference below observed bound')
        low,high=q[:,0],q[:,-1];samples,_=scorer.quadrature(q,bound)
        d[name+'_mae']=abs(point-y)
        d[name+'_coverage90']=((y>=low-1e-8)&(y<=high+1e-8)).astype(float)
        d[name+'_width90']=high-low
        d[name+'_interval_score90']=high-low+20*(np.maximum(low-y,0)+np.maximum(y-high,0))
        d[name+'_crps']=scorer.crps(samples,y)
    return pd.DataFrame(d)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=PRIVATE)
    p.add_argument('--base-evidence',type=Path,default=BASE_PRIVATE);p.add_argument('--data',type=Path,default=DATA)
    p.add_argument('--output',type=Path,default=OUT/'integrity_status.json');a=p.parse_args()
    status=json.loads((OUT/'score_status.json').read_text());f=pd.read_parquet(a.evidence/'predictions.parquet');base=pd.read_parquet(a.base_evidence/'predictions.parquet')
    daily=pd.read_parquet(a.data);series=daily.set_index(['station_id','shift_hours','date']).temperature_c
    if series.index.duplicated().any():raise ValueError('duplicate shifted daily record')
    local=module('independent_clock_mask',ROOT/'scripts/554_bc_reference_integrity.py')
    scorer=module('independent_clock_scores',ROOT/'scripts/576_verify_private_annual_predictions.py')
    max_truth=0.;max_bound=0.;masks=0
    if f.duplicated(KEY+['shift_hours']).any() or base.duplicated(KEY).any():raise ValueError('duplicate case key')
    for r in f.itertuples(index=False):
        dates=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31',freq='D')
        index=pd.MultiIndex.from_product([[str(r.station_id)],[int(r.shift_hours)],dates],names=['station_id','shift_hours','date'])
        truth,bound,n=local.compute(series.reindex(index).to_numpy(float),r.mask_runs)
        max_truth=max(max_truth,abs(truth-float(r.eval_truth_h30)));max_bound=max(max_bound,abs(bound-float(r.observed_lower_bound__observed_days)))
        masks+=int(n!=int(r.total_missing) or n!=int(r.gap_length))
    if max_truth>1e-8 or max_bound>1e-8 or masks:raise ValueError('shifted reference or mask arithmetic differs')
    cohorts=[]
    for shift in [-1,0,1]:
        fshift=f.loc[f.shift_hours.eq(shift)]
        identity=fshift[KEY].merge(base[KEY],on=KEY,how='outer',indicator=True,validate='one_to_one')
        if not identity._merge.eq('both').all():raise ValueError('original mask keys changed')
        columns=['eval_truth_h30','D2','stochastic_cal_q50']+[f'{prefix}_q{q:02d}' for prefix in ['D2','stochastic_cal'] for q in LEVELS]
        valid=np.isfinite(fshift[columns].to_numpy(float)).all(axis=1)
        cohorts.append(fshift.loc[valid,KEY])
    common=cohorts[0]
    for other in cohorts[1:]:common=common.merge(other,on=KEY,validate='one_to_one')
    if len(common)!=status['all_shift_common_cases']:raise ValueError('all-shift cohort differs')
    baseline=base[KEY+['peak_overlap']].rename(columns={'peak_overlap':'base_peak_overlap'})
    saved=pd.read_csv(OUT/'paired_summary.csv');metric_by_shift={};checked=0
    for shift in [-1,0,1]:
        g=common.merge(f.loc[f.shift_hours.eq(shift)],on=KEY,validate='one_to_one').merge(baseline,on=KEY,validate='one_to_one')
        metrics=measures(g,scorer);metric_by_shift[shift]=metrics
        for stratum,mask in [('all',np.ones(len(g),bool)),('danger',g.base_peak_overlap.ge(.5).to_numpy())]:
            row=saved.loc[saved.shift_hours.eq(shift)&saved.stratum.eq(stratum)]
            if len(row)!=1:raise ValueError('missing saved paired summary')
            row=row.iloc[0];equal(int(mask.sum()),row.n_common,'paired case count');checked+=1
            for name in metrics:
                equal(float(metrics.loc[mask,name].mean()),float(row[name]),f'{shift}/{stratum}/{name}');checked+=1
    differences=pd.read_csv(OUT/'paired_differences.csv')
    diff_checked=0
    for r in differences.itertuples(index=False):
        delta=metric_by_shift[int(r.shift_hours)][r.metric].to_numpy()-metric_by_shift[0][r.metric].to_numpy()
        equal(len(delta),r.n_common,'difference count');equal(float(delta.mean()),r.mean_shift_minus_zero,'difference mean')
        equal(float(abs(delta).max()),r.max_abs_case_change,'difference max');diff_checked+=3
    # The per-year reference delta is checked independently from all saved cases.
    truth=f[['station_id','year','shift_hours','eval_truth_h30']].drop_duplicates()
    if truth.duplicated(['station_id','year','shift_hours']).any():raise ValueError('truth differs across masks')
    original=truth.loc[truth.shift_hours.eq(0),['station_id','year','eval_truth_h30']].rename(columns={'eval_truth_h30':'base_h30'})
    truth=truth.merge(original,on=['station_id','year'],validate='many_to_one');truth['delta']=truth.eval_truth_h30-truth.base_h30
    saved_truth=pd.read_csv(OUT/'reference_h30_changes.csv',dtype={'station_id':str})
    matched=truth.merge(saved_truth,on=['station_id','year','shift_hours'],validate='one_to_one')
    if len(matched)!=len(truth) or not np.allclose(matched.delta,matched.h30_change_c,atol=1e-8,rtol=0):raise ValueError('reference delta differs')
    equal(float(truth.delta.abs().max()),status['max_abs_reference_h30_change_c'],'reference max delta')
    state={'status':'passed','case_rows':len(f),'common_masks':len(common),'stations':int(f.station_id.nunique()),
      'station_year_shift_rows':len(truth),'max_reference_difference_c':max_truth,'max_bound_difference_c':max_bound,
      'mask_count_mismatches':masks,'paired_summary_cells_checked':checked,'paired_difference_cells_checked':diff_checked,
      'scope':'independent convolution, support checks and score arithmetic on saved predictions and shifted reported-clock daily data; no model refit',
      'limitation':'post-hoc shifts do not determine true timezone, validate instrument quality, or establish independence; they keep NASA forcing fixed'}
    a.output.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))

if __name__=='__main__':main()
