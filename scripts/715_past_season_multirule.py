#!/usr/bin/env python3
"""Retrospective screening with warm seasons built from earlier water years.

This uses current-vintage processed data and retrospectively selected stations;
it is not an as-of-vintage prospective test, physical sensor audit, or proof
that a lower bound is the incomplete year's true annual maximum.
"""
from __future__ import annotations
import argparse
import calendar
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels

REV=ROOT/'results/wrr_review_response_20261027'
SNAP=REV/'open_observed_record_snapshot'
OUT=REV/'past_season_screening'
TOL=5e-6
RULES=['complete_100','annual_95','warm90_leave_year_out','warm90_past','warm90_past_four_complete']

def previous_complete_years(target,year):
    previous=target[target.index.year<year]
    valid=np.isfinite(previous.to_numpy(float))
    counts=pd.Series(valid,index=previous.index).groupby(previous.index.year).sum()
    return sum(int(count)==(366 if calendar.isleap(int(y)) else 365) for y,count in counts.items())

def prior_warm(target,year):
    """Same smoothed day-of-year season, using only observations before year."""
    index=pd.date_range(f'{year}-01-01',f'{year}-12-31')
    past=target.index.year<year
    n_past=int(np.isfinite(target.to_numpy(float)[past]).sum())
    n_complete=previous_complete_years(target,year)
    if not n_past:return {'months':None,'fraction':np.nan,'prior_finite_days':0,'prior_complete_years':n_complete}
    mask=pd.Series(past,index=target.index)
    climate=StationModels(target=target,donors=pd.DataFrame(index=target.index),air=None,train_mask=mask).smooth_climatology(index)
    if np.isfinite(climate).sum()<30:return {'months':None,'fraction':np.nan,'prior_finite_days':n_past,'prior_complete_years':n_complete}
    months=T.hottest_months(climate,index.dayofyear.to_numpy(),5)
    within=index.month.isin(months)
    fraction=float(np.isfinite(target.reindex(index).to_numpy(float)[within]).mean())
    return {'months':tuple(months),'fraction':fraction,'prior_finite_days':n_past,'prior_complete_years':n_complete}

def warm_state(complete,fraction,prior_complete,minimum):
    if complete:return 'accepted'
    if prior_complete<minimum or not np.isfinite(fraction):return 'unknown'
    return 'accepted' if fraction>=.9 else 'rejected'

def annotate_records(frame):
    """Compare to the greatest previously accepted observed-window value."""
    x=frame.sort_values(['station_key','year']).copy()
    if x.duplicated(['rule','station_key','year']).any():raise ValueError('Duplicate rule/station/year')
    x['prior_accepted_record']=np.nan;x['rejected_above_prior_record']=False
    for _,ids in x.groupby(['rule','station_key'],sort=False).groups.items():
        best=np.nan
        for pos in ids:
            row=x.loc[pos];bound=float(row.reported_window) if pd.notna(row.reported_window) else np.nan
            x.at[pos,'prior_accepted_record']=best
            x.at[pos,'rejected_above_prior_record']=bool(row.state=='rejected' and np.isfinite(bound) and np.isfinite(best) and bound>best+TOL)
            if row.state=='accepted' and np.isfinite(bound):best=max(best,bound) if np.isfinite(best) else bound
    return x

def compute():
    plan=json.loads((OUT/'plan.json').read_text())
    years=pd.read_csv(SNAP/'eligible_station_years.csv',dtype={'train_warm_months':str})
    group=pd.read_csv(REV/'summer_window_comparison/station_groups.csv')
    years=years.merge(group,on='station_key',validate='many_to_one')
    if years.duplicated(['station_key','year']).any() or years.independence_group.isna().any():raise ValueError('Invalid station-year cohort')
    daily=pd.read_parquet(SNAP/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    if daily.duplicated(['station_key','date']).any():raise ValueError('Duplicate daily records')
    if ((~np.isfinite(daily.water_c.to_numpy(float))) & (~pd.isna(daily.water_c.to_numpy(float)))).any():raise ValueError('Nonfinite nonmissing daily values')
    stations={k:g.set_index('date').water_c.sort_index() for k,g in daily.groupby('station_key',sort=False,observed=True)}
    rows=[]
    for r in years.itertuples(index=False):
        calculation=prior_warm(stations[r.station_key],r.year)
        fraction=calculation['fraction'];n=calculation['prior_complete_years'];complete=bool(r.complete_year)
        loo_fraction=float(r.train_warm_fraction) if pd.notna(r.train_warm_fraction) else np.nan
        annual_state=('accepted' if r.observed_fraction>=.95 else 'rejected') if np.isfinite(r.observed_fraction) else 'unknown'
        states={'complete_100':'accepted' if complete else 'rejected',
                'annual_95':annual_state,
                'warm90_leave_year_out':warm_state(complete,loo_fraction,0,0),
                'warm90_past':warm_state(complete,fraction,n,0),
                'warm90_past_four_complete':warm_state(complete,fraction,n,4)}
        for rule,state in states.items():
            rows.append({'station_key':r.station_key,'year':int(r.year),'independence_group':r.independence_group,
                         'rule':rule,'state':state,'complete_year':complete,'reported_window':r.reported_window,
                         'prior_complete_years':n,'prior_finite_days':calculation['prior_finite_days'],
                         'past_warm_fraction':fraction,'past_warm_months':';'.join(map(str,calculation['months'])) if calculation['months'] else '',
                         'loo_warm_fraction':loo_fraction,'loo_warm_months':r.train_warm_months if pd.notna(r.train_warm_months) else ''})
    decisions=annotate_records(pd.DataFrame(rows))
    witnesses=pd.read_csv(SNAP/'observed_record_certificates.csv')[['station_key','incomplete_year']].rename(columns={'incomplete_year':'year'})
    if len(witnesses)!=35 or witnesses.duplicated(['station_key','year']).any():raise ValueError('Original witness set changed')
    w=decisions.merge(witnesses,on=['station_key','year'],how='inner',validate='many_to_one')
    if len(w)!=35*len(RULES):raise ValueError('Witness decision cohort incomplete')
    summary=[]
    for rule,g in decisions.groupby('rule',sort=True):
        sub=w[w.rule.eq(rule)]
        rejected=g.state.eq('rejected');finite=np.isfinite(g.reported_window.to_numpy(float));prior=np.isfinite(g.prior_accepted_record.to_numpy(float))
        r={'rule':rule,'station_years':len(g),'stations':g.station_key.nunique(),'groups':g.independence_group.nunique(),
           'accepted':int(g.state.eq('accepted').sum()),'rejected':int(rejected.sum()),'unknown':int(g.state.eq('unknown').sum()),
           'rejected_with_bound':int((rejected & finite).sum()),'rejected_with_bound_and_prior_record':int((rejected & finite & prior).sum()),
           'rejected_above_prior_reported_record':int(g.rejected_above_prior_record.sum()),
           'stations_with_rejected_above_prior_record':g.loc[g.rejected_above_prior_record,'station_key'].nunique(),
           'witnesses':len(sub),'witness_accepted':int(sub.state.eq('accepted').sum()),
           'witness_rejected':int(sub.state.eq('rejected').sum()),'witness_unknown':int(sub.state.eq('unknown').sum()),
           'witness_rejected_above_prior_record':int(sub.rejected_above_prior_record.sum())}
        summary.append(r)
    piv=decisions.pivot(index=['station_key','year'],columns='rule',values='state')
    transitions=[]
    for method in ['warm90_past','warm90_past_four_complete']:
        counts=piv.groupby(['warm90_leave_year_out',method],dropna=False).size()
        transitions.extend({'method':method,'leave_year_out':a,'past':b,'station_years':int(v)} for (a,b),v in counts.items())
    return decisions,w,pd.DataFrame(summary),pd.DataFrame(transitions)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT);a=p.parse_args()
    decisions,w,summary,transitions=compute();a.output.mkdir(parents=True,exist_ok=True)
    decisions.to_csv(a.output/'station_year_decisions.csv',index=False)
    w.to_csv(a.output/'witness_decisions.csv',index=False)
    summary.to_csv(a.output/'summary.csv',index=False)
    transitions.to_csv(a.output/'transitions.csv',index=False)
    report={'status':'computed','stations':decisions.station_key.nunique(),'station_years':int(len(decisions)/len(RULES)),
            'witnesses':w[['station_key','year']].drop_duplicates().shape[0],
            'limits':'Current-vintage source data and retrospectively selected stations. Past-only climatology does not reconstruct historical data vintages; accepted prior incomplete years may hide higher annual H30.'}
    (a.output/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':main()
