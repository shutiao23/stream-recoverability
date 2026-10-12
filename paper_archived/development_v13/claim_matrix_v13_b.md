# Claim matrix v13: model-conditional historical stress testing (agent b)

Replaces `paper/development_v12/claim_matrix_v12.md`. All evidence is under
`results/revision_v12/` (analysis ids t01-t12); numbers are the same-unit or
same-panel values from the revision artifacts and were re-verified against the
CSVs (trust CSVs over report text). "Strong / partial / weak / unsupported"
refers to the allowed language, not to the importance of the finding.

The v13 paper restructures the claim space around **exactly three top-level
claims**: C1 predictive validity within support; C2 applicability boundaries;
C3 decision utility at prespecified coverage. Everything that was a separate
v12 claim (C4-C11) is folded under one of these three as evidence, a boundary,
or an explicit non-claim. The headline is the **persistence of local recovery
difficulty**, demonstrated by the empirical predictor ranking future loss at
least as well as the strongest fitting-record baseline — NOT big gains from
seasonal stratification, and NOT uniqueness in magnitude.

Evidence roles (used throughout): **frozen pre-outcome** = first-panel
analyses and the second panel (internally hash-bound, frozen before outcome
scoring; not externally verifiable preregistration because amendment and
outcomes share one commit); **post-hoc v12 development** = all revision
analyses on already-scored panels; **v13 harmonization** = re-runs on unified
panels/conventions still required before a finding can be evidence;
**future preregistered third panel** = protocol v3/v4 outcomes (none exist).

---

## C1. Predictive validity within support

**Claim.** The fitting-period block stress curve built for a recovery model
ranks that model's future recovery loss at directly supported horizons on
outcome-disjoint networks.

**Evidence required.**
- Same-unit paired comparison on identical units (both predictors on the same
  subset; paired network resampling for CIs).
- Per-horizon network-level rank at each directly supported horizon.
- Within-network decomposition (residualized pooled rank + median per-network
  rank) to show the rank is within-network station-horizon ordering, not
  persistent network difficulty.
- Exact-local-support tier result (the rank must survive restriction to exact
  station x duration x season cells).
- The strongest fitting-record baseline on the same units, reported with a
  paired difference and the predictor correlation (fairness control).

**Current evidence** (second panel = 57 outcome-disjoint networks; 874 direct
units, horizons 7/30/90/180 d):

| Quantity | Value | Artifact |
| --- | --- | --- |
| Empirical predictor, station-gap (pooled) Spearman | 0.945 (0.9453) | t01/t03 |
| Empirical predictor, network-level Spearman | 0.805 (0.8049) | t01/t03 |
| Empirical predictor, calibration slope | 0.938 (0.9383) | t01/t03 |
| Exact local support (station x duration x season) | 841/874 units; network Spearman 0.887 (0.8872) — alone exceeds 0.805 | t02 |
| Residualized (network-demeaned) pooled Spearman | 0.936 (0.9359) | t01 |
| Median within-network Spearman | 0.965 | t01 |
| Per-horizon network Spearman (7/30/90/180 d) | 0.932 / 0.916 / 0.865 / 0.659 | t01 |
| Paired vs simple descriptors (network) | +0.552 [+0.309, +0.814] | t01 |
| Paired vs simple descriptors (station-gap) | +0.098 [+0.059, +0.142] | t01 |

**Honest sub-row (the fairness control that shapes the language).** The
strongest fitting-record baseline is the **station x horizon historical mean
of fitting-period MAE** (t03 ladder rung r6_station_gap; the empirical
predictor is this object plus season stratification, with identical
information access). On the same 874 units: pooled 0.942 vs empirical 0.945;
network 0.763 vs 0.805; paired network DeltaRho +0.042 with CI straddling
zero (+0.0417 [-0.0006, +0.1154], 97.0% of bootstrap draws positive); paired
pooled Delta +0.003. The two predictors correlate 0.992 on the direct units
(0.9917; 0.9923 on all 1,446). First-panel replication (direct 858 units):
empirical minus r5/r6 paired network DeltaRho +0.0024 [-0.0239, +0.0262].
Simple descriptors remain far behind at the network level (+0.552, CI
excludes zero).

**Status: STRONG**, with the language constraint below. The persistence claim
is restricted to directly supported horizons and to the model that produced
the curve; it is not a magnitude claim over the baseline.

**Allowed language.** "The fitting-period stress curve ranks future loss at
directly supported horizons **at least as well as the strongest fitting-record
baseline** (station x horizon historical mean; pooled 0.945 vs 0.942, network
0.805 vs 0.763; paired network difference +0.042 with CI spanning zero)."
NOT allowed: "uniquely superior in magnitude", "beats all baselines",
"large gains from seasonal stratification", "recoverability is a property of
the network".

---

## C2. Applicability boundaries

**Claim.** The valid domain of the empirical predictor is bounded in four
ways: (a) duration support, (b) model family, (c) missingness mechanism,
(d) environmental regime. Outside these boundaries the predictor does not
transfer; the boundaries are themselves the finding.

### C2a. Duration support

**Evidence required.** Interpolation and extrapolation performance of the
continuous support-aware risk surface (fit only on fitting-period
placements), plus the network-mean fallback's performance, at 14/60 d
(interpolation) and 365 d (extrapolation).

**Current evidence** (t04; surface fit on 100,397 fitting-period rows, pure
transfer to the second panel):
- Interpolated 14/60 d (448 units): pooled Spearman 0.774, calibration slope
  1.025, R2 0.443, RMSE 0.317 — well calibrated.
- Extrapolated 365 d (124 units): network rank 0.270, 90% interval coverage
  46.8% (the pre-specified 1.435x widening is insufficient; observed 365-d
  losses run to 9.4 C).
- Network-mean fallback (596 units, t02): network Spearman 0.562, pooled
  0.339, within-network rank undefined by construction.
- Abstaining the 124 extrapolated units (8.6% of units, 28.9% of total loss)
  raises released-unit surface network Spearman to 0.691 and R2 to 0.663
  (t04/t09) — justified for point release, NOT for loss-capturing budgets.

**Status: PARTIAL-STRONG as a boundary.** Interpolation-capable within
support; 365-d use unsupported without abstention.

**Allowed language.** "The surface interpolates at 14/60 d and is
interpolation-capable within the fitted duration range"; "365-day
extrapolation fails (rank 0.270, coverage 46.8%) and is unsupported unless
real fitting-period support exists at that horizon"; "the network-mean
fallback does not rank within networks (network 0.562, pooled 0.339)".
NOT allowed: "full-horizon risk estimator", "predicts at any gap duration",
"365-day predictions are valid with widened intervals".

### C2b. Model family

**Evidence required.** Model-source x model-target matrix with properly
trained neural baseline; diagonal vs off-diagonal comparison.

**Current evidence** (t05):
- Engineered-feature block (linear/PCHIP, seasonal ridge, donor ridge,
  XGBoost): self-transfer network Spearman 0.93-0.98, cross within block
  0.72-0.98; diagonal above off-diagonal (one-sided MWU p = 0.033) but the
  gap is carried by the block.
- BiLSTM: **cross-instance transfer** (its "self-transfer" cell is a
  different training instance, not the same-instance fitting-period stress):
  self 0.29-0.69 (network-level), cross to block -0.24..0.28, neural vs
  XGBoost stress Spearman 0.067.
- air2stream: self 0.64 (8 networks), cross to XGBoost ~0.24 (0.238).

**Status: STRONG within block / STRONG NEGATIVE across families.** Every
stress-curve claim must be model-conditional.

**Allowed language.** "Difficulty ordering is shared within the
engineered-regression block but pipeline-specific across architecture
families"; "neural cross-instance transfer is weak (self 0.29-0.69, cross
-0.24..0.28)". NOT allowed: "self-transfer of the BiLSTM" (relabel to
cross-instance), "a single generic score orders all models".

### C2c. Missingness mechanism

**Evidence required.** Missingness matrix with matched and mismatched curves
(trial gaps generated with the same mechanism as evaluation gaps).

**Current evidence** (t06): matched curves transfer strongly in the
agent_a panel — multi-block 0.944, donor-synchronous 0.979, forcing 0.881,
online 0.930, matched slopes 0.89-1.01; mismatched (uniform) curve applied to
support-destroying mechanisms collapses rank (donor-sync 0.979 -> 0.294,
forcing 0.881 -> 0.196, online 0.930 -> 0.399; under-predicts 1.1-2.3 C;
multi-block slope 0.90 -> 0.14).

**Harmonization caveat (v13, why this is demoted).** The two independent
implementations used different 12-network panels and disagree on the matched
donor-synchronous cell: agent_a 0.979 vs agent_b 0.490 (agent_b's closest
analog to planted geometry, slope 0.743). The mismatch-collapse direction is
consistent across both implementations (agent_b: donor-sync curve on uniform
gaps DeltaRho -0.846, slope -0.845; multi-block -0.182/-0.712), so the
directional conclusion is reproducible, but the matched-strength claim is
not. The mechanism-stratified numbers are therefore **evidence only after a
v13 harmonized re-run on one unified 12-network panel** (single mechanism
definitions, single scoring convention).

**Status: WEAK (demoted pending harmonization)** for matched-strength;
**PARTIAL-STRONG (directional)** for mismatch collapse.

**Allowed language.** "A uniform-grid curve is not a generic curve: applied
to donor-synchronous, forcing, or online gaps it misranks (collapse to
0.20-0.40) and under-predicts by 1.1-2.3 C"; "matched-curve strength is
implementation-divergent (donor-sync 0.979 vs 0.490 across independent
panels) and requires harmonization before it can be evidence". NOT allowed:
"mechanism-matched curves transfer at 0.88-0.98" as a headline without the
harmonization caveat; "a single stress curve supports all mechanisms".

### C2d. Environmental regime

**Evidence required.** Horizon decomposition of the conditional-covariance
estimand vs realized error; 365-day tail behavior.

**Current evidence** (t10): the operator column is the **expected Gaussian
MAE** sqrt(2/pi) x per-day conditional SD, not a variance/SD bound. Expected
Gaussian MAE saturates 0.379 -> 0.451 C (7 -> 365 d) while realized MAE
0.544 -> 4.719 C; RMSE 0.631 -> 5.755; remainder 0.165 -> 4.268 C is NOT
identifiable as model error + drift (also covariance misspecification,
parameter error, non-Gaussianity, aggregation, finite-sample bias). Linear
increment R2 +0.0171; learned-model increment 0.701 -> 0.704. The 365-day
tail is where the gap between bound and realized error is largest.

**Status: STRONG mechanism + STRONG correction** (as a boundary, reported in
SI in v13).

**Allowed language.** "Conditional covariance saturates (0.379 -> 0.451 C
expected Gaussian MAE) while realized error grows (0.544 -> 4.719 C); it
does not bound realized error and is not a general lower bound". NOT
allowed: "remainder = model error + drift"; "conditional-variance lower
bound".

---

## C3. Decision utility at prespecified coverage

**Claim.** Decision value is conditional and prespecified: fixed-budget
triage, model selection, and downstream protection each require a stated
coverage floor, an abstention rule with its cost, and a stated baseline
before any positive claim.

### C3a. Fixed-budget triage (full panel) — NEGATIVE

**Evidence required.** Captured-loss and NDCG at budget B with network
bootstrap and an oracle.

**Current evidence** (t09 Part 1; 1,446 units, 57 networks):
- CapturedLoss@20%: simple 0.512 [0.485, 0.537], duration+season 0.504,
  surface 0.500, gap length 0.498, **empirical (frozen) 0.338 [0.302, 0.380] —
  the worst non-random policy** (random 0.200, oracle 0.529).
- Paired empirical-simple -0.174 [-0.198, -0.140]; NDCG@20% simple 0.908 vs
  empirical 0.617.
- Mechanism: the network-mean fallback (572 units, incl. all 124 365-d units)
  under-ranks the largest losses (mean prediction 1.33 C vs observed 5.27 C
  at 365 d); 365-d units carry 28.9% of total loss.

**Status: STRONG NEGATIVE.**

**Allowed language.** "The frozen empirical predictor is the worst non-random
fixed-budget triage policy on the full panel". NOT allowed: "the empirical
predictor guides triage", "risk-based budgets capture loss at 20%".

### C3b. Model selection — null without abstention, exploratory with abstention

**Evidence required.** Model-selection regret vs dev-chosen best fixed,
global blocked-CV, per-network CV, and random; abstention rules with
coverage.

**Current evidence** (t09 Part 2; first panel, 1,440 units, 42 networks,
three families):
- No abstention: proposed risk selector regret 0.084 vs best fixed / global
  blocked-CV 0.081 — **no advantage** (paired diff +0.0037 [-0.0255,
  +0.0330]); per-network average-CV 0.038 beats it (in-sample by design).
- With per-family support + ambiguity abstention (8.5% coverage: 123 released
  units, 8 of 42 networks): regret 0.0067 [0.0019, 0.0120] vs comparators on
  the same released units (best fixed 0.151, global CV 0.151, per-network CV
  0.164, gap rule 0.145, random 0.341).
- The released set is confined to the 8 t05 networks (not a random sample);
  family-2/3 calibration is in-sample (slope ~1.02/1.04, common-scale
  sensitivity reproduces every headline number).

**Status: WEAK / proof of concept, NOT operational validation.** The
no-abstention result is a null; the abstention result is exploratory and
conditional on non-random networks.

**Allowed language.** "Without abstention the risk-based selector shows no
advantage over a dev-chosen best fixed family or global blocked-CV (0.084 vs
0.081)"; "with support + ambiguity abstention at 8.5% coverage (123
units/8 networks) released-unit regret drops to 0.0067 — a proof of concept
on networks with full per-unit fitting-period evidence, not an operational
validation". NOT allowed: "the selector beats CV-based selection", "model
selection is solved", any claim at coverage below the floor.

### C3c. Downstream protection — baseline-dependent

**Evidence required.** Thermal-metric distortion under two baselines
(no-fill status quo; climatology fill), with budget experiment and
network-level risk-distortion correlation.

**Current evidence** (t08):
- No-fill baseline (canonical, agent_b, 15 networks, 1,755 placements):
  reconstruction helps integrated metrics — recon/no-fill error ratio 0.12
  (annual mean), 0.14 (degree days), 0.13 (trend slope), 0.30 (p90), 0.34
  (days >20 C); 0 error in 88-95% of placements for single-event metrics;
  no-fill leaves amplitude undefined in 20.9% of placements. Risk scores
  order integrated-metric distortion at network level (annual mean 0.764,
  degree days 0.743, phase 0.729, p90 0.668) but NOT amplitude (0.089) or
  summer max (0.250).
- Climatology baseline (agent_a, 15 networks, 1,965 placements): the
  risk-policy top-20% budget is **worse than the no-recovery climatology
  baseline for threshold/extreme metrics** (combined reduction -0.177 vs
  random +0.026; exceed_25_days -0.43, amplitude -0.34, summer mean -0.23,
  exceed_20_days -0.22) because top-risk gaps are long summer gaps where the
  reconstruction's cold peak bias flips threshold crossings; annual mean
  still protected (+0.02).
- Both baselines are reported; the incremental-benefit framing is used.

**Status: PARTIAL, baseline-dependent.** No single positive or negative
downstream sentence without naming the baseline.

**Allowed language.** "Reconstruction reduces distortion versus no-fill for
integrated metrics (12-14% of no-fill error) and restores computability";
"against a climatology-fill no-recovery baseline, a risk-targeted budget is
worse for threshold and extreme metrics (exceed_25_days -0.43)"; "the
incremental benefit of reconstruction is baseline-dependent". NOT allowed:
"reconstruction protects downstream metrics" unqualified; "the risk score
ranks threshold-metric distortion".

### C3d. Coverage floor and protocol requirement

**Evidence required for any positive decision claim.** A prespecified
coverage floor — **>= 50% of units and >= 60% of networks released** — a
stated abstention cost, a coverage-regret curve, and a preregistered
protocol. v13 contains no positive decision claim: the 8.5% coverage result
is below the floor by construction.

**Status: no operational claim in v13.** A positive decision claim requires
protocol v4 (v3 extended with the coverage floors, abstention rules, and
incremental-benefit endpoints, frozen before outcomes on a third,
outcome-disjoint panel).

---

## Claims explicitly NOT made in v13

- **No strongest-screen claim.** The empirical predictor is not "the best
  screen" anywhere; on the full panel it is the worst non-random triage
  policy (C3a).
- **No superiority over the station x horizon historical mean.** The claim is
  "ranks at least as well as the strongest fitting-record baseline" (pooled
  0.945 vs 0.942; paired network +0.042 with CI spanning zero; predictor
  correlation 0.992); not "uniquely superior in magnitude" (C1).
- **No generic-curve transfer.** A uniform-grid curve does not transfer to
  donor-synchronous, forcing, or online gaps, nor across model families
  (C2b, C2c).
- **No 365-day use without abstention.** Extrapolation rank 0.270, coverage
  46.8%; abstention is justified for point release only, never for
  loss-capturing budgets (C2a, C3a).
- **No self-transfer for the BiLSTM.** The BiLSTM "self-transfer" cell is
  cross-instance transfer (different training instances); relabeled
  (C2b).
- **No missingness strong evidence pre-harmonization.** Matched donor-sync
  strength is implementation-divergent (0.979 vs 0.490); harmonization on
  one panel is required before it is evidence (C2c).
- **No downstream claim vs climatology for threshold metrics.** Against a
  climatology-fill baseline, risk-policy budgets are worse for threshold and
  extreme metrics (exceed_25_days -0.43); downstream statements are
  baseline-dependent (C3c).
- **No operational model-selection claim below the coverage floor.** The
  0.0067 regret result is a proof of concept at 8.5% coverage (123 units /
  8 networks), below the >= 50% units / >= 60% networks floor; no positive
  decision claim without protocol v4 (C3b, C3d).
- **No model-agnostic recoverability.** All ranking claims are
  model-conditional ("the curve ranks the model that produced it").
- **No full-horizon risk estimator.** The surface is interpolation-capable
  within support, not a predictor at any duration (C2a).
- **No conditional-covariance bound.** Expected Gaussian MAE is not a
  variance/SD estimator and not a general lower bound on realized error
  (C2d).
- **No automatic filling or station removal.** Nothing in the revision adds
  a certified safe-fill or placement margin (t09; v11 protocol history).
- **No external preregistration claim.** v2 is internally hash-bound,
  same-commit; v3 is drafted, not registered; v4 is required for decision
  endpoints; no third-panel outcomes exist.

## v13 primary reporting order (Results)

1. **Strongest-baseline comparison** (C1): same-unit paired comparison vs
   the station x horizon historical mean (r6) and simple descriptors; the
   honesty sub-row (0.992 correlation; paired +0.042 CI spanning zero) is
   reported first, then the persistence claim.
2. **Support and duration** (C1 + C2a): exact local support tier (841/874,
   0.887), support hierarchy (five tiers), interpolation 14/60 d (0.774,
   slope 1.025), extrapolation boundary (0.270 / 46.8%).
3. **Within-network stability** (C1): per-horizon ranks (0.932/0.916/0.865/
   0.659), residualized pooled 0.936, median within-network 0.965; rolling
   origin and history length to SI.
4. **Decision experiment** (C3): full-panel triage negative (0.338 vs 0.512;
   paired -0.174 [-0.198, -0.140]); model selection null without abstention
   (0.084 vs 0.081) and the exploratory abstention result at 8.5% coverage;
   coverage floor and protocol v4 requirement.
5. **Downstream** (C3c): no-fill baseline protection of integrated metrics;
   climatology baseline negative for threshold/extreme metrics; both
   baselines, incremental-benefit framing.
6. **Model boundaries** (C2b): engineered block (self 0.93-0.98, cross
   0.72-0.98), neural cross-instance weakness, air2stream (0.64/8 networks).
7. **Missingness** (C2c): mismatch collapse direction (0.979 -> 0.294 etc.),
   implementation divergence (0.979 vs 0.490), demoted pending
   harmonization.
8. **Covariance mechanism (C2d) to Supporting Information** (expected
   Gaussian MAE saturation 0.379 -> 0.451 vs realized 0.544 -> 4.719;
   estimand correction).
