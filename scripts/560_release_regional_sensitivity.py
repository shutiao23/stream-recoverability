#!/usr/bin/env python3
"""Regional and connected-group sensitivity for fixed source-calibrated rules.

All model fits and thresholds remain frozen; removing a region here removes
its evaluation cases only, not its data from other regions' source training.
Cases with zero numerical outputs have undefined conditional error, not zero.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/release_outputs'
COUNTS=['n','score_kept','three_kept','score_bad','three_bad']


def rates(frame):
    x=frame.copy()
    x['score_retention']=x.score_kept/x.n
    x['three_retention']=x.three_kept/x.n
    x['score_error']=x.score_bad/x.score_kept.where(x.score_kept.gt(0))
    x['three_error']=x.three_bad/x.three_kept.where(x.three_kept.gt(0))
    x['retention_difference']=x.three_retention-x.score_retention
    x['conditional_error_difference']=x.three_error-x.score_error
    return x


def summarize(raw):
    if raw[['region','design_family','independence_group']].isna().any().any():raise ValueError('missing identifiers')
    if raw.duplicated(['region','design_family','independence_group']).any():raise ValueError('duplicate group rows')
    if (raw[COUNTS]<0).any().any() or (raw.score_kept>raw.n).any() or (raw.three_kept>raw.n).any():raise ValueError('invalid counts')
    if (raw.score_bad>raw.score_kept).any() or (raw.three_bad>raw.three_kept).any():raise ValueError('failure counts exceed published counts')
    region=rates(raw.groupby(['design_family','region'],as_index=False)[COUNTS].sum())
    group=rates(raw.groupby(['design_family','independence_group'],as_index=False)[COUNTS].sum())
    leave=[];equal=[];directions=[]
    for family,reg in region.groupby('design_family',sort=True):
        total=reg[COUNTS].sum()
        for r in reg.itertuples():
            remain=total-pd.Series({k:getattr(r,k) for k in COUNTS})
            if remain.n<=0:continue
            d=rates(pd.DataFrame([remain]))
            leave.append(dict(design_family=family,excluded_region=r.region,**d.iloc[0].to_dict()))
        g=group.loc[group.design_family.eq(family)].copy()
        common=g.score_kept.gt(0)&g.three_kept.gt(0)
        paired=g.loc[common]
        equal.append(dict(design_family=family,n_groups=len(g),n_both_defined=int(common.sum()),
                          n_score_zero=int(g.score_kept.eq(0).sum()),n_three_zero=int(g.three_kept.eq(0).sum()),
                          score_mean_group_error=float(paired.score_error.mean()) if len(paired) else np.nan,
                          three_mean_group_error=float(paired.three_error.mean()) if len(paired) else np.nan,
                          group_mean_error_difference=float(paired.conditional_error_difference.mean()) if len(paired) else np.nan))
        defined=reg.conditional_error_difference.notna()
        d=reg.loc[defined,'conditional_error_difference']
        directions.append(dict(design_family=family,n_regions=len(reg),n_both_defined=int(defined.sum()),
                               n_three_higher=int(d.gt(1e-12).sum()),n_three_lower=int(d.lt(-1e-12).sum()),
                               n_equal=int(d.abs().le(1e-12).sum()),n_undefined=int((~defined).sum())))
    return region,group,pd.DataFrame(leave),pd.DataFrame(equal),pd.DataFrame(directions)


def main():
    raw=pd.read_csv(OUT/'source_calibrated_group_availability.csv')
    region,groups,leave,equal,directions=summarize(raw)
    saved=pd.read_csv(OUT/'source_calibrated_release_summary.csv')
    for family,block in raw.groupby('design_family'):
        totals=block[COUNTS].sum()
        for label,prefix in [('three_outputs','three'),('score_only','score')]:
            row=saved.loc[saved.family.eq(family)&saved.method.eq(label)]
            if len(row)!=1 or int(row.iloc[0].n_eligible)!=totals.n or int(row.iloc[0].n_published)!=totals[prefix+'_kept'] or int(row.iloc[0].n_bad)!=totals[prefix+'_bad']:
                raise RuntimeError(f'Original denominator mismatch for {family}/{label}')
    region.to_csv(OUT/'source_release_by_region.csv',index=False)
    # Do not ship case- or group-level data in the public staging package.
    groups.to_csv(OUT/'source_release_by_connected_group.csv',index=False)
    leave.to_csv(OUT/'source_release_leave_one_region_out.csv',index=False)
    equal.to_csv(OUT/'source_release_equal_group.csv',index=False)
    directions.to_csv(OUT/'source_release_region_directions.csv',index=False)
    status={'cohort':'clean source archive; held-region predictions and source-rule thresholds frozen, one model seed',
            'regions_by_family':directions.to_dict('records'),
            'common_group_statistics':equal.to_dict('records'),
            'missing_policy_risk':'undefined if that rule releases no numeric values; excluded from paired region/group means',
            'deletion':'drop one held-region evaluation subset only; other models and source calibrations are not refit',
            'interpretation':'descriptive sensitivity under chosen masks; target retention differs and lower-bound/unknown information is not equated'}
    (OUT/'source_release_regional_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(directions.to_string(index=False));print(equal.to_string(index=False));print(leave[['design_family','excluded_region','conditional_error_difference']].to_string(index=False))

if __name__=='__main__':main()
