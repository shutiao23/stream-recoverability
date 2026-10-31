#!/usr/bin/env python3
"""Independently re-evaluate fixed source thresholds on saved held-region cases."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/release_outputs'


def main():
    target=pd.read_parquet(OUT/'clean.parquet')
    thresholds=pd.read_csv(OUT/'source_rule_thresholds.csv')
    if thresholds.duplicated(['region','family']).any():raise ValueError('duplicate source thresholds')
    c=target.merge(thresholds[['region','family','score_cutoff']],left_on=['region','design_family'],
                   right_on=['region','family'],how='left',indicator=True,validate='many_to_one')
    missing=int(c._merge.ne('both').sum())
    if missing:raise RuntimeError(f'{missing} held cases lack a source-derived threshold')
    saved=pd.read_csv(OUT/'source_calibrated_release_summary.csv');rows=[];mismatches=[]
    for (family,method),r in saved.groupby(['family','method']):
        if len(r)!=1:raise ValueError('nonunique summary row')
        row=r.iloc[0];b=c.loc[c.design_family.eq(family)]
        keep=(b.output.eq('estimate') if method=='three_outputs' else (b.risk_score.le(b.score_cutoff)&b.D2.notna()))
        bad=(b.D2-b.eval_truth_h30).abs().gt(.5)
        got={'n_eligible':len(b),'n_published':int(keep.sum()),'n_bad':int((keep&bad).sum())}
        for k,v in got.items():
            if int(row[k])!=v:mismatches.append(f'{family}/{method}/{k}: {row[k]} vs {v}')
        rows.append(dict(family=family,method=method,**got))
    group=pd.read_csv(OUT/'source_calibrated_group_availability.csv')
    bootstrap=[]
    for family,b in group.groupby('design_family'):
        g=b.groupby('independence_group')[['n','score_kept','three_kept','score_bad','three_bad']].sum()
        rng=np.random.default_rng(559);draws=rng.integers(0,len(g),size=(2000,len(g)))
        sums={k:g[k].to_numpy()[draws].sum(axis=1) for k in g.columns}
        valid=(sums['score_kept']>0)&(sums['three_kept']>0)
        ret=(sums['three_kept']-sums['score_kept'])/sums['n']
        risk=sums['three_bad'][valid]/sums['three_kept'][valid]-sums['score_bad'][valid]/sums['score_kept'][valid]
        for metric,values in [('retention_difference',ret),('conditional_error_difference',risk)]:
            lo,hi=np.quantile(values,[.025,.975]) if len(values) else (np.nan,np.nan)
            bootstrap.append(dict(family=family,metric=metric,lower=float(lo),upper=float(hi),valid_draws=len(values),groups=len(g)))
    pd.DataFrame(bootstrap).to_csv(OUT/'source_calibrated_group_bootstrap.csv',index=False)
    max_gap=float((thresholds.source_three_rate-thresholds.source_score_rate).abs().max())
    result=dict(n_target_cases=len(c),n_source_thresholds=len(thresholds),n_held_region_families=c[['region','design_family']].drop_duplicates().shape[0],
                missing_threshold_cases=missing,min_source_calibration_groups=int(thresholds.source_groups.min()),
                max_source_retention_gap=max_gap,
                summary_mismatches=mismatches,passed=not mismatches and missing==0,
                caveat='Checks target application and denominator; does not by itself validate role assignment, prospective transfer or reference quality.')
    (OUT/'source_calibrated_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
