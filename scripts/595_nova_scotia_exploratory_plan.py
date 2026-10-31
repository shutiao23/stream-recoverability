#!/usr/bin/env python3
"""Freeze a new, explicitly nonconfirmatory Nova Scotia masking experiment.

This is an amendment: an earlier intake plan stated no scoring pending strict
quality/time confirmation. This separate experiment uses weaker, reported-clock
reference data and does not change the strict qualification status.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    report=json.loads((INPUT/'report.json').read_text())
    if report['status']!='passed' or report['strict_reference_qualification']!='not established':raise RuntimeError('unexpected existing reference status')
    y=pd.read_csv(INPUT/'common_complete_label_years.csv',dtype={'station_id':str})
    y=y.loc[y.identical_all_numeric_1e6].copy()
    counts=y.groupby('station_id').size();sites=set(counts[counts.ge(4)].index)
    selected=y.loc[y.station_id.isin(sites),['station_id','year']].sort_values(['station_id','year']).reset_index(drop=True)
    if sites!={'NS01DL0009','NS01FB0001'} or len(selected)!=8:raise ValueError('reference agreement cohort changed')
    locations=pd.read_csv(INPUT/'exploratory_location_audit.csv',dtype={'station_id':str})
    selected=selected.merge(locations[['station_id','latitude','longitude','forcing_latitude','forcing_longitude']],on='station_id',validate='many_to_one')
    if selected.latitude.isna().any():raise ValueError('candidate coordinates unavailable')
    OUT.mkdir(parents=True,exist_ok=True);roster=OUT/'reference_year_roster.csv'
    if roster.exists():
        old=pd.read_csv(roster,dtype={'station_id':str})
        try:pd.testing.assert_frame_equal(old,selected,check_dtype=False)
        except AssertionError as exc:raise RuntimeError('frozen exploratory reference roster changed') from exc
    else:selected.to_csv(roster,index=False)
    model=SOURCE/'deployment/global_source_candidate.joblib';settings=SOURCE/'independent_study/source_case_settings.json';generator=SOURCE/'independent_study/source_missingness_generator.json'
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'frozen_exploratory_amendment',
      'previous_plan':'The original Nova Scotia intake retained no model scores because strict reference quality and timezone were unresolved; that strict status is unchanged.',
      'selection':'after comparing the two releases, select all sites with at least four complete reported-clock years whose hourly numeric values match at 1e-6 C; two sites, eight station-years; selection uses data availability and cross-release agreement, not prediction errors',
      'prior_access':'temperature records and release differences had been inspected algorithmically before this plan; no Nova Scotia model prediction errors were evaluated before the plan',
      'reference':'means of the 24 unique finite hourly numeric cells for each reported-clock day from the Nova Scotia Open Data Portal; exact workbook agreement is checked at every selected hour; no claim that observations are nonestimated, error-free or on a known physical day',
      'training':'three other selected complete years at the same site; target-year daily values are hidden by each mask before local fit; no other site donors; original global annual source model and independent source calibration held fixed',
      'masks':'existing source settings: controlled 30, 60 and 90 day gaps and 2 realizations per overlap cell; use no empirical calendar gaps because the panel intentionally omits other years',
      'estimators':'source-fixed D2, source-calibrated stochastic regression and plug-in; all constrained by observed H30 lower bound; compare D2 and stochastic on common available cases',
      'metrics':'point MAE, bias, failure above 0.5 C, 90 percent interval coverage, width and score, CRPS, counts and availability; masks are not independent stations',
      'forcing':'NASA POWER daily T2M in local solar time at provincial-map coordinates rounded to 0.01 degree; water timestamp basis unresolved, so day-boundary alignment is not established',
      'limitations':'unregistered post-hoc availability and version-agreement selection; two stations in one province, source QC and timezone not established; single-year leave-out with three other years is not whole-archive degradation, climate-independent confirmation or natural-outage evaluation',
      'source_model':'results/wrr_review_completion_20261024/deployment/global_source_candidate.joblib'}
    path=OUT/'plan.json'
    if path.exists():
        old=json.loads(path.read_text())
        for key in ['selection','reference','training','masks']:
            if old[key]!=plan[key]:raise RuntimeError(f'frozen exploratory plan changed: {key}')
    else:path.write_text(json.dumps(plan,indent=2)+'\n')
    print(selected.to_string(index=False));print(json.dumps(plan,indent=2))

if __name__=='__main__':main()
