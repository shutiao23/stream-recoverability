#!/usr/bin/env python3
"""Freeze and count-screen unresolved-network USGS metadata candidates.

No target temperatures or prediction errors are retained. A count-complete
candidate is not an eligible reference: network identity, prior contact,
nonestimated daily values, sensor history and independent climates remain to
be checked. This is an unregistered exploratory availability selection.
"""
from __future__ import annotations
import argparse
import calendar
import importlib.util
import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_unresolved_network'
SCOPE=ROOT/'results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv'
CATALOG=ROOT/'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'
URL='https://api.waterdata.usgs.gov/statistics/v0/observationIntervals'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def write_frozen_counts(path,counts):
    """Preserve the first count receipt if the provider later revises data."""
    if path.exists():
        old=pd.read_csv(path,dtype={'station_id':str})
        old=old.sort_values(['station_id','year']).reset_index(drop=True)
        new=counts.sort_values(['station_id','year']).reset_index(drop=True)
        try:pd.testing.assert_frame_equal(old,new,check_dtype=False)
        except AssertionError as exc:raise RuntimeError(f'Frozen count receipt changed; keep existing {path}') from exc
    else:counts.to_csv(path,index=False)


def prior_stations():
    sources=[('results/additional_usgs_observed/cohort_metadata.csv','station_id'),
        ('results/wrr_target_recovery_20261022/e10_sealed_usgs/sealed_roster.csv','station_id'),
        ('results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv','site_no'),
        ('results/wrr_review_response_20261027/external_usgs/cohort.csv','station_id'),
        ('results/wrr_review_response_20261027/external_usgs_fresh/cohort.csv','station_id'),
        ('results/wrr_review_response_20261027/external_usgs_count_screen/candidate_roster.csv','station_id'),
        ('results/wrr_submission_ready/followup_20261021/usgs_prior_cache_audit/expanded_prior_station_inventory.csv','station_id')]
    ids={'02450250'}
    for name,column in sources:ids.update(pd.read_csv(ROOT/name,dtype=str)[column].dropna())
    for p in (ROOT/'results/wrr_review_completion_20261024/national_meaning/site_results').glob('*.json'):
        try:
            if json.loads(p.read_text()).get('status')=='processed':ids.add(p.stem)
        except (OSError,json.JSONDecodeError):continue
    return ids


def freeze():
    OUT.mkdir(parents=True,exist_ok=True)
    scope=pd.read_csv(SCOPE,dtype=str)
    f=scope.loc[scope.not_yet_excluded_metadata_candidate.eq('True')
        &scope.same_HUC8_as_prior_record.eq('False')
        &scope.network_status.eq('pending_identity_or_schema_review')].copy()
    f=f.loc[pd.to_datetime(f.begin,utc=True).dt.year.le(2016)&pd.to_datetime(f.end,utc=True).dt.year.ge(2020)]
    f=f.loc[~f.station_name.str.contains('LAKE|RESERVOIR|CANAL|TAILRACE|DIVERSION|POWERPLANT|REGULATING',case=False,na=False)]
    prior=prior_stations();raw=ROOT/'data/external/wrr_target_recovery_20261022/usgs_new/values_raw'
    f=f.loc[~f.station_id.isin(prior)&~f.series_id.map(lambda x:(raw/(x+'.json')).exists())].copy()
    meta={x['id']:x['properties'] for x in json.loads(CATALOG.read_text())['features']}
    timezones=module('external_native_zones',ROOT/'scripts/490_review_completion_national_availability.py')
    f['native_zone']=[timezones.native_zone(meta[x]) for x in f.series_id]
    f=f.loc[f.native_zone.notna()].sort_values(['HUC2_region_proxy','station_id','series_id']).drop_duplicates('station_id')
    path=OUT/'candidate_roster.csv';plan=OUT/'plan.json'
    if path.exists():
        old=pd.read_csv(path,dtype=str)
        if old.series_id.tolist()!=f.series_id.tolist():raise RuntimeError('Existing frozen roster differs; retain it')
    else:f.to_csv(path,index=False)
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'n_candidates':len(f),
        'selection':'all previously unused metadata candidates in the existing pending-identity-or-schema-review scope; no prior HUC8 match in the named inventory, no known raw contact, stream name filter, begin <=2016, end >=2020, known native timezone',
        'screen':'approved daily-mean sample counts for full calendar years 2010-2024; discard temperatures and do not compute prediction errors',
        'next_step':'count-complete sites are only candidates; resolve NLDI/river-network identity and all prior-contact inventories, then freeze a separate post-network roster before acquiring any daily temperature values',
        'reference':'at least four distinct complete calendar years of approved, nonestimated, QC-passing daily means, including three usable other years for local history',
        'limitation':'unregistered and selected on availability, pending network identity, nonrandom, metadata does not prove independence, daily approval does not ensure complete hourly measurements'}
    if not plan.exists():plan.write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2));print(f[['station_id','station_name','state_name','native_zone']].to_string(index=False))


def screen():
    if not (OUT/'candidate_roster.csv').is_file() or not (OUT/'plan.json').is_file():raise RuntimeError('Freeze metadata roster and plan first')
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    if roster.station_id.duplicated().any():raise ValueError('duplicate station')
    p=[('monitoring_location_id','USGS-'+x) for x in roster.station_id]+[
       ('parameter_code','00010'),('start_date','2010-01-01'),('end_date','2024-12-31'),
       ('interval_type','CY'),('computation_type','arithmetic_mean'),('page_size','100')]
    response=requests.get(URL,params=p,timeout=90,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status();doc=response.json()
    if any(x.get('rel')=='next' for x in doc.get('links',[])):raise RuntimeError('paginated response requires complete retrieval')
    extractor=module('prior_count_extractor',ROOT/'scripts/548_usgs_approved_count_preflight.py')
    counts=extractor.extract_counts(doc,roster)
    write_frozen_counts(OUT/'approved_counts.csv',counts)
    by_site=counts.groupby('station_id').count_complete.sum().rename('n_count_complete_years')
    result=roster.merge(by_site,on='station_id',how='left',validate='one_to_one')
    result['statistics_returned']=result.station_id.isin(counts.station_id)
    result['n_count_complete_years']=result.n_count_complete_years.astype('Int64')
    result['count_preflight_pass']=result.n_count_complete_years.ge(4).fillna(False)
    result.to_csv(OUT/'candidate_counts.csv',index=False)
    state={'status':'completed_count_screen','timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'metadata_candidates':len(roster),'statistics_features':len(doc['features']),
        'statistics_not_returned':int((~result.statistics_returned).sum()),
        'count_preflight_pass':int(result.count_preflight_pass.sum()),'temperature_values_saved':False,
        'selected_reference_cohort':0,'network_status':'unresolved for every candidate',
        'interpretation':'approved-day counts alone do not establish nonestimated observations, 24-hour completeness, sensor quality, river-network independence or climate independence'}
    (OUT/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(result[['station_id','station_name','n_count_complete_years','statistics_returned','count_preflight_pass']].to_string(index=False));print(json.dumps(state,indent=2))


def freeze_2025():
    """Record the post-hoc full-cohort extension before requesting 2025 counts."""
    if not (OUT/'status.json').is_file():raise RuntimeError('Complete the original count screen first')
    original=json.loads((OUT/'status.json').read_text())
    if original['status']!='completed_count_screen':raise RuntimeError('Original count screen did not complete')
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'n_original_candidates':len(roster),
          'population':'the entire previously fixed candidate roster; no temperature-based or per-site selection',
          'reason':'extend the 2010-2024 count screen to the now-completed calendar year 2025 after observing zero original passes',
          'query':'2025 approved daily-mean counts for the exact previously selected time series; retain no temperatures',
          'decision':'a candidate passes the extended count screen if it has at least four complete approved-count years over 2010-2025; 2025 missing or unmatched is unknown, not zero',
          'limitation':'post-hoc, unregistered, availability-selected; network identity and point-level nonestimated quality remain unresolved'}
    path=OUT/'extension_2025_plan.json'
    if not path.exists():path.write_text(json.dumps(plan,indent=2)+'\n')
    else:
        old=json.loads(path.read_text())
        if old['n_original_candidates']!=len(roster):raise RuntimeError('Frozen extension roster changed')
    print(json.dumps(plan,indent=2))


def extract_year(doc,roster,year):
    """Extract only approved count metadata for the frozen series and full year."""
    index=roster.set_index('station_id');rows=[];seen=set()
    for feature in doc['features']:
        prop=feature['properties'];site=prop['monitoring_location_id'].removeprefix('USGS-')
        if site not in index.index:raise ValueError('server returned unexpected site')
        for series in prop.get('data',[]):
            if str(series.get('parent_time_series_id'))!=str(index.loc[site,'series_id']) or str(series.get('parent_statistic_id'))!='00003':continue
            for val in series.get('values',[]):
                if val.get('interval_type')!='calendar_year' or val.get('approval_status')!='approved':continue
                start=pd.Timestamp(val['start_date']);end=pd.Timestamp(val['end_date'])
                if start.year!=year:continue
                if end.year!=year:raise ValueError('calendar statistic crossed years')
                if site in seen:raise ValueError(f'duplicate series/year statistic: {site}')
                seen.add(site);expected=366 if calendar.isleap(year) else 365
                full=start==pd.Timestamp(year,1,1) and end==pd.Timestamp(year,12,31)
                count=int(val['sample_count'])
                rows.append(dict(station_id=site,year=year,approved_daily_count=count,expected_days=expected,
                                 interval_full_year=bool(full),count_complete=bool(full and count==expected)))
    return pd.DataFrame(rows,columns=['station_id','year','approved_daily_count','expected_days','interval_full_year','count_complete'])


def combine_2025(base,counts):
    result=base.merge(counts[['station_id','approved_daily_count','count_complete']],on='station_id',how='left',validate='one_to_one')
    result=result.rename(columns={'approved_daily_count':'approved_daily_count_2025','count_complete':'count_complete_2025'})
    result['count_complete_2025']=result.count_complete_2025.astype('boolean')
    base_count=result.n_count_complete_years.astype('Int64')
    # A missing 2025 statistic is unknown: do not manufacture an extended pass/fail.
    result['extended_count_complete_years']=base_count+result.count_complete_2025.astype('Int64')
    result['extended_count_pass']=result.extended_count_complete_years.ge(4).astype('boolean')
    # Even an unreturned 2025 statistic can add at most one complete year.
    impossible=base_count.notna() & result.count_complete_2025.isna() & base_count.le(2)
    result.loc[impossible,'extended_count_pass']=False
    # Four existing complete years already satisfy the count screen.
    already_passes=base_count.notna() & base_count.ge(4)
    result.loc[already_passes,'extended_count_pass']=True
    return result


def write_2025_summary(roster,counts,feature_count):
    base=pd.read_csv(OUT/'candidate_counts.csv',dtype={'station_id':str})
    result=combine_2025(base,counts)
    result.to_csv(OUT/'candidate_counts_2010_2025.csv',index=False)
    state={'status':'completed_posthoc_2025_count_screen','timestamp_utc':datetime.now(timezone.utc).isoformat(),
           'metadata_candidates':len(roster),'statistics_features':feature_count,
           '2025_count_not_returned':int(result.count_complete_2025.isna().sum()),
           'extended_count_pass':int(result.extended_count_pass.fillna(False).sum()),
           'extended_count_unknown':int(result.extended_count_pass.isna().sum()),
           'selected_reference_cohort':0,'temperature_values_saved':False,
           'limitation':'post-hoc extension of unregistered availability screen; network identity, point-level quality and climate independence remain unresolved'}
    (OUT/'extension_2025_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(result[['station_id','n_count_complete_years','approved_daily_count_2025','count_complete_2025','extended_count_complete_years','extended_count_pass']].to_string(index=False));print(json.dumps(state,indent=2))


def screen_2025():
    if not (OUT/'extension_2025_plan.json').is_file():raise RuntimeError('Freeze the 2025 extension first')
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    params=[('monitoring_location_id','USGS-'+x) for x in roster.station_id]+[
        ('parameter_code','00010'),('start_date','2025-01-01'),('end_date','2025-12-31'),
        ('interval_type','CY'),('computation_type','arithmetic_mean'),('page_size','100')]
    response=requests.get(URL,params=params,timeout=90,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status();doc=response.json()
    if any(x.get('rel')=='next' for x in doc.get('links',[])):raise RuntimeError('paginated response requires complete retrieval')
    counts=extract_year(doc,roster,2025);write_frozen_counts(OUT/'approved_counts_2025.csv',counts)
    write_2025_summary(roster,counts,len(doc['features']))


def recalculate_2025():
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    counts=pd.read_csv(OUT/'approved_counts_2025.csv',dtype={'station_id':str})
    state=json.loads((OUT/'extension_2025_status.json').read_text())
    write_2025_summary(roster,counts,state['statistics_features'])


def metadata_2025():
    """Inspect current series metadata for count-undetermined candidates only.

    This is retrospective: the first item's public metadata was already opened
    before this probe was formalized. End timestamps may lag recent records.
    """
    f=pd.read_csv(OUT/'candidate_counts_2010_2025.csv',dtype={'station_id':str,'series_id':str})
    unknown=f.loc[f.extended_count_pass.isna()]
    rows=[];root='https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items/'
    for row in unknown.itertuples(index=False):
        url=root+row.series_id
        response=requests.get(url,params={'f':'json'},timeout=30,headers={'User-Agent':'stream-temperature reference research'})
        response.raise_for_status();prop=response.json()['properties']
        if (str(prop.get('id'))!=row.series_id or prop.get('monitoring_location_id')!='USGS-'+row.station_id
            or str(prop.get('parameter_code'))!='00010' or str(prop.get('statistic_id'))!='00003'):
            raise ValueError('time series metadata identity mismatch')
        end=prop.get('end');parsed=pd.Timestamp(end) if end else pd.NaT
        rows.append(dict(station_id=row.station_id,series_id=row.series_id,metadata_url=url,
            retrieved_utc=datetime.now(timezone.utc).isoformat(),begin=prop.get('begin'),end=end,
            end_utc=prop.get('end_utc'),last_modified=prop.get('last_modified'),
            latest_metadata_end_before_2025=bool(pd.notna(parsed) and parsed.date()<pd.Timestamp('2025-01-01').date()),
            prior_count_complete_years=int(row.n_count_complete_years)))
    result=pd.DataFrame(rows);result.to_csv(OUT/'unresolved_2025_series_metadata.csv',index=False)
    status={'status':'metadata_checked','n_count_undetermined':len(unknown),
            'metadata_end_before_2025':int(result.latest_metadata_end_before_2025.sum()) if len(result) else 0,
            'first_item_opened_before_probe_formalized':True,'temperature_values_saved':False,
            'limitation':'USGS time-series metadata can lag observations; count status remains unknown when no annual statistic was returned, and other series at the station were not screened'}
    (OUT/'unresolved_2025_metadata_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(result.to_string(index=False));print(json.dumps(status,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['freeze','screen','freeze2025','screen2025','recalculate2025','metadata2025']);args=p.parse_args()
    {'freeze':freeze,'screen':screen,'freeze2025':freeze_2025,'screen2025':screen_2025,'recalculate2025':recalculate_2025,'metadata2025':metadata_2025}[args.phase]()

if __name__=='__main__':main()
