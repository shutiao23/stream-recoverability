#!/usr/bin/env python3
"""Prepare local-only case-level evidence for the current reviewer analysis.

Contains third-party observations/derivatives: not a public archive, data
licence, permission to send, or full reconstruction of raw-source models.
The destination is git-ignored and restricted to the current OS user.
"""
from __future__ import annotations
import json
import filecmp
import os
from pathlib import Path
import shutil
import stat
import sys
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
OUT=ROOT/'private/wrr_review_case_evidence_20261027'
QS=[5,10,25,50,75,90,95]
COLUMNS=['station_key','independence_group','year','observed_lower_bound__observed_days','D2'] + [
    f'{p}_q{q:02d}' for p in ['D2','stochastic_cal'] for q in QS]


def private_copy(src,relative):
    dest=OUT/relative;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if dest.exists():
        if not filecmp.cmp(src,dest,shallow=False):
            raise RuntimeError(f'Existing local evidence differs; use a new destination: {dest}')
    else:
        shutil.copyfile(src,dest)
    dest.chmod(0o600)


def main():
    os.umask(0o077)
    OUT.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.chmod(0o700)
    # Refuse to work in a destination that the repository would track.
    import subprocess
    ignored=subprocess.run(['git','check-ignore','-q',str(OUT.relative_to(ROOT))+'/README.txt'],cwd=ROOT)
    if ignored.returncode!=0:raise RuntimeError('Private destination is not protected by .gitignore')
    source=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
    ref=pd.read_parquet(source,columns=['station_key','year','design_family','eval_truth_h30'])
    key=['station_key','year','design_family']
    grouped=ref.groupby(key,dropna=False).eval_truth_h30.agg(['min','max','count'])
    if grouped['count'].eq(0).any() or (grouped['max']-grouped['min']).gt(1e-8).any():raise RuntimeError('Source reference inconsistent')
    refs=grouped['min'].rename('reference_h30').reset_index().rename(columns={'design_family':'family'})
    cases=[];files=0
    for family in ['calendar','crossed']:
        for mode in ['offline','forward']:
            paths=sorted((REV/'whole_archive'/family/mode).glob('replicate_*/*/annual_predictions.parquet'))
            files+=len(paths)
            for p in paths:
                if pq.ParquetFile(p).metadata.num_rows==0:continue
                d=pd.read_parquet(p,columns=COLUMNS)
                d['family']=family;d['mode']=mode;d['replicate']=int(p.parent.parent.name.split('_')[-1]);cases.append(d)
    case=pd.concat(cases,ignore_index=True).merge(refs,on=['station_key','year','family'],how='left',validate='many_to_one')
    if case.reference_h30.isna().any() or case.duplicated(['family','mode','replicate','station_key','year']).any():
        raise RuntimeError('Missing reference or repeated annual identity')
    target=OUT/'results/wrr_review_response_20261027/whole_archive/annual_case_evidence.parquet'
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if target.exists():
        if not pd.read_parquet(target).equals(case):
            raise RuntimeError('Existing private annual evidence differs; preserve it and use a new destination')
    else:
        case.to_parquet(target,index=False)
    target.chmod(0o600)
    # Preserve only eligible canonical daily observations needed to recheck
    # reported-record witnesses. These remain restricted, local-only data.
    station_years=pd.read_parquet(ROOT/'results/wrr_target_recovery_20261021/e1_archive/station_years.parquet')
    selected=station_years.loc[~station_years.edge_year & station_years.fully_active & station_years.year.between(1981,2025)].copy()
    complete=selected.loc[selected.complete_year & selected.truth_h30.notna()]
    counts=complete.groupby('station_key').size();eligible=counts.index[counts.ge(15)].tolist()
    selected=selected.loc[selected.station_key.isin(eligible)].reset_index(drop=True)
    daily=pd.read_parquet(ROOT/'scratch/wrr_target_recovery_20261021/archive_daily.parquet',
        columns=['station_key','date','water_c'],filters=[('station_key','in',eligible)])
    daily=daily.loc[daily.date.between(pd.Timestamp('1981-01-01'),pd.Timestamp('2025-12-31'))].reset_index(drop=True)
    for relative,frame in [
        ('results/wrr_target_recovery_20261021/e1_archive/station_years.parquet',selected),
        ('scratch/wrr_target_recovery_20261021/archive_daily.parquet',daily)]:
        path=OUT/relative;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.exists():
            if not pd.read_parquet(path).equals(frame):raise RuntimeError(f'Existing private record input differs: {path}')
        else:frame.to_parquet(path,index=False)
        path.chmod(0o600)
    files_to_copy=[
      'whole_archive/annual.csv','whole_archive/annual_summary.csv','whole_archive/trends.csv','whole_archive/trend_summary.csv',
      'whole_archive/factorial_contrasts.csv','whole_archive/factorial_paired_summary.csv',
      'whole_archive/quantile_tail_sensitivity.csv','whole_archive/uncertainty_paired_summary.csv',
      'whole_archive/support_projection_summary.csv','whole_archive/task_calibrated_trends.csv',
      'release_outputs/clean.parquet','release_outputs/air_exposure.parquet','release_outputs/hot_year_extrapolation.parquet',
      'release_outputs/future_years.parquet','release_outputs/smooth_non_air_shift.parquet',
      'release_outputs/release_metrics.csv','release_outputs/output_states.csv','release_outputs/hot_event_metrics.csv','release_outputs/matched_numerical_retention.csv',
      'release_outputs/source_rule_thresholds.csv','release_outputs/source_calibrated_release_summary.csv',
      'release_outputs/source_calibrated_group_availability.csv',
      'integrated_release_trend/annual_decisions.parquet','integrated_release_trend/station_repetitions.csv',
      'integrated_release_trend/summary.csv','integrated_release_trend/paired_baselines.csv',
      'annual/source_scorecard.csv','annual/source_scorecard_summary.csv','annual/source_paired.csv',
      'rules/eligible_station_years.csv','rules/witness_rules.csv','rules/rule_summary.csv',
    ]
    for rel in files_to_copy:private_copy(REV/rel,Path('results/wrr_review_response_20261027')/rel)
    cohort=pd.read_csv(ROOT/'results/additional_usgs_observed/cohort_metadata.csv',dtype={'station_id':str})
    for station in sorted(cohort.station_id):
        path=ROOT/'data/external/additional_usgs_observed/raw'/(station+'.json.gz')
        if not path.is_file():raise RuntimeError(f'Missing selected USGS API payload {station}')
        private_copy(path,path.relative_to(ROOT))
    for rel in ['results/additional_usgs_observed/cohort_metadata.csv',
                'results/additional_usgs_observed/raw_reference_summary.csv',
                'results/wrr_review_completion_20261024/observed_records/all_incomplete_year_bounds.csv',
                'results/wrr_review_completion_20261024/observed_records/observed_record_certificates.csv',
                'results/additional_usgs_observed/robust_record_witnesses.csv']:
        private_copy(ROOT/rel,Path(rel))
    seed_files=[OUT/'annual_source_cases'/f'seed_{seed:02d}.parquet' for seed in range(20)]
    seed_count=sum(path.is_file() for path in seed_files)
    absent=['provider-native raw files','full source-model training data and weights','an external deposit or permission']
    if seed_count < 20:absent.append('complete set of 20 individual source-seed case predictions')
    metadata={'archive_files_processed':files,'annual_case_rows':len(case),'stations':int(case.station_key.nunique()),
              'contains_sensitive_derivatives':True,'data_rights_resolved':False,
              'annual_source_case_seed_files':seed_count,'not_included':absent,
              'canonical_daily_scope':'96 eligible stations, 1981--2025; reported daily float32 values, not provider-native raw records; plus saved USGS daily API responses for 10 separate sites',
              'intended_use':'local audit only; do not send or publish without rights and author decisions',
              'limitations':'case-level recalculation checks reported scalar metrics; it cannot verify raw observations, fitted model training, joint sample generation or entire paper'}
    (OUT/'local_evidence_status.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (OUT/'local_evidence_status.json').chmod(0o600)
    readme='''LOCAL REVIEW WORKING DATA — NOT AUTHORISED FOR DISTRIBUTION

This directory includes individual published-record values, estimates, group
identifiers and derivatives of third-party observations. Provider permissions
and reviewer-access conditions have not been established. Keep it local and
private. Do not upload or send it to reviewers without resolving those rights.

It includes a 96-station canonical daily subset for local observed-record
checks, but not the provider-native raw files or a complete raw-data rebuild.
Use `make review-local-case-audit` in the original workspace. Optional saved
seed predictions and their scoring audit use `make review-private-annual-audit`.
The complete source-model training data and weights are not included;
retraining and obtaining a durable deposit remain separate tasks.
'''
    if not (OUT/'README.txt').exists():(OUT/'README.txt').write_text(readme)
    (OUT/'README.txt').chmod(0o600)
    print(json.dumps(metadata,indent=2),flush=True)

if __name__=='__main__':main()
