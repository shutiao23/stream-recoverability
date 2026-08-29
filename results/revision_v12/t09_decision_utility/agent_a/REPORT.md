# Revision v12, task 09 — End-to-end decision utility (agent A, adversarial pair)

**Namespace:** `results/revision_v12/t09_decision_utility/agent_a/`
**Script:** `scripts/rev_v12_t09_decision_utility_a.py` (runtime ≈ 3 min, CPU only)
**Date:** 2026-08-29

Two experiments demanded by the reviews: (1) fixed-budget gap prioritization on the
second panel (1,446 units, 57 networks) under seven risk scores; (2) model selection
among `seasonal_boundary_ridge`, `donor_blup_ridge`, `xgboost_b_d` on the first panel
(1,440 units, 42 networks), with uncertainty-penalized risk-based selection and
abstention. All numbers below were produced by the script in this namespace from
read-only inputs; nothing under `results/` outside this namespace was modified.

---

## HEADLINE (answers first)

**Part 1 — prioritization: YES, risk-based prioritization beats the frozen empirical
predictor by a wide margin, and the simple descriptor model is the best practical
policy.**
At a 20% budget, CapturedLoss@20% is 0.512 (bootstrap CI 0.485–0.537) for the simple
descriptor model, 0.504 (0.475–0.531) for duration+season, 0.500 (0.463–0.533) for the
hierarchical surface, 0.500 (0.471–0.530) for raw gap length, **0.338 (0.302–0.380) for
the frozen empirical transfer predictor**, 0.200 for random and 0.529 for the oracle.
The empirical predictor loses **−17.4 points of captured loss vs the simple model
(95% CI −19.8 to −14.0)** and **−16.3 vs the surface (CI −18.7 to −13.3)**; the surface
vs simple difference is −1.2 points (CI −3.1 to +0.3, not significant). The empirical
predictor's failure is structural: its network-mean fallback tier (572 units, including
all 124 365-day units) under-ranks the largest losses (mean prediction 1.33 °C vs
observed 5.27 °C at 365 d), so a fixed budget spent on its top ranks misses the loss
mass. NDCG@20%: simple 0.908 (0.879–0.936), duration+season 0.899, gap 0.898, surface
0.861 (0.800–0.917), empirical 0.617 (0.572–0.672).

**Part 2 — selection: the risk-based selector does NOT beat a dev-chosen best fixed
family or global blocked-CV on the full first panel (difference +0.0037 °C, CI
−0.025 to +0.033), and the per-network average-CV comparator beats it significantly
(0.038 vs 0.085, non-overlapping CIs).** BUT with abstention, the picture reverses:
when every family has unit-level fitting-period evidence (8 of 42 networks, 123 units,
8.5% coverage), the proposed selector's network-balanced regret drops to **0.0067
(CI 0.0019–0.0120)** — an order of magnitude below every comparator evaluated on the
same released units (best fixed 0.151, global CV 0.151, per-network CV 0.164, gap rule
0.145, random 0.341). The winning families are nearly tied in mean loss
(donor ridge 1.270, xgboost 1.274 on the first panel), so the no-abstention
comparison is dominated by a coin-flip donor-vs-xgboost choice; per-unit selection
matters only where per-unit fitting-period stress exists for all candidates, and there
it matters a lot.

---

## PART 1 — Budget-constrained prioritization (second panel, 1,446 units, 57 networks)

### Scores evaluated (policy = rank units by score, descending; tie-break seeded)

| policy | score | note |
|---|---|---|
| (a) gap_length | raw `gap_length` (d) | ties broken by seeded random permutation (seed 42) |
| (b) durseason | fitted duration+season risk | season per unit = dominant season of the unit's placement roster (`scoring/placement_losses.csv` `gap_start` → mean DOY → DJF/MAM/JJA/SON; `candidates.csv` carries no season, so the placement roster was used — reconstructable for all 1,446 units); curve = per-season monotone (isotonic PAV in log gap) curve of log1p(MAE) fit on pooled development + first-panel fitting-period placements (47,408 + 52,989 rows), evaluated at the unit's (season, gap) |
| (c) simple | `simple_fitperiod` column of `t01_paired_comparison/agent_a/predictions.csv` (route-A descriptors, coefficients fit on fitting-period only: development + first panel) | reused read-only |
| (d) empirical | `empirical_transfer_prediction` (frozen) | reused read-only; has heavy ties (network-mean fallback) |
| (e) surface | `surface_prediction_mae` from `t04_risk_surface/agent_a/second_panel_predictions.csv` | reused read-only |
| (f) random | 20 seeded uniform permutations | reported as mean over draws |
| (g) oracle | observed loss (upper bound) | |

Budget B ∈ {5, 10, 20, 30}% → k = ceil(B × 1446) top-ranked units.

Metrics per (policy, budget): CapturedLoss@B = Σ loss(top-k)/Σ total loss;
worst-decile recall@B = mean over networks of |network worst-decile (top
ceil(0.1·n_net) loss units) ∩ global top-k| / |decile|; NDCG@B = position-discount DCG
over the score-ranked list truncated at k, normalized by the ideal (loss-ranked)
DCG@k; regret = oracle CapturedLoss − policy CapturedLoss.

### Results (utility table; `utility_table_part1.csv`, fig `utility_curves_part1.png`)

| policy | Captured@5% | Captured@10% | Captured@20% | Captured@30% | wd-recall@20% | NDCG@20% |
|---|---|---|---|---|---|---|
| oracle | 0.2071 | 0.3414 | 0.5294 | 0.6418 | 0.898 | 1.000 |
| simple | 0.1827 | 0.3131 | 0.5145 | 0.6157 | 0.842 | 0.909 |
| durseason | 0.1657 | 0.2956 | 0.5061 | 0.6142 | 0.842 | 0.900 |
| surface | 0.1563 | 0.2861 | 0.5039 | 0.6253 | 0.806 | 0.856 |
| gap_length | 0.1715 | 0.3154 | 0.4982 | 0.6151 | 0.798 | 0.893 |
| empirical | 0.1169 | 0.2045 | 0.3367 | 0.4833 | 0.398 | 0.613 |
| random | 0.0508 | 0.1011 | 0.2003 | 0.3008 | 0.200 | 0.336 |

Top-20% sets: simple/gap/durseason/surface overlap heavily (Jaccard 0.74–0.86 among
themselves); empirical overlaps only 0.31–0.37 with each of them
(`policy_overlap_part1.csv`).

### Network bootstrap (2,000 draws, resample 57 networks with replacement; multiset convention — a sampled network's units enter the draw as many times as the network was drawn; `bootstrap_part1.csv`)

| quantity | mean | 95% CI |
|---|---|---|
| CapturedLoss@20% simple | 0.5119 | 0.4852 – 0.5372 |
| CapturedLoss@20% durseason | 0.5039 | 0.4755 – 0.5313 |
| CapturedLoss@20% surface | 0.5004 | 0.4628 – 0.5328 |
| CapturedLoss@20% gap_length | 0.5000 | 0.4712 – 0.5295 |
| CapturedLoss@20% empirical | 0.3377 | 0.3019 – 0.3799 |
| NDCG@20% simple | 0.9084 | 0.8788 – 0.9360 |
| NDCG@20% surface | 0.8608 | 0.7998 – 0.9170 |
| NDCG@20% empirical | 0.6168 | 0.5716 – 0.6723 |
| **diff empirical − simple** | **−0.1742** | **−0.1984 – −0.1396** |
| **diff empirical − surface** | **−0.1626** | **−0.1875 – −0.1327** |
| diff surface − simple | −0.0116 | −0.0308 – +0.0031 |

All three bootstrap differences use paired draws (same resampled networks). The
empirical predictor is significantly worse than both the simple model and the surface
at every level of the bootstrap; the surface and simple are statistically
indistinguishable at the 20% budget (surface edges ahead at 30%: 0.6253 vs 0.6157).

### Why the empirical predictor fails as a prioritization instrument

Pooled Spearman vs observed loss: empirical 0.740, simple 0.835, surface 0.893, gap
0.819. Within the empirical fallback tier (572 units), pooled Spearman is 0.388 and
the predictor takes only 57 distinct values (network means). The 365-day units (the
largest losses, mean 5.27 °C) receive fallback predictions averaging 1.33 °C, so they
rank below ~40% of the panel despite carrying 28.9% of total loss. This is not a
criticism of the predictor's published network-level calibration (0.715 network
Spearman), but a decision-context failure: **for fixed-budget triage the frozen
empirical predictor is the worst non-random policy**.

### Abstention coverage-risk curve (Part 1; `abstention_curve_part1.csv`, fig `abstention_curve_part1.png`)

Rules: (A) surface extrapolation flag (`support_status == extrapolated`, 124 units);
(B) old-predictor fallback support tier (`horizon_group == fallback` in t01, 572
units); (C) union (identical to B, since the 124 extrapolated units are all in the
fallback tier). For each rule: fraction abstained, share of total loss abstained, and
the surface policy's CapturedLoss@B recomputed on the released units only.

| rule | abstained | loss share | released | surface Captured@5/10/20/30 (released-normalized) | oracle (released) |
|---|---|---|---|---|---|
| A: surface extrapolated | 8.6% | 28.9% | 1,322 | 0.140 / 0.256 / 0.431 / 0.546 | 0.165 / 0.287 / 0.452 / 0.572 |
| B: old fallback tier | 39.6% | 46.6% | 874 | 0.121 / 0.238 / 0.434 / 0.575 | 0.153 / 0.275 / 0.461 / 0.592 |

Reference (t04 agent_a `abstention_curve.csv`): abstaining the 124 extrapolated units
raised released-unit network Spearman 0.674 → 0.691 and R² 0.475 → 0.663. The trade-off
is explicit: rule A buys rank-quality on the released units at the cost of abstaining
8.6% of units carrying **28.9% of the total loss** (the 365-day tail); rule B abstains
39.6% of units carrying 46.6% of total loss and is too aggressive for a
loss-capturing prioritization use. Abstention is therefore only justified for
point-use release decisions (as t04 recommends), not for budget allocation when the
365-day gaps are in scope.

---

## PART 2 — Model selection with abstention (first panel, 1,440 units, 42 networks)

### Per-family predicted loss (exact construction)

Unit = (network, station, gap); unit outer loss per family = mean over roster
placements of `mae_deg_c` (`confirmation_model_roster_losses.csv`).

1. **Per-family fitting-period stress.** `xgboost_b_d`: empirical fit losses
   (development + first-panel `*_empirical_fit_losses.csv`, 100,397 placements).
   `seasonal_boundary_ridge` / `donor_blup_ridge`: t05 agent_a
   `source_fit_stress_families_1_3.csv` (12 networks: 8 first + 4 second
   confirmation, 895 placements per family, gaps {7,30,90,180}).
2. **Per-family duration curve** C_f(g): pooled placements, per-gap mean of
   log1p(MAE), isotonic (PAV) in log gap, piecewise-linear in log gap, extrapolated
   beyond 180 d with the edge segment slope. Used (i) for the gap-length-rule
   comparator and (ii) as the curve-only fallback below.
3. **Unit-level predicted stress** s_f(u): if the unit has its own family-f
   placements, its per-gap means form the unit's own monotone curve, evaluated at the
   unit's target gap (interpolation for 14/60 d, extrapolation for 365 d with the
   edge slope) — flag `unit`; otherwise C_f(g_u) — flag `curve`.
4. **Recalibration to outer-loss scale** (per family, OLS: outer ≈ a + b·s on
   fitting-period rows where both stress and roster outer loss are observed; raw
   scale, unrestricted intercept; `selection_calibration_part2.csv`):

| family | n rows | networks | intercept | slope | R² | resid SD | rows used |
|---|---|---|---|---|---|---|---|
| seasonal_boundary_ridge | 119 | 8 | +0.019 | 1.023 | 0.925 | 0.250 | first panel only (t05 stress does not cover development networks) |
| donor_blup_ridge | 119 | 8 | −0.005 | 1.039 | 0.928 | 0.212 | first panel only |
| xgboost_b_d | 673 | 42 | +0.024 | 0.982 | 0.920 | 0.239 | development (640) + first panel (673) |

   The spec's "if available" branch applied: development + first-panel fit rows exist
   for xgboost; for families 2/3 no development stress rows exist (t05 ran only
   confirmation networks), so first-panel rows were used and the regression is
   in-sample for those families. The fitted slopes are ≈ 1 with intercept ≈ 0, i.e.
   the calibration is effectively an identity mapping; the common-scale-factor
    alternative (single OLS-through-origin scale c applied to all raw stresses,
    c = 1.006 over 911 pooled fit rows, `common_scale_c.json`) is reported as a
    robustness check and gives statistically identical
   results (below), so the in-sample calibration does not drive any finding.
5. **Predicted risk** r_f(u) = a_f + b_f·s_f(u); **interval width** w_f(u) =
   2·z₉₀·(family resid SD), inflated by (1 + 2·max(0, log(g/180)/log(180/7))) for
   gaps beyond 180 d (365-day extrapolation).
6. **Selection**: argmin over families of r_f + λ·w_f, λ ∈ {0, 0.5, 1}.
7. **Abstention**: ambiguous if the two smallest penalized risks are within 10%
   (r₂ ≤ 1.10·r₁); support-missing if any family (rule `any`) or the winning family
   (rule `winner`) rests on `curve`-only stress.

### Regret table (`selection_regret_table_part2.csv`, fig `selection_regret_part2.png`)

Per-unit regret = L_selected − min_A L_A. Network-balanced regret = mean over the 42
networks of within-network mean regret. Comparators: (i) best fixed family chosen on
development unit-level outcomes — xgboost (dev mean loss 1.236 vs donor 1.310,
seasonal 1.970); (ii) global blocked-CV = leave-one-network-out CV on pooled
dev+first roster, selects xgboost (identical to best fixed on this panel); (iii)
per-network average-CV = per-network leave-one-unit-out CV on the network's own
first-panel roster (in-sample benchmark); (iv) gap-length rule = argmin C_f(g);
(v) random, 20 seeds; (vi) proposed (λ ∈ {0, 0.5, 1} × abstention); (vii) oracle.

| selector | λ | abstention | abstained | net-balanced regret | worst-network regret | mean unit regret | top-2 hit |
|---|---|---|---|---|---|---|---|
| oracle | — | none | 0% | 0.0000 | 0.000 | 0.000 | — |
| per-network avg-CV | — | none | 0% | **0.0383** | 0.129 | 0.037 | — |
| best fixed (dev) | — | none | 0% | 0.0815 | 0.430 | 0.104 | — |
| global blocked-CV | — | none | 0% | 0.0815 | 0.430 | 0.104 | — |
| proposed risk | 0.0 | none | 0% | 0.0838 | 0.404 | 0.092 | 0.892 |
| proposed risk | 0.5 | none | 0% | 0.0850 | 0.404 | 0.093 | 0.897 |
| proposed risk | 1.0 | none | 0% | 0.0877 | 0.404 | 0.095 | 0.902 |
| common-scale rule | — | none | 0% | 0.0865 | 0.404 | 0.094 | — |
| gap-length rule | — | none | 0% | 0.0927 | 0.309 | 0.102 | — |
| random | — | none | 0% | 0.2628 | 0.557 | 0.279 | — |
| proposed | 0.5 | ambiguous | 31.6% | 0.0998 | 0.516 | 0.112 | 0.870 |
| proposed | 0.5 | ambiguous + support_any | **91.5%** | **0.0067** | 0.029 | 0.012 | 0.951 |
| proposed | 0.5 | ambiguous + support_winner | 67.0% | 0.0476 | 0.409 | 0.046 | 0.987 |

Notes: (i) best-fixed and global CV coincide because both pick xgboost; (ii) the
`ambiguous`-only abstention does not help — near-ties are cheap, so removing them
leaves the harder, higher-regret units; (iii) the `support_any` rule releases exactly
the 123 units (8 of 42 networks) where all three families have unit-level
fitting-period stress.

### Network bootstrap for regret differences (2,000 draws, resample 42 networks; `bootstrap_part2.csv`)

| quantity | mean | 95% CI |
|---|---|---|
| regret best fixed / global CV | 0.0815 | 0.0584 – 0.1034 |
| regret proposed λ=0.5 (no abstention) | 0.0852 | 0.0638 – 0.1050 |
| regret per-network avg-CV | 0.0384 | 0.0302 – 0.0462 |
| **diff proposed λ=0.5 − best fixed** | **+0.0037** | **−0.0255 – +0.0330** |
| diff proposed λ=0.5 − global CV | +0.0037 | −0.0255 – +0.0330 |
| **regret proposed λ=0.5 with abstention (released)** | **0.0067** | **0.0019 – 0.0120** |

The proposed selector is statistically indistinguishable from best-fixed/global-CV on
the full panel (CI spans ±0.033 °C) and significantly worse than per-network avg-CV
(0.085 vs 0.038, non-overlapping CIs). With abstention its released-unit regret is an
order of magnitude below all comparators on the same units
(`abstention_comparison_part2.csv`):

| abstention (λ=0.5) | released | proposed | best fixed | global CV | per-net CV | gap rule | common scale | random |
|---|---|---|---|---|---|---|---|---|
| ambiguous | 985 | 0.0998 | 0.1036 | 0.1036 | 0.0512 | 0.1093 | 0.0998 | 0.323 |
| ambiguous + support_any | 123 | **0.0067** | 0.1508 | 0.1508 | 0.1636 | 0.1447 | 0.0068 | 0.341 |
| ambiguous + support_winner | 475 | 0.0476 | 0.0806 | 0.0806 | 0.0875 | 0.0921 | 0.0476 | 0.353 |

### Abstention coverage-risk curve (Part 2, λ=0.5; `abstention_curve_part2.csv`, fig `abstention_curve_part2.png`)

Ambiguity threshold δ ∈ {0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30} × support rule
{none, winner, any}. At δ = 0.10 with `support_any`: 91.5% abstained, released-unit
network-balanced regret 0.0067, abstained units carry 91.4% of the panel's min-loss
mass. The `any`-support rule is the sharp lever (it releases only networks with
fitting-period evidence for all candidates); the ambiguity sweep alone trades small
amounts of coverage for a slight regret *increase* (0.085 → 0.100 at δ = 0.10), again
because near-ties are cheap.

### Top-2 hit rate (proposed)

0.892 / 0.897 / 0.902 for λ = 0 / 0.5 / 1 on all 1,440 units; 0.951 on the released
units (λ = 0.5). Note the true-best family is donor-ridge or xgboost for 99.1% of
units (seasonal ridge is best on only 13 units), so the three-way top-2 rate has a
random baseline of 2/3; the proposed rate is informative but not dramatic.

### Honest limitations (Part 2)

- The family-2/3 calibration regression is in-sample (8 networks); its fitted mapping
  is near-identity (slope ≈ 1.02/1.04, intercept ≈ 0), and the common-scale
  sensitivity reproduces every headline number, so the calibration leakage does not
  drive the results — but the family-2/3 stress itself exists only on the 8 t05
  networks, and nothing in the read-only artifacts can change that.
- The released `support_any` set (123 units) is confined to the 8 t05 first-panel
  networks, which t05 selected (not a random sample); the strong released-unit result
  is conditional on those networks and on unit-level fitting-period stress existing
  for all three families.
- 365-day units are extrapolations of the per-unit curves (gaps beyond the 180 d
  support); their interval widths are inflated and they are frequently flagged
  ambiguous or abstained — 365-day units are 15 of the 123 released units, where the
  proposed selects donor/xgboost mostly by per-unit 90–180 d trends.
- The per-network average-CV comparator uses the evaluated networks' own outcomes
  (in-sample by design); it is the strongest benchmark and the one the proposed
  method cannot beat without per-unit fitting-period support.

---

## Deliverables (all in `results/revision_v12/t09_decision_utility/agent_a/`)

| file | content |
|---|---|
| `utility_table_part1.csv` | CapturedLoss@B, worst-decile recall@B, NDCG@B, regret per policy × budget |
| `bootstrap_part1.csv` | 2,000-draw CIs: CapturedLoss@20% and NDCG@20% per policy; 3 paired differences |
| `abstention_curve_part1.csv` | abstention rules × budgets: fraction abstained, loss share, released-unit utility |
| `durseason_curve_part1.csv`, `policy_overlap_part1.csv` | season curves; top-20% Jaccard overlaps |
| `selection_regret_table_part2.csv` | all selectors × λ × abstention: regret, top-2 hit, coverage |
| `selection_calibration_part2.csv` | per-family recalibration (n, slope, intercept, R², resid SD) |
| `bootstrap_part2.csv` | 2,000-draw CIs: regret per selector; proposed-vs-best-fixed and proposed-vs-global-CV differences; abstaining variant |
| `abstention_curve_part2.csv` | λ=0.5 ambiguity-δ × support-rule coverage-risk curve |
| `abstention_comparison_part2.csv` | comparators on the same released units (fair coverage-risk view) |
| `selection_predictions_part2.csv` | per-unit: per-family risk/width/support/loss, selected family per λ, true best |
| `common_scale_c.json` | common-scale factor c (robustness) |
| `summary.json` | run metadata |
| `utility_curves_part1.png`, `abstention_curve_part1.png`, `selection_regret_part2.png`, `abstention_curve_part2.png` | figures |
