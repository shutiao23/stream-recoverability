#!/usr/bin/env python3
"""Attach separately recorded reference H30 after target selections are fixed.

The first scoring pass found no usable reference values in the annual model
cache. Preserve that pass and join the full-archive reference by explicit case
identity, checking against the original source station/year/family values.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('projected_risk_reference_inputs',ROOT/'scripts/701_projected_risk_fit.py')
SOURCE=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
ANNUAL=M.REV/'integrated_release_trend/annual_decisions.parquet'
KEY=['family','station_key','replicate','year']

def freeze():
    M.verify_source_freeze()
    amendment=M.OUT/'reference_score_amendment.json'
    if amendment.exists():raise FileExistsError('Reference scoring amendment already exists')
    target=M.PRIVATE/'target_scores.parquet';frame=pd.read_parquet(target)
    if np.isfinite(frame.reference_h30.to_numpy(float)).any():raise ValueError('Initial target reference is not empty')
    old_summary=pd.read_csv(M.OUT/'summary.csv')
    if not old_summary.n_reference_evaluable.eq(0).all():raise ValueError('Initial summary is not the unscored pass')
    archive=M.PRIVATE/'target_scores_unscored.parquet'
    if archive.exists():raise FileExistsError('Unscored selection snapshot already exists')
    shutil.copyfile(target,archive)
    for name in ['summary.csv','leave_region_out.csv','status.json']:
        shutil.copyfile(M.OUT/name,M.OUT/('unscored_'+name))
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc correction after finding candidate prediction cache contains no reference values',
          'selection':'The source classifiers, source cutoffs, target scores, source-threshold selections and deterministic per-region count matches were already saved; none used target reference values.',
          'reference':'Attach the separately recorded original full-archive H30 by family, station, replicate and year; independently compare with original source station-year-family truth. No threshold or target selection is changed.',
          'limitations':'Original source and target datasets and previous study results were already inspected; this is not an unopened prospective reference or a risk-control guarantee.',
          'masked_cases':len(frame)}
    amendment.write_text(json.dumps(plan,indent=2)+'\n')
    print('Preserved unscored target decisions; reference attachment frozen',flush=True)

def attach_reference(target,annual,source):
    if target.duplicated(KEY).any():raise ValueError('Duplicate target decisions')
    annual=annual[annual['mode'].eq('forward')&annual.output_state.ne('complete_observed')].copy()
    if annual.duplicated(KEY).any():raise ValueError('Duplicate archived reference identity')
    annual=annual[KEY+['region','independence_group','eval_reference_h30']]
    joined=target.merge(annual,on=KEY,how='outer',suffixes=('','_annual'),indicator=True,validate='one_to_one')
    if not joined._merge.eq('both').all():raise ValueError('Target selection and original masked-year cohorts differ')
    if not joined.region.eq(joined.region_annual).all() or not joined.independence_group.eq(joined.independence_group_annual).all():
        raise ValueError('Reference region or connected group differs')
    reference=joined.eval_reference_h30.to_numpy(float)
    if not np.isfinite(reference).all():raise ValueError('Missing full-archive reference H30')
    identity=['family','station_key','year']
    g=source.groupby(identity,dropna=False).eval_truth_h30.agg(['min','max','count'])
    if g['count'].eq(0).any() or (g['max']-g['min']).abs().gt(1e-10).any():
        raise ValueError('Source station/year/family reference is absent or nonunique')
    original=g['min'].rename('source_truth').reset_index()
    joined=joined.drop(columns=['_merge']).merge(original,on=identity,how='left',validate='many_to_one',indicator=True)
    if not joined._merge.eq('both').all() or not np.allclose(joined.eval_reference_h30,joined.source_truth,atol=1e-10,rtol=0):
        raise ValueError('Archived and source reference H30 differ')
    joined['reference_h30']=joined.eval_reference_h30.to_numpy(float)
    return joined.drop(columns=['region_annual','independence_group_annual','eval_reference_h30','source_truth','_merge'])

def score():
    M.verify_source_freeze()
    plan=json.loads((M.OUT/'reference_score_amendment.json').read_text())
    if (M.OUT/'reference_score_status.json').exists():raise FileExistsError('Reference scoring already completed')
    target=pd.read_parquet(M.PRIVATE/'target_scores_unscored.parquet')
    annual=pd.read_parquet(ANNUAL,columns=KEY+['mode','output_state','region','independence_group','eval_reference_h30'])
    source=pd.read_parquet(SOURCE,columns=['station_key','year','design_family','eval_truth_h30']).rename(columns={'design_family':'family'})
    scored=attach_reference(target,annual,source)
    before=target.set_index(KEY).sort_index();after=scored.set_index(KEY).sort_index()
    for col in ['D2','original_score','projected_score','common_predictable','original_selected','projected_selected','matched_projected_selected']:
        if not before[col].equals(after[col]):raise ValueError('Selection or prediction changed when attaching truth: '+col)
    if len(scored)!=plan['masked_cases']:raise ValueError('Masked target denominator changed')
    scored.to_parquet(M.PRIVATE/'target_scores.parquet',index=False)
    summary,region=M.metric_summary(scored)
    summary.to_csv(M.OUT/'summary.csv',index=False);region.to_csv(M.OUT/'leave_region_out.csv',index=False)
    status={'status':'computed_with_separately_verified_reference','target_masked_cases':len(scored),
            'target_archives':1640,'reference_available':int(np.isfinite(scored.reference_h30).sum()),
            'reference_used_to_choose_threshold_or_match':False,'source_models_and_cutoffs_frozen_first':True,
            'unscored_first_pass_preserved':True,'group_count':int(scored.independence_group.nunique()),
            'limitations':'Post-hoc, previously opened source and target archives. Scores, source cutoffs and target count matching preceded this reference join. Repeated masks and group correlations do not establish prospective risk or independent-climate transfer.'}
    (M.OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    (M.OUT/'reference_score_status.json').write_text(json.dumps({'status':'passed','masked_cases':len(scored),
        'archived_and_source_reference_equal':True,'predictions_and_decisions_unchanged':True,
        'unscored_first_pass_preserved':True},indent=2)+'\n')
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','score']);a=p.parse_args()
    freeze() if a.action=='freeze' else score()
