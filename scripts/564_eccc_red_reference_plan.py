#!/usr/bin/env python3
"""Freeze one metadata-selected ECCC Red River station before value retrieval.

This is a single same-river exploratory reference, not an independent basin or
preregistered confirmation. Dataset codes and counts are obtained from public
metadata and named local contact inventories, not temperature observations.
"""
import io
import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_eccc_red'
BASE='/substances/monitor/automated-fresh-water-quality-monitoring-and-surveillance-data/'
API='https://data-donnees.az.ec.gc.ca/api/'
STATION='MA05OC0001'
ALIAS='05102500'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    r=requests.get(API+'path_contents',params={'path':BASE},timeout=40);r.raise_for_status();doc=r.json()
    names=['auto-water-qual-eau-stations.csv','auto-water-qual-eau-variableinfo.csv','auto-water-qual-eau-tabledescriptions.csv']
    for name in names:
        path=OUT/name
        # Preserve the metadata snapshot used by the frozen plan.
        if not path.exists():
            response=requests.get(API+'file',params={'path':BASE+name},timeout=45);response.raise_for_status()
            path.write_bytes(response.content)
    stations=pd.read_csv(OUT/names[0],encoding='cp1252',dtype={'STATION_NO':str})
    row=stations.loc[stations.STATION_NO.eq(STATION)]
    if len(row)!=1:raise ValueError('Selected metadata identity not unique')
    files=[x for x in doc['path_contents'] if x['name'].startswith('auto-water-qual-eau-'+STATION+'-') and x['name'].endswith('.csv')]
    # Fix all published blocks covering 2011--2025 before retrieving values.
    files=[x for x in files if any(str(y) in x['name'] for y in ['2011','2016','2018','2022','2024','2025'])]
    if len(files)!=6:raise ValueError('Unexpected file roster; inspect metadata without selecting by observed errors')
    roster_path=OUT/'file_roster.json'
    if roster_path.exists():
        oldfiles=json.loads(roster_path.read_text())
        if [x['name'] for x in oldfiles] != [x['name'] for x in files]:raise RuntimeError('Frozen source file roster changed')
    else:
        pd.DataFrame(files).to_json(roster_path,orient='records',indent=2)
    station_path=OUT/'station_metadata.csv'
    if not station_path.exists():row.to_csv(station_path,index=False)
    inputs=[('source_usgs','results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv','site_no'),
            ('previous_e10','results/wrr_target_recovery_20261022/e10_sealed_usgs/sealed_roster.csv','station_id'),
            ('national_metadata','results/wrr_review_completion_20261024/national_meaning/national_roster.csv','station_id'),
            ('expanded_identity','results/wrr_submission_ready/followup_20261021/usgs_prior_cache_audit/expanded_prior_station_inventory.csv','station_id')]
    identity={}
    for name,path,column in inputs:
        d=pd.read_csv(ROOT/path,dtype={column:str});identity[name]=int(d[column].eq(ALIAS).sum())
    prior=ROOT/'results/development_v11/eccc_automated_temperature/selected_station_summary.csv'
    old=pd.read_csv(prior,dtype={'site_id':str});identity['previous_eccc_daily_station']=int(old.site_id.eq(STATION).sum())
    point={'station_id':STATION,'usgs_alias':ALIAS,'named_inventory_matches':identity,
           'same_river_source':'USGS-05054000 Red River of the North at Fargo, in source station metadata; separation about 241 km, same river basin',
           'identity_evidence':'https://pubs.usgs.gov/publication/sir20255002/full',
           'caveat':'named inventories only; zero identifier matches does not establish all-cache or independent-river status'}
    (OUT/'prior_contact_audit.json').write_text(json.dumps(point,indent=2)+'\n')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'selected_station':STATION,'usgs_alias':ALIAS,
          'selection':'single station with public metadata and 2011--2025 data blocks, no match in named prior source, E10, national and earlier ECCC daily inventories; no temperature values or reconstruction results used',
          'source':'https://open.canada.ca/data/en/dataset/f258b0c8-7871-4572-b567-1ba2bd55f1b6',
          'reference_rule':'VMV 4730 water temperature, validated status V, quality grade 1 or 2, unflagged finite values; each provider-local date requires exactly one valid reading in each of 24 distinct local hours; no interpolation; require >=4 complete calendar years',
          'time_caveat':'dictionary states local time but does not resolve daylight-saving treatment, physical day boundaries or sensor changes; 24 wall-clock bins are not assumed to prove 24 physical hours',
          'scope':'unregistered single-station exploratory same-river transfer only; upstream Red River station was in source model data; not a new independent climate, watershed, natural-outage or risk guarantee',
          'quality_grade':'official metadata states 1 excellent, 2 good, 3 fair, 4 poor; validation V means validated',
          'files': [x['name'] for x in files]}
    p=OUT/'plan.json'
    if p.exists():
        oldplan=json.loads(p.read_text())
        if oldplan['selected_station']!=STATION or oldplan['files']!=plan['files']:raise RuntimeError('Frozen station/file roster changed')
    else:p.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'station':STATION,'files':plan['files'],'prior':identity,'same_river_source':True},indent=2))

if __name__=='__main__':main()
