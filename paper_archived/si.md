# Supporting Information

This Supporting Information accompanies “A Case-Study Covariance Heuristic for Stream-Temperature Recoverability in Two Regulated River Networks.” The submission build expands Texts S1--S15 and embeds supplementary figures and compact tables into one self-contained package.

## Contents

- **Text S1: Extended methods.** [`methods.md`](methods.md) documents the M1--M10 grid, frozen masks, overlap-aware bootstrap, dual-denominator frontier, official deep-model adapters, and evaluate-once external protocol.
- **Text S2: Independence and matching audits.** [`si_independence_audits.md`](si_independence_audits.md) reports anchor overlap, effective replication, and event/control matching. Masked days are never treated as independent replicates.
- **Text S3: Validation-only model funnel.** Official BRITS, SAITS, CSDI, and the proposed multisource quantile model were evaluated with train-only scaling and the frozen 400-epoch budget. Required seeds with `best_epoch < 50` or an epoch-cap hit were excluded. Rankings, checkpoint histories, and stability diagnoses are `model_selection_only`, `formal_evidence=false`, and do not support a “deep learning is ineffective” claim.
- **Text S4: Proposed-model information groups.** S0 is permanent calendar climatology; A is target history/boundary distance, B is same-site hydraulics, C is other-site hydrology and temperature, and D is same-site meteorology. These are predictive information contracts, not a heat-balance decomposition. Validation branch-removal deltas are retained only as mechanism diagnostics.
- **Text S5: Hydrothermal state tables.** [`../results/revision/annual_thermal_metrics.csv`](../results/revision/annual_thermal_metrics.csv) and [`../results/revision/period_thermal_metrics.csv`](../results/revision/period_thermal_metrics.csv) contain every annual P3 minimum/amplitude and the pre/post anomaly SD, acf30, acf90, skewness, and excess kurtosis used in the manuscript.
- **Text S5b: P3 change-date sensitivity.** [`../results/revision/p3_change_point_summary.csv`](../results/revision/p3_change_point_summary.csv) reports Pettitt and least-squares single-break dates, iid reference p values, dependence-aware calendar-year permutation p values, and 365-day residual-block bootstrap intervals. [`../results/revision/p3_change_point_diagnostic.png`](../results/revision/p3_change_point_diagnostic.png) shows why the exact date is method-sensitive. The primary Pettitt interval does not cover commissioning; the least-squares sensitivity interval does.
- **Text S6: Stationarity and low-frequency controls.** [`../results/revision/stationarity_controlled_budgets.csv`](../results/revision/stationarity_controlled_budgets.csv), [`../results/revision/budget_evaluation_summary.csv`](../results/revision/budget_evaluation_summary.csv), and [`../results/revision/dense_skill_sensitivities.csv`](../results/revision/dense_skill_sensitivities.csv) distinguish the frozen prediction from post-hoc 2016--2017, 2016--2020, and annual-demeaned diagnostics added after the frozen analysis.
- **Text S7: Omitted-covariate budget.** [`../results/revision/expanded_covariate_budget.csv`](../results/revision/expanded_covariate_budget.csv) adds same-site air temperature, discharge, and level and donor-site air temperature and discharge to the anomaly regression.
- **Text S8: Frontier-path repair.** The old scenario-resampling dual-frontier path is retired for formal output. Both denominators now use the canonical anchor/year overlap-aware implementation. The climatology rows in [`../results/analysis/dual_frontier_comparison.csv`](../results/analysis/dual_frontier_comparison.csv) match [`../results/analysis/statistical_frontiers.csv`](../results/analysis/statistical_frontiers.csv) cell for cell. The original defect and repair are recorded in `docs/protocol_change_v5_to_v6.md`.
- **Text S9: Corrected hypothesis family.** The family contains 24 candidate model-versus-climatology contrasts and three explicit `reference_not_tested` climatology rows. All finite tests are now `withheld_insufficient_independent_clusters` because each station has one overlap component and three years.
- **Text S10: Cross-fitted node importance.** [`../results/revision/node_importance_cross_fitted.csv`](../results/revision/node_importance_cross_fitted.csv) selects models on other evaluation years and scores the held-out year. The former event-wise best-available table is a descriptive oracle sensitivity only.
- **Text S11: Donor falsification.** Same-day, lag, lead, identity-permutation, and seasonal-residual contrasts are in [`../results/analysis/donor_c_falsification_effects.csv`](../results/analysis/donor_c_falsification_effects.csv). The decision is `falsified_network_propagation` and the permitted language is `correlated_predictive_source_only`.
- **Text S12: Temporally held-out external evaluation.** The complete 540-unit output is bound to the external once-lock. The main sensitivity selects one model per site using only truncated 2021--2022 validation placements and scores it unchanged in 2023--2025. Because the rule was formulated after the once-open envelope, it is post-hoc rather than preregistered. The frozen train-only prediction remains unchanged.
- **Text S12b: Validation-period mask-placement scale.** Fixed-model SDs use 20 validation placements. The manifest proves that inputs end on 31 December 2022, held-out outcomes were not read, and the once-lock was neither read nor modified. These SDs are descriptive noise scales, not confidence intervals for the held-out points.
- **Text S13: Data and software rights.** [`../DATA_RIGHTS.md`](../DATA_RIGHTS.md) and [`../metadata/data_rights.csv`](../metadata/data_rights.csv) govern restricted Jinsha and public USGS/NASA materials. Restricted daily values are not SI data.
- **Text S14: Independently frozen national regulation panel.** [`../results/regulation_panel_v1_legacy_transport/report.json`](../results/regulation_panel_v1_legacy_transport/report.json) contains the primary null discrimination result, adjusted sensitivity, distance profile, source identities, API blocker, transport equivalence audit, and confirmatory-isolation audit. Station metrics, exclusions, predictions, regression coefficients, portable artifact manifest, and clean reproduction instructions are colocated. The panel uses no Chattahoochee data or outcomes. This frozen-panel citation is unchanged.
- **Text S15: Post-hoc within-fold leave-one-ecoregion-out AUC diagnosis.** After the freeze, AUC was computed inside each held-out ecoregion because pooled out-of-fold AUC under leave-one-group-out can attribute intercept and base-rate mismatch to discrimination. [`../results/revision/loeo_within_fold_auc.csv`](../results/revision/loeo_within_fold_auc.csv) reports fold size, dam rate, median out-of-fold probability, and within-fold AUC. Post-hoc mean within-fold AUC is 0.526 and the median is 0.513 (nine defined folds). The post-hoc correlation between fold base rate and fold out-of-fold probability median is $-0.671$. Alaska is undefined ($n=6$, all unregulated). This diagnosis does not replace or reopen the frozen primary pooled AUC of 0.407.

### Table S8. Post-hoc within-fold leave-one-ecoregion-out AUC

Source: [`../results/revision/loeo_within_fold_auc.csv`](../results/revision/loeo_within_fold_auc.csv). Values are rounded for display; the CSV retains full precision. The frozen primary remains the pooled AUC of 0.407.

| Held-out ecoregion | $n$ | Base rate | Median OOF probability | Within-fold AUC |
| --- | ---: | ---: | ---: | ---: |
| NorthEast | 33 | 0.727 | 0.592 | 0.755 |
| EastHghlnds | 31 | 0.710 | 0.596 | 0.742 |
| CntlPlains | 22 | 0.591 | 0.609 | 0.667 |
| MxWdShld | 15 | 0.733 | 0.591 | 0.614 |
| WestMnts | 123 | 0.602 | 0.708 | 0.513 |
| WestXeric | 16 | 0.812 | 0.602 | 0.487 |
| WestPlains | 20 | 0.950 | 0.559 | 0.421 |
| SECstPlain | 6 | 0.167 | 0.609 | 0.400 |
| SEPlains | 63 | 0.508 | 0.652 | 0.132 |
| Alaska | 6 | 0.000 | 0.722 | undefined |

## Evidence boundaries

Validation-only tables are not WRR result tables. The state-matched and annual-demeaned analyses are post-hoc robustness diagnostics and do not replace the frozen prediction. The within-fold leave-one-ecoregion-out AUC table is a post-hoc metric diagnosis and does not replace the frozen pooled AUC. The Chattahoochee result is one temporal/network confirmation, not five independent basins. No application, ecological, or regulatory safe-fill threshold was declared.
