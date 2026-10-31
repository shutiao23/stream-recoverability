#!/usr/bin/env python3
"""Independently verify approved-USGS reference years and witness windows.

This uses saved provider API payloads and local-day metadata. It checks the
reported daily series, not subdaily sampling completeness or sensor accuracy.
"""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'results/wrr_review_response_20261027/audit'


def local_day(value,zone):
    text=str(value);stamp=pd.Timestamp(text)
    if len(text)!=10 and stamp.tzinfo is not None:
        if not zone:raise ValueError('Timezone unavailable')
        stamp=stamp.tz_convert(zone).tz_localize(None)
    return stamp.normalize()


def has_estimate(value):
    text=';'.join(map(str,value)) if isinstance(value,list) else (str(value) if value is not None else '')
    return bool(re.search(r'(?i)(?:estimated|(?:^|;)e(?:;|$))',text))


def approved_values(features,zone):
    rows=[]
    for feature in features:
        p=feature.get('properties',feature)
        try:value=float(p.get('value'))
        except (TypeError,ValueError):value=np.nan
        rows.append((local_day(p['time'],zone),value,str(p.get('approval_status','')).lower()=='approved',has_estimate(p.get('qualifier'))))
    if not rows:return pd.DataFrame(columns=['value','estimated'],index=pd.DatetimeIndex([],name='date'))
    frame=pd.DataFrame(rows,columns=['date','value','approved','estimated'])
    # Match documented comparison: any conflicting values or unapproved entry
    # invalidates a day, while approved estimated values remain in references.
    out=[]
    for day,g in frame.groupby('date',sort=True):
        vals=g.value.dropna().unique();good=len(vals)==1 and g.approved.all() and np.isfinite(vals[0])
        out.append((day,float(vals[0]) if good else np.nan,bool(g.estimated.any())))
    return pd.DataFrame(out,columns=['date','value','estimated']).set_index('date')


def audit(root=ROOT):
    source=root/'results/additional_usgs_observed'
    cohort=pd.read_csv(source/'cohort_metadata.csv',dtype={'station_id':str})
    witnesses=pd.read_csv(source/'robust_record_witnesses.csv',dtype={'station_id':str})
    saved=pd.read_csv(source/'raw_reference_summary.csv',dtype={'station_id':str}).set_index('station_id')
    if cohort.station_id.duplicated().any():raise ValueError('duplicate station in cohort')
    records=0;n_refs=0;n_station_refs=0;max_reference_diff=0.;max_daily_diff=0.;n_missing=0
    for row in cohort.to_dict('records'):
        station=row['station_id'];path=root/'data/external/additional_usgs_observed/raw'/(station+'.json.gz')
        with gzip.open(path,'rt') as f:doc=json.load(f)
        series=approved_values(doc.get('features',[]),row.get('native_zone'))
        first=max(1981,int(row['first_full_year']));last=min(2025,int(row['last_full_year']))
        refs=[]
        for year in range(first,last+1):
            index=pd.date_range(f'{year}-01-01',f'{year}-12-31');x=series.value.reindex(index).to_numpy(float)
            if np.isfinite(x).all():refs.append((year,float(np.convolve(x,np.ones(30)/30,'valid').max())))
        n_refs+=len(refs);n_station_refs+=bool(refs)
        if int(saved.loc[station,'n_raw_approved_complete_years'])!=len(refs):raise ValueError(f'reference year count mismatch {station}')
        w=witnesses.loc[witnesses.station_id.eq(station)]
        if int(saved.loc[station,'n_robust_witness_years'])!=len(w):raise ValueError(f'witness count mismatch {station}')
        for r in w.itertuples(index=False):
            if not refs:raise ValueError('Witness has no complete-year reference')
            y=[int(x) for x in str(r.reference_years).split(';')]
            if y!=[x[0] for x in refs] or len(refs)!=int(r.n_raw_complete_years):raise ValueError('reference-year identities differ')
            reference=max(x[1] for x in refs);delta=abs(reference-r.maximum_raw_complete_H30)
            max_reference_diff=max(max_reference_diff,delta)
            if delta>1e-8:raise ValueError('reference maximum differs')
            index=pd.date_range(r.observed_window_start,r.observed_window_end)
            data=series.reindex(index);values=data.value.to_numpy(float);saved_values=np.fromstring(r.approved_window_values,sep=';')
            if len(index)!=30 or len(saved_values)!=30 or not np.isfinite(values).all() or data.estimated.fillna(True).any():
                raise ValueError('witness window is not fully approved and non-estimated')
            delta=float(np.max(abs(values-saved_values)));max_daily_diff=max(max_daily_diff,delta)
            if delta>1e-8 or abs(float(values.mean())-r.window_mean)>1e-8 or values.mean()<=reference+1e-9:
                raise ValueError('witness values or superiority differ')
            annual=series.value.reindex(pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31'))
            if int(annual.isna().sum())!=int(r.n_absent_or_unapproved) or not annual.isna().any():
                raise ValueError('source-record incompleteness differs')
            n_missing+=int(annual.isna().sum());records+=1
    if records!=len(witnesses):raise ValueError('unmatched witness station')
    return {'stations_acquired':len(cohort),'stations_with_complete_reference':n_station_refs,
            'complete_approved_station_years':n_refs,'witness_station_years_checked':records,
            'witness_stations':witnesses.station_id.nunique(),'max_complete_reference_discrepancy_c':max_reference_diff,
            'max_witness_day_discrepancy_c':max_daily_diff,'total_witness_missing_or_unapproved_days':n_missing,
            'passed':True,'scope':'saved USGS daily API responses; provider-local days and approved finite reference values, estimated values allowed in reference but not in witness window',
            'limitations':'quality-screened window selection itself not reproduced; not a proof of 24-hour native sampling, error-free physical truth, random incidence or independent accuracy validation'}


def main():
    AUDIT.mkdir(parents=True,exist_ok=True)
    try:result=audit()
    except Exception as exc:result={'passed':False,'error':f'{type(exc).__name__}: {exc}'}
    (AUDIT/'usgs_observed_independent_reaudit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
