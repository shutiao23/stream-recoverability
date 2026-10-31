#!/usr/bin/env python3
"""Post-index, metadata-only audit of prior USGS station contact."""
import argparse
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import subprocess
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_camelsh_hourly'
PRIVATE=ROOT/'private/wrr_camelsh_hourly_reference_20261027'

def freeze():
    path=OUT/'contact_plan.json'
    if path.exists():raise FileExistsError('Preserve existing contact plan')
    status=json.loads((OUT/'index_status.json').read_text());members=OUT/'archive_members.csv'
    if status['status']!='index_read':raise ValueError('Archive index changed')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Private source mappings are not ignored')
    source=[ROOT/'scripts/583_usgs_unresolved_network_count_screen.py',ROOT/'scripts/431_tr_cases.py',
            T.E1/'station_years.parquet',T.E1/'usgs_site_metadata.csv',
            ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json',
            ROOT/'results/wrr_review_response_20261027/external_usgs_late_start/candidate_roster.csv',
            ROOT/'results/wrr_review_response_20261027/external_usgs_unresolved_network/candidate_roster.csv']
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc after examining archive file names and multiple earlier reference screens; no archive member temperatures or prediction errors read',
        'correction':'The original index recognized zero IDs because its generic filename pattern omitted the observed _temperature suffix; retain that initial record and extract suffix-form names separately.',
        'selection':'Extract exactly 8–15 decimal digit USGS-like IDs from *_temperature.nc members; classify all by named source panel headers, station-year inventory, earlier USGS prior-contact lists, previously fetched donor API IDs and named metadata screens.',
        'uncontacted_candidate':'No exact ID in any of these inventories; conservative identity screen only. No estimate of unrecorded contacts, hidden network relationships, quality or climate independence.',
        }
    path.write_text(json.dumps(metadata,indent=2)+'\n');print('Recorded post-index identity screening plan')

def run():
    plan=json.loads((OUT/'contact_plan.json').read_text());members=OUT/'archive_members.csv'
    f=pd.read_csv(members,dtype=str);f['station_id']=f.member.map(lambda s:re.fullmatch(r'(\d{8,15})_temperature\.nc',Path(s).name) or [None,None][1])
    candidates=f[f.station_id.notna()].copy()
    if candidates.station_id.duplicated().any():raise ValueError('Duplicate station member')
    prior=T.load_script('camelsh_previous_contact',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py').prior_stations()
    jobs=T.load_script('camelsh_source_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')
    usgs=[x for x in jobs if x['provider']=='usgs'];source_columns=set();unique_paths={j['input_path'] for j in usgs}
    for path in unique_paths:
        with open(path,encoding='utf-8-sig',newline='') as h:header=next(csv.reader(h))
        if header[0]!='date':raise ValueError('Unexpected source panel header')
        source_columns.update(header[1:])
    years=pd.read_parquet(T.E1/'station_years.parquet',columns=['provider','station_id']);source_years=set(years.loc[years.provider.eq('usgs'),'station_id'].astype(str))
    manifest=json.loads((ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json').read_text())
    fetched={x for batch in manifest['batches'] for x in batch['sites']}
    screens=set()
    for path in [ROOT/'results/wrr_review_response_20261027/external_usgs_late_start/candidate_roster.csv',
                 ROOT/'results/wrr_review_response_20261027/external_usgs_unresolved_network/candidate_roster.csv']:
        screens.update(pd.read_csv(path,dtype=str).station_id.dropna())
    candidates['source_panel_column']=candidates.station_id.isin(source_columns)
    candidates['source_station_year']=candidates.station_id.isin(source_years)
    candidates['named_prior_inventory']=candidates.station_id.isin(prior)
    candidates['previous_donor_api_fetch']=candidates.station_id.isin(fetched)
    candidates['prior_reference_metadata_screen']=candidates.station_id.isin(screens)
    flags=['source_panel_column','source_station_year','named_prior_inventory','previous_donor_api_fetch','prior_reference_metadata_screen']
    candidates['no_named_prior_contact']=~candidates[flags].any(axis=1)
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);roster=PRIVATE/'archive_identity_screen.csv';candidates.to_csv(roster,index=False);roster.chmod(0o600)
    counts={'archive_files':len(f),'temperature_station_files':len(candidates),'distinct_station_ids':int(candidates.station_id.nunique()),
            'nonstation_files':len(f)-len(candidates),'source_panels_inspected':len(unique_paths),
            **{x:int(candidates[x].sum()) for x in flags},'no_named_prior_contact':int(candidates.no_named_prior_contact.sum())}
    status={'status':'metadata_only','counts':counts,'member_contents_opened':False,'temperature_values_opened':False,'model_errors_opened':False,
            'interpretation':'Exact identifier screening over named local inventories and source panel headers only; missing links do not demonstrate uncontacted data, distinct catchments, complete or quality-qualified years, or new climates.'}
    (OUT/'contact_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()
