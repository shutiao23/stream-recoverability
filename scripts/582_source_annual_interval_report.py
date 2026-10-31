#!/usr/bin/env python3
"""Render and cross-check the source-only annual interval expansion experiment."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/annual_interval_expansion'
PAPER=ROOT/'paper/wrr_tr'


def main():
    status=json.loads((OUT/'status.json').read_text())
    if status['status']!='passed':raise RuntimeError('annual expansion experiment not passed')
    plan=pd.read_csv(OUT/'source_support.csv');s=pd.read_csv(OUT/'paired_summary.csv')
    common=s.loc[s.scope.eq('both_methods_common')&s.stratum.eq('all')].copy()
    if len(common)!=8:raise ValueError('expected four settings and two methods')
    a=common.loc[common.estimator.eq('D2')];b=common.loc[common.estimator.eq('stochastic_calibrated')]
    joined=a.merge(b,on=['family','mode'],suffixes=('_d','_s'),validate='one_to_one')
    if not joined.n_eligible_d.eq(joined.n_eligible_s).all() or not joined.n_supported_d.eq(joined.n_supported_s).all():
        raise ValueError('method comparisons do not use the same target cases')
    supported=plan.loc[plan.status.eq('supported_exploratory')]
    if supported.n_source_groups.lt(3).any() or supported.empirical_radius.le(1e-8).any():raise ValueError('invalid source support status')
    if plan.loc[plan['mode'].eq('forward'),'last_source_year'].dropna().ge(2010).any():raise ValueError('future source calibration leakage')
    # The last analysis independently established the same reference-defined
    # strata on the original whole-archive cases.
    peaks=pd.read_csv(ROOT/'results/wrr_review_response_20261027/whole_archive/peak_visibility_annual.csv')
    q=s.loc[s.scope.eq('both_methods_common')&s.stratum.isin(['bound_matches_reference','unobserved_peak_excess'])]
    m=q.merge(peaks,on=['family','mode','estimator','stratum'],validate='one_to_one')
    if len(m)!=16 or not m.n_eligible.eq(m.n).all():raise ValueError('reference-stratum denominators differ')
    for col in ('coverage90','width90','interval_score90','zero90'):
        if not np.allclose(m['baseline_all_'+col],m[col],rtol=0,atol=1e-10,equal_nan=True):
            raise ValueError(f'reference-stratum baseline differs: {col}')
    def get(estimator):
        x=common.loc[common.family.eq('crossed')&common['mode'].eq('forward')&common.estimator.eq(estimator)]
        if len(x)!=1:raise ValueError('nonunique forward controlled result')
        return x.iloc[0]
    d=get('D2');c=get('stochastic_calibrated')
    def f(v,digits=2):return '--' if pd.isna(v) else f'{float(v):.{digits}f}'
    vals={'AEFwdCommon':f'{int(d.n_eligible):,}','AEFwdSupported':f'{int(d.n_supported):,}',
          'AEFwdPct':f'{100*d.availability:.1f}','AEFwdStations':str(int(d.stations)),
          'AEFwdDTwoBefore':f(100*d.baseline_paired_coverage90,1),'AEFwdDTwoAfter':f(100*d.expanded_paired_coverage90,1),
          'AEFwdClassicBefore':f(100*c.baseline_paired_coverage90,1),'AEFwdClassicAfter':f(100*c.expanded_paired_coverage90,1),
          'AEFwdDTwoWidthBefore':f(d.baseline_paired_width90,3),'AEFwdDTwoWidthAfter':f(d.expanded_paired_width90,3),
          'AEFwdClassicWidthBefore':f(c.baseline_paired_width90,3),'AEFwdClassicWidthAfter':f(c.expanded_paired_width90,3),
          'AEMaxSourceGroups':str(int(plan.n_source_groups.max()))}
    (PAPER/'annual_interval_expansion_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    table=[r'\begin{table}[p]\centering\scriptsize',
       r'\caption{Exploratory source-only annual interval expansion on two-method common cases. Supported cases have at least three disjoint source groups and a positive empirical correction; unavailable and zero-correction regions remain in the denominator. Before and after use exactly the same supported cases. The source-group-weighted empirical correction has no finite-sample or climate-transfer guarantee; it was explored after inspecting the principal results. Coverage is percent, width and interval score are in $^{\circ}$C.}\label{tab:annual-expansion}',
       r'\begin{tabular}{lllrrccc}\toprule',
       r'Family & Setting & Method & Eligible & Supported & Coverage & Width & Interval score\\\midrule']
    for _,r in common.sort_values(['family','mode','estimator']).iterrows():
        name='D2' if r.estimator=='D2' else 'Stochastic'
        a1=f(100*r.baseline_paired_coverage90,1);a2=f(100*r.expanded_paired_coverage90,1)
        w1=f(r.baseline_paired_width90,3);w2=f(r.expanded_paired_width90,3)
        i1=f(r.baseline_paired_interval_score90,3);i2=f(r.expanded_paired_interval_score90,3)
        combine=lambda x,y:'--' if x=='--' else x+r'$\to$'+y
        table.append(' & '.join([r.family,r['mode'],name,str(int(r.n_eligible)),str(int(r.n_supported)),combine(a1,a2),combine(w1,w2),combine(i1,i2)])+r'\\')
    table.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'annual_interval_expansion_table.tex').write_text('\n'.join(table)+'\n')
    report={'status':'passed','forward_controlled_common':int(d.n_eligible),'forward_controlled_supported':int(d.n_supported),
       'forward_controlled_availability':float(d.availability),'forward_controlled_supported_stations':int(d.stations),
       'forward_d2_coverage_before':None if pd.isna(d.baseline_paired_coverage90) else float(d.baseline_paired_coverage90),
       'forward_d2_coverage_after':None if pd.isna(d.expanded_paired_coverage90) else float(d.expanded_paired_coverage90),
       'forward_d2_width_before':None if pd.isna(d.baseline_paired_width90) else float(d.baseline_paired_width90),
       'forward_d2_width_after':None if pd.isna(d.expanded_paired_width90) else float(d.expanded_paired_width90),
       'plan_status_counts':{str(k):int(v) for k,v in plan.status.value_counts().items()},
       'maximum_source_groups':int(plan.n_source_groups.max()),
       'finite_group_max_corrections':int(plan.group_max_radius.notna().sum()),
       'limitations':status['limitation']}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
