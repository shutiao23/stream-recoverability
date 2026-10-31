#!/usr/bin/env python3
"""Descriptive reported-day field-versus-hourly range comparison.

Field times are absent, statuses preliminary and sensor independence unknown.
These ranges do not validate the physical day, sensor accuracy or H30 recovery.
"""
from __future__ import annotations
import gzip
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'
PRIVATE=ROOT/'private/wrr_nova_scotia_field_checks_20261027';DATA=PRIVATE/'nova_scotia_field_v6.csv'
PORTAL=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified/portal_acquisition.json'

def portal_records(site,pages):
    """Read the fixed open-portal pages without importing workbook parsers."""
    rows=[]
    for item in pages:
        if item['station_id']!=site:continue
        content=gzip.decompress((ROOT/item['file']).read_bytes())
        rows.extend(json.loads(content))
    if not rows:return pd.DataFrame(columns=['timestamp','value']),0
    f=pd.DataFrame(rows)
    if not f.station_number.eq(site).all() or ':id' not in f or f[':id'].duplicated().any():raise ValueError('Portal record identity differs')
    dates=f.get('date',pd.Series('',index=f.index)).fillna('').astype(str).str.slice(0,10)
    times=f.get('time',pd.Series('',index=f.index)).fillna('').astype(str)
    stamp=pd.to_datetime(dates+' '+times,errors='coerce',format='mixed')
    if getattr(stamp.dt,'tz',None) is not None:raise ValueError('Portal timestamp requires time-zone review')
    values=pd.to_numeric(f.get('temperature_c',pd.Series(np.nan,index=f.index)),errors='coerce')
    return pd.DataFrame({'timestamp':stamp,'value':values}),int(stamp.isna().sum())

def full_day_ranges(frame):
    """Keep a date only when all 24 reported hours are unique and finite."""
    f=frame.dropna(subset=['timestamp']).copy();f['day']=f.timestamp.dt.normalize();rows=[]
    for day,g in f.groupby('day',sort=True):
        expected=pd.date_range(day,periods=24,freq='h')
        h=g.sort_values('timestamp')
        if len(h)!=24 or h.timestamp.duplicated().any() or not np.array_equal(h.timestamp.to_numpy(),expected.to_numpy()):continue
        values=h.value.to_numpy(float)
        if not np.isfinite(values).all():continue
        rows.append({'day':day,'minimum':float(values.min()),'maximum':float(values.max())})
    return pd.DataFrame(rows,columns=['day','minimum','maximum']).set_index('day')

def excess(value,low,high):return max(low-value,value-high,0.)

def aggregates(frame,scope):
    records=[]
    for label,h in [('both_sites',frame),*[(site,g) for site,g in frame.groupby('site',sort=True)]]:
        for window in ['same_day','three_day']:
            valid=h[h[window+'_available']].copy();d=valid[window+'_excess'].to_numpy(float)
            events=valid.groupby(['site','day'])[window+'_excess'].max()
            records.append({'scope':scope,'site':label,'window':window,'field_rows':len(h),
                            'numeric_field_rows':int(h.field_numeric.sum()),'site_dates':int(h[['site','day']].drop_duplicates().shape[0]),
                            'compared_rows':len(valid),'compared_site_dates':len(events),
                            'rows_outside_range':int((d>0).sum()),'rows_over_0_5_c_outside':int((d>.5).sum()),
                            'site_dates_any_outside':int(events.gt(0).sum()),'site_dates_any_over_0_5_c_outside':int(events.gt(.5).sum()),
                            'median_range_excess_c':float(np.median(d)) if len(d) else None,
                            'maximum_range_excess_c':float(np.max(d)) if len(d) else None})
    return records

def main():
    plan=json.loads((OUT/'comparison_plan.json').read_text())
    receipt=json.loads(PORTAL.read_text())
    columns=['MonitoringLocationID','ActivityStartDate','ActivityStartTime','ActivityStartTimeZone','CharacteristicName',
             'ResultValue','ResultUnit','ResultValueType','ResultDetectionCondition','ResultStatusID','SampleCollectionEquipmentName']
    f=pd.read_csv(DATA,usecols=columns,dtype=str,keep_default_na=False)
    f=f[f.MonitoringLocationID.isin(plan['site_ids'])&f.CharacteristicName.eq('Temperature, water')].copy()
    f['day']=pd.to_datetime(f.ActivityStartDate,format='%Y-%m-%d',errors='coerce')
    if f.day.isna().any():raise ValueError('Candidate field date cannot be interpreted')
    f=f[f.day.dt.year.isin(plan['years'])].copy()
    excluded_units=f.loc[f.ResultUnit.ne('deg C'),'ResultUnit'].value_counts().to_dict()
    f=f[f.ResultUnit.eq('deg C')].copy()
    if f.empty:raise ValueError('No planned field records')
    f['site']=f.MonitoringLocationID;f['value']=pd.to_numeric(f.ResultValue,errors='coerce')
    f['field_numeric']=np.isfinite(f.value.to_numpy(float))
    if f.ActivityStartTime.ne('').any() or f.ActivityStartTimeZone.ne('').any():raise ValueError('Field timing metadata changed; reassess comparison')
    if not f.ResultStatusID.eq('Preliminary').all():raise ValueError('Field quality metadata changed; reassess comparison')
    rows=[];portal_counts={}
    for site,g in f.groupby('site',sort=True):
        series,unparsed=portal_records(site,receipt['pages'])
        if unparsed:raise ValueError('Portal has unparseable reported timestamps')
        daily=full_day_ranges(series);portal_counts[site]=len(daily)
        for row in g.itertuples(index=False):
            day=row.day;present=bool(row.field_numeric) and day in daily.index
            out={'site':site,'day':day,'field_value':float(row.value) if row.field_numeric else None,
                 'field_numeric':bool(row.field_numeric),'same_day_available':present,'three_day_available':False,
                 'same_day_excess':np.nan,'three_day_excess':np.nan}
            if present:
                q=daily.loc[day];out['same_day_excess']=excess(float(row.value),float(q.minimum),float(q.maximum))
            days=[day+pd.Timedelta(days=k) for k in (-1,0,1)]
            if row.field_numeric and all(d in daily.index for d in days):
                x=daily.loc[days];out['three_day_available']=True
                out['three_day_excess']=excess(float(row.value),float(x.minimum.min()),float(x.maximum.max()))
            rows.append(out)
    data=pd.DataFrame(rows)
    if len(data)!=len(f):raise ValueError('Field row denominator changed')
    target=PRIVATE/'reported_day_comparisons.parquet'
    if target.exists():
        pd.testing.assert_frame_equal(pd.read_parquet(target),data,check_dtype=False)
    else:data.to_parquet(target,index=False);target.chmod(0o600)
    multiplicity=data.groupby(['site','day']).size()
    distinct=data.groupby(['site','day']).field_value.nunique(dropna=True)
    summary=pd.DataFrame(aggregates(data,'all_2009_2017'))
    summary.to_csv(OUT/'range_summary.csv',index=False)
    info={'status':'computed_exploratory','field_rows':len(data),'numeric_field_rows':int(data.field_numeric.sum()),
          'distinct_site_dates':len(multiplicity),'site_date_multiplicity':{str(int(k)):int(v) for k,v in multiplicity.value_counts().sort_index().items()},
          'site_dates_with_multiple_distinct_numeric_values':int(distinct.gt(1).sum()),
          'field_status_counts':f.ResultStatusID.value_counts().to_dict(),'units_excluded':excluded_units,
          'complete_reported_days_in_portal':portal_counts,'time_label_present':0,
          'interpretation':plan['limitations'],'row_level_evidence':'local private only'}
    (OUT/'status.json').write_text(json.dumps(info,indent=2)+'\n')
    print(summary.to_string(index=False));print(json.dumps(info,indent=2),flush=True)

if __name__=='__main__':main()
