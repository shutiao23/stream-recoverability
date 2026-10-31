#!/usr/bin/env python3
"""Independently reconstruct two history-climatology lag correlations."""
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'

def direct_phi(series,years,months):
    selected=series[series.index.year.isin(years)]
    finite=selected.dropna();day=finite.index.dayofyear.to_numpy();values=finite.to_numpy(float)
    sums=np.bincount(day,weights=values,minlength=367);counts=np.bincount(day,minlength=367)
    full=np.arange(1,367);known=full[counts[1:]>0]
    if not len(known):return np.nan,0
    climate=np.interp(full,known,sums[known]/counts[known]);padded=np.r_[climate[-7:],climate,climate[:7]]
    smooth=np.convolve(padded,np.full(15,1/15),mode='same')[7:-7]
    anomalies=selected.to_numpy(float)-smooth[selected.index.dayofyear.to_numpy()-1]
    anomalies[~selected.index.month.isin(months)]=np.nan
    x=anomalies[:-1];y=anomalies[1:];valid=np.isfinite(x)&np.isfinite(y);x=x[valid];y=y[valid]
    if len(x)<=10:return np.nan,len(x)
    x=x-x.mean();y=y-y.mean();return float(np.dot(x,y)/math.sqrt(np.dot(x,x)*np.dot(y,y))),len(x)

def main():
    h=T.load_script('usace_phi_independent_helpers',ROOT/'scripts/856_partial_history_feature_support_plan.py');plan=json.loads((OUT/'partial_history_autocorrelation_plan.json').read_text());status=json.loads((OUT/'partial_history_autocorrelation_status.json').read_text())
    path=PRIVATE/'partial_history_autocorrelation_sensitivity.csv'
    expected=pd.read_csv(path).set_index(['resource_id','year']);roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');cases=pd.read_parquet(PRIVATE/'partial_history_scored_cases.parquet')
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day);support=pd.read_csv(PRIVATE/'partial_history_feature_support.csv').set_index('feature').loc['law_phi_a'];lo=float(support.source_min);hi=float(support.source_max)
    rows=[]
    for r in roster.itertuples(index=False):
        panel=pd.read_csv(PRIVATE/'partial_history_predictions'/r.resource_id/str(r.year)/'panel.csv',parse_dates=['date']).set_index('date')[r.resource_id].astype(float)
        raw=daily[daily.resource_id.eq(r.resource_id)].set_index('day').mean_c.reindex(panel.index).astype(float);years=[int(x) for x in r.history_years.split(';')]
        c=cases[cases.resource_id.eq(r.resource_id)&cases.year.eq(r.year)];months=[int(x) for x in c.warm_months.iloc[0].split(';')]
        ip,ni=direct_phi(panel,years,months);ob,no=direct_phi(raw,years,months);e=expected.loc[(r.resource_id,r.year)]
        for key,val in [('phi_interpolated',ip),('phi_observed_only',ob),('change_interpolated_minus_observed',ip-ob),('pairs_interpolated',ni),('pairs_observed_only',no)]:
            if not np.isclose(val,e[key],atol=1e-10,rtol=0,equal_nan=True):raise AssertionError('Mismatch '+key)
        rows.append((np.isfinite(ip) and ip<lo or ip>hi,np.isfinite(ob) and ob<lo or ob>hi))
    rows=np.asarray(rows,bool)
    checks={'target_years':len(rows),'interpolated_phi_outside_training_range_years':int(rows[:,0].sum()),'observed_only_phi_outside_training_range_years':int(rows[:,1].sum()),
            'both_outside_years':int((rows[:,0]&rows[:,1]).sum()),'interpolated_outside_observed_inside_years':int((rows[:,0]&~rows[:,1]).sum())}
    if any(status[k]!=v for k,v in checks.items()):raise AssertionError('Autocorrelation aggregate differs')
    result={'status':'passed',**checks,'scope':'Independent day-of-year accumulation, linear interpolation, 15-day smoothing and scalar Pearson correlation for both history treatments.',
      'limits':'Same fixed history roster, season and source inputs are reused; this does not establish sensor quality, predictive validity, causal attribution or independent climates.'}
    (OUT/'partial_history_autocorrelation_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
