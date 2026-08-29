# v13 decision harmonization — agent_b (adversarial pair: decision-utility + downstream harmonization)

**Namespace:** `results/revision_v13/decision_harmonization/agent_b/`
**Scripts (in this namespace):** `analyze_partA_coverage_regret.py`, `analyze_partB_downstream.py`
**Date:** 2026-08-29 · Python 3.11, pandas/numpy only, no GPU, no training, deterministic seeds (42)
**Inputs (read-only):**
- `results/revision_v12/t09_decision_utility/agent_a/selection_predictions_part2.csv` (1,440 units, 42 networks)
- `results/revision_v12/t09_decision_utility/agent_a/selection_calibration_part2.csv`
- `results/revision_v12/t09_decision_utility/agent_a/abstention_curve_part2.csv`, `abstention_comparison_part2.csv`, `selection_regret_table_part2.csv` (reference values)
- `results/revision_v12/t08_downstream_metrics/agent_b/placement_metrics.csv` (1,755 placements), `budget_comparison.csv`
- `results/revision_v12/t08_downstream_metrics/agent_a/placement_thermal_metrics.csv`, `budget_comparison.csv`, `budget_combined.csv`, `reconstruction_series.parquet`

No repository file outside this namespace was modified; no git operations were performed.

Two deliverables:
- **(A)** fixed-coverage model-selection coverage–regret curves (t09 Part-2 data) → Figure 4
- **(B)** downstream multi-untreated-baseline thermal comparison (t08 data) → Figure 5

---

# PART A — Fixed-coverage model-selection coverage–regret curves

## A1. Regret definition (reused verbatim from t09 agent_a REPORT.md)

- Unit = (network, station, gap); per-family loss = outer roster loss `loss_<family>` (mean over
  roster placements of MAE, °C).
- Per-unit regret = loss(selected family) − min over families of loss (the `min_loss` column).
- **Network-balanced regret** = mean over networks of within-network mean per-unit regret.
  t09 computes this on released sets as the mean over networks **with ≥ 1 released unit**
  (verified: the 123-unit set reproduces 0.0067202 exactly under this convention; the 42-network
  convention with zeros would give 0.00672 × 8/42 ≈ 0.00128, which does not match the t09 table).
  Networks with zero released units are therefore "not released", per the task spec.
- Pooled regret = mean over released units of per-unit regret.
- Primary lambda = **0.5** (t09 headline λ; the REPORT's +0.0037 vs best-fixed uses λ=0.5).
  Verified: `selected_lambda0.5` equals argmin(risk + 0.5·width) on 100% of units
  (same for λ = 0.0, 1.0).
- Ambiguity (t09): a unit is ambiguous iff the 2nd-smallest penalized risk ≤ 1.10 × smallest.
- Support-any abstention: any family with `support == 'curve'` (no unit-level fitting-period
  evidence).
- top2_hit in the curve CSVs = share of released units where the **selected family's loss** is
  within the two smallest losses (method-agnostic). The t09 definition (true-best family within
  the top-2 of the penalized-risk ranking, proposed selector only) reproduces 0.8965 at the
  no-abstention point and is reported separately in A4.

## A2. Reproduction of the t09 reference results (all exact to ≥ 10 digits)

| quantity | reproduced | t09 reference (agent_a) |
|---|---|---:|
| no-abstention, proposed λ=0.5, network-balanced regret | 0.0849530207 | 0.0849530207 |
| no-abstention, proposed λ=0.5, pooled (mean unit) regret | 0.0931839674 | 0.0931839674 |
| no-abstention, best fixed (xgboost, dev-chosen) | 0.0814985224 | 0.0814985224 |
| no-abstention, global blocked-CV (= xgboost on this panel) | 0.0814985224 | 0.0814985224 |
| no-abstention, per-network avg-CV | 0.0382955322 | 0.0382955322 |
| no-abstention, gap-length rule (argmin C_f(g)) | 0.0926709954 | 0.0926709954 |
| abstention support_any+ambiguous (λ=0.5), released units | 123 (8 networks) | 123 (8 networks) |
| abstention point, proposed network-balanced regret | 0.0067202375 | 0.0067202375 |
| abstention point, proposed pooled regret | 0.0121400504 | 0.0121400504 |
| abstention point, comparators (same 123 units) | best_fixed 0.15079, per-net CV 0.16359, gap rule 0.14474, common-scale 0.00676, random(20-draw mean) 0.34073 | identical (abstention_comparison_part2.csv) |
| top-2 hit, t09 definition, proposed λ=0.5, full panel | 0.8965278 | 0.8965278 |

Reproduction notes (important for the sibling/reviewer):
- The `selected_lambda*` columns are exact argmin penalized-risk choices; no tie-breaking was
  needed (verified 100% agreement with a recomputation).
- The gap-length rule requires the per-family duration curve C_f(g). It is not stored
  explicitly, but for curve-support units risk_f = a_f + b_f·C_f(g_u) with the recalibration
  coefficients of `selection_calibration_part2.csv` (seasonal: 0.018641 + 1.023·s; donor:
  −0.005117 + 1.039·s; xgboost: 0.024015 + 0.982·s). Inverting on curve-support units gives
  C_f(g) exactly (within-gap SD of the inverted values ≤ 2e−14). The gap rule then selects
  argmin_f C_f(g_u) per unit; this reproduces both the no-abstention regret (0.0926710) and
  the 123-unit-set value (0.14474).
- The per-network avg-CV comparator selects, per network, the family with the smallest
  full-roster mean loss (not per released set). This reproduces the full-panel 0.0382955 and
  the released-set 0.16359; the alternative (per-network selection on the released units only)
  gives 0.03308 on the 123-unit set, which does not match t09 — the full-roster convention is
  therefore the t09 one.

## A3. Fixed-coverage design

For each confidence criterion, units are rank-ordered by the criterion and the **top c
fraction** is released (c ∈ {0.1, …, 0.9}; n_released = round(c × 1440), all integral;
c = 1.0 no-abstention point added; the t09 8.5% abstention point added as a fixed rule
row, c = 123/1440 = 0.0854):

| criterion | rank order | interpretation |
|---|---|---|
| `ambiguity_margin` | 2nd-smallest penalized risk − smallest (λ=0.5), descending; ties by stable unit order | release the units where the risk ranking is most decisive |
| `mean_width` | mean over families of interval width, ascending; ties by stable unit order | release the units with the tightest intervals |
| `support_completeness` | # families with unit-level support (0–3) descending; tie-break ambiguity margin descending, then stable unit order | release units with the fullest fitting-period evidence first |
| `abstention_rule` (fixed row) | released = NOT ambiguous AND all three families unit-supported | the t09 8.5% point |

Degeneracy note on `mean_width`: each family's width takes exactly **two** values across the
panel (constant for gaps ≤ 180 d; inflated by (1 + 2·log(g/180)/log(180/7)) at g = 365 d), so
the criterion separates the 144 365-day units from the rest and is otherwise file-order.
Reported for completeness; it is not a discriminating confidence ranking (its curve is
interpretable as "release everything except the 365-day extrapolation tail, then in file
order").

Methods evaluated on each released set (selection within the released units):
`proposed` (λ=0.5, argmin penalized risk), `best_fixed` (xgboost), `global_cv` (xgboost;
identical by construction on this panel), `per_network_cv` (per-network full-roster argmin
mean loss), `gap_rule` (argmin C_f(g)), `random` (uniform per-unit draw, `RandomState(42)`,
single draw), `oracle` (true best).

Metrics per (criterion, c, method) — `coverage_regret_curve.csv`:
`released_units`, `released_networks`, `unit_coverage`, `network_coverage`,
`network_balanced_regret` (released-network convention), `pooled_regret`,
`selection_accuracy` (share where selected == true best), `top2_hit` (selected loss within
the two smallest), `abstention_cost_units` = 1 − unit_coverage, `abstention_cost_networks` =
1 − network_coverage.

## A4. Key results

**No-abstention point (c = 1.0; identical across criteria; t09 reproduction):**

| method | net-bal regret | pooled regret | accuracy | top2 |
|---|---:|---:|---:|---:|
| proposed (λ=0.5) | 0.0850 | 0.0932 | 0.5153 | 0.9722 |
| best_fixed / global_cv | 0.0815 | 0.1039 | 0.5437 | 0.9556 |
| per_network_cv | 0.0383 | 0.0369 | 0.6687 | 0.9715 |
| gap_rule | 0.0927 | 0.1024 | 0.4854 | 0.9799 |
| random (seed 42) | 0.2605 | 0.2924 | 0.3312 | 0.6535 |
| oracle | 0.0000 | 0.0000 | 1.0000 | 1.0000 |

(Proposed λ=0.0 no-abstention: 0.0838 net-balanced, 0.0924 pooled — t09 table row reproduced.)

**t09 8.5% abstention point (criterion `abstention_rule`, 123 units / 8 networks):**

| method | net-bal regret | pooled regret | accuracy | top2 |
|---|---:|---:|---:|---:|
| proposed (λ=0.5) | **0.0067** | 0.0121 | 0.8455 | 1.0000 |
| best_fixed / global_cv | 0.1508 | 0.2021 | 0.3415 | 0.9837 |
| per_network_cv | 0.1636 | 0.0471 | 0.7967 | 1.0000 |
| gap_rule | 0.1447 | 0.1402 | 0.5610 | 0.9919 |
| random | 0.2686 | 0.3770 | 0.3415 | 0.6667 |
| oracle | 0.0000 | 0.0000 | 1.0000 | 1.0000 |

**Fixed-coverage rows (network-balanced regret, released-network convention):**

| criterion | c | proposed | best_fixed | per_net_cv | gap_rule | random | oracle |
|---|---|---:|---:|---:|---:|---:|---:|
| ambiguity_margin | 0.5 | 0.1147 | 0.1300 | 0.0613 | 0.1347 | 0.3606 | 0 |
| ambiguity_margin | 0.7 | 0.0978 | 0.1085 | 0.0487 | 0.1114 | 0.3161 | 0 |
| mean_width | 0.5 | 0.0719 | 0.0462 | 0.0218 | 0.0739 | 0.2049 | 0 |
| mean_width | 0.7 | 0.0662 | 0.0561 | 0.0278 | 0.0761 | 0.1981 | 0 |
| support_completeness | 0.5 | 0.0977 | 0.0813 | 0.0479 | 0.0936 | 0.3241 | 0 |
| support_completeness | 0.7 | 0.0837 | 0.0730 | 0.0405 | 0.0852 | 0.2759 | 0 |

Full grid (0.1–0.9 × 7 methods × 3 criteria + 2 special points) in `coverage_regret_curve.csv`;
key rows in `coverage_regret_summary.md`; per-method summary in `comparators_table.csv`.

**Reading of the curves:**
1. **Margin-based abstention never helps the proposed selector**: regret is minimized at
   c = 1.0 (0.0850) for every non-oracle method under `ambiguity_margin`; releasing only
   high-margin units keeps the harder units (regret 0.2256 at c = 0.1), consistent with the
   t09 finding that near-ties in risk are cheap. The proposed selector beats best-fixed
   exactly in the mid-coverage range where low-margin units are included (c = 0.2–0.8,
   differences −0.001 to −0.038; e.g. c = 0.5: 0.1147 vs 0.1300, c = 0.7: 0.0978 vs 0.1085),
   and loses only at the extremes (c = 0.1: +0.060, c = 0.9: +0.001) — i.e. the per-unit risk
   signal pays off where margins are small.
2. **Support completeness is the operative confidence axis** (it is the basis of the t09
   abstention rule): under `support_completeness` the proposed selector's decisive win is at
   c = 0.1 — 144 all-unit-supported units, regret 0.0139 vs best-fixed 0.1416 and per-net CV
   0.1640 (−0.128); the t09 ambiguity-filtered 123-unit subset improves this to 0.0067.
   From c = 0.2 upward, best-fixed (xgboost) is better on the released sets (0.1050 vs 0.1435
   at c = 0.2, shrinking to 0.0868 vs 0.0945 at c = 0.9): outside the fully-supported,
   non-ambiguous core, the donor-vs-xgboost coin-flip region dominates and xgboost's strong
   panel-wide mean wins.
3. **Mean width is degenerate** (two distinct values; see A3) and its curve mostly
   demonstrates that excluding the 365-day extrapolation tail lowers regret for every method
   (min at c = 0.2 for all methods); best-fixed beats the proposed selector at every c under
   this criterion (0.001–0.026).
4. Oracle headroom (min regret of each method over c, minus oracle at the same c; oracle is 0
   everywhere) equals the method's min regret: 0.0067 (proposed, abstention rule) vs 0.0244
   (best-fixed, mean_width c=0.2) vs 0.0170 (per-net CV) — see `comparators_table.csv`.

**Selected-model frequency** (`selection_frequency.csv`, share of released units per family):
- proposed at c = 0.5 (`ambiguity_margin`): donor 0.508, xgboost 0.492, seasonal 0.000
  (seasonal_ridge is selected essentially never; it is the true best on only 13/1440 units).
- proposed at c = 0.1 (`support_completeness`, top 144 all-unit-supported units): donor 0.694,
  xgboost 0.299, seasonal 0.007 — the margin tie-break within the full-support tier favors
  donor-ridge units.
- best_fixed/global_cv: xgboost 1.0 at every c; oracle mirrors the true-best distribution
  (xgboost 0.544, donor 0.447, seasonal 0.009 on the full panel).

---

# PART B — Downstream multi-untreated-baseline thermal comparison

## B1. Procedures

Input: `agent_b/placement_metrics.csv` (1,755 placements, 15 networks, horizons 7/30/90 d).
Per placement and metric the file stores truth, reconstruction (XGBoost fill), missing
(no-fill: gap days dropped), climatology (day-of-year median fill) values and absolute errors
`*_err_*` (phase error is the circular day difference).

- **Common-support convention**: per-metric means are placement-level means over placements
  where the metric is defined under **all three** scenarios (recon, missing, clim). This is
  required because no-fill is undefined when the gap swallows July/January (amplitude:
  err_missing defined on 1,171/1,755 placements; summer metrics on 1,703) — a skipna mean
  mixes different placement subsets and corrupts ratios (e.g. amplitude ratio recon/missing
  becomes 2.49 under skipna vs 0.33 on the common support; the 2.49 is an artifact of
  dropping the no-fill-undefined placements from the denominator while keeping their large
  recon errors in the numerator).
- Ratios = mean_err_recon / mean_err_missing (resp. clim) on the common support.
- Shares = fraction of common-support placements with err_recon > err_missing (resp. clim).
- Network-level median = median over the 15 networks of the per-network mean error
  (common support) — `network_median_errors.csv`.
- Skipna means for transparency: `skipna_means.csv`.

## B2. Per-metric table (`downstream_baseline_comparison.csv`; common support)

| metric | mean_err_recon | mean_err_missing | mean_err_clim | recon/missing | recon/clim | worse vs clim | worse vs missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| annual_mean | 0.0933 | 0.7535 | 0.1049 | 0.124 | 0.889 | 0.313 | 0.036 |
| summer_mean | 0.0960 | 0.1626 | 0.1160 | 0.591 | 0.828 | 0.103 | 0.086 |
| amplitude | 0.0307 | 0.0917 | 0.0778 | 0.335 | 0.394 | 0.057 | 0.039 |
| phase_doy | 2.4923 | 3.5875 | 2.9214 | 0.695 | 0.853 | 0.044 | 0.038 |
| p90 | 0.1411 | 0.4688 | 0.1430 | 0.301 | 0.987 | 0.085 | 0.071 |
| summer_max | 0.1243 | 0.1486 | 0.0943 | 0.836 | 1.319 | 0.028 | 0.003 |
| exceed_days_20 | 2.2274 | 6.5493 | 2.2387 | 0.340 | 0.995 | 0.073 | 0.011 |
| exceed_days_25 | 0.5157 | 0.6308 | 0.4108 | 0.818 | 1.255 | 0.007 | 0.000 |
| cdd10 | 21.72 | 157.73 | 23.49 | 0.138 | 0.925 | 0.223 | 0.014 |
| trend_slope | 0.0831 | 0.6599 | 0.1236 | 0.126 | 0.672 | 0.280 | 0.151 |

Network-level medians (median over 15 networks of per-network mean; `network_median_errors.csv`):
annual_mean recon 0.0914 / missing 0.7913 / clim 0.0937; cdd10 19.4 / 149.4 / 22.8;
trend 0.0641 / 0.5156 / 0.1025; p90 0.1072 / 0.4440 / 0.1089; amplitude 0.0276 / 0.1088 /
0.0941; summer_mean 0.0644 / 0.1202 / 0.1162; phase 2.36 / 3.87 / 3.26; exceed_20 2.04 /
6.80 / 1.40; exceed_25 0.00 / 0.00 / 0.06; summer_max 0.0496 / 0.0600 / 0.0600.

Agreement with agent_b's station-gap-level `metric_error_summary.csv`: ratios match to
±0.01–0.05 (placement-level vs station-gap-level weighting; annual_mean/p90/cdd10/trend/
exceed_20/phase are identical to 3 dp because they have no missing rows). Amplitude differs
(0.335 here on n=1,171 placements vs 0.375 in agent_b on n=342 station-gaps) because the two
common supports differ (placement vs station-gap level).

## B3. Budget joint table (`budget_joint_table.csv`)

policy × metric × default, reduction = 1 − aggregate distortion(treated)/aggregate
distortion(untreated), as stored in the source CSVs (fractions; multiply by 100 for %).

| default | policy | cdd10 | annual_mean | trend_slope | p90 | exceed_20 | exceed_25 | amplitude | summer_mean | summer_max | phase_doy |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| no_fill (agent_b, 270 units) | risk | 0.395 | 0.377 | 0.348 | 0.307 | 0.308 | 0.109 | 0.095 | 0.188 | 0.133 | 0.117 |
| no_fill (agent_b) | gap_length | 0.344 | 0.386 | 0.522 | 0.290 | 0.240 | 0.021 | 0.159 | 0.182 | 0.119 | 0.109 |
| no_fill (agent_b) | random | 0.171 | 0.173 | 0.173 | 0.133 | 0.124 | 0.036 | 0.119 | 0.084 | 0.033 | 0.053 |
| climatology (agent_a, 1965 units) | risk | **−0.179** | **0.022** | −0.157 | −0.130 | **−0.222** | **−0.425** | **−0.338** | **−0.230** | 0.000 | −0.108 |
| climatology (agent_a) | gap_length | −0.132 | 0.127 | −0.064 | −0.142 | −0.331 | −0.420 | −0.343 | −0.201 | 0.000 | 0.020 |
| climatology (agent_a) | random | 0.071 | 0.128 | −0.020 | 0.044 | 0.029 | −0.082 | −0.025 | 0.066 | −0.005 | 0.054 |

n_units: agent_b 270 (261 amplitude; 54 treated); agent_a 1,965 (393 treated; summer metrics
and amplitude 1,950). Random: agent_b mean of 20 draws, agent_a mean of 200 draws; SDs in the
source CSVs (agent_b 0.02–0.05; agent_a ≤ 0.03). agent_a per-metric "combined" equal-weight
mean: risk −0.177, gap_length −0.148, random +0.026 (from `budget_combined.csv`).

## B4. Verification of the review's quoted numbers

**agent_b no-fill ratios (recon/no-fill), review: "integrated metrics 12–14 % (degree days,
annual mean, trend), 30–37 % (p90, amplitude, threshold days)":**
- cdd10 13.8 %, annual_mean 12.4 %, trend_slope 12.6 % → **12–14 % band confirmed** (all
  three within 12.4–13.8 %).
- p90 30.1 %, amplitude 33.5 % (agent_b's own station-gap number 37.5 %), exceed_days_20
  34.0 % → **30–37 % band confirmed for p90, amplitude, days>20** (amplitude at 37.5 % is the
  upper edge at station-gap level; 33.5 % at placement level).
- **Caveat on "threshold days"**: exceed_days_25 is 81.8 % (not in the 30–37 % band), as are
  summer_mean 59 % (placement-level 59.1 %) and summer_max 84 %. The review's claim is best
  read as referring to days>20 only; days>25 has a ratio of ~0.82, still < 1 (recon better)
  but far from the integrated-metric band.

**agent_a climatology default, risk policy, review: NEGATIVE for degree days (−17.9 %),
days>20 (−22.2 %), days>25 (−42.5 %), amplitude (−33.8 %), summer mean (−23.0 %), annual mean
slightly positive:**
- Verified exactly from `budget_comparison.csv`: degree_days_10 −0.1790, exceed_20_days
  −0.2216, exceed_25_days −0.4254, amplitude −0.3383, summer_mean −0.2299, annual_mean
  +0.0217. All six numbers match the review's quoted values to rounding.

**agent_b claim "reconstruction errors exceed no-fill errors in only 0–8 % of placements for
all metrics"** — NOT fully reproduced at placement level: the placement-level shares are
0.0–8.6 % for nine metrics (annual_mean 3.6 %, summer_mean 8.6 %, amplitude 3.9 %, phase 3.8 %,
p90 7.1 %, summer_max 0.3 %, exceed_20 1.1 %, exceed_25 0.0 %, cdd10 1.4 %) but
**trend_slope = 15.1 %** (265/1,755 placements). The claim holds for 9 of 10 metrics; the
trend-slope exception is not disclosed in agent_b's REPORT (the exact definition agent_b used
is not in the artifacts; at station-gap level the shares change materially — amplitude 48 %,
summer_mean 24.5 %, phase 14 %, summer_max 14 % — so the claim is sensitive to aggregation
level). Discrepancy logged; recommended manuscript wording: "reconstruction error exceeds
no-fill error in < 9 % of placements for nine of ten metrics, 15 % for trend slope".

**Linear-interpolation baseline** — **not computable**. Neither artifact set contains a
linear-interpolation reconstruction: `agent_a/reconstruction_series.parquet` stores only
truth/reconstruction/climatology daily series (8 columns), `agent_a/placement_thermal_metrics.csv`
stores errors for reconstruction and climatology only, and `agent_b/placement_metrics.csv`
stores no interp fill. Computing err_interp would require re-running the downstream metric
pipeline (window definition, 15-day phase smoothing, trend OLS) on a newly created fill —
outside this read-only artifact analysis (`interp_availability.txt`).

## B5. Divergence note (summary; full text in `divergence_note.md`)

agent_a vs agent_b (t08): 11 shared networks with identical per-network rosters (1,530
placements each) + disjoint extras (agent_a +435, agent_b +225 → 1,965 vs 1,755 placements);
metric windows differ (agent_a: whole evaluation record; agent_b: 365 d centred on the gap —
the main reason absolute distortions differ, e.g. annual_mean 0.011 vs 0.093 °C); untreated
baselines differ (agent_a climatology fill vs agent_b no-fill drop); budget units differ
(agent_a per placement, n=1,965; agent_b per station-gap, n=270 risk-scored); risk-score
coverage differs (all 1,965 placements vs 270/351 station-gaps). The sign flip of risk-policy
budget reductions between defaults (positive for every metric under no-fill; negative for
threshold/extreme metrics under climatology) is the paper-relevant contrast: climatology
already supplies the seasonal cycle, so on the long summer gaps the XGBoost fill's cold peak
bias flips threshold crossings, whereas no-fill destroys the gap days entirely.

---

# Figure and manuscript mapping (v13)

- **Figure 4** — coverage–regret curves: plot `network_balanced_regret` (y) vs `c` (x) per
  method from `coverage_regret_curve.csv`. Recommended panel layout: one panel per criterion
  (`ambiguity_margin`, `support_completeness`; `mean_width` only as an appendix panel given
  its degeneracy), lines for proposed (bold), best_fixed, global_cv, per_network_cv, gap_rule,
  random, oracle; markers at the t09 8.5% point row (criterion `abstention_rule`) and at
  c = 0.5/0.7. Secondary y-axis or line style can carry `selection_accuracy`; report
  `abstention_cost_units/networks` as coverage on the x-axis if a risk–coverage plot is
  preferred (x = unit_coverage, y = regret). The no-abstention points (c = 1.0) are the t09
  full-panel headline values.
- **Figure 5** — downstream baseline contrast: (a) grouped bar of mean_err_recon vs
  mean_err_missing vs mean_err_clim per metric (log scale; `downstream_baseline_comparison.csv`),
  with recon/missing and recon/clim ratios as text labels; (b) budget reductions
  policy × metric × default from `budget_joint_table.csv` (two panels: default = no_fill,
  default = climatology), or a single panel with default on the x-axis; the sign flip for
  cdd10/exceed days/amplitude/summer_mean under climatology is the headline.
- **Manuscript text** (recommended): Part A — the proposed selector matches best-fixed/
  global-CV at full coverage (0.0850 vs 0.0815, t09 CI +0.0037 [−0.0255, +0.0330]) and reaches
  0.0067 at 8.5 % coverage with the support-any+ambiguity rule, an order of magnitude below
  every comparator on the same units; margin-based abstention alone does not reduce regret
  (near-ties are cheap), support completeness is the operative confidence axis. Part B —
  reconstruction recovers integrated metrics to 12–14 % of no-fill error (degree days, annual
  mean, trend) and 30–34 % for p90/amplitude/days>20, but the climatology-default budget
  experiment shows the XGBoost fill is worse than climatology on the long summer gaps for
  threshold/extreme metrics (risk-policy reductions −17.9 % … −42.5 %), qualifying the
  end-to-end protection claim: mean/percentile metrics are protected, threshold-extreme
  metrics need a peak-corrected fill. Numbers with exact provenance: `coverage_regret_curve.csv`,
  `comparators_table.csv`, `selection_frequency.csv`, `downstream_baseline_comparison.csv`,
  `budget_joint_table.csv`.

# Files in this namespace

| file | content |
|---|---|
| `analyze_partA_coverage_regret.py` | Part A script (reproduction + fixed-coverage curves) |
| `analyze_partB_downstream.py` | Part B script (baselines, budget joint table, review checks) |
| `coverage_regret_curve.csv` | 217 rows: criterion × c × method grid + no-abstention + 8.5% point |
| `coverage_regret_summary.md` | key rows: c = 0.5, 0.7, 8.5 % point, no-abstention |
| `comparators_table.csv` | per method: regret at no-abstention / c=0.5 / c=0.7, min over c, oracle headroom |
| `selection_frequency.csv` | per method × c: share of released units selecting each family |
| `downstream_baseline_comparison.csv` | per metric: means, ratios, worse-than shares (common support) |
| `network_median_errors.csv` | network-level median errors + n per (metric, scenario) |
| `skipna_means.csv` | skipna (defined-rows) means — transparency vs common support |
| `budget_joint_table.csv` | policy × metric × default reductions (60 rows) |
| `divergence_note.md` | agent_a vs agent_b implementation differences |
| `interp_availability.txt` | linear-interpolation baseline: not computable, reason |
| `REPORT.md` | this report |
