#!/usr/bin/env python3
"""Render full-cohort paired stress sensitivity into manuscript inputs."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/expanded_stress'
PAPER=ROOT/'paper/wrr_tr'


def unique(frame, **conditions):
    for field,value in conditions.items():frame=frame[frame[field].eq(value)]
    if len(frame)!=1:raise ValueError(f'Expected one stress summary: {conditions}')
    return frame.iloc[0]


def main():
    audit=json.loads((OUT/'independent_audit.json').read_text())
    if audit['status']!='passed' or audit['baseline_masks_checked']!=205:
        raise ValueError('Expanded scenario audit incomplete')
    p=pd.read_csv(OUT/'paired_summary.csv');m=pd.read_csv(OUT/'mask_summary.csv');r=pd.read_csv(OUT/'leave_one_region_out.csv')
    donor=unique(p,scenario='synchronized_donors',estimator='D2',dependence='point')
    heat=unique(p,scenario='heat_associated_matched',estimator='D2',dependence='point')
    hm=unique(m,scenario='heat_associated_matched');dm=unique(m,scenario='synchronized_donors')
    db=unique(r,scenario='synchronized_donors',estimator='D2',dependence='point',removed_region='gkd_bayern')
    hb=unique(r,scenario='heat_associated_matched',estimator='D2',dependence='point',removed_region='gkd_bayern')
    if donor.n_common!=205 or heat.n_common!=205 or hm.n_available!=205 or dm.n_available!=205:
        raise ValueError('Unexpected full D2 case denominator')
    vals={'ESArchives':str(int(donor.n_common)),'ESStations':str(int(donor.n_stations)),'ESGroups':str(int(donor.n_groups)),
          'ESBaseline':f'{donor.baseline_rmse:.4f}','ESDonor':f'{donor.stress_rmse:.4f}','ESHeat':f'{heat.stress_rmse:.4f}',
          'ESDonorLow':f'{donor.bootstrap_low:.4f}','ESDonorHigh':f'{donor.bootstrap_high:.4f}',
          'ESHeatLow':f'{heat.bootstrap_low:.4f}','ESHeatHigh':f'{heat.bootstrap_high:.4f}',
          'ESYears':f'{int(hm.baseline_masked_years):,}','ESHotBaseline':str(int(hm.baseline_hot_masked_years)),
          'ESHotHeat':str(int(hm.stress_hot_masked_years)),'ESDaysBaseline':f'{int(hm.baseline_hidden_days):,}',
          'ESDaysHeat':f'{int(hm.stress_hidden_days):,}','ESDonorCells':f'{int(dm.donor_observations_removed_counting_repeated_masks):,}',
          'ESBavariaDonorBase':f'{db.baseline_rmse:.4f}','ESBavariaDonorStress':f'{db.stress_rmse:.4f}',
          'ESBavariaHeatBase':f'{hb.baseline_rmse:.4f}','ESBavariaHeatStress':f'{hb.stress_rmse:.4f}'}
    (PAPER/'expanded_stress_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    rows=[]
    for scenario,label in [('synchronized_donors','Donor gaps'),('heat_associated_matched','Heat, fixed years')]:
        for est,short in [('D2','D2'),('stochastic_calibrated','Stochastic')]:
            a=unique(p,scenario=scenario,estimator=est,dependence='independent')
            rows.append(f"{label} & {short} & {int(a.n_common)} & {a.baseline_rmse:.4f} / {a.stress_rmse:.4f} & {100*a.baseline_missing_coverage95:.1f} / {100*a.stress_missing_coverage95:.1f} & {a.baseline_width95:.3f} / {a.stress_width95:.3f} & {a.baseline_interval_score95:.3f} / {a.stress_interval_score95:.3f} \\\\")
    content=r'''\section{Expanded missingness-mechanism sensitivities}
After the earlier results and seven-site pilot had been inspected, we fixed an expansion to the first five masks for all 41 forward-eligible original archive stations in 17 connected groups. Only controlled gaps and one seed-zero source-model assignment are studied. For the donor sensitivity, the target masks are unchanged and those same dates are hidden in every other panel column before local fitting. All 205 settings have at least one finite donor-panel observation removed; the total of \ESDonorCells{} finite donor-panel cells counts repeated masks and may include columns not ultimately selected by the local estimator. It is not a count of independent outages or necessarily of observations the estimator would have used.

For the heat-associated sensitivity, the original 35\% Bernoulli draw determines the number of masked years in each station--repetition archive. An independent seeded exponential-race sample chooses exactly that number of eligible years, with weight five for years whose annual air H30 is at least the first-seven-year 80th percentile, and weight one otherwise. Air information determines a synthetic test mask; it is not a hidden water-temperature outcome. The full cohort has \ESYears{} masked years in either design, of which \ESHotBaseline{} and \ESHotHeat{} are classified as air-hot. However, the selected years have different existing within-year gap shapes and positions, so the total hidden target days change from \ESDaysBaseline{} to \ESDaysHeat{}. These paired scenarios cannot isolate the causal effect of heat association alone or represent a measured outage mechanism.

Table~\ref{tab:expanded-stress} compares fixed-prediction cohorts for both estimators, with availability reported on the common subset. Nominal trend interval coverage, widths and scores use independent annual ranks and the original normal-spacing tails; the intervals are not validated climate-transfer guarantees. Connected-group resampling of paired D2 squared-error differences gives [\ESDonorLow, \ESDonorHigh] for synchronized donors and [\ESHeatLow, \ESHeatHigh] for heat-associated masking, in $({}^{\circ}\mathrm{C}/\mathrm{decade})^2$. These describe a selected archive and depend on group exchangeability. Removing Bavaria without refitting changes baseline and donor RMSE to \ESBavariaDonorBase{} and \ESBavariaDonorStress{}, and baseline and heat RMSE to \ESBavariaHeatBase{} and \ESBavariaHeatStress{}. Other fixed-prediction leave-region-out summaries are supplied in the aggregate files. Repeated masks are not independent climates; original forward source roles are not uniformly strict named-region holdouts.

\begin{table}[ht]
\caption{Expanded paired controlled-gap stresses, original / stress. RMSE and interval widths are $^{\circ}$C per decade. Coverage is for nominal 95\% trend intervals; scores are also in $^{\circ}$C per decade. Common fitted cohorts differ between estimators and scenarios.}
\label{tab:expanded-stress}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{llrrrrr}\toprule
Scenario & Estimator & Cases & RMSE & Coverage & Width & Score \\
\midrule
'''+'\n'.join(rows)+r'''
\bottomrule\end{tabular}}\end{table}

An independent audit reconstructs all 205 baseline masks, 205 synchronized masks and 205 heat-associated masks, and recomputes eight paired RMSE and mean-squared-error cells. It uses the same source observations, random seeds and saved fitted predictions; it does not independently refit the models, check bootstrap intervals or establish sensor quality.
'''
    (PAPER/'expanded_stress_supporting.tex').write_text(content)
    print('Rendered expanded stress manuscript inputs')


if __name__=='__main__':main()
