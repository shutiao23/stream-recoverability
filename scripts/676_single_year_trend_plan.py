#!/usr/bin/env python3
"""Freeze post-hoc trend propagation of source-only annual interval expansion."""
from __future__ import annotations
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026'
BASE=ROOT/'results/wrr_review_completion_20261024'

def main():
    path=OUT/'single_year_trend_plan.json'
    if path.exists():raise RuntimeError('Preserve the existing trend sensitivity plan')
    plan=json.loads((OUT/'single_year_calibration_plan.json').read_text())
    status=json.loads((OUT/'single_year_calibration_status.json').read_text())
    audit=json.loads((OUT/'single_year_independent_audit.json').read_text())
    alignment=json.loads((OUT/'single_year_support_alignment.json').read_text())
    if not all(x['status']=='passed' for x in [status,audit,alignment]):raise ValueError('Annual source expansion audits must pass')
    support=pd.read_csv(OUT/'single_year_source_support.csv')
    pivot=support.pivot(index=['family','mode','region'],columns='estimator',values='status')
    eligible=pivot.loc[pivot[['D2','stochastic_calibrated']].eq('supported_exploratory').all(axis=1)].reset_index()
    if len(eligible)!=4 or not (eligible.family.eq('crossed')&eligible['mode'].eq('forward')).all():
        raise ValueError('Source-supported trend scope differs; reassess plan')
    trends=pd.read_csv(ROOT/'results/wrr_review_response_20261027/open_source_sensitivity/archive_four_way_comparison.csv')
    if not len(trends):raise ValueError('Prior paired trend audit missing')
    core=T.load_script('single_year_trend_plan_jobs',ROOT/'scripts/431_tr_cases.py')
    design=json.loads((OUT/'plan.json').read_text());regions=set(eligible.region)
    jobs=[j for j in core.jobs_for('source') if j['region'] in regions]
    # Restrict to the actual previously evaluated whole-archive roster.
    roster=set(json.loads((ROOT/'results/wrr_review_response_20261027/whole_archive/design.json').read_text())['station_keys'])
    jobs=[j for j in jobs if j['station_key'] in roster]
    if len(jobs)!=38 or len({j['station_key'] for j in jobs})!=38:raise ValueError('Supported station roster differs from annual analysis')
    panel_paths=sorted({Path(j['input_path']).resolve() for j in jobs})
    if any(not p.is_relative_to(ROOT.resolve()) for p in panel_paths):raise ValueError('Target panel outside project root')
    input_files=[BASE/'cases/leave_one_year_out/seed_00.parquet',Path(jobs[0]['air_input_path']),T.CONFIG,
                 ROOT/'scripts/521_whole_archive.py',ROOT/'scripts/431_tr_cases.py',
                 ROOT/'src/stream_recoverability/experiments/tr_revision/archive.py',
                 ROOT/'src/stream_recoverability/experiments/v19_revision/data.py',
                 ROOT/'src/stream_recoverability/experiments/development_recovery.py',
                 ROOT/'src/stream_recoverability/seeds.py',
                 OUT/'single_year_calibration_plan.json',OUT/'single_year_source_support.csv',
                 OUT/'single_year_source_freeze.json',OUT/'single_year_calibration_status.json',
                 OUT/'single_year_independent_audit.json',OUT/'single_year_support_alignment.json',
                 OUT/'annual_sensitivity_status.json']+panel_paths
    for p in input_files:
        if not p.resolve().is_relative_to(ROOT.resolve()) or not p.is_file():raise ValueError('Planned input missing or outside root')
    receipts=sorted((PRIVATE/'whole_archive').glob('crossed/forward/replicate_*/*/open_source_receipt.json'))
    if len(receipts)!=820:raise ValueError('Candidate archive receipts not complete')
    for p in receipts:sig.update(str(p.relative_to(PRIVATE/'whole_archive')).encode()+b'\0'+p.read_bytes())
    payload={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc_frozen_before_new_trend_propagation',
      'source_supported_regions':sorted(regions),'supported_target_stations':len(jobs),'planned_archive_settings':len(jobs)*20,
      'source_supported_both_methods_required':True,'target_archive_must_have_incomplete_year':True,
      'family':'crossed','mode':'forward','replicates':20,'draws':256,'marginals':['baseline','endpoint_only','tapered'],
      'adjustments':'For each incomplete year, use the frozen source radius for its region and method. Endpoint-only shifts q05 downward and q95 upward; tapered also moves q10/q25 and q75/q90 by 0.8/0.4 radii toward the tails, keeping q50 unchanged. Project all quantiles to the observed bound. Both have identical adjusted q05 and q95; their interior and normal-spacing outer-tail representations differ.',
      'couplings':['independent','shared_parameters','residual_blocks'],
      'coupling_rule':'Reconstruct the original seed-specific ranks, including history fits from masked target and pre-2010 restriction. Reuse exactly the same rank matrices across baseline and adjusted marginals. Original baseline 95% coverage, width, interval endpoints and interval score must reproduce saved candidate archive outputs.',
      'evaluation':'Same station-repetition cases with positive source support for both methods, at least one incomplete year, finite distributions and all three ranks; report original availability, source-supported and four-way common cases, trend coverage, width, interval score and connected-group resampling.',
      'limitations':'Post-hoc after target annual and trend results were observed. Endpoint-only and tapered quantile interpolation are assumptions beyond the calibrated 90% endpoints. Single-year source calibration differs from jointly degraded target archives. Candidate source changes multiple components, has only 6-8 assigned forward rule groups, and does not guarantee group or independent-climate coverage. Trend point estimate remains unchanged; climate-process trend and physical sensor uncertainty are not evaluated.'}
    path.write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload,indent=2))

if __name__=='__main__':main()
