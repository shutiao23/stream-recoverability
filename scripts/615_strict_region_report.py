#!/usr/bin/env python3
"""Render post-hoc strict-region sensitivity from checked aggregate outputs."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'results/wrr_review_response_20261027/strict_region_holdout'; PAPER=ROOT/'paper/wrr_tr'

def main():
    for path,expected in [('refit_status.json','strict_models_refitted'),('future_comparison_status.json','passed'),('archive_sensitivity_status.json','affected_archives_reanalyzed'),('archive_pooled_status.json','passed'),('integrated_release_status.json','passed'),('annual_diagnostics_status.json','passed'),('all_source_role_effects_status.json','passed'),('future_matched_retention_status.json','passed'),('calibration_source_upper_bound_status.json','passed'),('scenario_sensitivity_status.json','passed'),('uncertainty_sensitivity_status.json','passed'),('archive_prediction_replay_status.json','passed'),('robustness_status.json','passed')]:
        if json.loads((OUT/path).read_text())['status']!=expected:raise ValueError('strict sensitivity incomplete: '+path)
    p=pd.read_csv(OUT/'archive_estimator_four_way_paired.csv');f=pd.read_csv(OUT/'future_release_comparison.csv')
    def only(x):
        if len(x)!=1:raise ValueError('expected a unique summary row')
        return x.iloc[0]
    a=only(p.loc[p.family.eq('crossed')]);b=only(f.loc[f.scope.eq('all_regions')&f.family.eq('crossed')&f.method.eq('three_outputs')]);c=only(f.loc[f.scope.eq('usgs_huc17')&f.family.eq('crossed')&f.method.eq('three_outputs')])
    vals={'SRPairN':str(int(a.n_common)),'SRPairStations':str(int(a.n_stations)), 'SROldDTwo':f'{a.original_d2_rmse:.4f}','SRNewDTwo':f'{a.strict_d2_rmse:.4f}', 'SROldStoch':f'{a.original_stoch_rmse:.4f}','SRNewStoch':f'{a.strict_stoch_rmse:.4f}', 'SRFutureN':f'{int(b.n_eligible):,}', 'SROldRet':f'{100*b.original_retention:.1f}','SRNewRet':f'{100*b.strict_retention:.1f}', 'SROldRisk':f'{100*b.original_selected_failure:.1f}','SRNewRisk':f'{100*b.strict_selected_failure:.1f}', 'SRHucOldRet':f'{100*c.original_retention:.1f}','SRHucNewRet':f'{100*c.strict_retention:.1f}', 'SRHucOldRisk':f'{100*c.original_selected_failure:.1f}','SRHucNewRisk':f'{100*c.strict_selected_failure:.1f}'}
    z=pd.read_csv(OUT/'integrated_paired_summary.csv'); integrated=only(z.loc[z.scope.eq('pooled_forward')&z.family.eq('crossed')&z.method.eq('released_values_and_bounds')])
    v=pd.read_csv(OUT/'annual_paired_diagnostics.csv'); annual=only(v.loc[v.scope.eq('all_regions')&v.family.eq('crossed')&v.stratum.eq('unobserved_peak_excess')&v.estimator.eq('D2')])
    mm=pd.read_csv(OUT/'future_matched_retention.csv'); matched=only(mm.loc[mm.family.eq('crossed')&mm.version.eq('strict')])
    tt=pd.read_csv(OUT/'integrated_state_transitions.csv',index_col=0); transitions=int(tt.loc['observed_bound','estimate'])
    vals.update({'SRIntN':f"{int(integrated.n_common):,}",'SRIntOld':f"{integrated.original_rmse:.4f}",'SRIntNew':f"{integrated.strict_rmse:.4f}",
      'SRIntOldWidth':f"{integrated.original_total_working_width95:.2f}",'SRIntNewWidth':f"{integrated.strict_total_working_width95:.2f}",
      'SRChangedStates':str(transitions),'SRAnnualN':f"{int(annual.n_common):,}",'SRAnnualOld':f"{100*annual.original_coverage90:.1f}",'SRAnnualNew':f"{100*annual.strict_coverage90:.1f}",
      'SRMatchedN':f"{int(matched.n_equal_numerical):,}",'SRMatchedThree':f"{100*matched.three_output_risk:.2f}",'SRMatchedScore':f"{100*matched.score_only_risk:.2f}"})
    uncertainty=pd.read_csv(OUT/'uncertainty_common_paired_sensitivity.csv')
    u=only(uncertainty.loc[uncertainty.family.eq('crossed')&uncertainty['mode'].eq('forward')&uncertainty.estimator.eq('D2')])
    scenarios=pd.read_csv(OUT/'scenario_paired_sensitivity.csv');scenarios=scenarios.loc[scenarios.family.eq('crossed')&scenarios.estimator.eq('D2')&scenarios.retention.eq('all')&scenarios.dependence.eq('point')]
    donor=only(scenarios.loc[scenarios.scenario.eq('synchronized_donors')]);heat=only(scenarios.loc[scenarios.scenario.eq('heat_associated')])
    vals.update({'SRUncN':str(int(u.n_common_both_versions)), 'SRUncGroups':str(int(u.groups)),
       'SRConstOld':f"{100*u.original_constant_coverage95:.1f}", 'SRConstNew':f"{100*u.strict_constant_coverage95:.1f}",
       'SRNormalOld':f"{100*u.original_normal_coverage95:.1f}", 'SRNormalNew':f"{100*u.strict_normal_coverage95:.1f}",
       'SRIndOld':f"{100*u.original_independent_coverage95:.1f}", 'SRIndNew':f"{100*u.strict_independent_coverage95:.1f}",
       'SRBlockOld':f"{100*u.original_residual_blocks_coverage95:.1f}", 'SRBlockNew':f"{100*u.strict_residual_blocks_coverage95:.1f}",
       'SRNormalOldWidth':f"{u.original_normal_width95:.3f}", 'SRNormalNewWidth':f"{u.strict_normal_width95:.3f}",
       'SRNormalOldScore':f"{u.original_normal_interval_score95:.3f}", 'SRNormalNewScore':f"{u.strict_normal_interval_score95:.3f}",
       'SRScenarioN':str(int(donor.n_common)), 'SRScenarioBaseOld':f"{donor.original_baseline_rmse:.4f}", 'SRScenarioBaseNew':f"{donor.strict_baseline_rmse:.4f}",
       'SRDonorOld':f"{donor.original_stress_rmse:.4f}", 'SRDonorNew':f"{donor.strict_stress_rmse:.4f}",
       'SRHeatOld':f"{heat.original_stress_rmse:.4f}", 'SRHeatNew':f"{heat.strict_stress_rmse:.4f}"})
    robust=pd.read_csv(OUT/'robustness_paired_bootstrap.csv');rg=only(robust.loc[robust.family.eq('crossed')&robust.right.eq('stochastic_calibrated')])
    leave=pd.read_csv(OUT/'robustness_leave_one_region_out.csv');lc=only(leave.loc[leave.family.eq('calendar')&leave.right.eq('stochastic_calibrated')&leave.excluded_region.eq('gkd_bayern')]);lx=only(leave.loc[leave.family.eq('crossed')&leave.right.eq('stochastic_calibrated')&leave.excluded_region.eq('gkd_bayern')])
    vals.update({'SRRobustN':str(int(rg.n_common)),'SRRobustGroups':str(int(rg.n_groups)),
      'SRRobustOld':f"{rg.original_pooled_mse_difference:+.6f}",'SRRobustNew':f"{rg.strict_pooled_mse_difference:+.6f}",
      'SRRobustNewLo':f"{rg.strict_pooled_low:+.6f}",'SRRobustNewHi':f"{rg.strict_pooled_high:+.6f}",
      'SRBayernCalendarN':str(int(lc.n_remaining)),'SRBayernCalendarOld':f"{lc.original_pooled_mse_difference:+.6f}",'SRBayernCalendarNew':f"{lc.strict_pooled_mse_difference:+.6f}",
      'SRBayernCrossN':str(int(lx.n_remaining)),'SRBayernCrossGroups':str(int(lx.n_groups)),'SRBayernCrossOld':f"{lx.original_pooled_mse_difference:+.6f}",'SRBayernCrossNew':f"{lx.strict_pooled_mse_difference:+.6f}"})
    (PAPER/'strict_region_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    (PAPER/'strict_region_supporting.tex').write_text(r'''\section{Post-hoc strict-region sensitivity}
We refitted the two affected before-2010 seed-zero models after removing every source connected group that appears in the named target region. The original assignment and bootstrap multiplicities of other groups were retained; no replacement groups were drawn. Source interval and release thresholds were recalculated from the filtered roles. In the whole-archive experiment, only the three affected HUC17 stations were reanalysed, on the same 120 original masks; all other original results were retained. Each strict run checked the original mask and the absence of hidden target values. Both estimators were compared on the same station--repetition cases available in both versions. For forward controlled gaps this common cohort comprises \SRPairN{} cases at \SRPairStations{} stations. Original and strict D2 trend RMSE are \SROldDTwo{} and \SRNewDTwo{}; the corresponding stochastic RMSE values are \SROldStoch{} and \SRNewStoch{} $^{\circ}$C per decade.

The future-year release analysis replaces predictions in both affected regions while preserving all target cases and the other regional models. Across \SRFutureN{} forward controlled-gap cases, the three-output rule publishes \SROldRet\% and \SRNewRet\% in the original and strict comparisons, with \SROldRisk\% and \SRNewRisk\% observed failures among the published values. In HUC17, publication changes from \SRHucOldRet\% to \SRHucNewRet\%, and the selected error rate from \SRHucOldRisk\% to \SRHucNewRisk\%. The selected sets differ, so the conditional rates cannot be interpreted without retention. The strict refits use fewer source observations; these paired comparisons do not identify the causal effect of an individual group and do not establish external validity or safety. They do not recompute every analysis in this paper under strict regional exclusion. Case counts contain repeated masks and are not independent climates.
''')
    with (PAPER/'strict_region_supporting.tex').open('a') as fh:
        fh.write(r"""
The source-role comparison additionally checked held test station identities across all source regions, the positive bootstrap weights and the effective split of classifier and probability-calibration groups. Only the two before-2010 models changed positive source weights; zero-weight role membership still matters for downstream group-list use, so this does not prove every downstream result unchanged.

The release-then-trend pipeline was replayed for all 120 HUC17 settings with the original masks, source-specific strict limits and newly fitted model. Original annual states reproduced for 1,440 station--year records. Across the affected records, \SRChangedStates{} observed-bound outputs become numerical estimates; the other observed-bound and estimate states remain unchanged. The original and strict pooled controlled-gap comparisons comprise \SRIntN{} common station--repetition cases and give released-values-plus-bounds working-likelihood trend RMSE \SRIntOld{} and \SRIntNew{} $^{\circ}$C per decade, respectively, with mean working interval widths \SRIntOldWidth{} and \SRIntNewWidth{}. These working intervals include regression variation and do not establish calibrated missingness-only coverage.

In the outcome-defined stratum with an unobserved peak, the \SRAnnualN{} common forward controlled-gap annual cases have D2 nominal 90\% coverage \SRAnnualOld\% originally and \SRAnnualNew\% under the stricter source. This retrospective stratum is unavailable to a decision maker and repeated masks are not independent climate realizations. The affected HUC17 source rule-calibration pool contains at most one eligible connected group before model prediction, below the minimum of three for both annual expansion and task calibration; strict refitting cannot change that source-group upper bound, although the corresponding radius and errors were not recalculated.

For forward controlled gaps, the same \SRUncN{} station--repetition cases from \SRUncGroups{} connected groups have every annual, tail and rank-coupling output in both source versions. Under constant tails, nominal 95\% D2 trend coverage is \SRConstOld\% originally and \SRConstNew\% strictly; normal-spacing tails yield \SRNormalOld\% and \SRNormalNew\%, with widths \SRNormalOldWidth{} and \SRNormalNewWidth{} and interval scores \SRNormalOldScore{} and \SRNormalNewScore{}. In the separate normal-tailed rank experiment, independent ranks yield \SRIndOld\% and \SRIndNew\% coverage and residual blocks yield \SRBlockOld\% and \SRBlockNew\%. Original tail results reproduced on all 480 affected tail rows. These comparisons use the same random ranks within each tail or coupling experiment, but the tail and coupling experiments use different draws; they do not identify additive causes of undercoverage. Descriptive connected-group bootstrap intervals for strict-minus-original metrics accompany the aggregate results.

For the forward controlled-gap D2 versus stochastic comparison, \SRRobustN{} cases at \SRRobustGroups{} connected groups are available under both source versions and both estimators. The pooled D2-minus-stochastic MSE difference is \SRRobustOld{} originally and \SRRobustNew{} strictly; the descriptive connected-group bootstrap interval for the strict result is [\SRRobustNewLo{}, \SRRobustNewHi{}] $({}^{\circ}\mathrm{C}/\mathrm{decade})^2$. The same resampled groups are used for both source versions. Removing Bavaria from these fixed predictions leaves \SRBayernCrossN{} cases in \SRBayernCrossGroups{} groups and changes the difference from \SRBayernCrossOld{} originally to \SRBayernCrossNew{} strictly. For empirical calendars the corresponding original and strict differences are \SRBayernCalendarOld{} and \SRBayernCalendarNew{} on \SRBayernCalendarN{} cases. These small changes can alter the sign of the regional comparison; the leave-one-region-out exercise does not refit source models and does not establish independent climates or significance.

The small controlled-gap stress comparison reanalyses 20 settings for one HUC17 station while retaining other stations' original results. Among \SRScenarioN{} common baseline/stress station--repetition cases, original and strict baseline D2 RMSE are \SRScenarioBaseOld{} and \SRScenarioBaseNew{}; for synchronized donor gaps they are \SRDonorOld{} and \SRDonorNew{}, and for heat-associated gaps \SRHeatOld{} and \SRHeatNew{} $^{\circ}$C per decade. Original scenario metrics and masks reproduce. The heat-associated scenario changes both the identity and potentially the number of masked years, so these are exploratory paired scenario comparisons, not isolated causal effects or independent climate tests.

A separate recalculation of the transductive, same-number numerical-output comparator under the strict source model publishes \SRMatchedN{} controlled-gap values: three-output and score-only failure rates are \SRMatchedThree\% and \SRMatchedScore\%, respectively. The score threshold uses the target feature distribution and the three-output count; counts and selected cases differ between source versions, and lower-bound information is not held equal.
""")
    print(json.dumps(vals,indent=2))
if __name__=='__main__':main()
