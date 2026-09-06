# Figure plan v14 — round-3 revision (2026-09-04, six-duration grid)

Supersedes the round-1 figure plan (figures were numbered per PLAN §8.4; the
argument order below matches WORKPLAN_v14.md §4 and the manuscript's Results
order). Figures are drawn to `results/v14/figures_v3/` by
`scripts/153_run_v14_figures_r3.py`; every annotation is asserted in-script
against the named CSV. Round-2 review changes incorporated: Fig 1 is the
three-family robustness visualisation plus the duration structure (it carries
the headline and the robustness function at once); the ~60-d flip band is
replaced by the MAE-scale crossing with its bootstrap CI band and the
Johnson (2021) m_max = 49 d reference inside the downstream 39–60-d window;
Fig 3 carries the sign-flipped legacy predictor (−risk) as a comparator row.

**v15/W3 addition (2026-09-05, WORKPLAN_v15.md Step 3.1/3.2): the figure set
is final.** The assembled set lives in `results/v15/figures/` (drawn by
`scripts/154_run_v15_fig1_mechanism.py` and `scripts/157_run_v15_figures_w3.py`;
every annotation asserted in-script; `FIGURE_NOTES_v15.md` lists the data
sources):

- Fig 1 — the mechanism (two error curves, one crossing, station scatter);
- Fig 2 — duration structure of benefit (Table 2) + three-family robustness
  (Table 7) [renumbers round-3 fig01];
- Fig 3 — regime structure: the inverted-U advantage (Table 3a) and the
  signal migration between the two terms;
- Fig 4 — main ranking result [renumbers round-3 fig03];
- Fig 5 — decision layer: B = 0.20 bars incl. default_difficulty / −risk /
  oracle / random, budget sweeps with network-cluster CIs at 90/180 d
  (`results/v15/budget_full/`), EC(ξ)/δ curves [extends round-3 fig04];
- Fig 6 — boundaries: three-level decomposition, drift null, support-tier
  composition [extends round-3 fig06].

The round-3 estimator-contrast and downstream-flip figures move to the
Supporting Information (SI-Fig 1/2); the downstream Table 6 remains in the
main text. The previous round-3 PNGs stay in `results/v14/figures_v3/` as
the archived record.

## Figure 1 (v15, final) — The benefit law: two error curves, one crossing, and its station-level prediction

- (a) Second panel: climatology MAE (nearly flat, 1.440 → 1.376 °C, −4%,
  7 → 365 d) and deployment model MAE (0.534 → 5.234 °C, 9.8×), log-x; the
  crossing where the model's expected error meets the station's own
  climatological error, annotated with the canonical MAE-scale crossing
  91 d [85–95] (`p4_flip_analysis/mae_crossing_ci.csv`); left of the
  crossing shaded "reconstruct (expected gain)", right "use the default
  (expected harm)".
- (b) First panel: the same flat climatology threshold line with the three
  model-family error curves (`p1_baselines/family_benefit_table.csv`,
  model MAE = clim MAE − benefit) crossing it at different grid intervals —
  seasonal_boundary_ridge in 60–90 d, deployment and donor ridge in 90–180 d —
  the "same threshold line, different model curves" reading of Table 7.
- (c)/(d) Station-level test of the law, one panel each
  (`p5_mechanism/station_crossings.csv`): x = the station's own climatology
  MAE, y = log10 crossing day, fit line, and Spearman ρ = +0.411 (second,
  210 stations, p = 6e−10) / +0.243 (first, 188 stations, p = 8e−4).
- Required caption statements: benefit is over calendar-day climatology fill;
  the two panels share no network; the crossing is the law's prediction
  (B < 0 ⇔ MAE_model > MAE_climatology), not an empirical coincidence.

Shared conventions:

- Independent unit = river network; all CIs are 95% network-cluster bootstrap
  (2,000 draws, seed 20260903).
- Per-duration panels are never pooled across durations; pooled rows are
  dashed, greyed, and labeled "diagnostic only" when they appear.
- Harmful-rate axes: % harmful (benefit < 0). Budget panels pair mean benefit
  with harmful rate.
- Colors by duration: 7/14/30/60/90/180 d; provider symbols at network level.
- Evidence labels printed per claims_v14.md ("second panel, internally frozen —
  not externally verifiable preregistration" for P0 rows).

## Figure 2 (final) — Duration structure of benefit over climatology fill + three-family robustness

- (a) Unit-mean realized benefit over the climatology default by gap duration
  (log-x), both panels, with network-cluster CIs; zero line; MAE-scale zero
  crossing markers and CI bands per panel (`results/v14/p4_flip_analysis/
  flip_table.csv` mae_reference rows and `mae_crossing_ci.csv`); Johnson et al.
  (2021) m_max = 49 d reference line (inside the downstream 39–60-d window).
- (b) Three-family benefit curves (first panel): deployment xgboost_b_d,
  donor_blup_ridge, seasonal_boundary_ridge vs the climatology default on the
  identical 28,728-placement geometry (`p1_baselines/family_benefit_table.csv`),
  all reproducing the sign flip.
- Required caption statements: benefit is over calendar-day climatology fill;
  60 d is now a directly fitted duration; crossing values 105 d [98–114] first /
  91 d [85–95] second (MAE scale); the withdrawn "~60 d" figure never appears.

## Figure 3 (final) — Regime structure: the confirmed inverted U and the signal migration

- (a) The differential curve's placement-level Spearman advantage over the
  better single-term shortcut (default_difficulty at short gaps, −risk at
  long gaps) vs duration, both panels (`p5_mechanism/regime_structure.csv`
  `diff_advantage`), peak annotated at 90 d (+0.179 second / +0.143 first) —
  the inverted U of Table 3a, asserted in-script.
- (b) Per-duration placement-level ρ of diff / −risk / default_difficulty
  (second panel) with the transition zone shaded — the ranking information
  migrates between the clim term and the model term as the duration changes.
- Required caption statement: the shape is the design principle's prediction
  (small at both ends, peak in the transition zone), not an optimization
  artifact.

## SI-Figure 1 (was round-3 Fig 2) — Estimator contrast

Two scatter panels (second panel, direct placements, colored by duration):
(a) x = v13 risk prediction, y = realized benefit — downward/absent structure;
(b) x = differential benefit prediction — upward structure. Per-duration
placement-level Spearman annotated from `p0_differential/metrics_by_horizon.csv`
(diff, with CI; risk).

## Figure 4 (final) — Main result: ranking strength and paired deltas

- (a) Per-duration placement-level ρ (second panel) for diff / −risk / r6-diff /
  risk, with the season-LOO ceiling line (`season_loo_upper.csv`) and the
  0.25–0.35 partial band marked; diff values annotated.
- (b) Paired network-cluster deltas with 95% CIs: diff − r6-diff
  (`paired_diff_vs_r6.csv`) and diff − (−risk) (`paired_diff_vs_negrisk.csv`).
- Required caption statement: 10 of 12 paired cells exclude zero (all six
  second-panel cells); crossing cells are first-panel 60 d and 90 d; the
  irreplaceable range is the positive-benefit regime 7–60 d.

## Figure 5 (final) — Decision layer with oracle/random brackets

- (a) Within-duration top-20% budgets (second panel): mean realized benefit of
  the treated set for diff / duration-only / r6-diff / risk with harmful-rate
  labels per duration (`p0_differential/budget_within_duration.csv`).
- (b) Continuous cost–loss EC(ξ)/δ curves (second panel; `p2_decision/
  laio_tamea_curves.csv`): ξ<0.5 realistic region highlighted, reference line
  at 1, 60/90-d bounded excursions annotated (1.038 at ξ=0.45; 1.033 at ξ=0.55).

## SI-Figure 2 (was round-3 Fig 5) — Downstream flips

Per-panel rows (metric × flip day, log-x) of the climatology-default crossings
(`p4_flip_analysis/flip_table.csv` crossing rows), with the MAE-scale crossing
line and the 39–60-d family-median window shaded.

## Figure 6 (final) — Boundaries

- (a) Three-level decomposition (second panel, pooled direct): between-network /
  within-network-across-duration / per-network-mean ρ for diff vs duration-only
  (`three_level_decomposition.csv`).
- (b) Stationarity null: T2 (placement) and T3 (network) drift-stratum
  contrasts with CIs (`p3_drift/direction_test.json`).

## Verification checklist (run before submission)

1. Every panel number traces to the CSV named in this plan (asserted in-script).
2. Gating lines (ρ = 0.35, EC/δ = 1) drawn only where protocol v5 defines them.
3. Visual QC by a human of `results/v14/figures_v3/` (pending; programmatic
   audits + annotation asserts pass).
4. Citation keys used on panels exist in `paper/references.bib`.
