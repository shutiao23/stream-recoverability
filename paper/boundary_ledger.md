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

## BL-016 — E5 specification error (dam detection is not recoverability)

**Observed.** The Phase-2 twin gate scored `is_dam_like` with classification AUC. The operator floor was 0.85 and each univariate ceiling was 0.65. Manifest `results/framework/synthetic_v2/twin_design_manifest.json` records `operator_auc: 1.0`, `univariate_max_auc: 1.0`, `univariate_auc_max: 0.65`, `gate_pass: false`, `hard_negative_gate_pass: false`, and top-level `identifiability_status: operator_separable_univariates_also_separable`. The label is 7 dam-like nodes versus 73 ordinary nodes. Dam-like was generated as a marginal signature (high AR plus isolation). Univariate ACF and donor \(R^2\) therefore separate the same label perfectly. The topology-matched alias that T5 asked for was never instantiated.

**Legal status of `gate_pass: false`.** Uninformative. Wrong estimand, and the univariates also have AUC 1.0. It is not T5 complete. It is not a negative recoverability result. It is not evidence that the Schur operator fails to predict gap skill. Do not quote `identifiability_status` as a pass, a partial pass, or “twins are separable.” Do not retune \(\varphi\), isolation, or noise to manufacture univariate AUC \(\le 0.65\) on dam labels. That would be \(\varphi\)-hacking to save a retired gate.

**Specification error.** v9 already forbids reservoir mechanism in the headline (`reservoir_mechanism_in_headline: false`) and forbids national dam AUC as recoverability evidence. E5 reused dam-detection as the synthetic gate. The next-paper headline is recoverability as a network property. The right synthetic question is whether \(\hat{\mathcal R}\) recovers true recoverability from known \(\Sigma\), not whether it recovers the generator's dam switch.

**Correction (v9.1; locked before any new temperatures).** Dependent variable: true recoverability from known \(\Sigma\) (true conditional risk or true optimal MAE), per node \(\times\) gap length. Metrics: Spearman and calibration slope, not classification AUC. Gate, all required: operator Spearman \(\ge 0.90\) on true recoverability; best of the four preregistered univariates \(\le 0.70\); operator calibration slope \(\in[0.9,1.1]\); Twin E passes as its own cell (do not average Twin E into A–D). Univariates have no calibration requirement. The superseded AUC floor is retained only as an audit of the defect. A hold-out twin family must be locked before scoring; the 14 design graphs are the design suite, not a hold-out identifiability number.

**Twin E is a design correction, not a retune.** Dam-like node and endpoint share the same marginal ACF and the same donor \(R^2\), and differ only in \(\Sigma_{G\mid O}\). Equalize donor \(R^2\) by donor count and direction; use travel-time lag so one node's boundary information is redundant with donors and the other's is complementary. Do not change \(\varphi\) to save any gate. If the operator still cannot beat univariates on Twin E, that is a publishable negative result. Write it. Do not retune.

**Strictness (harder gate, different estimand).** Old: AUC \(\ge 0.85\) and univariate AUC \(\le 0.65\) on dam labels. New: Spearman \(\ge 0.90\) plus univariate Spearman \(\le 0.70\) plus calibration plus an extra hard-negative cell on a continuous, matched-marginal estimand. The 0.70 is not a raised 0.65. Those numbers are not on the same outcome. See `protocol_change_v9_to_v9.1.md` Strictness proof. Development may only raise the new floors, never lower them. This amendment is not licensed by the six-river pilot miss.

**Five questions.**

1. **Is it a validity issue?** YES. Classification AUC on `is_dam_like` is not a recoverability estimand. A joint fail in which univariates also have AUC 1.0 does not validate or falsify \(\hat{\mathcal R}\) as a predictor of gap skill.
2. **Is it a regime boundary?** NO. There is no river regime here. Over-separation on a generator knob is not a SEPlains-class boundary and is not T6. It does not license a weaker real-data T5.
3. **Is it a specification defect?** YES. The frozen E5 gate measured dam detection, which v9 already barred as a headline. Twin A geometry can be interior and still leak a marginal signature. The *gate* is wrong. Retuning the generator to drive univariate AUC to 0.65 would hide the defect.
4. **Does it suggest a redesign of the historical freeze?** NO. Do not unfreeze historical confirmatory outcomes. Do not retarget `design_freeze_v4`. Do not rewrite BL-006 type predictions after seeing them. Do not reopen the 540-unit once-open. Do not change `DEFAULT_DESIGN_PATH`. v9.1 amends the *next* paper freeze only.
5. **Which claim changes?** E5 dam-detection AUC is retired. Current `gate_pass: false` may not be cited as T5 done or as a negative recoverability finding. The next paper must instantiate Twin E and score true conditional risk. The new gate is harder, not easier. Generator retuning to save the old gate remains forbidden. No title license. `formal_evidence` stays false.

**Update.** Keep the published twin manifest as a frozen audit of the wrong estimand. Do not treat operator AUC 1.0 / univariate AUC 1.0 as confirmation, as T5, or as a recoverability failure. Do not claim reservoir causation from synthetic dam labels. Do not loosen T2 because this gate was uninformative.

## BL-017 — Grouping defect (name×HUC2 is not a data limit; HUC8 is a tighter unit)

**Observed.** `cluster_rivers_from_catalog` groups by parsed `river_name` and the first two characters of an unpadded HUC string. Honest public-USGS counts under that rule were written as 98 (name+official HUC2, 3 stations, 8-year *catalog* overlap) and 31 (v1-style 4 stations / 8 years). Those numbers were treated as the method-eligible ceiling. The same on-disk catalog, grouped by HUC8 with ≥3 stations and ≥8-year catalog-span intersection, is **166** under an exact interval scan (W1-A). The reviewer's published **161** is reproduced exactly by naive `str(huc).zfill(8)[:8]`; it is not the official prefix and is not T2. A reviewer-style truncated combo search (n>12 → 12) was tested on this catalog and still yields 166 network rows; truncation undercounts `n_stations` in large groups and does not explain 161. A 4-station HUC8 cut is 105, not 31. Name×HUC2 both splits real networks (renamed tributaries, mainstem plus differently named donors) and invents pseudo-networks (`missouri_river_huc10`: 18 catalog stations occupy 15 HUC8 codes, not one recoverability network; only 3 of those HUC8s currently form a 3-station/8-year cluster that still contains those sites).

**This is not a 4-station/HUC2 scrape of 150.** v9 already locked the scientific station floor at 3 (`inventory_targets.stations_per_network_min: 3`). The 4-station validator lag is a known contract lag, not this amendment. HUC8 is a hydrologic subbasin (about 1,000–5,000 km²). HUC2 is a region. Replacing a regional name-string with a subbasin polygon is a **different, spatially tighter unit**. It splits Missouri-style fakes and it can join differently named stations that actually share a subbasin. The net count moving 98 → 166 is therefore not extra rivers found by loosening. Writing it that way is a **claim violation**. Pre-empted here. Do not mix this change with the v9 failure hatch “if qualified networks <100, relax to 3 stations / 6 years.” That hatch is unused until post-QC qualified count is known.

**166 is not T2 and 161 was not an exact official inventory.** Catalog `daily_begin`/`daily_end` intersection is not 300 approved days × 8 years. It is not post-download concurrency (the 12→6 collapse already proved catalog span ≠ same-day overlap). Pre-registered attrition after download and ingest QC is 25–40%. \(166\times 0.65\approx 108\) can still sit above the network-CI floor of 100 and still miss the inventory *target* of 150. 108 is not 150. 166 is not confirmatory. Do not download the 98-list. Do not treat the v2 mixed-name HUC8-only table (which also happened to print 166) as the W1-A inventory. Do not count Loire or Swiss daily years that were never public.

**Connectivity.** HUC8 does not guarantee flow connection. NLDI UM+DM is required. Groups whose NLDI status is `false` or `partial` are marked `spatially_proximate_not_flow_connected` and retained as a covariate, not dropped. Pairwise caps, if used, are geodesic kilometres. Missing lat/lon is an explicit policy, not silent 0/inf.

**never_sealed.** Inherit the fourteen freeze tokens exactly. Do not rename `delaware_river_huc20`, `cahaba_river_huc31`, `mahoning_river_huc50`, `suwannee_river_huc31` to padded HUC2 IDs. Loire / Swiss still cannot fill T8 or the 10 non-North-America sealed seats. Split 50/20/30, stratified climate × regulation × size, seed and SHA-256 locked before download. Point at `configs/network_catalog_v3_huc8.yaml` and `configs/network_catalog_v3_split.yaml` when those files exist.

**Five questions.**

1. **Is it a validity issue?** YES. A name×HUC2 string is not an independent river network. Treating 98/31 as a data ceiling invalidates any claim that T2 is blocked by USGS scarcity. Treating reviewer 161 or W1-A catalog 166 as qualified networks would be the opposite validity error.
2. **Is it a regime boundary?** NO. Grain of grouping is not a climate or regulation regime. Nested tributaries (McKenzie ⊂ Willamette; Santa Fe ⊂ Suwannee) remain a unit-independence issue to flag; they are not a new scientific regime and not a license to count both as independent bootstrap clusters without a flag.
3. **Is it a grouping defect?** YES. The estimator of “how many networks exist” was a `groupby` on a parsed title and a raw prefix. Same class as BL-011 question 3: the implementation produced the number. HUC8 + exact max-overlap subset is the correction. It is stricter spatially, not looser. Reviewer 161 equals naive zfill on this catalog; a truncated search does not produce it. W1-A 166 is the exact catalog-level figure and is still not T2.
4. **Does it suggest a redesign of the historical freeze?** NO. Do not unfreeze historical confirmatory outcomes. Do not retarget `design_freeze_v4`. The historical Chattahoochee panel remains one Upper-to-Middle mainstem as already written. Do not remap `network_catalog_v1.yaml` into sealed. Do not reopen BL-006. Do not delete `recoverability_study_freeze_v1.yaml`. v9.1 amends the next-paper freeze only.
5. **Which claim changes?** The honest *catalog* count is W1-A HUC8 overlap **166**, labelled catalog-only, not T2. Reviewer 161 is naive `zfill(8)[:8]`, not the official inventory and not a truncated-combo count. The 98/31 figures remain as a contrast audit of the defective grouper. Do not claim extra rivers by loosening. Do not claim T2 inventory is in hand. Attrition 25–40% is preregistered. Network-level CIs still require ≥100 qualified networks after QC; 12-river and 6-river pilots still cannot report them (BL-012 internalized). `never_sealed` unchanged. No title license.

**Update.** Keep 98/31/reviewer-161/W1-A-166 as labelled catalog statistics. Do not sell 166 as recoverability evidence, as a qualified corpus, or as a T2 pass. Do not sell 161 as the exact count. Do not download the wrong candidate set. Do not loosen Spearman 0.60 or the 0.40 CI floor because grouping was repaired.

## BL-018 — FOEN public-daily condition satisfied; Swiss split locked before values

**Observed without temperature values.** On 2026-08-26 the official FOEN data platform exposed an unauthenticated `data_1day_mean` GraphQL table with water-temperature parameter `WT`, dated rows, units, and release states. The W6 probe selected only timestamp/parameter/unit/release metadata for station 2016; it did not select `value`. Seven daily timestamps were returned for 1–7 January 2025, all release state 2. The older repository statement that all historical FOEN daily data require a manual order is obsolete. The manual service still exists for legacy/special products.

**Conditional exclusion, not a relaxed gate.** v9/v9.1 excluded Swiss from T8 and the ten non-North-America sealed seats *until daily values were public and dated*. That source-availability condition is now satisfied. It permits a prospective split before values are opened. It does not make a station or network qualified, does not replace the 300-day/eight-common-year QC rule with metadata, and does not count anything toward T8 today.

**Burn and lock.** Station 2016 was touched by the timestamp probe, so its complete Aare metadata group is permanently `foen_aare_aaregebiet`, role `never_sealed`, `development_burned: true`. The remaining temperature-location metadata yield exactly ten unprobed accent-normalized river×catchment groups: Doubs, Emme, Inn, Linth, Reuss, Rhein, Rhône/Rhone (merged, not double-counted), Simme, Thur, and Ticino. They are prospectively `sealed`. Seed `20260826`; canonical split SHA-256 `4405cf690ccf9d9b62a8dfa76d2d1d74806e662835bff0043ee9fe1e5619ae59`; catalog SHA-256 `2e348f571a6e19025d8f6d6aca2dfe55997927b94a608a78baedd89819a78727`. No temperature value was queried.

**Metadata boundary.** The builder intersects current FOEN station metadata with the pre-existing water-temperature station inventory, keeps river water-body types, and groups accent-normalized `riverName × catchmentName` at a three-station minimum. `coverageFrom/coverageTo` are not requested and cannot be used as qualified years. Coordinates and maximum pairwise distance are diagnostics. Flow connectivity, daily density, common years, and independent-network eligibility remain unknown until the authorized sealed path is opened once.

**Five questions.**

1. **Is it a validity issue?** YES. Treating a public API timestamp as eight qualified years would be invalid. The lock explicitly claims zero qualified Swiss networks.
2. **Is it a regime boundary?** NO. This is a source-availability/governance transition, not a hydrologic result.
3. **Is it an implementation defect?** The old “manual order only” assumption became stale when FOEN launched its public platform. Correcting source capability before values are opened is not outcome-driven.
4. **Does it redesign the historical freeze?** NO. `design_freeze_v4`, the fourteen inherited never-sealed tokens, old once-open results, and all T2/E5 gates remain unchanged. Station 2016 adds a source-local burn; it does not remove or rename an inherited token.
5. **Which claim changes?** Prospective Swiss sealed seats may now be locked. T8 remains zero for Swiss until post-unseal provider QC proves three stations × eight common qualified years. Failed sealed candidates are not replaced after outcomes are seen.

**Update.** Use `configs/foen_prospective_catalog_v1.yaml` with the corrected
`configs/foen_prospective_split_v2.yaml`. The v1 value-query pilot produced 208
identical opaque GraphQL error bodies because `releaseState` is not a valid
provider filter; those objects remain sealed and are never reused. The v2 query
changed only that API-schema defect, retained membership/roles, and completed
2,652/2,652 write-only custody objects with zero failures. Future unsealing and
QC remain unauthorized until the frozen T2 model is ready. See
`docs/protocol_condition_foen_public_daily_v9_1.md` and
`docs/protocol_deviation_foen_failed_pilot_v1_to_v2.md`.
