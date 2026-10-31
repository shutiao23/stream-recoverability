#!/usr/bin/env python3
"""Re-analyse affected forward archives with a stricter same-region exclusion.

The old archive, global source models and existing results are not overwritten.
Local masked-case features and exact masks are reused; source calibration and
annual predictions are recalculated for the newly fitted HUC17 source model.
"""
from __future__ import annotations
import os
for x in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[x]='1'
os.umask(0o077)
import argparse
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import joblib
from joblib import Parallel,delayed
import wrr_tr_common as T

ROOT=T.ROOT
SOURCE=ROOT/'results/wrr_review_completion_20261024'
REV=ROOT/'results/wrr_review_response_20261027'
BASE=REV/'whole_archive'
OUT=REV/'strict_region_holdout'
PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
REGION='usgs_huc17'
KEY=['family','mode','region','station_key','replicate','estimator','retention','dependence']

def work(job,reference,replicate,family,calibration,stage):
    target=stage/family/'forward'/f'replicate_{replicate:02d}'/job['station_key'].replace('|','_')
    original=BASE/family/'forward'/f'replicate_{replicate:02d}'/job['station_key'].replace('|','_')
    source_file=original/'annual_predictions.parquet';source_design=original/'design.json'
    if not source_file.is_file() or not source_design.is_file():raise RuntimeError('original archive inputs missing')
    target.mkdir(parents=True,exist_ok=True,mode=0o700);receipt=target/'strict_receipt.json'
    if receipt.exists():
        info=json.loads(receipt.read_text())
        return str(target)
    staged=target/'annual_predictions.parquet'
    if staged.exists():
        pass
    else:shutil.copyfile(source_file,staged);staged.chmod(0o600)
    archive=T.load_script('strict_archive_worker',ROOT/'scripts/521_whole_archive.py');archive.SOURCE=PRIVATE
    archive.one(job,reference,replicate,'forward',family,calibration,stage,256,False,True,'baseline')
    old=json.loads(source_design.read_text());new=json.loads((target/'design.json').read_text())
    if old['masks']!=new['masks'] or old['station_key']!=new['station_key'] or new['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('strict reanalysis changed masks or exposed target hidden values')
    record={'same_masks':True,'hidden_values_present':0}
    receipt.write_text(json.dumps(record,indent=2)+'\n');receipt.chmod(0o600)
    return str(target)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replicates',type=int,default=20);p.add_argument('--workers',type=int,default=2);args=p.parse_args()
    if not 1<=args.replicates<=20:raise ValueError('replicates must be 1..20')
    status=json.loads((OUT/'refit_status.json').read_text())
    if status['status']!='strict_models_refitted':raise RuntimeError('strict source models not ready')
    target=OUT if args.replicates==20 else OUT/f'pilot_{args.replicates}'
    stage=PRIVATE/'whole_archive' if args.replicates==20 else PRIVATE/f'whole_archive_pilot_{args.replicates}'
    target.mkdir(parents=True,exist_ok=True);stage.mkdir(parents=True,exist_ok=True,mode=0o700)
    strict_module=T.load_script('strict_archive_roles',ROOT/'scripts/610_strict_region_refit.py').strict_module()
    analysis=T.load_script('strict_archive_repair',ROOT/'scripts/467_review_completion_analysis.py')
    archive=T.load_script('strict_archive_calibration',ROOT/'scripts/521_whole_archive.py')
    source=pd.read_parquet(SOURCE/'cases/before_2010/seed_00.parquet');source=analysis.apply_bridge_repairs(source,0,'before_2010')
    bundle=joblib.load(PRIVATE/'refits/before_2010/seed_00'/f'{REGION}.joblib')
    calibration=archive.classical_calibration(source,REGION,strict_module)
    calibration['D2_offsets'],calibration['D2_calibration_groups']=archive.recalibrate_d2(source,REGION,strict_module,bundle)
    cp=PRIVATE/'strict_archive_calibration.json'
    if cp.exists():
        previous=json.loads(cp.read_text())
        if previous!=calibration:raise RuntimeError('existing strict calibration differs')
    else:cp.write_text(json.dumps(calibration,indent=2)+'\n');cp.chmod(0o600)
    cols=['station_key','region','independence_group','year','design_family','mask_runs','h30__policy','eval_truth_h30']
    reference=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=cols)
    original_trends=pd.read_csv(BASE/'trends.csv')
    expected=original_trends.loc[original_trends['mode'].eq('forward')&original_trends.region.eq(REGION),'station_key'].unique()
    core=T.load_script('strict_archive_jobs',ROOT/'scripts/431_tr_cases.py')
    jobs=[j for j in core.jobs_for('source') if j['station_key'] in expected]
    if set(j['station_key'] for j in jobs)!=set(expected):raise ValueError('affected target roster changed')
    tasks=[]
    for job in jobs:
        for family in ['calendar','crossed']:
            ref=reference.loc[reference.station_key.eq(job['station_key'])&reference.design_family.eq(family)]
            for rep in range(args.replicates):tasks.append((job,ref,rep,family,calibration,stage))
    print('Reanalyzing affected archive settings:',len(tasks),flush=True)
    paths=Parallel(n_jobs=args.workers,verbose=10)(delayed(work)(*row) for row in tasks)
    revised=pd.concat([pd.read_csv(Path(p)/'trends.csv') for p in paths],ignore_index=True)
    old=original_trends.loc[original_trends['mode'].eq('forward')&original_trends.region.eq(REGION)&original_trends.replicate.lt(args.replicates)]
    joined=old.merge(revised,on=KEY,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
    if not joined._merge.eq('both').all():raise ValueError('strict and original trend keys differ')
    plug=joined.loc[joined.estimator.eq('plug_in')&joined.dependence.eq('point')]
    if not plug.available_original.eq(plug.available_strict).all() or not np.allclose(plug.error_original,plug.error_strict,rtol=0,atol=1e-8,equal_nan=True):
        raise ValueError('unchanged plugin target data did not reproduce')
    rows=[]
    for keys,g in joined.groupby(['family','estimator','retention','dependence'],sort=True):
        family,estimator,retention,dependence=keys
        valid=g.available_original&g.available_strict
        row={'family':family,'mode':'forward','estimator':estimator,'retention':retention,'dependence':dependence,
             'n_eligible':len(g),'n_common_available':int(valid.sum()),'original_available':int(g.available_original.sum()),'strict_available':int(g.available_strict.sum())}
        for name in ['error','squared_error','missing_coverage95','width95','interval_score95']:
            oldcol=name+'_original';newcol=name+'_strict'
            if oldcol in g and newcol in g:
                row['original_'+name]=float(g.loc[valid,oldcol].mean()) if valid.any() else np.nan
                row['strict_'+name]=float(g.loc[valid,newcol].mean()) if valid.any() else np.nan
        if valid.any():
            row['original_rmse']=float(np.sqrt(g.loc[valid,'squared_error_original'].mean()))
            row['strict_rmse']=float(np.sqrt(g.loc[valid,'squared_error_strict'].mean()))
        rows.append(row)
    summary=pd.DataFrame(rows);summary.to_csv(target/'archive_affected_paired.csv',index=False)
    state={'status':'affected_archives_reanalyzed','region':REGION,'replicates':args.replicates,
      'archive_settings':len(paths),'stations':len(jobs),'paired_trend_rows':len(joined),
      'same_masks_verified':True,'unchanged_plugin_verified':True,'source_calibration':'recomputed after filtering all same-region groups',
      'limitation':'post-hoc paired sensitivity of three stations in one region; remaining source groups and bootstrap weights retained, but smaller source estimator sample changes fitted model; not an independent climate test'}
    (target/'archive_sensitivity_status.json').write_text(json.dumps(state,indent=2)+'\n');print(summary.to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()
