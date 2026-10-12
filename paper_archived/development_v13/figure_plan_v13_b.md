# Figure plan v13 (agent fig_b): five main figures and SI displays

This document **replaces** `paper/development_v12/figure_plan_v12.md` and defines
exactly five main figures plus a Supporting Information (SI) list for the v13
manuscript. Every number below was verified against the CSVs under
`results/revision_v12/<task>/<agent>/` and the planned
`results/revision_v13/strongest_baseline/agent_a/` and
`results/revision_v13/decision_harmonization/agent_a/` outputs; where a number
appears in the review text but not in the artifacts it is not used.

## Global conventions

**Primary comparator.** The strongest fair baseline is the station × horizon
historical mean of fitting-period MAE ("r6"; ladder rung `r6_station_gap`). On
the second panel direct-874 subset it reaches pooled Spearman 0.942 vs the
empirical predictor's 0.945 and network-level Spearman 0.763 vs 0.805
(`t03_baseline_ladder/agent_a/master_ladder_table.csv`); the paired network
Δρ ≈ +0.042 with a CI straddling zero
(`t03_baseline_ladder/agent_a/paired_bootstrap.csv`). Figure 2 makes r6 the
primary comparator; simple structural descriptors are the second comparator;
the +0.55-vs-simple headline is demoted to a secondary annotation.

**Evidence-provenance roles** (shown in every figure and caption):
- **Frozen pre-outcome**: predictions produced before any outcome-based
  revision: the empirical transfer curve (`empirical_transfer_prediction`,
  `t03`/`t01` `predictions.csv`), the frozen hierarchical risk surface
  (`t04`, `r11_surface`), and all fitting-period-only descriptors (r1–r8
  ladder rungs).
- **Post-hoc v12 development**: analyses developed during revision v12 on
  frozen predictions: paired bootstraps, duration/abstention analysis,
  decision utility, downstream metrics, model-family and missingness
  matrices.
- **v13 harmonization**: independent re-verification and harmonization
  (`results/revision_v13/strongest_baseline/agent_a/`,
  `results/revision_v13/decision_harmonization/agent_a/`), including the
  missingness-implementation divergence and coverage–regret curves.
- **Future preregistered**: the protocol-v4 third panel; shown only as a
  dashed/future region, never as data.

**Visual code.** Solid dark markers/lines = frozen pre-outcome;
solid light = post-hoc v12; hatched/accent = v13 harmonization; dashed
outline = future preregistered. Extrapolation regions are always red with
hatching; interpolation regions are amber. Colors encode domain, panel, or
support tier, never individual networks. Captions lead with the scientific
result and state the panel (development / first / second), the unit count,
the support restriction, and the evidence role.

**Panel composition (verified in
`results/revision_v13/strongest_baseline/agent_a/panel_composition.csv`).**
Second panel: 57 networks (US 32, CZ 15, NO 10), 224 stations, 1,446 units
(874 direct, 572 fallback). First panel: 42 networks, 1,440 units (858
direct). Development panel: 55 networks, 1,260 units. (The v12 manuscript's
"35 US" is a bug; US = 32.)

---

## Figure 1 — Nested temporal design, support tiers, and evidence provenance

**Purpose.** Make the design that licenses every claim in the paper visible:
the model-conditional stress-test construction, the support hierarchy that
defines prediction provenance, the interpolation/extrapolation regions of the
duration surface, and the evidence status of each analysis stream.

**Panels / unit counts.** Schematic; no data. Panel counts annotated:
development 55 networks / 1,260 units; first 42 / 1,440; second 57 / 1,446
(US 32, CZ 15, NO 10; 224 stations).

**Layout.** (a) Outer chronological split (70% fitting / 30% evaluation) with
the nested split inside the fitting years (70% fit / 30% artificial-gap
truth); the four stress durations (7, 30, 90, 180 d) with seasonal placement
strata. (b) The five-level support hierarchy: exact station × duration ×
season; station–duration; network–duration; network-mean fallback;
unavailable. (c) The continuous duration surface with supported (≤180 d),
interpolated (14, 60 d, amber) and extrapolated (365 d, red/hatched)
regions; the extrapolation factor (0.218) and widening multiplier (1.435)
annotated. (d) Evidence-provenance legend mapping the four roles (frozen
pre-outcome / post-hoc v12 / v13 harmonization / future preregistered) to the
visual code above; a dashed "third panel (preregistered)" box marks the
prospective confirmation panel. Fallback composition annotation: 596
second-panel fallback units = 224@14 d + 224@60 d + 124@365 d + 4@90 d +
20@180 d (`t02_support_hierarchy/agent_a/REPORT.md`), of which 24 are
direct-horizon cross-duration fallbacks (4@90 d, 20@180 d, 6 networks).

**Data sources.** Design constants only:
`results/revision_v12/t02_support_hierarchy/agent_a/REPORT.md` (tier
definitions and counts), `results/revision_v13/strongest_baseline/agent_a/panel_composition.csv`
(columns `panel`, `subset`, `domain`, `n_networks`, `n_stations`, `n_units`),
`results/revision_v12/t04_risk_surface/agent_a/surface_fit_summary.json`
(`extrapolation.max_supported_gap`, `extrapolation_factor_365`,
`widening_multiplier_365`).

**Caption (leading with the result).** "The stress test is a nested,
model-conditional design: every prediction is measured inside the fitting
record of the recovery model it ranks, every prediction carries an explicit
support tier, and the 365-day duration is flagged extrapolation, not
support; each analysis stream below is labeled frozen pre-outcome,
post-hoc v12 development, v13 harmonization, or future preregistered."
(Second panel, 57 networks; design schematic; evidence-provenance legend.)

---

## Figure 2 — Strongest-baseline external comparison (second panel, direct-874)

**Purpose.** Report the head-to-head of the frozen empirical predictor against
the two comparators on the *same* units: the station × horizon mean (r6,
primary) and simple structural descriptors (secondary). This is the
fair-baseline figure; it supersedes the v12 "empirical vs simple" framing.

**Units.** 874 direct-support units, 57 networks (second panel). No fallback
units enter; the fallback-dependent reversals are shown only as inset rows.

**Panel A — Empirical vs station × horizon mean (r6).** Predicted vs observed
loss (both in °C MAE) on the same 874 units, empirical predictor vs
`r6_station_gap`, with equal-network calibration lines and per-network
medians. Printed statistics: pooled Spearman 0.945 vs 0.942; network
Spearman 0.805 vs 0.763; calibration slopes 0.938 vs 0.924, intercepts 0.138
vs 0.167 (verified in
`results/revision_v13/strongest_baseline/agent_a/summary_metrics.csv` rows
`second/direct_874/empirical` and `second/direct_874/r6`). The 1:1 line is
drawn; the two curves are nearly collinear (predictor Spearman
correlation 0.996, `predictor_correlation.csv`), which is the point:
r6 is the strongest fair comparator.

**Panel B — Empirical vs simple descriptors.** Same layout as Panel A against
`r8_simple` (`simple_fitperiod` in `t01` files; identical column
`r8_simple` in `unit_predictions_second.csv`). Printed statistics: pooled
0.945 vs 0.846; network 0.805 vs 0.248. This is the demoted v12 headline,
now presented as the secondary comparator.

**Panel C — Paired network-bootstrap Δρ forest relative to BOTH baselines.**
Four rows (2000-network resamples of the 57 networks, paired):
- empirical − r6, network level: **+0.041 [−0.000, +0.114]**, win fraction
  0.971 (v13 canonical) / +0.042 [−0.001, +0.115] (t03);
- empirical − r6, station-gap (pooled) level: **+0.003 [−0.000, +0.007]**;
- empirical − simple, network level: **+0.552 [+0.309, +0.814]**;
- empirical − simple, station-gap (pooled) level: **+0.098 [+0.059,
  +0.142]**.
Insets (grey, marked "fallback artifact", second panel all-1,446):
empirical − simple network +0.109 [−0.126, +0.356], pooled −0.097 [−0.158,
−0.028]; empirical − r6 network −0.011 [−0.036, +0.008].

**Panel D — Within-network effects distribution.** Violin/box of
per-network Spearman (empirical vs r6 vs simple; n = 57 networks) plus the
network-demeaned (residualized) pooled Spearman. Values (second/direct_874):
empirical median within-network 0.965 (Q1–Q3 0.944–0.982), demeaned pooled
0.936; r6 0.968 (0.937–0.982), demeaned 0.930; simple 0.937 (0.909–0.962),
demeaned 0.896. Benchmark: a predictor separating network means only reaches
pooled 0.326 (`t01_paired_comparison/agent_a/REPORT.md`), i.e. the ranking
power is within-network, and r6 achieves the same within-network level as the
empirical predictor.

**Data sources.**
- `results/revision_v13/strongest_baseline/agent_a/paired_bootstrap.csv`
  (columns `panel`, `subset`, `level` [pooled|network], `delta_mean`,
  `ci_low`, `ci_high`, `win_fraction`, `rho_empirical_boot_mean`,
  `rho_r6_boot_mean`, `n_networks`, `n_units`, `repeats`),
  `summary_metrics.csv` (columns `panel`, `subset`, `method`, `n`,
  `n_networks`, `pooled_spearman`, `network_spearman`,
  `calibration_intercept`, `calibration_slope`, `r2`, `rmse`),
  `within_network_decomposition.csv` (columns `panel`, `subset`, `method`,
  `network_demeaned_pooled_rho`, `median_within_network_rho`, `within_q1`,
  `within_q3`, `n_networks_defined`), `predictor_correlation.csv`.
- `results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_second.csv`
  (columns `network_id`, `horizon_group`, `empirical_transfer_prediction`,
  `r6_station_gap`, `r8_simple`, `surface_prediction_mae`,
  `observed_recovery_loss`), `master_ladder_table.csv` (rung rows),
  `paired_bootstrap.csv` (rows `empirical` vs `r6_station_gap` and
  `empirical` vs `r8_simple`; columns `delta_network_spearman_mean`,
  `delta_network_spearman_ci95`, `delta_pooled_spearman_mean`,
  `delta_pooled_spearman_ci95`, `fraction_delta_network_positive`).
- `results/revision_v12/t01_paired_comparison/agent_a/predictions.csv`
  (columns `empirical_transfer_prediction`, `simple_fitperiod`,
  `observed_recovery_loss`, `horizon_group`),
  `paired_bootstrap.csv` (direct_874 and all_1446 rows, columns
  `delta_network_spearman_mean`, `delta_network_spearman_ci95`,
  `delta_station_gap_spearman_mean`, `delta_station_gap_spearman_ci95`),
  `within_network_decomposition.csv`.

**Layout.** 2×2 grid: A top-left, B top-right, C bottom-left (forest with
95% CI lines, zero line at x = 0, baseline-labeled facet headers), D
bottom-right. Shared x/y scales within A/B rows.

**Axis/color conventions.** Predicted vs observed axes in °C; A/B use the
same axis limits. Empirical = dark solid; r6 = blue; simple = grey; CIs
horizontal error bars; inset fallback rows 50% transparency.

**Caption.** "Against the strongest fair baseline — the fitting-period
station × horizon mean — the frozen empirical predictor ranks future loss
equally well at the network level (paired Δρ +0.041 [−0.000, +0.114]) and
the pooled level (+0.003 [−0.000, +0.007]) on the same 874 directly
supported second-panel units (57 networks), and the two are 99.6%
correlated; the v12 headline advantage over simple descriptors (+0.552
[+0.309, +0.814]) is a second comparator, and both advantages collapse on
the 572 network-mean fallback units." (Evidence roles: empirical predictions
and r6 fitting-period descriptors frozen pre-outcome; paired bootstraps
post-hoc v12; all statistics re-verified in v13 harmonization; no future
panel data.)

---

## Figure 3 — Duration response: supported, interpolated, extrapolated

**Purpose.** Explain *why* methods differ and make the failure boundary
explicit: the response of loss to gap duration, the interval coverage by
support region, and the abstention boundary that removes extrapolated units.
Extrapolation beyond 180 days fails and is visually separated from
supported/interpolated durations.

**Units.** Second panel, 1,446 units, 57 networks. Subsets: supported direct
7/30/90/180 d (874 units); interpolated 14/60 d (448 units); extrapolated
365 d (124 units from 30 networks).

**Panel A — Predicted vs observed by duration.** Mean predicted vs mean
observed loss at each duration (7, 30, 90, 180 d supported; 14, 60 d
interpolated in amber; 365 d extrapolated in red hatching), with the
monotone surface duration curve overlaid: fitted effect MAE 0.633 °C at 7 d,
1.595 °C at 180 d, 2.563 °C at 365 d
(`t04_risk_surface/agent_a/surface_fit_summary.json` →
`monotone_curve.effect_mae_at_7/180/365`). Realized MAE series annotated
(`t10_covariance_fix/agent_a/mechanism_horizon_corrected.csv`: 7 d 0.544,
14 d 0.667, 30 d 0.815, 60 d 0.975, 90 d 1.240, 180 d 2.432, 365 d 4.719 °C)
and the expected-Gaussian-MAE bound (flat 0.379–0.451 °C) as a shaded band,
demonstrating the covariance estimand saturates while realized MAE runs
0.544–4.719 °C.

**Panel B — Interval coverage by region.** 90% interval coverage:
overall 92.5%; direct 96.0%; interpolated 98.2%; **extrapolated 365 d
46.8%** (`t04_risk_surface/agent_a/REPORT.md`). The extrapolated bar is red
with hatching and annotated "pre-specified widening (factor 0.218, width
×1.435) does not rescue coverage". Per-region evaluation annotation
(`t04_risk_surface/agent_a/evaluation_second_panel.csv`): surface network
Spearman 0.689 (direct 874) / 0.768 (interpolated 448) / **0.270
(extrapolated 124, pooled 0.411, RMSE 3.309 °C)**.

**Panel C — Abstention boundary.** Abstention curve for the
extrapolated-flag rule (`t04_risk_surface/agent_a/abstention_curve.csv`,
rule `extrapolation_factor`, threshold 0.217; and
`t09_decision_utility/agent_a/abstention_curve_part1.csv`, rule
`surface_extrapolated`): abstains 124 units = 8.6% of units carrying
**28.9%** of total observed loss (652.9 / 2,257.2 °C,
`t03_baseline_ladder/agent_a/unit_predictions_second.csv`); released-unit
network Spearman **0.691**, R² **0.663**, slope 1.312; released-set
CapturedLoss@20% rises to 0.431 vs oracle 0.452
(`abstention_curve_part1.csv` columns `rule`, `fraction_abstained`,
`n_abstained`, `n_released`, `abstained_loss_share`,
`captured_loss_released_surface`, `oracle_captured_released`).

**Data sources.** `t04_risk_surface/agent_a/` (`duration_curve.csv` columns
`gap_days`, `duration_effect_mae`; `second_panel_predictions.csv` columns
`gap_length`, `surface_prediction_mae`, `surface_lower90`,
`surface_upper90`, `observed_recovery_loss`, `support_status`
[direct|interpolated|extrapolated], `extrapolation_factor`;
`evaluation_second_panel.csv`; `abstention_curve.csv`;
`surface_fit_summary.json`), `t10_covariance_fix/agent_a/mechanism_horizon_corrected.csv`
(columns `gap_length`, `realized_mae`, `expected_gaussian_mae`,
`conditional_risk`), `t09_decision_utility/agent_a/abstention_curve_part1.csv`,
`t03_baseline_ladder/agent_a/unit_predictions_second.csv`.

**Layout.** Three stacked panels (A top, B middle, C bottom); C is a
two-curve plot (released loss share vs fraction abstained with the 124-unit
operating point marked). Extrapolated elements are red hatched in all three
panels.

**Axis/color conventions.** x = gap duration (log scale in A); extrapolated
region shaded red/hatched everywhere; interpolated region amber; vertical
boundary at 180 d labeled "max supported gap".

**Caption.** "Loss grows monotonically with gap duration and the Gaussian
bound saturates (0.379–0.451 °C) while realized MAE runs 0.544–4.719 °C;
interval coverage is 92.5% overall and 98.2% for interpolated durations but
collapses to 46.8% at the extrapolated 365-day duration (network Spearman
0.270), which is why the abstention rule removes exactly those 124 units —
8.6% of units, 28.9% of loss — leaving released-unit network Spearman 0.691
(R² 0.663) and raising 20%-budget captured loss from 0.337 to 0.431."
(Second panel, 57 networks; supported/interpolated/extrapolated regions
separated; surface fit frozen pre-outcome, coverage/abstention post-hoc
v12.)

---

## Figure 4 — Model-selection coverage–regret (decision figure)

**Purpose.** The decision figure for the model-selection result: coverage
(fraction of units released) on the x-axis, network-balanced regret on the
y-axis. Fixed-budget triage is reported as a negative (empirical
CapturedLoss@20% 0.338 vs simple 0.512), so the paper's positive decision
claim is the selection gain at a protocol-compliant coverage point — which
must be ≥50% of units, ≥60% of networks, with 70% the target
(protocol-v4 floors).

**Units.** First panel, 1,440 units, 42 networks (`selection_predictions_part2.csv`).

**Curves.** Coverage–regret curves (full sweep of the abstention threshold,
coverage 0–100% on the x-axis) for: proposed support-aware selector
(`proposed_risk`), best fixed family (`best_fixed_dev`), global blocked CV
(`global_blockedCV`), per-network CV (`per_network_avgCV`), gap-length rule
(`gap_length_rule`), random, oracle. Existing verified endpoints
(`selection_regret_table_part2.csv`, columns `selector`, `lambda`,
`abstention`, `fraction_abstained`, `net_balanced_regret`, `n_released`;
`abstention_comparison_part2.csv`; `bootstrap_part2.csv`):
- Coverage 100% (no abstention): proposed 0.084 (λ 0.5; 0.084 at λ 0.0),
  best fixed 0.081, global CV 0.081, per-network CV 0.038, gap rule 0.093,
  random 0.263, oracle 0.000.
- Coverage 8.5% (123 released units from 8 networks;
  `selection_calibration_part2.csv` shows 8 networks per ridge family):
  proposed **0.0067 [0.0019, 0.0120]** (bootstrap), best fixed 0.151,
  global CV 0.151, per-network CV 0.164, gap rule 0.145, random 0.341.
The 8.5% point is marked with a filled hatched marker and labeled "current
operating point — below the ≥50% coverage floor"; vertical dashed lines at
coverage 50%, 60%, 70% mark the protocol floors, with the 70% target
annotated "target". The interpolated curves between the two endpoint columns
are the v13 harmonization deliverable: `results/revision_v13/decision_harmonization/agent_a/coverage_regret_curves.csv`
(schema: `selector`, `coverage` [0–1], `net_balanced_regret`,
`n_released`, `n_networks`, `lambda`), produced by threshold sweeps of
`selection_predictions_part2.csv` risk scores plus the abstention rules.

**Data sources (existing).** `t09_decision_utility/agent_a/selection_regret_table_part2.csv`,
`abstention_comparison_part2.csv`, `bootstrap_part2.csv` (rows
`regret_proposed_l0.5_abst` mean 0.006669, CI [0.001933, 0.012003];
`diff_proposed_l0.5_minus_best_fixed` 0.0037 [−0.0255, 0.0330]),
`selection_predictions_part2.csv` (columns `network_id`, `station_id`,
`gap_length`, risk and support scores, `true_best_family`, `min_loss`,
`selected_lambda*`), `selection_calibration_part2.csv`.

**Layout.** Single panel, coverage 0–100% (x) vs network-balanced regret (y,
log or linear as the curves demand; linear default), one line per selector
with 95% bootstrap bands for the proposed selector at the two endpoint
columns; floor lines vertical, target line heavier.

**Axis/color conventions.** Proposed selector = dark solid with hatched
band; comparators = light greys/blue; oracle = thin black at 0; floors =
vertical grey dashed (50, 60) and dark dashed (70); current 8.5% point =
red hatched marker.

**Caption.** "Model-selection regret is only meaningful at a protocol
coverage: the proposed support-aware selector reaches network-balanced
regret 0.0067 [0.0019, 0.0120] but only at 8.5% coverage (123 units, 8
networks) — below the ≥50%-unit/≥60%-network floors and the 70% target —
while at full coverage it is statistically indistinguishable from the best
fixed family (0.084 vs 0.081, paired diff 0.004 [−0.026, +0.033]); fixed-
budget triage by the frozen empirical risk score is a reported negative
(CapturedLoss@20% 0.338 vs simple 0.512, diff −0.174 [−0.198, −0.140])."
(First panel, 1,440 units, 42 networks; full coverage = post-hoc v12,
abstention sweeps and coverage floors = v13 harmonization; floors are
protocol-v4 constraints, not data.)

---

## Figure 5 — Downstream incremental benefit vs untreated baselines

**Purpose.** Report downstream thermal-metric value against three untreated
baselines — no-fill (gap days dropped), climatology (day-of-year medians of
the fitting record), and interpolation (linear fill across the gap) —
because the v12 no-fill-only framing reverses for threshold metrics under
climatology. The figure is a forest of incremental benefit
B = D(baseline) − D(model) per thermal metric, in the metric's units, with
sign-reversal points marked.

**Units.** Placement-level: 351 placements, 15 networks (amplitude 342;
`t08_downstream_metrics/agent_b/metric_error_summary.csv`). Risk-selected
rows: 270 treatable placements, 54 treated
(`t08_downstream_metrics/agent_b/budget_comparison.csv`).

**Panels.** Three forest panels, one per baseline, x = B (benefit; positive
= model beats the baseline), one row per metric (annual mean, summer JJA
mean, amplitude, phase day, p90, summer max, exceed days >20, exceed days
>25, degree days >10, trend slope):

- **No-fill baseline** (existing v12 numbers): fixed-model row B =
  mean error no-fill − mean error recon (`metric_error_summary.csv` columns
  `metric`, `mean_err_missing`, `mean_err_recon`): annual mean +0.660,
  summer mean +0.067, amplitude +0.064, phase +1.059 d, p90 +0.328,
  summer max +0.024, exceed_20 +4.322, exceed_25 +0.115, cdd10 +136.0
  degC-days, trend slope +0.577. Risk-selected row (top-20% risk placements
  treated, `budget_comparison.csv` columns `policy=top20_risk`, `metric`,
  `aggregate_no_treatment`, `aggregate_treated`; B per placement =
  (no_treatment − treated)/n_units): all ten metrics positive (reductions
  0.095–0.395). Oracle row: v13 harmonization recomputation on the same 270
  units (top-20% by true loss); agent_a `budget_combined.csv` `oracle_*`
  rows are the v12 reference but use a different denominator — flagged, not
  mixed.
- **Climatology baseline**: fixed-model row B = `mean_err_clim` −
  `mean_err_recon`: annual mean +0.012, summer mean +0.019, amplitude
  +0.040, phase +0.413, p90 +0.002, **summer max −0.029 (reversal)**,
  exceed_20 +0.011, **exceed_25 −0.105 (reversal)**, cdd10 +1.774, trend
  slope +0.040. Reversed points drawn red. Risk-selected and oracle rows:
  planned v13 harmonization output.
- **Interpolation baseline**: no existing artifact; all three rows are
  planned v13 harmonization outputs computed from
  `t08_downstream_metrics/agent_b/placement_metrics.csv` (per-placement
  `*_truth`, `*_recon`, `*_missing`, `*_clim`, `*_err_*` columns) with
  gap-fill by linear interpolation of the daily series.

Vertical zero line; sign-reversal points (B < 0) in red with the metric
name bolded; "reversal" bracket annotation. Computability annotation:
amplitude is undefined for no-fill in 20.9% of placements
(`t08_downstream_metrics/agent_b/REPORT.md`,
`uncomputable_no_fill.csv`).

**Data sources (existing).** `t08_downstream_metrics/agent_b/metric_error_summary.csv`,
`budget_comparison.csv`, `placement_metrics.csv`, `uncomputable_no_fill.csv`;
`t08_downstream_metrics/agent_a/budget_combined.csv` (oracle rows, flagged
scale difference). **Planned:** `results/revision_v13/decision_harmonization/agent_a/thermal_benefit_{nofill,climatology,interpolation}.csv`
(schema: `baseline`, `policy` [fixed|risk20|oracle], `metric`, `n_units`,
`benefit`, `benefit_ci_low`, `benefit_ci_high`), with bootstrap CIs over
placements.

**Caption.** "Reconstruction recovers downstream thermal metrics to 12–84%
of the no-fill error on all ten metrics, and risk-selected triage improves
distortion further (0.10–0.40 reductions), but against climatology the
benefit reverses for threshold metrics (summer max −0.029, days >25 °C
−0.105) and is near zero for p90 and days >20 °C; incremental value is
baseline-dependent and must be reported against no-fill, climatology, and
interpolation together." (351 placements, 15 networks; placement-level
distortion; fixed-model rows post-hoc v12, climatology/interpolation rows
v13 harmonization; no future panel data.)

---

## Supporting Information (SI) displays

1. **Study flow and panel composition.** Phase diagram (development 55
   networks / 1,260 units; first 42 / 1,440; second 57 / 1,446 = US 32, CZ
   15, NO 10; 224 stations), outcome-disjoint audit, and
   `results/revision_v13/strongest_baseline/agent_a/panel_composition.csv`.
2. **Full 12-rung baseline ladder.** `t03_baseline_ladder/agent_a/master_ladder_table.csv`
   for both panels and subsets (r1_global through r12_stack; r9_condcov
   empty/NA documented): all rungs with pooled/network Spearman,
   calibration, RMSE; rung 6 (station × horizon mean) flagged as the
   primary fair baseline; rung 10 (blocked CV) negative as expected.
3. **Per-horizon tables.** `t01_paired_comparison/agent_a/per_horizon_network_spearman.csv`
   (7/30/90/180 d: n = 224/224/220/206, networks 57/57/56/53; empirical vs
   simple) and `results/revision_v13/strongest_baseline/agent_a/per_horizon_network_spearman.csv`
   (empirical vs r6: 0.932 vs 0.938, 0.916 vs 0.915, 0.865 vs 0.843, 0.659
   vs 0.603); provider-block descriptives (US 32 / CZ 15 / NO 10).
4. **Support-tier tables.** `t02_support_hierarchy/agent_a/` for all three
   panels: per-tier counts, pooled and network Spearman, calibration,
   support-quality terciles, mixing diagnostics; the exact
   station×duration×season tier alone reproduces network 0.887 on 841
   second-panel units; fallback composition 596 = 224@14 + 224@60 +
   124@365 + 4@90 + 20@180 with the 24 direct-horizon fallback units
   separated.
5. **Rolling-origin and history length.** `t07_rolling_origin/agent_a/`:
   per-cutoff tables (0.6/0.7/0.8 legs; 60% leg retains 14 of 20 networks,
   6 attrited), rank stability (Kendall W 0.917, mean pairwise Spearman
   0.875, min 0.824), history-length learning curves (2–8 y + full;
   `learning_curve_metrics.csv`), training-length comparability
   (`comparability_summary.csv`: matched-vs-unmatched network Spearman
   0.940, pooled 0.908, max rank change 6, mean network-prediction
   difference 0.135 °C).
6. **Model-family matrix.** `t05_model_matrix/agent_a/matrix_network_spearman.csv`
   with per-cell n-networks (`matrix_n_networks.csv`), panel labels per cell
   (`matrix_headline.csv`: first_confirmation 119 units/8 networks,
   second_confirmation 1,446/57, development_validation 640/51, bilstm
   10 networks, air2stream 4–8 networks/14–23 units), diagonal vs
   off-diagonal (one-sided MWU p = 0.033; diagonal mean 0.783 vs
   off-diagonal 0.434), calibration slopes, station-gap-level matrix,
   neural convergence/seed stability (best-epoch medians 32–99, epoch-cap
   hit rates 0–0.667 across 12 networks × 3 seeds), air2stream caveats; a
   note that matrix conclusions are instance-specific where only one
   analysis instance exists.
7. **Missingness matrix, both implementations.** `t06_missingness_matrix/agent_a/`
   (matched design; `mechanism_metrics.csv` diagonal: multi-block 0.944,
   donor-synchronous 0.979, target+primary-covariate 0.881, online 0.930,
   uniform 0.531, summer-biased 0.594, high-temperature-biased 0.580;
   `mismatch_metrics.csv` uniform-curve mismatch rows, slope collapse
   0.90→0.14 for multi-block) and `agent_b/` (supported/full design;
   `mechanism_metrics.csv` donor-sync supported network 0.490 with
   bootstrap CI [−0.236, +0.925]; `mechanism_bootstrap_intervals.csv`). The
   donor-synchronous divergence (0.979 matched vs 0.490
   supported/full-design) is documented with its cause (curve
   re-estimation on support-restricted units vs matched design) and the
   v13 harmonization plan: one shared design re-estimated in
   `results/revision_v13/decision_harmonization/agent_a/missingness_harmonized.csv`.
8. **Covariance estimand appendix.** `t10_covariance_fix/agent_a/mechanism_horizon_corrected.csv`
   (corrected horizon table: expected Gaussian MAE flat 0.379–0.451 °C vs
   realized 0.544–4.719 °C), plug-in covariance simulation (downward bias
   at small M), incremental-value replications.
9. **Downstream full tables.** `t08_downstream_metrics/agent_a/metric_error_tables.csv`
   (ten-metric errors by horizon), `correlation_risk_distortion.csv`,
   `metric_protection_summary.csv`, agent_b `placement_metrics.csv`,
   `budget_comparison.csv` (all policies × metrics), `metric_error_summary.csv`,
   uncomputable-placement audit (amplitude undefined in 20.9% of no-fill
   placements).
10. **Decision-utility detail.** `t09_decision_utility/agent_a/utility_table_part1.csv`
    (full budget grid with worst-decile recall, NDCG, regret vs oracle),
    `bootstrap_part1.csv`, `policy_overlap_part1.csv` (top-20% Jaccard
    overlaps), `abstention_curve_part1.csv`, part-2 per-family calibration
    (`selection_calibration_part2.csv`), common-scale robustness
    (`common_scale_c.json`), ambiguity threshold sweep, and the
    coverage–regret endpoint tables.
11. **Protocol v4 summary table.** Endpoints and frozen margins; primary
    comparator fixed as station × horizon mean with paired Δρ
    (power: 80% at N = 120 for Δρ +0.038, v3 anchor retained); coverage
    floors ≥50% units / ≥60% networks, 70% target; the three untreated
    downstream baselines (no-fill, climatology, interpolation) declared;
    abstention rule (extrapolated-flag + support) declared; external
    timestamping requirements.

---

## Sources and verification notes

- Numbers above are read from the v12 CSV artifacts and the existing
  `results/revision_v13/strongest_baseline/agent_a/` outputs (which
  re-verified the ladder, paired bootstrap, per-horizon and within-network
  statistics; `verification_summary.json` lists `master_ladder_verification`
  rows with per-method `True` matches for both panels and subsets).
- Points in Figure 3 and Figure 4 that require new computation (coverage–
  regret curves; climatology/interpolation benefit rows) are explicitly
  marked as planned `results/revision_v13/decision_harmonization/agent_a/`
  outputs; nothing is invented where no artifact exists.
- The v12 figure plan's numbers that no longer appear here were demoted or
  corrected per the v13 restructure: +0.552-vs-simple is secondary; the
  "13 networks / Kendall W 0.811" rolling-origin text is replaced by the
  artifact values (14 networks, W 0.917); the "35 US" panel count is
  corrected to 32.
