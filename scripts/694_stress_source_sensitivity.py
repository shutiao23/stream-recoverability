#!/usr/bin/env python3
"""Replay stress archives with strict-region and candidate-provider models.

Both comparisons are post-hoc and reuse previously fitted local daily features.
The strict-original sensitivity replaces only the affected HUC17 model; the
candidate sensitivity also changes provider pool and source role assignments.
Local case-level outputs are never placed in the review package.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='1'
os.umask(0o077)
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'expanded_stress_source_sensitivity'
EXP=ROOT/'private/wrr_expanded_stress_20261027'
STAGE=ROOT/'private/wrr_expanded_stress_source_20261027'
STRICT=ROOT/'private/wrr_strict_region_holdout_20261026'
CAND=ROOT/'private/wrr_open_source_sensitivity_20261026'
BASE=REV/'whole_archive'
SOURCE=ROOT/'results/wrr_review_completion_20261024'
SCENARIOS=('synchronized_donors','heat_associated_matched')
KEY=['family','mode','station_key','replicate','estimator','retention','dependence']

def suffix(station,rep):
    return Path('crossed')/'forward'/f'replicate_{rep:02d}'/station.replace('|','_')

def input_set():
    roster=pd.read_csv(EXP/'roster.csv')
    if len(roster)!=41 or roster.station_key.duplicated().any():raise ValueError('Expanded roster changed')
    files=[Path(__file__),ROOT/'scripts/689_fixed_count_heat_stress.py',EXP/'roster.csv',EXP/'input_manifest.json',
           REV/'expanded_stress/plan.json',REV/'expanded_stress/independent_audit.json',
           REV/'audit/region_holdout_role_report.json',REV/'open_source_sensitivity/candidate_source_role_audit.json',
           STRICT/'refit_receipts.json', STRICT/'strict_archive_calibration.json', CAND/'refit_receipts.json']
    regions=sorted(roster.region.unique())
    files.append(STRICT/'refits/before_2010/seed_00/usgs_huc17.joblib')
    for region in regions:
        files.extend([CAND/'refits/before_2010/seed_00'/f'{region}.joblib',CAND/'calibrations/forward'/f'{region}.json'])
    for row in roster.itertuples(index=False):
        for rep in range(5):
            rel=suffix(row.station_key,rep)
            for directory in (BASE/rel,CAND/'whole_archive'/rel):
                files.extend([directory/'design.json',directory/'trends.csv'])
            if row.region=='usgs_huc17':
                files.extend([STRICT/'whole_archive'/rel/'design.json',STRICT/'whole_archive'/rel/'trends.csv'])
            for scenario in SCENARIOS:
                directory=EXP/scenario/rel
                files.extend([directory/'design.json',directory/'trends.csv',directory/'annual_predictions.parquet'])
    return roster,list(dict.fromkeys(files))

def check_source_roles():
    old=json.loads((REV/'audit/region_holdout_role_report.json').read_text())
    candidate=json.loads((REV/'open_source_sensitivity/candidate_source_role_audit.json').read_text())
    sr=json.loads((STRICT/'refit_receipts.json').read_text())['usgs_huc17']
    cr=json.loads((CAND/'refit_receipts.json').read_text())
    if old['status']!='passed' or candidate['status']!='passed' or candidate['positive_target_region_rows']!=0 or candidate['post_2009_forward_source_rows']!=0:
        raise ValueError('Previously checked source-role evidence is not valid')
    if sr['same_region_positive_weight_cases']!=0:
        raise ValueError('Strict HUC17 model or role receipt differs')
    roster,_=input_set()
    for region in roster.region.unique():
        row=cr['forward|'+region]
        model=CAND/'refits/before_2010/seed_00'/f'{region}.joblib'
        if row['strict_target_region_positive_rows']!=0:
            raise ValueError(f'Candidate model or strict-role receipt differs: {region}')

def freeze():
    if (OUT/'plan.json').exists():raise FileExistsError('Existing source-sensitivity plan is preserved')
    check_source_roles()
    roster,files=input_set()
    missing=[str(p) for p in files if not p.is_file()]
    if missing:raise FileNotFoundError(f'Missing frozen inputs: {missing[:4]}')
    STAGE.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.mkdir(parents=True,exist_ok=True)
    manifest=[{'path':str(p.relative_to(ROOT)),} for p in files]
    m=STAGE/'input_manifest.json';m.write_text(json.dumps(manifest,indent=2)+'\n')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc after the source-role, original archive and expanded stress results were examined; not prospective registration',
          'expected_archives_per_scenario':205,'target_stations':len(roster),'target_groups':int(roster.independence_group.nunique()),
          'strict_original':'Replace the affected forward HUC17 source model for its three stations with the previously refitted model excluding all HUC17 connected groups; retain original models for other target regions. Source sample size changes.',
          'candidate':'Use the six previously refitted candidate-provider models that exclude all target-region groups; provider pool, sample size and role assignment all change together.',
          'fixed_inputs':'Use the existing baseline and stress target masks and already fitted daily features for all versions; source annual predictions and calibration offsets are recomputed. The previous daily feature fits and test masks are not regenerated.',
          'comparison':'For each scenario and estimator, compare baseline and stress under all three source versions on the six-way common available archives. Report availability, bias, RMSE, interval coverage and scores and connected-group resamples. Report matched stress effect as stress minus baseline; do not equate different selected cohorts.',
          'bootstrap':'4000 connected-group resamples of paired squared-error stress-minus-baseline difference, seed 694; descriptive, not an independent-climate interval.',
          'limitations':'All source-role and stress results are already viewed. Retrospective sensitivity changes model sample size; candidate version also changes providers and roles. Group bootstrap and leave-region-out do not establish general transfer. Heat-selected years may change gap days and positions. Not natural-outage or external validation. Provider and derivative rights remain unresolved.',
          'privacy':'case-level predictions, source models, input manifest and local output receipts remain private; only aggregate summaries in candidate package',
          'input_count':len(manifest),}
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(f'Frozen 205 archives per scenario and {len(manifest)} input files',flush=True)

def verify_plan():
    plan=json.loads((OUT/'plan.json').read_text())
    manifest=STAGE/'input_manifest.json'
    # The prior expanded-stress plan also binds station panels, air, source and masks.
    prior=json.loads((REV/'expanded_stress/plan.json').read_text())
    prior_manifest=EXP/'input_manifest.json'
    for row in json.loads(prior_manifest.read_text()):
        p=Path(row['path']);p=p if p.is_absolute() else ROOT/p
    check_source_roles()
    return plan

def verify_plugin(original,target):
    old=pd.read_csv(original/'trends.csv');new=pd.read_csv(target/'trends.csv')
    x=old.merge(new,on=KEY,how='outer',suffixes=('_old','_new'),indicator=True,validate='one_to_one')
    if not x._merge.eq('both').all():raise ValueError('Trend row identity differs')
    p=x[x.estimator.eq('plug_in')&x.dependence.eq('point')]
    if p.empty or not p.available_old.eq(p.available_new).all() or not np.allclose(p.error_old,p.error_new,rtol=0,atol=1e-8,equal_nan=True):
        raise ValueError('Unchanged plug-in or target trend does not replay')
    oldpred=pd.read_parquet(original/'annual_predictions.parquet')
    newpred=pd.read_parquet(target/'annual_predictions.parquet')
    if len(oldpred)!=len(newpred):raise ValueError('Annual target cases differ')
    if len(oldpred):
        a=oldpred[['year','mask_runs','h30__policy','eval_truth_h30','observed_lower_bound__observed_days']].sort_values('year').reset_index(drop=True)
        b=newpred[a.columns].sort_values('year').reset_index(drop=True)
        if not a[['year','mask_runs']].equals(b[['year','mask_runs']]):raise ValueError('Yearly gap masks differ')
        for field in ['h30__policy','eval_truth_h30','observed_lower_bound__observed_days']:
            if not np.allclose(a[field],b[field],rtol=0,atol=1e-8,equal_nan=True):raise ValueError(f'Daily feature changed: {field}')

def work(scenario,version,job,reference,rep,calibration,model_path,cal_path):
    rel=suffix(job['station_key'],rep)
    original=EXP/scenario/rel
    source=original/'annual_predictions.parquet'
    root=STAGE/version/scenario
    target=root/rel;target.mkdir(parents=True,exist_ok=True,mode=0o700)
    receipt=target/'receipt.json'
    inputs={}
    if receipt.exists():
        r=json.loads(receipt.read_text())
        if r['inputs']!=inputs:
            raise ValueError('Existing scenario receipt changed')
        verify_plugin(original,target)
        return str(target)
    staged=target/'annual_predictions.parquet'
    if staged.exists():
        pass
    else:
        shutil.copyfile(source,staged);staged.chmod(0o600)
    model=T.load_script('expanded_strict_worker',ROOT/'scripts/689_fixed_count_heat_stress.py')
    model.SOURCE=STRICT if version=='strict_original' else CAND
    model.one(job,reference,rep,'forward','crossed',calibration,root,256,False,True,scenario)
    old=json.loads((original/'design.json').read_text());new=json.loads((target/'design.json').read_text())
    if old['station_key']!=new['station_key'] or old['masks']!=new['masks'] or new['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('Reanalysis changed masks or exposed hidden targets')
    if scenario=='synchronized_donors' and new['hidden_donor_values_present']!=0:
        raise ValueError('Reanalysis exposed hidden donor observations')
    verify_plugin(original,target)
    receipt.write_text(json.dumps({'inputs':inputs,'same_masks':True},indent=2)+'\n')
    return str(target)

def run(workers):
    verify_plan()
    roster=pd.read_csv(EXP/'roster.csv')
    core=T.load_script('source_stress_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={x['station_key']:x for x in core.jobs_for('source')}
    ref=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','region','independence_group','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
    strict_cal=STRICT/'strict_archive_calibration.json'
    candidate_cal={r:CAND/'calibrations/forward'/f'{r}.json' for r in roster.region.unique()}
    tasks=[]
    for row in roster.itertuples(index=False):
        job=jobs[row.station_key];reference=ref[(ref.station_key==row.station_key)&(ref.design_family=='crossed')]
        for rep in range(5):
            for scenario in SCENARIOS:
                tasks.append((scenario,'candidate',job,reference,rep,json.loads(candidate_cal[row.region].read_text()),
                              CAND/'refits/before_2010/seed_00'/f'{row.region}.joblib',candidate_cal[row.region]))
                if row.region=='usgs_huc17':
                    tasks.append((scenario,'strict_original',job,reference,rep,json.loads(strict_cal.read_text()),
                                  STRICT/'refits/before_2010/seed_00/usgs_huc17.joblib',strict_cal))
    if len(tasks)!=440:raise ValueError('Unexpected task count')
    print('Reanalyzing',len(tasks),'stress settings under alternative source models',flush=True)
    completed=Parallel(n_jobs=workers,verbose=10)(delayed(work)(*item) for item in tasks)
    (OUT/'execution.json').write_text(json.dumps({'status':'completed','scenario_reanalyses':len(completed),
        'candidate_reanalyses':410,'strict_huc17_reanalyses':30,'same_masks_and_plugin_replayed':True,
        'limit':'post-hoc reuse of local features, no independent sensor or climate data'},indent=2)+'\n')
    print('All scenario refits completed; summaries remain to be computed',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['freeze','run'])
    p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    freeze() if args.action=='freeze' else run(args.workers)
