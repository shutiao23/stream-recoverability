#!/usr/bin/env python3
"""Freeze metadata-only candidates for an unregistered USGS count preflight.

The endpoint pilot site (02450250) was already in E10 and previously
scored; it is excluded for prior contact as well as the recent API test. Temperature values and reconstruction errors do not determine
this roster. A later preflight uses only approved annual sample counts; this is
still an outcome-dependent availability design, not a random cohort.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_count_screen'
SCOPE=ROOT/'results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv'
CATALOG=ROOT/'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    scope=pd.read_csv(SCOPE,dtype=str)
    f=scope.loc[scope.not_yet_excluded_metadata_candidate.eq('True') & scope.network_status.eq('complete')
        & scope.all_component_candidate_checks_complete.eq('True') & scope.same_HUC8_as_prior_record.eq('False')].copy()
    f=f.loc[pd.to_datetime(f.begin,utc=True).dt.year.le(2016) & pd.to_datetime(f.end,utc=True).dt.year.ge(2020)]
    f=f.loc[~f.station_name.str.contains('LAKE|RESERVOIR|CANAL|TAILRACE|DIVERSION|POWERPLANT|REGULATING',case=False,na=False)]
    prior=set(pd.read_csv(ROOT/'results/additional_usgs_observed/cohort_metadata.csv',dtype=str).station_id)
    prior |= set(pd.read_csv(ROOT/'results/wrr_target_recovery_20261022/e10_sealed_usgs/sealed_roster.csv',dtype=str).station_id)
    prior |= set(pd.read_csv(ROOT/'results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv',dtype=str).site_no)
    prior |= set(pd.read_csv(ROOT/'results/wrr_review_response_20261027/external_usgs/cohort.csv',dtype=str).station_id)
    prior |= set(pd.read_csv(ROOT/'results/wrr_review_response_20261027/external_usgs_fresh/cohort.csv',dtype=str).station_id)
    prior |= set(pd.read_csv(ROOT/'results/wrr_submission_ready/followup_20261021/usgs_prior_cache_audit/expanded_prior_station_inventory.csv',dtype=str).station_id)
    prior.add('02450250')
    for p in (ROOT/'results/wrr_review_completion_20261024/national_meaning/site_results').glob('*.json'):
        try:
            if json.loads(p.read_text()).get('status')=='processed': prior.add(p.stem)
        except (OSError,json.JSONDecodeError): continue
    raw=ROOT/'data/external/wrr_target_recovery_20261022/usgs_new/values_raw'
    f=f.loc[~f.station_id.isin(prior) & ~f.series_id.map(lambda x:(raw/(x+'.json')).exists())]
    f=f.sort_values(['HUC2_region_proxy','provisional_network_index_component','station_id','series_id']).drop_duplicates('station_id')
    # Preserve all metadata-eligible candidates, including repeated index components;
    # separation is enforced on the later selected roster, not hidden here.
    catalog={x['id']:x['properties'] for x in json.loads(CATALOG.read_text())['features']}
    spec=importlib.util.spec_from_file_location('national_timezones',ROOT/'scripts/490_review_completion_national_availability.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    f['native_zone']=[module.native_zone(catalog[x]) for x in f.series_id]
    f=f.loc[f.native_zone.notna()].copy()
    path=OUT/'candidate_roster.csv'
    if path.exists():
        old=pd.read_csv(path,dtype=str)
        if old.series_id.tolist()!=f.series_id.tolist(): raise RuntimeError('Frozen metadata candidate roster changed')
    else: f.to_csv(path,index=False)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'n_metadata_candidates':len(f),
          'selection':'previously unused metadata candidates with completed NLDI indexed-component screen, no prior HUC8 contact, begin by 2016 and end in/after 2020; nonriver names, no timezone, known source/E10/national/fresh/cache contacts, and the 02450250 endpoint pilot are excluded',
          'preflight':'USGS annual approved counts for the matching daily mean series, complete 2010-2024 calendar years, no annual temperatures or prediction errors saved or used; estimated qualifiers and point-level quality cannot be determined from counts',
          'future_roster':'select up to two sites per HUC2 with >=4 count-complete years, choose distinct indexed components and sort by descending complete-year count then station ID, before requesting daily observations; all candidates and excluded sites remain documented',
          'strict_reference':'after roster fixed, require every calendar day of at least four years to pass approved, nonestimated and point-level quality checks, using agency daily mean',
          'caveat':'unregistered exploratory study, completeness-based selection and current-vintage metadata; agency-approved daily means do not establish that every underlying hourly value passed independent QC, and river-network/climatic independence is not guaranteed'}
    if not (OUT/'plan.json').exists(): (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print('fixed candidates',len(f));print(f.groupby('HUC2_region_proxy').size().to_string())

if __name__=='__main__':main()
