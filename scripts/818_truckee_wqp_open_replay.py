#!/usr/bin/env python3
"""Offline replay of the same-agency WQP/DWR field-time comparison."""
import argparse
import csv
from datetime import datetime,timedelta
import gzip
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';SNAP=ROOT/'data/external/wrr_truckee_dwr_20261027';WQP=SNAP/'wqp_field_snapshot'

def nearest(t):
    base=t.replace(minute=(t.minute//15)*15,second=0,microsecond=0)
    return base+timedelta(minutes=15) if t-base>timedelta(minutes=7,seconds=30) else base

def metrics(rows):
    diffs=[r['difference'] for r in rows];absvals=[abs(x) for x in diffs]
    out={'comparable_observations':len(rows),'distinct_dates':len({r['time'].date() for r in rows}),
         'distinct_logger_times':len({r['nearest'] for r in rows})}
    if rows:out.update(bias_field_minus_logger=math.fsum(diffs)/len(diffs),mae=math.fsum(absvals)/len(absvals),
        median_abs=float(np.median(absvals)),max_abs=max(absvals),within_0_1_c=sum(x<=.1+1e-10 for x in absvals),
        within_0_5_c=sum(x<=.5+1e-10 for x in absvals),exact_timestamp=sum(r['offset']==0 for r in rows),
        max_time_offset_minutes=max(r['offset'] for r in rows))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'results/wrr_review_response_20261027/audit/truckee_wqp_open_replay.json');args=p.parse_args()
    manifest=json.loads((WQP/'manifest.json').read_text());parent=json.loads((SNAP/'manifest.json').read_text())
    for key in ['field_results','station_metadata']:
        item=manifest[key];path=(WQP/item['file']).resolve()
        if not path.is_relative_to(WQP.resolve()):raise ValueError('WQP snapshot changed')
    matches=[x for x in parent['files'] if x.get('station_code')=='TRB8']
    if len(matches)!=1:raise ValueError('TRB8 source manifest ambiguous')
    logger=SNAP/matches[0]['file']
    field=[];raw=0
    with (WQP/manifest['field_results']['file']).open(encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            raw+=1
            try:value=float(r['ResultMeasureValue']);time=datetime.strptime(r['ActivityStartDate']+' '+r['ActivityStartTime/Time'],'%Y-%m-%d %H:%M:%S')
            except (TypeError,ValueError):continue
            if (math.isfinite(value)
                and r['ResultMeasure/MeasureUnitCode']=='deg C'
                and r['ResultStatusIdentifier']=='Accepted'
                and r['ResultValueTypeName']=='Actual'
                and r['ActivityTypeCode']=='Field Msr/Obs'
                and not r['MeasureQualifierCode'].strip()
                and r['ActivityStartTime/TimeZoneCode']=='PST'):
                field.append({'time':time,'value':value,'nearest':nearest(time)})
    if raw!=manifest['field_results']['rows']:raise ValueError('WQP row count differs')
    targets={x['nearest'] for x in field};data={}
    with gzip.open(logger,'rt',encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['Station_Code']!='TRB8':raise ValueError('Unexpected DWR station')
            t=datetime.strptime(row['Date_Time'],'%m/%d/%Y %H:%M:%S')
            if t not in targets:continue
            if t in data:raise ValueError('Duplicate selected logger timestamp')
            try:data[t]=float(row['Water_Temperature'])
            except (ValueError,TypeError):data[t]=float('nan')
    pairs=[]
    for x in field:
        v=data.get(x['nearest'],float('nan'))
        if math.isfinite(v):pairs.append({'time':x['time'],'nearest':x['nearest'],'offset':abs((x['time']-x['nearest']).total_seconds())/60,'difference':x['value']-v})
    saved=pd.read_csv(OUT/'wqp_field_comparison.csv');strata=pd.read_csv(OUT/'wqp_time_strata_summary.csv');checked=0
    def compare(row,subset):
        nonlocal checked
        for key,value in metrics(subset).items():
            if not np.isclose(value,getattr(row,key),rtol=0,atol=1e-9,equal_nan=True):raise ValueError('Published field summary differs: '+key)
            checked+=1
    for r in saved.itertuples(index=False):compare(r,pairs if str(r.period)=='all' else [x for x in pairs if x['time'].year==int(r.period)])
    for r in strata.itertuples(index=False):
        if r.stratum not in ('all','exact_quarter_hour','nearest_nonexact'):raise ValueError('Unexpected timing stratum')
        subset=pairs if r.stratum=='all' else [x for x in pairs if (x['offset']==0)==(r.stratum=='exact_quarter_hour')]
        compare(r,subset)
    result={'status':'passed','source_rows':raw,'eligible_rows':len(field),'comparable_rows':len(pairs),'summary_cells_checked':checked,
        'scope':'Offline replay of reduced WQP fields and the bundled DWR logger source; no model predictions or hidden observations are used.',
        'limitations':'Same agency and station; different instrumentation, physical co-location, true clock convention, sensor accuracy and full-year representativeness remain unverified. The reduced file does not contain all columns of the original WQP responses.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
