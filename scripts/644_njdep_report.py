#!/usr/bin/env python3
"""Render the NJDEP qualification boundary from verified aggregate statuses."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PAPER=ROOT/'paper/wrr_tr'


def main():
 r=json.loads((OUT/'report.json').read_text());a=json.loads((OUT/'independent_timestamp_audit.json').read_text());b=json.loads((OUT/'subdaily_extension_clock_status.json').read_text())
 if r['status']!='posthoc_qualification_screen_completed' or a['status']!='independent_timestamp_recount_passed' or not b['independent_arrow_recount_passed']:raise ValueError('NJDEP qualification audit incomplete')
 text=(r'\par\medskip\noindent\textbf{New Jersey continuous-monitoring intake.} The NJDEP portal provides downloadable quality-reviewed records (\url{https://njdep.rutgers.edu/continuous/download/}). '
  f"The station selector contained {r['metadata_station_options']} entries, of which {r['freshwater_labeled_options']} were labeled freshwater; "
  f"{r['freshwater_options_without_qa_dates']} freshwater entries lacked quality-period boundaries and remain unresolved. "
  f"After discovering inconsistent water-type labels, a post-hoc check found {r['all_water_types_four_year_qa_span_options']} entries whose quality-period envelopes spanned at least four possible calendar years; "
  f"all were labeled marine, and {r['all_types_four_nonzero_count_year_options']} had nonzero record counts in at least four queried years. Counts can include different variables and do not prove complete water-temperature observations. "
  f"We selected {r['screened_stations']} river/stream candidates after inspecting metadata and counts, then acquired their 2016--2019 temperature files. "
  f"All {r['screened_station_years']} returned station-years lacked some reported date labels, with {r['minimum_missing_reported_dates']}--{r['maximum_missing_reported_dates']} missing dates per station-year. "
  f"The downloaded CSV row counts agree with the provider count endpoint for all {r['station_year_csv_count_endpoint_matches']} station-years. An independent Arrow/Python implementation reproduced the timestamp counts without examining temperature values or model errors. "
  'The files use an EST label, but the real time basis, expected sampling cadence, nonestimated status, individual quality flags and catchment independence remain unresolved. '
  'These selected cases do not qualify as complete reference years under their reported-clock convention; this post-hoc screen does not establish the number of qualifying stations in the full portal.\n')
 (PAPER/'njdep_reference_supporting.tex').write_text(text);print(json.dumps({'status':'rendered','screened_stations':r['screened_stations'],'screened_station_years':r['screened_station_years']},indent=2))
if __name__=='__main__':main()
