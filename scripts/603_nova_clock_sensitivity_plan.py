#!/usr/bin/env python3
"""Freeze a post-hoc reported-day boundary sensitivity for scored NS cases."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_clock_sensitivity'


def main():
    score=json.loads((BASE/'score_status.json').read_text());integrity=json.loads((BASE/'integrity_status.json').read_text())
    if score['status']!='exploratory_scored' or integrity['status']!='passed':raise RuntimeError('base exploratory study not audited')
    roster=pd.read_csv(BASE/'reference_year_roster.csv',dtype={'station_id':str})
    if len(roster)!=8 or roster.station_id.nunique()!=2:raise ValueError('unexpected original target roster')
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/'plan.json'
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'frozen_posthoc_sensitivity',
      'base_plan':'results/wrr_review_response_20261027/external_nova_scotia_exploratory/plan.json',
      'scope':'same two sites and eight already scored station-years; no new sites or calendar years selected',
      'shifts_hours':[-1,0,1],
      'reported_day_definition':'for each stated date use the 24 reported hourly labels beginning at 00:00 plus the specified shift; this is a hypothetical boundary convention, not an inferred true time zone',
      'boundary_rule':'require all 24-hourly labels and finite values from both provincial releases, unique in each and equal within 1e-6 C; include adjacent-year boundary hours when necessary; no interpolation',
      'unavailable':'if any selected year lacks a needed boundary value, retain its failure reason and do not invent data; full variant scoring for a site requires all four originally selected years',
      'masks':'reuse each original site-year mask exactly; compare same gap realizations under all available day-boundary variants',
      'fitting':'rebuild daily features under each boundary, refit local leave-one-year-out stages using the other three years; original source model, source calibration and NASA POWER forcing remain fixed',
      'evaluation':'paired H30 MAE, nominal 90 percent coverage, width and interval score; report availability and per-site results',
      'timing':'defined after the original exploratory scores and source-version comparison were inspected; not preregistered or confirmatory',
      'limitation':'one-hour shifts do not identify the actual source time basis, resolve estimated-value/QC status, represent every possible local solar-time discrepancy, or establish climate independence'}
    if path.exists():
        old=json.loads(path.read_text())
        for k in ['scope','shifts_hours','boundary_rule','masks','fitting']:
            if old[k]!=plan[k]:raise RuntimeError(f'existing sensitivity plan changed: {k}')
    else:path.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan,indent=2))

if __name__=='__main__':main()
