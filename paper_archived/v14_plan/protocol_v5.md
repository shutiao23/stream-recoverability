# Protocol v5: prospective confirmation of differential (benefit) ranking for stream-temperature gap reconstruction

| field | value |
| --- | --- |
| protocol_id | `differential_benefit_confirmation_v5` |
| status | **new draft (v14 planning); supersedes protocol v4's primary endpoint before any v5 outcome is computed or viewed** |
| target_journal | Water Resources Research (WRR). Companion submission: v13 negative-result Technical Note (`paper/v14_plan/negative_result_note.md`) |
| supersedes | `paper/development_v13/protocol_v4.md` — v4's primary endpoint (fixed-coverage selection regret of a support-aware selector vs a deployable nested-CV selector) is **abandoned** (§1.1); everything else in v4 that is compatible is carried forward (§1.3) |
| parent evidence | **P0 differential stress test — FINAL, gates GO**: `results/v14/p0_differential/REPORT.md` (+ `gates.json`, `metrics_by_horizon.csv`, `paired_bootstrap.csv`, `budget_curve.csv`, `budget_within_duration.csv`, `derived_network_level.csv`, `season_loo_upper.csv`, `sanity_checks.txt`) |
| prior work we no longer claim | the v13 negative-result record, spun off as `paper/v14_plan/negative_result_note.md` (HESS Technical Note or EMS); no v13 loss-ranking claim is carried into v14 as evidence of benefit (§1.2, §7) |
| independent unit | river network; bootstrap resamples networks within provider strata (32 US / 15 CZ / 10 NO composition of the parent panel) |
| estimand | realized benefit `B = MAE(default handling) − MAE(model)` per evaluation placement; default = climatology (calendar-day median estimated on inner-fitting years only), robustness leg = linear interpolation |
| target panel | prospective, outcome-disjoint scored networks — 80–120 networks, quotas carried from v4 §4.1 (US 40–65%; ≥ 2 non-US domains each ≥ 15; non-US total ≥ 30); no network from the development, first, or second panels |
| registration | OSF/Zenodo external registration before outcomes (§6). AGU/WRR has **no Registered Report track**; WRR is a TOP-framework signatory, so the registrable content is analysis transparency + data/code availability. Internal hash-bound freeze is **not** externally verifiable preregistration (wording frozen, §6.3) |

---

## Gate revision log (2026-09-03)

Post-review revision of the P0 gates G2/G3 (original wording frozen in PLAN.md §3.4 before
P0). Trigger: the adversarial review (paper/v14_plan/REVIEW_v14.md, Major 1) recomputed the
duration-only comparators. The verdicts below are the standing ones for the archived P0 run;
P0 outputs, `gates.json`, and `REPORT.md` themselves are untouched as the historical record.

| gate | status and definition |
| --- | --- |
| G1 | **unchanged** (network-level Spearman ≥ 0.35, clustered CI lower > 0, per duration); primary reporting level clarified: placement-within-duration, network level auxiliary |
| G2 | old (paired delta vs the risk curve) **DEMOTED to diagnostic**: the risk baseline is negatively correlated with realized benefit (pooled direct ρ = −0.481; within-network demeaned −0.897), so beating it is not evidence. **NEW G2**: paired network-cluster bootstrap delta of diff over r6_diff at placement level within duration; CI lower > 0 — **PASS 7/8 cells**; first-panel 90 d CI [−0.022, +0.056] crosses zero (canonical table: `results/v14/p0_differential/paired_diff_vs_r6.csv`) |
| G3 | old (cross-duration top-20% ≥ 1.3 × panel mean, harmful rate < 15%) **VOIDED**: duration-composition audit — duration-only selects 100% short (7 d) gaps and beats diff (+0.906 vs +0.878 °C); the 17.6× ratio is prohibited (near-zero denominator: panel mean 0.051 °C; differences only). **NEW G3**: within-duration top-20% budget margins over duration-only and r6_diff with cluster CI — **PASS**: +0.22/+0.23/+0.32/+1.01 °C over duration-only and +0.065/+0.068/+0.013/+0.225 °C over r6_diff at 7/30/90/180 d; harmful rates per duration 9.4%/10.9%/25.1%/62.7% (never a single number) |
| G4 | **unchanged** (G1 holds in ≥ 2 of the 7/30/90/180 d strata) |

The revision was made **after** the adversarial review recomputed the duration-only comparators
and **before** any new experimental data were collected. P0 outputs, `gates.json`, and
`REPORT.md` remain untouched as the historical record; this log and
`results/v14/p0_differential/GATE_REVISION_v2.md` (+ `gates_v2.json`) are the revision trail.
The redefinition is disclosed, dated, and ordered relative to the evidence it reinterprets — a
hypothesis/design revision under the evidence-role rules of Pfister & Kirchner
\cite{pfister2017debates}, not a post-outcome amendment. Verdict: GO under the redefined gates
(7/8 G2 cells; 4/4 G3 margins).

---

## 1. Rationale and changes vs v4

### 1.1 Why the v4 primary endpoint is abandoned, and the P0 reframing

Protocol v4's primary endpoint (fixed-coverage network-balanced selection-regret difference
between a support-aware selector and a deployable nested-CV selector) was carried into v14
planning and then dropped, because the v13 evidence on which it rested already showed the
endpoint failing at its own coverage floors: at coverage floors of ≥ 50% of units / ≥ 60% of
networks, two of the three release criteria performed **worse** than best-fixed, and the only
superior criterion won on only 10–12% of the domain — below the protocol's own 20% success
line (`results/revision_v13/decision_harmonization/agent_a/coverage_regret_curve.csv`; PLAN §8.3).
Asking reviewers for a third panel to test an endpoint already known to fail was not defensible.

P0 replaced the question. Instead of predicting **which gaps the recovery model will find
hard** (loss; captured by station history — v13's null result), the v14 estimand predicts
**which gaps are worth rebuilding** — the incremental benefit of the model over the default
handling the user would otherwise apply. P0 scored this estimand on the existing panels with
the differential stress design and its gates passed under the archived definitions (G1–G4 all
TRUE; OVERALL GO TRUE, `gates.json`; G2/G3 since redefined — see the gate revision log above):

- G1 (network-level Spearman ≥ 0.35 with clustered CI lower > 0, per duration): pass 4/4 —
  7 d 0.718 [0.550, 0.824], 30 d 0.551 [0.280, 0.753], 90 d 0.662 [0.443, 0.814],
  180 d 0.647 [0.438, 0.789];
- G2 (archived P0 definition: paired delta vs the v13 risk curve, CI above zero): TRUE —
  placement-pooled Δρ = +1.087, 95% CI [1.019, 1.156] — **re-marked DIAGNOSTIC by the gate
  revision log (2026-09-03): the risk baseline is negatively correlated with realized benefit
  (pooled direct ρ = −0.481; within-network demeaned −0.897); the standing verdict is the
  redefined G2, paired delta of diff over r6_diff, 7/8 cells pass**;
- G3 (archived P0 definition: cross-duration top-20% budget, mean realized benefit ≥ 1.3 ×
  panel mean, harmful rate < 15%): TRUE under the archived rule — 0.899 °C vs panel 0.051 °C
  (17.6×); harmful 14.5% vs panel 36.7% — **VOIDED by the gate revision log (2026-09-03):
  duration-composition audit (duration-only selects 100% short gaps and beats diff, +0.906 vs
  +0.878 °C) and the 17.6× ratio divides a near-zero denominator (panel mean 0.051 °C; ratios
  prohibited, differences only); the standing verdict is the redefined G3, within-duration
  top-20% margins over duration-only and r6_diff, 4/4 durations pass**;
- G4 (≥ 2 durations with G1): TRUE — all four.

P0 also established the one caveat that shapes this protocol's primary endpoint (P0
`REPORT.md` §5): **cross-duration budget curves are dominated by the gap-length scale** —
duration-only and the differential curve are nearly tied at a cross-duration top-20% budget
(0.891 vs 0.899 °C on the second panel), because gap length is the dominant determinant of
both default difficulty and benefit magnitude. Ranking signal is per-duration:
per-duration placement-level ρ (predicted vs realized benefit) is 0.297 / 0.303 / 0.370 /
0.555 at 7/30/90/180 d. **Protocol v5 therefore compares treatments WITHIN duration strata
(7/30/90/180 d) or budgets by duration; cross-duration pooling is reserved for a labeled
diagnostic and never gates a claim.**

### 1.2 The estimand change and the v13 negative-result spin-off

The v13 record — reported in the companion negative-result note
(`paper/v14_plan/negative_result_note.md`, planned as a HESS Technical Note or EMS paper) —
established that a fitting-period loss curve ranks future loss well (pooled 0.945) but **no
better than a station's own history** (station × horizon mean 0.942; paired network
difference +0.042 with CI spanning zero), and that loss ranking is a poor fixed-budget triage
instrument (CapturedLoss@20% 0.337 vs 0.512 for simple descriptors). v14 **no longer claims
loss ranking, loss-triaging, or rank-superiority over station history in any form**. Those
results are cited only as the prior work the v5 design deliberately replaces, and the
estimand under test here is benefit, not loss. The default-handling difficulty — not model
difficulty — was the signal P0 found (predictor correlation sanity checks: risk prediction vs
differential prediction correlate −0.722 on the second panel, `sanity_checks.txt`), which is
why the differential curve, not the legacy risk curve, is the treatment-ranking instrument.

### 1.3 What is carried forward from v4 (unchanged, frozen)

- Outcome-disjoint prospective panel; independent unit = river network; **no network appears
  in any earlier panel's outcome set**.
- External registration workflow: separate pre-outcome public commit → OSF/Zenodo registration
  with minted DOI → outcome-scoring commit referencing the registration (§6).
- Candidate floor 150, expected retention 0.50, target 80–120 scored networks; provider
  quotas; eligibility/QC rules; evaluate-once; attrition flow tables.
- Duration roster {7, 30, 90, 180} d with real same-horizon fitting-period support;
  365-day units: **support-or-abstain** (scored only with real 365-day fitting-period support,
  otherwise forced-abstained and never extrapolated) — carried from v4 §5.5.
- Network bootstrap, networks resampled **within provider strata** (2,000 draws);
  paired comparisons on identical unit/placement subsets.
- Amendment policy (no post-outcome amendment of rules/endpoints/margins; downgrades are
  automatic and non-amendable).
- Tier-0/Tier-1/Tier-2/Tier-3 baseline architecture and reporting norms (§4.2 of PLAN) for the
  P1 suite, including the R&H γ_m prior-technique comparator implemented from
  Richardson & Hollinger \cite{richardson2007longgaps}.

### 1.4 What is new in v5

1. **Estimand**: benefit `B = MAE_default − MAE_model`, not loss.
2. **Primary endpoint**: fixed treatment budgets **within duration strata** (see §2.2, §3),
   replacing v4's coverage-regret endpoint.
3. **Comparator set**: the v13 risk curve is promoted to an explicit comparator (self-
   adversarial — P0: risk ranking of benefit is negative, −0.481 pooled direct / −0.540 at
   180 d, `REPORT.md` Table 1), alongside gap-length-only and random.
4. **Harm-avoidance endpoint** at 180 d (long horizons are where the deployed model is
   net-harmful vs the climatology default; §2.3, S2).
5. Registration wording is tightened per §6.3 (internal hash-bound freeze ≠ externally
   verifiable preregistration; exploratory vs confirmatory labels per
   Pfister & Kirchner \cite{pfister2017debates}).

---

## 2. Scientific questions and endpoints

- **Q1 (primary)**: At fixed treatment budgets B ∈ {10, 20, 30}% applied **within each
  duration stratum**, does ranking gaps by the differential (predicted incremental benefit)
  curve deliver higher mean realized benefit than ranking by (i) gap length only, (ii) random,
  and (iii) the v13 model-risk curve?
- **Q2 (direction replication)**: Does the per-duration ranking of predicted vs realized
  benefit replicate in sign on the prospective panel (placement-level and network-level
  Spearman), with a zero margin?
- **Q3 (harm avoidance)**: Where the model is net-harmful against the default (observed at
  180 d in P0), does the differential curve select a least-harmful treatment set?
- **Q4 (baseline suite)**: Does the differential curve beat the Tier-0 trivial baselines
  (r6-diff, R&H γ_m, default-difficulty) on the prospective panel? (P1 endpoints, gated per
  PLAN §2/§4.1.)
- **Q5 (decision layer)**: value curves EC(ξ)/δ, risk–coverage/E-AURC, and the η response-
  effectiveness envelope (P2 endpoints, PLAN §5; not gated here).
- **Q6 (stationarity boundary)**: stratum-specific differential advantage under stable /
  moderate / drift thermal regimes (P3 endpoints, PLAN §6.1; no hard gate).

### 2.1 Common definitions (frozen)

**Units.** A unit is a station-gap row; a **placement** is one artificial evaluation gap
start `p = (network i, station s, gap length g ∈ {7,30,90,180}, season q, start date)`,
with the P0 scoring roster conventions (up to 20 placements per station × gap × season).
Both the recovery model and the default handler are scored on **identical placement rosters**.

**Realized benefit.** `b(p) = MAE_default(p) − MAE_model(p)` (°C), positive when the model
beats the default on placement p. **Harmful** ⇔ b(p) < 0.

**Default handling.** Primary: climatology — calendar-day medians estimated **only from the
inner-fitting years**, with the same mask as the model's training years (leakage rule, §4.3).
Robustness leg (reported, non-gating): linear interpolation between gap boundaries. no-fill
is excluded from the placement-level estimand (MAE undefined for dropped days; PLAN §3.2) and
is addressed only at downstream-metric level in P4.

**Duration strata.** D = {7, 30, 90, 180} d. All primary analyses are computed **per
stratum**. Cross-duration pooling of any rank statistic or budget statistic is forbidden for
claims (citation base: \cite{forman2010apples}; \cite{airola2011auc}) and may appear only as
a labeled diagnostic (§5.4) because pooling inflates Spearman (gap length drives benefit
scale: direct pooled placement ρ 0.607 vs per-duration 0.297–0.555, P0 REPORT §3) and lets
gap-length baselines absorb the treatment effect (P0 REPORT §5).

**Predictors (all frozen before outcomes; all built from fitting-period data only).**

| predictor | definition | role |
| --- | --- | --- |
| `diff` | four-level benefit curve (station×gap×season → station×gap → network×gap → network mean; §4.1), the P0 differential curve | **primary** treatment ranker |
| `duration` (gap-length-only) | per-stratum constant? **no** — gap length g as the score; **within a duration stratum all placements share the gap length, so ties are broken by a frozen random order within stratum** (seed frozen at registration). This is the honest within-stratum reading of "rank by gap length"; its treated set is a random sample of the stratum, so its expectation is the stratum mean | comparator (i) |
| `random` | uniform random ordering, frozen seed | comparator (ii) |
| `risk` | the v13 model-risk curve (model-MAE ranking, four-level fallback), carried unchanged | comparator (iii) |
| `r6_diff` | station × horizon historical mean of fitting-period **benefit** | Tier-0 baseline (P1 context) |
| `default_difficulty` | climatology-MAE curve alone | Tier-0 baseline (P1 context) |
| `rh_gamma` | R&H γ_m monthly error-vs-gap-length slope prior \cite{richardson2007longgaps}, implemented and applied prospectively (P1) | Tier-0 baseline (P1 context) |
| `oracle` | ranking by realized benefit | upper bound (reported, never compared against for claims) |
| `loo_upper` | season-level leave-one-out benefit curve | feasibility bound (reported only; P0 second-panel per-duration values 0.240 / 0.295 / 0.414 / 0.734 are the calibration context) |

**Budget.** Within stratum g, budget fraction B ∈ {0.10, 0.20, 0.30}; the treated set
`T_{g,B}(predictor)` = the top ⌈B·N_g⌉ placements of the stratum by the predictor's score,
ties broken by frozen rule (random within tie, seed frozen). Outcomes:

- `μ_{g,B}(predictor)` = mean realized benefit over T;
- `h_{g,B}(predictor)` = harmful rate over T (fraction with b < 0).

**Stratum panel mean** `μ_g` and **stratum harmful rate** `h_g` = the same quantities over
all scored placements of stratum g. (P0 180-d stratum context: μ_180 = −1.477 °C, 83%
harmful — the model is net-harmful at 180 d; see §2.3.)

**Panel mean** = mean over all direct placements of the four strata (P0 second-panel value
+0.051 °C, harmful share 36.7%, is the calibration context).

### 2.2 Primary endpoint (P1-v5)

**Within-stratum fixed-budget mean realized benefit of the differential ranking versus the
three comparators**, at B ∈ {0.10, 0.20, 0.30} and each duration stratum g ∈ D:

- Per-network paired differences, network i in stratum g:
  `d_i = μ_{g,B,i}(diff) − μ_{g,B,i}(comparator)`, with per-network treated-set means over the
  network's placements in the stratum (both predictors scored on the identical subset; the
  treated set is defined by the frozen fitting-period rankings, so it is outcome-independent).
- Panel difference Δ = mean over networks of d_i.
- Inference: two-sided 95% **network-cluster paired bootstrap** (2,000 draws; networks
  resampled with replacement within provider strata), per (g, B) cell.
- Success: per §3, gate G2′ (CI above zero in ≥ 2 of 4 strata at B = 0.20; the full
  B × g grid is reported).

**Justification of within-stratum budgets (frozen rationale).** P0's cross-duration budget
experiment (P0 `REPORT.md` §5; `budget_curve.csv`) is dominated by the gap-length scale:
at a cross-duration top-20% budget on the second panel the differential curve and the
duration-only ranking are nearly tied (0.899 vs 0.891 °C mean realized benefit; harmful
14.5% vs 10.7%), because gap length determines both default difficulty and benefit magnitude.
A cross-duration primary endpoint would therefore be absorbable by a gap-length baseline and
would not test the ranking signal at all. The ranking signal that P0 did establish is
per-duration (per-duration placement-level ρ 0.297 / 0.303 / 0.370 / 0.555; per-duration
network-level ρ 0.718 / 0.551 / 0.662 / 0.647). The v5 primary endpoint therefore fixes the
budget fraction **inside** each duration stratum, so the three comparators can no longer
absorb the effect via gap-length composition. (Cross-duration curves are still reported as a
labeled diagnostic — P0 `budget_curve.csv`, §5.4 — with the same caveat text.)

### 2.3 Key secondary endpoints

- **S1 — Direction replication (per-duration rank).** Per-duration placement-level Spearman
  ρ(predicted benefit, realized benefit) and per-duration network-level Spearman, each with a
  network-cluster bootstrap 95% CI; zero margin (direction replication). The second-panel P0
  values are the **replication targets** (not margins): placement-level
  **ρ = 0.297 (7 d), 0.303 (30 d), 0.370 (90 d), 0.555 (180 d)**; network-level
  **0.718 [0.550, 0.824], 0.551 [0.280, 0.753], 0.662 [0.443, 0.814], 0.647 [0.438, 0.789]**
  (`REPORT.md` Table 1; `derived_network_level.csv`). Also report the paired Δρ vs the v13
  risk curve (G2 form) per duration.
- **S2 — Harm avoidance at 180 d.** On the 180-d stratum (where P0 observed the deployed
  model net-harmful against the climatology default: μ = −1.477 °C, 83% of placements
  harmful), the treated set at B ∈ {10, 20, 30}% must **not increase the harmful rate above
  the 180-d stratum's own rate**: `h_{180,B}(diff) ≤ h_180` AND `μ_{180,B}(diff) > μ_180`,
  with a network-cluster CI on Δ = μ_{180,B}(diff) − μ_180. P0 calibration context: top-20%
  by the differential curve reached −0.636 °C with 63% harmful vs duration-only −1.647 °C
  (86%) and the risk curve −2.881 °C (98%) (`REPORT.md` §4; `budget_within_duration.csv`).
- **S3 — Paired Δ vs the v13 risk curve (G2 form).** Placement-pooled paired Δρ and paired
  Δμ_B (diff minus risk) with network-cluster CIs per duration stratum; P0's pooled Δρ =
  +1.087 [1.019, 1.156] is the calibration context, not a margin.
- **S4 — Full within-stratum budget grid.** All predictors × B ∈ {0.10, 0.20, 0.30} ×
  4 strata: μ, h, n (P0 produced the B = 0.20 block only:
  `budget_within_duration.csv` — §3's tables and figures consume the full grid).
- **S5 — Baseline suite (P1).** Tier-0 comparisons on the prospective panel: `diff` vs
  `r6_diff`, `rh_gamma`, `default_difficulty`, `duration`, global constant; Tier-2 domain
  SOTA recovery models as evidence that benefit is not an artifact of a weak recovery model;
  Tier-3 random (lower) and oracle (upper) brackets with E-AURC normalization (PLAN §4.1–4.2).
  Gates: the differential curve must beat every Tier-0 baseline (PLAN §2).
- **S6 — Decision layer (P2).** EC(ξ)/δ curves with the CRPS integral identity
  \cite{laio2007verification}; selective risk–coverage curves and E-AURC
  \cite{geifman2017selective} with the flaws checklist of Traub et al. \cite{traub2024overcoming}
  and the conditional-variance-optimal rejection theory of Zaoui et al.
  \cite{zaoui2020rejectoption} as the theoretical baseline; Laugesen-style flexible-value
  caveats \cite{laugesen2023flexiblevalue}; η response-effectiveness sensitivity envelope
  (\cite{verkade2011floodwarning}; \cite{khader2013voi}; Pappenberger loss-reduction facts
  per PLAN §5.5). Gate: at least one value curve positive over its realistic ξ range.
- **S7 — Stationarity boundary (P3).** Stratified comparison of `diff` vs `r6_diff` in
  stable / moderate / drift strata (drift covariates and the 19/19/19 stratum rule exist:
  `results/v14/p3_drift/README.md`, `network_drift_covariates.csv`); the pre-registered
  directional hypothesis is that the differential curve's advantage over r6_diff is larger in
  the drift stratum than in the stable stratum. No hard gate; either outcome is reportable
  (PLAN §6.1).

### 2.4 Removed endpoints (explicit)

- v4 primary endpoint P1 (fixed-coverage selection-regret difference vs nested-CV selector)
  — removed (§1.1). Model-family selection enters v14 only as the two-sentence negative
  finding of PLAN §5.6 (oracle space 0.100 °C of 1.1705 vs 1.2705; near-degenerate).
- v4 S1 (per-unit paired rank of selected-family predicted loss vs r6 loss) — removed with
  the loss estimand.
- v4 S6 family matrix (loss) — removed; replaced by the P1 Tier-1/Tier-2 recovery-roster
  evidence for the benefit estimand.
- Any cross-duration pooled rank or budget endpoint (P0 REPORT §5) — forbidden for claims,
  allowed only as the §5.4 diagnostic.
- v3-era triage endpoints (CapturedLoss/NDCG on loss) — removed (the v13 record already
  reports them as a negative diagnostic; see the negative-result note).

---

## 3. Success criteria (prespecified, frozen before the run)

GO on the prospective panel requires **all** of:

- **G1′ — Direction replication (mirror P0 G1/G4).** Per-duration **network-level Spearman
  ≥ 0.35** of predicted vs realized benefit, with the two-sided 95% network-cluster bootstrap
  CI **lower bound > 0**, in **≥ 2 of the 4 duration strata** (7/30/90/180 d).
- **G2′ — Superiority over the v13 risk curve (mirror P0 G2, within strata).** At B = 0.20
  within each stratum, the paired network-bootstrap 95% CI of
  Δ = μ(diff) − μ(risk) lies entirely above 0 in ≥ 2 of the 4 strata.
- **G3′ — Budget value (mirror P0 G3, within strata).** At B = 0.20 within each stratum:
  `μ_20(diff) ≥ 1.3 × μ_g` **and** `h_20(diff) < 15%`, in ≥ 2 of the 4 strata. In a stratum
  with μ_g ≤ 0 (net-harmful model; P0's 180-d stratum: μ = −1.477 °C), the numeric ratio
  clause is not evaluable as a ratio and the stratum is governed by the harm-avoidance gate
  S2′ instead (§ below); such a stratum does not count toward the ≥ 2.
- **S2′ — Harm-avoidance floor (freezes S2 into a gate for the 180-d stratum only).**
  `h_{180,0.20}(diff) ≤ h_180` and `μ_{180,0.20}(diff) > μ_180`, CI on the difference
  excluding zero at the 95% level.
- **G4′ — Count rule (mirror P0 G4).** G1′ holds in ≥ 2 of 4 duration strata (i.e., the G1′
  pass count ≥ 2).

Partial-GO band and fallbacks (frozen; PLAN §3.5, §8.3):

- **Partial GO (0.25 ≤ network-level ρ < 0.35 in ≥ 2 strata, or G1′ met in only 1 stratum)**:
  claims shrink to direction-of-benefit prediction. Primary claim becomes the binary
  classification of `B < 0` (harmful) evaluated with AUC + precision@k; within-stratum budget
  results are reported as exploratory. P0 context: at 7/30 d the model-default benefit is
  positive at nearly every treated gap (harmful shares 9%/11% within top-20%), so the
  classification reading is most informative at 90/180 d.
- **Plan B trigger**: any stratum in which the treated set's harmful rate exceeds the
  stratum's own harmful rate h_g (treating by the differential curve worsens harm) — that
  stratum is reported as a harm-failure with the full budget grid, and no benefit claim is
  made for it.
- **NO-GO**: direction replication fails (network-level ρ < 0.25 in ≥ 3 strata) — the v14
  confirmatory program stops; the honest negative outcome is folded into the negative-result
  narrative (PLAN §3.5 Plan C) and no WRR submission is made on the benefit claim.

### 3.1 Automatic downgrade rule (frozen; non-amendable post-outcome)

1. Failure of any of G1′/G2′/G3′/S2′/G4′ is failure of the corresponding claim; no rule may
   be loosened to recover a pass. Downgrades are scripted, not discretionary.
2. If the scored panel is < 80 networks, the panel is reported `insufficient_panel`; no
   confirmatory claim from any endpoint; attrition rows reported in full.
3. Post-outcome amendments of endpoints, margins, comparator definitions, budget definitions,
   or tie-break rules invalidate the confirmatory status of the affected endpoints
   (reported `amended_post_outcome`).
4. Every result carries an evidence-role label (§7): confirmatory (gated endpoints), or
   exploratory/descriptive (all P0/P1–P3-era context quoted here and in the manuscript).

### 3.2 Success-margin summary (frozen)

| Endpoint | Criterion | Gate |
| --- | --- | --- |
| G1′ direction replication | network-level ρ ≥ 0.35 AND CI lower > 0 in ≥ 2 of 4 strata | gated |
| G2′ Δμ_20 vs risk | 95% CI entirely above 0 in ≥ 2 of 4 strata | gated |
| G3′ budget value | μ_20 ≥ 1.3·μ_g AND h_20 < 15% in ≥ 2 of 4 strata (μ_g > 0 strata) | gated |
| S2′ 180-d harm avoidance | h_20 ≤ h_180 and μ_20 > μ_180, CI excludes 0 | gated (180 d) |
| G4′ count rule | G1′ pass count ≥ 2 | gated (derived) |
| S1 per-duration ρ | CIs reported; margin 0 | not gated (direction replication; P0 targets 0.297/0.303/0.370/0.555) |
| S3 paired Δρ vs risk | CIs reported | not gated (P0 Δρ = +1.087 [1.019, 1.156] context) |
| S4 budget grid | full grid reported | not gated |
| S5 P1 baselines | beat every Tier-0 baseline | gated at P1 stage (PLAN §2) |
| S6 P2 value curves | ≥ 1 curve positive over realistic range | gated at P2 stage |
| S7 P3 stationarity | descriptive; directional hypothesis pre-registered | no hard gate |

### 3.3 Power analysis plan (simulation-based, frozen at registration)

Simulation on the within-stratum budget endpoint: per-network realized-benefit distributions
resampled from the P0 second panel by duration stratum (7 d: 4,480 placements; 30 d: 4,480;
90 d: 4,400; 180 d: 3,938; 17,298 direct in total), effect anchors = the P0 within-stratum
B = 0.20 differences between the differential and duration-only treated-set means (7 d:
1.219 − 1.000 = +0.219 °C; 30 d: 0.840 − 0.605 = +0.235 °C; 90 d: 0.380 − 0.056 = +0.324 °C;
180 d: −0.636 − (−1.647) = +1.011 °C; `budget_within_duration.csv`), and between the
differential and risk treated-set means (7 d +0.193, 30 d +0.224, 90 d +0.637, 180 d +2.245 °C).
These anchors are inputs for sizing, **not** margins. The panel is sized so that the 95%
paired network-bootstrap CI for G2′ at B = 0.20 has the frozen width target in ≥ 2 strata at
N = 80–120 networks; the worked-example scheme of protocol v4 §4.3 is retained, with
placements as within-network replicates and networks as bootstrap units. Power curves are
frozen in the pre-outcome commit.

---

## 4. Study design

### 4.1 Panel and roster (frozen at registration)

- Target 80–120 outcome-disjoint scored networks, quotas per §1.3; scoring follows the P0
  pipeline conventions bit-for-bit (`results/v14/p0_differential/run_script_140.py` is the
  reference implementation for placement rosters, season stratification, and the four-level
  fallback).
- Durations {7, 30, 90, 180} d; up to 20 placements per station × gap × season; seasons DJF,
  MAM, JJA, SON.
- The recovery model roster for the benefit estimand: the prespecified gradient-boosting
  recovery condition (as in §2.2 of the v13 manuscript) plus the Tier-1/Tier-2 roster of PLAN
  §4.1 (mean/median fill, LOCF, linear interpolation, calendar-day climatology,
  donor-with-offset, air-temperature regression; air2stream, Mohseni logistic, air-temperature
  multivariate regression) — scored on identical placement rosters. The **same-instance rule**
  of v4 §6.2 carries over (a model's fitting-period benefit curve is built with that model;
  no cross-instance "self" cells).
- The default-handling roster: climatology (primary), linear interpolation (robustness),
  no-fill (downstream-metric leg only, P4).

### 4.2 The four-level fallback (frozen; reused verbatim from P0)

Benefit curves are built by the generic groupby-mean machinery of the existing pipeline
(`empirical_transfer_predictions` on a benefit column), with support hierarchy
`station × gap × season → station × gap → network × gap → network mean`. Level-1
predictions are exact-cell means over the network's own fitting placements; each level's
fallback is used only when the finer cell has no fitting placements. A placement whose
finest available level is the network mean is flagged `diff_supported=False`
(P0 `unit_predictions_*.csv` column) and reported separately in support accounting.
Network means of a stratum with **< 15 networks of support are labeled illustrative case
study and carry no transfer claim** (n < 15 rule, §4.4; rationale:
\cite{hanczar2010rocprecision}; \cite{kratzert2024nevertrain}).

### 4.3 No-leakage rules (frozen)

1. Default-handling parameters (climatology calendar-day medians; interpolation endpoints are
   observed boundaries) are estimated **only from inner-fitting years**, using exactly the
   model's training mask — otherwise the benefit curve leaks evaluation truth.
2. Benefit curves are built **strictly inside the inner-fitting split** and applied forward
   to outer-evaluation placements; no evaluation loss enters any curve, any predictor, or any
   tie-break.
3. The differential predictions are frozen before any evaluation outcome is opened on the
   prospective panel (commit #1, §6.1).
4. Predictors are never re-fit or re-calibrated on prospective evaluation outcomes; the v13
   risk curve is imported unchanged (its predictions must bit-match the archived predictor;
   P0 sanity gate: max |risk_prediction − archived| = 8.88e−16 over 874 direct units,
   `sanity_checks.txt`).

### 4.4 Reporting norms (frozen)

- **No cross-duration pooling of Spearman or budget statistics for claims** (§2.1), citing
  \cite{forman2010apples} and \cite{airola2011auc} in Methods.
- Every network-level correlation carries a network-cluster bootstrap CI
  (spatial/temporal-structure cross-validation rationale: \cite{roberts2017crossvalidation};
  transfer-validity rationale: \cite{wenger2012transferability}).
- Cells with < 15 networks: illustrative only (\cite{hanczar2010rocprecision};
  \cite{kratzert2024nevertrain}).
- All paired comparisons are on identical subsets with paired network resampling within
  provider strata.
- Budget means are reported with harmful rates; a budget result is never reported as a bare
  mean benefit.

---

## 5. Analysis plan (P1–P4 continuation; per PLAN §4–§7)

1. **P1 — baseline suite**: Tier-0 constant, gap-length, R&H γ_m
   (\cite{richardson2007longgaps}), r6-diff, default-difficulty, signal-amplitude proxies;
   Tier-1 trivial recovery methods; Tier-2 air2stream / Mohseni / air-temperature regression;
   Tier-3 random (lower) and oracle (upper) with E-AURC normalization
   (\cite{geifman2017selective}; \cite{traub2024overcoming}). Gate: `diff` must beat all
   Tier-0 baselines. Outputs land under `results/v14/p1_baselines/` (planned artifacts:
   `rh_gamma_curve.csv`, per-unit predictions, `REPORT.md`).
2. **P2 — decision layer**: Laio & Tamea continuous cost–loss EC(ξ)/δ with the
   ∫EC(ξ)dξ = CRPS identity \cite{laio2007verification}; risk–coverage + E-AURC; the
   conditional-covariance operator re-positioned as the theory-optimal rejection baseline
   \cite{zaoui2020rejectoption}; binary-action REV reporting per Richardson
   \cite{richardson2000economicvalue}, with the fixed-suboptimal-threshold value-loss report
   following Roulin \cite{roulin2007skill}; Laugesen defense \cite{laugesen2023flexiblevalue};
   η response-effectiveness envelope \cite{verkade2011floodwarning}, \cite{khader2013voi}.
3. **P3 — stationarity boundary**: strata from `results/v14/p3_drift/`
   (`network_drift_covariates.csv`; stable 19 / moderate 19 / drift 19); directional
   hypothesis pre-registered (S7).
4. **P4 — downstream extension**: 180/365-d downstream legs and the linear-interpolation and
   no-fill default contrasts; third default conclusion; 180-d gap coverage of the 28.9%
   loss-mass claim; bootstrap CIs on all network-level downstream correlations; Johnson et al.
   \cite{johnson2021datagap} incremental framing appears in the manuscript Introduction
   (model-conditional + benefit-oriented, not "more accurate").

---

## 6. Registration and evidence roles

### 6.1 Pre-outcome commit (commit #1, separate public commit)

Contents (no outcome-derived file may be present): this protocol; the frozen scoring roster;
the frozen margins table (§3.2); the tie-break and budget definitions; the power curves
(§3.3); predictor files (differential curve code path, imported v13 risk predictor, R&H γ_m
implementation); readiness record with `external_registration_verified: false`; sha256 of all
registered files. Pushed to the public remote **before any prospective outcome is computed or
viewed**.

### 6.2 External registration (gate)

AGU/WRR has **no Registered Report track**; WRR is a TOP-framework signatory, so the binding
transparency requirements are data/code availability and analysis transparency. OSF/Zenodo
external registration goes **beyond** the journal's baseline and is done anyway (PLAN §8.3):
deposit commit #1 at OSF or Zenodo; mint DOI; `registration_record_v5.json` records
registry, DOI, URL, UTC time, commit hash, file sha256s, and
`separate_pre_outcome_commit: true`, `externally_verifiable_preregistration: true`.
Outcome scoring begins only after the gate flips.

### 6.3 Wording rules (frozen)

- The internal hash-bound freeze of the earlier panels (v13-era second panel) is **not
  externally verifiable preregistration** — the v13 wording ("frozen … not externally
  verifiable preregistration", `manuscript_v13.md` §2.10 and the harmonization memo) is
  retained verbatim wherever those panels are described. This protocol does not inherit that
  limitation: v5 outcomes open only after §6.1–§6.2.
- Post-hoc, amendment, and exploratory analyses are labeled explicitly and defended by
  citation to the debate on hypothesis testing in hydrology
  \cite{pfister2017debates}: confirmatory claims may be made only from endpoints under
  §2.2–§2.3 and §3; everything from the P0-era and earlier records (including every P0 number
  quoted in this protocol as context) is **exploratory/descriptive evidence** and is labeled
  as such in the manuscript and claim matrix.
- The v13 negative-result record (`paper/v14_plan/negative_result_note.md`) is referenced as
  the **prior work we no longer claim**; the v14 manuscript's Introduction and Discussion
  cite it as such rather than re-arguing loss ranking.

### 6.4 Amendment policy (frozen)

Pre-outcome amendments (roster, margins, endpoints, comparators, budgets, tie-breaks,
operating points, power parameters) require a new amendment record and a **new external
registration** before affected outcomes are scored. Post-outcome amendments are prohibited
for every rule and endpoint; post-outcome documentation-only changes are permitted as a
changelog entry that alters no number or definition. The automatic downgrade rule (§3.1) is
non-amendable.

---

## 7. Outcome-scoring commit and reporting

Outcome-scoring runs in a later, distinct commit (commit #2) referencing the registration DOI
and binding commit #1's sha256. Reporting tables (all produced regardless of outcome):

1. `attrition_flow_v5.csv` — candidates → QC → frozen roster → scored, by provider.
2. `direction_replication_v5.csv` — per stratum: placement-level ρ [CI], network-level ρ
   [CI], paired Δρ vs risk [CI] (P0 format: `metrics_by_horizon.csv`,
   `derived_network_level.csv`, `paired_bootstrap.csv`).
3. `budget_within_duration_v5.csv` — full predictor × B × stratum grid: μ, h, n, Δ vs each
   comparator with CIs (P0 produced the B = 0.20 block only: `budget_within_duration.csv`).
4. `harm_avoidance_v5.csv` — 180-d stratum: h and μ of treated sets at each B vs h_180, μ_180.
5. `cross_duration_diagnostic_v5.csv` — labeled diagnostic only (P0: `budget_curve.csv`).
6. `gates_v5.json` — G1′/G2′/G3′/S2′/G4′ verdicts with per-duration detail (P0 format:
   `gates.json`).
7. P1–P4 stage outputs under `results/v14/p1_baselines/`, `p2_decision/`, `p3_boundaries/`,
   `p4_downstream/` with their own REPORTs.

Figures follow `paper/v14_plan/figure_plan_v14.md`; claims follow
`paper/v14_plan/claims_v14.md`; the manuscript skeleton is
`paper/v14_plan/manuscript_v14_skeleton.md`.

---

## 8. Endpoint formulas (frozen, machine-readable reference)

```
placement p = (network, station, gap g ∈ {7,30,90,180}, season, start)
b(p)       = MAE_default(p) − MAE_model(p)          # realized benefit, °C
harmful    : b(p) < 0
stratum g  : all scored placements with gap g
N_g        = |stratum g| ;  μ_g = mean(b over stratum g) ;  h_g = P(b < 0) over stratum g
treated set T_{g,B}(pred) = top ⌈B·N_g⌉ placements in stratum g by pred, ties → frozen
                            random order within tie (seed frozen)
μ_{g,B}(pred) = mean(b over T) ;  h_{g,B}(pred) = P(b < 0 over T)
per-network d_i(predA, predB) = μ_{g,B,i}(predA) − μ_{g,B,i}(predB), i over networks in g
Δ = mean_i d_i ;  95% CI via 2,000-draw network bootstrap within provider strata
G1′: per-stratum network-level Spearman(predicted benefit, realized benefit) ≥ 0.35,
     CI lower > 0, in ≥ 2 of 4 strata
G3′: μ_{g,0.20}(diff) ≥ 1.3·μ_g AND h_{g,0.20}(diff) < 0.15, in ≥ 2 of 4 strata with μ_g > 0
S2′: h_{180,0.20}(diff) ≤ h_180 AND μ_{180,0.20}(diff) > μ_180 with 95% CI on Δ excluding 0
```

All definitions above reuse the P0 reference implementation
(`results/v14/p0_differential/run_script_140.py`: `_budget_rows`, `_gates`,
`_cluster_bootstrap_delta`, `_mean_rho`) so that prospective scoring is bit-compatible with
the evidence base quoted in this protocol.
