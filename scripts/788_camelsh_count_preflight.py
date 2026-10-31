#!/usr/bin/env python3
"""Approved-count-only preflight of fixed CAMELSH metadata candidates."""
import argparse
import calendar
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_camelsh_hourly'
PRIVATE=ROOT/'private/wrr_camelsh_hourly_reference_20261027';URL='https://api.waterdata.usgs.gov/statistics/v0/observationIntervals'

def freeze():
    dest=OUT/'count_plan.json'
    if dest.exists():raise FileExistsError('Preserve count-only plan')
    status=json.loads((OUT/'metadata_status.json').read_text());source=PRIVATE/'metadata_screen.csv'
    if status['status']!='metadata_screen_completed':raise ValueError('Metadata screen changed')
    f=pd.read_csv(source,dtype={'station_id':str,'series_id':str,'huc8':str});f=f.loc[f.metadata_candidate].sort_values('station_id')
    if len(f)!=status['metadata_candidates'] or f.station_id.duplicated().any():raise ValueError('Metadata roster differs')
    path=PRIVATE/'count_roster.csv';f.to_csv(path,index=False);path.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc fixed preflight after archive and existing metadata screening, before requesting annual statistics and before any target prediction errors',
        'cohort':'All 12 single-series candidates from the metadata screen; no sampling by temperature or prediction error.',
        'count_rule':'USGS approved annual 00010/00003 counts for 2000–2025; the exact candidate time-series ID and full calendar interval must match. Count 365/366 as potentially complete; absence is unknown, not zero.',
        'handling':'The API may return annual temperature statistics; extract only dates, series identities, approval state and sample_count, and retain no returned temperature statistic or raw response. Two independent count extractions must agree.',
        'next_step':'A candidate with four count-complete years is only a necessary-condition pass. Resolve catchment and prior contacts, nonestimated observations, time-zone/day support and sensor quality before considering reference scoring.',
        'cohort_count':len(f),'limitations':'Posthoc and selected for availability, not random or independently climate-confirmed. Annual count may contain estimated days and does not establish full subdaily sampling.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded count-only candidate preflight')

def extract(doc,expected):
    if not isinstance(doc.get('features'),list) or any(x.get('rel')=='next' for x in doc.get('links',[])):raise ValueError('Invalid or paginated statistics response')
    seen=set();rows=[]
    for feature in doc['features']:
        p=feature['properties'];site=str(p['monitoring_location_id']).removeprefix('USGS-')
        if site not in expected:raise ValueError('Unexpected USGS site')
        for s in p.get('data',[]):
            if str(s.get('parent_time_series_id'))!=expected[site] or str(s.get('parent_statistic_id'))!='00003':continue
            for a in s.get('values',[]):
                if a.get('interval_type')!='calendar_year' or a.get('approval_status')!='approved':continue
                start=pd.Timestamp(a['start_date']);end=pd.Timestamp(a['end_date']);year=start.year
                if year not in range(2000,2026):continue
                if end.year!=year or end<start:raise ValueError('Invalid annual interval')
                key=(site,year)
                if key in seen:raise ValueError('Duplicate site-year statistic')
                seen.add(key);n=int(a['sample_count']);days=366 if calendar.isleap(year) else 365
                if n<0 or n>days:raise ValueError('Invalid number of daily samples')
                full=start==pd.Timestamp(year,1,1) and end==pd.Timestamp(year,12,31)
                rows.append((site,year,n,days,bool(full)))
    return sorted(rows)

def extract_independent(doc,expected):
    """Separate scalar implementation; do not inspect returned temperature statistics."""
    rows=[]
    for item in doc['features']:
        prop=item['properties'];site=prop['monitoring_location_id'].replace('USGS-','',1)
        for series in prop.get('data',[]):
            if str(series.get('parent_time_series_id'))!=expected[site] or str(series.get('parent_statistic_id'))!='00003':continue
            for rec in series.get('values',[]):
                if rec.get('interval_type')!='calendar_year' or rec.get('approval_status')!='approved':continue
                first=str(rec['start_date'])[:10];last=str(rec['end_date'])[:10];year=int(first[:4])
                if not 2000<=year<=2025:continue
                days=366 if year%4==0 and year%100!=0 or year%400==0 else 365
                rows.append((site,year,int(rec['sample_count']),days,first==f'{year}-01-01' and last==f'{year}-12-31'))
    return sorted(rows)

def run():
    plan=json.loads((OUT/'count_plan.json').read_text());roster=PRIVATE/'count_roster.csv'
    f=pd.read_csv(roster,dtype={'station_id':str,'series_id':str,'huc8':str});rows=[];receipts=[]
    for start in range(0,len(f),4):
        g=f.iloc[start:start+4];expected=dict(zip(g.station_id,g.series_id));params=[('monitoring_location_id','USGS-'+s) for s in g.station_id]
        params += [('parameter_code','00010'),('start_date','2000-01-01'),('end_date','2025-12-31'),('interval_type','CY'),('computation_type','arithmetic_mean'),('page_size','100')]
        item={'batch':start//4+1,'sites_requested':len(g),'status':'unknown'}
        try:
            response=requests.get(URL,params=params,timeout=45,headers={'User-Agent':'stream-temperature reference screening/1.0'})
            item['http_status']=response.status_code
            if response.status_code==200:
                doc=response.json();first=extract(doc,expected);second=extract_independent(doc,expected)
                if first!=second:raise ValueError('Independent count extraction differs')
                rows.extend(first);item.update(status='completed',count_records=len(first),features=len(doc['features']))
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:item['error_type']=type(exc).__name__
        receipts.append(item);print('Count batch',item['batch'],item['status'],flush=True)
    count=pd.DataFrame(rows,columns=['station_id','year','approved_count','expected_days','full_year_interval'])
    if len(count) and count.duplicated(['station_id','year']).any():raise ValueError('Duplicate site-year counts')
    count['count_complete']=count.approved_count.eq(count.expected_days)&count.full_year_interval if len(count) else pd.Series(dtype=bool)
    file=PRIVATE/'approved_counts.csv';count.to_csv(file,index=False);file.chmod(0o600)
    by=count.groupby('station_id').agg(reported_years=('year','size'),count_complete_years=('count_complete','sum')) if len(count) else pd.DataFrame(columns=['reported_years','count_complete_years'])
    out=f[['station_id','series_id','huc8','native_zone']].join(by,on='station_id');out[['reported_years','count_complete_years']]=out[['reported_years','count_complete_years']].fillna(0).astype(int)
    out['four_confirmed_years']=out.count_complete_years.ge(4);path=PRIVATE/'count_summary.csv';out.to_csv(path,index=False);path.chmod(0o600)
    result={'status':'completed' if all(x['status']=='completed' for x in receipts) else 'partial_unknown',
        'sites':len(f),'batches':receipts,'reported_site_year_counts':len(count),'sites_with_reported_years':int(out.reported_years.gt(0).sum()),
        'sites_four_confirmed_complete_count_years':int(out.four_confirmed_years.sum()),
        'raw_response_retained':False,'annual_temperatures_retained_or_used':False,
        'limitations':plan['limitations']+' Unreturned statistics are unknown; no reference values or model errors were scored.'}
    (OUT/'count_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
