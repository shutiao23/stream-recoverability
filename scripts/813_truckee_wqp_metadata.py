#!/usr/bin/env python3
"""Post-hoc, metadata-only search for nearby water-temperature sampling sites."""
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';URL='https://www.waterqualitydata.us/data/Station/search'

def distance_km(lat,lon,lats,lons):
    k=np.pi/180.;a=np.sin((lats-lat)*k/2)**2+np.cos(lat*k)*np.cos(lats*k)*np.sin((lons-lon)*k/2)**2
    return 12742*np.arcsin(np.sqrt(np.clip(a,0,1)))

def freeze():
    dest=OUT/'wqp_site_search_plan.json'
    if dest.exists():raise FileExistsError('Preserve existing WQP plan')
    score=json.loads((OUT/'exploratory_score_status.json').read_text());roster=PRIVATE/'exploratory_roster.csv';stations=OUT/'station_metadata_03.csv'
    if score['status']!='exploratory_scored':raise ValueError('Prior scored cohort unavailable')
    f=pd.read_csv(roster);site=f.station_code.unique()
    if len(site)!=1 or len(f)!=4:raise ValueError('Unexpected scored target')
    meta=pd.read_csv(stations).set_index('Station_Code',verify_integrity=True);r=meta.loc[site[0]]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc after viewing target scores and provider metadata, before requesting WQP station metadata or additional temperature observations',
          'target_station':str(site[0]),'latitude':float(r.Latitude),'longitude':float(r.Longitude),
          'query':'WQP Station service: all reporting organizations and site types, water-temperature characteristic, within 5 miles of the published coordinates, sample dates 2011–2020. This returns station metadata only.',
          'distance_thresholds_km':[0.25,0.5,1.0,5.0],
          'candidate_rule':'Preserve all returned station metadata. Proximity and a temperature result during the date envelope are leads only; establish physical river connection, sample timing, organizational independence, measurement type, data quality and access before any accuracy comparison.',
          'caveats':'The WQP historical profile may omit some USGS updates after March 2024. A nearby station may share an instrument or underlying data; multiple sites in one watershed are not independent climates. A failed or empty query is not proof that no reference exists.',
          'endpoint':URL}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded metadata-only WQP site search')

def fetch():
    plan=json.loads((OUT/'wqp_site_search_plan.json').read_text())
    if (OUT/'wqp_site_search_status.json').exists():raise FileExistsError('Preserve prior WQP search')
    params={'lat':plan['latitude'],'long':plan['longitude'],'within':'5','characteristicName':'Temperature, water',
            'startDateLo':'01-01-2011','startDateHi':'12-31-2020','mimeType':'csv','zip':'no','sorted':'no'}
    result={'status':'unknown','search_center':'DWR TRB8 coordinates','radius_miles':5,'observation_values_requested':False,
            'metadata_time_window':'2011–2020','limitations':plan['caveats']}
    try:
        r=requests.get(URL,params=params,timeout=45,headers={'User-Agent':'stream-temperature reference metadata research/1.0'})
        result.update(http_status=r.status_code,response_bytes=len(r.content))
        if r.status_code==204:result.update(status='completed_no_station_rows',station_rows=0)
        elif r.status_code==200:
            table=pd.read_csv(io.BytesIO(r.content),dtype=str);columns=['MonitoringLocationIdentifier','MonitoringLocationName','LatitudeMeasure','LongitudeMeasure','MonitoringLocationTypeName','OrganizationIdentifier']
            if not set(columns).issubset(table.columns):raise ValueError('Unexpected WQP station schema')
            raw=PRIVATE/'wqp_station_metadata.csv';raw.write_bytes(r.content);raw.chmod(0o600)
            lat=pd.to_numeric(table.LatitudeMeasure,errors='coerce');lon=pd.to_numeric(table.LongitudeMeasure,errors='coerce')
            table['distance_km']=distance_km(plan['latitude'],plan['longitude'],lat.to_numpy(float),lon.to_numpy(float))
            table['finite_coordinates']=np.isfinite(table.distance_km);table=table.sort_values(['distance_km','MonitoringLocationIdentifier'],na_position='last')
            path=PRIVATE/'wqp_station_distance_audit.csv';table.to_csv(path,index=False);path.chmod(0o600)
            result.update(status='completed_metadata_only',station_rows=len(table),unique_station_ids=int(table.MonitoringLocationIdentifier.nunique()),
                rows_with_coordinates=int(table.finite_coordinates.sum()),rows_within_0_25km=int(table.distance_km.le(.25).sum()),
                rows_within_0_5km=int(table.distance_km.le(.5).sum()),rows_within_1km=int(table.distance_km.le(1.).sum()),
                rows_within_5km=int(table.distance_km.le(5.).sum()),)
    except (requests.RequestException,ValueError,KeyError,pd.errors.ParserError) as e:result['error_type']=type(e).__name__
    (OUT/'wqp_site_search_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','fetch']);a=p.parse_args();freeze() if a.action=='freeze' else fetch()
