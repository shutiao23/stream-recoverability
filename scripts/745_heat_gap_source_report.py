#!/usr/bin/env python3
"""Render the checked source-version sensitivity for matched heat gaps."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/heat_gap_source_sensitivity';PAPER=ROOT/'paper/wrr_tr'


def one(frame,**conditions):
    for key,val in conditions.items():frame=frame[frame[key].eq(val)]
    if len(frame)!=1:raise ValueError('Missing source-sensitivity summary: '+str(conditions))
    return frame.iloc[0]


def main():
    audit=json.loads((OUT/'independent_audit.json').read_text());status=json.loads((OUT/'status.json').read_text())
    interaction_audit=json.loads((OUT/'source_interactions_independent_audit.json').read_text())
    influence_audit=json.loads((OUT/'source_interaction_influence_independent_audit.json').read_text())
    if (audit['status']!='passed' or audit['daily_feature_files_compared']!=220 or audit['summary_rows_checked']!=48
            or status['source_replays']!=220 or interaction_audit['status']!='passed'
            or interaction_audit['interaction_rows_checked']!=16 or influence_audit['status']!='passed'
            or influence_audit['leave_group_rows_checked']!=68
            or interaction_audit['bootstrap_draws_per_cell']!=40000):raise ValueError('Source sensitivity audit incomplete')
    f=pd.read_csv(OUT/'six_way_summary.csv');x=f[f.dependence.eq('independent')&f.scope.eq('both_methods_six_way')]
    if len(x)!=6 or x.n_common.nunique()!=1 or x.groups.nunique()!=1:raise ValueError('Common source cohort differs')
    vals={'HGRCases':str(int(x.n_common.iloc[0])),'HGRStations':str(int(x.stations.iloc[0])),
          'HGRGroups':str(int(x.groups.iloc[0])),'HGRFeatureRows':f"{audit['daily_feature_rows_compared']:,}"}
    interactions=pd.read_csv(OUT/'source_interactions.csv')
    chosen=one(interactions,estimator='D2',dependence='independent',comparison='candidate_minus_original')
    influence=one(pd.read_csv(OUT/'source_interaction_influence_summary.csv'),estimator='D2',comparison='candidate_minus_original')
    if not (chosen.bootstrap_high<0 or chosen.bootstrap_low>0):raise ValueError('Reassess reported interaction interval interpretation')
    if not ((x.bootstrap_low<=0)&(x.bootstrap_high>=0)).all():raise ValueError('Reassess source-specific interval interpretation')
    vals.update(HGRInteraction=f'{chosen.interaction_mean:.4f}',HGRInteractionLow=f'{chosen.bootstrap_low:.4f}',
                HGRInteractionHigh=f'{chosen.bootstrap_high:.4f}',
                HGRInfluenceCross=str(int(influence.intervals_crossing_or_touching_zero)),
                HGRInfluenceGroups=str(int(influence.excluded_groups_tested)))
    rows=[]
    for method,short,code in [('D2','D2','D'),('stochastic_calibrated','Stochastic','S')]:
        for version,label,vcode in [('original','Original','O'),('strict_original','Strict original','R'),('candidate','Candidate providers','C')]:
            r=one(x,estimator=method,version=version)
            vals['HGR'+code+vcode+'Base']=f'{r.baseline_rmse:.3f}';vals['HGR'+code+vcode+'Stress']=f'{r.stress_rmse:.3f}'
            rows.append(f'{short} & {label} & {r.baseline_rmse:.3f} / {r.stress_rmse:.3f} & '
                        f'{100*r.baseline_missing_coverage95:.1f} / {100*r.stress_missing_coverage95:.1f} & '
                        f'{r.equal_group_mse_difference:.4f} & [{r.bootstrap_low:.4f}, {r.bootstrap_high:.4f}] '+r'\\')
    (PAPER/'heat_gap_source_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    content=r'''\section{Source-model sensitivity of matched heat-gap archives}
After observing the earlier source-role and matched-gap results, we held each target mask and daily feature record fixed and re-applied three source-model choices. The original version uses the original source model in every region. The strict-original version replaces only the affected HUC17 model with its earlier refit excluding all HUC17 source groups; elsewhere it is identical to the original. The candidate-provider version uses the earlier target-region-excluded models, which also change the provider set, sample size and role allocation. In all, 205 candidate and 15 strict-original matched-gap settings were re-scored. The source models and daily feature fits were not independently retrained for this comparison.

Table~\ref{tab:heat-gap-source} uses the same \HGRCases{} archives at \HGRStations{} stations and \HGRGroups{} connected groups, where all six source-version by baseline/stress results are available for both methods. The nominal 95\% trend intervals use independent annual ranks. Group resamples concern repeated masks and depend on the sampled groups; all displayed paired-MSE intervals cross zero. Changing source versions also changes group-equal estimates, so the apparent average direction is not a general effect of heat-associated outage. The four stations whose seven-year air reference includes an evaluation-period year, template transfer and retrospective scenario selection remain limitations of the same stress design.

\begin{table}[ht]\caption{Matched-gap source sensitivity, baseline / stress on the same two-method, six-way common cohort. RMSE is $^{\circ}$C per decade; group-equal paired MSE difference and group-resampled intervals are $({}^{\circ}\mathrm{C}/\mathrm{decade})^2$.}\label{tab:heat-gap-source}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{llrrrr}\toprule
Method & Source & RMSE & Coverage (\%) & Group-equal MSE & Paired MSE interval \\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule\end{tabular}}\end{table}

After inspecting the source-specific results, we also computed a directly paired difference between the stress-minus-baseline MSE changes under the candidate and original sources. For D2 with independent ranks, this difference is \HGRInteraction{} with group-resampled interval [\HGRInteractionLow, \HGRInteractionHigh] $({}^{\circ}\mathrm{C}/\mathrm{decade})^2$. The interval does not cross zero but its upper limit is close to zero, whereas each within-source interval in Table~\ref{tab:heat-gap-source} crosses zero; paired contrasts account for covariance and are not equivalent to comparing two separate intervals. The preliminary calculation used separate 4,000-draw streams across rank representations that shared the same point predictions, and its limits differed near zero. After inspecting those results, we retained them and used 40,000 shared group resamples per method and source comparison. In a further post-hoc fixed-prediction check, deleting one connected group and recomputing the interval makes it cross or touch zero for \HGRInfluenceCross{} of \HGRInfluenceGroups{} possible deletions. This is one of 16 reported post-hoc cells, with no multiplicity adjustment; rank representations share point estimates and are not independent tests. Candidate source membership, role assignments and sample size change together. It is evidence of sensitivity in these selected archives, not a causal provider or climate-transfer effect.

Independent checks compare every non-source-model column in 220 replay files (\HGRFeatureRows{} annual rows), confirm that strict and original predictions coincide outside HUC17, and reconstruct 48 summary cells, 144 fixed-prediction leave-region-out cells, all 16 paired source interactions and 68 leave-one-group resamples from saved predictions. These are numerical checks on shared observations and fitted models, not an independent climate, sensor or legal-rights evaluation. The first attempt to distribute tasks to eight processes failed to deserialize a task; the same plan completed serially with receipt checks.
'''
    (PAPER/'heat_gap_source_supporting.tex').write_text(content)
    print('Rendered matched-gap source sensitivity')


if __name__=='__main__':main()
