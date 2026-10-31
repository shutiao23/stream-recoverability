#!/usr/bin/env python3
"""Replay the bounded-H30 and record screens from public-source snapshots."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'
RESULTS=ROOT/'results/wrr_review_response_20261027'
SOURCE=RESULTS/'external_usace_reservoir'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def compare(a,b):
    x=pd.read_csv(a).sort_values(['resource_id','year']).reset_index(drop=True)
    y=pd.read_csv(b).sort_values(['resource_id','year']).reset_index(drop=True)
    pd.testing.assert_frame_equal(x,y,check_dtype=False,rtol=0,atol=1e-10)


def check_daily():
    saved=pd.read_parquet(DATA/'finite_daily.parquet')
    saved['day']=pd.to_datetime(saved.day)
    saved=saved[saved.day.dt.year.between(2021,2025)].sort_values(['resource_id','day']).reset_index(drop=True)
    pieces=[]
    for item in json.loads((DATA/'manifest.json').read_text())['records']:
        x=pd.read_csv(DATA/item['file'],compression='gzip',dtype=str)
        x['time']=pd.to_datetime(x.timestamp,errors='raise')
        if x.time.dt.tz is not None:x['time']=x.time.dt.tz_convert('Etc/GMT+7').dt.tz_localize(None)
        x=x[x.time.dt.year.between(2021,2025)].copy()
        x['day']=x.time.dt.normalize()
        x['grid']=x.time.dt.minute.mod(15).eq(0)&x.time.dt.second.eq(0)&x.time.dt.microsecond.eq(0)
        v=pd.to_numeric(x.temp_degC,errors='coerce')
        x['value']=v.where(np.isfinite(v)&v.between(-5,50))
        by=x.groupby('day').agg(rows=('time','size'),unique=('time','nunique'),grid=('grid','sum'),finite=('value','count'),mean_c=('value','mean'))
        good=by.rows.eq(96)&by.unique.eq(96)&by.grid.eq(96)&by.finite.eq(96)
        z=by.loc[good,['mean_c']].reset_index();z['resource_id']=item['resource_id'];pieces.append(z)
    actual=pd.concat(pieces,ignore_index=True).sort_values(['resource_id','day']).reset_index(drop=True)
    if not actual[['resource_id','day']].equals(saved[['resource_id','day']]) or not np.allclose(actual.mean_c,saved.mean_c,atol=1e-10,rtol=0):
        raise AssertionError('Complete daily values do not reproduce from original extracts')
    return len(actual)


def main():
    daily_checked=check_daily()
    with tempfile.TemporaryDirectory(prefix='usace_bounds_replay_') as temp:
        temp=Path(temp);out=temp/'results';private=temp/'private';out.mkdir();private.mkdir()
        for name in ['partial_year_bounds_plan.json','finite_reference_years.csv','finite_reference_independent_audit.json',
                     'partial_year_record_screen_plan.json','partial_year_bounds_independent_audit.json']:
            shutil.copyfile(SOURCE/name,out/name)
        b=module('public_usace_bounds',ROOT/'scripts/830_usace_partial_year_h30_bounds.py')
        b.OUT=out;b.PRIVATE=private;b.DATA=DATA;b.run()
        compare(private/'partial_year_h30_bounds.csv',DATA/'partial_year_h30_bounds.csv')
        # The record plan hashes the original frozen derived table and complete-day
        # file, which have just been checked against the raw-source replay.
        shutil.copyfile(DATA/'partial_year_h30_bounds.csv',private/'partial_year_h30_bounds.csv')
        shutil.copyfile(DATA/'finite_daily.parquet',private/'finite_daily.parquet')
        r=module('public_usace_records',ROOT/'scripts/832_usace_bound_record_screen.py')
        r.OUT=out;r.PRIVATE=private;r.run()
        compare(private/'partial_year_record_screen.csv',DATA/'partial_year_record_screen.csv')
        counts=json.loads((out/'partial_year_record_screen_status.json').read_text())
        result={'status':'passed','resources':counts['resources'],'station_years':counts['station_years'],
                'guaranteed_added_record_years_95':counts['rules']['95']['guaranteed_added_record_years'],
                'complete_days_recomputed':daily_checked,
                'scope':'Replayed bounds and complete-day means from ten two-column source snapshots, and reproduced record screening.',
                'limitations':'Assumed range, source quality and model accuracy remain unverified.'}
    target=RESULTS/'audit/usace_bounds_open_replay.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
