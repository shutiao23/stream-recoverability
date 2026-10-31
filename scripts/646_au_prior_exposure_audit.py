#!/usr/bin/env python3
"""Audit prior Australian reference exposure using identities and time windows.

No models are run and no new prediction errors are computed. The earlier F2
score gate remains unchanged. Read previously stored cases only to inspect their
station/time keys and the availability flags used by the old evaluation.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'audit';FOLLOW=ROOT/'results/wrr_submission_ready/followup_20261021/au_confirmation'
R1=ROOT/'results/wrr_target_recovery_20261021/e7_sealed';R2=ROOT/'results/wrr_target_recovery_20261022/e7_au_development'


def prior_cases(path):
    columns=['station_id','year','hot_year_start','hemisphere_shift_days','policy_choice','state_h30_q50','eval_truth_h30']
    x=pd.read_parquet(path,columns=columns);x['station_id']=x.station_id.astype(str)
    # Only finite/nonmissing status is used. No observed temperatures, model
    # predictions or differences are exported or newly computed.
    x['old_evaluation_case_eligible']=x.policy_choice.ne('unavailable')&x.state_h30_q50.notna()&x.eval_truth_h30.notna()
    return x


def audit_reference(reference,old_calendar,old_hot):
    q=reference.loc[reference.observed_sampling_reference_eligible.eq(True),['station_id','year','role']].drop_duplicates().copy()
    if q.duplicated(['station_id','year']).any():raise ValueError('reference station/year has multiple old roles')
    q.station_id=q.station_id.astype(str);q.year=q.year.astype(int)
    v1=old_calendar.groupby(['station_id','year'],as_index=False).agg(calendar_cases=('old_evaluation_case_eligible','size'),calendar_eligible=('old_evaluation_case_eligible','sum'))
    z=q.merge(v1,on=['station_id','year'],how='left',validate='one_to_one')
    z[['calendar_cases','calendar_eligible']]=z[['calendar_cases','calendar_eligible']].fillna(0).astype(int)
    hot=old_hot[['station_id','hot_year_start','hemisphere_shift_days','old_evaluation_case_eligible']].copy()
    if hot.hemisphere_shift_days.ne(184).any():raise ValueError('unexpected round-2 hot-year definition')
    hot['start']=pd.to_datetime(hot.hot_year_start,format='%Y-%m-%d',errors='raise');hot['end']=hot.start+pd.DateOffset(years=1)
    hot=hot.groupby(['station_id','start','end'],as_index=False).agg(hot_cases=('old_evaluation_case_eligible','size'),hot_eligible=('old_evaluation_case_eligible','sum'))
    pairs=q.merge(hot,on='station_id',how='left',validate='many_to_many')
    pairs['reference_start']=pd.to_datetime(pairs.year.astype(str)+'-01-01');pairs['reference_end']=pairs.reference_start+pd.DateOffset(years=1)
    overlap=pairs.start.lt(pairs.reference_end)&pairs.end.gt(pairs.reference_start)
    pairs=pairs.loc[overlap].copy()
    v2=pairs.groupby(['station_id','year'],as_index=False).agg(hot_overlapping_windows=('hot_cases','size'),hot_overlap_cases=('hot_cases','sum'),hot_overlap_eligible=('hot_eligible','sum'))
    z=z.merge(v2,on=['station_id','year'],how='left',validate='one_to_one')
    for col in ['hot_overlapping_windows','hot_overlap_cases','hot_overlap_eligible']:z[col]=z[col].fillna(0).astype(int)
    return z


def main():
    reference=pd.read_csv(FOLLOW/'observed_reference_release.csv',dtype={'station_id':str})
    before=json.loads((FOLLOW/'observed_reference_summary.json').read_text());prior=json.loads((R1/'sealed_results.json').read_text());dev=json.loads((R2/'development_check.json').read_text())
    calendar=prior_cases(R1/'cases.parquet');hot=prior_cases(R2/'cases.parquet')
    if calendar.hemisphere_shift_days.ne(0).any():raise ValueError('round-1 period is not calendar-year')
    if int(calendar.old_evaluation_case_eligible.sum())!=prior['n_cases']:raise ValueError('old evaluated case denominator differs from existing result')
    if int(hot.old_evaluation_case_eligible.sum())!=dev['n_cases']:raise ValueError('old development case denominator differs from existing result')
    audit=audit_reference(reference,calendar,hot)
    if len(audit)!=before['qualified_observed_sampling_station_years']:raise ValueError('qualified reference cohort differs')
    if before['primary_test_error_access_allowed'] or before['new_H30_prediction_errors_opened']:raise ValueError('historical F2 intake status differs')
    grouped=audit.groupby('role').agg(reference_station_years=('year','size'),stations=('station_id','nunique'),
      round1_calendar_case_station_years=('calendar_cases',lambda s:int(s.gt(0).sum())),
      round1_evaluated_station_years=('calendar_eligible',lambda s:int(s.gt(0).sum())),
      round2_hot_window_station_years=('hot_overlapping_windows',lambda s:int(s.gt(0).sum())),
      round2_evaluable_hot_window_station_years=('hot_overlap_eligible',lambda s:int(s.gt(0).sum()))).reset_index()
    grouped.to_csv(OUT/'australia_prior_exposure_by_role.csv',index=False)
    status={'status':'historical_target_overlap_confirmed','original_reference_station_years':len(audit),'original_reference_stations':int(audit.station_id.nunique()),
      'round1_prior_case_overlap_station_years':int(audit.calendar_cases.gt(0).sum()),
      'round1_prior_evaluation_eligible_station_years':int(audit.calendar_eligible.gt(0).sum()),
      'round1_original_test_role_station_years':int(audit.loc[audit.role.eq('test'),'year'].size),
      'round1_original_test_role_evaluated':int(audit.loc[audit.role.eq('test'),'calendar_eligible'].gt(0).sum()),
      'round2_hot_window_overlap_station_years':int(audit.hot_overlapping_windows.gt(0).sum()),
      'round2_evaluable_hot_window_overlap_station_years':int(audit.hot_overlap_eligible.gt(0).sum()),
      'round1_evaluation_utc':prior['evaluated_utc'],'round1_existing_evaluated_cases':prior['n_cases'],
      'round2_existing_development_cases':dev['n_cases'],
      'round1_period_definition':'calendar year, no southern hemisphere shift',
      'round2_period_definition':'July 1 through next July 1 exclusive; any overlap with original calendar year is counted',
      'original_formal_F2_primary_test_gate':before['primary_test_error_access_allowed'],
      'original_formal_F2_recorded_new_errors_opened':before['new_H30_prediction_errors_opened'],
      'new_F2_predictions_or_errors_computed_by_this_audit':False,
      'interpretation':f"Of {len(audit)} candidate station-years, {int(audit.calendar_cases.gt(0).sum())} occur in the later first Australian case file and {int(audit.calendar_eligible.gt(0).sum())} in its earlier evaluated case set; {int(audit.loc[audit.role.eq('test'),'calendar_eligible'].gt(0).sum())} former F2 test-role years entered that separate evaluation. The historical F2 intake recorded its test as unopened, and this audit did not run F2; the overlapping records are nevertheless not unopened independent records for a new test.",
      'limitation':'matches station IDs and calendar/season windows only; overlap is prior use, not proof of model-training leakage or identical masked cases. Reference sampling allowed 20 observed hours and is not a strict 24-hour measurement guarantee.'}
    (OUT/'australia_prior_exposure_status.json').write_text(json.dumps(status,indent=2)+'\n');print(grouped.to_string(index=False));print(json.dumps(status,indent=2))
if __name__=='__main__':main()
