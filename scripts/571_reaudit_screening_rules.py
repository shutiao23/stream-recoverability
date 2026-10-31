#!/usr/bin/env python3
"""Recompute witness screening from local reported daily water values.

This checks rule arithmetic and target-year noninterference on the same
canonical archive. It does not establish sensor accuracy or validate H30
rules in literature that used different targets.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels

ROOT=T.ROOT
SCRIPT_ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'results/wrr_review_response_20261027/audit'
RULES=ROOT/'results/wrr_review_response_20261027/rules'
SOURCE=ROOT/'results/wrr_review_completion_20261024/observed_records'


def longest_missing(values):
    bad=~np.isfinite(np.asarray(values,float))
    starts=np.flatnonzero(bad & ~np.r_[False,bad[:-1]])
    ends=np.flatnonzero(bad & ~np.r_[bad[1:],False])+1
    return int((ends-starts).max()) if len(starts) else 0


def audit():
    years=pd.read_csv(RULES/'eligible_station_years.csv',dtype={'station_key':str,'train_warm_months':str})
    if years.duplicated(['station_key','year']).any():raise ValueError('duplicate eligible station-year')
    eligible=years.station_key.unique().tolist()
    daily=pd.read_parquet(ROOT/'scratch/wrr_target_recovery_20261021/archive_daily.parquet',
       columns=['station_key','date','water_c'],filters=[('station_key','in',eligible)])
    if daily.duplicated(['station_key','date']).any():raise ValueError('duplicate daily observations')
    series={k:g.set_index('date').water_c.sort_index() for k,g in daily.groupby('station_key',observed=True)}
    spec=importlib.util.spec_from_file_location('independent_window',SCRIPT_ROOT/'scripts/570_reaudit_observed_records.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rows=[];fraction_maxdiff=0.;warm_maxdiff=0.
    for r in years.itertuples(index=False):
        idx=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31');v=series[r.station_key].reindex(idx).to_numpy(float)
        finite=np.isfinite(v);fraction=float(finite.mean());diff=abs(fraction-r.observed_fraction);fraction_maxdiff=max(fraction_maxdiff,diff)
        if diff>1e-8:raise ValueError(f'annual coverage mismatch {r.station_key}/{r.year}')
        longest=longest_missing(v)
        if longest!=int(r.longest_run):raise ValueError(f'gap length mismatch {r.station_key}/{r.year}')
        julaug=bool(finite[idx.month.isin([7,8])].all())
        if julaug!=bool(r.julaug_complete):raise ValueError(f'July/August completeness mismatch {r.station_key}/{r.year}')
        if bool(finite.all())!=bool(r.complete_year):raise ValueError(f'complete-year mismatch {r.station_key}/{r.year}')
        if pd.notna(r.train_warm_months) and str(r.train_warm_months).strip():
            months=[int(z) for z in str(r.train_warm_months).split(';')]
            active=idx.month.isin(months);warm=float(finite[active].mean())
            diff=abs(warm-r.train_warm_fraction);warm_maxdiff=max(warm_maxdiff,diff)
            if diff>1e-8:raise ValueError(f'warm coverage mismatch {r.station_key}/{r.year}')
        else:warm=np.nan
        window,_=m.maximum_window(v)
        if not np.isclose(window,r.reported_window,atol=5e-6,rtol=0,equal_nan=True):raise ValueError(f'reported-window mismatch {r.station_key}/{r.year}')
        rows.append(dict(station_key=r.station_key,year=int(r.year),complete_100=bool(finite.all()),annual_95=fraction>=.95,
                         warm_90_station_specific=bool(np.isfinite(warm) and warm>=.9),
                         warm_90_fixed_original=bool(r.warm_observed_fraction>=.9),
                         july_aug_complete=julaug,gap_le_49_days_context=longest<=49,reported_window=window))
    calculated=pd.DataFrame(rows);witness=pd.read_csv(SOURCE/'observed_record_certificates.csv')
    original=pd.read_csv(RULES/'witness_rules.csv');reconstructed=[]
    for rule in ['complete_100','annual_95','warm_90_station_specific','warm_90_fixed_original','july_aug_complete','gap_le_49_days_context']:
        maxima=calculated.loc[calculated[rule]&calculated.reported_window.notna()].groupby('station_key').reported_window.max()
        w=witness.merge(calculated[['station_key','year',rule]],left_on=['station_key','incomplete_year'],right_on=['station_key','year'],validate='one_to_one')
        reference=w.station_key.map(maxima);excluded=(~w[rule])&(w.observed_window_mean>reference+5e-6)
        saved=original.loc[original.rule.eq(rule)].merge(w[['station_key','incomplete_year',rule]],on=['station_key','incomplete_year'],validate='one_to_one')
        if len(saved)!=len(w) or not saved.passes_rule.eq(saved[rule]).all():raise ValueError(f'witness admissions differ for {rule}')
        aligned=w[['station_key','incomplete_year']].copy();aligned['new_excluded_above']=excluded.to_numpy()
        saved=saved.merge(aligned,on=['station_key','incomplete_year'],validate='one_to_one')
        if not saved.excluded_exceeds_accepted_observed_record.eq(saved.new_excluded_above).all():raise ValueError(f'record comparison differs for {rule}')
        reconstructed.append(dict(rule=rule,witness_years=len(w),admitted_witness_years=int(w[rule].sum()),
                                  excluded_witness_years=int((~w[rule]).sum()),admitted_witness_stations=int(w.loc[w[rule],'station_key'].nunique()),
                                  excluded_exceed_reported_record=int(excluded.sum()),
                                  excluded_exceed_reported_record_stations=int(w.loc[excluded,'station_key'].nunique())))
    new=pd.DataFrame(reconstructed);stored=pd.read_csv(RULES/'rule_summary.csv')
    c=new.merge(stored,on='rule',suffixes=('_new','_old'),validate='one_to_one')
    for column in [x for x in new.columns if x!='rule']:
        if not c[column+'_new'].eq(c[column+'_old']).all():raise ValueError(f'rule summary differs: {column}')
    # Perturb the entire held year's observed values. The source station's
    # leave-target-year-out climatology must not change in these probes.
    max_climate_diff=0.;changed=0
    for r in witness.itertuples(index=False):
        target=series[r.station_key];index=pd.date_range(f'{r.incomplete_year}-01-01',f'{r.incomplete_year}-12-31')
        train=pd.Series(target.index.year!=r.incomplete_year,index=target.index)
        base=StationModels(target=target,donors=pd.DataFrame(index=target.index),air=None,train_mask=train).smooth_climatology(index)
        modified=target.copy();modified.loc[modified.index.year==r.incomplete_year]+=5.
        other=StationModels(target=modified,donors=pd.DataFrame(index=target.index),air=None,train_mask=train).smooth_climatology(index)
        if not np.allclose(base,other,atol=1e-9,rtol=0,equal_nan=True):changed+=1
        finite=np.isfinite(base)&np.isfinite(other)
        if finite.any():max_climate_diff=max(max_climate_diff,float(np.max(abs(base[finite]-other[finite]))))
        warm=T.hottest_months(base,index.dayofyear.to_numpy(),5)
        saved_months=years.loc[years.station_key.eq(r.station_key)&years.year.eq(r.incomplete_year),'train_warm_months'].iloc[0]
        if tuple(map(int,str(saved_months).split(';')))!=tuple(warm):raise ValueError(f'warm month definition mismatch {r.station_key}/{r.incomplete_year}')
    if changed:raise ValueError(f'{changed} target-year perturbation probes changed climatology')
    return {'eligible_stations':len(eligible),'station_years_checked':len(years),'witnesses_checked':len(witness),
            'rules_checked':len(new),'witness_rule_decisions_checked':len(witness)*len(new),
            'target_year_perturbation_probes':len(witness),'changed_climatology_probes':changed,
            'max_climatology_difference':max_climate_diff,'max_annual_coverage_difference':fraction_maxdiff,
            'max_warm_coverage_difference':warm_maxdiff,'rule_totals_match':True,'passed':True,
            'limitations':'fixed-original warm fraction is taken from saved source metadata; perturbation checks only witness years; same canonical archive, not external raw or independent climate validation'}


def main():
    AUDIT.mkdir(parents=True,exist_ok=True)
    try:report=audit()
    except Exception as exc:report={'passed':False,'error':f'{type(exc).__name__}: {exc}'}
    (AUDIT/'screening_rule_reaudit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
