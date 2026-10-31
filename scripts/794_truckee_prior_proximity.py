#!/usr/bin/env python3
"""Metadata-only prior-USGS proximity audit for the Truckee DWR stations."""
import argparse
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'
CATALOG=ROOT/'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'
DONOR=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json'

def identities():
    source=T.load_script('truckee_prior_ids',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py').prior_stations()
    jobs=T.load_script('truckee_source_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source');columns=set()
    for path in {x['input_path'] for x in jobs if x['provider']=='usgs'}:
        with open(path,encoding='utf-8-sig',newline='') as f:columns.update(next(csv.reader(f))[1:])
    previous=json.loads(DONOR.read_text());source=set(source)|columns|{x for b in previous['batches'] for x in b['sites']}
    return source,columns

def identity_sha(ids):return ('\n'.join(sorted(ids))+'\n')

def freeze():
    dest=OUT/'prior_proximity_plan.json'
    if dest.exists():raise FileExistsError('Preserve Truckee prior-contact plan')
    status=json.loads((OUT/'station_metadata_status.json').read_text())
    if status['status']!='completed':raise ValueError('Station metadata incomplete')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:raise ValueError('Private roster not ignored')
    files=[Path(__file__),CATALOG,DONOR,T.E1/'usgs_site_metadata.csv',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py',
           ROOT/'scripts/431_tr_cases.py',OUT/'station_metadata_status.json',OUT/'metadata.xml']+[OUT/x['file'] for x in status['tables']]
    source,columns=identities()
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after published station descriptions, coordinate metadata and evidence of prior Truckee-basin USGS caches; before obtaining DWR time-series or evaluating errors',
          'selection':'All 12 DWR stations from the source station metadata; report date-envelope possibilities and distance to named prior USGS identities with available official coordinates.',
          'prior_scope':'Separate source-panel column identities from a wider collection of earlier source, external, cache and most recent donor-data IDs; both are best-effort inventories. Multiple coordinates per ID are retained.',
          'interpretation':'Straight-line proximity is not proof of same gauge, same measurement, connection or independence. All 12 DWR sites belong to the same managed Truckee watershed and must not be counted as independent climates.',
          }
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded Truckee prior-contact proximity plan')

def distances(lat,lon,lats,lons):
    r=np.pi/180;dlat=(lats-lat)*r;dlon=(lons-lon)*r
    a=np.sin(dlat/2)**2+np.cos(lat*r)*np.cos(lats*r)*np.sin(dlon/2)**2
    return 12742*np.arcsin(np.sqrt(np.clip(a,0,1)))

def run():
    plan=json.loads((OUT/'prior_proximity_plan.json').read_text())
    prior,source_columns=identities()
    coords=[]
    for feature in json.loads(CATALOG.read_text())['features']:
        p=feature['properties'];site=str(p.get('monitoring_location_id','')).removeprefix('USGS-');geo=feature.get('geometry') or {};xy=geo.get('coordinates') or []
        if site in prior and len(xy)>=2:
            try:lon,lat=float(xy[0]),float(xy[1])
            except (ValueError,TypeError):continue
            if np.isfinite(lat) and np.isfinite(lon):coords.append({'station_id':site,'latitude':lat,'longitude':lon,'source_panel':site in source_columns})
    existing=pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype=str)
    for r in existing.itertuples(index=False):
        try:lat,lon=float(r.dec_lat_va),float(r.dec_long_va)
        except (ValueError,TypeError):continue
        coords.append({'station_id':r.site_no,'latitude':lat,'longitude':lon,'source_panel':r.site_no in source_columns})
    coord=pd.DataFrame(coords).drop_duplicates(['station_id','latitude','longitude'])
    station=pd.read_csv(OUT/'station_metadata_03.csv',dtype=str)
    if len(station)!=12 or station.Station_Code.duplicated().any():raise ValueError('Unexpected DWR metadata')
    reports=[]
    for row in station.itertuples(index=False):
        lat=float(row.Latitude);lon=float(row.Longitude);item={'station_code':row.Station_Code}
        for kind in ('source_panel','any_named_prior'):
            f=coord[coord.source_panel] if kind=='source_panel' else coord
            if f.empty:item[kind+'_nearest_km']=np.nan;continue
            dist=distances(lat,lon,f.latitude.to_numpy(float),f.longitude.to_numpy(float));idx=int(np.argmin(dist))
            item[kind+'_nearest_km']=float(dist[idx]);item[kind+'_nearest_id']=f.iloc[idx].station_id
        begin=pd.to_datetime(row.Dataset_Begin_Date,errors='raise');end=pd.to_datetime(row.Dataset_End_Date,errors='raise')
        first=begin.year+begin.month!=1 or begin.day!=1;last=end.year-end.month!=12 or end.day!=31
        item['possible_full_calendar_years']=max(0,last-first+1);reports.append(item)
    result=pd.DataFrame(reports);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);path=PRIVATE/'proximity.csv';result.to_csv(path,index=False);path.chmod(0o600)
    stats={'status':'metadata_only_with_known_truckee_prior_cache','stations':len(result),
           'known_prior_ids':len(prior),'prior_ids_with_coordinates':coord.station_id.nunique(),
           'source_panel_ids_with_coordinates':coord.loc[coord.source_panel,'station_id'].nunique(),
           'at_least_four_possible_full_years':int(result.possible_full_calendar_years.ge(4).sum()),
           'same_watershed_independence_groups_at_most':1,
           'nearest_source_panel_within_250m':int(result.source_panel_nearest_km.le(.25).sum()),
           'nearest_source_panel_within_1km':int(result.source_panel_nearest_km.le(1).sum()),
           'nearest_any_named_prior_within_250m':int(result.any_named_prior_nearest_km.le(.25).sum()),
           'nearest_any_named_prior_within_1km':int(result.any_named_prior_nearest_km.le(1).sum()),
           'nearest_any_named_prior_within_10km':int(result.any_named_prior_nearest_km.le(10).sum()),
           'station_time_series_opened':False,'temperature_values_opened':False,'model_errors_opened':False,
           'limits':plan['interpretation']+' Coordinate inventories may omit prior sites, and latitude/longitude does not prove river connectivity, exposure, precise gauge identity, sensor quality or complete data.'}
    (OUT/'prior_proximity_status.json').write_text(json.dumps(stats,indent=2)+'\n');print(json.dumps(stats,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
