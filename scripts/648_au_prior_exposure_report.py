#!/usr/bin/env python3
"""Render the checked historical Australian reference-overlap boundary."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/audit';PAPER=ROOT/'paper/wrr_tr'


def main():
 a=json.loads((OUT/'australia_prior_exposure_status.json').read_text());b=json.loads((OUT/'australia_prior_exposure_independent.json').read_text())
 if a['status']!='historical_target_overlap_confirmed' or b['status']!='independent_prior_exposure_recount_passed':raise ValueError('prior exposure audits incomplete')
 if a['original_formal_F2_primary_test_gate'] or a['new_F2_predictions_or_errors_computed_by_this_audit']:raise ValueError('F2 gate or analysis scope changed')
 values={'AURefYears':str(a['original_reference_station_years']),'AURefStations':str(a['original_reference_stations']),
   'AUFirstCases':f"{a['round1_existing_evaluated_cases']:,}",'AUFirstMatch':str(a['round1_prior_case_overlap_station_years']),
   'AUFirstEvaluable':str(a['round1_prior_evaluation_eligible_station_years']),'AUFormerTest':str(a['round1_original_test_role_station_years']),
   'AUFormerTestEvaluable':str(a['round1_original_test_role_evaluated']),'AUHotOverlap':str(a['round2_hot_window_overlap_station_years']),
   'AUHotEvaluable':str(a['round2_evaluable_hot_window_overlap_station_years'])}
 (PAPER/'au_prior_exposure_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
 text=r'''\section{Prior Australian reference exposure}
An earlier Australian recruitment stage identified \AURefYears{} observation-supported candidate station-years from \AURefStations{} stations. The historical intake record states that its designated F2 formal test was closed; this audit does not run that model or calculate new F2 errors. Subsequently, a separate, earlier-method Australian evaluation used calendar-year cases from the same acquired source archive. All \AUFirstMatch{} of the candidate station-years appear in that case file; \AUFirstEvaluable{} had at least one case in the old evaluation's eligible case set, including all \AUFormerTestEvaluable{} of the \AUFormerTest{} originally designated F2 test-role station-years. The prior evaluation contained \AUFirstCases{} eligible masked cases across its wider roster. These are previously evaluated records for a different pipeline, not unopened target station-years for a new independent test.

A later Australian development analysis used July--June rather than calendar-year windows. Counting physical time overlap rather than matching the year labels alone, \AUHotOverlap{} of the original \AURefYears{} calendar station-years intersect a saved development window, of which \AUHotEvaluable{} intersect at least one eligible development case. A separate Arrow/Python recount reproduced these counts. Matching station and interval does not prove that masked days are identical, that the F2 model was evaluated, or that data leaked into source-model training. The original native-sampling criterion allowed 20 observed hours per day and does not establish a complete 24-hour physical reference. These previously opened Australian records cannot supply a fresh independent confirmation of the current pipeline.
'''
 (PAPER/'au_prior_exposure_supporting.tex').write_text(text);print(json.dumps(values,indent=2))
if __name__=='__main__':main()
