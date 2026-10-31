#!/usr/bin/env python3
"""Check HJ Andrews Lookout Creek identity against saved source metadata.

This is a metadata and already-opened source-case audit. It downloads no HJA
measurements and cannot establish sensor equivalence, quality or completeness.
"""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
META=ROOT/'results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv'
OUT=ROOT/'results/wrr_review_response_20261027/external_andrews_metadata'
SITE='14161500'


def summarize(cases,metadata):
    target=cases.loc[cases.station_key.eq('usgs|'+SITE)]
    if target.empty:raise ValueError('documented Lookout Creek source station absent')
    groups=target.independence_group.dropna().unique()
    if len(groups)!=1:raise ValueError('source station group ambiguous')
    group=groups[0]; members=cases.loc[cases.independence_group.eq(group)]
    if members.station_key.isna().any() or not members.station_key.str.startswith('usgs|').all():raise ValueError('unexpected non-USGS group member')
    summary=members.groupby('station_key',as_index=False).agg(region=('region','first'),independence_group=('independence_group','first'),
       first_case_year=('year','min'),last_case_year=('year','max'),unique_case_years=('year','nunique'),masked_case_rows=('year','size'))
    summary['site_no']=summary.station_key.str.removeprefix('usgs|')
    if metadata.site_no.duplicated().any():raise ValueError('source station metadata identifiers are not unique')
    summary=summary.merge(metadata[['site_no','station_nm','dec_lat_va','dec_long_va','huc_cd']],on='site_no',how='left',validate='one_to_one')
    if summary.station_nm.isna().any():raise ValueError('source group metadata missing')
    target_summary=summary.loc[summary.site_no.eq(SITE)].iloc[0]
    return summary,target_summary


def main():
    cols=['station_key','region','independence_group','year','policy_choice','eval_truth_h30']
    cases=pd.read_parquet(SOURCE,columns=cols);cases=cases.loc[cases.policy_choice.ne('unavailable')&cases.eval_truth_h30.notna()].copy()
    meta=pd.read_csv(META,dtype={'site_no':str,'huc_cd':str})
    roster,target=summarize(cases,meta)
    OUT.mkdir(parents=True,exist_ok=True);roster.to_csv(OUT/'source_group_roster.csv',index=False)
    status={'status':'source_overlap_confirmed','source_station_alias':'usgs|'+SITE,'source_independence_group':target.independence_group,
      'source_region':target.region,'source_station_case_years':int(target.unique_case_years),'source_station_first_case_year':int(target.first_case_year),
      'source_station_last_case_year':int(target.last_case_year),'source_station_masked_case_rows':int(target.masked_case_rows),
      'connected_source_stations':len(roster),'source_huc8':str(target.huc_cd),
      'hja_identity_source':'https://andrewsforest.oregonstate.edu/data/studies/hf04/hja_gage_ws_descriptions_instrumentation.pdf',
      'hja_data_catalog':'https://andrewsforest.oregonstate.edu/data/datacatalog/HT004',
      'decision':'do not treat the documented Lookout Creek station or its same-flow-system record as new independent basin confirmation; other HJA probes require explicit network identity and prior-access assessment',
      'hja_measurement_rows_downloaded_or_scored':False,
      'access_note':'provider download page requests one-time user registration; EDI public-access endpoint returned HTTP 403 in this environment',
      'limitation':'same USGS station and recorded source group prove prior exposure; they do not establish equivalence of particular HJA temperature probes, timestamps, years, or complete 24-hour quality'}
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n');print(roster.to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
