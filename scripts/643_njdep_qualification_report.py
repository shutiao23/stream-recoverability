#!/usr/bin/env python3
"""Combine independently recounted NJDEP timestamp qualification screens."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026'

def main():
 meta=json.loads((OUT/'metadata_status.json').read_text());alltypes=json.loads((OUT/'all_water_types_status.json').read_text())
 counts=json.loads((OUT/'all_candidate_counts_status.json').read_text());first=json.loads((OUT/'timestamp_screen_status.json').read_text())
 audit=json.loads((OUT/'independent_timestamp_audit.json').read_text());second=json.loads((OUT/'subdaily_extension_clock_status.json').read_text())
 if first['status']!='reported_timestamp_label_screen_only' or audit['status']!='independent_timestamp_recount_passed' or second['status']!='posthoc_extension_clock_independently_recounted':raise ValueError('both independent timestamp screens are required')
 a=pd.read_csv(PRIVATE/'timestamp_year_summary.csv',dtype={'site':str});b=pd.read_csv(PRIVATE/'timestamp_extension_year_summary.csv',dtype={'site':str});cases=pd.concat([a,b],ignore_index=True)
 if cases.duplicated(['site','year']).any() or len(cases)!=first['station_year_files']+second['station_year_files']:raise ValueError('duplicate or missing screened station years')
 nmissing=int(cases.status.eq('reported_date_labels_incomplete').sum());unknown=int(cases.status.eq('unparseable_time_unknown').sum())
 if nmissing!=first['station_years_with_missing_reported_date_labels']+second['station_years_missing_reported_dates']:raise ValueError('missing-label counts differ')
 if not audit['station_year_files_checked']==first['station_year_files'] or not second['independent_arrow_recount_passed']:raise ValueError('independent recount incomplete')
 api_matches=0
 for row in cases.itertuples(index=False):
  receipt=PRIVATE/'candidate_count_receipts'/(row.site+'.json')
  record=json.loads(receipt.read_text());years=[z for z in record['counts'] if z['year']==row.year]
  if len(years)!=1 or years[0]['status']!='returned':raise ValueError('missing candidate count endpoint response')
  total=int(row.reported_year_rows+row.outside_requested_calendar_year_rows+row.unparseable_timestamp_rows)
  if total!=years[0]['count']:raise ValueError('provider CSV row count differs from count endpoint')
  api_matches+=1
 result={'status':'posthoc_qualification_screen_completed','metadata_station_options':meta['station_options'],'freshwater_labeled_options':meta['freshwater_options'],
  'freshwater_options_without_qa_dates':meta['freshwater_with_missing_dates'],'all_water_types_four_year_qa_span_options':alltypes['options_with_four_year_qa_span'],
  'all_types_four_nonzero_count_year_options':counts['candidates_four_or_more_nonzero_count_years'],
  'screened_stations':int(cases.site.nunique()),'screened_station_years':len(cases),'station_years_missing_reported_dates':nmissing,
  'station_years_with_unparseable_times':unknown,'minimum_missing_reported_dates':int(cases.days_with_no_reported_time.min()),
  'maximum_missing_reported_dates':int(cases.days_with_no_reported_time.max()),
  'independent_timestamp_recounts_passed':True,'station_year_csv_count_endpoint_matches':api_matches,'temperature_values_or_model_errors_examined':False,
  'quality_and_reference':'date-label screening only; no complete reference year or prediction accuracy established',
  'limitations':'four stations selected post-hoc after metadata and count inspection; not a representative sample; 86 freshwater-labelled entries without QA spans, unscreened stations and other years remain unresolved; reported clock and provider quality/sensor procedures require further validation'}
 (OUT/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
