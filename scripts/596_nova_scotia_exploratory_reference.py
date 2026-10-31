#!/usr/bin/env python3
"""Build reported-clock daily inputs for a frozen, nonconfirmatory NS experiment."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PRE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
PRIVATE=ROOT/'private/wrr_nova_scotia_verified_20261026'
DATA=ROOT/'data/external/wrr_nova_scotia_open_20261026'

def main():
    plan_path=OUT/'plan.json'
    if not plan_path.is_file():raise RuntimeError('freeze exploratory amendment first')
    plan=json.loads(plan_path.read_text());years=pd.read_csv(OUT/'reference_year_roster.csv',dtype={'station_id':str})
    receipt=json.loads((PRE/'acquisition.json').read_text());portal=json.loads((PRE/'portal_acquisition.json').read_text())
    spec=importlib.util.spec_from_file_location('ns_portal_compare',ROOT/'scripts/590_nova_scotia_portal_audit.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    daily=[];checks=[]
    for site,g in years.groupby('station_id',sort=True):
        candidates=[x for x in receipt['files'] if x['station_id']==site]
        if len(candidates)!=1:raise ValueError('workbook receipt not unique')
        item=candidates[0];path=PRIVATE/item['workbook']
        w,unparsed=m.workbook_records(path);p,p_unparsed=m.portal_records(site,portal['pages'])
        if unparsed or p_unparsed:raise ValueError('numeric input with unparseable timestamp')
        for year in sorted(g.year.astype(int)):
            expected=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='h',inclusive='left')
            a=w.loc[w.timestamp.dt.year.eq(year)].sort_values('timestamp').reset_index(drop=True)
            b=p.loc[p.timestamp.dt.year.eq(year)].sort_values('timestamp').reset_index(drop=True)
            for q in (a,b):
                if len(q)!=len(expected) or q.timestamp.duplicated().any() or not np.array_equal(q.timestamp.to_numpy(),expected.to_numpy()):
                    raise ValueError(f'non-complete reported-hour labels: {site}/{year}')
                if not np.isfinite(q.value.to_numpy(float)).all():raise ValueError('nonfinite selected hour')
            delta=np.abs(a.value.to_numpy(float)-b.value.to_numpy(float))
            if (delta>1e-6).any():raise ValueError('selected workbook and portal observations differ beyond frozen tolerance')
            index=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left')
            day_a=a.value.to_numpy(float).reshape(-1,24).mean(axis=1)
            day_b=b.value.to_numpy(float).reshape(-1,24).mean(axis=1)
            if not np.allclose(day_a,day_b,atol=1e-6,rtol=0):raise ValueError('daily means disagree')
            daily.append(pd.DataFrame({'station_id':site,'date':index,'temperature_c':day_b}))
            checks.append({'station_id':site,'year':year,'hourly_labels':len(expected),'daily_means':len(index),
                           'max_source_difference_c':float(delta.max()),'validated_equal_to_1e6':True})
    data=pd.concat(daily,ignore_index=True)
    if data.duplicated(['station_id','date']).any():raise ValueError('duplicate reported-calendar date')
    DATA.mkdir(parents=True,exist_ok=True);target=DATA/'exploratory_selected_reported_daily.parquet'
    if target.exists():
        old=pd.read_parquet(target)
        try:pd.testing.assert_frame_equal(old,data,check_dtype=True,check_exact=True)
        except AssertionError as exc:raise RuntimeError('existing selected daily reference differs; preserve it') from exc
    else:data.to_parquet(target,index=False)
    (OUT/'panels').mkdir(exist_ok=True)
    for site,g in data.groupby('station_id'):
        panel=g[['date','temperature_c']].set_index('date').rename(columns={'temperature_c':site})
        path=OUT/'panels'/f'{site}.csv'
        if path.exists():
            old=pd.read_csv(path,parse_dates=['date']).set_index('date')
            if not old.index.equals(panel.index) or not np.allclose(old[site],panel[site],rtol=0,atol=1e-12):raise RuntimeError('existing panel differs; preserve it')
        else:panel.to_csv(path,index_label='date')
    pd.DataFrame(checks).to_csv(OUT/'reference_integrity.csv',index=False)
    status={'status':'reported_clock_reference_built','stations':int(data.station_id.nunique()),'station_years':len(checks),'daily_values':len(data),
       'hourly_labels_checked':sum(x['hourly_labels'] for x in checks),'source_comparison_tolerance_c':1e-6,
       'strict_reference_qualified':False,'model_scoring_performed':(OUT/'score_status.json').exists(),
       'limitation':'daily means are means of reported hourly values; timezone, nonestimated status, per-record QA and sensor error remain unresolved; same two releases of one monitoring programme'}
    (OUT/'reference_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(pd.DataFrame(checks).to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()
