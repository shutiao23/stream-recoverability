#!/usr/bin/env python3
"""Independently audit frozen NS case masks, references and saved scores.

This checks arithmetic using the same reported-clock series and saved
predictions. It does not prove physical-time alignment, sensor quality,
independent climates or absence of leakage in every model feature.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
PRIVATE=ROOT/'private/wrr_nova_scotia_exploratory_20261026'
DATA=ROOT/'data/external/wrr_nova_scotia_open_20261026/exploratory_selected_reported_daily.parquet'
LEVELS=[5,10,25,50,75,90,95]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def same(a,b,name):
    if not np.isclose(a,b,rtol=0,atol=1e-8,equal_nan=True):raise ValueError(f'saved summary differs: {name} ({a} versus {b})')

def independent_metrics(block,column,prefix,quad):
    y=block.eval_truth_h30.to_numpy(float);lower=block.observed_lower_bound__observed_days.to_numpy(float)
    point=block[column].to_numpy(float);point=np.where(np.isfinite(lower),np.maximum(point,lower),point)
    valid=np.isfinite(point)&np.isfinite(y);result={'n_eligible':len(block),'n_point_available':int(valid.sum()),
       'point_availability':float(valid.mean()) if len(block) else np.nan,'n_interval_available':0}
    if valid.any():
        err=point[valid]-y[valid];result.update(mae=float(np.abs(err).mean()),bias=float(err.mean()),failure_rate=float((abs(err)>.5).mean()))
    if prefix:
        q=block[[f'{prefix}_q{x:02d}' for x in LEVELS]].to_numpy(float)
        good=valid&np.isfinite(q).all(axis=1);result['n_interval_available']=int(good.sum())
        if good.any():
            v=q[good];bound=lower[good];truth=y[good];samples,_=quad.quadrature(v,bound)
            lo,hi=v[:,0],v[:,-1];score=hi-lo+20*(np.maximum(lo-truth,0)+np.maximum(truth-hi,0))
            result.update(coverage90=float(((truth>=lo-1e-8)&(truth<=hi+1e-8)).mean()),
                width90=float((hi-lo).mean()),interval_score90=float(score.mean()),crps=float(quad.crps(samples,truth).mean()))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,default=PRIVATE)
    parser.add_argument('--data',type=Path,default=DATA)
    parser.add_argument('--output',type=Path,default=OUT/'integrity_status.json')
    args=parser.parse_args()
    status=json.loads((OUT/'score_status.json').read_text());f=pd.read_parquet(args.evidence/'predictions.parquet')
    if status['status']!='exploratory_scored' or len(f)!=status['cases']:raise ValueError('score status and case count disagree')
    ref=pd.read_parquet(args.data);table=ref.set_index(['station_id','date']).temperature_c
    if table.index.duplicated().any():raise ValueError('duplicate daily reference')
    local=module('independent_mask_arithmetic',ROOT/'scripts/554_bc_reference_integrity.py')
    quad=module('independent_quantile_arithmetic',ROOT/'scripts/576_verify_private_annual_predictions.py')
    max_truth=0.;max_lower=0.;bad_counts=0;nonfinite=0;support=0
    for r in f.itertuples(index=False):
        dates=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31',freq='D')
        ids=pd.MultiIndex.from_product([[str(r.station_id)],dates],names=['station_id','date'])
        values=table.reindex(ids).to_numpy(float);truth,lower,n=local.compute(values,r.mask_runs)
        max_truth=max(max_truth,abs(truth-float(r.eval_truth_h30)));max_lower=max(max_lower,abs(lower-float(r.observed_lower_bound__observed_days)))
        bad_counts+=int(n!=int(r.total_missing) or n!=int(r.gap_length))
        if not np.isfinite(lower):nonfinite+=1
        for prefix in ['D2','stochastic_cal']:
            q=np.array([getattr(r,f'{prefix}_q{x:02d}') for x in LEVELS],float)
            if np.isfinite(q).all():
                if np.any(np.diff(q)<-1e-8) or np.isfinite(lower) and np.any(q<lower-1e-8):support+=1
    if max_truth>1e-8 or max_lower>1e-8 or bad_counts or nonfinite or support:raise ValueError('reference, mask or support integrity failure')
    scored=pd.read_csv(OUT/'score_summary.csv');score_checks=0
    for r in scored.itertuples(index=False):
        b=f if r.stratum=='all' else f.loc[f.peak_overlap.ge(.5)]
        column,prefix={'plug_in':('h30__policy',None),'D2':('D2','D2'),'stochastic_calibrated':('stochastic_cal_q50','stochastic_cal')}[r.estimator]
        for name,value in independent_metrics(b,column,prefix,quad).items():
            same(value,getattr(r,name),f'{r.stratum}/{r.estimator}/{name}');score_checks+=1
    paired=pd.read_csv(OUT/'paired_summary.csv');paired_checks=0
    for r in paired.itertuples(index=False):
        b=f if r.stratum=='all' else f.loc[f.peak_overlap.ge(.5)]
        y=b.eval_truth_h30.to_numpy(float);low=b.observed_lower_bound__observed_days.to_numpy(float)
        a=b.D2.to_numpy(float);s=b.stochastic_cal_q50.to_numpy(float)
        qa=b[[f'D2_q{x:02d}' for x in LEVELS]].to_numpy(float);qs=b[[f'stochastic_cal_q{x:02d}' for x in LEVELS]].to_numpy(float)
        common=np.isfinite(a)&np.isfinite(s)&np.isfinite(y)&np.isfinite(qa).all(axis=1)&np.isfinite(qs).all(axis=1)
        same(int(common.sum()),r.n_common,'paired count');paired_checks+=1
        for prefix,point,q in [('D2',a,qa),('stochastic',s,qs)]:
            v=q[common];yy=y[common];lo=v[:,0];hi=v[:,-1];samples,_=quad.quadrature(v,low[common])
            metrics={'mae':float(np.mean(abs(point[common]-yy))),
              'coverage90':float(np.mean((yy>=lo-1e-8)&(yy<=hi+1e-8))),
              'width90':float(np.mean(hi-lo)),
              'interval_score90':float(np.mean(hi-lo+20*(np.maximum(lo-yy,0)+np.maximum(yy-hi,0)))),
              'crps':float(quad.crps(samples,yy).mean())}
            for key,val in metrics.items():same(val,getattr(r,f'{prefix}_{key}'),f'{r.stratum}/{prefix}/{key}');paired_checks+=1
    byyear=pd.read_csv(OUT/'site_year_summary.csv');year_checks=0
    for r in byyear.itertuples(index=False):
        b=f.loc[f.station_key.eq(r.station_key)&f.year.eq(r.year)]
        same(len(b),r.n_eligible,'year eligible');year_checks+=1
        z=independent_metrics(b,'D2','D2',quad);w=independent_metrics(b,'stochastic_cal_q50','stochastic_cal',quad)
        same(z['n_interval_available'],r.n_common,'year paired count');year_checks+=1
        same(w['n_interval_available'],r.n_common,'year stochastic paired count');year_checks+=1
        for prefix,d in [('D2',z),('stochastic',w)]:
            for name in ['mae','coverage90']:
                same(d[name],getattr(r,f'{prefix}_{name}'),f'year/{prefix}/{name}');year_checks+=1
    state={'status':'passed','cases':len(f),'stations':int(f.station_key.nunique()),'station_years':len(byyear),
       'max_truth_difference_c':max_truth,'max_bound_difference_c':max_lower,'mask_count_mismatches':bad_counts,
       'nonfinite_bound_cases':nonfinite,'quantile_order_or_bound_violations':support,
       'score_summary_cells_checked':score_checks,'paired_summary_cells_checked':paired_checks,'station_year_cells_checked':year_checks,
       'scope':'recomputed daily H30, visible bound, masks and scores using the same saved inputs; no refit or independent sensor validation',
       'limitations':'reported-clock time basis, nonestimated status and sensor quality remain unverified; population and climate independence are not established'}
    args.output.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))

if __name__=='__main__':main()
