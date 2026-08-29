# Protocol v4 — third confirmation panel of stream-recovery predictors (agent A)

| field | value |
| --- | --- |
| protocol_id | `route_a_third_confirmation_v4_a` |
| status | **frozen draft, pending external registration (no v4 outcome has been computed or viewed)** |
| target_journal | Water Resources Research |
| supersedes | `protocol_v3.md` (agent A and agent B drafts, `results/revision_v12/t12_confirmation_protocol/`) — v3 was **rejected by review as currently registrable**; this protocol is the resubmission |
| evidence_status_parent | second confirmation panel: 57 scored networks, 1,446 units (`results/development_v11/second_confirmation/scoring/`); first confirmation panel: 42 networks, 1,440 units |
| independent_unit | river network (as in v1/v2/v3); bootstrap units = networks; strata = providers |
| guidance_artifacts | `results/revision_v12/t03_baseline_ladder/agent_a/master_ladder_table.csv`, `paired_bootstrap.csv`, `per_horizon_network_spearman.csv`; `results/revision_v12/t09_decision_utility/agent_a/selection_regret_table_part2.csv`, `bootstrap_part2.csv`, `abstention_curve_part2.csv`, `abstention_comparison_part2.csv`, `selection_predictions_part2.csv`, `selection_calibration_part2.csv`, `utility_table_part1.csv`, `bootstrap_part1.csv`; `results/revision_v12/t12_confirmation_protocol/agent_a/power_table.csv`, `recommended_sample_size.json` |
| power_analysis | simulation-based on the **selection-regret endpoint** (Section 4); the v3 rank-correlation effect size (+0.038 Δρ) is **explicitly not reused** |
| analysis_script | `scripts/rev_v13_t12_protocol_a.py` (to be written and frozen in the pre-outcome commit) |
| target panel | 80–120 outcome-disjoint scored networks (Section 4) |

---

## 1. Rationale and changes vs v3

### 1.1 What failed review, and the v4 fix

The reviewer rejected protocol v3 as currently registrable on the following
grounds. Each row states the failure, the evidence (all numbers from the
cited artifacts), and the v4 clause that fixes it.

| # | v3 element | Review failure (evidence) | v4 fix | v4 clause |
| --- | --- | --- | --- | --- |
| R1 | Primary endpoint: paired Δρ of the empirical predictor vs **simple descriptors** on direct-support units; power anchor +0.038 | The simple descriptors are not the strongest fitting-record baseline. The station × horizon historical mean of the network's own fitting record (t03 ladder **r6**) is the true strongest fitting-record comparator and nearly matches the full curve: pooled 0.942 vs 0.945, network 0.763 vs 0.805; the paired network-level Δρ is +0.042 with a 95% CI straddling zero (artifact −0.0006 to +0.1154; manuscript 0.0001 to 0.1117). A power analysis anchored on +0.038 vs simple descriptors is therefore not registrable. | The primary endpoint is **no longer a rank-correlation margin**. It becomes the network-balanced **selection-regret difference** between the proposed support-aware selector and the deployable nested-CV selector at fixed coverage (R2). Rank comparisons are demoted to secondary (S1, S2) with r6 as the baseline and a zero margin (direction-replication). No v4 power calculation uses the +0.038 anchor (Section 4.1). | §2.2, §2.3, §4.1, §7 |
| R2 | v3 primaries (b)/(c): captured-loss and NDCG of the empirical predictor vs **random** prioritization | The triage endpoints are obsolete: as a fixed-budget prioritization instrument the empirical predictor already loses to simple descriptors by **−0.174 [−0.198, −0.140]** in CapturedLoss@20% and its fallback tier under-ranks the 365-day loss mass (predictions 1.33 °C vs observed 5.27 °C). Endpoints against random are no longer decision-relevant. | All v3 triage endpoints (b)/(c) are **removed**. Decision endpoints are re-centered on **model selection among recovery families** — the only v12 decision signal that was positive — with defaults (climatology, interpolation) as the no-model reference in the downstream endpoints (§8). | §1.2, §2.4, §8 |
| R3 | v3 had no coverage floors; abstention rules (T1/T2/T3) permitted arbitrarily small released sets | The only positive decision signal so far is model-selection regret **0.0067 (CI 0.0019–0.0120) at 8.5% coverage (123 units, 8 of 42 networks)** under support-any + ambiguity abstention — a proof of concept, not a deployable claim. Review requires mandatory coverage floors: **≥ 50% released units, ≥ 60% released networks; 70% target**, and a full coverage–regret curve. | Coverage floors are mandatory success criteria (§3.1); a **70% coverage design target** (§3.2); an **automatic downgrade rule** when coverage falls below the floors (§3.4); the full coverage–regret curve and area under the selective-risk curve are secondary endpoints (S4). The roster and stress-construction rules (§6) are designed so the frozen abstention gates (support-any + ambiguity + LCB>0, §7.3) can meet the floors. | §3, §6, §7.3, S4 |
| R4 | v3 power analysis (network bootstrap over rank endpoints, margins 0.5×/1×/1.5× of Δρ anchors) | Obsolete with R1/R2: its anchors (Δρ +0.038, ΔCapturedLoss vs random, ΔNDCG vs random) are not decision-relevant, and the observed released-unit effect for selection regret was never powered. | Power analysis is **simulation-based on the regret endpoint**, networks as bootstrap units, providers as strata, with a worked example (Section 4.3) and the parameters the analyst must estimate from the v12 artifacts (Section 4.2). The panel is sized for the CI and relative-reduction criteria jointly at the coverage target. | §4 |
| R5 | v3 comparators for selection were best-fixed and global blocked-CV only; per-network CV beat the proposed selector on the full panel | On the full first panel the proposed selector did **not** beat a dev-chosen best family or global blocked-CV (difference +0.0037, CI −0.0255 to +0.0330) and the per-network average-CV comparator won (0.038 vs 0.085). A protocol must define the deployable comparator the claim is made against. | The primary comparison is against the **deployable nested-CV selector** (§6.6, §7.2): LOO-network CV risk estimates with inner-CV hyperparameter selection, computable for any target network, evaluated on the identical released set (fixed coverage). Per-network CV is retained only as an explicitly in-sample, non-deployable benchmark. | §6.6, §7.2, §7.5 |
| R6 | v3 model roster lacked defaults, explicit neural training rules, and forcing rules | The reviewer's required v4 roster includes climatology/interpolation defaults, a fully trained mask-aware BiLSTM with ≥ 3 seeds and a source=target instance rule, and air2stream only where forcing permits. | Full roster with per-model training rules, seeds, stress construction, and the same-instance source=target rule (§6); forcing rules in the frozen missingness manifest (§5.3). | §5.3, §6 |
| R7 | v3 duration roster {7,14,30,60,90,180,365} allowed 365-day units via extrapolation | The t03 per-horizon table shows 365-day predictions are fallback-identical (empirical = r6 = 0.736 network ρ, 30 networks, 124 units) and t09 shows the 365-day tail is systematically under-predicted. Extrapolated 365-day predictions without fitting-period support are not registrable as scored units. | Duration roster {7,14,30,60,90,180} plus a **365-day support-or-abstain rule**: a 365-day unit is scored only with real same-horizon fitting-period stress support in the network's own fitting record; otherwise it is **forced-abstained** (counted in the flow table, never scored, never extrapolated) (§5.5). | §5.5, §7.3 |
| R8 | v3 missingness manifest had no forcing layer | The reviewer requires a frozen missingness manifest with real NASA POWER air temperature and **no donor-proxy forcing**. | Frozen manifest `missingness_manifest_v4.csv` with mechanism definitions, forcing flags, thermal flags, and the no-donor-proxy forcing rule (§5.3). | §5.3 |
| R9 | v3 inference ignored provider structure | Reviewer requires networks as bootstrap units and **providers as strata**. | All network bootstraps are stratified by provider (frozen resampling rule) (§10.3). | §10.3 |
| R10 | v3 endpoint (d) (thermal protection floor) was a sparsity-proxy floor with no real outcome anchor | Review replaced it with downstream degree-day / threshold-exceedance distortion reduction vs climatology and interpolation defaults, with the integrated + extreme metrics selected before outcomes. | Section 8 defines the prespecified downstream thermal metric list and the frozen primary integrated (annual mean) and extreme (7-day average of daily maximum) metrics, with the incremental-benefit form B = D(default) − D(model) − λC. | §2.5, §8 |
| R11 | v3 success margins were rank/capture margins with no downgrade path for coverage | Review requires CI-based success plus a relative-reduction criterion plus an automatic downgrade when coverage < floor. | Success criteria = paired network-bootstrap 95% CI of the regret difference below 0 **and** ≥ 20% relative regret reduction vs best fixed model, at coverage ≥ 50% units / ≥ 60% networks; automatic downgrade rule §3.4. | §3 |

### 1.2 What is retained from v3 (unchanged in v4)

- Outcome-disjoint third panel; independent unit = river network.
- External registration workflow: separate pre-outcome public commit → OSF/Zenodo
  registration with DOI → outcome-scoring commit referencing the registration
  (§9). This part of v3 was accepted and is carried forward.
- Candidate floor 150, expected retention 0.50, target 80–120 scored networks;
  domain quotas (US ≥ 40 and ≤ 65%; ≥ 2 non-US domains, each ≥ 15; non-US
  total ≥ 30).
- Eligibility and strict daily QC rules; scoreable-gap eligibility; roster
  freeze; evaluate-once self-destruct; QC-only-reuse rule (≤ 5 networks per
  panel, disclosed as `qc_only_reuse=true`, not counted toward quotas).
- Attrition classes and flow-table reporting (§5.4).
- Frozen tie-break rule (descending gap length → station id → original row
  order).
- "Temperature values may not select networks" invariant.
- No post-outcome amendment path (tightened, §9.5).

### 1.3 Scientific questions (claims under test)

- **Q1 (primary)**: At a fixed, prespecified released-unit coverage, does a
  support-aware selector that uses each target network's own fitting-period
  stress (same-instance) achieve lower realized selection regret than the
  best deployable selector that must rely on leave-one-network-out
  cross-validation of other networks' fitting records?
- **Q2**: Does the model-selection benefit survive with mandatory coverage
  (≥ 50% units, ≥ 60% networks; 70% target), i.e., is the v12 proof of
  concept (0.0067 regret at 8.5% coverage) generalizable to deployable
  coverage?
- **Q3**: Does the fitting-period empirical predictor still rank within the
  direct-support subset against the station × horizon fitting mean (r6), the
  true strongest fitting-record baseline?
- **Q4**: Does model-filled reconstruction reduce downstream thermal
  distortion (degree days, annual mean, p90, 7-day average of daily maximum,
  threshold-exceedance days, summer mean) relative to climatology and
  interpolation defaults, net of a prespecified per-unit release cost?
- **Q5**: Which rostered family is best on a common panel, and how does the
  family ranking differ by support tier and horizon?

---

## 2. Scientific questions and endpoints

### 2.1 Common definitions (frozen)

**Units.** A unit u = (network i, station s, gap g) is a station-gap row with an
observed third-panel recovery loss, defined exactly as in second-panel
scoring (observed recovery loss = mean over the unit's roster placements of
the outer `mae_deg_c`). U = the complete scored evaluation-unit set;
|U| is the scored-unit count of the frozen roster.

**Families.** The selection families are the rostered recovery models
(§6): seasonal ridge, donor ridge, XGBoost, mask-aware BiLSTM, and air2stream
where forcing permits. M(u) ⊆ {families} is the family set eligible for unit u
under §6.7 (air2stream excluded where forcing does not permit; families
without stress for u are excluded; defaults are never eligible).

**Predicted loss.** For each family f and unit u, r_f(u) = a_f + b_f·s_f(u),
where s_f(u) is the family's fitting-period stress at u (unit-level curves
where placements exist in the fitting record, pooled duration–season curves
otherwise; §6.5) and (a_f, b_f) are the frozen per-family recalibration
coefficients fitted on fitting-period rows where both stress and outer loss
are observed (v12 guidance: near-identity, §6.5).

**Interval width.** Half-width h_f(u) = z_0.90 · σ̂_f · infl(g), where σ̂_f is
the recalibration residual SD of family f and infl(g) = 1 for g ≤ 180 d and
infl(g) = 1 + 2·max(0, log(g/180)/log(180/7)) for g > 180 d (frozen v12
construction). The 90% interval is [r_f(u) − h_f(u), r_f(u) + h_f(u)].

**Penalized risk.** p_f(u) = r_f(u) + λ·w_f(u) with w_f(u) = 2·h_f(u) and
λ = 0.5 frozen as the primary operating penalty (λ ∈ {0, 0.5, 1} reported).

**Selection.** sel(u) = argmin_{f ∈ M(u)} p_f(u), ties broken by the frozen
tie-break rule (§1.2).

**Unit regret.** R_u(sel) = L_{sel(u),u} − min_{f ∈ M(u)} L_{f,u}, where
L_{f,u} is family f's realized outer loss on u.

**Network regret (released).** For a released set R ⊆ U: R_i(sel) =
(1/|R_i|) Σ_{u ∈ R_i} R_u(sel) for networks with R_i = R ∩ U_i ≠ ∅.

**Network-balanced panel regret.** Regret(sel; R) =
(1/|I_R|) Σ_{i ∈ I_R} R_i(sel), where I_R = {networks i : R_i ≠ ∅}.
Equal network weighting (a network with k released units counts once, with
the within-network mean). This is the t09 definition, frozen.

**Worst-network regret.** max_{i ∈ I_R} R_i(sel).

**Coverage (frozen definitions).**
- Unit coverage c_u = |R| / |U|.
- Network coverage c_n = |I_R| / |{i : U_i ≠ ∅}|.
- Coverage is always reported as a pair (c_u, c_n).

**Released set.** R is determined **once**, by the proposed selector's frozen
abstention gates (§7.3) applied to all units. All selectors and comparators
are scored on the identical set R (fixed-coverage evaluation, §7.4). No
selector has its own abstention rule; R is external to every selector.

**Fixed coverage.** "At fixed coverage" means: the released set R is fixed
before any selector is scored; every selector's metrics are computed on R
and on R alone for the primary endpoint. Comparators that do not abstain
nevertheless report on R only (fair coverage-risk view, as in t09's
`abstention_comparison_part2.csv`).

### 2.2 Primary endpoint (P1)

**Network-balanced selection-regret difference between the proposed
support-aware selector and the deployable nested-CV selector, at fixed
coverage.**

- Per-network paired difference d_i = R_i(proposed) − R_i(nestedCV), i ∈ I_R,
  on the fixed released set R.
- Panel difference ΔRegret = Regret(proposed; R) − Regret(nestedCV; R) =
  mean over I_R of d_i.
- Inference: two-sided 95% network-bootstrap CI over the d_i distribution
  (2,000 draws, networks resampled with replacement within provider strata,
  §10.3). Success criterion: **CI upper bound < 0** (equivalently, the 95%
  CI lies entirely below zero), jointly with the relative-reduction
  criterion (§3.1).
- The nested-CV selector is defined in §6.6; the only difference between the
  two selectors is the risk-estimate source (§7.2). Both are evaluated on R.

### 2.3 Key secondary endpoints (rank, calibration, coverage, family matrix)

- **S1 — Direct-support paired rank vs station × horizon mean (r6)**.
  On direct-support units (g ∈ {7,30,90,180} with a same-horizon
  fitting-period curve), per-network paired Spearman:
  ρ(selected-family predicted loss, observed) − ρ(r6 prediction, observed),
  where r6 is the station × gap fitting-period mean with the documented
  network fallback (t03 rung 6). Network-bootstrap 95% CI; **margin 0**
  (direction-replication only): the v3 +0.019/+0.038 margins are superseded
  (R1). Reported per network and pooled; the v12 anchor is +0.042 with a CI
  straddling zero, so S1 is explicitly not powered for superiority.
- **S2 — Per-horizon rank.** Network Spearman per horizon g ∈
  {7,14,30,60,90,180,365} of selected-family predicted loss vs observed, with
  r6 and r4 (network historical mean) as baselines (t03
  `per_horizon_network_spearman.csv` format). Descriptive, reported for every
  horizon, including forced-abstained 365-day units (marked `forced_abstain`).
- **S3 — Calibration.** Equal-network-weighted slope and intercept of
  selected-family predicted vs observed loss on R and on U; band
  [0.90, 1.10] reported (not gated). Interval coverage of the nominal 90%
  intervals on R.
- **S4 — Coverage–regret curve and area under the selective-risk curve
  (AUSRC).** Sweep the frozen abstention parameters (§7.3): ambiguity
  δ ∈ {0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30} × support rule
  {winner, any} × LCB rule {on, off}, at λ = 0.5. For each operating point,
  recompute R, c_u, c_n, and Regret of the proposed selector and of every
  comparator **on the same released set** (as in
  `abstention_curve_part2.csv` / `abstention_comparison_part2.csv`). The
  full curve is reported; the primary operating point is frozen at δ = 0.10,
  support-any, LCB>0, λ = 0.5 (§7.3). AUSRC(sel) = (1/(1−c_min)) ·
  ∫_{c_min}^{1} Regret(sel; R(c)) dc over the achievable coverage range
  [c_min, 1], where R(c) is the release set at the operating point whose
  coverage is c; lower is better; report the ratio
  AUSRC(proposed)/AUSRC(best fixed).
- **S5 — Downstream thermal outcomes.** Section 8 (degree days, annual mean,
  p90, 7-day average of daily maximum, threshold-exceedance days, summer
  mean; climatology and interpolation defaults; incremental benefit
  B = D(default) − D(model) − λC).
- **S6 — Model-family matrix on a common panel.** Every selection family and
  both defaults scored on identical units (U, direct subset, and R):
  per-family network Spearman, pooled Spearman, RMSE, calibration slope,
  coverage (for families that could abstain — none do at the family level;
  coverage is selector-level), and mean unit regret. Family ranking reported
  per subset and per horizon.
- **S7 — Abstention cost reporting.** For every operating point in S4 and
  for the primary point: fraction abstained, **abstained loss share** (share
  of Σ_u min_f L_{f,u} carried by abstained units), forced-365 counts,
  mechanism-stratified abstention rates. The cost of abstention is also
  expressed downstream: abstained units are filled by the default (§8.2).

### 2.4 Removed endpoints (explicit)

- v3 (a): Δρ vs simple descriptors with frozen margins — removed (R1);
  replaced by P1 + S1/S2.
- v3 (b)/(c): ΔCapturedLoss and ΔNDCG vs random prioritization — removed
  (R2). The empirical predictor's captured-loss deficit vs simple descriptors
  (−0.174 [−0.198, −0.140]) is reported in the manuscript as a decision-
  context finding, not an endpoint.
- v3 (d): thermal protection floor on Δρ — removed (R10); replaced by §8.
- v3 secondary triage endpoints (certified sets, placement replay) — removed;
  their decision role is subsumed by S4 (coverage–regret curve) and §8.

### 2.5 Incremental benefit (formal definition, used in §8)

B = D(default) − D(model) − λ·C, evaluated per network and per metric:

- D(·) = mean absolute distortion (°C) of a thermal metric over the
  evaluation-period reconstructed record vs the observed record (§8.3);
- default ∈ {climatology, interpolation} (§8.2);
- C = number of gap-days filled from the model's **released** predictions
  (abstained units are filled by the default, so the model's C counts only
  released unit-days);
- λ = 0.05 °C per filled gap-day (frozen before outcomes; sensitivity grid
  λ ∈ {0, 0.05, 0.10} reported). λ is the prespecified per-unit release
  cost, ~10% of the direct-support RMSE scale (t03: 0.455 °C), i.e., a unit
  release must pay for itself in distortion reduction.

---

## 3. Success criteria (prespecified, frozen before outcomes)

### 3.1 Primary success (joint, all required)

The primary endpoint P1 succeeds if and only if **all** of the following hold
at the frozen primary operating point (δ = 0.10, support-any, LCB>0,
λ = 0.5):

1. **Coverage floors**: c_u ≥ 0.50 **and** c_n ≥ 0.60 (mandatory; reviewer
   floors).
2. **CI criterion**: the two-sided 95% network-bootstrap CI of ΔRegret
   (proposed − nested-CV, paired per network, on R) has **upper bound < 0**.
3. **Relative-reduction criterion**: the proposed selector's network-balanced
   regret on R is at least **20% lower** than the best fixed model's regret
   on R: RR = 1 − Regret(proposed; R)/Regret(best_fixed; R) ≥ 0.20, where
   best_fixed is the development-frozen single family (§7.5).

All three must hold; failure of any one is failure of the primary endpoint.

### 3.2 Coverage target

The design target is **c_u ≥ 0.70 and c_n ≥ 0.70** (reviewer target). The
power analysis (§4) is computed at coverage levels {0.50, 0.60, 0.70, 0.80};
the panel is sized for the 70% level. Achieved coverage between the floors
and the target does not invalidate a primary success but requires the
realized-power and coverage-limitation disclosure of §3.4.

### 3.3 Success margins summary

| Endpoint | Criterion | Gate |
| --- | --- | --- |
| P1 (primary) | CI upper < 0 AND RR ≥ 0.20 AND c_u ≥ 0.50 AND c_n ≥ 0.60 | gated (primary claim) |
| S1 direct-support rank vs r6 | 95% CI reported; margin 0 | not gated (direction-replication) |
| S2 per-horizon rank | table reported | not gated |
| S3 calibration | slope band [0.90, 1.10], interval coverage reported | not gated |
| S4 coverage–regret curve + AUSRC | curve and ratio reported | not gated |
| S5 downstream (B vs defaults) | 95% CI of B; margin 0 for the two frozen primary metrics (§8.5) | not gated |
| S6 family matrix | table reported | not gated |
| S7 abstention cost | reported | not gated |

### 3.4 Automatic downgrade rule (frozen)

1. If the achieved coverage at the primary operating point is **below either
   floor** (c_u < 0.50 or c_n < 0.60), the primary endpoint is **automatically
   downgraded**: no confirmatory claim may be made from P1; the endpoint is
   reported as `not_achieved (coverage floor)` with the achieved (c_u, c_n),
   the reasons (which abstention gate abstained how much, by mechanism and
   provider), and the full S4 curve so the result remains falsifiable. No
   rule may be loosened to recover coverage.
2. If the floors are met but coverage < target (70%), P1 may claim success
   only with (i) the realized power read from the frozen §4 curves at the
   achieved coverage, and (ii) an explicit coverage-limitation statement in
   the reporting.
3. If the scored panel is < 80 networks, the panel is reported as
   `insufficient_panel`; no confirmatory claims from any endpoint; attrition
   rows are reported in full.
4. Downgrades are automatic (a scripted step in the frozen pipeline); they
   are not subject to analyst discretion and cannot be amended away
   post-outcome (§9.5).

---

## 4. Study design

### 4.1 Panel target and quotas (frozen)

| Quantity | Value | Source |
| --- | --- | --- |
| Candidate floor | 150 networks | v1 invariant |
| Expected retention | 0.50 (candidate → scored) | v1 invariant |
| **Target scored networks** | **80–120** | §4.3 power plan |
| Minimum scored for confirmatory analysis | 80 | §3.4(3) |
| Domain quotas | US ≥ 40 and ≤ 65%; ≥ 2 non-US domains, each ≥ 15; non-US total ≥ 30 | v3 agent A |
| Provider strata | provider of each network recorded at roster freeze; all bootstrap inference stratified | §10.3 |

Outcome-disjointness, QC-only reuse (≤ 5 networks), and eligibility rules are
as in v3 (§1.2). **No v3 or v12 outcome value may be used to select, augment,
or re-order the roster** (temperature values may not select networks).

### 4.2 Power analysis plan: simulation-based on the regret endpoint

The power analysis is **simulation-based on the primary endpoint P1** with
networks as bootstrap units and providers as strata. It is run once, frozen
in the pre-outcome commit, and never re-estimated after outcomes. The v3
rank-correlation effect size (+0.038 Δρ) is **not reused**; no power
calculation in this protocol uses rank-correlation anchors.

**Parameters the analyst must estimate from the v12 artifacts (frozen
before outcomes; each estimate is written to `power_parameters_v4.json` in
the pre-outcome commit):**

| Parameter | Meaning | Source artifact (v12) |
| --- | --- | --- |
| Δ_lo | observed panel ΔRegret (proposed − nested-CV/global-CV) at the released operating point | `abstention_comparison_part2.csv`: proposed 0.0067 vs global blocked-CV 0.1508 → Δ_lo = −0.1441 at c_lo = 0.085; bootstrap CI of the proposed regret from `bootstrap_part2.csv` [0.0019, 0.0120] |
| Δ_hi | observed ΔRegret with no abstention (full panel) | `selection_regret_table_part2.csv`: proposed λ=0.5 none 0.0850 vs global CV 0.0815 → Δ_hi = +0.0037, CI [−0.0255, +0.0330] (`bootstrap_part2.csv`) |
| c_lo | coverage of the released operating point | 123/1,440 = 0.085 units; 8/42 = 0.190 networks |
| Regret_bf(c) | best-fixed regret as a function of coverage | `abstention_comparison_part2.csv`: 0.1508 at c = 0.085; `selection_regret_table_part2.csv`: 0.0815 at c = 1 |
| σ_d | per-network SD of the paired difference d_i on released units | per-network released regrets computable from `selection_predictions_part2.csv` (per-unit selected family, min loss) restricted to the released set; cross-checked against the bootstrap SD of the panel mean (0.0026 in `bootstrap_part2.csv`) |
| release structure | which networks/units the abstention gates release, and how coverage responds to δ | `abstention_curve_part2.csv` (δ × support rule coverage ladder) + the v4 LCB>0 gate added per §7.3 |
| strata | provider → stratum assignment of each guidance-panel network | roster metadata in `selection_predictions_part2.csv` / provider tables |
| k | number of guidance networks contributing released units | 8 (t09 part 2); the v4 estimate of contributing networks at target coverage is a design parameter, not an artifact number |

**Simulation scheme (fixed, Section 12.3 pseudocode):** for each panel size
N ∈ {40, 60, 80, 100, 120, 140, 160}, coverage level c ∈ {0.50, 0.60, 0.70,
0.80}, and effect scale s ∈ {0.5, 0.75, 1.0}: (i) resample N networks with
replacement within provider strata; (ii) block-bootstrap units within
networks and assign release flags so that expected coverage equals c,
matching the v12 release structure (whose release probability by unit type
is estimated from the artifacts above); (iii) compute per-network d_i under
the coverage-scaled effect Δ(c) = s · Δ_model(c) (Δ_model defined in §4.3)
and per-network σ_d; (iv) compute the network-bootstrap 95% CI of the panel
ΔRegret (nested 200 draws) and the relative reduction vs best fixed; (v)
success = CI upper < 0 AND RR ≥ 0.20; power = fraction of B = 1,000
replicates with success. Output: `power_table_v4.csv`, `power_curve_v4.png`,
`recommended_panel_size_v4.json`.

### 4.3 Worked example of the simulation scheme (illustrative; the analyst
must redo every number from the artifacts and freeze the result)

**Coverage–effect model.** The observed effect degrades with coverage. Two
anchors exist in the artifacts: the released operating point (c_lo = 0.085,
Δ_lo = −0.1441) and the no-abstention full panel (c = 1, Δ_hi = +0.0037,
CI [−0.0255, +0.0330]). The prespecified default model is **linear
interpolation in coverage** between the anchors (the analyst must justify in
the pre-outcome commit any departure, e.g., a saturating log model, and
freeze it):

  Δ_model(c) = Δ_lo + (Δ_hi − Δ_lo) · (c − c_lo) / (1 − c_lo)

with Δ_lo = −0.1441, Δ_hi = +0.0037, c_lo = 0.085. Numerically:
Δ_model(0.50) ≈ −0.077, Δ_model(0.60) ≈ −0.061, Δ_model(0.70) ≈ −0.045,
Δ_model(0.80) ≈ −0.029, Δ_model(0.90) ≈ −0.012. The sign crossover lies near
c ≈ 0.91; the frozen operating point must keep achieved coverage below the
crossover region for a negative Δ to be plausible — a key design constraint
recorded here before outcomes.

**Best-fixed regret vs coverage** (same linear scheme, anchors 0.1508 at
c = 0.085 and 0.0815 at c = 1): Regret_bf(0.60) ≈ 0.108,
Regret_bf(0.70) ≈ 0.100, Regret_bf(0.80) ≈ 0.091. The relative-reduction
criterion RR ≥ 0.20 under the linear model requires
Δ_model(c) ≤ −0.20 · Regret_bf(c); numerically this fails near c ≈ 0.88
(RR(0.90) ≈ 0.15 < 0.20). Hence the protocol's design window for the
operating point is **c_u ∈ [0.50, ~0.85]**, centered on the 0.70 target.

**Sample size.** For a one-sided 97.5% CI rule (CI-upper < 0) with 80% power
at Δ and per-network SD σ_d, the required number of contributing networks is
N_eff = 61.6 · (σ_d/Δ)², and the nominal panel size is N = N_eff / c_n
(only networks with ≥ 1 released unit contribute). Examples:

- Δ = Δ_model(0.70) = −0.045, σ_d = 0.05: N_eff ≈ 76; c_n = 0.70 → N ≈ 109
  (inside 80–120).
- Δ = Δ_model(0.60) = −0.061, σ_d = 0.05: N_eff ≈ 41; c_n = 0.60 → N ≈ 69.
- Δ = Δ_model(0.70), σ_d = 0.07: N_eff ≈ 149; c_n = 0.70 → N ≈ 213
  (infeasible → the downgrade/coverage-limitation path of §3.4 applies at
  the achieved panel).

**Frozen decision rule:** the analyst estimates σ_d as the 75th percentile
of the bootstrap SD distribution from the artifacts; the recommended N is
the smallest N ∈ {80,…,120} with joint power ≥ 0.80 at c = 0.70 and s = 0.5
(the conservative scale, i.e., Δ = 0.5·Δ_model(0.70) ≈ −0.0225, which
requires σ_d ≲ 0.029 for N_eff ≤ 84 — if the artifact-based σ_d exceeds
this, the frozen power report states the achievable power at N = 120 and the
primary claim is conditioned on the CI rule alone with the realized power
disclosed). If the recommended N cannot be reached, the protocol does **not**
loosen margins or lower coverage floors; it runs at the achieved panel with
the §3.4 disclosures.

### 4.4 Roster construction rules (candidate → scored)

1. Candidates from official provider public download surfaces only (USGS,
   NASA POWER, CHMI, NVE, ARSO, GKD, LUBW, RWS, FOEN, ECCC, eHYD, SYKE, and
   any additional provider that passes the frozen strict daily-QC rule; a
   source stating its observations are unvalidated is ineligible — v2
   precedent).
2. Strict daily QC before any outcome scoring: ≥ 3 stations per network;
   ≥ 8 common years; positive and complete same-site approved daily
   discharge where used; finite daily air temperature at station
   coordinates.
3. Scoreable-gap eligibility: ≥ 1 evaluation gap in the duration roster
   (network with none = scoring attrition).
4. Roster freeze: complete strict-QC arrival roster, sorted, hash-bound in
   `frozen_scoring_roster_v4.csv` inside the pre-outcome commit; exact
   per-domain counts recorded; counts may only exceed quotas upward.
5. Provider strata and mechanism flags frozen with the roster.

---

## 5. Data and missingness

### 5.1 Data sources

- Daily water temperature and discharge: official provider surfaces as in
  §4.4 (audited per SI Text S17 of the manuscript).
- Air temperature forcing: **real NASA POWER daily air temperature** at
  station coordinates (day-boundary disclosure per DATA_RIGHTS.md); no
  donor-proxy forcing is permitted (frozen, R8).
- Temperature values are used inside the thermal endpoints (§8) and forcing
  (§6.4) only, never for network selection (invariant).

### 5.2 Frozen missingness manifest

`missingness_manifest_v4.csv`, frozen in the pre-outcome commit, records per
network and per unit:

| Field | Values | Definition (frozen) |
| --- | --- | --- |
| `mechanism` | `mechanical` / `scheduled` / `sensor_failure` / `aggregation_lag` / `unspecified` | frozen v3 taxonomy: sensor/logger failure; planned maintenance or seasonal removal; instrument malfunction with QC flag; provider publication delay; no recorded mechanism (never merged with another class) |
| `forcing` | `power_retrieved` / `power_missing` | NASA POWER retrieval status at station coordinates over the evaluation window |
| `thermal_outcome` | `available` / `missing` | real daily temperature available over the evaluation window (required for §8) |
| `support_365` | `true` / `false` | network's own fitting record contains same-horizon 365-day fitting-period placements at the station (or at the network, with `support_level` = `unit`/`network`) |
| `abstention_gate` | filled at scoring time | which gate(s) abstained the unit: `support_any` / `ambiguity` / `lcb` / `forced_365` / `none` |

Missingness is exogenous: gaps are not model-selected. A pre-outcome audit
checks each manifest field for association with fitting-period predictors
(e.g., network mean loss); any correlation is reported in the manuscript.

### 5.3 Forcing rules (frozen)

- Air2stream is rostered **only where forcing permits** (forcing =
  `power_retrieved` and harmonized daily boundaries feasible); on other
  units it is excluded from M(u) (never extrapolated with proxy forcing).
- No donor-proxy forcing: a network's forcing gaps may never be filled from
  another network's temperature record (R8).
- If > 20% of frozen-roster networks have any `power_missing` flag, the
  air2stream matrix rows (S6) and §8 metrics are reported conditional on
  forcing availability, and the count is disclosed; the primary endpoint P1
  is unaffected (air2stream simply drops out of M(u) on those units).

### 5.4 Attrition classes and flow table

| Class | Assumed mechanism | Recorded |
| --- | --- | --- |
| `source_qc_attrition` | MNAR at provider/source level | networks by provider and domain |
| `scoreable_gap_attrition` | MAR given network record length | networks and unit counts |
| `thermal_outcome_attrition` | MNAR/MAR (seasonal coverage, provider temperature availability) | networks; §8 scored only when ≥ 20 networks retain thermal outcomes, else `not_achieved` with reason |
| `abstention_attrition` | decision-rule-induced | units by gate, mechanism, and provider |
| `forced_365_attrition` | decision-rule-induced (no real 365-day fitting-period stress support) | units and networks |

`attrition_flow_v4.csv` reports candidates → QC-arrivals → frozen roster →
scored → excluded-by-class, with counts by domain and provider.

### 5.5 Duration roster and the 365-day support-or-abstain rule (frozen)

- Eligible horizons: **{7, 14, 30, 60, 90, 180} days** (all always eligible
  for scoring).
- **365-day units** are scored only when the unit has **real fitting-period
  stress support**: `support_365 = true`, i.e., the network's own fitting
  record contains same-horizon (365-day) fitting-period placements at the
  station (`unit` level) or elsewhere in the network (`network` level, with
  the level recorded). A family may predict a 365-day unit only from such
  real 365-day evidence; extrapolation of ≤ 180-day curves to 365 d is
  prohibited for every family and for the defaults (R7).
- A 365-day unit without support is **forced-abstained**: it is counted in
  `forced_365_attrition`, never scored in any endpoint, and is filled by the
  default in §8 (with the share of 365-day loss mass abstained reported,
  S7). The t09/v12 finding that 365-day fallback predictions (1.33 °C) miss
  the observed loss mass (5.27 °C mean) is the rationale, recorded as
  guidance, not as a margin.

---

## 6. Model roster

### 6.1 Roster (frozen; every model scored on identical outer gaps and
identical third-panel outcomes)

| Model | Role | Training/construction rule | Seeds | Forcing |
| --- | --- | --- | --- | --- |
| Climatology default | downstream default (§8.2) | calendar-day mean of the network's own fitting-period daily record | n/a | none |
| Interpolation default | downstream default (§8.2) | linear interpolation across the gap from pre- and post-gap observed daily values | n/a | none |
| Seasonal ridge | selection family | fitting-period placements, seasonal-boundary ridge | deterministic | none |
| Donor ridge | selection family | fitting-period placements, donor-BLUP ridge | deterministic | none |
| XGBoost | selection family | fitting-period placements (B ∪ D information condition) | fixed seed | none |
| Mask-aware BiLSTM | selection family | fully trained; gap-masked fitting on fitting-period records (the network is trained to reconstruct through masked gaps, so incomplete records are usable); non-SOTA disclaimer as in v11 | **≥ 3 seeds**, across-seed spread reported (epoch caps and non-convergence rates reported) | none |
| air2stream | selection family where forcing permits | published 8-parameter equation, harmonized daily boundaries, fit on fitting-period records | deterministic | real NASA POWER, `power_retrieved` only (§5.3) |

### 6.2 Same-instance source=target rule (frozen, R6)

For a target network i, **every** selection family's instance used for i's
evaluation units is fit on fitting-period data that **include network i's
own fitting record** (same-instance, source=target): fitting records =
development panel + first-panel + second-panel fitting records + each target
network's own fitting record. This mirrors the information access of the
frozen empirical predictor (t03: a panel's own fitting record is
pre-evaluation and was used by the proposed method too). **No family
instance is trained on any evaluation-period observation or any third-panel
outcome**; training inputs are hash-bound in the pre-outcome commit.

### 6.3 Seeds and training rules

- Ridges and air2stream: deterministic (fixed solver seeds recorded).
- XGBoost: single fixed seed (recorded).
- BiLSTM: ≥ 3 seeds; the across-seed mean and min/max of every family-level
  metric are reported; a seed may not be dropped post hoc; non-convergence
  (epoch cap hit) is reported per seed and treated as a stress signal, not a
  failure to disclose.
- All hyperparameters and fitted-checkpoint identifiers are frozen in the
  registration archive; post-registration training is prohibited.

### 6.4 Forcing-dependent training

air2stream uses real NASA POWER air temperature (day-boundary disclosure);
no other family uses forcing. Mask-aware BiLSTM may use forcing as an input
only if that is frozen in its hyperparameter record; by default it does not.

### 6.5 Stress construction (per family, frozen; v12 construction extended)

1. **Unit-level stress**: if unit u's station has family-f fitting-period
   placements, s_f(u) = the family's own per-gap curve (isotonic in log gap
   within season) evaluated at g — flag `unit`.
2. **Curve-level stress**: otherwise s_f(u) = C_f(g), the family's pooled
   duration–season curve over all fitting-period placements — flag `curve`.
   C_f exists for every family on every unit (pooled fitting placements
   always exist), so `curve` support is universal; `none` occurs only when a
   family is ineligible for the unit (air2stream without forcing; any
   family without the 365-day evidence required by §5.5).
3. **Recalibration**: per family, OLS outer ≈ a_f + b_f·s_f on fitting-period
   rows where both stress and roster outer loss are observed (v12 guidance:
   seasonal +0.019/1.023 R² 0.925; donor −0.005/1.039 R² 0.928; xgboost
   +0.024/0.982 R² 0.920 — near-identity; the common-scale-factor sensitivity
   c = 1.006 is reported for every family).
4. **Interval width**: §2.1.

The v12 limitation that family-2/3 unit-level stress existed only on 8 t05
networks is a **guidance constraint, not a v4 design constraint**: v4 stress
is constructed for all rostered families on all fitting records (including
each target network's own record), which is what makes the coverage floors
achievable (§3.1). The t09-style unit-level support-any rule is retained as
a sensitivity operating point in S4 (`support rule = any, unit-level
required`), reproducing the 8.5%-coverage proof of concept.

### 6.6 The deployable nested-CV selector (primary comparator, frozen)

For each target network i and each family f ∈ M(u):

1. **Inner loop (hyperparameters)**: choose θ_f by leave-one-network-out CV
   over fitting networks ≠ i, minimizing pooled CV loss of family f.
2. **Outer loop (risk estimate)**: r̃_f(u) = LOO-network CV estimate of
   family f's loss at u's (station, gap, season) cell from the fitting
   records of networks ≠ i: unit-level curves where placements exist among
   those networks, pooled duration–season curve otherwise; recalibrated with
   the same frozen (a_f, b_f).
3. **Selection**: sel_CV(u) = argmin_f [r̃_f(u) + λ·w̃_f(u)] with the same
   λ = 0.5 and the same tie-break; w̃_f from the CV residual SD.

The nested-CV selector is **deployable**: it uses only other networks'
fitting records (plus the frozen recalibration), never the target's
evaluation outcomes and never the target's own fitting record for the risk
estimate. It never abstains; it is scored on the released set R like every
other selector. This isolates exactly the quantity in Q1: the value of
same-instance, support-aware stress over cross-network CV risk.

### 6.7 Family eligibility per unit (M(u))

- air2stream ∈ M(u) iff forcing permits (§5.3).
- Family f ∈ M(u) iff s_f(u) is computable (not `none`): curve-level support
  is universal; `none` occurs only per §6.5(2) (365-day rule §5.5).
- Defaults are never in M(u) (they are not recovery models; §8 handles them).

---

## 7. Decision pipeline

### 7.1 Information flow (frozen)

1. Everything below the selection step uses **fitting-period data only**:
   fitting records of development/first/second panels and of each target
   network (pre-evaluation), NASA POWER forcing, frozen recalibrations and
   hyperparameters.
2. Evaluation outcomes (third-panel recovery losses) enter **only at the
   scoring step**, which runs after the registration gate (§9).
3. Temperature values may not select networks; no evaluation-period
   observation may enter any training or calibration step.
4. All inputs hash-bound; the pipeline binds input hashes into its output
   manifest.

### 7.2 Selection

- Proposed: sel(u) = argmin_{f ∈ M(u)} p_f(u) with same-instance stress
  (§6.2, §6.5).
- Nested-CV: sel_CV(u) per §6.6.
- All other selectors (comparators, §7.5) are computed from the same per-unit
  family predictions and the same recalibration; only the risk-estimate
  source and/or the choice rule differ.

### 7.3 Abstention gates (frozen; primary operating point in bold)

A unit u is **released** (u ∈ R) iff it passes **all** gates; otherwise it is
abstained, with the triggering gate recorded (`abstention_gate`):

1. **Support-any** (primary: rule `any` at least curve-level): every
   f ∈ M(u) has stress for u (`curve` level suffices per §6.5; `none`
   abstains). Sensitivity: `winner` (only the winning family needs stress)
   and `any-unit` (all families need `unit`-level stress — the t09 rule).
2. **Ambiguity**: the two smallest penalized risks satisfy
   p_(2) ≤ (1 + δ) · p_(1) → abstain. Primary δ = 0.10; S4 sweeps
   δ ∈ {0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30}.
3. **LCB>0**: the selected family's 90% lower confidence bound on the
   outer-loss scale is ≤ 0 → abstain: LCB_sel(u) = r_sel(u) − h_sel(u) ≤ 0.
   Rationale (frozen): units whose selected-family loss is indistinguishable
   from zero carry only noise for selection regret; releasing them inflates
   regret without protecting loss mass.
4. **Forced-365**: §5.5 (365-day units without real support are never
   released).

**Abstention cost reporting (S7)**: every operating point reports fraction
abstained, abstained loss share, forced-365 counts, and gate attribution;
the downstream effect of abstention is charged through C and D (§8).

### 7.4 Fixed-coverage evaluation protocol (frozen)

1. Compute all family predictions, intervals, and selector choices for all
   u ∈ U (fitting-period information only).
2. Apply §7.3 gates → R; compute c_u and c_n.
3. **Coverage-floor check** (§3.4): below floors → automatic downgrade path;
   the primary analysis is still computed and reported.
4. Score every selector on the identical R: per-network regrets R_i(sel),
   panel Regret, worst-network regret, top-2 hit rate, per §2.1/§2.2.
5. Primary inference: paired d_i with provider-stratified network bootstrap
   (2,000 draws).
6. S4 curve sweep (δ × support × LCB at λ = 0.5) — exploratory by design,
   no margin changes.
7. Report achieved power from the frozen §4 curves at the achieved (N, c).

### 7.5 Comparators (all scored on R)

| Selector | Rule | Deployable? | v12 reference value on released set (guidance only) |
| --- | --- | --- | --- |
| Proposed (support-aware) | §7.2, §7.3 | yes | 0.0067 (CI 0.0019–0.0120) at 8.5% coverage |
| Nested-CV | §6.6 | yes | ≈ global blocked-CV 0.1508 on the same released set |
| Best fixed model | single family chosen on development fitting-period outcomes **before outcomes** (v12: xgboost, dev mean loss 1.236 vs donor 1.310, seasonal 1.970); frozen at registration | yes | 0.1508 |
| Global CV | leave-one-network-out CV on pooled fitting records, family choice per unit | yes | 0.1508 |
| Per-network CV | per-network leave-one-unit-out CV on the network's own roster | **no (in-sample benchmark)** | 0.1636 |
| Gap-length rule | argmin over families of the pooled duration curve C_f(g) at the unit's gap | yes | 0.1447 |
| Station × horizon selector | selects argmin_f |r_f(u) − r6(u)|, r6 = station × gap fitting mean (t03 r6, documented network fallback) | yes | n/a |
| Random | uniform over families, 20 seeded draws, mean | yes | 0.341 |
| Oracle | selects argmin_f L_{f,u} (realized) | no (upper bound) | 0.000 |

The station × horizon selector encodes the strongest fitting-record
baseline (R1) as a **selection** rule: choose the family whose predicted
loss most closely matches the station × horizon fitting mean, so a model
that merely redisovers r6 cannot win P1.

---

## 8. Downstream thermal outcomes

### 8.1 Prespecified metric list (frozen; evaluated per network on the
evaluation-period reconstructed daily record)

1. Degree days above 10 °C (annual sum of (T − 10) for days with T > 10 °C).
2. Annual mean daily temperature.
3. 90th percentile (p90) of daily mean temperature.
4. **7-day average of daily maximum temperature (7DADM)**.
5. Threshold-exceedance days: days with daily maximum > 20 °C and > 25 °C
   (both thresholds reported).
6. Summer (JJA) mean daily temperature.

### 8.2 Defaults (frozen comparators)

- **Climatology default**: each gap day filled with the network's
  calendar-day mean from the fitting-period daily record.
- **Interpolation default**: each gap filled by linear interpolation between
  the last pre-gap and first post-gap observed daily values.
- No-fill (dropping gap days) is reported as a third reference in the
  supporting information only, not as a primary default comparator (the v12
  §2.7 analysis used no-fill; the review requires climatology and
  interpolation defaults).

### 8.3 Distortion and incremental benefit

- Reconstruction: insert each model's released predictions (or the default
  fill) into the evaluation-period daily record at gap days; abstained and
  forced-365 units are filled by the default, so the model's record differs
  from the default's only on released unit-days.
- Distortion per metric: D = mean over networks of |reconstructed metric −
  observed (truth) metric|, in °C (or °C·days for degree days and days for
  exceedance counts; each metric reports its own unit).
- Incremental benefit per network: B = D(default) − D(model) − λ·C with
  λ = 0.05 °C per filled gap-day (frozen, §2.5; sensitivity λ ∈
  {0, 0.05, 0.10}).
- Primary downstream inference: per-network paired B vs **each** default;
  provider-stratified network bootstrap 95% CI; margin 0 for the two frozen
  primary metrics; all six metrics reported (S5).

### 8.4 Frozen primary metric selection (made here, before outcomes)

- **Primary integrated metric**: distortion of the **annual mean** daily
  temperature.
- **Primary extreme metric**: distortion of the **7-day average of daily
  maximum temperature (7DADM)**.
These two are the only downstream metrics with a margin-0 CI claim; the
remaining four are reported with CIs and no claim status. Thermal outcomes
exist only where `thermal_outcome = available` (real temperature); units
with `power_missing` over the window are `thermal_outcome_attrition`.

### 8.5 Downstream success (not gated)

S5 succeeds descriptively if the network-bootstrap 95% CI of B excludes 0 in
favor of the model against the better of the two defaults, for both frozen
primary metrics; any other outcome is reported as null with the full CI
table. No downstream margin may gate or un-gate P1.

---

## 9. Registration workflow

### 9.1 Pre-outcome commit (commit #1, separate public commit)

Contents (no outcome-derived file may be present):

- This protocol (`protocol_v4_a.md`), the v3 protocols as read-only
  references, and this namespace's power-analysis artifacts
  (`power_table_v4.csv`, `power_curve_v4.png`, `power_parameters_v4.json`,
  `recommended_panel_size_v4.json`).
- `frozen_scoring_roster_v4.csv` (exact per-domain roster, sorted, hash-bound)
  and its sha256.
- `missingness_manifest_v4.csv` (§5.2) and the pre-outcome attrition audit.
- Frozen margins table (§3.3), abstention rules (§7.3), comparator
  definitions (§7.5), downstream metric selection (§8.4), λ (§2.5).
- Frozen per-family recalibration coefficients, hyperparameters, seeds, and
  the dev-frozen best-fixed choice (§7.5).
- `readiness.json` with `external_registration_verified: false`.
- Analysis scripts (`scripts/rev_v13_t12_protocol_a.py` etc.) and the
  `registration_record_v4.json` template.

Commit #1 is pushed to the public remote and its hash recorded **before any
third-panel outcome is computed or viewed**.

### 9.2 External registration (gate)

Deposit commit #1's content (or the OSF preregistration form built from it)
at **OSF or Zenodo**; obtain a minted handle/DOI. `registration_record_v4.json`
records: registry, DOI, registration URL, registration UTC, registered
commit hash, sha256 of the registered files, and the flags
`separate_pre_outcome_commit: true`, `externally_verifiable_preregistration:
true` (the explicit opposite of the v2 record).

### 9.3 Authorization

`readiness.json` flips to `external_registration_verified: true` only when
the registration record exists and its file hashes match commit #1. No v4
analysis step may read, merge, or reference any outcome file before this
gate.

### 9.4 Outcome-scoring commit (commit #2)

Scoring runs, summaries, flow table, endpoint results, and this protocol's
outcome section, in a **later, distinct commit** referencing the
registration DOI and binding commit #1's sha256. Outcome files written
before the registration timestamp invalidate the panel.

### 9.5 Amendment policy (frozen)

- **Pre-outcome amendments** (roster change, margin change, endpoint change,
  abstention change, operating-point change, power-parameter change):
  require a new amendment record **and a new external registration** before
  any affected outcome is scored; there is no partial registration.
- **Post-outcome amendments**: prohibited for every rule, endpoint, margin,
  operating point, roster, and analysis setting — any such change
  invalidates the confirmatory status of the affected endpoints, which are
  then reported as downgraded (`amended_post_outcome`) per §3.4(4).
- **Post-outcome documentation-only changes** (typos, reference fixes,
  formatting): permitted as a changelog entry, never as a rule change, and
  must not alter any number or definition.
- The automatic downgrade rule (§3.4) is itself non-amendable post-outcome.

---

## 10. Reporting plan

### 10.1 Tables (all produced regardless of outcome)

1. `attrition_flow_v4.csv` — candidates → QC-arrivals → frozen roster →
   scored → excluded-by-class, by domain and provider.
2. `coverage_table_v4.csv` — (c_u, c_n) at the primary operating point and
   at every S4 sweep point, with gate attribution.
3. `primary_regret_table_v4.csv` — per selector on R: panel Regret (CI),
   worst-network regret, mean unit regret, top-2 hit, relative reduction vs
   best fixed; plus the paired d_i summary and the ΔRegret bootstrap CI.
4. `selection_predictions_v4.csv` — per unit: per-family risk/width/support/
   loss, selected family per selector, true best family, abstention gate.
5. `family_matrix_v4.csv` — S6: family × metric × subset {U, direct, R}.
6. `per_horizon_rank_v4.csv` — S2 (t03 `per_horizon_network_spearman.csv`
   format).
7. `calibration_v4.csv` — S3: slope/intercept/interval coverage on R and U.
8. `abstention_cost_v4.csv` — S7: fraction abstained, abstained loss share,
   forced-365 counts, per gate/mechanism/provider.
9. `downstream_v4.csv` — S5: per-metric D and B vs each default, CIs.
10. `power_achieved_v4.csv` — realized power read from the frozen §4 curves
    at the achieved (N, c_u, c_n).

### 10.2 Figures

- Coverage–regret curves for proposed and all comparators (S4), with the
  frozen primary operating point marked.
- Area-under-selective-risk-curve comparison (proposed vs best fixed ratio).
- Per-horizon rank plot (S2); calibration plot (S3); downstream distortion
  bar/CIs (S5); family matrix heatmap (S6).

### 10.3 Statistics (frozen)

- **Bootstrap units**: river networks. **Strata**: providers — every
  bootstrap resamples networks with replacement **within provider strata**,
  holding stratum composition at its achieved value.
- Primary inference: two-sided 95% percentile CI of the panel ΔRegret over
  2,000 draws; success = upper bound < 0 (§3.1).
- Secondary inference: same scheme for S1/S3/S4/S5; paired Wilcoxon across
  networks reported as a robustness check for P1 and S1.
- Calibration checks: equal-network-weighted slope/intercept on R and U;
  nominal 90% interval coverage on R.
- All numbers reported with the achieved panel size and achieved coverage;
  realized power from the frozen curves; downgrade statements per §3.4.
- Sensitivity (reported, non-gating): per-domain, per-mechanism, per-horizon,
  direct-subset-only, λ ∈ {0, 0.5, 1}, δ ∈ sweep, support rules {winner,
  any, any-unit}.

---

## 11. Data and software policy

- **Archival DOI (required)**: before submission, the permitted archival
  package (per `metadata/data_rights.csv` and the v3 open-research
  checklist) is deposited at Zenodo or OSF; the minted DOI is inserted into
  the manuscript Open Research section, `CITATION.cff`, `.zenodo.json`, and
  the package manifest, and is cited as the registration's related
  identifier. No placeholder DOI is cited as an archived record.
- **Code release**: all analysis scripts, configurations, and the frozen
  protocol artifacts are released under the repository license; the
  outcome-scoring pipeline is runnable from the released commit.
- **Provider daily values**: raw daily observations are not redistributed
  unless the provider's terms permit; official retrieval routes, hashes of
  raw files held, and the controlled-access channel for reviewer access to
  derived-but-restricted aggregates are documented (v3 checklist, §5).
- **NASA POWER forcing**: retained with day-boundary disclosure; no
  donor-proxy forcing (R8).
- The registration DOI and the archival DOI are distinct; both are cited in
  the manuscript.

---

## 12. Appendices

### 12.1 Endpoint formulas (frozen, machine-readable reference)

Let U = evaluation units; R = released set (§7.3); M(u) = eligible families
(§6.7); L_{f,u} = realized outer loss of family f on u; sel(u) = selected
family (§7.2).

- Unit regret: R_u(sel) = L_{sel(u),u} − min_{f ∈ M(u)} L_{f,u}.
- Network regret (released): R_i(sel) = (1/|R_i|) Σ_{u ∈ R_i} R_u(sel),
  R_i = R ∩ U_i ≠ ∅.
- Panel regret: Regret(sel; R) = (1/|I_R|) Σ_{i ∈ I_R} R_i(sel).
- Coverage: c_u = |R|/|U|; c_n = |I_R|/|{i : U_i ≠ ∅}|.
- Primary difference: d_i = R_i(proposed) − R_i(nestedCV); ΔRegret =
  (1/|I_R|) Σ d_i; two-sided 95% provider-stratified network-bootstrap CI
  (2,000 draws) of ΔRegret; success iff CI upper < 0.
- Relative reduction: RR = 1 − Regret(proposed; R)/Regret(best_fixed; R);
  success iff RR ≥ 0.20.
- S1: per-network Δρ_i = ρ(P_i, O_i) − ρ(r6_i, O_i) on direct-support
  released units (P = selected-family predictions); panel Δρ with bootstrap
  CI; margin 0.
- S4: AUSRC(sel) = (1/(1−c_min)) Σ_k Regret(sel; R_k)·Δc_k over the sweep
  operating points sorted by coverage (trapezoidal integral), c_min = the
  strictest sweep point's coverage.
- S5: B_i = D_i(default) − D_i(model) − λ·C_i, λ = 0.05 °C per filled
  gap-day; D_i = |reconstructed metric − truth metric| per network.
- S3: equal-network-weighted OLS slope and intercept of predicted vs
  observed on R and U; interval coverage = mean over R of
  I[L_{sel,u} ∈ interval_sel(u)].

### 12.2 Abstention pseudocode (frozen; returns gate or `released`)

```
input: u = (network i, station s, gap g); M(u); p_f(u), r_f(u), h_f(u) for f in M(u)
gate = None
if g == 365 and support_365(u) == false:            # §5.5
    gate = "forced_365"
elif any(f in M(u) has stress level "none" for u):  # §7.3.1, support-any (curve level)
    gate = "support_any"
else:
    sort p_f(u); p1 = min; p2 = second-min
    if p2 <= (1 + delta) * p1:                       # delta = 0.10 primary
        gate = "ambiguity"
    else:
        sel = argmin p_f(u)                          # frozen tie-break
        if r_sel(u) - h_sel(u) <= 0:                 # §7.3.3 LCB>0
            gate = "lcb"
        else:
            gate = "released"
record abstention_gate(u) = gate
```

### 12.3 Power-simulation pseudocode (frozen; §4.2)

```
# Inputs (power_parameters_v4.json, estimated per §4.2):
#   per-network released regret vectors of proposed/nested-CV/best-fixed
#   (from selection_predictions_part2.csv restricted to released units),
#   provider stratum per network, release structure vs (delta, support, LCB),
#   Delta_lo, Delta_hi, c_lo, sigma_d estimates.
for N in {40, 60, 80, 100, 120, 140, 160}:
  for c in {0.50, 0.60, 0.70, 0.80}:
    for s in {0.5, 0.75, 1.0}:
      Delta = s * Delta_model(c)      # Delta_model: linear, §4.3
      for b in 1..1000:
        draw panel: stratified resample of N networks (within providers);
          block-bootstrap units within networks; assign release flags so
          that E[c_u] = c and E[c_n] matches the v12 release structure
          scaled to c
        for each released network i: d_i = R_i(proposed) - R_i(nestedCV)
          with unit regrets scaled to achieve panel Delta and per-network
          SD sigma_d (additive zero-mean noise with SD sigma_d on d_i)
        CI = percentile bootstrap of mean(d_i) over 200 nested draws
        RR = 1 - Regret(proposed)/Regret(best_fixed)
        success_b = (CI.upper < 0) and (RR >= 0.20)
      power(N, c, s) = mean(success_b)
recommend N* = min N in [80,120] with power(N*, 0.70, 0.5) >= 0.80
freeze power_table_v4.csv, power_curve_v4.png, recommended_panel_size_v4.json
```

### 12.4 Checklist: every review requirement mapped to a protocol clause

| Review requirement | v4 clause |
| --- | --- |
| Primary endpoint = network-balanced selection-regret difference, proposed vs deployable nested-CV selector, at fixed coverage | §2.1, §2.2, §6.6, §7.4 |
| v3 Δρ-vs-simple primary (power +0.038) dropped; r6 station × horizon mean recognized as the strongest fitting-record baseline (pooled 0.942 vs 0.945; network 0.763 vs 0.805; paired Δρ +0.042 CI straddling zero) | §1.1 R1; S1, S2; §4.1 |
| v3 triage endpoints (empirical vs random CapturedLoss) obsolete (empirical −0.174 [−0.198, −0.140] vs simple) | §1.1 R2; §2.4 |
| Only positive signal = selection regret 0.0067 at 8.5% coverage (123 units, 8 networks) = proof of concept | §1.1 R3; Q2 |
| Coverage floors mandatory: ≥ 50% released units, ≥ 60% released networks; 70% target | §3.1(1), §3.2 |
| Report full coverage–regret curve | S4, §10.1(2), §10.2 |
| Secondary: direct-support paired rank vs station × horizon mean | S1 |
| Secondary: per-horizon rank | S2 |
| Secondary: calibration | S3 |
| Secondary: coverage–regret curve + area under selective-risk curve | S4 |
| Secondary: downstream degree-day and threshold-exceedance distortion reduction vs climatology and interpolation defaults | §2.5, §8 |
| Secondary: model-family matrix on a common panel | S6 |
| Success = paired network-bootstrap 95% CI of regret difference below 0 | §3.1(2), §12.1 |
| AND ≥ 20% relative regret reduction vs best fixed model | §3.1(3) |
| Automatic downgrade rule when coverage < floor | §3.4 |
| Abstention rules: support-any + ambiguity + LCB>0 | §7.3 |
| Abstention cost reporting | S7, §7.3, §10.1(8) |
| Model roster: climatology/interpolation defaults, seasonal ridge, donor ridge, XGBoost, fully-trained mask-aware BiLSTM ≥ 3 seeds with source=target instance, air2stream where forcing permits | §6.1, §6.2, §6.3, §6.4 |
| Duration roster 7/14/30/60/90/180; 365 only with real fitting-period stress support else forced abstention | §5.5 |
| Missingness manifest: frozen mechanism definitions, real NASA POWER air temperature, no donor-proxy forcing | §5.2, §5.3 |
| Networks as bootstrap units, providers as strata | §10.3, §4.1 |
| Simulation-based power around the regret endpoint; do NOT reuse the +0.038 Δρ effect size | §4.2, §4.3, §12.3 |
| Registration workflow: pre-outcome public commit → OSF/Zenodo registration → outcome-scoring commit referencing the registration | §9.1–§9.4 |
| Attrition rules | §5.4 |
| Post-outcome amendment policy | §9.5 |
| Panel: 80–120 outcome-disjoint networks | §4.1 |

---

*End of protocol v4 (agent A). This document, the roster, the margins, and
the power analysis are frozen at the pre-outcome commit; nothing in this
document depends on any third-panel outcome.*


