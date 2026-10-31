#!/usr/bin/env python3
"""Post-hoc nearest-value diagnostic with missing field sample times."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'
PRIVATE=ROOT/'private/wrr_nova_scotia_field_checks_20261027'
PRE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified/portal_acquisition.json'
ROSTER=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/reference_year_roster.csv'

def complete_days(frame):
    f=frame.dropna(subset=['timestamp']).copy();f['day']=f.timestamp.dt.normalize();result={}
    for day,g in f.groupby('day',sort=True):
        expected=pd.date_range(day,periods=24,freq='h');g=g.sort_values('timestamp')
        values=g.value.to_numpy(float)
        if len(g)==24 and not g.timestamp.duplicated().any() and np.array_equal(g.timestamp.to_numpy(),expected.to_numpy()) and np.isfinite(values).all():
            result[day]=values
    return result

def main():
    plan=json.loads((OUT/'hour_membership_plan.json').read_text())
    rows=pd.read_parquet(PRIVATE/'reported_day_comparisons.parquet')
    if len(rows)!=146 or rows.duplicated(['site','day']).sum()!=73:raise ValueError('Field row cohort changed')
    original=json.loads((OUT/'comparison_plan.json').read_text());source=PRIVATE/'nova_scotia_field_v6.csv'
    fields=['MonitoringLocationID','ActivityStartDate','CharacteristicName','ResultUnit','ResultValue']
    source_rows=pd.read_csv(source,usecols=fields,dtype=str,keep_default_na=False)
    source_rows=source_rows[source_rows.MonitoringLocationID.isin(original['site_ids'])
                            &source_rows.CharacteristicName.eq('Temperature, water')&source_rows.ResultUnit.eq('deg C')].copy()
    source_rows['day']=pd.to_datetime(source_rows.ActivityStartDate,format='%Y-%m-%d',errors='coerce')
    source_rows=source_rows[source_rows.day.dt.year.isin(original['years'])].copy()
    source_rows['field_value']=pd.to_numeric(source_rows.ResultValue,errors='coerce')
    left=source_rows.rename(columns={'MonitoringLocationID':'site'})[['site','day','field_value']].sort_values(['site','day','field_value']).reset_index(drop=True)
    right=rows[['site','day','field_value']].sort_values(['site','day','field_value']).reset_index(drop=True)
    pd.testing.assert_frame_equal(left,right,check_dtype=False,check_exact=True)
    roster=pd.read_csv(ROSTER);selected=set(zip(roster.station_id,roster.year.astype(int)))
    if len(selected)!=8:raise ValueError('Earlier modeled reference-year roster changed')
    spec=importlib.util.spec_from_file_location('nova_field_range_membership',ROOT/'scripts/753_nova_field_range_check.py')
    portal=importlib.util.module_from_spec(spec);spec.loader.exec_module(portal)
    receipt=json.loads(PRE.read_text());computed=[]
    for site,g in rows.groupby('site',sort=True):
        series,unparsed=portal.portal_records(site,receipt['pages'])
        if unparsed:raise ValueError('Portal timestamp parsing failed')
        days=complete_days(series)
        for row in g.itertuples(index=False):
            day=row.day;three=[day+pd.Timedelta(days=k) for k in (-1,0,1)];value=float(row.field_value) if row.field_numeric else np.nan
            single=day in days and bool(row.field_numeric)
            triple=all(d in days for d in three) and bool(row.field_numeric)
            if single!=bool(row.same_day_available) or triple!=bool(row.three_day_available):raise ValueError('Range and membership availability differ')
            computed.append({'site':site,'day':day,'selected_year':(site,int(day.year)) in selected,
                             'single_available':single,'triple_available':triple,
                             'single_distance':float(np.min(abs(days[day]-value))) if single else np.nan,
                             'triple_distance':float(np.min(abs(np.concatenate([days[d] for d in three])-value))) if triple else np.nan})
    data=pd.DataFrame(computed)
    path=PRIVATE/'hour_membership_comparisons.parquet'
    if path.exists():pd.testing.assert_frame_equal(pd.read_parquet(path),data,check_dtype=False)
    else:data.to_parquet(path,index=False);path.chmod(0o600)
    output=[]
    for scope,subset in [('all',data),('modeled_years',data[data.selected_year]),('other_years',data[~data.selected_year])]:
        for label,g in [('both_sites',subset),*list(subset.groupby('site',sort=True))]:
            for window in ['single','triple']:
                t=g[g[window+'_available']];v=t[window+'_distance'].to_numpy(float)
                bydate=t.groupby(['site','day'])[window+'_distance'].min()
                output.append({'scope':scope,'site':label,'window':window,'field_rows':len(g),'compared_rows':len(t),
                               'compared_site_dates':len(bydate),'rows_within_1e_6_c':int((v<=1e-6).sum()),
                               'rows_within_0_01_c':int((v<=.01+1e-12).sum()),
                               'site_dates_within_1e_6_c':int(bydate.le(1e-6).sum()),
                               'site_dates_within_0_01_c':int(bydate.le(.01+1e-12).sum()),
                               'median_nearest_difference_c':float(np.median(v)) if len(v) else None,
                               'maximum_nearest_difference_c':float(np.max(v)) if len(v) else None})
    summary=pd.DataFrame(output);summary.to_csv(OUT/'hour_membership_summary.csv',index=False)
    range_spec=importlib.util.spec_from_file_location('nova_selected_range',ROOT/'scripts/753_nova_field_range_check.py')
    range_module=importlib.util.module_from_spec(range_spec);range_spec.loader.exec_module(range_module)
    selected_flag=np.array([(site,int(day.year)) in selected for site,day in zip(rows.site,rows.day)],dtype=bool)
    range_rows=[]
    for scope,subset in [('modeled_years',rows.loc[selected_flag]),('other_years',rows.loc[~selected_flag])]:
        range_rows.extend(range_module.aggregates(subset,scope))
    pd.DataFrame(range_rows).to_csv(OUT/'selected_year_range_summary.csv',index=False)
    report={'status':'computed_posthoc','rows':len(data),'modeled_reference_years':len(selected),
            'interpretation':plan['selection_warning'],'limit':'Same monitoring programme and unresolved sample time, location within reach, instrument and quality. Proximity is not a time-matched comparison.',
            'per_record_results':'local private only'}
    (OUT/'hour_membership_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(summary[summary.site.eq('both_sites')].to_string(index=False));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
