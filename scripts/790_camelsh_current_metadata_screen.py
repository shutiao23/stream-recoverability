#!/usr/bin/env python3
"""Apply the fixed reference-eligibility metadata rules to current USGS data."""
import argparse
import csv
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import re
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_camelsh_hourly'
PRIVATE=ROOT/'private/wrr_camelsh_hourly_reference_20261027';CACHE=PRIVATE/'current_metadata'
OLD=ROOT/'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'
SCOPE=ROOT/'results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv'
DONOR=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/donor_usgs_daily_snapshot/request_manifest.json'

def freeze():
    path=OUT/'current_screen_plan.json'
    if path.exists():raise FileExistsError('Preserve current metadata screen')
    acq=json.loads((OUT/'unlisted_metadata_acquisition.json').read_text());receipt=CACHE/'receipt.json'
    if acq['status']!='completed':raise ValueError('Current metadata acquisition incomplete')
    files=[Path(__file__),receipt,CACHE/'station_ids.json',OLD,SCOPE,DONOR,T.E1/'usgs_site_metadata.csv',
           ROOT/'scripts/583_usgs_unresolved_network_count_screen.py',ROOT/'scripts/431_tr_cases.py',
           ROOT/'scripts/490_review_completion_national_availability.py',ROOT/'scripts/787_camelsh_metadata_screen.py']
    for item in json.loads(receipt.read_text()):
        for kind in ('sites','series'):
            f=CACHE/f"{kind}_{item['batch']:02d}.dat"
            if item[kind]['status']!='completed':raise ValueError('Metadata response changed')
            files.append(f)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after acquiring current site and series metadata; before approved-count preflight or target observation/error access',
          'rules':'Same substantive stream, HUC8, time-zone, non-obvious-waterbody and >=4 possible complete calendar years in 2000–2025 as the original metadata screen. Additionally require an explicit Y/N daylight-saving flag from site metadata. Keep sites with >1 eligible primary daily series as ambiguous.',
          'prior_exclusions':'Exclude HUC8 already observed for named prior stations and earlier known connected-component contacts; unobserved HUC or network links are not assumed independent.',
          'limits':'Selection remains posthoc, depends on current metadata and incomplete prior inventories. No count, nonestimated status, complete subdaily sampling or independent network is verified.'}
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded current USGS metadata-screen rules')

def screen():
    plan=json.loads((OUT/'current_screen_plan.json').read_text())
    ids=json.loads((CACHE/'station_ids.json').read_text());receipts=json.loads((CACHE/'receipt.json').read_text())
    sites={};series=[]
    for item in receipts:
        body=(CACHE/f"sites_{item['batch']:02d}.dat").read_text();lines=[x for x in body.splitlines() if x and not x.startswith('#')]
        table=pd.read_csv(io.StringIO('\n'.join(lines)),sep='\t',skiprows=[1],dtype=str).fillna('')
        for row in table.to_dict('records'):
            if row['site_no'] in sites:raise ValueError('Duplicate current site metadata')
            sites[row['site_no']]=row
        data=json.loads((CACHE/f"series_{item['batch']:02d}.dat").read_text())
        series.extend(data['features'])
    base=T.load_script('camelsh_metadata_rules',ROOT/'scripts/787_camelsh_metadata_screen.py');zones=T.load_script('camelsh_current_zones',ROOT/'scripts/490_review_completion_national_availability.py')
    prior=T.load_script('camelsh_current_prior',ROOT/'scripts/583_usgs_unresolved_network_count_screen.py').prior_stations()
    jobs=T.load_script('camelsh_current_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')
    for p in {j['input_path'] for j in jobs if j['provider']=='usgs'}:
        with open(p,encoding='utf-8-sig',newline='') as f:prior.update(next(csv.reader(f))[1:])
    previous=json.loads(DONOR.read_text());prior.update(x for b in previous['batches'] for x in b['sites'])
    prior_hucs=set()
    for item in json.loads(OLD.read_text())['features']:
        prop=item['properties'];site=str(prop.get('monitoring_location_id','')).removeprefix('USGS-')
        h=base.huc8(prop.get('hydrologic_unit_code'))
        if site in prior and h:prior_hucs.add(h)
    for h in pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype=str).huc_cd.dropna():
        if base.huc8(h):prior_hucs.add(base.huc8(h))
    scope=pd.read_csv(SCOPE,dtype=str).drop_duplicates('station_id').set_index('station_id')
    by={x:[] for x in ids}
    for item in series:
        p=item['properties'];site=str(p.get('monitoring_location_id','')).removeprefix('USGS-')
        if site not in by:raise ValueError('Unexpected site')
        if site not in sites:continue
        s=sites[site];h=base.huc8(s.get('huc_cd'));date_count=base.full_years(p.get('begin'),p.get('end'))
        daylight=s.get('local_time_fg','');zone=zones.native_zone({'time_zone_abbreviation':s.get('tz_cd'), 'uses_daylight_savings':daylight}) if daylight in ('Y','N') else None
        name=s.get('station_nm','');old=scope.loc[site] if site in scope.index else None
        known_huc=(h in prior_hucs) if h else None
        old_huc=bool(old is not None and str(old.get('same_HUC8_as_prior_record'))=='True')
        old_connection=bool(old is not None and str(old.get('component_has_prior_connection_screen'))=='True')
        eligible=bool(str(s.get('site_tp_cd','')).startswith('ST') and str(p.get('parameter_code'))=='00010' and str(p.get('statistic_id'))=='00003' and str(p.get('primary'))=='Primary' and h and zone and date_count is not None and date_count>=4 and not re.search(r'LAKE|RESERVOIR|CANAL|TAILRACE|DIVERSION|POWERPLANT|REGULATING',name,re.I) and not known_huc and not old_huc and not old_connection)
        by[site].append({'station_id':site,'series_id':str(p.get('id') or item['id']),'station_name':name,'huc8':h,'native_zone':zone,
            'site_type_code':s.get('site_tp_cd'),'begin':p.get('begin'),'end':p.get('end'),
            'possible_full_years_2000_2025':date_count,'same_prior_huc8':known_huc,'scope_prior_huc8':old_huc,
            'scope_known_connection':old_connection,'in_earlier_network_scope':old is not None,'metadata_candidate_series':eligible})
    entries=[]
    for site in ids:
        if site not in sites:entries.append({'station_id':site,'metadata_status':'site_not_returned_unknown','metadata_candidate':False});continue
        if not by[site]:entries.append({'station_id':site,'metadata_status':'no_daily_mean_series_returned','metadata_candidate':False});continue
        candidates=[r for r in by[site] if r['metadata_candidate_series']]
        if len(candidates)==1:entries.append({**candidates[0],'metadata_status':'candidate_one_series','metadata_candidate':True})
        else:entries.append({'station_id':site,'metadata_status':'multiple_candidate_series' if len(candidates)>1 else 'no_candidate_series_in_current_metadata',
                             'metadata_candidate':False,'series_records':len(by[site]),'candidate_series_records':len(candidates)})
    f=pd.DataFrame(entries).sort_values('station_id');dest=PRIVATE/'current_metadata_screen.csv';f.to_csv(dest,index=False);dest.chmod(0o600)
    result={'status':'metadata_screen_completed','requested_sites':len(ids),'sites_returned':len(sites),'daily_series_records_returned':len(series),
            'status_counts':f.metadata_status.value_counts().to_dict(),'metadata_candidates':int(f.metadata_candidate.sum()),
            'temperature_values_opened':False,'model_errors_opened':False,'limits':plan['limits']}
    (OUT/'current_metadata_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','screen']);a=p.parse_args();freeze() if a.action=='freeze' else screen()
