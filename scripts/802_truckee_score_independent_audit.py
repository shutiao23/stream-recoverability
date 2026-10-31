#!/usr/bin/env python3
"""Independently recalculate Truckee masks, observed bounds and scores."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';LEVELS=[5,10,25,50,75,90,95]

def main():
    status=json.loads((OUT/'exploratory_score_status.json').read_text());plan=json.loads((OUT/'exploratory_score_plan.json').read_text())
    path=PRIVATE/'exploratory_predictions.parquet'
    if status['status']!='exploratory_scored':raise ValueError('Score data changed')
    frame=pd.read_parquet(path);daily=pd.read_parquet(PRIVATE/'finite_reported_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    if len(frame)!=status['cases'] or frame.station_key.nunique()!=1 or frame.year.nunique()!=4:raise ValueError('Unexpected target cohort')
    station=str(frame.station_id.iloc[0]);reference=daily[daily.station_code.eq(station)].set_index('day').mean_c
    if reference.index.duplicated().any():raise ValueError('Duplicate daily reference')
    arithmetic=T.load_script('truckee_independent_masks',ROOT/'scripts/554_bc_reference_integrity.py')
    metrics=T.load_script('truckee_independent_metrics',ROOT/'scripts/599_nova_scotia_exploratory_integrity.py')
    quad=T.load_script('truckee_independent_quadrature',ROOT/'scripts/576_verify_private_annual_predictions.py')
    max_truth=max_bound=0.;violations=0
    for r in frame.itertuples(index=False):
        values=reference.reindex(pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')).to_numpy(float)
        truth,lower,n=arithmetic.compute(values,r.mask_runs);max_truth=max(max_truth,abs(truth-float(r.eval_truth_h30)))
        max_bound=max(max_bound,abs(lower-float(r.observed_lower_bound__observed_days)))
        if n!=r.total_missing or n!=r.gap_length:raise ValueError('Saved mask length differs')
        for prefix in ['D2','stochastic_cal']:
            q=np.asarray([getattr(r,f'{prefix}_q{x:02d}') for x in LEVELS],float)
            if np.isfinite(q).all() and np.any(np.diff(q)<-1e-8) or np.any(q<lower-1e-8):violations+=1
    if max_truth>1e-8 or max_bound>1e-8 or violations:raise ValueError('Reference or support mismatch')
    summary=pd.read_csv(OUT/'exploratory_score_summary.csv');count=0
    for r in summary.itertuples(index=False):
        b=frame if r.stratum=='all' else frame[frame.peak_overlap.ge(.5)]
        col,prefix={'plug_in':('h30__policy',None),'D2':('D2','D2'),'stochastic_calibrated':('stochastic_cal_q50','stochastic_cal')}[r.estimator]
        for key,value in metrics.independent_metrics(b,col,prefix,quad).items():metrics.same(value,getattr(r,key),f'{r.stratum}/{r.estimator}/{key}');count+=1
    pairs=pd.read_csv(OUT/'exploratory_paired_summary.csv');pair_count=0
    for r in pairs.itertuples(index=False):
        b=frame if r.stratum=='all' else frame[frame.peak_overlap.ge(.5)];y=b.eval_truth_h30.to_numpy(float);lower=b.observed_lower_bound__observed_days.to_numpy(float)
        a=b.D2.to_numpy(float);s=b.stochastic_cal_q50.to_numpy(float);qa=b[[f'D2_q{x:02d}' for x in LEVELS]].to_numpy(float);qs=b[[f'stochastic_cal_q{x:02d}' for x in LEVELS]].to_numpy(float)
        common=np.isfinite(a)&np.isfinite(s)&np.isfinite(y)&np.isfinite(qa).all(axis=1)&np.isfinite(qs).all(axis=1)
        metrics.same(int(common.sum()),r.n_common,'common count');pair_count+=1
        for name,point,q in [('D2',a,qa),('stochastic',s,qs)]:
            yy=y[common];v=q[common];lo=v[:,0];hi=v[:,-1];draws,_=quad.quadrature(v,lower[common])
            values={'mae':np.mean(abs(point[common]-yy)),'coverage90':np.mean((yy>=lo-1e-8)&(yy<=hi+1e-8)),
                    'width90':np.mean(hi-lo),'interval_score90':np.mean(hi-lo+20*(np.maximum(lo-yy,0)+np.maximum(yy-hi,0))),
                    'crps':np.mean(quad.crps(draws,yy))}
            for key,value in values.items():metrics.same(value,getattr(r,f'{name}_{key}'),f'{r.stratum}/{name}/{key}');pair_count+=1
    by=pd.read_csv(PRIVATE/'exploratory_year_scores.csv');year_count=0
    for r in by.itertuples(index=False):
        b=frame[frame.year.eq(r.year)];a=metrics.independent_metrics(b,'D2','D2',quad);s=metrics.independent_metrics(b,'stochastic_cal_q50','stochastic_cal',quad)
        for name,val in [('n_eligible',len(b)),('n_common',a['n_interval_available']),('D2_mae',a['mae']),('stochastic_mae',s['mae']),
                         ('D2_coverage90',a['coverage90']),('stochastic_coverage90',s['coverage90'])]:
            metrics.same(val,getattr(r,name),f'{r.year}/{name}');year_count+=1
    result={'status':'passed','cases':len(frame),'reference_years':frame.year.nunique(),'max_truth_difference_c':max_truth,
            'max_observed_bound_difference_c':max_bound,'quantile_support_violations':violations,
            'summary_cells_checked':count,'paired_cells_checked':pair_count,'year_cells_checked':year_count,
            'scope':'Independent rolling-window, mask, score and quadrature arithmetic from the same processed target data and saved predictions; does not retrain source models or establish physical sensor accuracy.',
            'limitations':plan['limitations']}
    (OUT/'exploratory_score_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
