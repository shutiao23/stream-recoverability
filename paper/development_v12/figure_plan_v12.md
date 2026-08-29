# Figure plan v12: five main figures and supporting displays

All revision analysis figures are produced under
`results/revision_v12/<task>/<agent>/`; the manuscript regenerates or
references them as listed. Colors distinguish domain and support tier, never
dozens of individual networks. Captions lead with the scientific result and
state the panel (development / first / second), the unit count, and any
support restriction.

## Figure 1 — Nested temporal design and support tiers

Schematic of the model-conditional design: outer chronological split (70%
fitting / 30% evaluation), nested split inside the fitting years (70% fit /
30% artificial-gap truth), the four stress-test durations (7, 30, 90, 180 d)
with seasonal placement strata, and the five-level support hierarchy
(exact station x duration x season; station-duration; network-duration;
network-mean fallback; unavailable), plus the interpolation (14, 60 d) and
extrapolation (365 d) regions of the continuous surface. Caption: "Historical
block stress tests are measured inside the fitting record of the same
recovery model they rank; support tiers make the provenance of every
prediction explicit."

## Figure 2 — Same-unit paired external validation (second panel)

Two-panel figure. Left: observed versus predicted loss on the same 874
direct-support units, empirical predictor versus simple descriptors
(fitting-period fit), with equal-network calibration lines and per-network
medians; both rank metrics and slopes printed. Right: paired 2,000-network
bootstrap distributions of DeltaRho (empirical minus simple) at the
network and station-gap levels, with 95% CIs (+0.552 [0.309, 0.814];
+0.098 [0.059, 0.142]) and the full-panel diagnostics inset (+0.109
[-0.126, 0.356] network; -0.095 [-0.158, -0.028] station-gap) labeled as
fallback-artifact. Caption: "On the same units, the stress test ranks
future loss better at directly supported horizons; the advantage
disappears where the network-mean fallback applies."

Sources: `t01_paired_comparison/agent_a/` (predictions.csv,
paired_bootstrap.csv, beat_fraction.csv, per_horizon_network_spearman.csv).

## Figure 3 — Why methods differ: duration response

Common-axis plot of mean realized loss versus gap duration (7-365 d) with
the simple-descriptor response, the continuous surface's monotone duration
curve (with 14/60-d interpolation and 365-d extrapolation flagged), and the
expected-Gaussian-MAE bound from the corrected covariance estimand
(flat 0.379-0.451 C while realized MAE runs 0.544-4.719 C). A secondary
panel shows the 365-d tail: 90% interval coverage 46.8% overall 92.5%, and
the abstention trade-off (8.6% of units, 28.9% of total loss; released-unit
network Spearman 0.691, R2 0.663). Caption: "The Gaussian bound saturates,
simple descriptors compress, the surface interpolates the unsupported
durations, and extrapolation beyond 180 days fails."

Sources: `t10_covariance_fix/agent_a/mechanism_horizon_corrected.csv`,
`t04_risk_surface/agent_a/` (duration_curve.csv, abstention_curve.csv,
surface_fit_summary.json).

## Figure 4 — Model-family x missingness transfer matrices

Left: source-model x target-model network-level Spearman matrix (rows =
fitting-period stress source; columns = outer-evaluation loss target;
engineered block rows 1-4, BiLSTM row, air2stream row), diagonal versus
off-diagonal annotation (one-sided MWU p = 0.033), neural row highlighted
(-0.24 to +0.28 cross, 0.29-0.69 self). Right: missingness-mechanism
matrix, matched diagonal (multi-block 0.944, donor-synchronous 0.979,
target+primary-covariate 0.881, online 0.930, uniform 0.531-0.622,
summer-biased 0.594, high-temperature-biased 0.580) and the uniform-curve
mismatch row (0.20-0.40 for support-destroying mechanisms; slope collapse
0.90->0.14 for multi-block). Caption: "Recoverability difficulty is shared
within the engineered-regression block and within a matched missingness
mechanism, but not across architecture families or mechanisms."

Sources: `t05_model_matrix/agent_a/matrix_network_spearman.csv` (+
matrix_n_networks.csv, diagonal_vs_offdiagonal.json),
`t06_missingness_matrix/agent_a/` (mechanism_metrics.csv,
mismatch_metrics.csv, support_matrix.csv).

## Figure 5 — End-to-end decision utility

Three panels. (a) Budget curves: CapturedLoss@B for B = 5/10/20/30% across
policies (simple 0.512@20%, duration+season 0.504, surface 0.500, gap
length 0.498, empirical 0.338, random 0.200, oracle 0.529) with bootstrap
bands; (b) model-selection regret: proposed selector versus comparators
with and without abstention (released-unit regret 0.0067 vs best fixed
0.151 / per-network CV 0.164 / random 0.341; no-abstention 0.084 vs 0.081);
(c) abstention coverage-risk curves for Part 1 (extrapolated-flag rule:
8.6% of units, 28.9% of loss) and Part 2 (ambiguity x support-any rule:
91.5% abstained, released regret 0.0067), plus the downstream-metric
budget inset (degree days 39.5% risk vs 34.4% length vs 17.1% random).
Caption: "Decision value is conditional: the frozen empirical predictor is
the worst non-random triage policy; selection gains and point-release
abstention require per-unit model-specific support."

Sources: `t09_decision_utility/agent_a/` (utility_table_part1.csv,
bootstrap_part1.csv, abstention_curve_part1.csv,
selection_regret_table_part2.csv, bootstrap_part2.csv,
abstention_curve_part2.csv, abstention_comparison_part2.csv),
`t08_downstream_metrics/agent_b/budget_comparison.csv`.

## Supporting Information displays (SI)

- Study-phase flow and panel composition (development 55 networks / 1,260
  units; first 42 / 1,440; second 57 / 1,446; outcome-disjoint audit).
- Same-unit per-horizon table (7/30/90/180 d: n, networks, empirical vs
  simple Spearman) and provider-block sensitivity (CZ 15, NO 10, US 32).
- Support-tier tables for all three panels (t02): tier counts, network and
  pooled Spearman, calibration, support-quality terciles, mixing
  diagnostics; corrected 596-unit fallback count and the 24 direct-horizon
  fallback units.
- Twelve-rung fitting-period baseline ladder (t03): rung 6 (station x
  horizon mean, network 0.763 on the 874; paired Delta +0.042
  [0.000, 0.112]) and rung 4 (network historical mean, 0.772 on the full
  panel) as network-difficulty controls.
- Risk-surface diagnostics (t04): variance components (sigma_e 0.232/69%,
  sigma_network 0.109/15%, sigma_station 0.109/15%), fitted duration
  curve, covariate effects, lambda tuning, extrapolation widening,
  abstention curves, first-panel cross-check.
- Rolling-origin results (t07): per-cutoff tables, 60%-leg attrition to 13
  networks, Kendall W 0.811; history-length learning curve (2-8 years and
  full; ~4-year minimum); training-length comparability (paired diff
  0.013 C, Spearman 0.989).
- Model matrix detail (t05): all per-panel cells, calibration slopes,
  station-gap-level matrix, n-networks matrix, neural convergence curves
  (median best epoch 68, 28% epoch-cap), air2stream subset and caveats.
- Missingness matrix detail (t06): mechanism definitions and support matrix,
  per-mechanism unit counts and fallback shares, mismatch tables, the
  skipped drought/low-flow mechanism.
- Downstream metrics (t08): full ten-metric error tables by horizon,
  network-level and placement-level correlations, budget tables by policy
  and metric, uncomputable-placement audit (amplitude undefined in 20.9%).
- Decision-utility detail (t09): full utility tables, worst-decile recall,
  NDCG, top-20% set overlaps (Jaccard), Part-2 per-family calibration,
  common-scale robustness, ambiguity threshold sweep.
- Covariance estimand appendix (t10): code reading of
  `expected_gaussian_mae`, corrected horizon table, plug-in covariance
  simulation (downward bias at small M), incremental-value replications.
- Heterogeneity models (from v11, demoted to SI): HUC2 climate and
  GAGES-II regulation effect modification, with the maritime interaction
  and descriptive caveats.
- Matched planted field-outage geometry (v11 result, retained as SI
  context for the missingness-matrix generalization).
- Protocol v3 summary table: endpoints, frozen margins, power analysis
  (80% at N = 120 for primary DeltaRho +0.038; anchors for captured loss,
  NDCG@5%, thermal protection floor), external timestamping requirements.
