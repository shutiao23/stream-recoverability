# Revision v13 — Decision-utility harmonization (agent_a of the adversarial pair)

**Namespace:** `results/revision_v13/decision_harmonization/agent_a/`
**Scripts (this namespace):** `partA_coverage_regret.py`, `partB_downstream.py`
**Date:** 2026-08-29 · Python 3 (pandas/numpy/scipy), CPU only, runtime ≈ 1 min.
**Inputs (read-only):** `results/revision_v12/t09_decision_utility/agent_a/*`
(selection_predictions_part2.csv, selection_regret_table_part2.csv,
abstention_comparison_part2.csv), the t09 script's inputs
(`results/development_v11/reviewer_completion/*roster_losses.csv`,
`*empirical_fit_losses.csv`, `results/revision_v12/t05_model_matrix/agent_a/
source_fit_stress_families_1_3.csv`), and
`results/revision_v12/t08_downstream_metrics/agent_b/*` +
`agent_a/*`. Nothing outside this namespace was written or modified; no git
operations; no training; all randomness seeded (seed 42).

Deliverable A (Figure 4 data): fixed-coverage model-selection coverage–regret
curves from the t09 Part-2 panel. Deliverable B (Figure 5 data): downstream
multi-untreated-baseline thermal comparison from the t08 runs, with the joint
policy×metric×default budget table and a review-claim verification.

---

# PART A — Fixed-coverage model-selection coverage–regret

## A.1 Panel and definitions (identical to t09 where the two overlap)

- Panel: 1,440 first-panel units (network, station, gap) across 42 networks;
  families `seasonal_ridge` (seasonal_boundary_ridge), `donor_ridge`
  (donor_blup_ridge), `xgboost` (xgboost_b_d).
- Per-unit loss L_f = mean over the unit's roster placements of MAE
  (`confirmation_model_roster_losses.csv`); reproduced exactly from
  `selection_predictions_part2.csv` `loss_*` columns (max abs diff
  8.9e-16).
- Proposed selector: argmin_f (risk_f + λ·width_f), λ = 0.5 (the t09
  reference value), taken from `selected_lambda0.5`.
- **Per-unit regret** = L(selected) − min_f L_f.
- **Network-balanced regret** = mean over the networks that have ≥ 1 released
  unit of the within-network mean per-unit regret (networks with zero released
  units count as not released; reported separately: `released_networks`,
  `network_coverage`).
- **Pooled regret** = mean per-unit regret over all released units.
- **Selection accuracy** = share of released units where the selected family
  equals the true best family (by loss).
- **Top-2 hit** = share of released units where the selected family is among
  the two lowest-loss families (random baseline 2/3). A second column
  `top2_hit_pen_t09` reproduces t09's published top-2 definition (true best
  contained in the selector's penalized-risk top 2; proposed method only).
- **Abstention cost** = 1 − coverage (units; networks).

## A.2 Reproduction of the t09 reference results (before any new analysis)

No-abstention, all 1,440 units (vs `selection_regret_table_part2.csv`):

| selector | net-balanced regret (recomputed) | t09 value | pooled regret | match |
|---|---|---|---|---|
| proposed λ=0.5 | 0.084953 | 0.084953 | 0.093184 | exact |
| best fixed (dev; xgboost) | 0.081499 | 0.081499 | 0.103947 | exact |
| global blocked-CV (xgboost) | 0.081499 | 0.081499 | 0.103947 | exact |
| per-network avg-CV | 0.038296 | 0.038296 | 0.036918 | exact |
| gap-length rule | 0.092671 | 0.092671 | 0.102384 | exact |
| random (mean over 20 draws, seed 42) | 0.262837 | 0.262837 | 0.278586 | exact |
| oracle | 0.000000 | 0.000000 | 0.000000 | exact |

The task brief quotes "reference regret 0.084 vs best-fixed 0.081" — the
0.084 value is the proposed λ=0.5 net-balanced regret, reproduced exactly.

Abstention point (ambiguity δ = 0.10 AND all-family unit-level support,
λ = 0.5; released 123 units / 8 networks = 8.54 % of units; vs
`abstention_comparison_part2.csv`):

| method | net-balanced regret (recomputed) | t09 value |
|---|---|---|
| proposed | 0.006720 | 0.006720 |
| best fixed / global CV | 0.150792 | 0.150792 |
| per-network avg-CV | 0.163591 | 0.163591 |
| gap-length rule | 0.144745 | 0.144745 |
| random (20-draw mean) | 0.350862 (net-balanced) / **0.340730** (pooled) | 0.340730 (t09 column is the pooled mean over draws; see discrepancy log) |
| oracle | 0.000000 | — |

Both reference results reproduce to 6 decimals. The 8.5% point therefore
carries forward unchanged: **regret 0.0067 at 8.54% unit coverage / 19.0%
network coverage (8 of 42)**, selection accuracy 0.8455, top-2 hit 0.9512
(t09 penalized definition; loss-based 1.0000).

## A.3 New analysis: fixed-coverage curves

**Released sets.** Units are rank-ordered by a confidence criterion and the
top c fraction is released, k = round(c·1,440), c ∈ {0.1,…,0.9} plus c = 1.0
(no abstention) and the current 8.5% point (123 units). Three criteria:

- **(a) ambiguity margin** = r₂ − r₁, the gap between the two smallest
  penalized risks (λ = 0.5); release descending margin (most confident
  first), ties broken by (network, station, gap).
- **(b) mean width** = mean over families of width_f; release ascending
  (smallest interval first), same tie-break.
- **(c) support completeness** = number of families with `unit`-level
  fitting-period stress (0–3); all-unit-support first, then margin descending,
  then the same tie-break.

**Methods** evaluated on every released set: proposed (λ = 0.5), best-fixed
(xgboost), global CV (xgboost), per-network avg-CV (reconstructed exactly as
in the t09 script: per network, argmin over families of the mean leave-one-
unit-out prediction on the network's own roster units), gap-length rule
(argmin of the reconstructed pooled per-family duration curve at the unit's
gap — curves rebuilt from the same stress data and algorithm as t09),
random (t09 convention: mean over 20 seeded draws, seed 42), oracle (true
best). Per-unit selections of every comparator were recomputed from the raw
roster/stress artifacts, so any released set can be scored.

**Headline findings**

1. **The fixed-coverage curves do NOT reproduce the t09 abstention headline.**
   The 0.0067 result is specific to the combined support-any + ambiguity rule
   at 8.5% coverage. For every fixed top-c release with c ≥ 0.1 and every
   criterion, the proposed selector's network-balanced regret is ≥ 0.0139 and
   rises to ≈ 0.07–0.19 for c ≥ 0.3. Figure 4 must either plot the abstention
   rule's operating point separately or use the rule-based curve; a naive
   "release the top-c most confident units" reading does not reproduce the
   abstention gain.
2. **Support completeness at c = 0.1 is the only fixed-coverage regime where
   the proposed selector wins** (0.0139 vs best-fixed 0.1416, per-network CV
   0.1636, gap rule 0.1207, random 0.3759). That released set (144 units)
   is the 123-unit abstention set plus 21 of the all-unit-support units that
   the ambiguity rule would abstain; the ambiguity filter alone is worth half
   the remaining regret (0.0139 → 0.0067 at 123 units).
3. **By mean width, the per-network CV comparator beats the proposed selector
   at every c** (e.g., c = 0.1: 0.0260 vs 0.0522; c = 0.5: 0.0218 vs 0.0719),
   and best-fixed xgboost beats it for c = 0.1–0.2 — the lowest-width units
   are easy for any method that picks the dev-best family. By ambiguity
   margin, the proposed selector is worst at c = 0.1 (0.2256): large-margin
   units are not low-regret units.
4. **Coverage structure differs by criterion**: mean-width release covers only
   25 of 42 networks at c = 0.5 (networks with narrow intervals cluster; 17
   networks unreleased); margin and completeness release all 42 networks
   already at c = 0.5.
5. **Non-monotonicity**: support-completeness regret jumps at c = 0.2–0.3
   (0.1435, 0.1878 for proposed) — after the 221 all-unit-support units are
   exhausted, the added curve-support units are the hard ones. Reporting only
   c = 0.5/0.7 would hide the low-coverage regime where abstention logic
   actually bites.

**Key rows — c = 0.5 and c = 0.7 (per criterion; full grid in
`coverage_regret_curve.csv`)** (network-balanced regret; net_cov =
released networks / 42):

| method | c | criterion | released_units | released_networks | net_balanced_regret | pooled_regret | sel_acc | top2_hit |
|---|---|---|---|---|---|---|---|---|
| proposed | 0.5 | a_margin | 720 | 42 | 0.1147 | 0.1373 | 0.517 | 0.992 |
| proposed | 0.5 | b_width | 720 | 25 | 0.0719 | 0.0772 | 0.490 | 0.978 |
| proposed | 0.5 | c_support | 720 | 42 | 0.0977 | 0.0875 | 0.563 | 0.990 |
| proposed | 0.7 | a_margin | 1008 | 42 | 0.0978 | 0.1124 | 0.524 | 0.981 |
| proposed | 0.7 | b_width | 1008 | 35 | 0.0662 | 0.0737 | 0.490 | 0.976 |
| proposed | 0.7 | c_support | 1008 | 42 | 0.0837 | 0.0785 | 0.529 | 0.980 |
| best_fixed | 0.5 | b_width | 720 | 25 | 0.0462 | 0.0761 | 0.543 | 0.986 |
| best_fixed | 0.7 | b_width | 1008 | 35 | 0.0561 | 0.0709 | 0.564 | 0.971 |
| per_net_cv | 0.5 | b_width | 720 | 25 | 0.0218 | 0.0209 | 0.708 | 0.989 |
| per_net_cv | 0.7 | b_width | 1008 | 35 | 0.0278 | 0.0239 | 0.692 | 0.981 |
| gap_rule | 0.5 | b_width | 720 | 25 | 0.0739 | 0.0785 | 0.460 | 0.981 |
| random | 0.5 | b_width | 720 | 25 | 0.2023 | 0.2226 | 0.326 | 0.662 |
| oracle | any | any | — | — | 0.0000 | 0.0000 | 1.000 | 1.000 |

(Full rows for all methods × criteria × c, plus abstention costs and the
8.5%-point rows, are in `coverage_regret_curve.csv`; the same key rows are in
`coverage_regret_summary.md`.)

**Comparators table (`comparators_table.csv`)** — regret_no_abstention,
regret at c = 0.5 / 0.7 (mean over the three criteria), regret at the 8.5%
point, and the minimum fixed-coverage regret over c ∈ [0.1, 0.9] with its c
and criterion; oracle_headroom = min_regret_any_c (the oracle's regret is 0
on every set by construction):

| method | no-abstention | at 50% | at 70% | 8.5% point | min over c | min c | min criterion |
|---|---|---|---|---|---|---|---|
| proposed | 0.0850 | 0.0947 | 0.0826 | **0.0067** | 0.0139 | 0.1 | c_support |
| best_fixed | 0.0815 | 0.0858 | 0.0792 | 0.1508 | 0.0244 | 0.2 | b_width |
| global_cv | 0.0815 | 0.0858 | 0.0792 | 0.1508 | 0.0244 | 0.2 | b_width |
| per_net_cv | 0.0383 | 0.0437 | 0.0390 | 0.1636 | 0.0170 | 0.2 | b_width |
| gap_rule | 0.0927 | 0.1008 | 0.0909 | 0.1447 | 0.0553 | 0.2 | b_width |
| random | 0.2628 | 0.3044 | 0.2611 | 0.3509 | 0.1456 | 0.1 | b_width |
| oracle | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.1 | a_margin |

**Selection frequency (`selection_frequency.csv`)** — per (method, c,
criterion), the share of released units assigned to each family. Selected
no-abstention shares (c = 1.0): proposed donor 0.594 / xgboost 0.405 /
seasonal 0.001; best_fixed and global_cv: xgboost 1.0; per-network CV:
donor 0.523 / xgboost 0.477 (42 per-network choices); gap rule: donor 0.585 /
xgboost 0.415 (gap-dependent curve argmin); random ≈ 1/3 each. On the 8.5%
set: proposed donor 0.732 / xgboost 0.268; per-network CV donor 0.813 /
xgboost 0.187; gap rule donor 0.724 / xgboost 0.276.

## A.4 Part A caveats

- The per-network avg-CV comparator is in-sample by design (the strongest
  benchmark, as in t09); it is unbeatable by any out-of-sample method at
  high coverage.
- The 8.5% set is confined to the 8 t05 networks with all-family unit-level
  fitting-period evidence; the t09 caveats about that conditioning apply
  unchanged.
- Fixed-coverage release is per-unit ranking; it is NOT the t09 abstention
  rule, and the results differ sharply (finding 1). Figure 4 should show
  both: the rule-based 8.5% operating point and the top-c curves.
- Tie-breaks (network/station/gap lexicographic) are deterministic but
  arbitrary; they matter only within exact ties of margin/width/support.
- Random = mean over 20 seeded draws (t09 convention); a single seeded draw
  differs slightly (0.2940 vs 0.2628 no-abstention).

---

# PART B — Downstream multi-baseline thermal comparison

## B.1 Data

- `agent_b/placement_metrics.csv`: 1,755 placements, 15 networks, 117
  stations; per-metric truth/recon/missing(no-fill)/climatology values and
  absolute errors; metrics computed on a 365-day window centred on the gap
  (clipped at panel edges).
- `agent_b/metric_error_summary.csv`, `agent_b/budget_comparison.csv`:
  agent_b's own station-gap-level summaries and budget results (no-fill
  default).
- `agent_a/placement_thermal_metrics.csv`, `agent_a/budget_combined.csv`,
  `agent_a/reconstruction_series.parquet`: agent_a's per-placement distortions
  (whole-record window) and budget results (climatology default).
- Implementation differences (networks, 1,965 vs 1,755 placements, baselines,
  metric windows, budget semantics) are documented in `divergence_note.md`.

## B.2 Per-metric baseline comparison (`downstream_baseline_comparison.csv`)

Means on the 3-way common support (placements where the metric is defined
under recon, no-fill and climatology; n per metric in the CSV); ratios and
worse-shares on the same support. Network-level median = median over the 15
networks of the per-network mean error.

| metric | n | mean recon | mean no-fill | mean clim | recon/no-fill | recon/clim | share recon worse vs clim | share recon worse vs no-fill |
|---|---|---|---|---|---|---|---|---|
| annual_mean | 1755 | 0.0933 | 0.7535 | 0.1049 | 0.124 | 0.889 | 0.313 | 0.036 |
| summer_mean | 1703 | 0.0960 | 0.1626 | 0.1160 | 0.590 | 0.828 | 0.103 | 0.086 |
| amplitude | 1171 | 0.0307 | 0.0917 | 0.0778 | 0.335 | 0.394 | 0.057 | 0.039 |
| phase_doy | 1755 | 2.4923 | 3.5875 | 2.9214 | 0.695 | 0.853 | 0.044 | 0.038 |
| p90 | 1755 | 0.1411 | 0.4688 | 0.1430 | 0.301 | 0.987 | 0.086 | 0.071 |
| summer_max | 1703 | 0.1243 | 0.1486 | 0.0943 | 0.836 | 1.319 | 0.028 | 0.003 |
| exceed_days_20 | 1755 | 2.2274 | 6.5493 | 2.2387 | 0.340 | 0.995 | 0.073 | 0.011 |
| exceed_days_25 | 1755 | 0.5157 | 0.6308 | 0.4108 | 0.818 | 1.255 | 0.007 | 0.000 |
| cdd10 | 1755 | 21.721 | 157.727 | 23.495 | 0.138 | 0.925 | 0.223 | 0.014 |
| trend_slope | 1755 | 0.0831 | 0.6599 | 0.1236 | 0.126 | 0.672 | 0.280 | 0.151 |

Reads: (i) reconstruction beats no-fill on every metric, most strongly for
the integrated/accumulated metrics (annual mean, degree days, trend slope,
p90, days>20) — ratios 0.12–0.34; (ii) vs climatology the advantage is
smaller (ratios 0.67–0.99) and reverses for two single-event metrics
(summer_max 1.32, exceed_days_25 1.26): on average the XGBoost reconstruction
is slightly worse than a climatology fill for the hottest-day metrics on the
same placements; (iii) reconstruction worsens vs no-fill on ≤ 8.6% of
placements for 9 of 10 metrics (the trend-slope exception: 15.1%); vs
climatology, 22–31% of placements are worsened for the record-average metrics
(annual mean 0.313, trend slope 0.280, cdd10 0.223), reflecting the
reconstruction's cold-peak bias on summer gaps.

Network-level medians (per-metric medians of network means): recon ≤ no-fill
for all metrics (e.g., annual_mean 0.091 vs 0.791; cdd10 19.4 vs 149.4;
trend_slope 0.064 vs 0.516); recon vs climatology nearly tied for
record-average metrics (annual_mean 0.091 vs 0.094; p90 0.107 vs 0.109) with
climatology ahead for exceed_days_25 and summer_max (0.062 vs 0.000 and 0.060
vs 0.050).

**Support-sensitivity note (affects amplitude and summer metrics).** The
3-way common support excludes placements where no-fill is undefined (amplitude
584/1,755; summer metrics 52/1,755) and where reconstruction itself is
undefined (amplitude 217). Those excluded amplitude placements are the
high-distortion ones: on the reconstruction-only support the mean recon
amplitude error is 0.229 °C vs 0.031 °C on the common support, and the
recon/clim ratio changes from 0.394 (common support) to 0.856 (recon-only
support). The common-support numbers in the table are the conservative ones
(the excluded placements are those where reconstruction struggles), consistent
with agent_b's own station-gap-level aggregation (its amplitude mean recon =
0.0386, ratio 0.375).

Cross-check against agent_b's own station-gap-level summary
(`metric_error_summary.csv`, means over 351 station-gaps): identical to 3–4
decimals for the fully-defined metrics (annual_mean 0.0933, p90 0.1411,
exceed_days_20 2.2274, exceed_days_25 0.5157, cdd10 21.721, trend_slope
0.0831); the placement-level and station-gap-level means differ only for the
partially-defined metrics (summer_mean 0.0960 vs 0.0981; amplitude 0.0307 vs
0.0386; summer_max 0.1243 vs 0.1243; phase 2.4923 vs 2.3614) because of the
different weighting and support. Ratios recon/no-fill match the review's
quoted bands (below).

## B.3 Joint budget table (`budget_joint_table.csv`)

Reduction = 1 − aggregate absolute distortion(policy)/aggregate absolute
distortion(no treatment), per metric; positive = distortion reduced.
Defaults: agent_b = no-fill (270 station-gaps, top 20% = 54 treated;
amplitude 261/53); agent_a = climatology fill (1,965 placements, top 20% =
393 treated). Random: agent_b mean of 20 draws; agent_a mean of 200 draws.

| policy | metric | no-fill default (agent_b) | climatology default (agent_a) |
|---|---|---|---|
| risk | annual_mean | 0.377 | +0.022 |
| risk | summer_mean | 0.188 | −0.230 |
| risk | amplitude | 0.095 | −0.338 |
| risk | phase_doy | 0.117 | −0.108 |
| risk | p90 | 0.307 | −0.130 |
| risk | summer_max | 0.133 | 0.000 |
| risk | exceed_days_20 | 0.308 | −0.222 |
| risk | exceed_days_25 | 0.109 | −0.425 |
| risk | cdd10 | 0.395 | −0.179 |
| risk | trend_slope | 0.348 | −0.157 |
| gap_length | annual_mean | 0.386 | +0.127 |
| gap_length | summer_mean | 0.182 | −0.201 |
| gap_length | amplitude | 0.159 | −0.343 |
| gap_length | phase_doy | 0.109 | +0.020 |
| gap_length | p90 | 0.290 | −0.142 |
| gap_length | summer_max | 0.119 | 0.000 |
| gap_length | exceed_days_20 | 0.240 | −0.331 |
| gap_length | exceed_days_25 | 0.021 | −0.420 |
| gap_length | cdd10 | 0.344 | −0.132 |
| gap_length | trend_slope | 0.522 | −0.064 |
| random | annual_mean | 0.173 | +0.128 |
| random | summer_mean | 0.084 | +0.066 |
| random | amplitude | 0.119 | −0.025 |
| random | phase_doy | 0.053 | +0.054 |
| random | p90 | 0.133 | +0.044 |
| random | summer_max | 0.033 | −0.005 |
| random | exceed_days_20 | 0.124 | +0.029 |
| random | exceed_days_25 | 0.036 | −0.082 |
| random | cdd10 | 0.171 | +0.071 |
| random | trend_slope | 0.173 | −0.020 |

Interpretation for Figure 5 / manuscript: the no-fill default shows recovery
always reduces aggregate distortion (risk policy 9.5–39.5% across metrics);
the climatology default shows risk and gap-length targeting of the longest
summer gaps makes threshold and amplitude metrics *worse* than the
climatology no-treatment baseline (negative reductions), because the top-risk
gaps are long summer gaps where the reconstruction's cold peak bias dominates.
Random selection stays near zero under the climatology default (it mixes
short gaps where reconstruction is clearly better). Both defaults must be
labelled explicitly.

## B.4 Verification of the review's quoted numbers

| claim | found (this analysis) | source / verdict |
|---|---|---|
| agent_b no-fill, integrated metrics recover to 12–14% of no-fill error (degree days, annual mean, trend) | cdd10 0.138, annual_mean 0.124, trend_slope 0.126 | `downstream_baseline_comparison.csv` (placement level) and `metric_error_summary.csv` (0.138/0.124/0.126, station-gap level) — **confirmed** |
| agent_b no-fill, 30–37% (p90, amplitude, threshold days) | p90 0.301, amplitude 0.335 (0.375 station-gap), exceed_days_20 0.340 | **confirmed** (exceed_days_25 at 0.818 sits outside the band and is not in the claimed set) |
| agent_b: recon worse than no-fill in only 0–8% of placements | ≤ 0.086 for 9 of 10 metrics; trend_slope 0.151 | **slight discrepancy**: trend slope exceeds the 8% band (see B.5 log) |
| agent_a climatology-default risk policy: NEGATIVE for degree days (−17.9%) | −17.90% | `budget_combined.csv` risk row — **confirmed** |
| agent_a: days>20 °C (−22.2%) | −22.16% | **confirmed** |
| agent_a: days>25 °C (−42.5%) | −42.54% | **confirmed** |
| agent_a: amplitude (−33.8%) | −33.83% | **confirmed** |
| agent_a: summer mean (−23.0%) | −22.99% | **confirmed** |
| agent_a: annual mean slightly positive | +2.17% | **confirmed** |

## B.5 Linear-interpolation baseline

**Not computable from the artifacts.** `agent_a/reconstruction_series.parquet`
contains only `truth`, `reconstruction`, `climatology` daily series (no
pchip/linear-interpolation series), and
`agent_a/placement_thermal_metrics.csv` contains distortion columns only for
the reconstruction and the climatology fill (`dist_*`, `signed_*`,
`recover_*`). `agent_b/placement_metrics.csv` likewise carries only
truth/recon/no-fill/climatology. The only interpolation-derived artifact in
the repository is the t05 model matrix MAE
(`source_fit_stress_families_1_3.csv` `pchip_or_linear` column: 895 fit
placements at gaps {7,30,90,180}), which contains no daily series and no
thermal metrics, so an `err_interp` column cannot be added without re-running
a reconstruction, which is out of scope for this harmonization task.

## B.6 Discrepancy log (Part B)

1. **agent_b "0–8%" worse-than-no-fill claim**: reproducible for 9 of 10
   metrics at placement level (max 8.6%, summer_mean) but trend_slope is
   15.1% (strict >, common support, n = 1,755). The claim as stated in
   agent_b's REPORT.md slightly overstates the worst case; recommend
   "0–9% (trend slope 15%)" or station-gap-level phrasing (station-gap level:
   0–48% of station-gaps have mean recon > mean no-fill — dominated by
   amplitude/summer means; not recommended as the primary phrasing).
2. **t09 random released-set "net_balanced_regret"**: the published 0.340730
   in `abstention_comparison_part2.csv` is the pooled mean over the 20 draws
   (line 811 of the t09 script), not the network-balanced regret; the
   definitionally consistent network-balanced value is 0.350862. Both are
   reported here; the pooled value reproduces exactly.
3. **Review numbers vs this recomputation**: all quoted agent_a budget
   percentages and agent_b ratio bands verified within rounding (Section
   B.4). The absolute per-placement distortion levels differ between the two
   t08 agents (e.g., annual_mean 0.011 agent_a vs 0.093 agent_b) because of
   the metric window (whole evaluation record vs 365-day gap-centred window)
   and panel composition — documented in `divergence_note.md`; ratios within
   each run are unaffected.
4. **top-2 hit definition**: t09's published values (0.8965 no-abstention,
   0.9512 at the 8.5% set) use the penalized-risk top-2 containing the true
   best; this analysis additionally reports the loss-based top-2 (selected
   family among the two lowest-loss families). Both columns are in
   `coverage_regret_curve.csv`; t09's definition reproduces exactly.

---

# What feeds the manuscript

- **Figure 4 (model-selection coverage–regret)**: `coverage_regret_curve.csv`
  (curves: per criterion × method × c, with unit/network coverage on the
  x-axis and network-balanced regret on the y-axis; the current-8.5% rows for
  the rule-based operating point), `coverage_regret_summary.md` (key rows),
  `comparators_table.csv` (headline numbers). Suggested figure: three panels
  (criteria a/b/c) with the 8.5% point marked; caption must state that the
  8.5% point is rule-based (support-any + ambiguity), not a top-c release.
- **Figure 5 (downstream thermal)**: `downstream_baseline_comparison.csv`
  (mean errors, ratios, worse-shares per metric) and `budget_joint_table.csv`
  (policy × metric × both defaults).
- **Text**: the review-claim verification (B.4) and the divergence note
  (baseline labels, metric-window statement) belong in the methods/limitations
  sections.

# Deliverables in this namespace

| file | content |
|---|---|
| `partA_coverage_regret.py` | full Part A pipeline (reproduction + fixed-coverage curves) |
| `partB_downstream.py` | full Part B pipeline (baseline table, joint budget, claim verification) |
| `coverage_regret_curve.csv` | 217 rows: (criterion, c, method) × metrics, incl. c=1.0 and current_85pct |
| `coverage_regret_summary.md` | key rows: c = 0.5/0.7 per criterion, 8.5% point, no-abstention |
| `comparators_table.csv` | per method: regret at no-abstention / 50% / 70% / 8.5% / min over c |
| `selection_frequency.csv` | per (method, criterion, c): share of released units per family |
| `downstream_baseline_comparison.csv` | per metric: means, net-medians, ratios, worse-shares (common support) |
| `budget_joint_table.csv` | policy × metric × default (no-fill / climatology) reductions |
| `divergence_note.md` | agent_a vs agent_b t08 implementation differences |
| `REPORT.md` | this report |
