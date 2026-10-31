#!/usr/bin/env python3
"""Conservatively screen all 11 reservoir-network resources before data access."""
import argparse
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'
CATALOG=ROOT/'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'
DONOR=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json'

def ids():
    prior=T.load_script('usace_prior_station_ids',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py').prior_stations()
    jobs=T.load_script('usace_source_station_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source');source=set()
    for name in {x['input_path'] for x in jobs if x['provider']=='usgs'}:
        with open(name,encoding='utf-8-sig',newline='') as f:source.update(next(csv.reader(f))[1:])
    recent=json.loads(DONOR.read_text());return set(prior)|source|{s for b in recent['batches'] for s in b['sites']},source

def identity_sha(x):return ('\n'.join(sorted(x))+'\n')

def full_calendar_years(start,end):
    b=pd.Timestamp(start);e=pd.Timestamp(end)
    if e<b:return 0
    first=b.year+b.month!=1 or b.day!=1;last=e.year-e.month!=12 or e.day!=31
    return max(0,last-first+1)

def freeze():
    path=OUT/'roster_plan.json'
    if path.exists():raise FileExistsError('Preserve source roster plan')
    metadata=json.loads((OUT/'metadata_status.json').read_text());receipt=PRIVATE/'metadata_receipt.json'
    if metadata['status']!='completed':raise ValueError('Metadata intake incomplete')
    prior,source=ids();files=[Path(__file__),OUT/'metadata_plan.json',OUT/'metadata_status.json',receipt,CATALOG,DONOR,T.E1/'usgs_site_metadata.csv',
        ROOT/'scripts/583_usgs_unresolved_network_count_screen.py',ROOT/'scripts/431_tr_cases.py']
    for x in json.loads(receipt.read_text()):
        f=PRIVATE/f"metadata_{x['id']}.json"
        files.append(f)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after reviewing all 11 descriptions, filename inventories and an initial exact-ID overlap probe; no resource temperature data or model errors examined',
        'scope':'All 11 public collection resources; inspect all referenced USGS IDs, level-1 file date ranges and site coordinates before target measurements.',
        'candidate_rule':'Require at least one explicit USGS site ID, no exact match to named prior identities or source panel columns, and one unambiguously latest level-1 QA/QC file whose filename date span permits at least four full calendar years. Multiple referenced gages remain a network-identity warning, not automatically independent.',
        'file_rule':'Choose the uniquely latest declared end date from names matching level1-qaqc_YYYYMMDD-YYYYMMDD with optional version suffix; no selection by data values. A suspicious river-name or metadata mismatch must be held for investigation before scoring.',
        'network':'Record distances to named prior USGS sites with known coordinates and all referenced gages. River-network and prior-role separation must be assessed separately; upstream/downstream pairs and tributaries are not independent climates.',
        'source_condition':'Authors describe level-1 QC and fouling/calibration corrections. This does not establish nonestimated values, continuous timestamp support or physical sensor accuracy.',
        }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded metadata-based reservoir candidate rules')

def run():
    plan=json.loads((OUT/'roster_plan.json').read_text())
    prior,source=ids()
    coords=[]
    for feature in json.loads(CATALOG.read_text())['features']:
        p=feature['properties'];site=str(p.get('monitoring_location_id','')).removeprefix('USGS-');geo=feature.get('geometry') or {};xy=geo.get('coordinates') or []
        if site in prior and len(xy)>=2:
            try:lon,lat=float(xy[0]),float(xy[1])
            except (ValueError,TypeError):continue
            if np.isfinite(lat) and np.isfinite(lon):coords.append((site,lat,lon,site in source))
    for r in pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype=str).itertuples(index=False):
        try:lat,lon=float(r.dec_lat_va),float(r.dec_long_va)
        except (ValueError,TypeError):continue
        if np.isfinite(lat) and np.isfinite(lon):coords.append((r.site_no,lat,lon,r.site_no in source))
    points=pd.DataFrame(coords,columns=['id','lat','lon','source']).drop_duplicates(['id','lat','lon'])
    rows=[]
    for item in json.loads((PRIVATE/'metadata_receipt.json').read_text()):
        info=json.loads((PRIVATE/f"metadata_{item['id']}.json").read_text());ident=info['numeric_ids_found_in_metadata'];lat=lon=np.nan
        for c in info['coverage']:
            e=re.search(r'(?:^|;\s*)east=([-\d.]+)',c);n=re.search(r'(?:^|;\s*)north=([-\d.]+)',c)
            if e and n:lon=float(e.group(1));lat=float(n.group(1));break
        options=[]
        for f in info['files']:
            name=str(f.get('file_name') or '');m=re.search(r'level1-qaqc_(\d{8})-(\d{8})(?:_v\d+)?\.csv$',name,re.I)
            if m:options.append({'file_name':name,'size':int(f['size']),'url':f['url'],
                                  'start':pd.Timestamp(m.group(1)).strftime('%Y-%m-%d'),'end':pd.Timestamp(m.group(2)).strftime('%Y-%m-%d')})
        options.sort(key=lambda x:(x['end'],x['start'],x['file_name']),reverse=True)
        unique_latest=bool(options and len(options)==1 or options[0]['end']!=options[1]['end'])
        latest=options[0] if unique_latest else None;n=full_calendar_years(latest['start'],latest['end']) if latest else None
        prior_hits=[x for x in ident if x in prior];source_hits=[x for x in ident if x in source]
        eligible=bool(ident and not prior_hits and not source_hits and latest and n>=4 and np.isfinite(lat) and np.isfinite(lon))
        min_prior=min_source=np.nan
        if np.isfinite(lat) and np.isfinite(lon) and len(points):
            rad=np.pi/180.;dl=(points.lat.to_numpy(float)-lat)*rad;dn=(points.lon.to_numpy(float)-lon)*rad
            a=np.sin(dl/2)**2+np.cos(lat*rad)*np.cos(points.lat.to_numpy(float)*rad)*np.sin(dn/2)**2
            dist=12742*np.arcsin(np.sqrt(np.clip(a,0,1)));min_prior=float(dist.min());idx=points.source.to_numpy(bool)
            if idx.any():min_source=float(dist[idx].min())
        rows.append({'resource_id':item['id'],'title':info['title'],'gage_ids':';'.join(ident),'n_gage_ids':len(ident),
                     'prior_gage_count':len(prior_hits),'source_gage_count':len(source_hits),'latitude':lat,'longitude':lon,
                     'nearest_prior_km':min_prior,'nearest_source_panel_km':min_source,
                     'latest_level1_filename':latest['file_name'] if latest else None,'latest_level1_url':latest['url'] if latest else None,
                     'latest_level1_size':latest['size'] if latest else None,'start':latest['start'] if latest else None,'end':latest['end'] if latest else None,
                     'possible_full_calendar_years':n,'metadata_candidate':eligible,
                     'caveat':'Exact-ID and filename metadata only; site and river-network identity, corrections, timezone and quality remain unverified.'})
    frame=pd.DataFrame(rows).sort_values('resource_id');path=PRIVATE/'roster.csv';frame.to_csv(path,index=False);path.chmod(0o600)
    result={'status':'metadata_screened','resources':len(frame),'resources_with_referenced_gage_ids':int(frame.n_gage_ids.gt(0).sum()),
            'resources_with_multiple_referenced_gages':int(frame.n_gage_ids.gt(1).sum()),
            'resources_with_named_prior_gage':int(frame.prior_gage_count.gt(0).sum()),
            'metadata_candidates':int(frame.metadata_candidate.sum()),'candidate_same_network_not_excluded':True,
            'prior_ids_with_known_coordinates':int(points.id.nunique()),'temperature_values_opened':False,'prediction_errors_opened':False,
            'limits':'Coordinates and exact-ID filters do not establish river-network separation, source history, timestamp completeness, nonestimated quality or independent climates. Files are chosen by stated date envelope; potentially misleading names remain to be investigated.'}
    (OUT/'roster_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
