# Figure plan v13 (merged): five main figures and supporting displays

Complete replacement of `paper/development_v12/figure_plan_v12.md`. All numbers below
were re-verified against the CSVs listed as sources (trust CSVs over review prose);
planned v13 analyses are referenced as sources where they are not yet computed.

## Cross-cutting conventions (apply to every figure)

- **Evidence-role taxonomy (must be visible in every figure and caption):**
  - **Frozen pre-outcome** — artifacts frozen before outer-panel outcomes were opened:
    the empirical transfer curve (t01/t03 `empirical` column), the hierarchical risk
    surface (t04, frozen surface predictions), the XGBoost reconstruction (t08).
    Color: solid blue.
  - **Post-hoc v12 development** — all revision analyses (baseline ladder, matrices,
    decision utility, downstream metrics, protocol v3). Color: solid grey/black.
  - **v13 harmonization** — the restructured comparisons specified here (primary
    strongest-baseline comparator, coverage–regret decision curves, three-baseline
    downstream benefit). Color: hatched orange.
  - **Future preregistered third panel** — protocol v4 items (external registration,
    third panel, support floors). Color: dashed green.
- **Comparator hierarchy:** the strongest fair baseline — station × horizon historical
  mean of fitting-period MAE (t03 ladder `r6_station_gap`) — is the primary comparator
  in Figure 2. Simple structural descriptors (ladder `r8_simple`, route-A fit-period)
  are a secondary comparator. The former headline "+0.55 vs simple" is demoted to a
  baseline-weakness explanation, never a headline.
- **Colors encode evidence role and support tier, never dozens of individual networks.**
  Direct = solid, interpolated = hollow, extrapolated = red + hatching.
- Captions lead with the scientific result and state: panel, unit count, support
  restriction, and evidence role.
- All second-panel claims use 57 networks (US 32 / CZ 15 / NO 10). The v12
  manuscript's "35 US" is a bug; the correct count is **32** (`t01_paired_comparison/
  agent_a/provider_sensitivity.csv`: usgs n=32 networks, 703 units; chmi n=15, 478;
  nve_hydapi n=10, 265).

---

## Figure 1 — Nested temporal design, support tiers, and interpolation/extrapolation regions

**Purpose.** Locate every stress test in the model-conditional design so that
support provenance and evidence provenance are explicit before any performance claim.
Schematic (no statistical estimation); it replaces the v12 Fig 1 with the added
interpolation/extrapolation regions and the evidence-role legend.

**Panels / unit counts.**
- Panel A — chronology: outer chronological split (70% fitting / 30% evaluation) of
  the second panel; nested split inside the fitting years (70% fit / 30%
  artificial-gap truth); the four stress-test durations 7/30/90/180 d with seasonal
  placement strata (DJF/MAM/JJA/SON); the continuous duration axis extended to the
  interpolated (14, 60 d) and extrapolated (365 d) regions.
- Panel B — support tiers (five-level hierarchy) with second-panel counts:
  exact station×duration×season tier 841 units / 57 networks; station-gap tier 9 / 2;
  network-gap tier 0; network-mean fallback 596 / 57 (of which 24 units fall on the
  four direct horizons); unavailable 0. Support regions on the duration axis: direct
  874 units, interpolated 448, extrapolated 124.
- Panel C — evidence-provenance legend (four categories above), placed inside the
  figure so that every subsequent figure reuses the same legend.

**Sources (existing).** `results/revision_v12/t02_support_hierarchy/agent_a/`
(`key_decomposition.json`, `analysis_results.json`, `tier_metrics_second.csv`,
`tier_gap_composition_second.csv`); `results/revision_v12/t03_baseline_ladder/agent_a/
unit_predictions_second.csv` (providers/domains); `results/revision_v12/t04_risk_surface/
agent_a/second_panel_predictions.csv` (column `support_status`: direct 874,
interpolated 448, extrapolated 124); `results/revision_v12/t01_paired_comparison/
agent_a/provider_sensitivity.csv` (panel composition); dev 55 networks / 1,260 units
(`t03_baseline_ladder/agent_a/dev_supplemental_conditional_covariance.csv`, n=1260,
n_networks=55); first panel 42 / 1,440 (858 direct; `unit_predictions_first.csv`).

**Layout.** Two-panel schematic (A: time line; B: support-tier ladder over the
duration axis) plus legend strip (C). The duration axis in B runs 3–365 d on a log
scale with vertical shading for the interpolated band (14–60 d) and red hatching for
the extrapolated band (180–365 d).

**Caption (draft).** "Every stress test is measured inside the fitting record of the
recovery model it ranks: the outer evaluation split (70/30) and the nested
artificial-gap split (70/30) keep the second-panel outcomes (1,446 units, 57 networks:
32 US, 15 CZ, 10 NO) untouched by fitting. A five-level support hierarchy makes the
provenance of every prediction explicit — 841 exact-tier units, 874 direct-horizon
units, 596 network-mean-fallback units (24 at direct horizons) — and the continuous
duration surface extends to interpolated (14/60 d) and extrapolated (365 d) regions
that are reported separately throughout. Colors and hatching denote evidence role
(frozen pre-outcome, post-hoc v12 development, v13 harmonization, future
preregistered third panel)."

**Evidence role.** Design schematic of frozen machinery with v13 harmonization
annotations (interpolation/extrapolation regions, evidence legend).

---

## Figure 2 — Strongest-baseline external comparison (second panel, direct-support units)

**Purpose.** Primary evaluation: the empirical stress-transfer predictor versus the
strongest fair baseline — the station × horizon historical mean of fitting-period MAE
(ladder `r6_station_gap`) — on identical units, with simple descriptors as a second
comparator. Replaces v12 Fig 2 (which led with the +0.552-vs-simple network Δρ).

**Units.** Direct-support subset of the second panel: **874 units, 57 networks**
(support restriction stated in caption; fallback units excluded from the primary
panels and reported separately).

### Panel A — empirical vs station × horizon mean (primary comparator)
- Predicted vs observed recovery loss (°C), one panel with both predictors on the
  same 874 units; equal-network-weighted calibration lines (empirical slope 0.938,
  r6 slope 0.924); per-network medians as faint markers.
- Annotated numbers (from `t03_baseline_ladder/agent_a/master_ladder_table.csv`,
  rows `second,direct_874,r6_station_gap` and `second,direct_874,empirical`):
  pooled Spearman empirical **0.9453** vs r6 **0.9424**; network-level Spearman
  **0.8049** vs **0.7632**; R² 0.8132 vs 0.7893; RMSE 0.455 vs 0.484.
- Paired network-bootstrap Δρ (2,000 draws, `paired_bootstrap.csv`, row
  empirical–r6_station_gap): **+0.0417 [−0.0006, +0.1154]**; pooled Δρ
  **+0.0029 [−0.0004, +0.0068]**; fraction of positive draws 0.971 (network),
  0.959 (pooled).

### Panel B — empirical vs simple descriptors (secondary comparator)
- Same layout on the same 874 units; `r8_simple` (route-A, fitting-period):
  pooled 0.8459, network 0.2475, R² 0.6477; development-only variant 0.8323 /
  0.2769 (`t01_paired_comparison/agent_a/predictions.csv` columns
  `simple_fitperiod`, `simple_devonly`).
- Annotate the paired Δρ network +0.5522 [0.3088, 0.8135] with the explicit
  framing "baseline-weakness, not headline": the simple descriptor barely ranks
  networks at all (network ρ 0.25).

### Panel C — paired network-bootstrap Δρ forest, both baselines and difficulty controls
- Rows (comparator): `r6_station_gap` (primary), `r5_network_gap` (network ×
  horizon; identical to r6 at network level — same network means), `r8_simple`
  (secondary), `r4_network` (network historical mean). Two points per row: pooled
  Δρ and network Δρ, 95% CIs, zero reference line.
- Values (all from `t03_baseline_ladder/agent_a/paired_bootstrap.csv`,
  subset `direct_874`): vs r6: pooled +0.0029 [−0.0004, +0.0068], network +0.0417
  [−0.0006, +0.1154]; vs r5: pooled +0.0436 [0.0291, 0.0604], network +0.0417
  [−0.0006, +0.1154]; vs r8: pooled +0.0982 [0.0589, 0.1420], network +0.5522
  [0.3088, 0.8135]; vs r4: pooled +0.6682 [0.5729, 0.7588], network +0.0770
  [−0.0015, +0.1774].
- Emphasize (bold or shaded) that the primary row's network CI straddles zero;
  annotate the same-panel fallback contrast: on all 1,446 units (incl. 572
  fallback) the network Δρ vs r6 is **−0.0107 [−0.0349, +0.0076]** — the
  advantage disappears where the network-mean fallback applies (fallback artifact).

### Panel D — within-network effects (empirical vs r6)
- Distribution of per-network within-network Spearman (units within each network):
  empirical median **0.9650** (IQR 0.9441–0.9824; 57 networks), r6 median
  **0.9676** (57 networks), simple median 0.9371 (IQR 0.9091–0.9624) — from
  `t01_paired_comparison/agent_a/within_network_decomposition.csv` (subset
  `direct_874`) and `t03_baseline_ladder/agent_a/master_ladder_table.csv`
  (`within_network_spearman_median`).
- Residualized pooled Spearman (between-network signal removed): empirical 0.9359,
  r6 0.9298, simple 0.8958 (same two files).
- Beat-fraction annotation: empirical beats simple in 71.9% of 57 networks
  (`beat_fraction.csv`); the r6-vs-empirical per-network difference distribution is
  a planned v13 output (`results/revision_v13/strongest_baseline/agent_a/`).

**Sources (exact columns).** `t03_baseline_ladder/agent_a/master_ladder_table.csv`
(rows `second,direct_874,{r6_station_gap,r8_simple,empirical}`; columns
`pooled_spearman, network_spearman, calibration_slope, r2, rmse,
within_network_spearman_median, residualized_pooled_spearman`);
`.../paired_bootstrap.csv` (columns `method_a, method_b, n_units, n_networks,
delta_pooled_spearman_mean, delta_pooled_spearman_ci95, fraction_delta_pooled_positive,
delta_network_spearman_mean, delta_network_spearman_ci95,
fraction_delta_network_positive`); `.../unit_predictions_second.csv` (columns
`r6_station_gap, r8_simple, empirical, observed_recovery_loss`); `.../per_horizon_
network_spearman.csv` (horizon rows 7/30/90/180 with `r6_station_gap_network_spearman`,
`r8_simple_network_spearman`, `empirical_network_spearman`);
`t01_paired_comparison/agent_a/within_network_decomposition.csv`,
`beat_fraction.csv`, `provider_sensitivity.csv`; planned
`results/revision_v13/strongest_baseline/agent_a/` (per-network Δρ distributions and
residualized r6 curves).

**Caption (draft).** "On the same 874 direct-support units of the second panel
(57 networks), the empirical stress-transfer predictor matches or slightly exceeds
the strongest fair baseline — the station × horizon mean of fitting-period MAE —
in pooled rank (0.945 vs 0.942) and network-level rank (0.805 vs 0.763), with a
paired network Δρ of +0.042 whose 95% CI [−0.001, +0.115] straddles zero; its large
apparent advantage over simple structural descriptors (network Δρ +0.552) reflects
baseline weakness (descriptor network ρ 0.25), not model strength. Within networks,
medians are indistinguishable (0.965 vs 0.968; residualized 0.936 vs 0.930), and the
advantage vanishes on the 572 network-mean-fallback units (network Δρ −0.011
[−0.035, +0.008]). Evidence: empirical predictor frozen pre-outcome; baseline ladder
and bootstrap post-hoc v12; per-network Δρ distributions v13 harmonization."

**Evidence role.** Empirical column = frozen pre-outcome; ladder rungs and bootstrap
= post-hoc v12; per-network r6 distribution and residualization = v13 harmonization
(planned output referenced).

---

## Figure 3 — Duration response: supported, interpolated, and extrapolated regions

**Purpose.** Explain *why* methods differ and isolate the extrapolation boundary.
Separates supported (7/30/90/180 d), interpolated (14/60 d), and extrapolated
(365 d) durations so the failed extrapolation is visually flagged, never pooled.

**Units.** Second panel, 1,446 units / 57 networks by support status: 874 direct,
448 interpolated, 124 extrapolated (per-horizon n: 7/30/90/180 = 224/224/220/206;
14/60 = 224/224; 365 = 124, 30 networks).

### Panel A — predicted vs observed mean loss vs gap duration
- X: gap duration (log scale, 3–365 d); Y: mean loss (°C). Points: mean surface
  prediction and mean observed loss per horizon (predicted/observed: 7 d 0.55/0.53,
  30 d 0.79/0.86, 90 d 1.29/1.37, 180 d 2.17/2.88; interpolated 14 d 0.70/0.68,
  60 d 0.98/1.10; extrapolated 365 d 2.36/5.27) — computed from
  `t04_risk_surface/agent_a/second_panel_predictions.csv` (columns
  `surface_prediction_mae`, `observed_recovery_loss`, grouped by `gap_length`).
- Curve: the fitted monotone duration curve `duration_curve.csv`
  (`duration_effect_mae` vs `gap_days`; anchor values at 7/180/365 d: 0.633/1.595/
  2.563 from `surface_fit_summary.json` `monotone_curve`).
- Support shading: solid markers + solid curve for supported durations; hollow for
  interpolated; **red + hatching** for extrapolated, with a vertical boundary line at
  180 d annotated with the pre-specified extrapolation factor (0.218) and 90%
  interval widening (1.435×).

### Panel B — 90% interval coverage by support tier
- Bars/points: overall 92.5%, direct 96.0%, interpolated 98.2%, extrapolated
  **46.8%** (recomputed from `second_panel_predictions.csv`: `surface_lower90` /
  `surface_upper90` vs `observed_recovery_loss`; 92.5% overall, 96.1% direct,
  98.2% interpolated, 46.8% extrapolated). Nominal 90% reference line; the
  extrapolated bar in red/hatched with the failure annotated (observed 365-d losses
  run to 9.4 °C).
- Companion annotation (same panel or adjacent): surface vs old network-mean
  fallback on the 448 interpolated units (network ρ 0.768 vs 0.653, R² 0.443 vs
  −0.667) and on the 124 extrapolated units (0.270 vs 0.736, R² −3.17 vs −5.77,
  RMSE 3.309 vs 4.216) — `evaluation_second_panel.csv`; the surface's full-panel
  network ρ 0.674 vs empirical 0.715 (transfer vs within-network information trade)
  stated in the caption, not the main result.

### Panel C — abstention boundary (support-based release rule)
- Trade-off curve from `abstention_curve.csv` (rule = extrapolation-factor
  threshold): abstaining the 124 extrapolated units (8.58% of 1,446 units; **28.93%
  of total observed loss**) releases 1,322 units with network Spearman **0.691**,
  pooled 0.872, R² **0.663**, RMSE 0.535 (row `extrapolation_factor,0.217`).
- Counterexample annotation: the width-based rule is counterproductive (width cap
  2.5 ⇒ 13.1% abstained, network ρ falls to 0.489) — support-based abstention is
  the correct policy.

**Sources.** `t04_risk_surface/agent_a/` (`second_panel_predictions.csv`,
`duration_curve.csv`, `abstention_curve.csv`, `surface_fit_summary.json`,
`evaluation_second_panel.csv`, REPORT.md §5–6 for the 9.4 °C tail and widening);
`t03_baseline_ladder/agent_a/per_horizon_network_spearman.csv` (365-d row:
surface 0.2534/0.2699 r8; empirical = r6 fallback 0.7357).

**Caption (draft).** "The duration response is monotone over the fitted range but
extrapolation beyond 180 d fails: the 365-d 90% interval covers only 46.8% of units
(92.5% overall; 96.0% direct; 98.2% interpolated) and the surface's network-level
rank collapses to 0.270, so the extrapolated region is reported and flagged
separately. Abstaining the 124 extrapolated units — 8.6% of units but 28.9% of
total observed loss — restores released-unit rank (network ρ 0.691, R² 0.663),
whereas interval-width-based abstention backfires (ρ 0.489 at 13% abstained).
Evidence: surface and intervals frozen pre-outcome; abstention analysis post-hoc
v12; the three-region presentation is v13 harmonization."

**Evidence role.** Surface, intervals, extrapolation constants = frozen pre-outcome;
abstention curves and width-rule contrast = post-hoc v12; region separation and
flagged 365-d tail = v13 harmonization presentation.

---

## Figure 4 — Model-selection coverage–regret (decision figure)

**Purpose.** The decision quantity is the coverage–regret frontier, not any single
point: model-family selection on the first panel with per-unit support-abstention.
Fixed-budget triage (t09 Part 1) is reported as a negative result in the SI, not in
the main text (empirical CapturedLoss@20% 0.338 [0.302, 0.380] vs simple 0.512
[0.485, 0.537]; SI figure).

**Units.** First panel: 1,440 units, 42 networks; candidate families
seasonal-boundary ridge, donor-BLUP ridge, XGBoost-B&D (`t09_decision_utility/agent_a/
summary.json` `part2_families`). Abstention policy: abstain units that are ambiguous
(top-2 predicted loss within 10%) or have no per-unit curve support for any family
(`support_any`); coverage = 1 − fraction abstained, in units.

### Panel A — regret vs unit coverage
- X: coverage 0–100% (units released). Y: network-balanced regret on released
  units (per-network mean of per-unit regret, averaged over networks).
- Curves: proposed support-aware selector (λ = 0.5), best fixed family (dev-fit),
  global blocked CV (LOO network), per-network CV, gap-length rule, common-scale
  rule, random, oracle (regret 0 at all coverage).
- Anchored points (existing CSVs): at 100% coverage `selection_regret_table_part2.csv`
  (`net_balanced_regret`): best fixed 0.0815, global CV 0.0815, per-network CV
  0.0383, gap-length 0.0927, common-scale 0.0865, random 0.2628, proposed λ0.5
  0.0840–0.0852; at 8.5% coverage (`abstention_comparison_part2.csv`, row
  `0.5,ambiguous+support_any`): proposed 0.0067, best fixed 0.1508, global CV
  0.1508, per-network CV 0.1636, gap-length 0.1447, common-scale 0.0068, random
  0.3407. Proposed trace across the δ sweep:
  `abstention_curve_part2.csv` (`fraction_abstained` vs
  `net_balanced_regret_released`, λ=0.5, support rule `any`).
- Mark the **current operating point** (coverage 8.5%, regret 0.0067) and the
  **harmonization floors** as vertical lines: ≥50% unit coverage (hard), 70% target;
  the ≥60% network-coverage floor is shown in Panel B.
- Bootstrap 95% bands (2,000 draws over 42 networks, `bootstrap_part2.csv`):
  no-abstention proposed λ0.5 0.0852 [0.0638, 0.1050]; abstention regret 0.0067
  [0.0019, 0.0120]; per-network CV 0.0384 [0.0302, 0.0462]; best fixed 0.0815
  [0.0584, 0.1034].

### Panel B — regret vs network coverage
- X: fraction of the 42 networks with at least one released unit (coverage in
  networks); Y: same network-balanced regret. Same selectors. Vertical line at 60%
  network coverage (floor) and dashed at 70% target.
- The harmonization floors (≥50% units, ≥60% networks, 70% target) are protocol
  constraints for the future preregistered third panel; full comparator curves
  across the sweep are planned v13 outputs.

**Sources.** `t09_decision_utility/agent_a/` (`selection_regret_table_part2.csv`,
`abstention_curve_part2.csv`, `abstention_comparison_part2.csv`,
`bootstrap_part2.csv`, `selection_calibration_part2.csv`, `common_scale_c.json`);
v13 harmonization curves already computed:
`results/revision_v13/decision_harmonization/agent_a/coverage_regret_curve.csv`
(criteria: ambiguity margin / mean width / support completeness; coverage
0.1–0.9 plus 0.5/0.7; per-method released units, released networks, unit and
network coverage, network-balanced regret, pooled regret, selection accuracy,
top-2 hit, abstention cost) and `comparators_table.csv`; both agents'
implementations agree on the anchored points.

**Caption (draft).** "Selection regret collapses only at low coverage: at 8.5% unit
coverage (123 of 1,440 released units) the support-aware selector reaches 0.0067
network-balanced regret, statistically indistinguishable from the common-scale rule
(0.0068) and far below best-fixed (0.151), per-network CV (0.164), and random
(0.341); at 100% coverage it does not beat per-network CV (0.085 vs 0.038, 95% CI
[0.064, 0.105]). The coverage–regret frontier — not the single 0.0067 point — is the
decision quantity, and the preregistered floors (≥50% units, ≥60% networks, 70%
target coverage) lie far from the current operating point, so the released-unit
regret is reported as an upper-bound demonstration, not a deployable policy.
Evidence: Part-2 experiment post-hoc v12; frontier and floors v13 harmonization;
third-panel deployment future preregistered."

**Evidence role.** t09 Part 2 = post-hoc v12; curve harmonization, floors, and
operating-point framing = v13 harmonization; floors as preregistration constraints =
future preregistered third panel.

---

## Figure 5 — Downstream incremental benefit vs untreated baselines

**Purpose.** Report thermal-metric benefits honestly against three untreated
baselines — no-fill (gap days dropped), climatology (day-of-year medians from
training), and linear interpolation of gap days — because benefit reverses for
threshold metrics under climatology. Figure = incremental benefit forest plots;
full metric tables go to SI.

**Units.** t08 downstream experiment: 15 networks, 117 stations, 351 station-gaps,
1,755 placements, horizons 7/30/90 d, ≤5 placements per gap; budget experiment on
the common 270 risk-scored units (54 treated at the 20% budget; 261/53 for
amplitude). Risk score = fitting-period empirical transfer loss (°C), frozen.

### Layout — three forest panels (one per baseline) or a grouped forest
- Y: the ten thermal metrics (annual mean, summer JJA mean, amplitude Jul–Jan,
  phase, 90th percentile, summer maximum, days >20 °C, days >25 °C, degree days
  >10 °C, trend slope). X: incremental benefit **B = D(baseline) − D(model)**,
  positive = the model reduces distortion relative to that untreated baseline.
- Model bars: risk-selected top-20% budget, fixed model (gap-length rule), oracle
  (per-metric best selection); random with ±SD band. Aggregate 20% budget
  reductions vs no-fill (`t08_downstream_metrics/agent_b/budget_comparison.csv`):
  risk vs length vs random — annual mean 0.377/0.386/0.173; degree days 0.395/
  0.344/0.171; trend 0.348/0.522/0.173; days >20 °C 0.308/0.240/0.124; p90 0.307/
  0.290/0.133; summer mean 0.188/0.182/0.084; summer max 0.133/0.119/0.033; phase
  0.117/0.109/0.053; days >25 °C 0.109/0.021/0.036; amplitude 0.095/0.159/0.119.
- Oracle anchors (`t08_downstream_metrics/agent_a/budget_combined.csv`,
  `oracle_<metric>` columns; note the different 1,965-placement pool — the v13
  harmonization run recomputes oracles on the common 270-unit pool): annual mean
  0.398, phase 0.324, degree days 0.312, summer mean 0.181, trend 0.105, p90 0.041,
  amplitude 0.006; and negative oracle values for days >25 °C (−0.368) and summer
  max (−0.017) — already signaling the reversal.
- **Sign-reversal markers** (shaded bands at B = 0, red where sign flips): from
  `t08_downstream_metrics/agent_b/metric_error_summary.csv`, reconstruction vs
  climatology mean distortion — days >25 °C 0.516 vs **0.411** (recon worse),
  summer maximum 0.124 vs **0.096** (recon worse), days >20 °C 2.23 vs 2.24 and
  p90 0.141 vs 0.143 (tie); every metric is far below no-fill (recon/no-fill
  0.12–0.84).
- Annotate the risk→distortion correlation (network-level, n=15,
  `risk_correlation.csv`): strong for integrated metrics (annual mean ρ 0.764,
  degree days 0.743, phase 0.729, p90 0.668), null for amplitude (0.089) and summer
  max (0.250) — why risk-selection fails on geometry-dominated metrics.

**Sources.** `t08_downstream_metrics/agent_b/` (`budget_comparison.csv`,
`metric_error_summary.csv`, `risk_correlation.csv`, `uncomputable_no_fill.csv` —
amplitude undefined under no-fill in 20.9% of placements, 367/1,755);
`t08_downstream_metrics/agent_a/` (`budget_combined.csv`, `metric_error_tables.csv`
by horizon, `correlation_risk_distortion.csv`, `reconstruction_series.parquet`);
planned `results/revision_v13/decision_harmonization/agent_a/` (or a sibling
downstream-harmonization output): climatology- and interpolation-baseline budget
reductions, per-metric oracle on the common 270-unit pool, and the interpolation
baseline (linear gap fill) computed on `reconstruction_series.parquet` +
`daily_wide_temperature.csv`.

**Caption (draft).** "Against the no-fill status quo, recovery reduces distortion
for every thermal metric (reconstruction errors are 12–84% of no-fill errors) and
risk-selected 20% budgets beat random by 1.9–4.0× on integrated metrics (degree
days 0.395 vs 0.171; annual mean 0.377 vs 0.173); but the incremental benefit
reverses for threshold and single-event metrics when the untreated baseline is
climatology — days >25 °C (reconstruction 0.52 vs climatology 0.41) and summer
maximum (0.12 vs 0.10) — and amplitude is not rankable by any MAE-type risk score
(network ρ 0.09). Incremental claims therefore name their baseline and metric.
Evidence: downstream experiment post-hoc v12; three-baseline comparison v13
harmonization; third-panel thermal endpoints future preregistered."

**Evidence role.** Reconstruction, risk scores, distortion tables = post-hoc v12
(on frozen reconstruction); three-baseline framing, oracle-on-common-pool,
interpolation baseline = v13 harmonization (planned); thermal protection floor in
protocol v4 = future preregistered.

---

## Supporting Information (SI) list

1. **Study flow and panel composition.** Development 55 networks / 1,260 units;
   first panel 42 / 1,440 (858 direct); second panel 57 / 1,446 — **US 32 / CZ 15 /
   NO 10** (703/478/265 units) — with the outcome-disjoint audit and the corrected
   count note (v12's "35 US" is a bug). Sources: `t01/provider_sensitivity.csv`,
   `t03/unit_predictions_{first,second}.csv`, `t03/dev_supplemental_conditional_
   covariance.csv`.
2. **Full 12-rung fitting-period baseline ladder** (t03 `master_ladder_table.csv`):
   r1_global … r12_stack per panel × subset (direct vs all), with pooled and
   network Spearman, calibration, R², RMSE, within-network median, residualized
   ρ; r9 (conditional covariance → MAE) unavailable; r10 (generic blocked CV)
   strongly negative; r4 network historical mean 0.772 network ρ on the full
   second panel and r6 0.763 on the 874 as network-difficulty controls; the full
   paired-bootstrap Δρ matrix.
3. **Per-horizon tables** (t03 `per_horizon_network_spearman.csv`): 7/30/90/180 d
   supported (n = 224/224/220/206; 57/57/56/53 networks), 14/60 d interpolated,
   365 d extrapolated (124 units, 30 networks) — empirical vs r6 vs r8 vs surface
   vs stack; provider-block sensitivity (t01 `provider_sensitivity.csv`, CZ 15,
   NO 10, US 32).
4. **Support-tier tables** (t02 `tier_metrics_second.csv`, `key_decomposition.json`,
   `support_quality_terciles.csv`, `mixing_diagnostics.json`): tier counts
   (exact 841 / 57; station-gap 9 / 2; network-mean fallback 596 / 57, incl. 24
   direct-horizon fallback units), pooled/network Spearman and calibration per
   tier (exact tier pooled 0.968, network 0.887), tier gap composition, mixing
   diagnostics, first/development panel counterparts.
5. **Rolling-origin and history length** (t07): per-cutoff tables (60/70/80%),
   rank-stability across cutoffs — agent_a: Kendall W 0.917 on 14 networks
   (`rolling_origin_rank_stability.csv`); agent_b: tie-adjusted W 0.811 on 13
   networks — divergence documented with both files; honest 60%-leg attrition
   (6/20 networks infeasible); history-length learning curve (first panel reaches
   network Spearman ≥ 0.7 at ~4 years, 0.881; 2 y 0.678; 8 y ≈ full 0.965);
   training-length comparability (mean paired difference 0.013 °C, pooled
   Spearman 0.989; `agent_b/comparability_metrics.csv`).
6. **Model-family × missingness transfer matrices** (t05): full
   `matrix_network_spearman.csv` with per-cell n-networks
   (`matrix_n_networks.csv`), panel labels per cell
   (`matrix_headline.csv`: first_confirmation / second_confirmation /
   development_validation), diagonal-vs-off-diagonal test (diagonal mean 0.783,
   off-diagonal 0.434; one-sided MWU p = 0.033), neural row (−0.24 to +0.28
   cross; self 0.285), air2stream subset (n ≤ 8) and caveats, and the
   cross-instance transfer note (the XGBoost row mixes three panels; per-cell
   panel labels required). Covariance estimand → SI appendix (item 8).
7. **Missingness matrix — both implementations and divergence** (t06): agent_a
   matched diagonal (`mechanism_metrics.csv`: multi-block 0.944, donor-synchronous
   0.979, target+primary-covariate 0.881, online 0.930, uniform 0.531, summer-
   biased 0.594, high-temperature-biased 0.580) and the uniform-curve mismatch row
   (`mismatch_metrics.csv`: 0.20–0.40 for support-destroying mechanisms; slope
   collapse 0.90 → 0.14 for multi-block); agent_b implementation
   (`mechanism_metrics.csv`, `mechanism_bootstrap_intervals.csv`: donor-sync
   0.490 [−0.236, 0.925]); the **implementation divergence is documented**
   (agent_a donor-sync matched 0.979 vs agent_b 0.490; mechanism definitions and
   support matrices differ — agent_b uses 12 networks, 4 horizons, 306 station-
   gaps), with the v13 harmonization plan (single implementation, bootstrap
   intervals on the matched diagonal, both mechanisms retained).
8. **Covariance estimand appendix** (t10): code reading of
   `expected_gaussian_mae`, corrected horizon table, plug-in covariance simulation
   (downward bias at small M), incremental-value replications.
9. **Downstream metrics full tables** (t08): ten-metric error tables by horizon
   (`agent_a/metric_error_tables.csv`), network-level and placement-level
   correlations (`agent_b/risk_correlation.csv`, `agent_a/correlation_risk_
   distortion.csv`), budget tables by policy and metric (`budget_comparison.csv`,
   `budget_combined.csv`), uncomputable-placement audit (amplitude undefined in
   20.9% of placements under no-fill).
10. **Decision-utility detail** (t09): full utility tables
    (`utility_table_part1.csv`), NDCG and worst-decile recall per budget, top-20%
    set overlaps / Jaccard (`policy_overlap_part1.csv`), Part-2 per-family
    calibration (`selection_calibration_part2.csv`), common-scale robustness
    (`common_scale_c.json`), ambiguity-threshold sweep (`abstention_curve_part2.csv`),
    and the fixed-budget triage negative result (empirical CapturedLoss@20% 0.338
    [0.302, 0.380] vs simple 0.512 [0.485, 0.537]; oracle 0.529, random 0.200).
11. **Protocol v4 summary table** (t12, `protocol_v3.md` + v4 update): endpoints
    (paired network-level Δρ on direct-support units; captured loss; NDCG@5%;
    thermal protection floor), frozen margins, power analysis (80% power at
    N = 120 for the observed Δρ anchor +0.038, sd 0.121; target band 80–120;
    `power_table.csv`, `observed_effects.json`), the third-panel support floors
    (≥50% units, ≥60% networks, 70% target coverage), and external timestamping /
    preregistration requirements (`open_research_checklist.md`).
12. **Heterogeneity models (v11, demoted):** HUC2 climate and GAGES-II regulation
    effect modification with descriptive caveats; matched planted field-outage
    geometry as context for the missingness generalization.

## Planned v13 outputs referenced above (produced in parallel)

- `results/revision_v13/strongest_baseline/agent_a/` — per-network within-network
  ρ distributions and paired Δρ bootstrap for empirical vs r6 (Figures 2C–D),
  residualized r6 curves, first-panel cross-check tables.
- `results/revision_v13/decision_harmonization/agent_a/` — full coverage–regret
  curves for all selectors at unit and network coverage (Figure 4, both panels),
  floor annotations, missingness harmonization (item 7), downstream three-baseline
  budget reductions and per-metric oracle on the common 270-unit pool (Figure 5),
  interpolation-baseline computation.

All existing CSVs cited above are verbatim-verified; where a planned v13 artifact is
referenced, the figure script must consume the planned file when it lands and fall
back to the cited v12 columns otherwise, with the fallback noted in the figure
caption.
