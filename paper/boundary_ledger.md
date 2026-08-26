# Boundary ledger

## BL-001 — Proposed/deep model roster

**Observed.** Required seeds for BRITS, CSDI, and the proposed model selected before epoch 50 or otherwise failed the frozen stability path. Proposed lost 27 of 36 difficult validation cells to donor regression.

**Update.** No deep model enters the formal roster. All rankings and architectures move to SI. Excluded runs cannot support a model-class conclusion.

## BL-002 — Universal analytic ceiling

**Observed.** The frozen curve tracks internal best-envelope shape, but 20 of 45 point estimates exceed it. A historical count of nine lower confidence bounds exceeding the heuristic, all at P3, is an audit of the old interval construction only; those bounds are withheld because each station has fewer than five independent clusters.

**State controls.** A post-hoc 2016--2020 calibration/denominator reverses 365-day P3 XGBoost skill from 0.209 to -0.588. The matching historical lower-bound audit count falls from nine to one and is still not an inferential claim. Annual demeaning retains 0.164 skill.

**Update.** Withdraw the universal information-ceiling claim. Retain a conditional state-specific shape heuristic. Do not claim that three stations prove a stationary ceiling.

## BL-003 — Frontier-path divergence

**Observed.** `statistical_frontiers.csv` and `dual_frontier_comparison.csv` used different resampling paths and disagreed on identical climatology cells.

**Correction.** Both denominators now use the canonical overlap-aware anchor/year path. All 27 climatology frontier/censoring cells match exactly. See `docs/protocol_change_v5_to_v6.md`.

## BL-004 — Degenerate climatology p-values

**Observed.** All anchors at one station were collapsed to one connected overlap component, so a Wilcoxon test with $n=1$ returned $p=1$ in every row.

**Correction.** Use one cross-gap mean per anchor/year after seed collapse. There are 24 actual finite tests and three explicit reference rows. Fourteen pass BH; seven are positive and seven negative.

## BL-005 — Model-damage node importance

**Observed.** The old same-model estimator produced B1/S2 donor-regression impacts of 2.42/1.98 °C because impaired models performed far worse than climatology.

**Intermediate correction.** Event-wise best-model reselection with a climatology cap reduced the headline values but still chose a model using the scored event, so it is retained only as a descriptive oracle envelope.

**Paper estimand.** For each target, gap, and failure set, leave one evaluation year out, select the lowest-MAE roster model on the other years, and score the fixed choice on the held-out year. S2→B1 is 0.105 °C (95% interval 0.044--0.169); no S2-target contrast excludes zero. This is a post-hoc non-oracle sensitivity, not independent confirmation.

## BL-006 — External confirmation

**Frozen prediction.** Site 02334430 was the only memory-dominated site; the other four were donor-dominated. Full predicted curves were written before confirmation.

**Observed once.** All 540 run units completed. The best-roster envelope gives site 02334430 the largest 30-to-180-day decline and lowest 180-day skill, but it selects the maximum observed performance in each scored cell and is descriptive only.

**Non-oracle sensitivity.** Mean 2021--2022 validation performance selects XGBoost at all five sites. Scored unchanged in 2023--2025, it is weakest at 02334430 at 90 and 180 days (-0.380/-0.300), while donor sites retain 0.555--0.746 skill at 180 days. The rule was formulated after the once-open result, so the paper calls this a held-out post-hoc sensitivity rather than preregistered confirmation.

## BL-007 — Submission compliance

**Release status.** The public history is rewritten to code-only scope after creating a verified private bundle and old-to-new commit map. The public audit reports zero restricted tracked paths. No archival software DOI yet exists, and AGU/editor acceptance of the restricted-data exception has not been obtained.

**Boundary.** The manuscript must not be submitted until a real archival DOI exists, the editor accepts the restricted-data plan, and confidential reviewer files are uploaded through AGU GEMS. Restricted data remain outside the public release.

## BL-008 — P3 change-date localization

**Observed.** Dependence-aware Pettitt inference estimates 26 May 2013 (95% block-bootstrap interval 14 May 2011--22 October 2013; year-block $p=0.0088$), which does not cover first-unit operation. Least-squares single segmentation estimates 18 October 2014 (interval 16 April 2014--1 January 2015; $p=0.0117$), which does cover it. Lag-1 anomaly autocorrelation is 0.973.

**Update.** Describe a significant but method-sensitive state change and a 2015 annual endpoint shift. Do not state that Pettitt statistically located commissioning or that the break test establishes reservoir causality.

## BL-009 — External single-placement uncertainty

**Observed.** The confirmatory panel has one frozen mask per station--gap--information cell. Type ordering is not present at 30 days. On 2021--2022 validation data, 20-seed best-roster placement SD ranges from 0.038 to 0.182 at 180 days; seed-paired donor-minus-02334430 SD is 0.109--0.128.

**Update.** The main figure reports the validation-selected fixed-model sensitivity, not the event-wise best envelope. Its long-gap ordering is present at 90 and 180 days. Error bars use the matching fixed-model validation placement SD and are explicitly not confidence intervals for the held-out point.

## BL-010 — National generalization

**Frozen primary result.** In the transport-limited maximum legal panel ($N=335$), the unadjusted index association is not significant (OR 1.23, 95% CI 0.93--1.61; $p=0.144$) and leave-one-ecoregion-out AUC is 0.407 (0.222--0.515). Stand-alone national discrimination is not supported.

**Supporting structure.** The adjusted OR is 2.52 (1.18--5.36) but has a fixed-effect separation warning. Within regulated watersheds, median index declines monotonically from 0.0110 within 5 km to 0.00463 at 50--100 km.

**Update.** Retain the primary null and restrict the mechanism to a geography-dependent local fingerprint. Do not call the index a universal dam classifier. BL-010 recorded the regime boundary and the claim change; it did not ask whether the pooled estimator itself was an implementation defect. That question is answered in BL-011.

## BL-011 — Pooled LOEO AUC as a generalization metric

**Frozen primary (unchanged).** Transport-limited maximum legal panel, $N=335$. Unadjusted OR 1.23 per index SD (95% CI 0.93--1.61; $p=0.144$). Pooled leave-one-ecoregion-out AUC 0.407 (ecoregion-cluster bootstrap 0.222--0.515). This number remains the frozen primary. An AUC near 0.5 does not reopen the freeze.

**Post-hoc diagnosis (does not reopen the freeze).** Mean within-fold AUC 0.526; median 0.513; min 0.132 (SEPlains, $n=63$, base rate 0.508); max 0.755 (NorthEast, $n=33$, base rate 0.727). Fold base rates range from 0 (Alaska) to 0.95 (WestPlains). Correlation of fold base rate with fold out-of-fold probability median is $-0.671$. Alaska has the highest fold median out-of-fold probability (0.722); WestPlains has the lowest (0.559) despite a 0.95 dam rate.

**Five questions.**

1. **Is it a validity issue?** YES. Pooled out-of-fold AUC under leave-one-group-out with heterogeneous base rates is not a valid standalone generalization metric.
2. **Is it a regime boundary?** YES. Fold AUCs 0.13--0.76 show geography-dependent direction, including a Southeast Plains reversal.
3. **Is it an implementation defect?** YES. The implementation pools fold-calibrated probabilities, so fold intercept mismatch is scored as (anti)discrimination. This is why 0.407 fell below 0.5.
4. **Does it suggest a redesign?** NO. Do not unfreeze, do not change the primary estimator after seeing it, and do not rerun the panel. Report within-fold AUC as a labelled post-hoc diagnosis.
5. **Which claim changes?** C4 reason and numbering: the national null stands, but 0.407 is downward-biased as a discrimination measure; the fairer level is about 0.53. NEW C5: the fingerprint's direction is region-dependent. The primary null is retained. The freeze is not reopened.

**Prior ledger gap.** BL-010 answered only the regime-boundary and claim-change questions and skipped the implementation-defect question.

**Update.** Keep 0.407 as the frozen primary number but not as a valid headline estimand. Label it a preregistered defective diagnostic. The valid post-hoc level is the mean within-fold AUC of 0.526. Do not claim that national discrimination is now supported.

## BL-012 — Overlap-aware inference withholding

**Observed.** Frontier tables recorded `n_hypothesis_clusters=1` and `n_bootstrap_clusters=3` while Wilcoxon tests treated 19--20 overlapping anchors as independent units, producing $10^{-6}$ p-values. Cross-fitted node-importance intervals resampled nested gap/anchor events within three years.

**Correction.** The only admissible unit is a site-year or overlap component. Below five independent clusters, p-values, BH decisions, statistical-frontier crossings, and bootstrap confidence intervals are withheld. Descriptive skill, MAE, and cross-fitted point estimates remain. See `docs/protocol_change_v6_to_v7.md`.

## BL-013 — Headline claim downgrade

**Observed.** The title, abstract, and conclusions treated a post-hoc Chattahoochee XGBoost rule and the defective pooled AUC as confirmatory support for “Reservoir-Associated Thermal Structure Predicts…”.

**Correction.** The title is now a case-study heuristic. Fixed-model external scores and national fold AUCs are labelled post-hoc. Reservoir causation, station-protection policy, and confirmatory significance are withdrawn.

## BL-014 — Jinsha source-quality boundary

**Observed.** Fifteen complete years of T/F/L have no per-value quality codes, instrument or calibration records, time zone, hydrological-day cut-off, or proof that daily temperatures were never interpolated.

**Update.** Jinsha remains an exploratory context network. Dates that cannot be shown to be uninterpolated are not fully traceable artificial-mask truth. A sealed request list is in `metadata/source_documentation/source_provenance_v3.md`.

## BL-015 — Hard type labels forced by donor $R^2$

**Observed.** The frozen classification is donor-dominated when the donor component is at least the memory component. Memory is $(1-R^2_{\mathrm{donor}})\rho^2(d/4)$ and $\rho^2\le 1$, so $R^2_{\mathrm{donor}}\ge 0.5$ forces a donor-dominated label at every horizon, regardless of local memory. This is the identity implemented as `forced_donor_dominated` in `heuristic_degeneration.py`, not an empirical discovery from either river.

**Thirty-day station table.** Source: `results/revision/recoverability_type_classification_uncertainty.csv` at `gap_length=30`. Theoretical memory ceiling is $1-R^2_{\mathrm{donor}}$ (`max_memory_component` in `degeneration_bound`). The CSV agrees with the rounded review table; values below are the CSV figures rounded to three decimals.

| site | $R^2_{\mathrm{donor}}$ | memory | label | ceiling | forced |
| --- | ---: | ---: | --- | ---: | --- |
| 02335000 | 0.853 | 0.043 | donor | 0.147 | yes |
| 02335450 | 0.913 | 0.027 | donor | 0.087 | yes |
| 02336000 | 0.925 | 0.019 | donor | 0.075 | yes |
| 02337170 | 0.868 | 0.031 | donor | 0.132 | yes |
| B1 | 0.464 | 0.058 | donor | 0.536 | effectively yes ($\rho$ too small to flip) |
| S2 | 0.470 | 0.079 | donor | 0.530 | effectively yes |
| 02334430 | 0.367 | 0.507 | memory | 0.633 | no |
| P3 | 0.106 | 0.553 | memory | 0.894 | no |

Four stations satisfy $R^2_{\mathrm{donor}}\ge 0.5$ and are formula-forced. B1 and S2 lie just below 0.5 and are **not** identities of `forced_donor_dominated`. A memory label would require $\rho^2>D/(1-D)$ (0.867 at B1; 0.886 at S2); realized 30-day memory is 0.058 and 0.079. Those two labels are empirically unflippable at the realized autocorrelation, not formula-forced. Only 02334430 and P3 are memory-dominated and not forced.

**Consequence.** Four of eight labels are identities of $R^2_{\mathrm{donor}}$. Two more are practically unflippable given realized ACF. Only two stations carry an unforced memory label. On this $n=8$ set, sorting by donor $R^2$ recovers P3 then 02334430; ranking by published acf30 recovers the same pair (02334430 0.762, P3 0.590; next is 02335000 at 0.397). That is not a claim that every univariate does: annual range ranks P3 (14.5) next to 02335000 (14.8). A real-data nested ablation of incremental $\Delta R^2$ versus donor-$R^2$-only was never reported. `results/framework/baseline_nested_r2.csv` is a synthetic nested sequence and is not a substitute.

**Topology alias.** `results/revision/topology_confound_audit.csv` records P3 as `downstream_terminus` and 02334430 as `upstream_origin`; both memory labels are aliased with endpoint geometry and one-sided donors. Site 02337170 is a downstream terminus but donor-dominated ($R^2_{\mathrm{donor}}=0.868$, formula-forced). That $n=1$ counterexample shows endpoint position does not determine type. It is not causal proof and does not identify a reservoir mechanism.

**Five questions.**

1. **Is it a validity issue?** YES. A label that is an identity of $R^2_{\mathrm{donor}}$ is not a recoverability type.
2. **Is it a regime boundary?** The two unforced memory labels coincide with network endpoints. That alias is recorded; it is not a new regime or reservoir claim.
3. **Is it a design defect?** YES. The additive $d/4$ rule cannot emit a memory label once $R^2_{\mathrm{donor}}\ge 0.5$. This is the same class of defect as BL-011 question 3: the estimator, not the river, produced those four labels. B1 and S2 are not in that identity set.
4. **Does it suggest a redesign of the historical freeze?** NO. Do not unfreeze historical confirmatory outcomes, do not retarget `design_freeze_v4`, and do not rewrite BL-006 type predictions after seeing them.
5. **Which claim changes?** Hard type labels are retired as a primary finding. Under v9 the additive heuristic is univariate baseline #4, not the operator. The next paper must report incremental $\Delta R^2$ on real data after donor $R^2$.

**Update.** Keep the eight-station 30-day numbers as a frozen audit of the formula identity. Do not treat donor/memory hard labels as a confirmed scientific partition. Do not claim reservoir causation from the endpoint alias or from 02337170.
