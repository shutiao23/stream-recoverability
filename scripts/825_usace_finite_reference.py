#!/usr/bin/env python3
"""Qualify fixed reservoir-network reference days by finite level-1 values."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';RAW=PRIVATE/'raw_level1'

def freeze():
    path=OUT/'finite_reference_plan.json'
    if path.exists():raise FileExistsError('Preserve finite reference plan')
    time=json.loads((OUT/'time_upper_bound_status.json').read_text());audit=json.loads((OUT/'time_upper_bound_independent_audit.json').read_text())
    if time['status']!='timestamp_upper_bound_completed' or audit['status']!='passed':raise ValueError('Timestamp preflight incomplete')
    receipt=PRIVATE/'time_acquisition.json';acq=json.loads((OUT/'time_acquisition.json').read_text())
    if acq['status']!='completed':raise ValueError('Acquisition changed')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
       'status':'posthoc after source metadata, NLDI, downloads and timestamp upper bounds were inspected; before reading numerical temperatures or target model errors',
       'cohort':'All 10 fixed candidate level-1 files, including those with known 200-km NLDI prior hits; do not select on temperature or model error.',
       'day_rule':'A reported fixed-MST day needs exactly 96 unique on-grid quarter-hour timestamps and 96 finite values in [-5,50] degrees C; a year requires every calendar day. Compute each valid daily arithmetic mean but do not compute annual H30 or model prediction errors.',
       'range_basis':'Authors describe YSI EXO sondes. Manufacturer EXO temperature measurement range is -5 to 50 C; use only as a broad invalid/sentinel guard, not a validation of sensor accuracy or all local instrument configurations.',
       'manufacturer_source':'https://www.xylemanalytics.com/File%20Library/Resource%20Library/YSI/Spec%20Sheets/YSI-EXO-Sonde-Platform-Specification-Sheet.pdf',
       'quality':'Published level-1 files are described as QA/QC and may be corrected for fouling or drift; unknown estimated/corrected flags, source version and physical accuracy preclude automatic strict-reference qualification. Record any candidate flag-like columns but do not infer their meaning.',
       'network':'Retain known NLDI connections and no-hit cases separately; 200-km gage proxies and one regional project do not prove independent climates.',
       }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded full-cohort finite-reference screen')

def run():
    p=json.loads((OUT/'finite_reference_plan.json').read_text())
    parser=T.load_script('usace_timestamp_parser',ROOT/'scripts/823_usace_timestamp_upper_bound.py');timestamp=pd.read_csv(PRIVATE/'timestamp_station_years.csv')
    annual=[];sites=[];daily=[];schemas=[]
    for item in json.loads((PRIVATE/'time_acquisition.json').read_text()):
        rid=item['resource_id'];path=RAW/f'{rid}.csv.gz'
        fields=list(pd.read_csv(path,compression='gzip',nrows=0).columns)
        if not {'timestamp','temp_degC'}.issubset(fields):raise ValueError('Temperature or time column absent')
        flags=[c for c in fields if re.search(r'flag|qualifier|qualit|estimat',c,re.I)];schemas.append({'resource_id':rid,'columns':fields,'flag_like_columns':flags})
        pieces=[]
        for x in pd.read_csv(path,compression='gzip',usecols=['timestamp','temp_degC'],dtype=str,chunksize=100000):
            time,kind=parser.timestamps(x.timestamp);v=pd.to_numeric(x.temp_degC,errors='coerce')
            valid=np.isfinite(v)&v.ge(-5)&v.le(50);pieces.append(pd.DataFrame({'time':time,'value':v.where(valid),'finite':np.isfinite(v),'valid_temp':valid}))
        data=pd.concat(pieces,ignore_index=True);data['day']=data.time.dt.normalize();data['grid']=data.time.dt.minute.mod(15).eq(0)&data.time.dt.second.eq(0)&data.time.dt.microsecond.eq(0)
        by=data.groupby('day').agg(rows=('time','size'),unique=('time','nunique'),grid=('grid','sum'),finite=('finite','sum'),valid_temp=('valid_temp','sum'),mean_c=('value','mean'))
        by['complete']=by.rows.eq(96)&by.unique.eq(96)&by.grid.eq(96)&by.valid_temp.eq(96)
        d=by.loc[by.complete,['mean_c']].reset_index();d['resource_id']=rid;daily.append(d)
        years=[];t=timestamp[timestamp.resource_id.eq(rid)].set_index('year')
        for year,g in by.groupby(by.index.year):
            expected=366 if pd.Timestamp(int(year),12,31).is_leap_year else 365;n=int(g.complete.sum())
            if int(year) not in t.index or n>int(t.loc[int(year),'days_with_96_unique_quarters']):raise ValueError('Finite day exceeds timestamp support')
            years.append({'resource_id':rid,'year':int(year),'reported_days':len(g),'complete_finite_days':n,'expected_days':expected,
                          'finite_reference_year':len(g)==expected and n==expected})
        years=pd.DataFrame(years);annual.append(years);sites.append({'resource_id':rid,'reported_years':len(years),
            'complete_finite_years':int(years.finite_reference_year.sum()),'at_least_four_finite_years':bool(years.finite_reference_year.sum()>=4),
            'finite_values_outside_sensor_range':int((data.finite&~data.valid_temp).sum()),'flag_like_columns':';'.join(flags)})
        print('Finite level-1 reference',len(sites),'of 10',flush=True)
    yr=pd.concat(annual,ignore_index=True);st=pd.DataFrame(sites);days=pd.concat(daily,ignore_index=True)
    if days.duplicated(['resource_id','day']).any():raise ValueError('Duplicate source-day means')
    for name,frame in [('finite_reference_years.csv',yr),('finite_reference_sites.csv',st)]:
        path=PRIVATE/name;frame.to_csv(path,index=False);path.chmod(0o600)
    path=PRIVATE/'finite_daily.parquet';days.to_parquet(path,index=False);path.chmod(0o600)
    schema=PRIVATE/'level1_schema.json';schema.write_text(json.dumps(schemas,indent=2)+'\n');schema.chmod(0o600)
    status={'status':'finite_level1_reference_screened','resources':len(st),'station_years':len(yr),'complete_finite_station_years':int(yr.finite_reference_year.sum()),
       'sites_with_four_finite_years':int(st.at_least_four_finite_years.sum()),'complete_finite_days':len(days),
       'finite_values_outside_sensor_range':int(st.finite_values_outside_sensor_range.sum()),'files_with_flag_like_columns':sum(bool(x['flag_like_columns']) for x in schemas),
       'annual_h30_calculated':False,'prediction_errors_calculated':False,'limitations':p['quality']+' '+p['network']}
    (OUT/'finite_reference_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
