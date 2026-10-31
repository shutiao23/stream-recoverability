#!/usr/bin/env python3
"""Record a post-hoc hourly-value proximity diagnostic, without timing claims."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'
ROSTER=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/reference_year_roster.csv'

def main():
    dest=OUT/'hour_membership_plan.json'
    if dest.exists():raise FileExistsError('Preserve existing proximity diagnostic plan')
    status=json.loads((OUT/'status.json').read_text())
    if status['status']!='computed_exploratory':raise ValueError('Reported-day range check is incomplete')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc after same-day range and duplicate-value results were viewed',
          'scope':'The same two previously selected Nova Scotia stations, all reported field dates 2009-2017; retain duplicate rows and distinguish site-date counts.',
          'comparison':'For each finite field value, calculate its minimum absolute difference from any of the 24 reported hourly values on that date; separately use 72 hours from three complete adjacent reported dates. Require each day to have exactly 24 unique finite hour labels.',
          'thresholds_c':[1e-6,.01],
          'stratification':'After seeing the range summary, separately describe the eight station-years used in the earlier exploratory model score and the remaining years; no error-driven site or record exclusion.',
          'selection_warning':'Field times and zones are absent. A close value anywhere in a day or three days may occur by chance. Exact numerical proximity does not establish simultaneous measurement, separate instruments, quality, physical truth, climate independence or model validation.',
          'privacy':'Field rows, hourly pair information and source workbook remain private; aggregated counts only.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n')
    print('Recorded post-hoc proximity and selected-year diagnostic; hourly proximity has not yet been computed.')

if __name__=='__main__':main()
