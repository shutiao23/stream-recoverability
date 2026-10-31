#!/usr/bin/env python3
"""Get NASA POWER air data for the frozen Truckee exploratory cohort."""
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'
URL='https://power.larc.nasa.gov/api/temporal/daily/point'

def main():
    plan=json.loads((OUT/'exploratory_score_plan.json').read_text());roster=PRIVATE/'exploratory_roster.csv'
    if (OUT/'exploratory_forcing_status.json').exists():raise FileExistsError('Preserve initial weather acquisition')
    sites=pd.read_csv(roster);site=sites.station_code.iloc[0]
    if sites.station_code.nunique()!=1 or len(sites)!=4:raise ValueError('Exploratory cohort changed')
    lat=round(float(sites.latitude.iloc[0]),2);lon=round(float(sites.longitude.iloc[0]),2)
    start=int(sites.year.min());end=int(sites.year.max());params={'parameters':'T2M','community':'RE','longitude':lon,'latitude':lat,
        'start':f'{start}0101','end':f'{end}1231','format':'JSON','time-standard':'LST'}
    r=requests.get(URL,params=params,timeout=50,headers={'User-Agent':'stream-temperature reference research/1.0'});r.raise_for_status();data=r.json()
    raw=PRIVATE/'exploratory_power_response.json';raw.write_bytes(r.content);raw.chmod(0o600)
    values=data['properties']['parameter']['T2M'];idx=pd.date_range(f'{start}-01-01',f'{end}-12-31',freq='D')
    temperatures=pd.Series([values.get(day.strftime('%Y%m%d'),np.nan) for day in idx],dtype=float)
    temperatures=temperatures.where(temperatures.gt(-990));frame=pd.DataFrame({'date':idx,'air_temperature_c':temperatures,
        'station_id':site,'network_id':'truckee_'+site})
    selected=frame[frame.date.dt.year.isin(sites.year)]
    if len(selected)!=sum(366 if pd.Timestamp(int(y),12,31).is_leap_year else 365 for y in sites.year) or not np.isfinite(selected.air_temperature_c).all():raise ValueError('Missing forcing for selected reference years')
    path=PRIVATE/'exploratory_air_forcing.parquet';frame.to_parquet(path,index=False);path.chmod(0o600)
    status={'status':'forcing_complete','requested_dates':len(frame),'selected_years':len(sites),'selected_year_days':len(selected),
            'coordinates_rounded':True,'time_standard':'NASA POWER local solar time','retrieved_utc':datetime.now(timezone.utc).isoformat(),'source':URL,'parameters':params,
            'limitations':'Current gridded air estimates are not direct station measurements; local solar days may not align with reported PST water days or historical API versions.'}
    (OUT/'exploratory_forcing_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':main()
