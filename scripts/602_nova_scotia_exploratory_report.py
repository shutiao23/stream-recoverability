#!/usr/bin/env python3
"""Cross-check and render the nonconfirmatory NS reported-clock experiment."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
PAPER=ROOT/'paper/wrr_tr'


def main():
    score=json.loads((OUT/'score_status.json').read_text());integrity=json.loads((OUT/'integrity_status.json').read_text())
    probe=json.loads((OUT/'hidden_value_probe.json').read_text());diag=json.loads((OUT/'diagnostic_status.json').read_text())
    ref=json.loads((OUT/'reference_status.json').read_text());forcing=json.loads((OUT/'forcing_status.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    if score['status']!='exploratory_scored' or integrity['status']!='passed' or probe['status']!='passed' or diag['status']!='passed':raise ValueError('experiment checks are incomplete')
    if score['strict_reference_qualified'] or ref['strict_reference_qualified'] or forcing['strict_reference_qualified']:raise ValueError('exploratory reference cannot be labelled strict')
    if score['cases']!=integrity['cases'] or score['cases']!=diag['cases'] or score['station_years']!=ref['station_years']:
        raise ValueError('case or reference denominators differ')
    if not ref['model_scoring_performed'] or not forcing['model_scoring_performed']:raise ValueError('pre-score artifact status was not updated')
    pair=pd.read_csv(OUT/'paired_summary.csv');summary=pd.read_csv(OUT/'score_summary.csv')
    years=pd.read_csv(OUT/'site_year_summary.csv');detail=pd.read_csv(OUT/'paired_posthoc_diagnostics.csv')
    allrow=pair.loc[pair.stratum.eq('all')]
    if len(allrow)!=1:raise ValueError('overall paired summary not unique')
    a=allrow.iloc[0]
    if int(a.n_eligible)!=score['cases'] or int(a.station_years)!=score['station_years']:raise ValueError('paired counts differ')
    def val(name,digits=3):return f'{float(a[name]):.{digits}f}'
    macros={'NSExpCases':str(int(a.n_common)),'NSExpStations':str(int(a.stations)),'NSExpYears':str(int(a.station_years)),
      'NSExpDTwoMAE':val('D2_mae'),'NSExpClassicMAE':val('stochastic_mae'),
      'NSExpDTwoCover':f'{100*a.D2_coverage90:.1f}','NSExpClassicCover':f'{100*a.stochastic_coverage90:.1f}',
      'NSExpDTwoWidth':val('D2_width90'),'NSExpClassicWidth':val('stochastic_width90'),
      'NSExpDTwoScore':val('D2_interval_score90'),'NSExpClassicScore':val('stochastic_interval_score90')}
    (PAPER/'nova_scotia_exploratory_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items()))
    lines=[r'\section{Nova Scotia reported-clock exploratory masking}',
      ('The preceding qualification did not establish strict reference quality. After inspecting availability and two-release agreement, '
       'a separate unregistered exploratory amendment fixed two sites and eight station-years before any model prediction errors were computed. '
       'Each selected year has 24 finite reported hourly labels per day and agrees numerically across the two releases of the same monitoring programme. '
       'Time zone, estimated-value status and point-level quality remain unresolved. The reported daily value is the mean of the 24 reported hourly values; '
       'it is not guaranteed to represent a physical civil day or an error-free temperature. The fixed global source model and source-only interval '
       'calibration were reused. Each year was masked separately with 30-, 60- and 90-day controlled gaps, using the other three selected years '
       'for local history; no empirical-calendar family or whole-archive degradation was evaluated. NASA POWER forcing uses local solar time '
       'and coordinates rounded to 0.01 degree. The adjacent-normal tail continuation is an assumption for CRPS. '
       'The 144 cases are repeated masks at two sites and eight station-years, not 144 independent watersheds. '
       'An independent arithmetic audit recomputed reference H30, bounds, masks and reported scores. In two post-hoc hidden-value probes, '
       'adding 5 $^{\circ}$C to hidden days changed the true H30 but did not change decision features or predictions when identically serialized '
       'controls were compared. Those two probes are not an exhaustive leakage proof.'),
      r'\begin{table}[p]\centering\small',
      r'\caption{Reported-clock exploratory controlled-gap scores on identical available cases. Coverage is percent, and MAE, width and interval score are in $^{\circ}$C. These are two sites, not independent climatic replications; source quality and time basis remain unresolved.}\label{tab:ns-exploratory}',
      r'\begin{tabular}{lrrrrr}\toprule',
      r'Method & Cases & MAE & 90\% coverage & 90\% width & Interval score\\\midrule']
    for name,label in [('D2','D2'),('stochastic','Stochastic')]:
        lines.append(' & '.join([label,str(int(a.n_common)),f'{a[name+"_mae"]:.3f}',f'{100*a[name+"_coverage90"]:.1f}',
           f'{a[name+"_width90"]:.3f}',f'{a[name+"_interval_score90"]:.3f}'])+r'\\')
    lines.extend([r'\bottomrule\end{tabular}',r'\end{table}',
      r'\begin{table}[p]\centering\scriptsize',
      r'\caption{Post-hoc descriptive paired results by gap length and site. Counts are repeated masks; group differences are not inferential tests.}\label{tab:ns-exploratory-detail}',
      r'\begin{tabular}{llrrrrr}\toprule',
      r'Axis & Level & Cases & D2 MAE & Stochastic MAE & D2 coverage & Stochastic coverage\\\midrule'])
    for r in detail.itertuples(index=False):
        axis='Gap days' if r.axis=='gap_length' else 'Station'
        lines.append(' & '.join([axis,str(r.level),str(int(r.n_common)),f'{r.D2_mae:.3f}',f'{r.stochastic_mae:.3f}',
          f'{100*r.D2_coverage90:.1f}',f'{100*r.stochastic_coverage90:.1f}'])+r'\\')
    lines.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'nova_scotia_exploratory_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','cases':int(a.n_common),'stations':int(a.stations),'station_years':int(a.station_years),
      'D2_mae':float(a.D2_mae),'stochastic_mae':float(a.stochastic_mae),
      'D2_coverage90':float(a.D2_coverage90),'stochastic_coverage90':float(a.stochastic_coverage90),
      'D2_width90':float(a.D2_width90),'stochastic_width90':float(a.stochastic_width90),
      'D2_interval_score90':float(a.D2_interval_score90),'stochastic_interval_score90':float(a.stochastic_interval_score90),
      'integrity_checks_passed':True,'hidden_value_probes':int(probe['probes']),
      'strict_reference_qualified':False,'limitations':score['limitations']}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
