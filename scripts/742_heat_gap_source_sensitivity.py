#!/usr/bin/env python3
"""Replay matched-gap target features using alternative source-region models.

Post-hoc sensitivity on the same target archives; does not independently refit
daily or source models and does not establish source or derivative permissions.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'heat_gap_source_sensitivity';STAGE=ROOT/'private/wrr_heat_gap_source_sensitivity_20261027'
GAP=ROOT/'private/wrr_heat_gap_matched_20261027/run';EXP=ROOT/'private/wrr_expanded_stress_20261027'
M=T.load_script('gap_source_old_sensitivity',ROOT/'scripts/694_stress_source_sensitivity.py')
STRICT=M.STRICT;CAND=M.CAND;BASE=M.BASE;SOURCE=M.SOURCE

def inputs():
    roster=pd.read_csv(EXP/'roster.csv')
    if len(roster)!=41 or roster.station_key.duplicated().any():raise ValueError('Target roster changed')
    paths=[Path(__file__),ROOT/'scripts/734_gap_matched_heat_stress.py',ROOT/'scripts/694_stress_source_sensitivity.py',
           REV/'heat_gap_matched/plan.json',REV/'heat_gap_matched/plan_clarification.json',
           REV/'heat_gap_matched/independent_audit.json',REV/'heat_gap_matched/threeway_independent_audit.json',
           REV/'expanded_stress_source_sensitivity/plan.json',REV/'expanded_stress_source_sensitivity/baseline_audit.json',
           M.STAGE/'input_manifest.json',EXP/'roster.csv',STRICT/'strict_archive_calibration.json',
           STRICT/'refits/before_2010/seed_00/usgs_huc17.joblib']
    for region in sorted(roster.region.unique()):
        paths.extend([CAND/'refits/before_2010/seed_00'/f'{region}.joblib',CAND/'calibrations/forward'/f'{region}.json'])
    for item in roster.itertuples(index=False):
        for rep in range(5):
            rel=M.suffix(item.station_key,rep)
            for name in ['design.json','trends.csv','annual_predictions.parquet']:paths.append(GAP/rel/name)
            for name in ['design.json','trends.csv','annual_predictions.parquet','open_source_receipt.json']:
                paths.append(CAND/'whole_archive'/rel/name)
            if item.region=='usgs_huc17':
                for name in ['design.json','trends.csv','annual_predictions.parquet']:paths.append(STRICT/'whole_archive'/rel/name)
    return roster,list(dict.fromkeys(paths))

def freeze():
    if (OUT/'plan.json').exists():raise FileExistsError('Preserve existing source sensitivity plan')
    if subprocess.run(['git','check-ignore','-q',str(STAGE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Restricted output directory must be ignored by Git')
    M.verify_plan()
    T.load_script('gap_source_plan_check',ROOT/'scripts/734_gap_matched_heat_stress.py').verify_plan()
    for name in ['independent_audit.json','threeway_independent_audit.json','plan_clarification.json']:
        if json.loads((REV/'heat_gap_matched'/name).read_text())['status']!='passed':raise ValueError('Matched-gap audit incomplete')
    roster,paths=inputs();missing=[str(p) for p in paths if not p.is_file()]
    if missing:raise FileNotFoundError('Missing source sensitivity input: '+str(missing[:3]))
    STAGE.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.mkdir(parents=True,exist_ok=True)
    manifest=[{'path':str(p.relative_to(ROOT)),} for p in paths]
    manifest_path=STAGE/'input_manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n');manifest_path.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc after original, source-sensitivity and matched-gap results were viewed; not preregistered',
          'cohort':'41 original forward stations, first five replicates, one matched-gap heat scenario; 205 archives',
          'strict_original':'Replace only the affected HUC17 annual model for its three stations with the earlier strict-region model; retain original source models elsewhere.',
          'candidate':'Use six earlier target-region-excluded candidate-provider models; providers, source sample size and roles change together.',
          'fixed_inputs':'Retain matched-gap masks and stored daily features, target reference and source baselines; recompute annual and trend predictions with alternate source models.',
          'comparison':'Three source versions by baseline and stress on the six-way common archive subset for each estimator and rank structure; also report a common subset across both methods.',
          'limitations':'Source and target results already observed. Original HUC17 strict refit changes source sample; candidate provider, role and sample changes are inseparable. Heat templates and years change jointly. Not natural-outage, independent-climate, new model fit or a coverage guarantee. Four stations use an evaluation-period year in the seven-year air reference.',
          'privacy':'Station-level predictions, input manifest, source models and receipts stay local private; aggregate outputs only.',
          'input_count':len(manifest),}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(f'Recorded post-hoc plan for 205 candidate and 15 strict-source replays; {len(manifest)} inputs.',flush=True)

def verify_plan():
    plan=json.loads((OUT/'plan.json').read_text());manifest=STAGE/'input_manifest.json'
    for row in json.loads(manifest.read_text()):
        path=ROOT/row['path']
        if not path.is_file():raise ValueError('Frozen input changed: '+row['path'])
    M.verify_plan()
    T.load_script('gap_source_input_verify',ROOT/'scripts/734_gap_matched_heat_stress.py').verify_plan()
    return plan

def work(version,job,reference,rep,calibration,model_path,cal_path):
    rel=M.suffix(job['station_key'],rep);original=GAP/rel;root=STAGE/version/'heat_gap_matched';target=root/rel
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    source=original/'annual_predictions.parquet';receipt=target/'receipt.json'
    expected={}
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        if saved['inputs']!=expected:
            raise ValueError('Existing source replay receipt changed')
        M.verify_plugin(original,target);return str(target)
    staged=target/'annual_predictions.parquet'
    if staged.exists():
        pass
    else:
        shutil.copyfile(source,staged);staged.chmod(0o600)
    runner=T.load_script('gap_source_worker',ROOT/'scripts/734_gap_matched_heat_stress.py')
    runner.SOURCE=STRICT if version=='strict_original' else CAND
    runner.one(job,reference,rep,'forward','crossed',calibration,root,256,False,True,'heat_gap_matched')
    previous=json.loads((original/'design.json').read_text());new=json.loads((target/'design.json').read_text())
    if previous['station_key']!=new['station_key'] or previous['masks']!=new['masks'] or new['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('Source replay changed masks or exposed hidden target values')
    M.verify_plugin(original,target)
    receipt.write_text(json.dumps({'inputs':expected,'same_masks':True},indent=2)+'\n');receipt.chmod(0o600)
    return str(target)

def run(workers,pilot=False):
    verify_plan();roster=pd.read_csv(EXP/'roster.csv')
    if pilot:roster=roster[roster.region.eq('usgs_huc17')].sort_values('station_key').iloc[:1]
    jobs={j['station_key']:j for j in T.load_script('gap_source_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')}
    ref=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','region','independence_group','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
    tasks=[]
    for row in roster.itertuples(index=False):
        reference=ref[ref.station_key.eq(row.station_key)&ref.design_family.eq('crossed')]
        for rep in (range(1) if pilot else range(5)):
            candidate=CAND/'calibrations/forward'/f'{row.region}.json'
            tasks.append(('candidate',jobs[row.station_key],reference,rep,json.loads(candidate.read_text()),
                          CAND/'refits/before_2010/seed_00'/f'{row.region}.joblib',candidate))
            if row.region=='usgs_huc17':
                cal=STRICT/'strict_archive_calibration.json'
                tasks.append(('strict_original',jobs[row.station_key],reference,rep,json.loads(cal.read_text()),
                              STRICT/'refits/before_2010/seed_00/usgs_huc17.joblib',cal))
    if len(tasks)!=(2 if pilot else 220):raise ValueError('Unexpected source replay denominator')
    result=Parallel(n_jobs=workers,verbose=10)(delayed(work)(*task) for task in tasks)
    status={'status':'pilot_passed_no_accuracy_claim' if pilot else 'completed','replays':len(result),
            'source_versions':2,'same_masks_daily_features_and_plugin_checked':True,
            'limitation':'Stored daily features, fitted source models and target observations are reused; not a new fit or independent climate validation.'}
    (OUT/('pilot.json' if pilot else 'execution.json')).write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','pilot','run']);p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    if args.workers<1:raise ValueError('Worker count must be positive')
    if args.action=='freeze':freeze()
    else:run(args.workers,pilot=args.action=='pilot')
