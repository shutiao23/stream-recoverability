#!/usr/bin/env python3
"""Repair a view-mutation error in post-hoc group-max summary denominators."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/groupmax_annual_calibration'
PRIVATE=ROOT/'private/wrr_groupmax_annual_calibration_20261027'

def summarize(data):
    summaries=[];loo=[];rng=np.random.default_rng(720)
    for (family,estimator),all_cases in data.groupby(['family','estimator'],sort=True):
      for stratum in ['all','unobserved_peak_excess']:
       subset=all_cases if stratum=='all' else all_cases[all_cases.stratum.eq(stratum)]
       for scope in ['both_groupmax_supported','both_groupmax_and_empirical_supported']:
        # A separate copy is essential: applying the empirical flag in-place
        # must never change the stored group-max support flag for later strata.
        mask=subset.both_groupmax_supported.to_numpy(dtype=bool,copy=True)
        if scope=='both_groupmax_and_empirical_supported':mask &= subset.both_empirical_supported.to_numpy(bool)
        g=subset.loc[mask].copy();groups=sorted(g.independence_group_old.unique())
        row={'family':family,'estimator':estimator,'stratum':stratum,'scope':scope,'n_eligible':len(subset),
             'n_supported':len(g),'availability':len(g)/len(subset) if len(subset) else np.nan,
             'stations':g.station_key.nunique(),'groups':len(groups)}
        for version in ['baseline','groupmax']+(['empirical'] if scope=='both_groupmax_and_empirical_supported' else []):
            for metric in ['coverage90','width90','interval_score90']:
                row[version+'_'+metric]=float(g[version+'_'+metric].mean()) if len(g) else np.nan
            group_all=g.groupby('independence_group_old')[version+'_coverage90'].min()
            row[version+'_groups_all_cases_covered']=int(group_all.sum())
        if len(groups):
            labels=g.independence_group_old.to_numpy();draw=rng.integers(len(groups),size=(4000,len(groups)))
            for metric in ['coverage90','width90','interval_score90']:
                delta=(g['groupmax_'+metric]-g['baseline_'+metric]).to_numpy(float)
                total=np.array([delta[labels==group].sum() for group in groups]);sizes=np.array([(labels==group).sum() for group in groups])
                sample=total[draw].sum(axis=1)/sizes[draw].sum(axis=1)
                row[metric+'_difference_group_equal']=float(np.mean(total/sizes))
                row[metric+'_difference_ci_low']=float(np.quantile(sample,.025))
                row[metric+'_difference_ci_high']=float(np.quantile(sample,.975))
        summaries.append(row)
        for region in sorted(g.region.unique()):
            remain=g[g.region.ne(region)]
            loo.append({'family':family,'estimator':estimator,'stratum':stratum,'scope':scope,'removed_region':region,
                        'n_supported':len(remain),'groups':remain.independence_group_old.nunique(),
                        **{metric+'_difference':float((remain['groupmax_'+metric]-remain['baseline_'+metric]).mean()) if len(remain) else np.nan
                           for metric in ['coverage90','width90','interval_score90']}})
    return pd.DataFrame(summaries),pd.DataFrame(loo)

def freeze():
    note=OUT/'summary_correction.json'
    if note.exists():raise FileExistsError('Summary correction already recorded')
    target=PRIVATE/'target_scores.parquet';evidence=pd.read_parquet(target)
    expected=(evidence.family.eq('crossed') & evidence.estimator.eq('D2') & evidence.stratum.eq('unobserved_peak_excess'))
    stored=pd.read_csv(OUT/'summary.csv')
    row=stored[(stored.family=='crossed')&(stored.estimator=='D2')&(stored.stratum=='unobserved_peak_excess')&(stored.scope=='both_groupmax_supported')]
    if len(row)!=1 or int(row.iloc[0].n_supported)==int((expected & evidence.both_groupmax_supported).sum()):
        raise ValueError('Expected denominator discrepancy is not present')
    for name in ['summary.csv','leave_region_out.csv','status.json']:
        dest=OUT/('before_correction_'+name)
        if dest.exists():raise FileExistsError('Prior summary archive already exists')
        shutil.copyfile(OUT/name,dest)
    record={'created_utc':datetime.now(timezone.utc).isoformat(),
            'problem':'The initial summary reused an in-place NumPy view of the group-max support flag when restricting to the earlier empirical method; this incorrectly carried that restriction into later strata.',
            'change':'Use an independent Boolean copy for each summary scope. Source radii, numerical intervals and per-case target scores are unchanged; recompute all summary cells and group resamples.',
            'timing':'The original aggregate and source radii had already been inspected; this is a transparent post-hoc correctness repair, not an unopened analysis.',
            }
    note.write_text(json.dumps(record,indent=2)+'\n')
    print('Preserved erroneous summary and froze denominator correction',flush=True)

def repair():
    correction=json.loads((OUT/'summary_correction.json').read_text())
    data=pd.read_parquet(PRIVATE/'target_scores.parquet')
    original=data[['both_groupmax_supported','both_empirical_supported']].copy()
    summary,loo=summarize(data)
    pd.testing.assert_frame_equal(original,data[['both_groupmax_supported','both_empirical_supported']])
    summary.to_csv(OUT/'summary.csv',index=False);loo.to_csv(OUT/'leave_region_out.csv',index=False)
    previous=json.loads((OUT/'before_correction_status.json').read_text())
    previous.update(summary_denominator_corrected=True,source_radii_and_target_scores_unchanged=True,
                    correction='See summary_correction.json; initial aggregate preserved.')
    (OUT/'status.json').write_text(json.dumps(previous,indent=2)+'\n')
    print(summary[(summary.family=='crossed')&(summary.stratum.isin(['all','unobserved_peak_excess']))].to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','repair']);a=p.parse_args()
    freeze() if a.action=='freeze' else repair()
