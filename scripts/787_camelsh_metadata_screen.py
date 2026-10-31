#!/usr/bin/env python3
"""Screen CAMELSH candidate IDs using existing USGS metadata only."""
import argparse
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_camelsh_hourly';PRIVATE=ROOT/'private/wrr_camelsh_hourly_reference_20261027'
META=ROOT/'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'
SCOPE=ROOT/'results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv'
DONOR=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json'

def huc8(v):
    x=str(v).strip()
    if x in ('None','nan',''):return None
    if not x.isdigit():return None
    return x.zfill(8)[:8] if len(x)<=8 else x[:8]

def full_years(begin,end):
    b=pd.to_datetime(begin,errors='coerce',utc=True);e=pd.to_datetime(end,errors='coerce',utc=True)
    if pd.isna(b) or pd.isna(e) or e<b:return None
    first=max(2000,b.year+int((b.month,b.day)!=(1,1)))
    last=min(2025,e.year-int((e.month,e.day)!=(12,31)))
    return max(0,last-first+1)

def freeze():
    target=OUT/'metadata_plan.json'
    if target.exists():raise FileExistsError('Preserve metadata screening plan')
    contact=json.loads((OUT/'contact_status.json').read_text());roster=PRIVATE/'archive_identity_screen.csv'
    if contact['status']!='metadata_only':raise ValueError('Identity screen changed')
    inputs=[Path(__file__),roster,META,SCOPE,DONOR,T.E1/'usgs_site_metadata.csv',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py',
            ROOT/'scripts/490_review_completion_national_availability.py',ROOT/'scripts/431_tr_cases.py']
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc exploratory metadata screen after archive index and preliminary metadata counts; no CAMELSH temperature files or target prediction errors opened',
          'scope':'All 533 archive IDs with no exact match in the named prior-contact identity lists. Existing current-vintage USGS daily-series metadata and the prior project network-screen table only.',
          'candidate_rule':'USGS 00010/00003 primary stream series with known time zone and HUC8; at least four whole calendar years could lie within the reported date envelope during 2000–2025; reject obvious nonriver names, known prior HUC8, and known connected-component overlap. Require exactly one eligible series per site; unknown fields or missing metadata remain unknown.',
          'huc_rule':'Conservatively flag HUC8 shared with any known prior USGS station whose HUC is in available prior metadata, or flagged in the earlier network scope; metadata lookup is incomplete and different HUC8 does not establish hydrologic or climate independence.',
          'next_step':'Preserve all counts and excluded/unknown statuses. A separate count-only preflight and separate network-identity audit must occur before any chosen target temperature or prediction error is accessed.',
          'limits':'Posthoc and incomplete prior inventories; metadata date envelope is only an availability upper bound and gives no daily coverage, nonestimated status, subdaily quality, physical representativeness, natural outage or source-model independence guarantee.'}
    target.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded metadata-screen protocol')

def screen():
    plan=json.loads((OUT/'metadata_plan.json').read_text())
    roster=pd.read_csv(PRIVATE/'archive_identity_screen.csv',dtype={'station_id':str});ids=set(roster.loc[roster.no_named_prior_contact,'station_id'])
    features=json.loads(META.read_text())['features'];scope=pd.read_csv(SCOPE,dtype=str).drop_duplicates('station_id').set_index('station_id')
    prev=T.load_script('camelsh_prior_ids',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py').prior_stations()
    jobs=T.load_script('camelsh_prior_metadata_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')
    for path in {x['input_path'] for x in jobs if x['provider']=='usgs'}:
        with open(path,encoding='utf-8-sig',newline='') as f:prev.update(next(csv.reader(f))[1:])
    source_manifest=json.loads(DONOR.read_text());prev.update(s for b in source_manifest['batches'] for s in b['sites'])
    prior_hucs=set()
    for x in features:
        p=x['properties'];site=str(p.get('monitoring_location_id','')).removeprefix('USGS-')
        if site in prev:
            h=huc8(p.get('hydrologic_unit_code'))
            if h:prior_hucs.add(h)
    source=pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype=str)
    for h in source.huc_cd.dropna():
        if huc8(h):prior_hucs.add(huc8(h))
    stations={site:[] for site in ids};zones=T.load_script('camelsh_native_zones',ROOT/'scripts/490_review_completion_national_availability.py')
    for f in features:
        p=f['properties'];site=str(p.get('monitoring_location_id','')).removeprefix('USGS-')
        if site not in stations:continue
        name=str(p.get('monitoring_location_name') or '');h=huc8(p.get('hydrologic_unit_code'));n=full_years(p.get('begin'),p.get('end'));zone=zones.native_zone(p)
        metadata_ok=(p.get('agency_code')=='USGS'
                     and str(p.get('site_type_code') or '').startswith('ST')
                     and str(p.get('parameter_code'))=='00010'
                     and str(p.get('statistic_id'))=='00003'
                     and str(p.get('primary'))=='Primary'
                     and bool(h)
                     and bool(zone)
                     and n is not None
                     and n>=4
                     and not bool(__import__('re').search(r'LAKE|RESERVOIR|CANAL|TAILRACE|DIVERSION|POWERPLANT|REGULATING',name,__import__('re').I)))
        prior_huc=h in prior_hucs if h else None
        old=scope.loc[site] if site in scope.index else None
        old_huc=(str(old.get('same_HUC8_as_prior_record'))=='True') if old is not None else False
        old_connection=(str(old.get('component_has_prior_connection_screen'))=='True') if old is not None else False
        candidate=bool(metadata_ok and not prior_huc and not old_huc and not old_connection)
        stations[site].append({'station_id':site,'series_id':str(p.get('id') or f['id']),
            'station_name':name,'site_type_code':p.get('site_type_code'),'huc8':h,'native_zone':zone,
            'begin':p.get('begin'),'end':p.get('end'),'possible_full_years_2000_2025':n,
            'metadata_eligible':metadata_ok,'same_prior_huc8':prior_huc,'scope_prior_huc8':old_huc,
            'scope_known_connection':old_connection,'metadata_candidate_series':candidate,
            'in_earlier_network_scope':old is not None})
    entries=[]
    for site,rows in stations.items():
        if not rows:entries.append({'station_id':site,'metadata_status':'not_in_existing_daily_catalog','metadata_candidate':False});continue
        candidates=[x for x in rows if x['metadata_candidate_series']]
        if len(candidates)==1:entries.append({**candidates[0],'metadata_status':'candidate_one_series','metadata_candidate':True})
        else:
            entries.append({'station_id':site,'metadata_status':'multiple_candidate_series' if len(candidates)>1 else 'no_candidate_series_in_existing_metadata',
                            'metadata_candidate':False,'series_records':len(rows),'candidate_series_records':len(candidates)})
    frame=pd.DataFrame(entries).sort_values('station_id');path=PRIVATE/'metadata_screen.csv';frame.to_csv(path,index=False);path.chmod(0o600)
    result={'status':'metadata_screen_completed','archive_unmatched_to_named_prior_ids':len(ids),
            'sites_in_existing_usgs_daily_catalog':sum(bool(v) for v in stations.values()),'prior_huc8s_observed_in_local_metadata':len(prior_hucs),
            'status_counts':frame.metadata_status.value_counts().to_dict(),
            'metadata_candidates':int(frame.metadata_candidate.sum()),'temperature_values_opened':False,'model_errors_opened':False,'limitations':plan['limits']}
    (OUT/'metadata_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','screen']);a=p.parse_args();freeze() if a.action=='freeze' else screen()
