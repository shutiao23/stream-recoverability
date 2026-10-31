#!/usr/bin/env python3
"""Verify candidate-baseline receipts and replay strict HUC17 baselines.

Only the existing model and same daily features are used; this is not an
independent refit, sensor check, prospective test or legal-rights assessment.
"""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import json
import hashlib
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('source_baseline_audit_dependencies',ROOT/'scripts/694_stress_source_sensitivity.py')
KEY=['family','mode','station_key','replicate','estimator','retention','dependence']

def verify_candidate_receipt(original,target,model,calibration):
    receipt=json.loads((target/'open_source_receipt.json').read_text())
    expected={'source_predictions_sha256':hashlib.sha256((original/'annual_predictions.parquet').read_bytes()).hexdigest(),
              'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
              'calibration_sha256':hashlib.sha256(calibration.read_bytes()).hexdigest(),
              'annual_predictions_sha256':hashlib.sha256((target/'annual_predictions.parquet').read_bytes()).hexdigest(),
              'trends_sha256':hashlib.sha256((target/'trends.csv').read_bytes()).hexdigest()}
    if any(receipt.get(k)!=v for k,v in expected.items()) or not receipt.get('same_masks') or receipt.get('hidden_target_values_present')!=0:
        raise ValueError('Candidate baseline receipt differs')

def replay(job,reference,rep,calibration):
    rel=M.suffix(job['station_key'],rep)
    original=M.BASE/rel; saved=M.STRICT/'whole_archive'/rel
    root=M.STAGE/'baseline_audit';target=root/rel
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    pred=target/'annual_predictions.parquet'
    if not pred.exists():
        shutil.copyfile(original/'annual_predictions.parquet',pred)
        runner=T.load_script('strict_baseline_audit_worker',ROOT/'scripts/521_whole_archive.py')
        runner.SOURCE=M.STRICT
        runner.one(job,reference,rep,'forward','crossed',calibration,root,256,False,True,'baseline')
    elif not (target/'design.json').is_file() or not (target/'trends.csv').is_file():
        raise RuntimeError('Partial baseline audit output must be reviewed')
    old=json.loads((saved/'design.json').read_text());new=json.loads((target/'design.json').read_text())
    if old['masks']!=new['masks'] or new['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('Strict baseline mask differs')
    a=pd.read_csv(saved/'trends.csv');b=pd.read_csv(target/'trends.csv')
    pair=a.merge(b,on=KEY,how='outer',suffixes=('_saved','_replayed'),indicator=True,validate='one_to_one')
    if not pair._merge.eq('both').all() or not pair.available_saved.eq(pair.available_replayed).all():
        raise ValueError('Strict baseline trend identities or availability differ')
    for field in ['truth_slope','slope','error','squared_error','lower95','upper95','width95','missing_coverage95','interval_score95']:
        x=pd.to_numeric(pair[field+'_saved'],errors='coerce');y=pd.to_numeric(pair[field+'_replayed'],errors='coerce')
        if not np.allclose(x,y,rtol=0,atol=1e-8,equal_nan=True):raise ValueError('Strict baseline trend replay differs: '+field)
    a=pd.read_parquet(saved/'annual_predictions.parquet');b=pd.read_parquet(target/'annual_predictions.parquet')
    if len(a)!=len(b):raise ValueError('Strict baseline annual cohort differs')
    if len(a):
        if a.year.duplicated().any() or b.year.duplicated().any():raise ValueError('Duplicate baseline year')
        a=a.sort_values('year').reset_index(drop=True);b=b.sort_values('year').reset_index(drop=True)
        if not a.year.equals(b.year) or not a.mask_runs.equals(b.mask_runs):raise ValueError('Strict baseline annual identities differ')
        fields=['D2','risk_score','h30__policy','observed_lower_bound__observed_days']
        fields += [f'{prefix}_q{level}' for prefix in ['D2','stochastic_cal'] for level in ['05','10','25','50','75','90','95']]
        for field in fields:
            if not np.allclose(pd.to_numeric(a[field],errors='coerce'),pd.to_numeric(b[field],errors='coerce'),rtol=0,atol=1e-8,equal_nan=True):
                raise ValueError('Strict baseline annual replay differs: '+field)
    return {'trends':len(pair),'annual':len(a)}

def main():
    M.verify_plan()
    roster=pd.read_csv(M.EXP/'roster.csv')
    verified=0
    for row in roster.itertuples(index=False):
        model=M.CAND/'refits/before_2010/seed_00'/f'{row.region}.joblib'
        calibration=M.CAND/'calibrations/forward'/f'{row.region}.json'
        for rep in range(5):
            rel=M.suffix(row.station_key,rep)
            verify_candidate_receipt(M.BASE/rel,M.CAND/'whole_archive'/rel,model,calibration)
            verified+=1
    core=T.load_script('strict_baseline_audit_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    reference=pd.read_parquet(M.SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','region','independence_group','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
    cal=json.loads((M.STRICT/'strict_archive_calibration.json').read_text())
    tasks=[]
    for row in roster[roster.region.eq('usgs_huc17')].itertuples(index=False):
        ref=reference[reference.station_key.eq(row.station_key)&reference.design_family.eq('crossed')]
        tasks.extend((jobs[row.station_key],ref,rep,cal) for rep in range(5))
    if verified!=205 or len(tasks)!=15:raise ValueError('Unexpected baseline audit cohort')
    # Avoid serializing a dynamically loaded module into worker processes.
    result=[replay(*task) for task in tasks]
    report={'status':'passed','candidate_baseline_receipts_verified':verified,'strict_huc17_baselines_replayed':len(result),
            'strict_trend_rows_replayed':sum(x['trends'] for x in result),'strict_annual_rows_replayed':sum(x['annual'] for x in result),
            'execution_note':'The first attempted parallel audit failed before dispatch because a dynamic module could not be deserialized; the full audit was then executed sequentially.',
            'scope':'Candidate baseline inputs, model, calibration and outputs checked against saved receipts. Strict HUC17 baseline replayed with current strict source model and same daily features and masks, comparing annual predictions and trend summaries. This is not an independent source-model refit or physical sensor validation.'}
    (M.OUT/'baseline_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
