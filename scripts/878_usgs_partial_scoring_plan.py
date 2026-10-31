#!/usr/bin/env python3
"""Freeze all USGS daily target model comparisons before predictions."""
import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path('/home/lzq/workspace/parttime/stream-recoverability');OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_partial_daily';USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024';STAGE=Path('/dev/shm/wrr_usgs_partial_daily_20261027')
def main():
 dest=STAGE/'scoring_plan.json'
 if dest.exists():raise FileExistsError('Preserve scoring plan')
 audit=json.loads((STAGE/'independent_audit_status.json').read_text());qualification=json.loads((STAGE/'continuous_qualification_status.json').read_text());network=json.loads((OUT/'network_status.json').read_text())
 if audit['status']!='passed' or qualification['status']!='completed_continuous_qualification' or network['status']!='completed':raise ValueError('Qualification audit incomplete')
 roster=PRIVATE/'continuous_target_roster.csv';r=pd.read_csv(roster,dtype={'station_id':str})
 if len(r)!=8 or r.station_id.nunique()!=4 or not r.eligible_partial_history.all():raise ValueError('Fixed target cohort changed')
 files=[roster,OUT/'feasibility_status.json',OUT/'network_status.json',STAGE/'continuous_qualification_status.json',STAGE/'continuous_qualification_years.csv',STAGE/'continuous_qualification_days.parquet',STAGE/'independent_audit_status.json',
   SOURCE/'deployment/global_source_candidate.joblib',SOURCE/'independent_study/source_case_settings.json',SOURCE/'independent_study/source_missingness_generator.json',ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json',
   ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/835_usace_partial_history_engine.py',ROOT/'scripts/871_usgs_partial_daily_feasibility.py',ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/wrr_tr_features.py',
   STAGE/'879_usgs_partial_power.py',STAGE/'880_usgs_partial_predict.py',STAGE/'881_usgs_partial_score.py',STAGE/'882_usgs_partial_hidden_probe.py',Path(__file__)]
 files += [DATA/'daily'/(s+'.parquet') for s in sorted(r.station_id.unique())]
 p={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after daily values, earlier witness years, full subdaily qualification and bounded network checks; before new target model predictions or error scores',
   'cohort':'All eight previously fixed approved, no-detected-estimate daily-complete years at four sites with at least three other eligible partial histories. Do not select on target H30, subdaily completeness, source-network results or model predictions.',
   'source':'Use the fixed global source annual model and its original source-only calibration; no target model refitting, no target-station water donors. One station appears exactly in a source panel and others have prior contacts; all target daily archives were previously opened, so this is not a blind independent climate test.',
   'history':'Exclude the entire target calendar year from local training. Other eligible history years have >=75% usable approved/no-detected-estimate days, observed endpoints and longest missing run <=45 days; linearly interpolate missing history days within their own year. Keep the actual count of completely observed history years, 0-2, not the number of interpolated years. These counts lie below the global estimator training minimum of 3 and outside the original four-complete-year protocol.',
   'target':'Published USGS approved daily mean, fully finite throughout the calendar year, with no estimated qualifier recognized by the existing parser. Use 30/60/90-day crossed masks from the fixed source generator. No target mask value enters local fitting or decision-time inputs; never fill absent target values as truth.',
   'metrics':'Report all target years and available/common masks, point MAE, bias, >0.5 C failures, 90% coverage, width and interval score for plug-in, D2 and calibrated stochastic. Separately report after-the-fact subsets with full fixed-standard hourly support and full quarter-hour support. Three hourly years and the only quarter-hour year all come from one station; do not treat masks or years as independent climates.',
   'clock':'For one year with complete 15-minute source data, compare H30 under fixed standard time and native civil time against the published daily-value H30; do not choose clock by agreement. NASA POWER daily LST may differ from both USGS conventions.',
   'limitations':'Prior source/witness exposure, USGS continuous quality, unknown pointwise corrections, input-domain extrapolation, incomplete history imputation, sensor accuracy, actual day convention and independence remain unresolved. The selected station-year labels were observed before this plan. One target station appears in a source panel. No trend or risk-calibration guarantee.',
   'target_years':len(r),'sites':int(r.station_id.nunique()),'expected_masks_per_year':18,}
 dest.write_text(json.dumps(p,indent=2)+'\n');print(json.dumps({'status':p['status'],'target_years':len(r),'sites':r.station_id.nunique()},indent=2))
if __name__=='__main__':main()
