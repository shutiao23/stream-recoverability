#!/usr/bin/env python3
"""Build paired hypothetical day-boundary references from two NS releases.

The true time zone is not inferred. Years with missing, duplicate, nonfinite or
nonmatching boundary hours are unavailable, not filled. No model is scored.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
PRE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_clock_sensitivity'
PRIVATE=ROOT/'private/wrr_nova_scotia_verified_20261026'
DATA=ROOT/'data/external/wrr_nova_scotia_open_20261026'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def build_year(workbook,portal,year,shift,tolerance=1e-6):
    """Return matched daily means or an explicit data-availability status."""
    start=pd.Timestamp(year=year,month=1,day=1)+pd.Timedelta(hours=shift)
    end=pd.Timestamp(year=year+1,month=1,day=1)+pd.Timedelta(hours=shift)
    expected=pd.date_range(start,end,freq='h',inclusive='left')
    arrays=[]
    for label,source in [('workbook',workbook),('portal',portal)]:
        a=source.loc[source.timestamp.isin(expected)].copy()
        if a.timestamp.duplicated(keep=False).any():return None,{'status':'duplicate_hour','source':label,'expected_hours':len(expected),'source_rows':len(a)}
        series=a.set_index('timestamp').value.reindex(expected)
        if len(a)!=len(expected) or not np.isfinite(series.to_numpy(float)).all():
            return None,{'status':'missing_or_nonfinite_hour','source':label,'expected_hours':len(expected),'source_rows':len(a),'finite_hours':int(np.isfinite(series.to_numpy(float)).sum())}
        arrays.append(series.to_numpy(float))
    delta=np.abs(arrays[0]-arrays[1])
    if np.any(delta>tolerance):return None,{'status':'release_disagreement','source':'both','expected_hours':len(expected),'mismatching_hours':int((delta>tolerance).sum()),'max_abs_difference_c':float(delta.max())}
    dates=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left')
    values=arrays[1].reshape(-1,24).mean(axis=1)
    return pd.DataFrame({'date':dates,'temperature_c':values}),{'status':'available','expected_hours':len(expected),'max_abs_difference_c':float(delta.max())}

def main():
    plan=json.loads((OUT/'plan.json').read_text());roster=pd.read_csv(BASE/'reference_year_roster.csv',dtype={'station_id':str})
    receipt=json.loads((PRE/'acquisition.json').read_text());portal=json.loads((PRE/'portal_acquisition.json').read_text())
    if plan['status']!='frozen_posthoc_sensitivity':raise RuntimeError('sensitivity plan not frozen')
    m=module('ns_clock_source',ROOT/'scripts/590_nova_scotia_portal_audit.py')
    base=pd.read_parquet(DATA/'exploratory_selected_reported_daily.parquet');rows=[];daily=[]
    for site,group in roster.groupby('station_id',sort=True):
        items=[x for x in receipt['files'] if x['station_id']==site]
        if len(items)!=1:raise ValueError('missing source workbook receipt')
        item=items[0];path=PRIVATE/item['workbook']
        w,n=m.workbook_records(path);p,n2=m.portal_records(site,portal['pages'])
        if n or n2:raise ValueError('unparseable input timestamps')
        for year in sorted(group.year.astype(int)):
            for shift in plan['shifts_hours']:
                result,status=build_year(w,p,year,int(shift));rows.append({'station_id':site,'year':year,'shift_hours':int(shift),**status})
                if result is None:continue
                result['station_id']=site;result['shift_hours']=int(shift);daily.append(result)
                if shift==0:
                    old=base.loc[base.station_id.eq(site)&base.date.dt.year.eq(year)].sort_values('date')
                    if not old.date.reset_index(drop=True).equals(result.date.reset_index(drop=True)) or not np.allclose(old.temperature_c,result.temperature_c,atol=1e-12,rtol=0):
                        raise ValueError('zero-shift daily reference differs from original')
        print('Checked boundary input availability for',site,flush=True)
    availability=pd.DataFrame(rows);availability.to_csv(OUT/'boundary_year_availability.csv',index=False)
    values=pd.concat(daily,ignore_index=True) if daily else pd.DataFrame(columns=['date','temperature_c','station_id','shift_hours'])
    target=DATA/'clock_sensitivity_reported_daily.parquet'
    if target.exists():
        old=pd.read_parquet(target)
        try:pd.testing.assert_frame_equal(old,values,check_exact=True)
        except AssertionError as exc:raise RuntimeError('existing shifted source output differs; preserve it') from exc
    else:values.to_parquet(target,index=False)
    panel_root=OUT/'panels';panel_root.mkdir(exist_ok=True)
    for (site,shift),block in values.groupby(['station_id','shift_hours']):
        panel=block[['date','temperature_c']].sort_values('date').set_index('date').rename(columns={'temperature_c':site})
        folder=panel_root/f'shift_{int(shift):+d}';folder.mkdir(exist_ok=True);path=folder/f'{site}.csv'
        if path.exists():
            old=pd.read_csv(path,parse_dates=['date']).set_index('date')
            if not old.index.equals(panel.index) or not np.allclose(old[site],panel[site],atol=1e-12,rtol=0):raise RuntimeError('existing sensitivity panel differs')
        else:panel.to_csv(path,index_label='date')
    full=[]
    for (site,shift),group in availability.groupby(['station_id','shift_hours']):
        count=int(group.status.eq('available').sum())
        full.append({'station_id':site,'shift_hours':int(shift),'available_years':count,'expected_years':len(group),'site_fully_available':count==len(group)})
    sites=pd.DataFrame(full);sites.to_csv(OUT/'boundary_site_availability.csv',index=False)
    state={'status':'boundary_inputs_checked','station_year_variants':len(availability),'available_station_year_variants':int(availability.status.eq('available').sum()),
       'full_site_variants':int(sites.site_fully_available.sum()),'total_site_variants':len(sites),
       'model_scoring_performed':(OUT/'score_status.json').exists(),'strict_reference_qualified':False,
       'limitation':plan['limitation']+'; source files are two releases of one programme and may share underlying errors'}
    (OUT/'reference_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(availability.to_string(index=False));print(sites.to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()
