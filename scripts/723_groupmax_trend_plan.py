#!/usr/bin/env python3
"""Freeze post-hoc propagation of group-max annual intervals to trends."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'groupmax_annual_calibration'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026'
PRIVATE=ROOT/'private/wrr_groupmax_annual_calibration_20261027'

def main():
    path=OUT/'trend_plan.json'
    if path.exists():raise FileExistsError('Group-max trend plan already exists')
    status=json.loads((OUT/'status.json').read_text());audit=json.loads((OUT/'independent_audit.json').read_text())
    if status.get('summary_denominator_corrected') is not True or audit['status']!='passed':raise ValueError('Annual source and target audits incomplete')
    support=pd.read_csv(OUT/'source_support.csv');rows=support[support.family.eq('crossed')]
    if len(rows)!=12 or not rows.status.eq('supported_exploratory').all():raise ValueError('Not all regions support both group-max radii')
    roster=pd.read_csv(ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv')
    if len(roster)!=41 or roster.station_key.duplicated().any():raise ValueError('Forward target roster changed')
    core=T.load_script('groupmax_trend_plan_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    if not set(roster.station_key).issubset(jobs):raise ValueError('A target station job is missing')
    files=[Path(__file__),ROOT/'scripts/724_groupmax_trend_propagation.py',ROOT/'scripts/677_single_year_trend_propagation.py',
           ROOT/'scripts/521_whole_archive.py',ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/wrr_tr_common.py',T.CONFIG,
           ROOT/'src/stream_recoverability/experiments/tr_revision/archive.py',
           ROOT/'src/stream_recoverability/experiments/v19_revision/data.py',
           ROOT/'src/stream_recoverability/experiments/development_recovery.py',ROOT/'src/stream_recoverability/seeds.py',
           ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',
           ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv',
           OUT/'plan.json',OUT/'source_support.csv',OUT/'source_freeze.json',OUT/'status.json',
           OUT/'summary_correction.json',OUT/'independent_audit.json']
    for row in roster.itertuples(index=False):
        for key in ['input_path','air_input_path']:
            p=Path(jobs[row.station_key][key])
            if not p.is_file():raise FileNotFoundError('Target panel or air input missing')
            files.append(p)
    receipts=sorted((INPUT/'whole_archive/crossed/forward').glob('replicate_*/*/open_source_receipt.json'))
    if len(receipts)!=820:raise ValueError('Candidate archive receipt count differs')
    previous=sorted((INPUT/'single_year_trend_propagation/full').glob('replicate_*/*/marginals_and_ranks.npz'))
    if len(previous)!=685:raise ValueError('Earlier matched-rank reference set changed')
    files=list(dict.fromkeys(files+receipts+previous))
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    manifest=[]
    for p in files:
        resolved=p.resolve()
        if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():raise ValueError('Planned input missing or outside root')
        manifest.append({'path':str(resolved.relative_to(ROOT.resolve())),})
    m=PRIVATE/'trend_input_manifest.json';m.write_text(json.dumps(manifest,indent=2)+'\n')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc propagation after annual group-max and prior trend results were inspected; not prospective registration',
          'scope':'41 forward target stations, 20 existing replicates and controlled-gap masks; 820 expected archives; source support for both estimators required',
          'source_radius':'fixed per-region and estimator group-max annual radius from disjoint numeric-fit/calibration source roles; 90% annual rank only, not a 95% joint-trend calibration',
          'annual_shapes':'baseline, endpoint-only and tapered; both expanded versions have the same q05/q95, fixed median and observed lower bound, but differing interior quantiles and normal-spacing outer tails',
          'dependence':'independent, auxiliary shared-parameter and residual-block ranks rebuilt with the same historical target masks and random seeds. All three representations use the same ranks and preserve their own annual marginals.',
          'validation':'replay saved candidate baseline trend; where earlier empirical-expansion rank snapshots exist, compare years, truth, masks, bounds, baseline quantiles and all rank matrices. Target groups are descriptive, not independent climates.',
          'evaluation':'report all 820 availability and common nontrivial archives, same-case 95% trend coverage, interval width and score for both estimators and three rank models, group bootstrap and fixed-prediction leave-region sensitivity.',
          'limitations':'source group maxima come from single-year masks, target archives have multiple joint gaps and different source/target group sizes; source and target groups are not known exchangeable. The 90% annual calibration and assumed shape/rank coupling do not establish 95% trend coverage or any guarantee. Previous empirical and group-max results have been viewed.',
          'expected_archive_settings':820,'expected_previous_rank_snapshots':len(previous),}
    path.write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen post-hoc propagation across 820 forward archive settings',flush=True)

if __name__=='__main__':main()
