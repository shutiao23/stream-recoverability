#!/usr/bin/env python3
"""Calibrate a score-only release threshold on independent source-rule groups.

For each held-out region and mask family, use only that model's source
rule-calibration groups to match the three-output rule's source release rate.
Apply that threshold without label or retention tuning in the held region. The
resulting target retention may differ. Outputs are descriptive, not risk bounds.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.outputs import release_states
from stream_recoverability.seeds import plain_seed

SOURCE=T.ROOT/'results/wrr_review_completion_20261024'
OUT=T.ROOT/'results/wrr_review_response_20261027/release_outputs'
KEY=['network_id','station_key','year','design_family','realization_id']


def fit_threshold(score, valid, weights, desired):
    """Nearest attainable weighted output rate, with ties admitted together."""
    score=np.asarray(score,float);valid=np.asarray(valid,bool)&np.isfinite(score);weights=np.asarray(weights,float)
    if np.any(weights<0) or not np.isfinite(weights).all() or weights.sum()<=0:raise ValueError('invalid calibration weights')
    order=np.flatnonzero(valid & (weights>0));order=order[np.argsort(score[order],kind='stable')]
    if not len(order):return None,0.0
    end=np.r_[score[order][1:]!=score[order][:-1],True]
    last=np.flatnonzero(end);coverage=np.cumsum(weights[order])[last]/weights.sum()
    # Empty selection is permitted; never break equal-score ties using labels.
    candidates=np.r_[0.,coverage];i=int(np.argmin(abs(candidates-desired)))
    return (None,0.0) if i==0 else (float(score[order[last[i-1]]]),float(candidates[i]))


def main():
    refit=T.load_script('retention_source_roles',T.ROOT/'scripts/466_review_completion_refit.py')
    infer=T.load_script('retention_source_prediction',T.ROOT/'scripts/495_review_completion_independent_analysis.py')
    c=pd.read_parquet(SOURCE/'cases/leave_one_year_out/seed_00.parquet')
    c=c.loc[c.policy_choice.ne('unavailable')&c.eval_truth_h30.notna()].reset_index(drop=True)
    source_quality=pd.read_parquet(OUT/'clean.parquet',columns=KEY+['agreement7'])
    if c.duplicated(KEY).any() or source_quality.duplicated(KEY).any():raise ValueError('nonunique quality keys')
    source_index=pd.MultiIndex.from_frame(source_quality[KEY]); query=pd.MultiIndex.from_frame(c[KEY])
    if not query.isin(source_index).all():raise ValueError('missing source visible-quality diagnostic cases')
    c['agreement7']=pd.Series(source_quality.agreement7.to_numpy(),index=source_index).reindex(query).to_numpy()
    design=json.loads((OUT/'design.json').read_text());limits=design['limits_by_training_split_and_held_region']['leave_one_year_out']
    target=pd.read_parquet(OUT/'clean.parquet');regions=sorted(c.region.unique());thresholds=[];target_rows=[]
    for i,region in enumerate(regions):
        _,roles,weights=refit.roles(c,region,plain_seed(7,0,i))
        bundle=joblib.load(SOURCE/'refits/leave_one_year_out/seed_00'/f'{region}.joblib')
        if roles!=bundle['roles']:raise RuntimeError(f'Role mismatch in {region}')
        mask=weights['rule_calibration']>0
        subset=c.loc[mask].copy();w=weights['rule_calibration'][mask]
        if set(subset.independence_group)&set(c.loc[c.region.eq(region),'independence_group']):
            raise RuntimeError(f'Calibration group overlaps held region: {region}')
        pred=infer.predict(subset,bundle)
        pred['output']=release_states(pred,limits[region],pred.agreement7.le(.05))
        held=target.loc[target.region.eq(region)]
        for family,cal in pred.groupby('design_family'):
            fam=pred.design_family.eq(family).to_numpy();fw=w[fam]
            if not len(cal) or fw.sum()<=0:continue
            desired=float(np.dot(fw,cal.output.eq('estimate').to_numpy())/fw.sum())
            threshold,rate=fit_threshold(cal.risk_score,cal.D2.notna(),fw,desired)
            thresholds.append(dict(region=region,family=family,source_groups=cal.independence_group.nunique(),
                                   source_cases=len(cal),weighted_source_cases=float(fw.sum()),
                                   source_three_rate=desired,source_score_rate=rate,score_cutoff=threshold))
            test=held.loc[held.design_family.eq(family)].copy()
            if test.empty:continue
            test['score_only']=test.risk_score.le(threshold)&test.D2.notna() if threshold is not None else False
            test['three_outputs']=test.output.eq('estimate')
            test['bad']=(test.D2-test.eval_truth_h30).abs().gt(.5)
            test['score_bad']=test.score_only & test.bad
            test['three_bad']=test.three_outputs & test.bad
            target_rows.append(test[['region','independence_group','design_family','score_only','three_outputs','bad','score_bad','three_bad']])
        print(f'calibrated {region}',flush=True)
    pd.DataFrame(thresholds).to_csv(OUT/'source_rule_thresholds.csv',index=False)
    if not target_rows:raise RuntimeError('No eligible held-out evaluation cases')
    data=pd.concat(target_rows,ignore_index=True)
    original=target.groupby(['region','design_family']).size().sort_index()
    observed=data.groupby(['region','design_family']).size().sort_index()
    if not original.equals(observed):
        raise RuntimeError('A target-region/family denominator is missing or differs')
    rows=[]
    for family,b in data.groupby('design_family'):
        for method in ['three_outputs','score_only']:
            keep=b[method].to_numpy(bool);bad=b.bad.to_numpy(bool);n=int(keep.sum());n_bad=int((keep&bad).sum())
            rows.append(dict(family=family,method=method,n_eligible=len(b),n_published=n,
                             retention=n/len(b),n_bad=n_bad,risk=n_bad/n if n else np.nan,
                             regions=b.region.nunique(),groups=b.independence_group.nunique()))
    summary=pd.DataFrame(rows);summary.to_csv(OUT/'source_calibrated_release_summary.csv',index=False)
    data.groupby(['region','design_family','independence_group']).agg(n=('bad','size'),
        score_kept=('score_only','sum'),three_kept=('three_outputs','sum'),
        score_bad=('score_bad','sum'),three_bad=('three_bad','sum')).reset_index().to_csv(OUT/'source_calibrated_group_availability.csv',index=False)
    (OUT/'source_calibrated_release_design.json').write_text(json.dumps({
       'scope':'clean retrospective source experiment, one existing model seed; group-disjoint source rule calibration for each held region and family',
       'calibration':'source bootstrap-weighted score threshold chosen without failure labels to approximately match source three-output numerical retention; ties admitted together',
       'target':'apply fixed source-derived threshold in held region, no target labels or target retention used for tuning',
       'comparison':'same D2 estimates and case population, but target numerical retention need not match and bounds/unknowns differ',
       'limitations':'model/thresholds are exploratory, source groups do not imply independent climates, and results are not a risk guarantee or natural-outage validation'},indent=2)+'\n')
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':main()
