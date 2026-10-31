#!/usr/bin/env python3
"""Best-effort prior-identity and proximity audit of the frozen RivTemp roster.

Reads location metadata only. No target dates, water values or model results are
used. Proximity is a screening signal, not a river-network or independence test.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
import pandas as pd
from pyproj import Geod

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata';PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026';REV=ROOT/'results/wrr_review_response_20261027'


def inventory():
    frames=[]
    def add(path,name,idcol,lat,lon,encoding='utf8',select=None):
        x=pd.read_csv(path,dtype=str,encoding=encoding)
        if select is not None:x=x.loc[select(x)]
        z=x[[idcol,lat,lon]].rename(columns={idcol:'station_id',lat:'latitude',lon:'longitude'});z['inventory']=name
        z['latitude']=pd.to_numeric(z.latitude,errors='coerce');z['longitude']=pd.to_numeric(z.longitude,errors='coerce')
        z=z.loc[z.latitude.between(-90,90)&z.longitude.between(-180,180)&z.station_id.notna()].drop_duplicates(['inventory','station_id','latitude','longitude'])
        frames.append(z)
    add(ROOT/'results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv','USGS_source_metadata','site_no','dec_lat_va','dec_long_va')
    add(REV/'external_bc_air2stream/roster.csv','BC_published_roster','station_number','latitude','longitude')
    add(REV/'external_nova_scotia_verified/exploratory_location_audit.csv','Nova_Scotia_opened_sites','station_id','latitude','longitude')
    add(REV/'external_eccc_red/auto-water-qual-eau-stations.csv','ECCC_automatic_catalog','STATION_NO','LATITUDE','LONGITUDE',encoding='cp1252')
    folder=ROOT/'results/wrr_review_completion_20261024/national_meaning/site_results';processed=set()
    for path in folder.glob('*.json'):
        try:
            if json.loads(path.read_text()).get('status')=='processed':processed.add(path.stem)
        except (OSError,json.JSONDecodeError):continue
    add(ROOT/'results/wrr_review_completion_20261024/national_meaning/national_roster.csv','USGS_processed_national','station_id','latitude','longitude',select=lambda x:x.station_id.isin(processed))
    return pd.concat(frames,ignore_index=True)


def nearest(roster,prior):
    g=Geod(ellps='WGS84');rows=[]
    for item in roster.itertuples(index=False):
        lat=float(item.MonitoringLocationLatitude);lon=float(item.MonitoringLocationLongitude)
        for name,group in prior.groupby('inventory',sort=True):
            _,_,distance=g.inv(np.full(len(group),lon),np.full(len(group),lat),group.longitude.to_numpy(float),group.latitude.to_numpy(float))
            i=int(np.argmin(distance));record=group.iloc[i]
            rows.append({'MonitoringLocationID':item.MonitoringLocationID,'inventory':name,'nearest_prior_station_id':record.station_id,'distance_km':float(distance[i]/1000)})
    return pd.DataFrame(rows)


def main():
    state=json.loads((OUT/'roster_freeze.json').read_text())
    if state['status']!='all_location_metadata_frozen_before_qualification':raise ValueError('location roster not frozen')
    roster=pd.read_csv(PRIVATE/'all_locations_before_qualification.csv',dtype=str,keep_default_na=False)
    if roster.MonitoringLocationID.duplicated().any() or len(roster)!=state['unique_location_ids']:raise ValueError('frozen roster has ambiguous location IDs')
    prior=inventory();dist=nearest(roster,prior)
    dup=roster.groupby(['MonitoringLocationLatitude','MonitoringLocationLongitude']).size()
    counts=dist.groupby('inventory').agg(locations=('MonitoringLocationID','nunique'),within_100m=('distance_km',lambda x:int(x.le(.1).sum())),within_10km=('distance_km',lambda x:int(x.le(10).sum())),nearest_km=('distance_km','min')).reset_index()
    # Search exact, full IDs in selected text files only. No binary-cache or
    # network-graph exhaustive search is implied by an empty result.
    ids=roster.MonitoringLocationID.tolist()
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf8') as f:
        f.write('\n'.join(ids)+'\n');f.flush()
        command=['rg','-l','-F','-f',f.name,'scripts','docs','paper','results','data','data_versions','--glob','*.py','--glob','*.csv','--glob','*.json','--glob','*.md','--glob','*.tex','--glob','*.yaml','--glob','!results/wrr_review_response_20261027/external_rivtemp_metadata/**','--max-filesize','25M']
        search=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=120)
    if search.returncode not in (0,1):raise RuntimeError('prior identity search failed: '+search.stderr[:300])
    dist.to_csv(PRIVATE/'nearest_prior_locations.csv',index=False);(PRIVATE/'nearest_prior_locations.csv').chmod(0o600)
    status={'status':'metadata_screen_completed_not_network_qualified','frozen_location_ids':len(roster),'inventories':counts.to_dict('records'),
      'coincident_coordinate_groups':int(dup.gt(1).sum()),'locations_with_coincident_coordinates':int(dup[dup.gt(1)].sum()),
      'prior_exact_id_text_files':len(search.stdout.splitlines()),
      'text_search_scope':'exact IDs in selected repository text files up to 25 MB, excluding new intake; binary, compressed, ignored and larger files not searched',
      'data_scope':'only published location metadata; target dates and water values not read; no reconstruction scored',
      'limitation':'different IDs, geographic distance, a clear exact-text search or different river names do not prove no prior contact, hydrologic separation, independent climates, or reference quality'}
    (OUT/'prior_contact_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()
