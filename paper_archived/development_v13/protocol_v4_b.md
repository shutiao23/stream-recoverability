# Protocol v4 (agent b): third confirmation panel for support-aware model selection in stream-temperature gap recovery

| field | value |
| --- | --- |
| protocol_id | `revision_v13_confirmation_panel_v4_agent_b` |
| status | `draft_pending_external_registration_before_outcome_scoring` |
| target_journal | Water Resources Research |
| supersedes | `revision_v12_confirmation_panel_v3` (both agent drafts: `results/revision_v12/t12_confirmation_protocol/agent_a/protocol_v3.md`, `agent_b/protocol_v3.md`); v3 superseded the internally hash-bound second panel (57 scored networks) |
| evidence_role | third, outcome-disjoint confirmation panel; externally registered before any v4 outcome is computed or viewed |
| authoring agent | agent b (adversarial pair), namespace `paper/development_v13/`, sibling `protocol_v4_a.md` reconciled by a senior reviewer |
| frozen before | any v4 recovery outcome is viewed or scored (Section 9) |
| v12 evidence inputs (read-only, cited) | `results/revision_v12/t03_baseline_ladder/agent_a/master_ladder_table.csv`, `results/revision_v12/t03_baseline_ladder/agent_b/paired_delta_vs_r6_station_x_horizon.csv`, `results/revision_v12/t03_baseline_ladder/agent_b/paired_delta_vs_empirical_curve.csv`, `results/revision_v12/t03_baseline_ladder/agent_b/paired_delta_vs_r8_simple_routeA.csv`, `results/revision_v12/t03_baseline_ladder/agent_b/per_horizon_network_spearman.csv`, `results/revision_v12/t09_decision_utility/agent_a/selection_regret_table_part2.csv`, `results/revision_v12/t09_decision_utility/agent_a/abstention_curve_part2.csv`, `results/revision_v12/t09_decision_utility/agent_a/selection_predictions_part2.csv`, `results/revision_v12/t09_decision_utility/agent_a/abstention_comparison_part2.csv`, `results/revision_v12/t09_decision_utility/agent_a/bootstrap_part2.csv`, `results/revision_v12/t09_decision_utility/agent_a/selection_calibration_part2.csv`, `results/revision_v12/t09_decision_utility/agent_a/utility_table_part1.csv`, `results/revision_v12/t09_decision_utility/agent_a/bootstrap_part1.csv`, `results/revision_v12/t12_confirmation_protocol/agent_b/power_analysis.csv`, `results/revision_v12/t12_confirmation_protocol/agent_b/power_analysis_summary.json`, `paper/development_v12/manuscript_v12.md` |

---

## 1. Rationale and changes vs v3

### 1.1 What the review rejected in v3

The third-panel review rejected protocol v3 as currently registrable on three grounds, all documented in the v12 artifacts:

1. **The v3 primary endpoint is no longer acceptable.** v3's binding primary was the paired network-level ΔRho between the fitting-period empirical-transfer curve and the simple-descriptor model on direct-support units (horizons 7/30/90/180 d), powered on the second-panel anchor +0.038. The v12 baseline ladder (t03) showed that the *station × horizon historical mean* (ladder rung r6, a pure fitting-record statistic: per station, per gap length, the mean fitting-period recovery loss) is the true strongest fitting-record baseline and nearly matches the full empirical-transfer curve:
   - second panel, 874 direct-support units, 57 networks: r6 pooled Spearman **0.9424** vs empirical curve 0.9453; r6 network-level Spearman 0.7632 vs empirical 0.8049; paired network-level Δ (empirical − r6) **+0.042** with 95% CI [0.0001, +0.1117] (lower bound effectively zero) and pooled Δ +0.0029 [−0.0005, +0.0066] (straddling zero) (`master_ladder_table.csv`, `paired_delta_vs_r6_station_x_horizon.csv`).
   - first panel, 858 direct-support units, 42 networks: r6 pooled 0.8250 vs empirical 0.8254; paired pooled Δ −0.0002 [−0.0041, +0.0039] (`paired_delta_vs_empirical_curve.csv`).
   - A "superiority over the strongest fitting-record baseline" claim built on that anchor is not confirmable, and the +0.038 anchor itself is no longer usable.
2. **The v3 triage endpoints are obsolete.** v3's captured-loss endpoints pitted the empirical predictor against random prioritization; but t09 part 1 showed the empirical predictor is the *worst non-random* prioritization policy: CapturedLoss@20% 0.338 [0.302, 0.380] vs simple descriptors 0.512 [0.485, 0.537], paired difference **−0.174 [−0.198, −0.140]** (`bootstrap_part1.csv`). Captured-loss superiority of the frozen empirical predictor is therefore falsified in the fitting-record context and cannot anchor a confirmation.
3. **The only positive decision signal is a proof of concept with unacceptable coverage.** t09 part 2 found that a support-aware, ambiguity-flagging family selector reaches network-balanced selection regret **0.0067** (95% CI [0.0019, 0.0120]) with comparators on the same released units at 0.145–0.341 — but only at **8.5% released-unit coverage (123 units, 8 of 42 networks)** under support-any + ambiguity abstention (`selection_regret_table_part2.csv`). Coverage floors are mandatory: the reviewer requires ≥ 50% released units and ≥ 60% released networks (70% target), a full coverage–regret curve, and a power analysis built around the *regret* endpoint rather than ΔRho.

### 1.2 How v4 fixes each failure

| # | v3 defect (review finding) | v4 fix | clause |
| --- | --- | --- | --- |
| R1 | Primary endpoint (paired ΔRho vs simple descriptors on direct-support units) anchored on an effect (+0.038) that vanishes against the strongest fitting-record baseline (r6 station × horizon mean; +0.042, CI at zero) | Primary endpoint replaced by the **network-balanced selection-regret difference between the proposed support-aware selector and the deployable nested-CV selector at fixed coverage** (Section 2.2); rank comparisons are demoted to key secondary endpoints, one of which is the direct-support paired rank **vs the r6 station × horizon mean** (Section 2.3.1) | 2.2, 2.3.1 |
| R2 | Triage endpoints (CapturedLoss vs random) claim a capacity the frozen predictor does not have (−0.174 [−0.198, −0.140] vs simple) | All captured-loss/NDCG superiority endpoints are **removed as claim-bearing**; they survive only as disclosed diagnostics (abstention loss-share accounting, Section 10.6) | 2.1, 10.6 |
| R3 | Positive signal (regret 0.0067) exists only at 8.5% coverage on 8 networks — proof of concept | Coverage becomes a design requirement: (i) frozen coverage floors ≥ 50% released units / ≥ 60% released networks, 70% target (Section 3.2); (ii) complete per-network fitting-period stress construction with a fitting-record placement budget sized by a pre-outcome coverage simulation (Section 7.2) — the v12 8.5% coverage was an artifact-availability limit (t05 stress existed for only 8 networks), not a method limit; (iii) automatic downgrade rule when realized coverage is below floor (Section 3.4) | 3.2, 3.4, 7.2 |
| R4 | Power analysis was built on the ΔRho endpoint (+0.038 anchor) | Power analysis is **simulation-based on the regret endpoint**, networks as bootstrap units, effect scenarios anchored on the v12 released-unit regret gap and discounted for the higher-coverage operating point; the +0.038 ΔRho effect is not reused (Section 4.4; Appendix C) | 4.4 |
| R5 | Abstention rules (support tiers + extrapolation) were defined but coverage-cost was not quantified | Abstention is governed by the frozen triple rule **support-any + ambiguity + LCB > 0** with explicit abstention-cost reporting (loss share, unit counts, network counts, mechanism composition; Section 2.3.3, 10.6) | 2.3.3 |
| R6 | Endpoint set retained triage machinery with no decision framing | Endpoints are organized as: primary (selection-regret difference at fixed coverage), key secondaries (r6 paired rank, per-horizon rank, calibration, coverage–regret curve + area under selective-risk curve, model-family matrix), and downstream thermal distortion endpoints with an explicit incremental-benefit definition B = D(default) − D(model) − λC (Sections 2.4, 8) | 2.2–2.4, 8 |
| R7 | Model roster lacked a fully trained neural model and deployment defaults | Roster adds the **fully-trained mask-aware BiLSTM (≥ 3 seeds, source = target instance**: each network trains its own instance on its own fitting record, no cross-network transfer) and the **climatology and interpolation defaults** (Section 6); air2stream retained where forcing permits | 6 |
| R8 | Missingness manifest was mechanism-only | Missingness manifest frozen: mechanism definitions (both the v12 placement-mechanism taxonomy and the provider-recorded class taxonomy), **real NASA POWER air temperature** at station coordinates as the only forcing source, **no donor-proxy forcing** (Section 5.5) | 5.5 |
| R9 | Inference did not incorporate provider structure | **Networks are the bootstrap units; providers are strata**; a provider-blocked bootstrap is a prespecified sensitivity (Sections 4.2, 10.2) | 4.2, 10.2 |
| R10 | Registration workflow existed but endpoint/margin churn between v3 drafts was possible | Registration workflow is strict and unchanged in spirit: pre-outcome public commit → OSF/Zenodo registration with DOI → outcome-scoring commit binding the DOI (Section 9); post-outcome amendment policy is frozen (Section 9.5) | 9 |

### 1.3 Provenance of every number in this protocol

All empirical numbers cited in this protocol come from the v12 artifacts listed in the metadata table (read-only inputs; none were recomputed or extended). No number was invented; where a quantity is needed that no artifact provides (e.g., the regret gap at 50–70% coverage, or the correlation between selector regrets), the protocol specifies that it **must be estimated pre-outcome** by the frozen analysis scripts and reports the estimation procedure and its inputs (Sections 4.4, 7.2, Appendix C). Placeholder values in worked examples are explicitly labelled as such.

---

## 2. Scientific questions and endpoints

### 2.1 Scientific questions

- **Q1 (primary)**. At a fixed, high released coverage (≥ 50% of units, ≥ 60% of networks; 70% target), does the proposed support-aware, uncertainty-penalized family selector achieve lower network-balanced selection regret than the deployable nested-CV selector, and lower regret than a development-chosen best fixed model by ≥ 20%?
- **Q2**. Does the fitting-period empirical-transfer machinery add rank value over the strongest fitting-record baseline (r6 station × horizon mean) on direct-support units, and per horizon, on an outcome-disjoint panel?
- **Q3**. Is the support-aware selector calibrated (equal-network-weighted slope in [0.90, 1.10]) on its released units, and what is the full coverage–regret trade-off (area under the selective-risk curve)?
- **Q4**. Do model-selected reconstructions reduce downstream thermal-metric distortion (degree days, annual mean, p90, 7-day mean of daily max, threshold-exceedance days, summer mean) relative to climatology and interpolation defaults, net of abstention cost?
- **Q5**. How do all rostered model families rank on a common panel (model-family matrix), and does the family-specific self-transfer stress curve degrade differently across families?

### 2.2 Primary endpoint: network-balanced selection-regret difference at fixed coverage

**Unit.** A unit u = (network n, station s, gap length g) is a station-gap row with an observed recovery loss L(u) (mean over placement-level `mae_deg_c` across the unit's evaluation placements, as in the v12 scoring).

**Family set.** The rostered candidate families F(u) are defined per unit in Section 6.1. In the primary configuration, F(u) excludes the two defaults (climatology, interpolation), which are baselines and downstream references; a registered sensitivity configuration includes them (Section 6.5).

**Per-unit selection regret.**

Regret(u) = L_selected(u) − min_{m ∈ F(u)} L_m(u),                              (1)

where L_selected(u) is the observed loss of the family the selector chose for u and min_m L_m(u) is the observed loss of the family with the smallest observed loss on u (the oracle family). Regret is a nonnegative quantity; the oracle achieves zero regret.

**Network-balanced averaging.** For a network n with released units U_n (Section 2.3.2), the within-network mean regret is

R̄_n = (1 / |U_n|) Σ_{u ∈ U_n} Regret(u),                                     (2)

and the network-balanced panel regret is

Regret(S) = (1 / |N_rel|) Σ_{n ∈ N_rel} R̄_n,                                   (3)

where N_rel is the set of networks with at least one released unit. Network-balanced averaging weights every releasing network equally regardless of unit count; pooling is reported only as a diagnostic (Section 10.4).

**The proposed support-aware selector.** Defined in full in Section 7: for each unit, it estimates per-family recalibrated risk r_m(u) = a_m + b_m·s_m(u) + λ·w_m(u) (stress s_m, interval width w_m, width penalty λ = 0.5 frozen, recalibration coefficients a_m, b_m fit on fitting-period data only), selects the family with the smallest r_m(u), and releases the unit only if the frozen abstention triple holds (support-any, ambiguity, LCB > 0; Section 2.3.3).

**The deployable nested-CV selector (primary comparator).** Defined in Section 7.4: a selector that uses only fitting-period information and never abstains — per-unit leave-one-placement-out CV within the unit's own fitting placements when ≥ 2 placements exist for all candidate families, otherwise stratum-blocked leave-one-network-out CV over pooled fitting records (falling back to global leave-one-network-out CV when the stratum has < 3 networks). This is the selection procedure a practitioner can actually deploy on a new network before any outcome is observed.

**Fixed-coverage evaluation protocol.** The frozen operating point (Section 7.2) is applied at scoring; the realized released set R* is the union of released units across scored networks. The primary comparison evaluates **both selectors on the identical released set R*** (coverage-matching; comparators do not get to abstain). Let

ΔRegret = Regret_proposed(R*) − Regret_nestedCV(R*).                            (4)

The panel-level inference is the network bootstrap over scored networks (Section 10.2): 2,000 resamples of networks with replacement; within each draw, per-network R̄_n values are recomputed for both selectors on the drawn networks' released units, and ΔRegret is recomputed; the 95% percentile CI is reported.

**Registration:** the primary endpoint is ΔRegret at the realized operating point, with success criteria in Section 3.3 (CI entirely below 0 AND ≥ 20% relative regret reduction vs best fixed model, at realized coverage ≥ 50% units / ≥ 60% networks).

### 2.3 Key secondary endpoints

#### 2.3.1 Direct-support paired rank vs station × horizon mean (r6)

On direct-support units only (g ∈ {7, 30, 90, 180} d), per network, compute Spearman(selected-family prediction, observed loss) − Spearman(r6 prediction, observed loss), where the r6 prediction is the station × horizon fitting-record mean (t03 ladder r6, refit inside the network's own fitting period). The endpoint is the network-bootstrapped mean paired difference Δρ_r6 with a 95% CI (2,000 draws). This endpoint replicates the t03 finding on an outcome-disjoint panel: the v12 estimates are +0.042 [0.0001, +0.1117] (network level) on the second panel and −0.0002 [−0.0041, +0.0039] (pooled) on the first panel, so **no superiority margin is registered**; the endpoint is claim-bearing only in the bounded-degradation sense: success requires the network-bootstrap 95% CI of the paired difference (selector − r6) to have its upper bound below **+0.05**, i.e., a rank-correlation loss of more than 0.05 relative to the strongest fitting-record baseline is ruled out (frozen margin +0.05, the v3 minimum meaningful magnitude). The per-horizon version (7/30/90/180 d) is reported per horizon (v12 reference network Spearman, second panel: 7 d r6 0.9384 vs empirical 0.9321; 30 d 0.9154 vs 0.9157; 90 d 0.8435 vs 0.8648; 180 d 0.6035 vs 0.6594, `per_horizon_network_spearman.csv`).

#### 2.3.2 Coverage definitions (frozen)

- **Unit coverage** c_U = |R*| / |U_all|, where U_all is the set of eligible evaluation units on all scored networks (Section 5.3).
- **Network coverage** c_N = |N_rel| / |N_scored|, where N_rel is the set of scored networks with ≥ 1 released unit.
- **Frozen floors:** c_U ≥ 0.50 AND c_N ≥ 0.60 for the primary claim; **target c_U = 0.70** at the frozen operating point. All reported coverage statistics carry both c_U and c_N.
- Coverage is reported: overall; per domain; per provider stratum; per mechanism; per horizon group (direct {7,30,90,180}, interpolated {14,60}, forced {365}).

#### 2.3.3 Abstention rules (frozen; pseudocode in Appendix B)

A unit is **released** only when all three conditions hold:

1. **Support-any.** Every family m ∈ F(u) has a *unit-level fitting-period stress estimate* s_m(u) (the unit's own placement-based monotone curve evaluated at g, with interpolation for 14/60 d and extrapolation for 365 d only where the network's fitting record contains a real one-year placement window, Section 5.4); a unit with any family at curve-level (pooled) support only is abstained.
2. **Ambiguity.** Ordering the penalized risks r_(1) ≤ r_(2) ≤ … over F(u), the top two are not within δ = 0.10: require r_(2) > (1 + δ)·r_(1); otherwise the unit is flagged ambiguous and abstained.
3. **LCB > 0.** The selected family's recalibrated risk has a strictly positive lower confidence bound: LCB(u) = r_(1)(u) − z_0.95·SE_m(u) > 0, where SE_m is the family's recalibration residual standard error (frozen values from v12: 0.250, 0.212, 0.239 °C for seasonal ridge, donor ridge, XGBoost; estimated pre-outcome for BiLSTM and air2stream). This guards against degenerate (non-positive) predicted-loss regimes.

Width penalty λ = 0.5 and ambiguity threshold δ = 0.10 are frozen at registration. **Abstention is symmetric** across rostered models: all models are scored on the identical unit set; no model may selectively abstain to improve its metrics (v3 §10.3 retained).

**Abstention-cost reporting (mandatory, every table):** for every operating point reported, the abstained set is characterized by (i) fraction of units, (ii) share of total observed loss abstained, (iii) number of fully abstained networks, (iv) per-mechanism and per-horizon composition, (v) fraction of gap-days that must fall back to a default reconstruction downstream (Section 8.4). v12 reference for the released operating point: 91.5% abstained, 91.4% of min-loss mass abstained at 8.5% coverage (`abstention_curve_part2.csv`); v4 targets are the opposite regime (≥ 50% released).

#### 2.3.4 Per-horizon rank

For each horizon group h ∈ {7, 14, 30, 60, 90, 180, 365} d, per network, Spearman(selected-family prediction, observed loss) on released units of that horizon; reported with network-bootstrap CIs per horizon and per model family (family rows feed the model-family matrix, Section 2.3.6). Falsifiable benchmark per horizon: the selector's per-horizon network Spearman must not be below the network-mean fallback's (ladder r4) by more than 0.05 in CI upper bound (bounded-degradation diagnostic; v12 r4 second panel: 0.545 (14 d), 0.698 (60 d), 0.736 (365 d), where the empirical curve equals r4 exactly on unsupported horizons).

#### 2.3.5 Calibration (selected predictions)

Equal-network-weighted OLS of observed loss on selected prediction (released units): report slope and intercept with CIs. Frozen band: slope ∈ [0.90, 1.10] is the calibration-success band (v3 rule retained, reporting-only; the band is not claim-gating except via the LCB rule's validity). Per-family calibration (each family's own predictions on all scored units) is reported in the model-family matrix. v12 recalibration reference (`selection_calibration_part2.csv`): slopes 1.023/1.039/0.982, intercepts +0.019/−0.005/+0.024, R² 0.925/0.928/0.920; common-scale alternative c = 1.006 reported as robustness.

#### 2.3.6 Coverage–regret curve and area under the selective-risk curve (AUSRC)

The full coverage–regret curve is constructed by sweeping the ambiguity threshold δ ∈ {0.02, 0.05, 0.10, 0.15, 0.20, 0.30} × support rule {support-any} × LCB ∈ {off, on} at λ = 0.5 (a frozen grid; the v12 curve shape — regret decreasing sharply as coverage tightens — is reported as reference, not as an assumption). The curve reports network-balanced regret on released units vs c_U (with c_N alongside). **AUSRC** = ∫_{c_min}^{1} Regret(c) dc estimated by trapezoidal integration over the realized grid (c_min = realized coverage of the tightest operating point), and its normalized form AUSRC / AUSRC_best-fixed; both reported with 2,000-draw network-bootstrap CIs. The primary claim is scored at the frozen operating point only; the curve is claim-free reporting except for the downgrade rule (Section 3.4).

#### 2.3.7 Model-family matrix on a common panel

Every rostered family m (Section 6) is scored on the identical v4 unit set (symmetric scoring): per-family (i) network Spearman, (ii) pooled Spearman, (iii) per-horizon network Spearman, (iv) calibration slope/intercept, (v) single-family selection regret (as if the family were chosen everywhere), (vi) self-transfer stress curve (fitting-period stress vs own outer losses; slope, R², and rank preservation), (vii) unit-level-support coverage (fraction of units with unit-level stress for that family). The matrix is the transfer-capacity statement of the panel; no margin is attached (v3 §8's self-transfer requirement retained).

### 2.5 Multiplicity and reporting hierarchy (frozen)

The endpoint hierarchy is: (i) **one primary endpoint** (ΔRegret at the frozen operating point, Section 2.2) gated by the Section 3 criteria; (ii) **key secondaries with their own frozen criteria** — Δρ_r6 bounded-degradation (2.3.1), calibration band (2.3.5), downstream B on the two primary thermal metrics (2.4/8.3) — each interpreted independently; (iii) **disclosure endpoints** — per-horizon rank (2.3.4), coverage–regret curve and AUSRC (2.3.6), model-family matrix (2.3.7), remaining downstream metrics (8.3), diagnostics (10.6) — with no confirmatory claim attached. No family-wise error correction is applied; the hierarchy is the multiplicity control (the primary endpoint is single and prespecified). Every table row states its hierarchy class. This structure makes the panel immune to cherry-picking among the retired v3 endpoints: CapturedLoss/NDCG quantities exist only in class (iii).

### 2.4 Downstream thermal-outcome endpoints

Defined in full in Section 8. The endpoint family is the **incremental benefit** of model-selected reconstruction over the better of the two defaults (climatology, interpolation), net of abstention cost:

B = D(default) − D(model) − λ·C,                                              (5)

where D is network-mean absolute distortion on a frozen primary metric (integrated: degree days above 10 °C; extreme: threshold-exceedance days; both chosen pre-outcome, Section 8.2), D(default) = min over the two defaults of their distortion, D(model) = distortion of the selected-family reconstruction, C = default distortion attributable to units the model does not release (abstained units must be filled by a default; C = (1/|U_all|) Σ_{u ∉ R*} D_default(u)), and λ is the abstention-cost multiplier frozen at 1.0 (sensitivity 0.5 and 1.5). Success: network-bootstrap 95% CI of B excluding 0 in the positive direction on **both** primary metrics (Section 3.3). The other four metrics (annual mean, p90, 7-day mean of daily max, summer mean) are reported with the same definition but no margin (secondary disclosure).

---

## 3. Success criteria (prespecified, frozen at registration)

### 3.1 Prerequisites

1. External registration completed and verified before any v4 outcome is computed or opened (Section 9); otherwise the panel is void.
2. Scored networks N_scored ≥ 60 for any confirmatory claim; target 80–120 (Section 4.1); below 40 scored networks the panel closes with no analysis claims (Section 5.4).
3. Roster, operating point, margins, model roster, and analysis pipeline unchanged from the registered versions (Section 9.5).

### 3.2 Coverage requirements (floors)

At the frozen operating point (λ = 0.5, δ = 0.10, support-any, LCB > 0), the realized coverage must satisfy:

- **c_U ≥ 0.50** (released units / eligible units on scored networks); and
- **c_N ≥ 0.60** (releasing networks / scored networks).

Target: c_U = 0.70 (the pre-outcome coverage simulation sizes the fitting-record placement budget to achieve E[c_U] ≥ 0.70, Section 7.2). The floors are frozen; they may only be tightened by a pre-outcome amendment (Section 9.5).

### 3.3 Primary success criteria (all three must hold)

1. **CI criterion.** The 2,000-draw network-bootstrap 95% percentile CI of ΔRegret = Regret_proposed − Regret_nestedCV (Equation 4) on the released set R* has upper bound strictly below 0: CI_hi < 0.
2. **Relative-reduction criterion.** Relative regret reduction vs the best fixed model (development-chosen single family, Section 7.4.1) is ≥ 20% on the same released set:

   relRed = (Regret_bestFixed(R*) − Regret_proposed(R*)) / Regret_bestFixed(R*) ≥ 0.20.   (6)

3. **Coverage criterion.** Realized c_U ≥ 0.50 and c_N ≥ 0.60 (Section 3.2).

The secondary endpoints of Section 2.3 are confirmatory only through their own frozen criteria: the Δρ_r6 bounded-degradation bound (CI_hi < +0.05, Section 2.3.1); calibration slope band [0.90, 1.10] (reporting-only); the downstream B > 0 criteria on both primary thermal metrics (Section 8.3). All other secondaries are disclosure.

### 3.4 Automatic downgrade rule (frozen)

If at the frozen operating point the realized coverage is below the floors (c_U < 0.50 or c_N < 0.60), the panel is **automatically downgraded**: the primary endpoint loses confirmatory status, is relabelled exploratory in every report, the realized coverage and the full coverage–regret curve become the headline deliverable, and the manuscript must state the downgrade verbatim ("confirmatory claim not made; coverage floor not met"). Downgrade also triggers automatically when N_scored < 60 (exploratory) or N_scored < 40 (panel closed, no claims). A downgrade is a reportable outcome of the panel, not an amendment; it cannot be appealed by margin or endpoint changes.

### 3.5 Direction-failure disclosure

If the CI of ΔRegret lies entirely above 0 (proposed selector worse than nested-CV) or relRed < 0, the panel is a documented failure of the primary claim and must be reported as such, with the per-network distribution of ΔRegret and the coverage–regret curve; no re-scoring, re-selection of operating point, or post-hoc family-set changes are permitted (Section 9.5).

### 3.6 Interpretation rules (frozen)

- The panel-median/mean primary quantities are computed on all scored networks with ≥ 1 released unit (attrition-tolerant); sensitivity reruns are reported, never substituted.
- A criterion is **failed** when its realized value does not meet the frozen bound, even when other criteria pass; the three primary criteria are ANDed, so failure of any one fails the primary claim (with downgrade rules of Section 3.4 applying for coverage and panel-size failures).
- Margins, floors, and the operating point are never relaxed post hoc; amendments may only tighten or register new disclosure endpoints, and post-outcome amendments are additive-only (Section 9.5).
- Coverage and power for the achieved panel are reported alongside every criterion; a claim is not "partially confirmed" — it is confirmatory, exploratory (downgraded), or failed, with the realized numbers disclosed in every case.

---

## 4. Study design

### 4.1 Independent unit, panel size, and targets

- Independent unit: **river network** (a connected set of official daily water-temperature stations sharing a recovery-loss scoring protocol), unchanged from v1–v3.
- Candidate floor: 150 candidate networks entering QC (invariant).
- Target scored networks: **80–120**; attrition-tolerant minimum for any confirmatory claim: **60**; absolute minimum for any analysis: **40** (v3 minima retained; the v4 panel-size justification is the regret-endpoint power simulation, Section 4.4, not the retired ΔRho power curve).
- Panel closure: when the 80–120 band is reached or the candidate pool is exhausted; the realized panel size is reported with the power table evaluated at that size.
- **Outcome disjointness:** every v4 scored network is disjoint from all development outcome networks, all 42 first-panel scored networks, and all 57 second-panel scored networks. QC-only reuse follows v3 §5.1 (individually listed, disclosed, capped at 5 networks, not counted toward domain floors).

### 4.2 Domain and provider strata

- Domain quotas (frozen, v3 agent-b values retained): `united_states` ≥ 40; ≥ 2 non-US domains, each ≥ 10; the non-US domains jointly ≥ 25; no domain > 70% of the scored panel.
- **Provider strata** (new in v4): every provider contributing ≥ 5 scored networks is a stratum (USGS, CHMI, NVE, ARSO, GKD, LUBW, RWS, FOEN, ECCC, eHYD, SYKE, and any additional audited provider). No single provider > 60% of the scored panel. The stratum table (provider × domain × networks) is frozen at roster freeze.
- Inference: networks are the bootstrap units; the provider-blocked bootstrap (resample providers with replacement, then networks within providers) is a prespecified sensitivity (Section 10.2).
- Roster selection uses provider, station counts, and metadata only; **temperature values and any outcome-derived quantity may not select networks** (invariant).

### 4.3 Roster construction rules (pre-outcome, frozen)

1. Candidates from official provider daily water-temperature sources with documented metadata and source audit per provider (v2/v3 rule).
2. Eligibility: ≥ 3 stations per network; ≥ 8 common years; metadata pilot passed; strict daily-concurrency QC passed before any outcome scoring; finite daily NASA POWER air temperature at station coordinates (Section 5.5).
3. Scoreable-gap eligibility: ≥ 1 evaluation gap at a rostered horizon (Section 5.3); networks with none are scoring attrition.
4. Roster freeze: complete strict-QC arrival roster by `network_id`, sorted, with domain and provider counts, bound into the pre-outcome commit (Section 9.2).
5. Evaluate-once self-destruct: any network's outcome may be scored by this protocol exactly once (v3 §5.6 retained).

### 4.4 Power analysis plan (simulation-based on the regret endpoint)

The v3 power analysis (paired ΔRho on +0.038, ΔNDCG +0.0095, CapturedLoss anchors −0.012 to +0.013; `power_analysis.csv`) is **not reused** for v4 because its endpoints are retired. v4 power is computed by a network-bootstrap simulation over the **regret endpoint** at fixed coverage. The analysis is run pre-outcome, frozen into the registration, and reported for the achieved panel size.

**Parameters the analyst must estimate pre-outcome from the v12 artifacts** (with their source):

| parameter | meaning | estimation source (v12 artifact) |
| --- | --- | --- |
| p_rel(n) | per-network release fraction of units under the frozen operating point | per-network unit-level support flags in `selection_predictions_part2.csv` (v12: nonzero only for 8 of 42 networks; mean 0.085) combined with the v4 complete-stress mandate (Section 7.2), which raises these fractions to the coverage target; the pre-outcome coverage simulation estimates p_rel under the frozen placement budget |
| μ_prop(u), σ_prop | per-unit regret distribution of the proposed selector on released units | per-unit regret = loss_selected − min_loss from `selection_predictions_part2.csv` (v12 released set: regret 0.0067 [0.0019, 0.0120], `bootstrap_part2.csv`; abstained-loss share 0.914 at 8.5% coverage, `abstention_curve_part2.csv`) |
| μ_ncv(u), σ_ncv | per-unit regret distribution of the deployable nested-CV selector | comparator rows on the same released units in `abstention_comparison_part2.csv` (v12: per-network CV 0.164, global CV 0.151 on 123 released units) |
| ρ | cross-selector correlation of per-network regrets | paired per-network differences implied by `bootstrap_part2.csv` (proposed vs best-fixed +0.0037 [−0.0255, +0.0330] full-panel) |
| θ_m, φ_m | recalibration slope/intercept and residual SD per family | `selection_calibration_part2.csv` (slopes 1.023/1.039/0.982; resid SD 0.250/0.212/0.239) |
| e_support | support-rate inflation factor (v12 artifact limitation → v4 complete construction) | 8/42 networks with full unit-level support in v12 (`selection_predictions_part2.csv`); v4 placement budget sized to reach E[c_U] = 0.70 (Section 7.2) |
| Δ0, sd0 | mean and SD of per-network ΔRegret at the target coverage under each scenario | not directly observable at 50–70% coverage from v12 (only 8.5% coverage was reached); **must be simulated** by extending the v12 per-unit regret tables to the released set at target coverage using the abstention-curve gradient (v12: regret rises from 0.0067 at 8.5% to 0.0081 at 6.9% (δ=0.15) to 0.0111 at 4.2% (δ=0.20) as coverage tightens; the curve at high coverage is extrapolated by the simulation) |

**Worked example of the simulation scheme** (algorithm in Appendix C; values below are the scheme's structure with illustrative numbers — the analyst replaces them with the frozen pre-outcome estimates):

1. *Coverage configuration.* Simulate the fitting-record placement budget: for N = 100 networks drawn from the QC-eligible pool with v12-like per-network unit counts, draw per-network release fractions p_rel(n) from the distribution implied by the frozen placement budget (v12 anchor: 8/42 networks fully supported; v4 budget aims for E[c_U] = 0.70, so the analyst estimates, e.g., p_rel ~ Beta(shape from placement counts) with E[p_rel] = 0.70 and sd 0.15 — placeholder).
2. *Regret generation.* For each released unit, draw per-unit regrets (r_prop, r_ncv, r_best) from the empirical per-unit regret distributions of `selection_predictions_part2.csv`, restricted to released units, scaled by scenario κ ∈ {0.5, 1.0, 1.5} applied to the per-unit proposed-selector advantage (v12 released-unit gap: proposed 0.0067 vs best-fixed 0.1508; the κ = 1.0 scenario takes this gap as the per-unit advantage and applies it at the target coverage; κ = 0.5 halves it; the null scenario sets it to 0). Add recalibration noise ~ N(0, (φ_m·z)²) with φ_m from the calibration table.
3. *Panel test.* Draw a panel of N networks with replacement; for each drawn network, recompute R̄_prop, R̄_ncv, R̄_best over its released units (unit sets resampled with replacement within the network); form ΔRegret and relRed; apply the frozen test — 95% percentile CI of ΔRegret over 2,000 network-bootstrap draws (on the simulated panel) with CI_hi < 0 AND relRed ≥ 0.20 AND simulated coverage ≥ floors.
4. *Power.* Power = fraction of 500 simulated panels (per (N, κ, coverage-target) cell) in which all three criteria hold. Grid: N ∈ {60, 80, 100, 120}, κ ∈ {0.5, 1.0, 1.5, null}, E[c_U] ∈ {0.50, 0.60, 0.70}. Null-cell power calibrates the CI at the size level.
5. *Deliverable.* `power_sim_v4.csv` (power by cell), `power_sim_summary.json` (recommended N, effect-size floor, CI-coverage calibration), frozen in the registration.

The panel target of 80–120 is justified by the simulated power table: the protocol registers the smallest N at which power ≥ 0.80 under κ = 1.0 at E[c_U] = 0.70, and the target band covers 2–3× the v3 minimum 40 to absorb attrition. If no cell reaches power ≥ 0.80 under κ = 1.0, the protocol registers that fact, keeps the frozen criteria, and reports the primary endpoint with realized power (v3 §12.3 discipline retained).

### 4.5 Readiness gates and pipeline order (frozen, gated)

1. Candidate assembly and per-provider source audits (pre-outcome).
2. Metadata pilot and strict daily-concurrency QC (pre-outcome).
3. Eligibility checks (stations, years, forcing, scoreable gaps) and attrition classes recorded (Section 5.4).
4. Roster freeze (sorted `network_id` list; domain, provider, air2stream-availability columns; Section 4.3).
5. Fitting-period stress construction and recalibration (Section 7.2); fitting-period-only by hash-bound pipeline.
6. Coverage simulation and operating-point confirmation (Section 7.2); power simulation (Section 4.4).
7. **External registration** (Section 9) — gate: nothing scored yet; `readiness.json` flips `external_registration_verified: true` only on hash-verified registration.
8. Outcome scoring with input-hash binding (roster, protocol, baseline tables, registration record).
9. Endpoint computation per frozen definitions (Sections 2–3, 7.5, 8.3).
10. Primary tests, criteria checks, downgrade evaluation (Section 3).
11. Sensitivity: provider-blocked bootstrap, mechanism-stratified, per-domain, S1–S3, QC-qualified-imputed-as-abstained (Section 10).
12. Disclosure of every endpoint, margin, realized power, coverage, abstention and attrition table, and the registration record — regardless of outcome (Section 10.7).

---

## 5. Data and missingness

### 5.1 Data sources (frozen manifest)

- Provider official daily water-temperature sources, accessed through official public download surfaces only, with a per-provider source audit (v2/v3 rule): USGS, CHMI, NVE, ARSO, GKD, LUBW, RWS, FOEN, ECCC, eHYD, SYKE, and any additional audited provider. A source that states its observations are not validated or checked is ineligible (v2 precedent).
- Forcing: **NASA POWER daily air temperature at station coordinates** (the only permitted forcing source); real observed values only. Day-boundary disclosure: POWER local-solar vs USGS local-civil daily windows share date labels but not identical 24-hour boundaries (manuscript §2.2); every network's forcing is tagged with its source day-boundary convention, and that tag is a stratification variable in the model-family matrix.
- No synthetic or donor-proxy forcing: missing forcing days are **not** filled by donor-station substitution or imputed proxies (Section 5.5). The `donor_synchronous` mechanism (Section 5.2) is a *scored mechanism*, not a forcing-substitution license.

### 5.2 Missingness mechanisms (frozen taxonomy; both taxonomies are mandatory tags)

**Placement-mechanism taxonomy** (v12 §2.5, frozen definitions): every artificial gap is generated by one of: `uniform_single_block`; `multi_block` (total length split into 2–8 blocks separated by short observed runs); `summer_biased`; `high_temp_biased`; `donor_synchronous` (target and all donors masked); `target_plus_primary_covariate` (target and strongest donor masked, weaker donors remain); `online_left_boundary_recovery`.

**Provider-recorded class taxonomy** (v3 §7, frozen): `mechanical`, `scheduled`, `sensor_failure`, `aggregation_lag`, `unspecified` (never merged with a mechanism class).

Every scored gap carries both tags where available; mechanism × outcome tables and mechanism-stratified primary/secondary endpoints are mandatory sensitivity (never a selection argument; v3 §7 retained).

### 5.3 Duration roster (frozen)

- Rostered gap lengths: **7, 14, 30, 60, 90, 180, 365 days**.
- Support classes per horizon (frozen): direct-support {7, 30, 90, 180} (same-horizon fitting-period curve available by construction); interpolation-support {14, 60} (per-unit stress interpolated from the unit's own monotone duration curve when the unit has placements at ≥ 2 horizons spanning the target; otherwise curve-level support only); forced horizon {365}.
- **365-day support-or-abstain rule (frozen):** a 365-day unit is eligible for release **only if** the network's fitting record contains a real fitting-period 365-day stress estimate (≥ 1 artificial one-year window fully inside the fitting years, with observed truth inside the fitting period). Otherwise the 365-day unit is **force-abstained** (excluded from the released set, counted in abstention cost and loss-share reporting, Section 2.3.3). This rule replaces the v12 extrapolation-widening policy (surface interval ×1.435) with a release decision: no real fitting-period support → no release.
- Evaluation windows and placement counts follow the frozen v12 scheme (up to 20 placements per station-gap cell distributed across eligible windows; fitting-years-only placements for stress construction).

### 5.4 Attrition rules (frozen; flow table format `attrition_flow_v4.csv`)

Pre-outcome attrition (candidate → QC-qualified): reasons per network (`source_qc_attrition`). Scoring attrition (QC-qualified → scored): `scoreable_gap_attrition` (no eligible evaluation gap), `thermal_outcome_attrition` (downstream temperature outcomes unavailable for Section 8; per-metric counts), `abstention_attrition` (unit/budget abstentions under Section 2.3.3, by reason: support / ambiguity / LCB / forced-365 / unsupported-family). The primary analysis runs on all scored networks and is repeated on the QC-qualified roster with missing outcomes imputed as abstained (v3 §5.4 retained). Every attrition row is reported by domain and provider stratum; missingness is audited for association with fitting-period predictors (pre-frozen audit, v3 §6 retained).

### 5.5 Forcing rules (frozen)

- Real NASA POWER air temperature at station coordinates; finite; day-boundary tagged.
- **No donor-proxy forcing** — donor stations may never substitute for missing target forcing; any unit whose forcing cannot be completed from real POWER observations at the target station is excluded from the unit set with reason `forcing_unavailable` (pre-outcome attrition class, distinct from mechanism tags).
- air2stream calibration uses the same real forcing (Section 6.4); where forcing or day-boundary conditions do not permit air2stream, the family is rostered-but-unavailable for that network and reported as such (Section 6.1).

---

## 6. Model roster

### 6.1 Roster and candidate-family set (frozen at registration)

| position | model | role | candidate family in primary configuration? |
| --- | --- | --- | --- |
| default | climatology (network × horizon fitting-period mean loss; daily climatology for reconstruction) | downstream default + comparator | no (sensitivity only) |
| default | interpolation (linear between observed gap boundaries) | downstream default + comparator | no (sensitivity only) |
| candidate | seasonal-boundary ridge (3 annual harmonics + linear boundary interpolation) | selection candidate | yes |
| candidate | donor covariance ridge (synchronous neighboring temperatures, ridge-stabilized) | selection candidate | yes |
| candidate | XGBoost recovery model (frozen v12 config: 300 trees, depth 4, learning rate 0.05) | selection candidate | yes |
| candidate | fully-trained mask-aware BiLSTM (hidden size 16, early stopping on nested fitting-period validation split, patience 12, ≥ 3 seeds, **source = target instance**, Section 6.3) | selection candidate | yes |
| candidate | air2stream-8 equivalent (Toffolon et al. 2015 state equation, Crank–Nicolson update, bounded multistart least squares) | selection candidate where forcing permits | yes, when available |
| comparator | station × horizon fitting-record mean (r6) | strongest fitting-record baseline (secondary endpoint 2.3.1) | no |
| comparator | best fixed (development-chosen family) | success-criterion benchmark (Section 7.4.1) | no |

For each unit, F(u) = {seasonal_ridge, donor_ridge, xgboost, bilstm} ∪ {air2stream if the network's forcing permits}; networks without air2stream eligibility keep the four-family candidate set, and the network's air2stream availability status is a registered roster attribute (`air2stream_available: true/false` per network, frozen pre-outcome).

### 6.2 Per-model training rules (all fitting-period-only)

1. All models are fit using the network's own fitting years (first 70% of calendar years, v12 scheme) plus the pooled development and first-panel fitting records for shared components (XGBoost global fit, recalibration regressions).
2. Median feature imputation, scaling, and all coefficients are fit on fitting years only (v12 §2.2 rule).
3. Every rostered model reports its **self-transfer stress curve**: its fitting-period artificial-gap losses vs its own outer evaluation losses (same units, no selective abstention), with leave-domain-out folds over the fitting domains (US / each non-US domain) — the v3 §8 requirement retained for every family.
4. Seeds: BiLSTM ≥ 3 seeds (epoch-cap hit rate and non-convergence rate reported per network; v12 reference: median best epoch 68, 28% of runs reached the epoch cap for the regularized variant); XGBoost and ridge families are deterministic given the frozen config; air2stream uses the frozen bounded multistart protocol.
5. Hyperparameters and fitted-checkpoint identifiers are frozen in the registration archive; post-registration training is prohibited (v3 §8 retained).

### 6.3 BiLSTM source = target instance (frozen)

Each network trains **its own** BiLSTM instance on its **own** fitting record (mask-aware training with artificial gaps inside the fitting years; the same gap/placement scheme that generates stress curves). No cross-network transfer, no donor-based pretraining, no evaluation-year information: the training source is the target network's own fitting period ("source = target instance"). The instance is fully trained (early stopping patience 12 on a nested fitting-period validation split; convergence criterion: median best epoch not at the cap — v12 reference 68 epochs, 28% cap-hit; if the cap is hit in > 50% of a network's seeds, the family's unit-level stress for that network is downgraded to curve-level, triggering the support-any abstention for affected units).

### 6.4 air2stream conditionality

The published 8-parameter equation with Crank–Nicolson update, calibrated on train-only bounded multistart least squares, is rostered for networks where real NASA POWER forcing permits (v12: US-only implementation, 8 networks, 89 units, POWER vs USGS day-boundary caveat). Networks without forcing permission are registered `air2stream_available: false`; the family's absence from F(u) on those networks is disclosed in every table.

### 6.5 Sensitivity configurations (registered, not claim-bearing)

- S1: defaults (climatology, interpolation) included in the candidate family set F(u) (changes the support-any condition; the support-any rule then requires unit-level stress for the defaults too, which the defaults trivially satisfy via their fitting-record definitions — reported, not claim-bearing).
- S2: common-scale recalibration (single OLS-through-origin scale c, v12 c = 1.006) instead of per-family regression.
- S3: λ ∈ {0.0, 1.0} width-penalty sensitivity on the primary endpoint.

---

## 7. Decision pipeline

### 7.1 Fitting-period-only information flow (frozen)

No outer evaluation year, no observed v4 outcome, and no quantity derived from either may enter: (i) stress construction, (ii) recalibration, (iii) interval-width estimation, (iv) the coverage simulation, (v) the operating point, (vi) any comparator (best fixed, global CV, per-network CV, nested-CV selector), or (vii) the downstream defaults. The pipeline binds input hashes (roster, protocol, baseline tables, registration record) into its output manifest (v3 §6 retained).

### 7.2 Support construction and the coverage budget

For every scored network and every candidate family, unit-level fitting-period stress is constructed for every evaluation unit: per-unit placement-based monotone duration curves (isotonic PAV in log gap over the unit's own fitting placements; v12 §2.8 Part 2 construction), evaluated at the unit's gap (interpolation for 14/60 d with the unit's own curve when it spans the target; 365 d only under Section 5.4's rule). The **fitting-record placement budget** (number of artificial gaps per station-gap cell in the fitting years) is a frozen design parameter, sized by the pre-outcome coverage simulation so that the expected released-unit coverage E[c_U] ≥ 0.70 with network coverage ≥ 0.60 (Section 4.4 step 1). The v12 8.5% coverage arose because t05 stress artifacts existed for only 8 networks; v4 mandates complete construction for all networks, making coverage a sized engineering target rather than an artifact accident.

### 7.3 Selection and abstention at the frozen operating point

Per unit u, per family m ∈ F(u):
- stress s_m(u) (unit-level or curve-level, flagged);
- recalibrated risk r_m(u) = a_m + b_m·s_m(u) + λ·w_m(u), λ = 0.5, with per-family (a_m, b_m) from the fitting-period recalibration (v12 reference slopes ≈ 1, intercepts ≈ 0);
- width w_m(u) = 2·z_90·φ_m inflated by (1 + 2·max(0, log(g/180)/log(180/7))) for g > 180 d (v12 rule; for 365 d, units additionally require Section 5.4 support, else force-abstained);
- LCB(u) = r_(1)(u) − z_0.95·φ_m.

Release u iff (i) s_m(u) is unit-level for every m ∈ F(u); (ii) r_(2) > 1.10·r_(1); (iii) LCB(u) > 0. Select the family with r_(1). Pseudocode: Appendix B.

### 7.4 Comparators (all evaluated on the identical released set R*)

| comparator | definition | information |
| --- | --- | --- |
| best fixed model | single family chosen on development fitting records by pooled validation loss (v12: XGBoost, dev mean loss 1.236 vs donor 1.310, seasonal 1.970) | fitting-period only; frozen pre-outcome |
| global blocked-CV | leave-one-network-out CV over pooled fitting records; selects one family per panel | fitting-period only |
| deployable nested-CV selector (primary comparator) | per-unit leave-one-placement-out CV within the unit's own fitting placements (≥ 2 placements for all families), else stratum-blocked leave-one-network-out CV (≥ 3 networks in provider stratum), else global leave-one-network-out CV; never abstains | fitting-period only |
| per-network CV (benchmark, strongest) | per-network leave-one-unit-out CV on the network's own fitting placements (v12 reference: 0.0383 [0.0302, 0.0462] on the full first panel — in-sample by design; reported, and the protocol does not require the proposed selector to beat it) | fitting-period only |
| gap-length rule | argmin over families of the pooled per-family duration curve C_f(g) at the unit's gap | fitting-period only |
| station × horizon selector (r6) | per station × horizon fitting-record mean (a fixed rule, not a selector) | fitting-period only |
| random | 20 seeded uniform permutations over families; mean regret | — |
| oracle | min over families of observed loss (upper bound; regret 0 by definition) | outcome (upper bound only) |

Coverage-matching: the proposed selector defines R*; every comparator's regret is computed on R* (v12 protocol, `abstention_comparison_part2.csv`). Additionally, the proposed selector is evaluated with abstention disabled on the full panel (endpoint of the coverage–regret curve).

### 7.5 Fixed-coverage evaluation protocol

1. Apply the frozen operating point to all scored networks; compute R*, c_U, c_N.
2. Primary analysis at the realized operating point (Section 2.2).
3. Coverage–regret curve over the frozen δ/support/LCB grid (Section 2.3.6), including c_U, c_N, and comparators per grid point.
4. Downgrade check (Section 3.4).

---

## 8. Downstream thermal outcomes

### 8.1 Metric list (frozen, all six)

For each released unit's reconstruction inserted into the evaluation-period daily record, and for each default fill, compute per network:

1. **Degree days above 10 °C (DD10)** — integrated;
2. **Annual mean** — integrated;
3. **90th percentile (p90)** — integrated;
4. **7-day mean of daily max (7D Tmax)** — extreme (new metric; mean of the trailing 7-day mean of daily maximum temperature over the record);
5. **Threshold-exceedance days** — days with daily max above the network's fitting-period 95th percentile — extreme;
6. **Summer (JJA) mean** — integrated.

Distortion on metric k: D_n^k = (1/|U_n^k|) Σ_{u ∈ U_n^k} |metric_k(reconstructed record) − metric_k(truth record)|, where U_n^k is network n's units for which metric k is computable (record contains the required season/quantile); units excluded per-metric are counted under `thermal_outcome_attrition`. The v12 metric set (manuscript §2.7: ten metrics) is superseded by this frozen six-metric list; amplitude, phase, summer maximum, days > 20/25 °C, and trend slope are retained in the SI as disclosed extensions, not endpoints.

### 8.2 Defaults and primary metric selection (chosen before outcomes, frozen)

- **Climatology default:** gap days filled with the station's day-of-year climatological mean from fitting years (network × horizon climatology).
- **Interpolation default:** linear interpolation between observed gap boundaries (the seasonal-boundary family's boundary rule).
- D(default) = min over the two defaults of network-mean distortion, per metric.
- **Primary integrated metric: DD10. Primary extreme metric: threshold-exceedance days.** Both are chosen at registration on a priori grounds (v12 §3.7: risk score predicts network-level distortion of degree days 0.743 and p90 0.668, but not amplitude 0.089 or summer maximum 0.250, which are geometry-dominated; budget experiment: degree-day error reduction 39.5% (risk) vs 34.4% (gap) vs 17.1% (random); days-above-25 °C 10.9% vs 2.1% vs 3.6%). The selection is frozen; no outcome-based metric selection is permitted (the choice is registered with its justification in the pre-outcome commit).

### 8.3 Downstream success criteria

Incremental benefit (Equation 5): B_k = D(default)_k − D(model)_k − λ·C_k, λ = 1.0 frozen (sensitivity 0.5/1.5), C_k = (1/|U_all|) Σ_{u ∉ R*} D_default^k(u). Success: network-bootstrap 95% CI of B_k excluding 0 in the positive direction for **both** k ∈ {DD10, threshold-exceedance days}. Secondary: B_k for the remaining four metrics (reporting-only); per-horizon downstream distortion tables; defaults-vs-each-other comparisons.

### 8.4 Abstention-cost linkage

The downstream analysis reuses the same released set R* and abstention-cost accounting as the primary endpoint (Section 2.3.3): units outside R* are filled by the better default, and that cost is charged to the model through C_k. This makes the downstream benefit and the selection-regret claim share one decision rule.

---

## 9. Registration workflow

### 9.1 Ordering requirement (the v3 fix, retained verbatim in effect)

No v4 recovery outcome may be computed or viewed before the external registration exists and is verified. Outcome files written before the registration timestamp invalidate the panel.

### 9.2 Pre-outcome public commit (commit #1; no outcome-derived files)

Must contain, with hashes: (i) this protocol and its sibling agent's protocol (reconciled version once the senior review is complete); (ii) the frozen roster CSV by `network_id` (sorted) with domain/provider/air2stream-availability columns; (iii) endpoint definitions and success criteria (Sections 2–3); (iv) the frozen operating point (λ = 0.5, δ = 0.10, support-any, LCB > 0) and the frozen δ/LCB grid; (v) the model roster with hyperparameters, seeds, and fitted-checkpoint identifiers (Section 6); (vi) the power-simulation table and summary (`power_sim_v4.csv`, `power_sim_summary.json`, scripts) and the coverage simulation (Section 4.4); (vii) the missingness manifest (Section 5); (viii) the downstream metric definitions and primary-metric selection with justification (Section 8.2); (ix) the analysis pipeline and reporting plan (Sections 7, 10); (x) data-rights and provider-treatment notes; (xi) `registration_record_v4.json` (template). No outcome-derived artifact may be present.

### 9.3 External registration

Deposit commit #1 content at OSF or Zenodo; obtain a DOI/handle; record in `registration_record_v4.json` the fields: registry, DOI, registration URL, registration UTC timestamp, registered commit hash, sha256 of the registered files, `separate_pre_outcome_commit: true`, `externally_verifiable_preregistration: true`. `readiness.json` sets `external_registration_verified: true` only when the record exists and file hashes match commit #1.

### 9.4 Outcome commit (commit #2)

Outcome scoring, summaries, flow table, endpoint tables, and this protocol's outcome section, referencing the registration DOI; the commit manifest binds the frozen-commit hash and the DOI.

### 9.5 Amendment policy (frozen)

- **Pre-outcome amendments** (tightening margins, adding disclosure endpoints, roster corrections that preserve outcome disjointness) require a written amendment plus a **new external registration** before scoring.
- **Post-outcome amendments:** only additive disclosure (new tables, new figures, SI extensions). Any post-outcome change to endpoints, margins, the operating point, the candidate family set, or the roster voids confirmatory status and converts the panel to exploratory.
- No post-hoc margin relaxation, no coverage-floor relaxation, no re-scoring (v3 §12.2 retained).

---

## 10. Reporting plan

### 10.1 Fixed table set

| table | content |
| --- | --- |
| T1 | attrition flow: candidates → QC-qualified → frozen roster → scored → excluded-by-class, by domain and provider (`attrition_flow_v4.csv`) |
| T2 | realized operating point: c_U, c_N, released units/networks, by domain, provider, mechanism, horizon group |
| T3 | primary endpoint: per-selector network-balanced regret on R* (proposed, nested-CV, best fixed, global CV, per-network CV, gap-length, station×horizon, random, oracle), ΔRegret with 2,000-draw network-bootstrap CI, relRed vs best fixed and vs every comparator |
| T4 | coverage–regret curve over the frozen grid + AUSRC (and normalized AUSRC) with CIs |
| T5 | secondary 2.3.1: paired Δρ vs r6 (direct-support, network-level) + per-horizon table (2.3.4) |
| T6 | calibration: slope/intercept per selector and per family, equal-network weights, band [0.90, 1.10] |
| T7 | model-family matrix on the common panel (Section 2.3.7) incl. self-transfer stress curves |
| T8 | downstream: D per metric × {model, climatology, interpolation}, B with CIs, abstention-cost C per metric |
| T9 | abstention-cost report per operating point (Section 2.3.3) |
| T10 | power table for the achieved panel size from `power_sim_v4.csv` |
| T11 | sensitivity rows: S1–S3 (Section 6.5), provider-blocked bootstrap, mechanism-stratified primaries, per-domain replication, QC-qualified-imputed-as-abstained rerun |

### 10.2 Statistics (frozen)

- Network bootstrap: 2,000 draws, resampling networks with replacement; within a draw, a sampled network's released units enter with multiplicity equal to the draw count (multiset convention, v12 `bootstrap_part1.csv`); percentile 95% CIs; the primary test is CI_hi < 0 (one-sided at the 2.5% level by construction).
- Provider-blocked bootstrap (sensitivity): resample providers with replacement, then networks within each provider up to its realized count; primary endpoint recomputed; any CI sign flip is reported.
- Pooled station-gap and within-network rank metrics are diagnostics only (v12 §2.9 ordering: network-level first).
- Power: reported from the frozen table at the achieved N and realized coverage; a downgrade statement where realized power < 0.80 (v3 discipline retained).

### 10.3 Calibration checks

Equal-network-weighted OLS slope/intercept (selected predictions; per family); calibration plots per horizon group and per domain; LCB rule validity check: the fraction of released units whose observed loss exceeds the LCB-implied bound (coverage of the LCB interval) reported with CI.

### 10.4 Pooled diagnostics

Pooled (unit-level) regret, pooled Spearman, and within-network median Spearman reported as diagnostics alongside the network-balanced primaries; never as success criteria.

### 10.5 Figures

F1 power curves (power vs N per scenario); F2 coverage–regret curve with comparators (v12 `selection_regret_part2.png` style); F3 per-horizon rank ladder (v12 ladder style) for selected predictions and per family; F4 model-family matrix heatmap; F5 downstream distortion bar set (model vs defaults, per metric, with B CIs); F6 attrition flow (Sankey).

### 10.6 Diagnostics inherited from retired endpoints

CapturedLoss@B and NDCG@B over the v4 units are reported **as diagnostics only** (no margins, no claims; explicitly labeled as the v3 endpoints that the review retired, with the v12 reference −0.174 [−0.198, −0.140] disclosed for context). The abstention loss-share accounting (Section 2.3.3) is the only claim-adjacent use of loss-share quantities.

### 10.7 Disclosure completeness (frozen)

Every endpoint, criterion, margin, realized power value, coverage statistic, abstention and attrition table, sensitivity result, and the registration record are reported **regardless of outcome** — success, failure, downgrade, or panel closure. The outcome section of the protocol (commit #2) follows the frozen reporting plan and cannot omit any T1–T11 table. A report that omits a registered quantity is treated as a protocol violation, not a presentation choice.

---

## 11. Data and software policy

1. **Archival DOI (mandatory before submission):** deposit the permitted archival package (code, configs, this protocol, registration record, power simulations, derived station-gap losses, result tables T1–T11, figure inputs) in Zenodo (or OSF with DOI) with AGU-recommended metadata; the minted DOI replaces `pending` in `.zenodo.json`, `CITATION.cff`, the package manifest, and the manuscript Open Research section. No placeholder DOI may be cited as an archived record (v3 checklist §2–3).
2. **Code release:** all analysis code released (MIT for software); scripts bound to the protocol (`rev_v13_protocol_b.py` equivalents: coverage simulation, power simulation, endpoint computation, bootstrap) with pinned seeds; regenerable outputs stay regenerable in the repo.
3. **Provider data:** provider daily values and raw parquets are not redistributed unless terms permit; the Data Availability statement gives official retrieval routes per provider, hashes of held raw files, a named contact and journal channel for reviewer access to derived-but-restricted aggregates, and provider permission letters as deposited attachments (`metadata/data_rights.csv` governs; v3 checklist §5).
4. **Registration artifacts:** the registration record, DOI, and commit hashes are themselves deposited with the results; the manuscript describes the third panel as externally registered with the DOI (replacing the current SI sentence on the v2 same-commit flaw).

---

## 12. Appendices

### Appendix A. Endpoint formulas (summary)

- Regret(u) = L_selected(u) − min_{m∈F(u)} L_m(u) (Eq. 1).
- R̄_n = mean over released units of Regret(u) within network n (Eq. 2); Regret(S) = mean of R̄_n over releasing networks (Eq. 3).
- ΔRegret = Regret_proposed(R*) − Regret_nestedCV(R*) (Eq. 4); CI: 2,000-draw network-bootstrap percentile CI; criterion CI_hi < 0.
- relRed = (Regret_bestFixed(R*) − Regret_proposed(R*))/Regret_bestFixed(R*) (Eq. 6); criterion ≥ 0.20.
- r_m(u) = a_m + b_m·s_m(u) + λ·w_m(u); λ = 0.5; w_m(u) = 2·z_90·φ_m·infl(g), infl(g) = 1 + 2·max(0, log(g/180)/log(180/7)) for g > 180 d.
- LCB(u) = r_(1)(u) − z_0.95·φ_m; release requires LCB(u) > 0.
- Coverage: c_U = |R*|/|U_all|; c_N = |N_rel|/|N_scored|; floors 0.50/0.60, target 0.70.
- Δρ_r6 per network: Spearman(selected, loss) − Spearman(r6, loss) on direct-support units; panel mean + CI; bound: CI_hi < +0.05 (unfavorable direction).
- B_k = D(default)_k − D(model)_k − λ·C_k (Eq. 5), λ = 1.0; D_k = mean per-network mean absolute metric distortion; C_k = mean over all eligible units of default distortion on units outside R*.
- AUSRC = ∫_{c_min}^{1} Regret(c) dc (trapezoidal over the frozen grid); normalized AUSRC/AUSRC_bestFixed.

### Appendix B. Abstention pseudocode (frozen)

```
for each scored network n:
  for each eligible evaluation unit u in n:
    for each family m in F(u):
      s_m(u) = unit_level_stress(m, u)        # placement-based monotone curve at g_u
      if s_m(u) is not unit-level:            # curve-level only
        flag support_any_fail(u); break
    if support_any_fail(u): abstain(u, reason="support_any"); continue
    compute r_m(u) = a_m + b_m*s_m(u) + 0.5*w_m(u) for all m
    order r_(1) <= r_(2) <= ...
    if r_(2) <= 1.10*r_(1): abstain(u, reason="ambiguity"); continue
    if r_(1) - z_0.95*phi_(family(1)) <= 0: abstain(u, reason="lcb"); continue
    if g_u == 365 and not real_365_stress(n): abstain(u, reason="forced_365"); continue
    release(u); select family with r_(1)
coverage = released_units / eligible_units, released_networks / scored_networks
```

### Appendix C. Power-simulation pseudocode (frozen; run pre-outcome)

```
inputs: selection_predictions_part2.csv, selection_regret_table_part2.csv,
        abstention_curve_part2.csv, abstention_comparison_part2.csv,
        bootstrap_part2.csv, selection_calibration_part2.csv, master_ladder_table.csv
for target_c in {0.50, 0.60, 0.70}:
  estimate placement budget -> per-network release fractions p_rel(n) (Section 4.4 step 1)
  for scenario kappa in {0.5, 1.0, 1.5, null}:
    for N in {60, 80, 100, 120}:
      for rep in 1..500:
        panel = resample N networks with replacement from the 42-network v12 panel
        for each drawn network n:
          units_n = resample with replacement from n's v12 unit table (probability p_rel(n) of release)
          for each unit: draw (r_prop, r_ncv, r_best) from empirical per-unit regret
            distributions, proposed advantage scaled by kappa, recalibration noise
            N(0, (phi_m*z)^2) added to risks
          recompute Rbar_prop, Rbar_ncv, Rbar_best; realized c_U, c_N
        DeltaRegret = mean over networks of (Rbar_prop - Rbar_ncv)
        relRed = 1 - Rbar_prop / Rbar_best
        bootstrap 95% CI of DeltaRegret (2,000 draws over the simulated panel)
        pass(rep) = (CI_hi < 0) and (relRed >= 0.20) and (c_U >= 0.50) and (c_N >= 0.60)
      power = mean(pass); null-cell power calibrates CI size
output: power_sim_v4.csv, power_sim_summary.json (frozen in commit #1)
```

### Appendix D. Review-requirement → protocol-clause checklist

| review requirement | clause |
| --- | --- |
| Primary endpoint = network-balanced selection-regret difference vs deployable nested-CV selector at fixed coverage | 2.2, 7.4, 7.5 |
| Secondary: direct-support paired rank vs station × horizon mean | 2.3.1 |
| Secondary: per-horizon rank | 2.3.4 |
| Secondary: calibration | 2.3.5, 10.3 |
| Secondary: coverage–regret curve + area under selective-risk curve | 2.3.6 |
| Secondary: downstream degree-day and threshold-exceedance distortion reduction vs climatology and interpolation defaults | 2.4, 8.1–8.3 |
| Secondary: model-family matrix on a common panel | 2.3.7 |
| Success: paired network-bootstrap 95% CI of regret difference below 0 | 3.3.1, 10.2 |
| Success: ≥ 20% relative regret reduction vs best fixed model | 3.3.2 |
| Coverage floors: ≥ 50% units, ≥ 60% networks, 70% target | 3.2, 2.3.2 |
| Abstention: support-any + ambiguity + LCB > 0, abstention-cost reporting | 2.3.3, 7.3, 10.6 (Appendix B) |
| Model roster: climatology/interpolation defaults, seasonal ridge, donor ridge, XGBoost, fully-trained mask-aware BiLSTM ≥ 3 seeds source = target, air2stream where forcing permits | 6.1–6.4 |
| Duration roster 7/14/30/60/90/180; 365 only with real fitting-period stress else forced abstention | 5.3 |
| Missingness manifest: frozen mechanisms, real NASA POWER air temperature, no donor-proxy forcing | 5.2, 5.5 |
| Networks as bootstrap units, providers as strata | 4.2, 10.2 |
| Simulation-based power around the regret endpoint (not the +0.038 Δρ anchor) | 4.4 (Appendix C) |
| Registration workflow: pre-outcome commit → OSF/Zenodo → outcome commit referencing DOI | 9.2–9.4 |
| Attrition rules | 5.4 |
| Post-outcome amendment policy | 9.5 |
| Automatic downgrade rule when coverage < floor | 3.4 |
| v3 failures: Δρ-vs-simple primary rejected | 1.1.1, 1.2 R1 |
| v3 failures: triage endpoints obsolete (−0.174 [−0.198, −0.140]) | 1.1.2, 1.2 R2 |
| v3 failures: proof-of-concept coverage (0.0067 at 8.5%) | 1.1.3, 1.2 R3–R4 |

### Appendix E. Worked trace of the primary endpoint on the v12 released set (illustrative arithmetic from cited artifacts only)

This trace demonstrates the endpoint computation on the v12 released set (123 units, 8 networks, 8.5% coverage; `selection_regret_table_part2.csv`, `bootstrap_part2.csv`, `abstention_comparison_part2.csv`). It is **not** a v4 estimate — it is the arithmetic template the v4 pipeline implements.

1. Per-unit regret (Eq. 1): for the 123 released units, Regret(u) = L_selected(u) − min_m L_m(u) with the λ = 0.5 selector. The network-balanced average over the 8 releasing networks is Regret_proposed = 0.0067 °C (95% CI [0.0019, 0.0120]).
2. Comparators on the identical released set: best fixed 0.1508, global CV 0.1508, per-network CV 0.1636, gap-length rule 0.1447, common-scale 0.0068, random 0.341. The deployable nested-CV selector's value on this set (v12's nearest available analogue is per-network CV on its own network roster, 0.1636) would be substituted in the v4 run by the Section 7.4 construction.
3. ΔRegret vs best fixed: 0.0067 − 0.1508 = −0.1441; relRed (Eq. 6) = (0.1508 − 0.0067)/0.1508 = 0.956. Both hypothetical criteria pass at this coverage — but c_U = 0.085 < 0.50, so the coverage floor (criterion 3) fails, and the panel would be **automatically downgraded** (Section 3.4). This is exactly the reviewer's objection: the v12 signal is a downgraded proof of concept, and v4's design mandate is to reach c_U ≥ 0.50 with the Section 7.2 placement budget before any confirmatory claim is possible.
4. Coverage arithmetic: c_U = 123/1,440 = 0.085; c_N = 8/42 = 0.190 (both v12 values). The v4 target operating point must satisfy c_U ≥ 0.50 and c_N ≥ 0.60, which is a design constraint on the fitting-record placement budget, not a selection criterion.
5. Abstention cost (Eq. 5 illustration): v12 abstained units carry 91.4% of the panel's min-loss mass (`abstention_curve_part2.csv`); under v4's fixed-coverage protocol, C would be the default distortion over the (smaller) abstained set at the high-coverage operating point, and λ = 1.0.
