#!/usr/bin/env python3
"""Match fixed NS candidate names to provincial station-map metadata.

This uses only station metadata. Name-based co-location and great-circle
distance do not establish river-network or climate independence.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
URL='https://data.novascotia.ca/resource/i9ee-9hct.json'
SITE_MAP={'NS01DL0009':('NS01DL001','KELLEY RIVER AT EIGHT MILE FORD'),
          'NS01FB0001':('NS01FB001','NORTHEAST MARGAREE RIVER AT MARGAREE VALLEY')}


def haversine(lat,lon,latitudes,longitudes):
    latitudes=np.asarray(latitudes,float);longitudes=np.asarray(longitudes,float)
    a=np.sin(np.deg2rad(latitudes-lat)/2)**2+np.cos(np.deg2rad(lat))*np.cos(np.deg2rad(latitudes))*np.sin(np.deg2rad(longitudes-lon)/2)**2
    return 2*6371.0*np.arcsin(np.sqrt(np.clip(a,0,1)))


def audit(records,source):
    rows=[]
    for site,(legacy,name) in SITE_MAP.items():
        match=[x for x in records if x.get('station_nu')==legacy and x.get('station_na','').strip().upper()==name]
        if len(match)!=1:raise ValueError(f'nonunique published station-map identity: {site}')
        geom=match[0].get('the_geom',{});coordinates=geom.get('coordinates',[])
        if geom.get('type')!='Point' or len(coordinates)!=2:raise ValueError('unexpected station coordinates')
        lon,lat=map(float,coordinates)
        if not (43<=lat<=48 and -67<=lon<=-59):raise ValueError('station falls outside expected Nova Scotia metadata bounds')
        valid=source.dropna(subset=['lat','lon']).reset_index(drop=True)
        if valid.empty:raise ValueError('source coordinate inventory empty')
        distances=haversine(lat,lon,valid.lat,valid.lon);index=int(np.argmin(distances))
        rows.append(dict(station_id=site,map_station_id=legacy,map_station_name=name,latitude=lat,longitude=lon,
          nearest_source_usgs_id=str(valid.loc[index,'site_no']),nearest_source_usgs_name=str(valid.loc[index,'station_nm']),
          nearest_source_usgs_km=float(distances[index]),forcing_latitude=round(lat,2),forcing_longitude=round(lon,2)))
    return pd.DataFrame(rows)


def main():
    response=requests.get(URL,params={'$limit':100},timeout=45,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status();data=response.json()
    if len(data)>=100:raise RuntimeError('map result may be truncated')
    source=pd.read_csv(ROOT/'results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv',dtype={'site_no':str})
    source['lat']=pd.to_numeric(source.dec_lat_va,errors='coerce');source['lon']=pd.to_numeric(source.dec_long_va,errors='coerce')
    f=audit(data,source);f.to_csv(OUT/'exploratory_location_audit.csv',index=False)
    state={'status':'metadata_checked','retrieved_utc':datetime.now(timezone.utc).isoformat(),'map_url':URL,
      'candidate_sites':len(f),'map_records_returned':len(data),'source_usgs_locations_checked':int(source[['lat','lon']].notna().all(axis=1).sum()),
      'mapping_basis':'provincial station map names and historical station codes match provincial monitoring report station descriptions',
      'forcing_coordinates':'site map coordinates rounded to 0.01 degree; derived forcing grid and local water timezone remain separate issues',
      'limitations':'metadata name matching and distance to USGS source stations do not prove exact gauge identity, catchment disconnection, absence from all other inventories or independent climates'}
    (OUT/'exploratory_location_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(f.to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()
