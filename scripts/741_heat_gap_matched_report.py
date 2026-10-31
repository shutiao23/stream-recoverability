#!/usr/bin/env python3
"""Render the post-hoc matched-gap sensitivity from verified aggregate data."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/heat_gap_matched';PAPER=ROOT/'paper/wrr_tr'


def one(frame,**keys):
    for k,v in keys.items():frame=frame[frame[k].eq(v)]
    if len(frame)!=1:raise ValueError('Expected one heat-gap summary row: '+str(keys))
    return frame.iloc[0]


def main():
    a=json.loads((OUT/'independent_audit.json').read_text());t=json.loads((OUT/'threeway_independent_audit.json').read_text())
    c=json.loads((OUT/'plan_clarification.json').read_text());m=json.loads((OUT/'mask_summary.json').read_text())
    if (a['status']!='passed' or a['independent_masks_checked']!=205 or t['status']!='passed'
            or c['status']!='passed' or m['settings']!=205 or not m['same_gap_template_multiset_and_actual_hidden_days_per_archive']):
        raise ValueError('Matched-gap checks incomplete')
    s=pd.read_csv(OUT/'threeway_summary.csv');d=pd.read_csv(OUT/'threeway_contrasts.csv')
    current=s[s.dependence.eq('independent')]
    if len(current)!=6 or current.n_common.nunique()!=1:raise ValueError('Three-way common cohort differs')
    vals={'HGArchives':str(int(current.n_common.iloc[0])),'HGStations':str(int(current.stations.iloc[0])),
          'HGGroups':str(int(current.groups.iloc[0])),'HGDays':f"{m['matched_hidden_days']:,}",
          'HGHotBase':str(m['baseline_air_hot_masked_years']),'HGHotNew':str(m['matched_air_hot_masked_years']),
          'HGBurninStations':str(c['stations_with_any_2010_or_later_burnin'])}
    rows=[]
    for method,short in [('D2','D2'),('stochastic_calibrated','Stochastic')]:
        v=[one(current,estimator=method,scenario=scenario) for scenario in ['baseline','previous_heat','matched_heat']]
        for suffix,r in zip(['Base','Previous','Matched'],v):vals['HG'+('D' if method=='D2' else 'S')+suffix]=f'{r.rmse:.3f}'
        contrast=one(d,estimator=method,dependence='independent',left='baseline')
        vals['HG'+('D' if method=='D2' else 'S')+'Low']=f'{contrast.bootstrap_low:.4f}'
        vals['HG'+('D' if method=='D2' else 'S')+'High']=f'{contrast.bootstrap_high:.4f}'
        rows.append(short+' & '+' / '.join(f'{x.rmse:.3f}' for x in v)+' & '+' / '.join(f'{100*x.missing_coverage95:.1f}' for x in v)+' & '+' / '.join(f'{x.width95:.3f}' for x in v)+' & '+' / '.join(f'{x.interval_score95:.3f}' for x in v)+r' \\')
    (PAPER/'heat_gap_matched_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    text=r'''\section{Heat-associated years with matched gap templates}
After examining earlier results and the available gap templates, we repeated the forward controlled-gap sensitivity for 41 stations and five archive masks per station. The selected heat-associated years are the same as in the prior heat sensitivity. For years masked in both the baseline and heat design, the original gap is retained; remaining baseline offset--length templates are transferred to the newly selected heat years. Every archive retains its original masked-year count, multiset of templates and actual number of hidden days. Total hidden days are \HGDays{} in either design, and air-hot masked years increase from \HGHotBase{} to \HGHotNew{}; repeated masks are not independent observations. Offsets are relative to the year, and the relationship of a transferred gap to a particular seasonal peak can change.

The matched-gap plan incorrectly described the first-seven-year air baseline as entirely pre-2010. In \HGBurninStations{} of the 41 stations, one of those seven reference-year labels is 2010 or later. The saved implementation uses the first seven reference years; no predictions were changed by this clarification. Air information constructs a synthetic retrospective mask and is not a hidden water-temperature outcome, but the mechanism is not a strictly prior-vintage or prospective outage generator.

After viewing the pairwise results, we additionally restricted all three designs and both methods to the same \HGArchives{} available station--replicate settings from \HGStations{} stations and \HGGroups{} connected groups (Table~\ref{tab:heat-gap-matched}). Group-resampled differences in paired MSE for matched minus baseline are [\HGDLow, \HGDHigh] for D2 and [\HGSLow, \HGSHigh] for the stochastic comparator, in $({}^{\circ}\mathrm{C}/\mathrm{decade})^2$. The shared cohort is post-hoc, and these differences change in group-equal weighting. The fixed heat-year count and gap-template distribution do not isolate year, position and peak alignment, establish a natural-outage mechanism, or prove climate transfer.

\begin{table}[ht]\caption{Three-way common cohort, baseline / previous heat / matched heat, with independent annual ranks. RMSE, widths and interval scores are $^{\circ}$C per decade; coverage is for nominal 95\% trend intervals.}\label{tab:heat-gap-matched}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lrrrr}\toprule
Method & RMSE & Coverage (\%) & Width & Interval score \\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule\end{tabular}}\end{table}

Separate checks reconstruct all 205 masks from the same underlying panels and seeded selection and independently recompute 32 paired summary rows, 96 fixed-prediction leave-region-out rows, 24 three-way summary rows and 16 three-way contrasts, including seeded group resampling. The underlying observations, trained source models and local daily refits are reused; these checks do not constitute independent physical or climate validation.
'''
    (PAPER/'heat_gap_matched_supporting.tex').write_text(text)
    print('Rendered matched-gap sensitivity')


if __name__=='__main__':main()
