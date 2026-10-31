#!/usr/bin/env python3
"""Independently audit DWR/WQP field-versus-logger pairs and timing strata."""
import argparse
import csv
from datetime import datetime,timedelta,timezone
import gzip
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';WQP=PRIVATE/'wqp_same_site'

def nearest_grid(t):
    base=t.replace(minute=(t.minute//15)*15,second=0,microsecond=0)
    return base+timedelta(minutes=15) if (t-base)>timedelta(minutes=7,seconds=30) else base

def freeze():
    dest=OUT/'wqp_time_strata_plan.json'
    if dest.exists():raise FileExistsError('Preserve timing-strata plan')
    score=json.loads((OUT/'wqp_field_comparison_status.json').read_text());summary=OUT/'wqp_field_comparison.csv'
    if score['status']!='computed_posthoc':raise ValueError('Field comparison incomplete')
    p={'created_utc':datetime.now(timezone.utc).isoformat(),
       'status':'posthoc after inspecting the overall field-versus-logger difference; before calculating timing-stratified results',
       'strata':'Compare all matched field observations, those exactly on a 15-minute label, and those paired to a neighboring label within 7.5 minutes; retain zero-count strata.',
       'audit':'Reconstruct eligibility and nearest timestamps directly from the saved WQP CSV and DWR logger file using Python csv/datetime; recompute every original aggregate and both timing strata.',
       'limitations':'One same-agency station and three sampled years; instrument independence, spatial placement, true water clock, field-visit selection and quality of all unvisited dates remain unresolved.',
       }
    dest.write_text(json.dumps(p,indent=2)+'\n');print('Recorded post-hoc exact-time sensitivity')

def audit():
    p=json.loads((OUT/'wqp_time_strata_plan.json').read_text())
    plan=json.loads((OUT/'wqp_field_comparison_plan.json').read_text());receipt=WQP/'acquisition.json';source=PRIVATE/'raw/TRB8.csv.gz'
    candidates=[];raw_count=0
    for path in sorted(WQP.glob('*.csv.gz')):
        with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                raw_count+=1
                try:value=float(r['ResultMeasureValue']);time=datetime.strptime(r['ActivityStartDate']+' '+r['ActivityStartTime/Time'],'%Y-%m-%d %H:%M:%S')
                except (ValueError,TypeError):continue
                good=math.isfinite(value) and r['ResultMeasure/MeasureUnitCode']=='deg C' and r['ResultStatusIdentifier']=='Accepted' and r['ResultValueTypeName']=='Actual' and r['ActivityTypeCode']=='Field Msr/Obs' and not r['MeasureQualifierCode'].strip() and r['ActivityStartTime/TimeZoneCode']=='PST'
                if good:candidates.append({'time':time,'field':value,'nearest':nearest_grid(time)})
    targets={x['nearest'] for x in candidates};log={};duplicates=set()
    with gzip.open(source,'rt',encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['Station_Code']!='TRB8':raise ValueError('Unexpected DWR station')
            t=datetime.strptime(r['Date_Time'],'%m/%d/%Y %H:%M:%S')
            if t not in targets:continue
            if t in log:duplicates.add(t)
            try:value=float(r['Water_Temperature'])
            except (ValueError,TypeError):value=float('nan')
            log[t]=value
    if duplicates:raise ValueError('Duplicate selected logger timestamp')
    pairs=[]
    for item in candidates:
        v=log.get(item['nearest'],float('nan'))
        if not math.isfinite(v):continue
        pairs.append({'year':item['time'].year,'date':item['time'].date(),'nearest':item['nearest'],
                      'offset':abs((item['time']-item['nearest']).total_seconds())/60,'difference':item['field']-v})
    if len(pairs)!=len({(x['time'],x['nearest'],x['field']) for x in candidates if math.isfinite(log.get(x['nearest'],float('nan')))}):
        # Duplicate records may be legitimate; report them instead of silently dropping them.
        duplicates_retained=True
    else:duplicates_retained=False
    def metrics(rows):
        d=[x['difference'] for x in rows];a=[abs(x) for x in d];result={'comparable_observations':len(rows),
             'distinct_dates':len({x['date'] for x in rows}),'distinct_logger_times':len({x['nearest'] for x in rows})}
        if rows:result.update(bias_field_minus_logger=math.fsum(d)/len(d),mae=math.fsum(a)/len(a),median_abs=float(np.median(a)),max_abs=max(a),
            within_0_1_c=sum(x<=.1+1e-10 for x in a),within_0_5_c=sum(x<=.5+1e-10 for x in a),
            exact_timestamp=sum(x['offset']==0 for x in rows),max_time_offset_minutes=max(x['offset'] for x in rows))
        return result
    saved=pd.read_csv(OUT/'wqp_field_comparison.csv');checked=0
    for r in saved.itertuples(index=False):
        subset=pairs if str(r.period)=='all' else [x for x in pairs if x['year']==int(r.period)]
        for name,value in metrics(subset).items():
            if not np.isclose(value,getattr(r,name),rtol=0,atol=1e-9,equal_nan=True):raise AssertionError('Field summary differs: '+name)
            checked+=1
    strata=[]
    for label,subset in [('all',pairs),('exact_quarter_hour',[x for x in pairs if x['offset']==0]),('nearest_nonexact',[x for x in pairs if x['offset']>0])]:
        row={'stratum':label,**metrics(subset)};strata.append(row)
    target=OUT/'wqp_time_strata_summary.csv';pd.DataFrame(strata).to_csv(target,index=False)
    original=json.loads((OUT/'wqp_field_comparison_status.json').read_text())
    if raw_count!=original['wqp_rows'] or len(candidates)!=original['eligible_field_rows'] or len(pairs)!=original['comparable_rows']:
        raise AssertionError('Field eligibility counts differ')
    result={'status':'passed','raw_rows_recomputed':raw_count,'eligible_rows_recomputed':len(candidates),'comparable_rows_recomputed':len(pairs),
            'summary_cells_checked':checked,'duplicate_equal_records_retained':duplicates_retained,'scope':'Separate CSV/datetime matching and scalar arithmetic over the same DWR and WQP files; timing strata selected after overall results.',
            'limitations':p['limitations']+' Equal dates or agreement do not prove independent instruments or correct historical clock conventions.'}
    (OUT/'wqp_field_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','audit']);a=p.parse_args();freeze() if a.action=='freeze' else audit()
