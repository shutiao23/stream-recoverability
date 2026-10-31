#!/usr/bin/env python3
"""Render retrospective peak-visibility diagnostics from saved aggregate scores."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/whole_archive'
PAPER=ROOT/'paper/wrr_tr'


def main():
    status=json.loads((OUT/'peak_visibility_status.json').read_text())
    if status['status']!='passed':raise RuntimeError('Peak-visibility diagnostics have not passed')
    f=pd.read_csv(OUT/'peak_visibility_annual.csv')
    def row(family,stratum,estimator):
        x=f.loc[f.family.eq(family)&f['mode'].eq('forward')&f.stratum.eq(stratum)&f.estimator.eq(estimator)]
        if len(x)!=1:raise ValueError('nonunique diagnostic summary')
        return x.iloc[0]
    ca=row('calendar','all','D2');cv=row('calendar','bound_matches_reference','D2')
    cd=row('calendar','unobserved_peak_excess','D2');cs=row('calendar','unobserved_peak_excess','stochastic_calibrated')
    xa=row('crossed','all','D2');xd=row('crossed','unobserved_peak_excess','D2');xs=row('crossed','unobserved_peak_excess','stochastic_calibrated')
    if cd.n!=cs.n or xd.n!=xs.n or cv.n+cd.n!=ca.n:raise ValueError('common strata disagree')
    vals={'PVCalendarAll':f'{int(ca.n):,}','PVCalendarVisible':f'{int(cv.n):,}',
          'PVCalendarHidden':f'{int(cd.n):,}','PVCalendarDTwoCoverage':f'{100*cd.coverage90:.1f}',
          'PVCalendarClassicCoverage':f'{100*cs.coverage90:.1f}',
          'PVCrossAll':f'{int(xa.n):,}','PVCrossHidden':f'{int(xd.n):,}',
          'PVCrossDTwoCoverage':f'{100*xd.coverage90:.1f}','PVCrossClassicCoverage':f'{100*xs.coverage90:.1f}',
          'PVCrossDTwoCILow':f'{100*xd.coverage90_bootstrap_low:.1f}',
          'PVCrossDTwoCIHigh':f'{100*xd.coverage90_bootstrap_high:.1f}',
          'PVCrossClassicCILow':f'{100*xs.coverage90_bootstrap_low:.1f}',
          'PVCrossClassicCIHigh':f'{100*xs.coverage90_bootstrap_high:.1f}'}
    (PAPER/'peak_visibility_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    table=[r'\begin{table}[p]\centering\scriptsize',
      r'\caption{Retrospective annual performance on the two-estimator common finite-bound cohort, stratified using the complete reference. Match means that the observed lower bound equals the complete reported H30 within $10^{-8}$ $^{\circ}$C; excess means the reference exceeds that bound. This outcome-defined stratum is unavailable at deployment. A station-year can occur in both strata under different masks. Intervals in brackets resample connected groups with 2,000 repetitions and are descriptive under the sampled archive, not independent-climate guarantees.}\label{tab:peak-visibility}',
      r'\begin{tabular}{llllrrrcc}\toprule',
      r'Family & Setting & Stratum & Method & $n$ & Groups & MAE & Coverage & Group interval\\\midrule']
    sub=f.loc[~f.stratum.eq('all')].sort_values(['family','mode','stratum','estimator'])
    for _,r in sub.iterrows():
        name='Match' if r.stratum=='bound_matches_reference' else 'Excess'
        method='D2' if r.estimator=='D2' else 'Stochastic'
        coverage=f'{100*r.coverage90:.1f}\\%'
        interval=f'[{100*r.coverage90_bootstrap_low:.1f}, {100*r.coverage90_bootstrap_high:.1f}]'
        table.append(' & '.join([r.family,r['mode'],name,method,str(int(r.n)),str(int(r.groups)),f'{r.mae:.3f}',coverage,interval])+r'\\')
    table.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'peak_visibility_table.tex').write_text('\n'.join(table)+'\n')
    report={'status':'passed','calendar_forward_common':int(ca.n),'calendar_reference_bound_matches':int(cv.n),
            'calendar_reference_above_bound':int(cd.n),'calendar_hidden_d2_coverage90':float(cd.coverage90),
            'calendar_hidden_stochastic_coverage90':float(cs.coverage90),'controlled_forward_common':int(xa.n),
            'controlled_reference_above_bound':int(xd.n),'controlled_hidden_d2_coverage90':float(xd.coverage90),
            'controlled_hidden_stochastic_coverage90':float(xs.coverage90),
            'limitation':'retrospective strata depend on complete reference, can overlap in station-years, and are unavailable for deployment; group bootstrap does not establish transfer or physical measurement certainty'}
    (OUT/'peak_visibility_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
