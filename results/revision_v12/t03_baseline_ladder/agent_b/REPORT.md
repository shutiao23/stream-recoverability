# REPORT — Agent B (adversarial pair): same-unit baseline ladder for the revision

Task: `t03_baseline_ladder` — a 12-rung fitting-period-only baseline ladder with
same-unit paired comparisons on the second panel (1,446 units, 57 networks) and
the first panel (1,440 cells, 42 networks). All numbers below were produced by
`scripts/rev_v12_t03_baseline_ladder_b.py` (run with `PYTHONPATH=$PWD/src
python3`, seed 20260829, 2,000-draw network bootstrap). Outputs:
`results/revision_v12/t03_baseline_ladder/agent_b/`.

## 0. Recommendation (read first)

**The fairest, strongest non-proposed comparator for the manuscript is the
station × horizon mean of the network's own fitting record (rung 6)** — on the
direct-horizon subset where the paper's claims are made. It ties rung 5
(network × horizon) exactly at network level on both panels (0.763 / 0.798) and
strictly dominates it on pooled rank, R2, and RMSE, so it is the stronger of the
two. It also beats the route-A simple model (rung 8) at network level on every
subset (0.763 vs 0.248 on the 874; 0.726 vs 0.605 on the 1,446) and nearly ties
the empirical curve on pooled rank on the direct subset (0.9424 vs 0.9453).

Against it, the empirical curve's headline advantage is small but directionally
positive at network level on the direct subset: **paired Δρ_net =
+0.0419 [0.0001, 0.1117] (P(Δ>0) = 0.976)**; pooled Δ is ≈ 0 (+0.0029
[−0.0005, 0.0066]). Versus the simple model the empirical advantage is large
and CI-excluding: **+0.5456 [0.2988, 0.8143]** on the 874 at network level and
+0.0982 [0.0594, 0.1438] pooled.

Two qualifications the manuscript must not drop:

1. On the full 1,446-unit panel the **network historical mean (rung 4)** ranks
   networks better than the empirical curve (0.7720 vs 0.7155; paired
   Δ_emp−r4 = −0.0577 [−0.1476, 0.0066]). Rung 4 is a degenerate
   within-network constant (pure between-network difficulty), so it is a
   "network difficulty" control, not a general baseline; it should be reported
   as a separate row, and the empirical curve's own fallback (572 constant
   rows) is exactly this rung, which is why the empirical curve loses pooled
   rank on the full panel.
2. On the first panel the risk surface (rung 11) is the best rung of all
   (network 0.898, pooled 0.908, R2 0.679), so first-panel claims should
   compare against the surface, not against the simple model.

The simple route-A model (rung 8) is **not** the strongest baseline at network
level on any subset — using it as the paper's comparator understates the
baseline ladder and should be replaced by rung 6 (with rung 4 as a network-level
control).

## 1. Design

Rungs (all fitting-period-only; no evaluation-period outcomes used anywhere):

| Rung | Definition | Fit data (second panel / first panel) |
|---|---|---|
| r1 | global mean | dev+conf fit losses / dev fit losses |
| r2 | gap length only (per-gap means, log-linear interp/extrap for 14/60/365) | same |
| r3 | gap length + 2 Fourier harmonics (unweighted OLS) | same |
| r4 | network historical mean of own fitting losses | 2nd-panel networks' own fitting losses (recomputed via `fitting_period_empirical_losses`, 63,863 rows) / conf fit losses |
| r5 | network × horizon mean (fallback r4→r1) | same |
| r6 | station × horizon mean (fallback r5→r4→r1) | same |
| r7 | empirical curve (previous-period, leave-one-period-out) | frozen `second_confirmation/scoring/empirical_predictions.csv` / t04 `first_panel_predictions.csv` `old_empirical_prediction` |
| r8 | route-A simple descriptors (fit-period coefficients on recomputed features) | dev-only for first panel; dev+first for second panel |
| r9 | conditional-covariance operator model | NA on both panels (see §6) |
| r10 | generic blocked-CV mean (per-gap mean of leave-one-network-out route-A predictions) | dev+conf LONO (nested_lono + recomputed conf LONO) / dev LONO |
| r11 | risk surface | t04 stored `surface_prediction_mae` (NOT refit) |
| r12 | meta-model: OLS stack of r8 + surface via fitting-period-only regression (equal-network weights), clip ≥ 0 | dev+conf route-A cells (2,700) / dev cells (1,260); surface feature = pooled-surface fixed effects reconstructed from t04 summary JSON |

Subsets: second panel 874 direct-horizon units (gap ∈ {7,30,90,180}) and 1,446
full; first panel 858 direct-horizon cells, 780 curve-supported cells
(`old_source_cell != network_mean_fallback`, the paper's direct-supported
subset), and 1,440 full. Metrics: pooled (station-gap) Spearman; network
Spearman (network means); median within-network Spearman (networks with ≥4
units and within-network variance); R2 and RMSE (pooled); calibration
slope/intercept (equal-network-weighted OLS, paper convention).

## 2. Validation (all cross-checks reproduce the frozen/stored values)

| Check | n | pooled ρ | network ρ | slope | R2 | RMSE |
|---|---|---|---|---|---|---|
| Empirical, 2nd panel, direct 874 | 874 | 0.9453 | 0.8049 | 0.9383 | 0.8132 | 0.455 |
| Empirical, 2nd panel, full 1,446 | 1,446 | 0.7399 | 0.7155 | 0.9503 | 0.2385 | 1.320 |
| Simple route-A dev-only, 1,446 | 1,446 | 0.8191 | 0.6141 | 1.0174 | 0.7836 | 0.704 |
| Simple fit-period, 1,446 | 1,446 | 0.8346 | 0.6046 | 1.1503 | 0.7564 | 0.747 |
| Surface (t04 column), 1,446 | 1,446 | 0.8928 | 0.6744 | 1.7297 | 0.4753 | 1.096 |
| Empirical, 1st panel, supported 780 | 780 | 0.9341 | 0.9219 | 0.8636 | 0.8120 | 0.362 |

- Recomputed simple features match archived features to ≤ 1.1e−16 on all four
  columns for both panels; dev-only and fit-period coefficients match the
  stored route-A model and agent B's t02 coefficients **exactly** (max diff 0.0).
- Recomputed second-panel fitting losses reproduce the frozen network-mean
  fallback to 2.2e−16 (all 57 networks; 63,863 fitting rows).
- The pooled-surface fixed-effects reconstruction reproduces the stored
  second-panel `surface_prediction_log1p` to 6.7e−16.

## 3. Master ladder — second panel

| subset | rung | pooled ρ | network ρ | within-ρ median | R2 | RMSE | slope |
|---|---|---|---|---|---|---|---|
| 874 | r1 global mean | — | — | — | −0.08 | 1.093 | 0.69 |
| 874 | r2 gap only | 0.833 | 0.314 | 0.950 | 0.644 | 0.629 | 1.26 |
| 874 | r3 gap+season | 0.790 | 0.093 | 0.908 | 0.465 | 0.771 | 1.32 |
| 874 | r4 network mean | 0.281 | 0.727 | — | 0.044 | 1.030 | 0.78 |
| 874 | r5 network×horizon | 0.902 | 0.763 | 0.946 | 0.726 | 0.551 | 0.94 |
| 874 | r6 station×horizon | 0.942 | 0.763 | 0.968 | 0.789 | 0.484 | 0.92 |
| 874 | **r7 empirical curve** | **0.945** | **0.805** | **0.965** | **0.813** | **0.455** | **0.94** |
| 874 | r8 simple route-A | 0.846 | 0.248 | 0.937 | 0.648 | 0.625 | 1.16 |
| 874 | r10 blocked-CV mean | 0.833 | 0.048 | 0.950 | 0.647 | 0.626 | 1.25 |
| 874 | r11 risk surface | 0.898 | 0.689 | 0.951 | 0.656 | 0.618 | 1.33 |
| 874 | r12 meta stack | 0.894 | 0.646 | 0.951 | 0.747 | 0.530 | 1.02 |
| 1446 | r1 global mean | — | — | — | −0.10 | 1.585 | 0.76 |
| 1446 | r2 gap only | 0.819 | 0.548 | 0.942 | 0.669 | 0.871 | 1.45 |
| 1446 | r3 gap+season | 0.799 | 0.450 | 0.924 | 0.357 | 1.213 | 1.84 |
| 1446 | r4 network mean | 0.314 | **0.772** | — | 0.013 | 1.503 | 0.97 |
| 1446 | r5 network×horizon | 0.711 | 0.726 | 0.631 | 0.213 | 1.342 | 0.96 |
| 1446 | r6 station×horizon | 0.735 | 0.726 | 0.687 | 0.231 | 1.326 | 0.94 |
| 1446 | r7 empirical curve | 0.740 | 0.715 | 0.682 | 0.238 | 1.320 | 0.95 |
| 1446 | r8 simple route-A | 0.835 | 0.605 | 0.938 | 0.756 | 0.747 | 1.15 |
| 1446 | r10 blocked-CV mean | 0.819 | 0.586 | 0.942 | 0.760 | 0.741 | 1.17 |
| 1446 | r11 risk surface | 0.893 | 0.674 | 0.940 | 0.475 | 1.096 | 1.73 |
| 1446 | r12 meta stack | 0.892 | 0.750 | 0.950 | **0.778** | 0.713 | 1.15 |
| 1446 | r12 LONO-stack (sens.) | 0.894 | 0.755 | — | 0.760 | 0.741 | — |

## 4. Master ladder — first panel (42 networks)

| subset | rung | pooled ρ | network ρ | within-ρ median | R2 | RMSE | slope |
|---|---|---|---|---|---|---|---|
| 858 | r2 gap only | 0.778 | 0.316 | 0.908 | 0.535 | 0.605 | 0.90 |
| 858 | r3 gap+season | 0.764 | 0.218 | 0.879 | 0.449 | 0.658 | 1.05 |
| 858 | r4 network mean | 0.291 | 0.748 | — | 0.029 | 0.874 | 0.64 |
| 858 | r5 network×horizon | 0.762 | 0.798 | 0.889 | 0.483 | 0.638 | 0.83 |
| 858 | r6 station×horizon | 0.825 | 0.798 | 0.951 | 0.561 | 0.588 | 0.84 |
| 858 | r7 empirical curve | 0.825 | 0.801 | 0.959 | 0.559 | 0.589 | 0.83 |
| 858 | r8 simple route-A | 0.792 | 0.485 | 0.906 | 0.520 | 0.615 | 0.90 |
| 858 | r10 blocked-CV mean | 0.778 | 0.002 | 0.908 | 0.585 | 0.572 | 1.01 |
| 858 | r11 risk surface | **0.910** | **0.870** | 0.960 | **0.746** | **0.447** | 1.23 |
| 858 | r12 meta stack | 0.818 | 0.680 | 0.923 | 0.467 | 0.648 | 0.79 |
| 780 | r7 empirical curve | 0.934 | 0.922 | 0.959 | 0.812 | 0.362 | 0.86 |
| 780 | r6 station×horizon | 0.934 | 0.912 | — | 0.815 | 0.360 | 0.84 |
| 780 | r11 risk surface | 0.922 | 0.923 | — | 0.829 | 0.346 | 1.21 |
| 1440 | r4 network mean | 0.290 | 0.724 | — | −0.01 | 1.259 | 0.71 |
| 1440 | r5 network×horizon | 0.593 | 0.779 | 0.597 | 0.122 | 1.172 | 0.83 |
| 1440 | r6 station×horizon | 0.633 | 0.779 | 0.645 | 0.145 | 1.156 | 0.84 |
| 1440 | r7 empirical curve | 0.633 | 0.767 | 0.646 | 0.145 | 1.156 | 0.83 |
| 1440 | r8 simple route-A | 0.803 | 0.563 | 0.896 | 0.603 | 0.788 | 0.81 |
| 1440 | r10 blocked-CV mean | 0.783 | 0.386 | 0.896 | 0.664 | 0.725 | 0.87 |
| 1440 | r11 risk surface | **0.908** | **0.898** | 0.955 | **0.679** | **0.708** | 1.56 |
| 1440 | r12 meta stack | 0.828 | 0.692 | 0.907 | 0.560 | 0.829 | 0.76 |

(The first-panel surface is the confirmation-only refit from t04; the r12
surface feature is the pooled surface applied out-of-sample — see §6.)

## 5. Headline paired DeltaRho (network-level, 2,000-network bootstrap, same draws)

vs the strongest non-proposed baseline (r5/r6 tied on direct subsets; r4
network mean on the full 1,446; `paired_delta_vs_strongest_baseline.csv`,
`paired_delta_vs_r6_station_x_horizon.csv`, `paired_delta_vs_r8_simple_routeA.csv`):

| panel | subset | rung | baseline | Δ network ρ [95% CI] | P(Δ>0) | Δ pooled ρ [95% CI] |
|---|---|---|---|---|---|---|
| second | 874 | r7 empirical | r4 net mean | +0.0767 [−0.0019, 0.1770] | 0.973 | +0.6690 [0.5742, 0.7572] |
| second | 874 | r7 empirical | **r6 st×hor** | **+0.0419 [0.0001, 0.1117]** | **0.976** | +0.0029 [−0.0005, 0.0066] |
| second | 874 | r7 empirical | r8 simple | +0.5456 [0.2988, 0.8143] | 1.000 | +0.0982 [0.0594, 0.1438] |
| second | 874 | r11 surface | r6 st×hor | −0.0744 [−0.2857, 0.1069] | 0.217 | −0.0437 [−0.0938, −0.0024] |
| second | 874 | r12 meta | r6 st×hor | −0.1106 [−0.3641, 0.0991] | 0.179 | −0.0475 [−0.0917, −0.0090] |
| second | 1446 | r7 empirical | r4 net mean | −0.0577 [−0.1476, 0.0066] | 0.047 | +0.4292 [0.3736, 0.4865] |
| second | 1446 | r7 empirical | r6 st×hor | −0.0105 [−0.0345, 0.0074] | 0.132 | +0.0046 [0.0013, 0.0088] |
| second | 1446 | r7 empirical | r8 simple | +0.1125 [−0.1208, 0.3576] | 0.825 | −0.0958 [−0.1601, −0.0295] |
| second | 1446 | r11 surface | r6 st×hor | −0.0518 [−0.2421, 0.1185] | 0.291 | +0.1587 [0.0900, 0.2159] |
| second | 1446 | r12 meta | r6 st×hor | +0.0220 [−0.2200, 0.2551] | 0.581 | +0.1578 [0.0959, 0.2127] |
| second | 1446 | r12 meta | r8 simple | **+0.1461 [0.0635, 0.2591]** | 0.9995 | +0.0565 [0.0390, 0.0755] |
| first | 1440 | r11 surface | r5/r6 st×hor | +0.1203 [0.0243, 0.2524] | 0.994 | +0.3159 [0.2182, 0.4262] |
| first | 1440 | r11 surface | r7 empirical | +0.1356 [0.0265, 0.2814] | 0.993 | +0.2754 [0.1787, 0.3903] |
| first | 780 | r7 empirical | r5/r6 st×hor | +0.0107 [−0.0075, 0.0325] | 0.883 | +0.0600 [0.0342, 0.0901] |

Also paired vs the empirical curve rung (`paired_delta_vs_empirical_curve.csv`):
on the second-panel 874, **no rung beats r7 at network level** (nearest: r6
−0.0409 [−0.1123, 0.0007]); on the full 1,446, r4 (+0.0571 [−0.0070, 0.1429])
and r5/r6 (+0.011) are ahead at network level and r11/r12 beat r7 on pooled
rank (+0.1553 [0.0907, 0.2123] / +0.1543 [0.0939, 0.2127]). On the first panel
r11 beats r7 everywhere (Δ network +0.136 on 1,440; on the 780 supported cells
they are tied: +0.0019 [−0.0322, 0.0426]).

Within-network beat fractions (`within_network_beat_fraction.csv`): 874 direct:
r7 beats r11 in 71.9% and r12 in 64.9% of networks; 1,446 full: r11 and r12
beat r7 in 96.5%/98.2% of networks (r7's fallback is constant within network);
first panel 1,440: r11 and r12 beat r7 in 100% of networks, r7 beats r5/r6 in
76.2% of networks on the full panel and 73.8% on the 780 supported subset.

## 6. Residualization controls

(i) **Per-horizon network Spearman** (`per_horizon_network_spearman.csv`);
second panel highlights (r6, r7, r11, r12):

| horizon | r6 | r7 | r11 | r12 |
|---|---|---|---|---|
| 7 | 0.938 | 0.932 | 0.693 | 0.758 |
| 14 | 0.545* | 0.545* | 0.734 | 0.733 |
| 30 | 0.915 | 0.916 | 0.771 | 0.659 |
| 60 | 0.698* | 0.698* | 0.742 | 0.641 |
| 90 | 0.843 | 0.865 | 0.714 | 0.604 |
| 180 | 0.603 | 0.659 | 0.465 | 0.483 |
| 365 | 0.736* | 0.736* | 0.270 | 0.283 |

(* = network-mean fallback, identical for r5/r6/r7 at that horizon.) The
empirical curve's advantage over r6 lives at 90 and 180 days; r6 is marginally
ahead at 7 days (0.938 vs 0.932). The surface is strongest at the interpolated
horizons (first panel 14 d 0.852, 60 d 0.807).

(ii) **Residualized pooled Spearman** (network means removed;
`residualized_pooled_spearman.csv`): second panel 874 — r7 0.936 (max), r6
0.930, r12 0.912, r8 0.896, r11 0.903; second panel 1,446 — r12 0.912, r10
0.911, r8 0.908, r11 0.876, r7 0.607 (fallback artifact); first panel 1,440 —
r11 0.910 (max), r12 0.875, r8 0.862, r6 0.513, r7 0.504.

(iii) **Amplitude-normalized MAE** (`amplitude_normalized_mae.csv`): second
panel, first 15 networks with panels (all chmi, 478 units; temperature SD/IQR
computed from the daily QC panels restricted to each station's training years)
— normalized RMSE (IQR / SD): r10 0.071 / 0.132, r8 0.075 / 0.139, r12 0.073 /
0.134, r6 0.149 / 0.276, r7 0.149 / 0.276, r11 0.122 / 0.225. On this small
chmi-only block the empirical curve's rank advantage does not translate into
amplitude-normalized magnitude (its slope is 0.94 and errors scale with
thermal amplitude); magnitude-normalized comparisons should use the first
panel's climatology normalization instead. First panel (219 stations,
climatology_mae from the same daily panels, training years): r11 0.697 (best),
r10 1.148, r3 1.146, r6 1.201, r7 1.202, r1 1.320.

## 7. Findings

1. **The baseline ladder is steep below the direct-horizon empirical curve**:
   gap-only (r2) and gap+season (r3) lose to r6/r7 at network level by
   0.45–0.71 on the 874; the simple model (r8) is mid-ladder (network 0.248 on
   the 874 — below even gap-only) and is not the strongest baseline anywhere.
2. **r6 (station × horizon mean) is the strongest non-proposed baseline on the
   direct subset** and nearly matches the empirical curve (pooled 0.942 vs
   0.945; network 0.763 vs 0.805). The empirical advantage is concentrated at
   network level (Δ +0.042, CI just excluding 0) and at 90/180-day horizons;
   at 7 days r6 is marginally better. This is the honest statement of how much
   the empirical curve adds over a station's own fitting-period history.
3. **On the full panel, pure network difficulty (r4, network mean) is the best
   network ranker (0.772)**, slightly ahead of the empirical curve (paired Δ
   −0.058, CI [−0.148, +0.007]); the empirical curve's network-mean fallback
   makes this comparison in-sample for r4's construction (its fallback IS r4),
   so it is a control, not a competitor. r12 (meta) is the only rung that
   combines full-panel network ρ ≈ 0.75 with top pooled ρ (0.892) and the best
   R2 (0.778); its network-level Δ vs r8 excludes zero (+0.146 [0.063, 0.259])
   and its pooled Δ vs r6 excludes zero (+0.158 [0.096, 0.213]).
4. **First panel: the surface (r11) is the strongest rung of the ladder**
   (network 0.898, pooled 0.908, R2 0.679; vs r5/r6 +0.120 [0.024, 0.252]),
   consistent with t04 — on the panel where it was refit from the same
   confirmation fit losses. The meta stack (r12) is weaker here (0.692) because
   it stacks the pooled surface (transfer) rather than the confirmation-refit
   surface.
5. **Rung 9 (conditional-covariance operator model) is unavailable for both
   panels**: `complete_operator_predictions.csv` covers only the 55 development
   networks (zero overlap with the 42 first-panel or 57 second-panel networks).
   Marked NA in the ladder. Dev-panel sanity (1,260 units): pooled 0.458,
   network 0.335, R2 −0.37, RMSE 1.35 — weak even in-sample; the manuscript's
   covariance criticism is not contradicted.
6. **LONO sensitivity**: the meta stack with leave-one-network-out simple
   predictions in the regression (r12_lono) gives nearly identical full-panel
   metrics (network 0.755, pooled 0.894, R2 0.760 vs 0.750/0.892/0.778), so the
   in-sample stacker is not materially overfit.

## 8. Caveats

- Rung 4's network-level ρ is computed against the same network means its
  fallback defines (in-sample for the empirical curve's 572 fallback units);
  treat it as a difficulty control.
- The empirical curve cell values (r7) are the frozen artifact
  (`second_confirmation/scoring/empirical_predictions.csv`); per-cell
  season-curve reconstruction from a fresh refit of the fitting losses
  disagreed with the frozen curve for some direct cells (season-assignment
  sensitivity), while the fitting-loss rows themselves are reproduced exactly
  (network-mean fallback matches to 2e−16). Rungs 4–6 therefore use the
  recomputed fitting rows; r7 uses the frozen file.
- r12's surface feature is the fixed-effects-only pooled surface; the 2nd
  Fourier harmonic for the dev/conf regression cells is derived from the
  stored 1st-harmonic cell means (exact for single placements, approximate for
  multi-placement cells); second-panel application uses the exact stored
  per-cell Fourier means (validation 6.7e−16). First-panel r12 uses the pooled
  surface (transfer), not t04's confirmation-refit surface, which is why
  r11 > r12 there.
- Amplitude normalization uses the first 15 second-panel networks with panels
  (all chmi; 478 units) — a provider-block convenience sample, not a random
  subset; treat its ranking as descriptive.
- Bootstrap CIs cover resampling of networks only (frozen/fitting-period
  models); rung 4's within-network and pooled metrics are undefined (constant
  predictions) and shown as NaN.

## 9. Artifacts (all under `results/revision_v12/t03_baseline_ladder/agent_b/`)

- `ladder_metrics_second_panel.csv`, `ladder_metrics_first_panel.csv` — full
  rung × subset tables (12 rungs + LONO-stack sensitivity).
- `predictions_second_panel.csv`, `predictions_first_panel.csv` — per-unit
  predictions for every rung.
- `paired_delta_point_matrix.csv` — all rung-pair point Δ (network ρ).
- `paired_delta_vs_strongest_baseline.csv`, `paired_delta_vs_r6_station_x_horizon.csv`,
  `paired_delta_vs_r8_simple_routeA.csv`, `paired_delta_vs_empirical_curve.csv`
  — paired bootstrap Δ with 95% CIs and P(Δ>0), network and pooled levels.
- `within_network_beat_fraction.csv`, `per_horizon_network_spearman.csv`,
  `residualized_pooled_spearman.csv`, `amplitude_normalized_mae.csv`,
  `crosschecks.csv`, `summary.json`.
- `intermediate/` — recomputed second-panel fitting losses, simple features,
  LONO predictions, acf_gap cache (all regenerable by the script).
- Script: `scripts/rev_v12_t03_baseline_ladder_b.py` (runtime ≈ 5 min with
  warm caches; ≈ 8 min cold).
