#!/usr/bin/env python3
"""Independently rebuild past-only seasons, states and prior records.

Uses the same current-vintage processed data, original station cohort and
recorded leave-year-out rule; this is not an as-of-vintage field validation.
"""
from __future__ import annotations
import calendar
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
REV=ROOT/'results/wrr_review_response_20261027'
SNAP=REV/'open_observed_record_snapshot'
OUT=REV/'past_season_screening'
GROUPS=REV/'summer_window_comparison/station_groups.csv'
TOL=5e-6

def independent_season(target,year,complete_years):
    historical=target[target.index.year<year]
    historical=historical[np.isfinite(historical.to_numpy(float))]
    n_complete=sum(y<year for y in complete_years)
    if historical.empty:return None,np.nan,0,n_complete
    mean=historical.groupby(historical.index.dayofyear).mean().reindex(range(1,367)).interpolate(limit_direction='both').to_numpy(float)
    padded=np.concatenate([mean[-7:],mean,mean[:7]])
    smooth=np.convolve(padded,np.ones(15)/15,mode='same')[7:-7]
    dates=pd.date_range(f'{year}-01-01',f'{year}-12-31')
    values=smooth[dates.dayofyear.to_numpy()-1]
    if np.isfinite(values).sum()<30:return None,np.nan,len(historical),n_complete
    nonleap=pd.Timestamp('2021-01-01')+pd.to_timedelta(dates.dayofyear.to_numpy()-1,unit='D')
    means=pd.Series(values).groupby(nonleap.month).mean().reindex(range(1,13))
    start=max(range(1,9),key=lambda m:means.loc[m:m+4].mean())
    months=tuple(range(start,start+5))
    fraction=float(np.isfinite(target.reindex(dates).to_numpy(float)[dates.month.isin(months)]).mean())
    return months,fraction,len(historical),n_complete

def main():
    plan=json.loads((OUT/'plan.json').read_text());amend=json.loads((OUT/'multirule_correction.json').read_text())
    years=pd.read_csv(SNAP/'eligible_station_years.csv',dtype={'train_warm_months':str}).merge(pd.read_csv(GROUPS),on='station_key',validate='many_to_one')
    daily=pd.read_parquet(SNAP/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    if daily.duplicated(['station_key','date']).any():raise ValueError('Duplicate daily input')
    stations={key:g.set_index('date').water_c.sort_index().astype(float) for key,g in daily.groupby('station_key',sort=False,observed=True)}
    complete_by_station={}
    for station,target in stations.items():
        full=[]
        for year in sorted(set(target.index.year)):
            index=pd.date_range(f'{year}-01-01',f'{year}-12-31')
            if np.isfinite(target.reindex(index).to_numpy(float)).all():full.append(int(year))
        complete_by_station[station]=full
    saved=pd.read_csv(OUT/'station_year_decisions.csv',dtype={'past_warm_months':str,'loo_warm_months':str})
    index=['station_key','year','rule']
    if saved.duplicated(index).any() or len(saved)!=len(years)*5:raise ValueError('Decision cohort differs')
    lookup=saved.set_index(index);checked=0
    for r in years.itertuples(index=False):
        months,fraction,finite,complete=independent_season(stations[r.station_key],r.year,complete_by_station[r.station_key])
        label=';'.join(map(str,months)) if months else ''
        row=lookup.loc[(r.station_key,r.year,'warm90_past')]
        stored='' if pd.isna(row.past_warm_months) else str(row.past_warm_months)
        if stored!=label or not np.isclose(fraction,row.past_warm_fraction,rtol=0,atol=1e-10,equal_nan=True) or int(row.prior_finite_days)!=finite or int(row.prior_complete_years)!=complete:
            raise ValueError(f'Past-only climatology differs: {r.station_key}/{r.year}')
        iscomplete=bool(r.complete_year)
        def state(frac,prior,mincount):
            if iscomplete:return 'accepted'
            if prior<mincount or not np.isfinite(frac):return 'unknown'
            return 'accepted' if frac>=.9 else 'rejected'
        loo=float(r.train_warm_fraction) if pd.notna(r.train_warm_fraction) else np.nan
        expected={'complete_100':'accepted' if iscomplete else 'rejected',
                  'annual_95':('accepted' if r.observed_fraction>=.95 else 'rejected') if np.isfinite(r.observed_fraction) else 'unknown',
                  'warm90_leave_year_out':state(loo,0,0),'warm90_past':state(fraction,complete,0),
                  'warm90_past_four_complete':state(fraction,complete,4)}
        for rule,val in expected.items():
            if lookup.loc[(r.station_key,r.year,rule),'state']!=val:raise ValueError('Rule state mismatch: '+rule)
        checked+=1
    witnesses=pd.read_csv(SNAP/'observed_record_certificates.csv')[['station_key','incomplete_year']].rename(columns={'incomplete_year':'year'})
    saved_w=pd.read_csv(OUT/'witness_decisions.csv')
    expected_w=saved.merge(witnesses,on=['station_key','year'],how='inner',validate='many_to_one')
    if len(expected_w)!=175 or len(saved_w)!=175:raise ValueError('Witness denominator differs')
    wd=expected_w[index+['state','rejected_above_prior_record']].merge(saved_w[index+['state','rejected_above_prior_record']],on=index,suffixes=('_expected','_saved'),how='outer',indicator=True,validate='one_to_one')
    if not wd._merge.eq('both').all() or not wd.state_expected.eq(wd.state_saved).all() or not wd.rejected_above_prior_record_expected.eq(wd.rejected_above_prior_record_saved).all():
        raise ValueError('Saved witness decisions differ')
    flags=[]
    for (_,station),g in saved.groupby(['rule','station_key'],sort=True):
        g=g.sort_values('year');v=pd.to_numeric(g.reported_window,errors='coerce').to_numpy(float)
        accepted=g.state.eq('accepted').to_numpy()&np.isfinite(v)
        previous=np.r_[-np.inf,np.maximum.accumulate(np.where(accepted,v,-np.inf))[:-1]]
        previous[~np.isfinite(previous)]=np.nan
        if not np.allclose(previous,g.prior_accepted_record.to_numpy(float),rtol=0,atol=1e-10,equal_nan=True):raise ValueError('Historical record differs')
        above=g.state.eq('rejected').to_numpy()&np.isfinite(v)&np.isfinite(previous)&(v>previous+TOL)
        if not np.array_equal(above,g.rejected_above_prior_record.to_numpy(bool)):raise ValueError('Rejected record flag differs')
        flags.append(len(g))
    summary=pd.read_csv(OUT/'summary.csv').set_index('rule')
    for rule,g in saved.groupby('rule'):
        w=expected_w[expected_w.rule.eq(rule)];rejected=g.state.eq('rejected');bound=np.isfinite(g.reported_window.to_numpy(float));prior=np.isfinite(g.prior_accepted_record.to_numpy(float))
        counts={'station_years':len(g),'stations':g.station_key.nunique(),'groups':g.independence_group.nunique(),
                'accepted':int(g.state.eq('accepted').sum()),'rejected':int(rejected.sum()),'unknown':int(g.state.eq('unknown').sum()),
                'rejected_with_bound':int((rejected&bound).sum()),'rejected_with_bound_and_prior_record':int((rejected&bound&prior).sum()),
                'rejected_above_prior_reported_record':int(g.rejected_above_prior_record.sum()),
                'stations_with_rejected_above_prior_record':g.loc[g.rejected_above_prior_record,'station_key'].nunique(),
                'witnesses':len(w),'witness_accepted':int(w.state.eq('accepted').sum()),'witness_rejected':int(w.state.eq('rejected').sum()),
                'witness_unknown':int(w.state.eq('unknown').sum()),'witness_rejected_above_prior_record':int(w.rejected_above_prior_record.sum())}
        for field,val in counts.items():
            if int(summary.loc[rule,field])!=val:raise ValueError('Summary count differs: '+rule+'/'+field)
    observed_transitions=pd.read_csv(OUT/'transitions.csv').set_index(['method','leave_year_out','past']).station_years
    pivot=saved.pivot(index=['station_key','year'],columns='rule',values='state')
    transition_cells=0
    for method in ['warm90_past','warm90_past_four_complete']:
        independent=pivot.groupby(['warm90_leave_year_out',method]).size()
        for (old,new),count in independent.items():
            if int(observed_transitions.loc[(method,old,new)])!=int(count):raise ValueError('State transition differs')
            transition_cells+=1
    if transition_cells!=len(observed_transitions):raise ValueError('Unexpected extra state transition')
    # Probe actual implementation with all current/future water values shifted.
    spec=importlib.util.spec_from_file_location('past_season_impl',ROOT/'scripts/715_past_season_multirule.py')
    impl=importlib.util.module_from_spec(spec);spec.loader.exec_module(impl)
    for r in witnesses.itertuples(index=False):
        target=stations[r.station_key]; altered=target.copy();altered.loc[altered.index.year>=r.year]+=5.
        a=impl.prior_warm(target,r.year);b=impl.prior_warm(altered,r.year)
        if a['months']!=b['months'] or not np.isclose(a['fraction'],b['fraction'],atol=1e-12,rtol=0,equal_nan=True):
            raise ValueError('Future perturbation changed past-only warm season')
    strict_unknown=saved[saved.rule.eq('warm90_past_four_complete') & saved.state.eq('unknown')]
    unknown_bounds=int(np.isfinite(pd.to_numeric(strict_unknown.reported_window,errors='coerce').to_numpy(float)).sum())
    report={'status':'passed','station_years_independently_reconstructed':checked,'rule_decisions_checked':len(saved),
            'prior_record_rows_checked':sum(flags),'witness_decisions_checked':len(expected_w),'transition_cells_checked':transition_cells,
            'four_complete_unknown_with_observed_window':unknown_bounds,
            'target_and_future_perturbation_probes':len(witnesses),'changed_season_probes':0,
            'scope':'Independent rolling day-of-year means and prior-record arithmetic on the same 95-station processed snapshot; 35 future perturbations exercise the original past-only implementation. Current data vintage, station selection, reference metadata and sensor quality are not independently validated.'}
    (OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
