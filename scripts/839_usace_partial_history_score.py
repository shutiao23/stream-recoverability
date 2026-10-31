#!/usr/bin/env python3
"""Score fixed predictions against interval-valued, assumption-dependent references."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'
ESTIMATORS={'plug_in':'h30__policy','D2':'D2','stochastic':'stochastic_cal_q50'}

def error_bounds(p,l,u):
    return np.maximum.reduce([l-p,np.zeros_like(p),p-u]),np.maximum(np.abs(p-l),np.abs(p-u))

def pair_bounds(p,q,l,u):
    points=np.stack([l,u,np.clip(p,l,u),np.clip(q,l,u)],axis=1)
    differences=np.abs(p[:,None]-points)-np.abs(q[:,None]-points)
    return differences.min(axis=1),differences.max(axis=1)

def inputs():
    runner=T.load_script('usace_partial_score_runner',ROOT/'scripts/838_usace_partial_history_predict.py');runner.verified()
    status=json.loads((OUT/'partial_history_predictions_status.json').read_text())
    probe=json.loads((OUT/'partial_history_hidden_probe_status.json').read_text())
    if status['status']!='predictions_complete_not_scored' or probe['status']!='passed':raise ValueError('Predictions or leakage probe incomplete')
    roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');receipts={}
    for r in roster.itertuples(index=False):
        root=PRIVATE/'partial_history_predictions'/r.resource_id/str(r.year);receipt=json.loads((root/'receipt.json').read_text())
    return runner,roster,receipts

def freeze():
    path=OUT/'partial_history_scoring_plan.json'
    if path.exists():raise FileExistsError('Preserve scoring plan')
    runner,roster,receipts=inputs();dest=PRIVATE/'partial_history_score_receipts.json'
    dest.write_text(json.dumps(receipts,sort_keys=True,indent=2)+'\n');dest.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc scoring procedure fixed after H30 reference bounds and one target prediction were examined for leakage; before reference-versus-prediction errors were calculated',
      'analysis':'Use all 17 fixed target years, retaining all controlled masks and unavailable outputs. Pair plug-in, D2, stochastic on common finite predictions. Compare each prediction with the full conditional H30 reference interval, not its midpoint.',
      'point_loss':'For p and [L,U], absolute error is bounded below by distance to the interval and above by max distance to endpoints. Report mean bounds, threshold exceedance lower and upper rates and biases [mean(p-U), mean(p-L)].',
      'interval_coverage':'For D2 and stochastic q05/q95, definite coverage requires the predictive interval to contain the entire reference interval; possible coverage requires overlap. Report both, predictive width and availability.',
      'pair_contrast':'For D2 minus comparator absolute error, calculate extrema over [L,U] at endpoints and clipped predictions; average per-case extrema. Because masks share station-year truth, the average is a conservative bound and may not be jointly attainable.',
      'subgroups':'All common cases and posthoc reference-width<=0.1 C subset. Subgroup and target quality were examined before this plan, so no confirmatory independence or selected-case prevalence claim.',
      'limitations':'Source H30 intervals depend on the fixed missing-value range; real data may be corrected; climate and river-network independence, sample count and model support remain unresolved. Incomplete histories are explicitly interpolated, while zero observed complete histories lies outside original model regime. Repeated masks are not independent years.',
      }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen bounded-reference scoring')

def run():
    runner,roster,receipts=inputs();p=json.loads((OUT/'partial_history_scoring_plan.json').read_text())
    if json.loads((PRIVATE/'partial_history_score_receipts.json').read_text())!=receipts:raise ValueError('Receipt mapping changed')
    allcases=[]
    for row in roster.itertuples(index=False):
        data=pd.read_parquet(PRIVATE/'partial_history_predictions'/row.resource_id/str(row.year)/'predictions.parquet')
        data['resource_id']=row.resource_id;allcases.append(data)
    cases=pd.concat(allcases,ignore_index=True)
    bounds=pd.read_csv(DATA/'partial_year_h30_bounds.csv')[['resource_id','year','h30_lower_c','h30_upper_c','h30_interval_width_c']]
    cases=cases.merge(bounds,on=['resource_id','year'],how='left',validate='many_to_one')
    if cases.h30_lower_c.isna().any() or (cases.h30_lower_c>cases.h30_upper_c+1e-10).any():raise ValueError('Missing or invalid reference bounds')
    if cases.duplicated(['resource_id','year','realization_id']).any():raise ValueError('Duplicate target case')
    for label,col in ESTIMATORS.items():
        x=pd.to_numeric(cases[col],errors='coerce').to_numpy(float);l=cases.h30_lower_c.to_numpy(float);u=cases.h30_upper_c.to_numpy(float)
        low,up=error_bounds(x,l,u);cases[label+'_err_low']=low;cases[label+'_err_high']=up
        cases[label+'_bias_low']=x-u;cases[label+'_bias_high']=x-l
    common=np.logical_and.reduce([np.isfinite(pd.to_numeric(cases[c],errors='coerce')) for c in ESTIMATORS.values()])
    cases['common']=common
    for label,prefix in [('D2','D2'),('stochastic','stochastic_cal')]:
        lo=cases[prefix+'_q05'].to_numpy(float);hi=cases[prefix+'_q95'].to_numpy(float)
        valid=np.isfinite(lo)&np.isfinite(hi);l=cases.h30_lower_c.to_numpy(float);u=cases.h30_upper_c.to_numpy(float)
        if np.any(valid&(lo>hi+1e-10)):raise ValueError('Unordered prediction interval')
        cases[label+'_interval_finite']=valid;cases[label+'_definite_coverage']=valid&(lo<=l+1e-10)&(hi>=u-1e-10)
        cases[label+'_possible_coverage']=valid&(lo<=u+1e-10)&(hi>=l-1e-10);cases[label+'_interval_width']=hi-lo
    summaries=[];pairs=[]
    for name,sub in [('all',cases),('reference_width_at_most_0.1_posthoc',cases[cases.h30_interval_width_c.le(.1+1e-12)])]:
        common_sub=sub[sub.common]
        for label,column in ESTIMATORS.items():
            available=np.isfinite(pd.to_numeric(sub[column],errors='coerce'));g=common_sub
            row={'cohort':name,'estimator':label,'target_cases':len(sub),'available_cases':int(available.sum()),
                 'common_cases':len(g),'common_station_years':len(g[['resource_id','year']].drop_duplicates()),'common_sites':g.resource_id.nunique(),
                 'mae_lower_c':g[label+'_err_low'].mean(),'mae_upper_c':g[label+'_err_high'].mean(),
                 'bias_lower_c':g[label+'_bias_low'].mean(),'bias_upper_c':g[label+'_bias_high'].mean(),
                 'failure_rate_definite':(g[label+'_err_low']>.5).mean() if len(g) else np.nan,
                 'failure_rate_possible':(g[label+'_err_high']>.5).mean() if len(g) else np.nan}
            if label!='plug_in':
                gg=g[g[label+'_interval_finite']]
                row.update(interval_common_cases=len(gg),coverage_definite=gg[label+'_definite_coverage'].mean(),
                           coverage_possible=gg[label+'_possible_coverage'].mean(),mean_interval_width_c=gg[label+'_interval_width'].mean())
            summaries.append(row)
        if len(common_sub):
            l=common_sub.h30_lower_c.to_numpy(float);u=common_sub.h30_upper_c.to_numpy(float);x=common_sub.D2.to_numpy(float)
            for label in ['plug_in','stochastic']:
                y=common_sub[ESTIMATORS[label]].to_numpy(float);low,high=pair_bounds(x,y,l,u)
                pairs.append({'cohort':name,'contrast':'D2_minus_'+label,'common_cases':len(common_sub),
                              'mean_absolute_error_difference_lower_c':low.mean(),'mean_absolute_error_difference_upper_c':high.mean()})
    summary=pd.DataFrame(summaries);paired=pd.DataFrame(pairs)
    summary.to_csv(OUT/'partial_history_score_summary.csv',index=False);paired.to_csv(OUT/'partial_history_score_pairs.csv',index=False)
    local=PRIVATE/'partial_history_scored_cases.parquet';cases.to_parquet(local,index=False);local.chmod(0o600)
    result={'status':'completed_exploratory_bounded_scoring','resources':int(cases.resource_id.nunique()),'target_station_years':len(roster),'cases':len(cases),
      'common_finite_cases':int(common.sum()),'strict_reference_qualified':False,'independent_climate_established':False,
      'limitations':p['limitations']}
    (OUT/'partial_history_score_status.json').write_text(json.dumps(result,indent=2)+'\n');print(summary.to_string(index=False));print(paired.to_string(index=False));print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
