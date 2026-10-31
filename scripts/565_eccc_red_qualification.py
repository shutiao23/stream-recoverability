#!/usr/bin/env python3
"""Acquire frozen ECCC Red River files and qualify provider-local hourly days.

Only V (validated), quality grades 1/2, finite unflagged temperature points
are accepted. Unknown status/grade is not reclassified. Local wall-clock
completeness does not establish an independently verified 24-hour physical day.
"""
from datetime import datetime,timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_eccc_red'
BASE='/substances/monitor/automated-fresh-water-quality-monitoring-and-surveillance-data/'
URL='https://data-donnees.az.ec.gc.ca/api/file'
STATION='MA05OC0001'

def daily_quality(frame):
    """One valid value per local clock hour, without gap filling or duplicate averaging."""
    x=frame.copy()
    if not x.station.eq(STATION).all():raise ValueError('Input contains wrong station')
    x['time']=pd.to_datetime(x.time,format='mixed',dayfirst=True,errors='coerce')
    x['value']=pd.to_numeric(x.value,errors='coerce')
    x['grade']=pd.to_numeric(x.grade,errors='coerce')
    x['valid']=x.time.notna() & np.isfinite(x.value) & x.status.eq('V') & x.grade.isin([1,2]) & x.flag.fillna('').astype(str).str.strip().eq('')
    x=x.loc[x.time.notna()].copy()
    x['date']=x.time.dt.normalize();x['hour']=x.time.dt.hour
    # Duplicate hour records are never resolved by peeking at their values.
    hours=x.groupby(['date','hour'],as_index=False).agg(n=('valid','size'),valid_n=('valid','sum'),value=('value','first'))
    hours['accepted']=hours.n.eq(1)&hours.valid_n.eq(1)
    daily=hours.groupby('date').agg(hour_bins=('hour','size'),valid_hour_bins=('accepted','sum'),
                                    ambiguous_hours=('n',lambda q:int((q>1).sum())))
    values=hours.loc[hours.accepted].groupby('date').value.mean()
    daily['temperature_c']=values.reindex(daily.index)
    daily['complete_wallclock']=daily.hour_bins.eq(24)&daily.valid_hour_bins.eq(24)&daily.ambiguous_hours.eq(0)
    daily.loc[~daily.complete_wallclock,'temperature_c']=np.nan
    return daily.reset_index()

def main():
    plan=json.loads((OUT/'plan.json').read_text())
    if plan['selected_station']!=STATION:raise ValueError('Unexpected preselected station')
    (OUT/'raw').mkdir(exist_ok=True)
    logpath=OUT/'request_log.json'
    previous={x['file']:x for x in json.loads(logpath.read_text())} if logpath.exists() else {}
    logs=[];frames=[]
    for name in plan['files']:
        dest=OUT/'raw'/name
        if dest.exists():
            payload=dest.read_bytes();
            meta=previous[name].copy() if name in previous else {'file':name,'status':'reused_local_cache','bytes':len(payload),'request_time_unknown':True}
        else:
            response=requests.get(URL,params={'path':BASE+name},timeout=120);response.raise_for_status();payload=response.content
            dest.write_bytes(payload);meta={'file':name,'status':'downloaded','url':response.url,'http_status':response.status_code,
                                            'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(payload)}
        logs.append(meta)
        (OUT/'request_log.json').write_text(json.dumps(logs,indent=2)+'\n')
        encoding='utf-8-sig' if payload.startswith(b'\xef\xbb\xbf') else 'cp1252'
        df=pd.read_csv(dest,encoding=encoding,dtype=str,low_memory=False)
        needed={'STATION_NO','DATE_TIME_HEURE','VMV_CODE','VALUE_VALEUR','STATUS_STATUT','GRADE_COTE','FLAG_FANION'}
        if needed-set(df.columns):raise ValueError(f'{name} missing fields {needed-set(df.columns)}')
        df=df.loc[pd.to_numeric(df.VMV_CODE,errors='coerce').eq(4730),['STATION_NO','DATE_TIME_HEURE','VALUE_VALEUR','STATUS_STATUT','GRADE_COTE','FLAG_FANION']]
        df.columns=['station','time','value','status','grade','flag'];df['file']=name;frames.append(df)
        print(name,'temperature rows',len(df),flush=True)
    full=pd.concat(frames,ignore_index=True)
    identity_counts=full.groupby(['file','station'],dropna=False).size().reset_index(name='n_temperature_rows')
    identity_counts.to_csv(OUT/'identity_counts.csv',index=False)
    rejected_identity=int((~full.station.eq(STATION)).sum())
    full=full.loc[full.station.eq(STATION)].copy()
    status_counts=full.groupby(['status','grade'],dropna=False).size().reset_index(name='n_hourly_rows')
    status_counts.to_csv(OUT/'status_grade_counts.csv',index=False)
    day=daily_quality(full)
    day.to_parquet(OUT/'daily_qualified.parquet',index=False)
    yearrows=[]
    for year in range(2011,2026):
        idx=pd.date_range(f'{year}-01-01',f'{year}-12-31')
        complete=day.set_index('date').complete_wallclock.reindex(idx,fill_value=False)
        yearrows.append(dict(year=year,expected_days=len(idx),complete_local_days=int(complete.sum()),
                             complete_reported_wallclock_year=bool(complete.all())))
    years=pd.DataFrame(yearrows);years.to_csv(OUT/'qualification_years.csv',index=False)
    n_years=int(years.complete_reported_wallclock_year.sum())
    status={'station':STATION,'n_files':len(logs),'n_temperature_rows_exact_station':len(full),'n_identity_unresolved_rows':rejected_identity,'n_literal_v_grade_numeric12_rows':int((full.status.eq('V')&pd.to_numeric(full.grade,errors='coerce').isin([1,2])).sum()),
            'complete_local_wallclock_years':n_years,'complete_years':years.loc[years.complete_reported_wallclock_year,'year'].tolist(),
            'physical_day_timezone_verified':False,'strict_physical_reference_eligible':False,
            'reconstruction_scored':False,'prior_same_river_source':True,
            'limitation':'V and grade 1/2 are required as specified before download; other values, including Corrected with absent grades and records with nonmatching station IDs, are not called invalid but are not established as eligible. Local-day DST convention unresolved; source includes an upstream site on the same river.'}
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(status_counts.to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()
