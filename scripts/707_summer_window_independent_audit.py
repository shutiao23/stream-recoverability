#!/usr/bin/env python3
"""Recompute summer-window comparisons by a separate rolling implementation.

The same project-processed daily data and previously selected stations are
used; agreement is not independent physical measurement or source-QC proof.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
SNAP=REV/'open_observed_record_snapshot'
OUT=REV/'summer_window_comparison'
TOL=5e-6


def rolling_max(series):
    if len(series)<30:return np.nan
    return float(series.rolling(30,min_periods=30).mean().max())


def main():
    daily=pd.read_parquet(SNAP/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    if daily.duplicated(['station_key','date']).any():raise ValueError('Duplicate snapshot station-days')
    data={k:g.set_index('date').water_c.sort_index().astype(float) for k,g in daily.groupby('station_key',sort=False,observed=True)}
    annual=pd.read_csv(OUT/'complete_year_windows.csv')
    source_years=pd.read_parquet(SNAP/'station_years.parquet')
    source_years=source_years[source_years.complete_year & source_years.truth_h30.notna()]
    keycheck=source_years[['station_key','year','truth_h30']].merge(annual,on=['station_key','year'],how='outer',indicator=True,validate='one_to_one')
    if not keycheck._merge.eq('both').all() or not np.allclose(keycheck.truth_h30,keycheck.full_h30,rtol=0,atol=TOL):
        raise ValueError('Complete reference cohort or source values differ')
    roster=pd.read_csv(SNAP/'source_roster.csv');groupmap=pd.read_csv(OUT/'station_groups.csv')
    metadata=roster[['station_key','provider']].merge(groupmap,on='station_key',validate='one_to_one')
    identity=annual.merge(metadata,on='station_key',suffixes=('_saved','_source'),validate='many_to_one')
    if not identity.provider_saved.eq(identity.provider_source).all() or not identity.independence_group_saved.eq(identity.independence_group_source).all():
        raise ValueError('Saved station provider/group differs')
    rows=[]
    for r in annual.itertuples(index=False):
        dates=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
        s=data[r.station_key].reindex(dates)
        if s.isna().any():raise ValueError('Annual complete reference has missing days')
        full=rolling_max(s);summer=rolling_max(s.loc[s.index.month.isin([7,8])])
        if not np.isclose(full,r.full_h30,atol=1e-10,rtol=0) or not np.isclose(summer,r.summer_h30,atol=1e-10,rtol=0):
            raise ValueError('Annual rolling-window result differs')
        rows.append({'station_key':r.station_key,'year':r.year,'group':r.independence_group,'provider':r.provider,'gap':full-summer})
    x=pd.DataFrame(rows);summary=json.loads((OUT/'summary.json').read_text())
    for key,val in {'complete_station_years':len(x),'stations':x.station_key.nunique(),'connected_groups':x['group'].nunique(),
                    'different_above_tolerance_years':int(x.gap.gt(TOL).sum()),'above_0p1_c_years':int(x.gap.gt(.1).sum()),
                    'above_0p5_c_years':int(x.gap.gt(.5).sum())}.items():
        if summary[key]!=val:raise ValueError('Summary count differs: '+key)
    for key,val in [('mean_gap_c',x.gap.mean()),('median_gap_c',x.gap.median()),('max_gap_c',x.gap.max())]:
        if not np.isclose(summary[key],val,rtol=0,atol=1e-10):raise ValueError('Summary statistic differs: '+key)
    clusters=x.groupby('group',sort=True).gap.agg(['sum','count','mean'])
    rng=np.random.default_rng(705);sample=rng.integers(len(clusters),size=(4000,len(clusters)))
    bs=clusters['sum'].to_numpy()[sample].sum(axis=1)/clusters['count'].to_numpy()[sample].sum(axis=1)
    for key,val in [('equal_group_mean_gap_c',clusters['mean'].mean()),('group_bootstrap_low_c',np.quantile(bs,.025)),('group_bootstrap_high_c',np.quantile(bs,.975))]:
        if not np.isclose(summary[key],val,rtol=0,atol=1e-10):raise ValueError('Group summary differs: '+key)
    station=x.groupby(['station_key','group'],sort=True).gap.agg(['mean','count']).reset_index()
    for key,threshold in [('stations_mean_gap_above_0p1_c',.1),('stations_mean_gap_above_0p5_c',.5)]:
        if summary[key]!=station['mean'].gt(threshold).sum():raise ValueError('Station mean count differs')
    witness=pd.read_csv(OUT/'witness_comparison.csv')
    original_witness=pd.read_csv(SNAP/'observed_record_certificates.csv')
    identities=original_witness[['station_key','incomplete_year']].merge(witness[['station_key','incomplete_year']],on=['station_key','incomplete_year'],how='outer',indicator=True,validate='one_to_one')
    if not identities._merge.eq('both').all():raise ValueError('Witness cohort differs')
    for r in witness.itertuples(index=False):
        index=pd.date_range(f'{r.incomplete_year}-01-01',f'{r.incomplete_year}-12-31')
        s=data[r.station_key].reindex(index);full=rolling_max(s);summer=rolling_max(s.loc[s.index.month.isin([7,8])])
        if not np.isclose(full,r.observed_full_window,atol=1e-10,rtol=0,equal_nan=True) or not np.isclose(summer,r.observed_summer_window,atol=1e-10,rtol=0,equal_nan=True):
            raise ValueError('Witness reported window differs')
    available=witness.summer_window_available
    above=available & (witness.full_minus_summer>TOL)
    for name,value in [('witness_station_years',len(witness)),('witness_summer_window_available',int(available.sum())),
                       ('witness_summer_window_unavailable',int((~available).sum())),('witnesses_full_above_summer',int(above.sum())),
                       ('witness_stations_full_above_summer',witness.loc[above,'station_key'].nunique())]:
        if summary[name]!=value:raise ValueError('Witness summary differs: '+name)
    saved=pd.read_csv(OUT/'screening_counts.csv').set_index('rule')
    years=pd.read_csv(SNAP/'eligible_station_years.csv');groups=pd.read_csv(OUT/'station_groups.csv')
    years=years.merge(groups,on='station_key',validate='many_to_one')
    specs={'complete_100':('complete_year',None),'annual_95':('observed_fraction',.95),
           'warm_90_station_specific':('train_warm_fraction',.90),'july_aug_complete':('julaug_complete',None)}
    for name,(column,threshold) in specs.items():
        g=years.copy();g['known']=g[column].notna()
        g['accepted']=g[column].fillna(False).astype(bool) if threshold is None else pd.to_numeric(g[column],errors='coerce').ge(threshold)
        excluded=g.known&~g.accepted;bounds=excluded&np.isfinite(pd.to_numeric(g.reported_window,errors='coerce'))
        counts={'station_years':len(g),'known':int(g.known.sum()),'accepted':int((g.known&g.accepted).sum()),
                'rejected':int(excluded.sum()),'unknown':int((~g.known).sum()),'rejected_with_observed_30day_bound':int(bounds.sum()),
                'stations_with_rejected_bound':g.loc[bounds,'station_key'].nunique(),'groups_with_rejected_bound':g.loc[bounds,'independence_group'].nunique()}
        for key,value in counts.items():
            if int(saved.loc[name,key])!=value:raise ValueError('Rule count differs: '+name+'/'+key)
    report={'status':'passed','complete_station_years_checked':len(x),'stations_checked':x.station_key.nunique(),
            'witnesses_checked':len(witness),'rule_station_years_checked':len(years),'screening_rules_checked':len(specs),
            'group_bootstrap_resamples_checked':4000,
            'scope':'Pandas rolling calculations, screening counts and connected-group resampling on the same project-processed daily snapshot; not an independent source, sensor or physical error check.'}
    (OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
