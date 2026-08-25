# Boundary ledger

## BL-001 — Proposed/deep model roster

**Observed.** Required seeds for BRITS, CSDI, and the proposed model selected before epoch 50 or otherwise failed the frozen stability path. Proposed lost 27 of 36 difficult validation cells to donor regression.

**Update.** No deep model enters the formal roster. All rankings and architectures move to SI. Excluded runs cannot support a model-class conclusion.

## BL-002 — Universal analytic ceiling

**Observed.** The frozen curve tracks internal best-envelope shape, but 20 of 45 point estimates and nine lower confidence bounds exceed it. Every lower-bound exceedance is at thermally nonstationary P3; B1/S2 have none.

**State controls.** A post-hoc 2016--2020 calibration/denominator reduces lower-bound exceedances to one and reverses 365-day P3 XGBoost skill from 0.209 to -0.588. Annual demeaning retains 0.164 skill.

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

**Update.** Keep 0.407 as the frozen primary headline. Label the within-fold table, the mean of 0.526, the correlation of $-0.671$, and C5 as post-hoc. Do not claim that national discrimination is now supported.
