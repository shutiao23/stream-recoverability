#!/usr/bin/env python3
"""Record a reported-day field-range diagnostic before opening field values."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'

def main():
    dest=OUT/'comparison_plan.json'
    if dest.exists():raise FileExistsError('Preserve existing field comparison plan')
    acquisition=json.loads((OUT/'acquisition.json').read_text());metadata=json.loads((OUT/'metadata_status.json').read_text())
    if not str(acquisition['status']).startswith('downloaded') or metadata['status']!='metadata_screen_complete' or metadata['result_values_read']:
        raise ValueError('Field source or metadata screen incomplete')
    portal=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified/portal_acquisition.json'
    field=ROOT/'private/wrr_nova_scotia_field_checks_20261027/nova_scotia_field_v6.csv'
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc reported-day diagnostic plan; field temperatures not yet inspected',
          'prior_exposure':'Portal measurements, selected site years, release comparisons and model errors were already observed. Field metadata were examined and showed absent time labels and two indistinguishable rows per site-date.',
          'site_ids':['NS01DL0009','NS01FB0001'],'years':list(range(2009,2018)),
          'field_selection':'All field records for these exact station IDs and years with characteristic Temperature, water and unit deg C; retain Preliminary status and all numeric values without error-based selection.',
          'duplicate_policy':'Keep both source rows; count site-date groups separately. Identical metadata and equal numeric values do not establish duplicate or independent sampling events.',
          'reported_day_test':'For each field row, compare against min and max of exactly 24 distinct finite portal hours bearing the same reported date. Require every integer hour 00 through 23; no interpolation or inferred timezone.',
          'adjacent_day_sensitivity':'Also compare against pooled minimum and maximum of three consecutive complete reported days, to describe sensitivity to date alignment. This wide range is not a single physical-day interval.',
          'statistics':'Field row counts, distinct site-dates, missing or nonnumeric records, ambiguous site-date multiplicity, same-day and three-day availability; range excess in degrees Celsius, and counts exceeding 0 and 0.5 C. No uncertainty interval or accuracy threshold is claimed.',
          'limitations':'All field records have no sample time or time zone and are preliminary. Same-program instruments may not be independent, and a non-hourly sample can fall outside hourly extrema. Uncertain day boundary, differing sites within a river reach, or data processing may also explain disagreement. This is not sensor calibration, strict reference qualification, independent-climate validation, or validation of H30 recovery.',
          'privacy':'Original field file and row-level comparisons stay local; aggregated descriptive results only.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded exploratory date-range plan; no field temperatures inspected.')

if __name__=='__main__':main()
