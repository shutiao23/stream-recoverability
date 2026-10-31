#!/usr/bin/env python3
"""Recompute Truckee retrospective peak strata and all reported metrics."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';LEVELS=[5,10,25,50,75,90,95]

def main():
    status=json.loads((OUT/'peak_visibility_status.json').read_text());plan=json.loads((OUT/'peak_visibility_plan.json').read_text())
    if status['status']!='computed_posthoc':
        raise ValueError('Peak summary absent or changed')
    f=pd.read_parquet(PRIVATE/'exploratory_predictions.parquet');daily=pd.read_parquet(PRIVATE/'finite_reported_daily.parquet')
    site=str(f.station_id.iloc[0]);ref=daily[daily.station_code.eq(site)].set_index('day').mean_c
    arithmetic=T.load_script('truckee_peak_independent_mask',ROOT/'scripts/554_bc_reference_integrity.py')
    score=T.load_script('truckee_peak_independent_metrics',ROOT/'scripts/599_nova_scotia_exploratory_integrity.py')
    quad=T.load_script('truckee_peak_independent_quad',ROOT/'scripts/576_verify_private_annual_predictions.py')
    bounds=[];truth=[]
    for r in f.itertuples(index=False):
        vals=ref.reindex(pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')).to_numpy(float);t,b,n=arithmetic.compute(vals,r.mask_runs)
        score.same(t,r.eval_truth_h30,'reference');score.same(b,r.observed_lower_bound__observed_days,'bound')
        if n!=r.total_missing:raise ValueError('Mask length differs')
        truth.append(t);bounds.append(b)
    truth=np.asarray(truth);bounds=np.asarray(bounds);labels=np.where(~np.isfinite(bounds),'bound_unavailable',np.where(abs(truth-bounds)<=1e-8,'reference_equals_bound','reference_above_bound'))
    common=np.isfinite(truth)&np.isfinite(f.h30__policy)&np.isfinite(f.D2)&np.isfinite(f.stochastic_cal_q50)
    for prefix in ['D2','stochastic_cal']:common &= np.isfinite(f[[f'{prefix}_q{x:02d}' for x in LEVELS]]).all(axis=1)
    table=pd.read_csv(OUT/'peak_visibility_summary.csv');cells=0
    for row in table.itertuples(index=False):
        mask=np.ones(len(f),bool) if row.stratum=='all' else labels==row.stratum;b=f.loc[mask&common]
        score.same(int(mask.sum()),row.n_eligible,'eligible');score.same(len(b),row.n_common,'common');score.same(b.year.nunique(),row.represented_years,'years');cells+=3
        if b.empty:continue
        col,prefix={'plug_in':('h30__policy',None),'D2':('D2','D2'),'stochastic_calibrated':('stochastic_cal_q50','stochastic_cal')}[row.estimator]
        m=score.independent_metrics(b,col,prefix,quad)
        for name,key in [('mae','mae'),('bias','bias'),('failure_gt_0_5','failure_rate')]:score.same(getattr(row,name),m[key],name);cells+=1
        if prefix:
            q=b[[f'{prefix}_q{x:02d}' for x in LEVELS]].to_numpy(float)
            for name,key in [('coverage90','coverage90'),('mean_width90','width90'),('interval_score90','interval_score90'),('crps','crps')]:
                score.same(getattr(row,name),m[key],name);cells+=1
            score.same(row.zero_width,int((abs(q[:,-1]-q[:,0])<=1e-8).sum()),'zero width');cells+=1
    result={'status':'passed','cases_recomputed':len(f),'summary_cells_checked':cells,'counts':{name:int((labels==name).sum()) for name in ('reference_equals_bound','reference_above_bound','bound_unavailable')},
            'scope':'Independent convolution, mask and score arithmetic on the same source values and saved model predictions.',
            'limitations':'Retrospective, outcome-defined strata; four years and one managed watershed. Does not refit models or verify sensor accuracy, current weather or climate independence.'}
    (OUT/'peak_visibility_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
