#!/usr/bin/env python3
"""Paired strict-region sensitivity of release followed by trend inference.

Replays original decisions as a mandatory check, then recalculates both steps
for the same 120 affected forward archive settings. Other regions are carried
forward unchanged. Case-level results and intermediate models remain private.
"""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
os.umask(0o077)
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
ORIGINAL=REV/'whole_archive'
SOURCE=ROOT/'results/wrr_review_completion_20261024'
PRIVATE=ROOT/'private/wrr_strict_region_holdout_20261026'
STRICT=PRIVATE/'whole_archive'
OUT=REV/'strict_region_holdout'
KEY=['family','mode','station_key','replicate','method']
ANNUAL_KEY=['family','mode','station_key','replicate','year']


def run_pair(oldpath,truth,jobs,old_limits,new_limits):
    rel=oldpath.relative_to(ORIGINAL)
    newpath=STRICT/rel
    if not newpath.is_file():raise ValueError('strict annual prediction is missing')
    olddesign=json.loads((oldpath.parent/'design.json').read_text())
    newdesign=json.loads((newpath.parent/'design.json').read_text())
    if olddesign['masks']!=newdesign['masks'] or olddesign['station_key']!=newdesign['station_key'] or newdesign['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('strict archive masks or hidden values differ')
    oldc=pd.read_parquet(oldpath);newc=pd.read_parquet(newpath)
    a=oldc[['year','mask_runs']].sort_values('year').reset_index(drop=True)
    b=newc[['year','mask_runs']].sort_values('year').reset_index(drop=True)
    if not a.equals(b):raise ValueError('masked-year cases differ')
    m=T.load_script('strict_integrated_worker',ROOT/'scripts/532_integrated_release_trend.py')
    m.ARCHIVE=ORIGINAL;old,annual_old=m.one(oldpath,truth,jobs,old_limits)
    m.ARCHIVE=STRICT;new,annual_new=m.one(newpath,truth,jobs,new_limits)
    return old,new,annual_old,annual_new


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--limit',type=int,help='pilot number of settings, no pooled results')
    args=parser.parse_args()
    if json.loads((OUT/'archive_sensitivity_status.json').read_text())['archive_settings']!=120:raise RuntimeError('full strict archive input required')
    output=OUT if args.limit is None else OUT/f'integrated_pilot_{args.limit}'
    private_out=PRIVATE/'integrated_release' if args.limit is None else PRIVATE/f'integrated_release_pilot_{args.limit}'
    output.mkdir(parents=True,exist_ok=True);private_out.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (output/'integrated_release_status.json').exists():raise RuntimeError('existing completed results are preserved')
    source=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','eval_truth_h30'])
    truth={(family,station):g.drop_duplicates('year').set_index('year').eval_truth_h30.sort_index() for (family,station),g in source.groupby(['design_family','station_key'])}
    core=T.load_script('strict_integrated_jobs',ROOT/'scripts/431_tr_cases.py');jobs={j['station_key']:j for j in core.jobs_for('source')}
    old_limits=json.loads((REV/'release_outputs/design.json').read_text())['limits_by_training_split_and_held_region']
    new_limits=copy.deepcopy(old_limits)
    gate=pd.read_csv(OUT/'future_gate_limits.csv')
    for row in gate.itertuples(index=False):new_limits['before_2010'][row.region][row.feature]=float(row.strict_limit)
    paths=sorted(ORIGINAL / p.relative_to(STRICT) for p in STRICT.glob('*/forward/replicate_*/*/annual_predictions.parquet'))
    if len(paths)!=120:raise ValueError('unexpected strict archive settings')
    if args.limit is not None:paths=paths[:args.limit]
    print('Replaying original and strict release-to-trend settings:',len(paths),flush=True)
    pairs=Parallel(n_jobs=args.workers,verbose=10)(delayed(run_pair)(p,truth,jobs,old_limits,new_limits) for p in paths)
    old=pd.DataFrame([r for x in pairs for r in x[0]]);new=pd.DataFrame([r for x in pairs for r in x[1]])
    annual_old=pd.concat([x[2] for x in pairs],ignore_index=True);annual_new=pd.concat([x[3] for x in pairs],ignore_index=True)
    saved=pd.read_csv(REV/'integrated_release_trend/station_repetitions.csv')
    saved_annual=pd.read_parquet(REV/'integrated_release_trend/annual_decisions.parquet')
    compare=old.merge(saved,on=KEY,how='left',suffixes=('_replayed','_saved'),indicator=True,validate='one_to_one')
    if not compare._merge.eq('both').all():raise ValueError('original integrated settings not found')
    for field in ['available','n_masked','n_estimates','n_bounds','n_unknown']:
        if not compare[field+'_replayed'].eq(compare[field+'_saved']).all():raise ValueError('original replay mismatch: '+field)
    for field in ['truth_slope','slope','error','squared_error','total_working_coverage95','total_working_width95','total_working_interval_score95']:
        if field+'_replayed' in compare and not np.allclose(pd.to_numeric(compare[field+'_replayed'],errors='coerce'),pd.to_numeric(compare[field+'_saved'],errors='coerce'),rtol=0,atol=1e-8,equal_nan=True):raise ValueError('original replay numeric mismatch: '+field)
    check=annual_old.merge(saved_annual,on=ANNUAL_KEY,how='left',suffixes=('_replayed','_saved'),indicator=True,validate='one_to_one')
    if not check._merge.eq('both').all() or not check.output_state_replayed.eq(check.output_state_saved).all():raise ValueError('original annual release states do not replay')
    for field in ['released_estimate','observed_lower_bound','quality_flag','eval_reference_h30']:
        if not np.allclose(pd.to_numeric(check[field+'_replayed'],errors='coerce'),pd.to_numeric(check[field+'_saved'],errors='coerce'),rtol=0,atol=1e-8,equal_nan=True):raise ValueError('original annual replay differs: '+field)
    paired=old.merge(new,on=KEY,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
    if not paired._merge.eq('both').all() or not np.allclose(paired.truth_slope_original,paired.truth_slope_strict,atol=1e-12,rtol=0):raise ValueError('strict trend cohort or truth differs')
    ann=annual_old.merge(annual_new,on=ANNUAL_KEY,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
    if not ann._merge.eq('both').all():raise ValueError('strict annual years differ')
    for field in ['quality_flag','eval_reference_h30','observed_lower_bound']:
        if not np.allclose(pd.to_numeric(ann[field+'_original'],errors='coerce'),pd.to_numeric(ann[field+'_strict'],errors='coerce'),atol=1e-8,rtol=0,equal_nan=True):raise ValueError('quality, truth or visible bounds differ: '+field)
    transition=pd.crosstab(ann.output_state_original,ann.output_state_strict,dropna=False)
    transition.to_csv(output/'integrated_state_transitions.csv')
    # Materialize restricted strict results for traceability; aggregate results only are public.
    new.to_csv(private_out/'strict_station_repetitions.csv',index=False)
    annual_new.to_parquet(private_out/'strict_annual_decisions.parquet',index=False)
    if args.limit is None:
        affected=saved[KEY].merge(new[KEY],on=KEY,how='left',indicator=True,validate='one_to_one')._merge.eq('both').to_numpy()
        combined=pd.concat([saved.loc[~affected],new],ignore_index=True)
        pooled=saved.loc[saved['mode'].eq('forward')].merge(combined.loc[combined['mode'].eq('forward')],on=KEY,how='outer',suffixes=('_original','_strict'),indicator=True,validate='one_to_one')
        if not pooled._merge.eq('both').all():raise ValueError('pooled keys differ')
    else:pooled=paired
    rows=[]
    for scope,frame in [('affected',paired),('pooled_forward',pooled)]:
      for (family,method),g in frame.groupby(['family','method'],sort=True):
        common=g.available_original & g.available_strict
        row={'scope':scope,'family':family,'method':method,'n_eligible':len(g),'n_stations':g.station_key.nunique(),
             'original_available':int(g.available_original.sum()),'strict_available':int(g.available_strict.sum()),'n_common':int(common.sum())}
        for label in ['original','strict']:
            h=g.loc[common]
            row[label+'_rmse']=float(np.sqrt(h['squared_error_'+label].mean())) if len(h) else np.nan
            row[label+'_bias']=float(h['error_'+label].mean()) if len(h) else np.nan
            for field in ['total_working_coverage95','total_working_width95','total_working_interval_score95']:
                if field+'_'+label in h:row[label+'_'+field]=float(pd.to_numeric(h[field+'_'+label],errors='coerce').mean())
        rows.append(row)
    summary=pd.DataFrame(rows);summary.to_csv(output/'integrated_paired_summary.csv',index=False)
    state={'status':'passed' if args.limit is None else 'pilot_passed','affected_archive_settings':len(paths),'station_repetition_rows':len(paired),
       'original_annual_rows_replayed':len(check),'original_states_mismatched':0,'same_target_mask_truth_and_quality':True,
       'strict_regions':'HUC17 in forward whole-archive; other regional results unchanged',
       'scope':'post-hoc sensitivity of same archive masks and evaluated finite-record trends; source training size changes',
       'limitation':'not independent climate validation; working-likelihood intervals include regression variation and are not calibrated missingness-only uncertainty; does not rerun every source analysis'}
    (output/'integrated_release_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(summary.to_string(index=False));print(transition.to_string());print(json.dumps(state,indent=2))
if __name__=='__main__':main()
