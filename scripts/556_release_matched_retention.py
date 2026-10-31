#!/usr/bin/env python3
"""Compare release rules at identical empirical numerical-output counts.

The score-only cutoff is chosen on the evaluated feature distribution to match
the number actually released by the three-output rule, without using labels.
This is a transductive descriptive comparison, not a prospective operating
rule, a risk guarantee, or equal total information: withheld cases can retain
bounds or become unknown under the original three-output rule.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/release_outputs'
KEY=['network_id','station_key','year','design_family','realization_id']
CONDITIONS=['clean','hot_year_extrapolation','future_years','air_exposure','smooth_non_air_shift']


def select_score_only(frame, n):
    """Admit exactly n finite, eligible scores, resolving ties by case identity."""
    if frame.duplicated(KEY).any():raise ValueError('nonunique case identities')
    eligible=frame.risk_score.notna() & frame.D2.notna()
    positions=np.flatnonzero(eligible.to_numpy())
    if n<0 or n>len(positions):raise ValueError('requested numerical count is infeasible')
    answer=np.zeros(len(frame),dtype=bool)
    if n==0:return answer, np.nan, 0
    rank=frame.iloc[positions][KEY+['risk_score']].copy()
    rank['tie_key']=pd.util.hash_pandas_object(rank[KEY],index=False).to_numpy(dtype='uint64')
    rank['position']=positions
    rank=rank.sort_values(['risk_score','tie_key']+KEY,kind='mergesort')
    answer[rank.position.iloc[:n].to_numpy(dtype=int)]=True
    cutoff=float(rank.risk_score.iloc[n-1]);tied=int(rank.risk_score.eq(cutoff).sum())
    return answer,cutoff,tied


def evaluate(frame, bootstrap=2000, seed=556):
    if frame.independence_group.isna().any():raise ValueError('missing group labels')
    truth=frame.eval_truth_h30.to_numpy(float); point=frame.D2.to_numpy(float)
    if not np.isfinite(truth).all():raise ValueError('missing target truth in evaluation cohort')
    actual=frame.output.eq('estimate').to_numpy()
    if np.any(actual & ~np.isfinite(point)):raise ValueError('released nonfinite point')
    baseline,cutoff,tied=select_score_only(frame,int(actual.sum()))
    bad=np.isfinite(point)&(abs(point-truth)>.5)
    base_error=int(np.sum(baseline & bad)); actual_error=int(np.sum(actual & bad));n=int(actual.sum())
    group=pd.DataFrame({'group':frame.independence_group.to_numpy(),'baseline_kept':baseline.astype(int),
                        'actual_kept':actual.astype(int),'baseline_bad':(baseline & bad).astype(int),
                        'actual_bad':(actual & bad).astype(int)})
    by=group.groupby('group',sort=True).sum()
    rng=np.random.default_rng(seed);draws=rng.integers(0,len(by),size=(bootstrap,len(by)))
    ab=by.actual_bad.to_numpy()[draws].sum(axis=1);ak=by.actual_kept.to_numpy()[draws].sum(axis=1)
    bb=by.baseline_bad.to_numpy()[draws].sum(axis=1);bk=by.baseline_kept.to_numpy()[draws].sum(axis=1)
    valid=(ak>0)&(bk>0); diff=ab[valid]/ak[valid]-bb[valid]/bk[valid]
    lo,hi=np.quantile(diff,[.025,.975]) if len(diff) else (np.nan,np.nan)
    summary=dict(n_eligible=len(frame),n_equal_numerical=n,retention=n/len(frame) if len(frame) else np.nan,
                 n_groups=len(by),score_cutoff=cutoff,n_at_cutoff=tied,n_selected_with_tied_score=int(np.sum(baseline & frame.risk_score.eq(cutoff).to_numpy())) if n else 0,
                 three_output_bad=actual_error,score_only_bad=base_error,
                 three_output_risk=actual_error/n if n else np.nan,score_only_risk=base_error/n if n else np.nan,
                 risk_difference=(actual_error-base_error)/n if n else np.nan,
                 three_only=int(np.sum(actual & ~baseline)),score_only=int(np.sum(baseline & ~actual)),
                 uncertainty_low=float(lo),uncertainty_high=float(hi),bootstrap_valid=int(valid.sum()),bootstrap_draws=bootstrap)
    return summary,by.reset_index()


def main():
    rows=[];groups=[]
    for condition in CONDITIONS:
        data=pd.read_parquet(OUT/(condition+'.parquet'))
        for family,frame in data.groupby('design_family',sort=True):
            summary,by=evaluate(frame)
            rows.append(dict(condition=condition,family=family)|summary)
            groups.append(by.assign(condition=condition,family=family))
    summary=pd.DataFrame(rows);summary.to_csv(OUT/'matched_numerical_retention.csv',index=False)
    pd.concat(groups,ignore_index=True).to_csv(OUT/'matched_retention_groups.csv',index=False)
    (OUT/'matched_retention_design.json').write_text(json.dumps({
        'goal':'compare empirical failure among equally many numerical outputs, same D2 predictions and same evaluation cases',
        'baseline':'rank finite raw individual classifier scores ascending, tie-break deterministically using case identifiers; set exact count equal to three-output rule',
        'threshold_source':'evaluated unlabeled feature distribution and three-output count; transductive descriptive comparison, not a prospective threshold or risk control',
        'outcome':'absolute D2 error greater than 0.5 C compared with available reference; no use of labels for cutoff or tie selection',
        'limitations':'same numeric count is not equivalent to equal information: three-output lower-bound/unknown states and source-selected sample matter; artificial scenarios have unknown prevalence',
        'bootstrap':'2000 connected-group resamples; conditional risk difference in resampled groups, descriptive only; one model seed and group/climate exchangeability uncertain'},indent=2)+'\n')
    print(summary.to_string(index=False))

if __name__=='__main__':main()
