#!/usr/bin/env python3
"""Compare same-agency field temperature records with nearby DWR logger times.

These records are not established to be from independent instruments. The
result assesses consistency at selected field-visit times only.
"""
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';WQP=PRIVATE/'wqp_same_site'

def freeze():
    target=OUT/'wqp_field_comparison_plan.json'
    if target.exists():raise FileExistsError('Preserve WQP field comparison plan')
    acquisition=json.loads((OUT/'wqp_same_site_acquisition.json').read_text());receipt=WQP/'acquisition.json'
    if acquisition['status']!='completed':raise ValueError('WQP acquisition incomplete')
    dwr=json.loads((PRIVATE/'acquisition.json').read_text());raw=[x for x in dwr if x['station_code']=='TRB8']
    if len(raw)!=1:raise ValueError('DWR logger input changed')
    entries=json.loads(receipt.read_text());files={}
    for r in entries:
        if r['status']=='completed':
            path=WQP/f"{r['year']}.csv.gz"
    p={'created_utc':datetime.now(timezone.utc).isoformat(),
       'status':'posthoc after target scores, WQP acquisition, and inspection of non-value status/method/time fields; before comparing numerical temperatures',
       'population':'All WQP Temperature, water rows for the same DWR station during the four scored reference years; no selection by measured temperature or model error.',
       'comparability':'Require finite numeric result in deg C, Accepted status, Actual value type, Field Msr/Obs, no measurement qualifier, explicit PST label, and a valid date/time. Pair to the nearest scheduled 15-minute DWR timestamp, with ties earlier, at most 7 minutes 30 seconds away; missing logger value is unavailable, not imputed.',
       'summary':'Report all WQP rows and exclusions, comparable observations and distinct dates, timing offsets, signed WQP-minus-DWR differences, MAE, median and maximum absolute difference and proportions within 0.1/0.5 C. Describe by year; no confidence interval or population frequency claim.',
       'independence':'Both records use the same DWR station and provider. WQP labels a field observation using EPA thermometric method 170.1, but instrument identity and processing overlap are not documented; do not claim a separate or independent sensor, calibrated accuracy, or independent climate.',
       'clock':'Both sources label the time PST. Interpret both as fixed UTC-8 only for this comparison; actual provider clock and daylight conventions remain unverified.',
       'limitations':'Field visits are sparse and potentially selected around service events; 2020 had no WQP rows. Agreement cannot validate all annual readings, the source quality flags, model error, or sensor independence.'}
    target.write_text(json.dumps(p,indent=2)+'\n');print('Recorded same-agency field-versus-logger comparison')

def compare():
    p=json.loads((OUT/'wqp_field_comparison_plan.json').read_text());dest=OUT/'wqp_field_comparison.json'
    if dest.exists():raise FileExistsError('Preserve field comparison')
    frames=[]
    for path in sorted(WQP.glob('*.csv.gz')):
        frames.append(pd.read_csv(path,compression='gzip',dtype=str))
    f=pd.concat(frames,ignore_index=True);numeric=pd.to_numeric(f.ResultMeasureValue,errors='coerce');tz=f['ActivityStartTime/TimeZoneCode'];time=f['ActivityStartTime/Time']
    stamp=pd.to_datetime(f.ActivityStartDate.fillna('')+' '+time.fillna(''),format='%Y-%m-%d %H:%M:%S',errors='coerce')
    qualifier=f.MeasureQualifierCode.fillna('').str.strip();good=(np.isfinite(numeric)&f['ResultMeasure/MeasureUnitCode'].eq('deg C')&
        f.ResultStatusIdentifier.eq('Accepted')&f.ResultValueTypeName.eq('Actual')&f.ActivityTypeCode.eq('Field Msr/Obs')&qualifier.eq('')&tz.eq('PST')&stamp.notna())
    used=f.loc[good].copy();used['field_c']=numeric.loc[good].to_numpy(float);used['field_time']=stamp.loc[good].to_numpy()
    floor=used.field_time.dt.floor('15min');delta=used.field_time-floor;used['nearest_time']=floor+pd.to_timedelta(np.where(delta>pd.Timedelta(minutes=7.5),15,0),unit='m')
    used['time_offset_minutes']=(used.field_time-used.nearest_time).dt.total_seconds().abs()/60
    if used.time_offset_minutes.gt(7.50000001).any():raise ValueError('Nearest-grid rule violated')
    logger=pd.read_csv(PRIVATE/'raw/TRB8.csv.gz',compression='gzip',usecols=['Station_Code','Date_Time','Water_Temperature'],dtype=str)
    if not logger.Station_Code.eq('TRB8').all():raise ValueError('Unexpected DWR station')
    logger['logger_time']=pd.to_datetime(logger.Date_Time,format='%m/%d/%Y %H:%M:%S',errors='coerce');logger=logger[logger.logger_time.dt.year.isin([2011,2013,2014,2020])].copy()
    if logger.logger_time.isna().any() or logger.logger_time.duplicated().any():raise ValueError('Ambiguous logger timestamp')
    logger['logger_c']=pd.to_numeric(logger.Water_Temperature,errors='coerce')
    paired=used.merge(logger[['logger_time','logger_c']],left_on='nearest_time',right_on='logger_time',how='left',validate='many_to_one')
    comparable=np.isfinite(paired.logger_c)&np.isfinite(paired.field_c);valid=paired.loc[comparable].copy();valid['difference_c']=valid.field_c-valid.logger_c
    private=PRIVATE/'wqp_field_pairs.parquet';paired.to_parquet(private,index=False);private.chmod(0o600)
    rows=[]
    for label,g in [('all',valid)]+[(str(y),valid[valid.field_time.dt.year.eq(y)]) for y in [2011,2013,2014,2020]]:
        a=g.difference_c.to_numpy(float);absval=np.abs(a)
        r={'period':label,'comparable_observations':len(g),'distinct_dates':int(g.field_time.dt.date.nunique()),
           'distinct_logger_times':int(g.nearest_time.nunique())}
        if len(g):r.update(bias_field_minus_logger=float(np.mean(a)),mae=float(np.mean(absval)),median_abs=float(np.median(absval)),
            max_abs=float(np.max(absval)),within_0_1_c=int(np.count_nonzero(absval<=.1+1e-10)),within_0_5_c=int(np.count_nonzero(absval<=.5+1e-10)),
            exact_timestamp=int(g.time_offset_minutes.eq(0).sum()),max_time_offset_minutes=float(g.time_offset_minutes.max()))
        rows.append(r)
    result=pd.DataFrame(rows);summary=OUT/'wqp_field_comparison.csv';result.to_csv(summary,index=False)
    out={'status':'computed_posthoc','wqp_rows':len(f),'eligible_field_rows':len(used),'comparable_rows':len(valid),
         'unavailable_logger_rows':int((~comparable).sum()),'distinct_comparable_dates':int(valid.field_time.dt.date.nunique()),
         'source_years_with_wqp_rows':sorted(pd.to_datetime(f.ActivityStartDate,errors='coerce').dt.year.dropna().astype(int).unique().tolist()),
         'independent_sensor_verified':False,
         'quality_interpretation':'WQP labels these accepted actual field observations, but instrument identity and processing overlap with DWR logger are unverified.',
         'limitations':p['limitations']+' '+p['independence']+' '+p['clock']}
    (OUT/'wqp_field_comparison_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','compare']);a=parser.parse_args();freeze() if a.action=='freeze' else compare()
