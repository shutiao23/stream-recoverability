# REPORT — End-to-end decision utility (revision v12, t09, agent B)

**Script:** `scripts/rev_v12_t09_decision_utility_b.py`
**Output namespace:** `results/revision_v12/t09_decision_utility/agent_b/`
**Date:** 2026-08-29. Every number below was produced by this script from the
read-only artifacts listed; no value is taken from any other source.

## 1. Design

Two decision experiments, both end-to-end (risk score -> rank/budget, or per-family
stress curve -> model selection), evaluated against observed recovery losses.

**Part 1 — budget-constrained gap prioritization, second panel** (1,446 units, 57
networks). Policies: (a) gap length; (b) duration+season (OLS log1p(MAE) ~ log(gap)
+ season dummies fit on pooled XGBoost fitting-period placements — development
(47,408) + first panel (52,989); season per unit =
plurality season of the unit's placement roster dates (`second_confirmation/scoring/
placement_losses.csv` gap_start, month-based bins validated 100% against the
project `season` column; every unit had placements, so no gap-only fallback was
needed); (c) simple descriptors = t01 `simple_fitperiod` (equal-network weighted
fit-period linear model, read-only); (d) empirical curve =
`empirical_transfer_prediction` (read-only); (e) hierarchical surface = t04 agent_a
`surface_prediction_mae` (read-only); (f) random (20 seeded draws); (g) oracle
(observed loss). Budgets B = 5/10/20/30% of units. Metrics: CapturedLoss@B =
loss of top-B% units / total loss; worst-decile recall@B = overlap of top-B% with
the worst decile (top 10% by observed loss); NDCG@B with gain 2^loss−1 over the
top-B% positions; regret@B = oracle CapturedLoss − method CapturedLoss (pp).
Ties in scores broken by stable index order (documented). Fitted duration+season
coefficients (log1p scale, DJF baseline): MAM +0.129, JJA +0.118, SON +0.097; log-gap slope 0.1941; fit R2 = 0.362, RMSE(log1p) = 0.317

**Part 2 — model selection, first panel** (1,440 units, 42 networks). For each unit,
per-family predicted loss (families: seasonal_boundary_ridge, donor_blup_ridge,
xgboost) from per-family fitting-period stress curves, recalibrated to the
outer-loss scale, plus uncertainty penalty λ × interval width, λ ∈ {0, 0.5, 1}.

### 1.1 Per-family stress and calibration (Part 2) — exact recipe

- **xgboost stress**: unit-level mean MAE of read-only `confirmation_empirical_fit_losses.csv`
  placements (gaps 7/30/90/180, 42 networks); units at gaps 14/60/365 (767/1,440)
  receive the network-level mean of unit stresses (same fallback structure as the
  empirical predictor). Development-panel stress identically from
  `development_empirical_fit_losses.csv`.
- **ridge-family stress**: t05 agent B `fit_losses_families_1_3.csv` unit-level means
  (10 first-panel networks, gaps 7/30/90/180); 297 first-panel units carry the
  family-specific stress (143 units per family at the fit gaps, 154 further units of
  the same 10 networks at other gaps).
- **Two calibration mappings per ridge family** (OLS outer ~ stress, unit rows):
  (1) `t05` — outer ~ family-specific t05 stress on the 143 matched rows (first-panel
  rows only; no development family-specific fitting-period stress exists in read-only
  artifacts — documented); (2) `axis` — outer ~ xgboost fitting-period stress on the
  matched direct rows pooled over development + first panel (n = 1,313 per family),
  i.e. the conditional expectation of the family's outer loss given the xgboost stress.
  The xgboost family uses only the `axis` mapping (n = 1,313, development+first-panel
  fit rows). Units on the 10 t05 networks use the `t05` mapping; all other units use
  the `axis` mapping (proxy tier, justified by the t05 shared-difficulty block: xgboost
  stress vs ridge-family outer losses, network Spearman 0.72–0.94).
- **Interval width**: 2×1.96× prediction SE from the mapping's OLS at the unit's
  stress value (leverage formula). Units whose xgboost stress is a network-mean
  fallback get the interval widened by the fallback error σ_fb (RMSE of unit stress ~
  network mean over direct rows, 0.7603 °C): width = 2×1.96×
  √(SE² + (b·σ_fb)²).
- **Selection**: argmin_f [risk_f + λ·width_f]. **Abstention**: top-two penalized
  scores within 10% (relative gap) or missing support (a unit with no stress at all;
  count reported — 0 units, because the fallback/proxy tiers cover every unit).
  A strict-support rule (abstain every unit whose ridge-family stress is proxy) is
  reported as a sensitivity row in the abstention curve (threshold = −1).

### 1.2 Part 2 comparators — exact recipe

- (i) **best fixed family**: family with the lowest mean unit-level outer loss on the
  development panel (1,548 units, 56 networks) — xgboost.
- (ii) **global blocked-CV**: leave-one-network-out on the 42 first-panel networks;
  for each held-out network, select the family with the lowest mean unit loss on the
  other 41 networks; apply that family to all units of the held-out network.
- (iii) **per-network average-CV**: for each unit, per-family score = mean unit loss of
  that family over the OTHER units of the same network (leave-one-unit-out within
  network); select argmin per unit.
- (iv) **gap-length rule**: per gap length, the family with the lowest mean development
  outer loss at that gap (chosen on development outcomes), applied to first-panel
  units by gap.
- (v) **random**: 20 seeded draws.
- (vi) **proposed risk-based** with/without abstention (λ sweep).
- (vii) **outcome oracle**: argmin actual loss per unit (regret baseline).

Regret = L_selected − min_f L_f per unit (°C). Reported: network-balanced regret
(mean over networks of within-network mean regret), worst-network regret, top-2 hit
rate (selected family is not the unique worst family for the unit), pooled regret.

## 2. Validation cross-checks

- Second panel: 1,446 units / 57 networks; direct 874, fallback 572 (t01 horizon_group),
  surface support direct 874 / interpolated 448 / extrapolated 124 — matches t04.
- Season bins (month-based) reproduce the project `season` column on 100% of the
  52,989 first-panel fit placements.
- First panel: 1,440 units / 42 networks; 3 families × 28,728 placements; dev panel
  1,548 units / 56 networks.
- t05 stress coverage: 10 networks, 143 units per ridge family, all with roster outer
  loss (calibration rows). First-panel units on those 10 networks: 297.

## 3. Part 1 — prioritization results

### 3.1 CapturedLoss@B, NDCG@B, worst-decile recall@B, regret (pp)

| policy | B | CapturedLoss | worst-decile recall | NDCG | regret (pp) |
|---|---|---|---|---|---|
| gap_length | 5% | 0.1807 | 0.4690 | 0.4797 | 2.42 |
| gap_length | 10% | 0.3173 | 0.7379 | 0.6149 | 2.41 |
| gap_length | 20% | 0.4991 | 0.9448 | 0.6391 | 2.93 |
| gap_length | 30% | 0.6110 | 1.0000 | 0.6521 | 3.08 |
| dur_season | 5% | 0.1577 | 0.3793 | 0.3447 | 4.73 |
| dur_season | 10% | 0.3163 | 0.7448 | 0.5720 | 2.51 |
| dur_season | 20% | 0.5044 | 0.9862 | 0.6035 | 2.40 |
| dur_season | 30% | 0.6142 | 1.0000 | 0.6118 | 2.77 |
| simple | 5% | 0.1797 | 0.4207 | 0.5217 | 2.52 |
| simple | 10% | 0.3131 | 0.7379 | 0.5992 | 2.82 |
| simple | 20% | 0.5134 | 0.9931 | 0.6352 | 1.50 |
| simple | 30% | 0.6157 | 1.0000 | 0.6400 | 2.62 |
| empirical | 5% | 0.1156 | 0.2276 | 0.1017 | 8.94 |
| empirical | 10% | 0.2045 | 0.2690 | 0.1203 | 13.68 |
| empirical | 20% | 0.3362 | 0.3517 | 0.1816 | 19.22 |
| empirical | 30% | 0.4829 | 0.5586 | 0.3375 | 15.89 |
| surface | 5% | 0.1535 | 0.3241 | 0.3548 | 5.14 |
| surface | 10% | 0.2861 | 0.6000 | 0.4453 | 5.53 |
| surface | 20% | 0.5015 | 0.9448 | 0.5674 | 2.69 |
| surface | 30% | 0.6253 | 1.0000 | 0.5861 | 1.65 |
| oracle | 5% | 0.2049 | 0.4966 | 1.0000 | 0.00 |
| oracle | 10% | 0.3414 | 1.0000 | 1.0000 | 0.00 |
| oracle | 20% | 0.5284 | 1.0000 | 1.0000 | 0.00 |
| oracle | 30% | 0.6418 | 1.0000 | 1.0000 | 0.00 |
| random | 5% | 0.0507 | 0.0517 | 0.0469 | 15.42 |
| random | 10% | 0.1037 | 0.1086 | 0.0776 | 23.77 |
| random | 20% | 0.2030 | 0.1986 | 0.1224 | 32.54 |
| random | 30% | 0.3045 | 0.3076 | 0.1640 | 33.73 |

Random rows are means over 20 seeded draws (SD of CapturedLoss ≈ 0.0083).

### 3.2 Network-bootstrap 95% CI — CapturedLoss@20% differences (2,000 draws)

| pair | mean diff | 95% CI | frac draws > 0 |
|---|---|---|---|
| empirical − simple | -0.1755 | [-0.2008, -0.1431] | 0.000 |
| empirical − surface | -0.1647 | [-0.1916, -0.1333] | 0.000 |
| surface − simple | -0.0108 | [-0.0274, +0.0020] | 0.066 |

### 3.3 Abstention coverage-risk curve (budget 20%, surface ranking)

Captured loss of the released units' top-20% (within released total, and relative to
the full-panel total). All policies are in `part1_abstention_curve.csv`.

| rule | fraction abstained | n released | captured@20 (released) | captured@20 (full total) |
|---|---|---|---|---|
| none | 0.000 | 1446 | 0.5015 | 0.5015 |
| extrapolated | 0.086 | 1322 | 0.4298 | 0.3055 |
| fallback_tier | 0.396 | 874 | 0.4345 | 0.2321 |
| extrapolated_or_fallback | 0.396 | 874 | 0.4345 | 0.2321 |
| extrap_factor> 0 | 0.086 | 1322 | 0.4298 | 0.3055 |
| extrap_factor> 0.05 | 0.086 | 1322 | 0.4298 | 0.3055 |
| extrap_factor> 0.1 | 0.086 | 1322 | 0.4298 | 0.3055 |
| extrap_factor> 0.15 | 0.086 | 1322 | 0.4298 | 0.3055 |
| extrap_factor> 0.2 | 0.086 | 1322 | 0.4298 | 0.3055 |
| extrap_factor> 0.217718 | 0.000 | 1446 | 0.5015 | 0.5015 |
| extrap_factor> 0.25 | 0.000 | 1446 | 0.5015 | 0.5015 |

## 4. Part 2 — model-selection results

### 4.1 Selection regret by strategy

| strategy | λ | abstain | fraction abstained | net-balanced regret | worst-network regret | pooled regret | top-2 hit |
|---|---|---|---|---|---|---|---|
| best_fixed_xgboost | nan | none | 0.000 | 0.0815 | 0.4300 | 0.1039 | 0.956 |
| global_CV | nan | none | 0.000 | 0.1466 | 0.4300 | 0.1525 | 0.984 |
| per_network_CV | nan | none | 0.000 | 0.0480 | 0.2347 | 0.0435 | 0.970 |
| gap_rule | nan | none | 0.000 | 0.1017 | 0.2742 | 0.1064 | 0.958 |
| oracle | nan | none | 0.000 | 0.0000 | 0.0000 | 0.0000 | 1.000 |
| proposed_l0 | nan | none | 0.000 | 0.0738 | 0.3629 | 0.0958 | 0.956 |
| proposed_l0.5 | nan | none | 0.000 | 0.0731 | 0.3629 | 0.0952 | 0.958 |
| proposed_l1 | nan | none | 0.000 | 0.0741 | 0.3629 | 0.0956 | 0.958 |
| proposed_l0_abstain | 0.0 | ambiguous10% | 0.644 | 0.0262 | 0.3804 | 0.0873 | 0.957 |
| proposed_l0.5_abstain | 0.5 | ambiguous10% | 0.640 | 0.0277 | 0.1385 | 0.0312 | 0.952 |
| proposed_l1_abstain | 1.0 | ambiguous10% | 0.601 | 0.0350 | 0.1385 | 0.0369 | 0.949 |
| random | nan | none | 0.000 | 0.2620 | 0.6699 | 0.2812 | 0.665 |

### 4.2 Abstention coverage-risk curve (ambiguity-threshold sweep)

| λ | threshold | fraction abstained | n released | net-balanced regret (released) | worst-network regret (released) |
|---|---|---|---|---|---|
| 0.5 | 0.02 | 0.009 | 1427.0 | 0.0736 | 0.3629 |
| 0.5 | 0.05 | 0.403 | 859.0 | 0.0488 | 0.3629 |
| 0.5 | 0.10 | 0.640 | 519.0 | 0.0277 | 0.1385 |
| 0.5 | 0.15 | 0.744 | 368.0 | 0.0178 | 0.0748 |
| 0.5 | 0.20 | 0.851 | 215.0 | 0.0150 | 0.1033 |
| 0.5 | 0.30 | 0.978 | 32.0 | 0.0021 | 0.0157 |
| 0.5 | 0.50 | 0.995 | 7.0 | 0.0000 | 0.0000 |
| 0.5 | -1.00 | 0.901 | 143.0 | 0.0284 | 0.1009 |

### 4.3 Network-bootstrap 95% CI — regret differences (2,000 draws)

| pair | mean diff | 95% CI | frac draws < 0 |
|---|---|---|---|
| proposed_vs_best_fixed | -0.0084 | [-0.0150, -0.0000] | 0.976 |
| proposed_vs_global_CV | -0.0733 | [-0.0995, -0.0480] | 1.000 |
| proposed_abstain_vs_best_fixed | -0.0540 | [-0.0741, -0.0318] | 1.000 |
| proposed_abstain_vs_global_CV | -0.1189 | [-0.1449, -0.0927] | 1.000 |

### 4.4 Calibration detail (Part 2)

`axis` mapping (outer ~ xgboost fitting-period stress, dev + first-panel direct rows);
`t05` mapping (outer ~ family-specific t05 stress, 143 first-panel rows, 10 networks).

| family | mapping | n fit rows | intercept | slope | residual sd (°C) |
|---|---|---|---|---|---|
| seasonal_boundary_ridge | axis | 1313 | 0.5121 | 1.0006 | 0.6787 |
| seasonal_boundary_ridge | t05 | 143 | 0.1470 | 0.8929 | 0.3162 |
| donor_blup_ridge | axis | 1313 | 0.1046 | 0.9561 | 0.3727 |
| donor_blup_ridge | t05 | 143 | 0.0465 | 0.9581 | 0.2525 |
| xgboost | axis | 1313 | 0.0300 | 0.9692 | 0.2899 |

Fallback widening σ_fb (unit stress ~ network mean, direct rows): 0.7603 °C (n = 1313).

## 5. Headline

Part 1: at the 20% budget the empirical curve captures 0.336 of total loss vs simple 0.513 and surface 0.502 (bootstrap Δ empirical−simple -0.1755 °C-loss-pp, CI [-0.2008, -0.1431]; Δ empirical−surface -0.1647, CI [-0.1916, -0.1333]). Captured loss rises with budget for all policies; random 0.203; oracle 0.528.

Part 2: proposed risk-based selection (λ=0) reaches network-balanced regret 0.074 °C vs best-fixed 0.081, global blocked-CV 0.147, per-network avg-CV 0.048, gap rule 0.102, random 0.262, oracle 0.000. Bootstrap Δ proposed−best-fixed -0.0084 (CI [-0.0150, -0.0000]), Δ proposed−global-CV -0.0733 (CI [-0.0995, -0.0480]).

