# P4 — Cross-panel flip analysis: downstream vs MAE-scale benefit

Namespace `results/v14/p4_flip_analysis/`. Inputs: the two P4 downstream panels (`results/v14/p4_downstream/`, `results/v14/p4_downstream_second/`) and the P0 MAE-scale tables (`results/v14/p0_differential/unit_predictions_{first,second}.csv`). Machine-readable rows: `ci_tables.csv`, `flip_table.csv`.

## 1. Conventions

- **Unit of analysis:** station-gap units (network, station, gap_length). Downstream unit errors are means over the sampled placements of each P4 panel on the default support (recon/clim/linear errors all defined) — the exact pools of each panel's metric_error_summary. MAE-scale unit benefits are the P0 realized_benefit (climatology MAE − recon MAE over the full archived placements of the unit); all units at the horizon are used (7/30/90/180-day units are all direct; the 365-day units have realized benefits but no direct support — “direct + 365”).
- **Benefit over a default:** err_default − err_recon per unit (distortion reduction; positive = reconstruction reduces distortion). Harmful share = fraction of units with benefit < 0. Climatology default = day-of-year medians of the outer training years; linear default = interpolation between the two flanking observed days (the model's own boundary feature).
- **CIs:** 2000-draw network-cluster bootstrap, seed 20260903: networks resampled with replacement; each draw statistic is the mean over the units of the drawn networks (a network drawn k times contributes its units k times). Benefit draws are paired within each resample (mean_clim_draw − mean_recon_draw).
- **Network-level correlations:** the P0 convention (scripts/142_p0_derived_metrics.py): per-network means of the two quantities over the horizon's units, then Spearman across networks; the CI resamples the network-level (x, y) pairs with replacement.
- **Crossing days:** piecewise-linear interpolation of the benefit-vs-horizon curve in **log10(gap)** between the sampled horizons 7/30/90/180/365. Log-gap interpolation is chosen because the design points are log-uniform (ratio ≈ 3) and benefit decays roughly linearly in log duration while being strongly nonlinear in days (most change happens below ~120 days); plain linear-in-days interpolation would smear the curvature across the 180–365 interval. “Flip” = first positive-to-negative crossing; later recoveries (negative-to-positive) are listed in the notes.
- **Metric families (Q3):** integral-type (record-level means/quantiles/accumulated/slope): annual_mean, summer_mean, p90, cdd10, trend_slope. Threshold/peak-type (extreme days, seasonal peak, annual range, peak timing): exceed_days_20, exceed_days_25, summer_max, amplitude, phase_doy. This mirrors the grouping used in the first-panel REPORT (its “integrated, no-fill-insensitive” metrics versus distortion set by a few days inside the gap) and the v13 finding that risk scores rank integral-type distortion 0.74–0.76 but amplitude only 0.089.

## 2. MAE-scale reference (P0 realized benefit over climatology)

| panel | horizon | n units | n networks | mean benefit (degC) | 95% CI | harmful share |
|---|---|---|---|---|---|---|
| first | 7 d | 219 | 42 | +0.979 | [+0.876, +1.078] | 0.0% |
| first | 14 d | 219 | 42 | +0.848 | [+0.766, +0.930] | 0.0% |
| first | 30 d | 219 | 42 | +0.684 | [+0.618, +0.753] | 0.0% |
| first | 60 d | 219 | 42 | +0.479 | [+0.403, +0.547] | 5.9% |
| first | 90 d | 219 | 42 | +0.260 | [+0.157, +0.357] | 27.4% |
| first | 180 d | 201 | 39 | -0.885 | [-1.151, -0.643] | 83.6% |
| first | 365 d | 144 | 32 | -2.502 | [-2.846, -2.125] | 94.4% |
| second | 7 d | 224 | 57 | +0.906 | [+0.832, +0.977] | 0.0% |
| second | 14 d | 224 | 57 | +0.755 | [+0.680, +0.837] | 0.0% |
| second | 30 d | 224 | 57 | +0.553 | [+0.495, +0.612] | 0.4% |
| second | 60 d | 224 | 57 | +0.320 | [+0.260, +0.386] | 11.2% |
| second | 90 d | 220 | 56 | +0.036 | [-0.043, +0.117] | 46.8% |
| second | 180 d | 206 | 53 | -1.500 | [-1.693, -1.310] | 95.6% |
| second | 365 d | 124 | 30 | -3.893 | [-4.250, -3.523] | 100.0% |

These reproduce the headline numbers of REVIEW_v14.md Major 5 (first +0.979/+0.684/+0.260/−0.885; second +0.906/+0.553/+0.036/−1.500 degC at 7/30/90/180 d) and extend them to 365 d (−2.50 first, −3.89 second).

## 3. Downstream climatology-default benefit by metric and horizon

Cells: mean benefit err_clim − err_recon on the metric's own scale (annual_mean = degC, summer_mean = degC, amplitude = degC, phase_doy = days, p90 = degC, summer_max = degC, exceed_days_20 = days, exceed_days_25 = days, cdd10 = degC-days, trend_slope = degC/yr), with the 95% cluster CI and the harmful share; all rows in `ci_tables.csv` / `flip_table.csv`.

### 3.1 first panel

| metric | 7 d | 30 d | 90 d | 180 d | 365 d |
|---|---|---|---|---|---|
| annual_mean | +0.022 [+0.017, +0.026] · 1% | +0.039 [+0.025, +0.056] · 12% | -0.032 [-0.073, +0.009] · 56% | -0.645 [-0.786, -0.501] · 94% | -2.427 [-2.841, -1.963] · 97% |
| summer_mean | +0.024 [+0.010, +0.041] · 6% | +0.048 [+0.015, +0.086] · 22% | +0.001 [-0.081, +0.074] · 44% | -0.814 [-1.187, -0.505] · 84% | -4.102 [-4.879, -3.277] · 97% |
| amplitude | +0.079 [+0.046, +0.114] · 11% | +0.048 [-0.006, +0.104] · 29% | -0.106 [-0.237, +0.028] · 65% | -1.699 [-2.090, -1.302] · 91% | -7.995 [-8.872, -7.035] · 99% |
| phase_doy | +0.226 [-0.106, +0.577] · 5% | -0.176 [-1.112, +0.624] · 10% | -0.505 [-2.115, +1.000] · 34% | -5.983 [-9.525, -2.606] · 68% | +0.904 [-3.533, +4.841] · 45% |
| p90 | +0.019 [+0.009, +0.031] · 5% | +0.028 [+0.001, +0.057] · 15% | -0.050 [-0.148, +0.041] · 47% | -0.906 [-1.250, -0.567] · 86% | -4.373 [-5.220, -3.476] · 96% |
| summer_max | +0.004 [-0.015, +0.022] · 0% | -0.001 [-0.047, +0.047] · 5% | -0.110 [-0.242, +0.018] · 39% | -1.038 [-1.506, -0.618] · 87% | -5.060 [-6.057, -4.038] · 96% |
| exceed_days_20 | +0.236 [+0.090, +0.397] · 2% | +0.499 [+0.023, +0.968] · 9% | -0.165 [-1.619, +1.158] · 21% | -7.102 [-12.617, -1.965] · 45% | -22.758 [-32.195, -13.351] · 49% |
| exceed_days_25 | +0.045 [-0.009, +0.107] · 2% | +0.057 [-0.282, +0.411] · 2% | -0.172 [-0.883, +0.447] · 5% | -0.212 [-1.401, +0.812] · 7% | -1.701 [-6.648, +1.310] · 6% |
| cdd10 | +2.675 [+1.654, +3.902] · 7% | +6.984 [+3.106, +11.549] · 23% | -4.176 [-15.188, +5.788] · 49% | -150.151 [-198.507, -102.430] · 89% | -675.751 [-768.337, -582.241] · 98% |
| trend_slope | +0.062 [+0.037, +0.088] · 9% | +0.076 [+0.003, +0.165] · 26% | +0.037 [-0.037, +0.120] · 37% | -0.197 [-0.321, -0.078] · 72% | -4.727 [-6.023, -3.571] · 96% |

### 3.2 second panel

| metric | 7 d | 30 d | 90 d | 180 d | 365 d |
|---|---|---|---|---|---|
| annual_mean | +0.020 [+0.016, +0.024] · 4% | +0.026 [+0.013, +0.039] · 29% | -0.074 [-0.107, -0.039] · 72% | -0.950 [-1.070, -0.827] · 97% | -3.831 [-4.296, -3.374] · 100% |
| summer_mean | +0.016 [+0.008, +0.023] · 9% | +0.026 [+0.003, +0.050] · 21% | -0.141 [-0.230, -0.054] · 64% | -1.588 [-1.973, -1.194] · 89% | -6.406 [-7.422, -5.249] · 100% |
| amplitude | +0.078 [+0.055, +0.104] · 14% | +0.094 [+0.026, +0.164] · 24% | -0.147 [-0.298, -0.002] · 56% | -2.588 [-3.019, -2.205] · 96% | -10.825 [-11.794, -9.816] · 100% |
| phase_doy | +0.594 [+0.245, +0.958] · 5% | +0.591 [-0.041, +1.223] · 10% | -0.942 [-2.271, +0.408] · 43% | -10.112 [-13.755, -6.483] · 73% | -7.430 [-12.984, -2.274] · 58% |
| p90 | +0.016 [+0.009, +0.024] · 9% | +0.021 [-0.003, +0.046] · 18% | -0.155 [-0.257, -0.059] · 65% | -1.485 [-1.932, -1.086] · 85% | -6.699 [-7.796, -5.532] · 98% |
| summer_max | +0.012 [-0.007, +0.031] · 2% | +0.014 [-0.027, +0.057] · 8% | -0.232 [-0.403, -0.076] · 45% | -1.806 [-2.404, -1.221] · 77% | -7.614 [-8.827, -6.454] · 99% |
| exceed_days_20 | +0.191 [+0.082, +0.304] · 2% | +0.297 [-0.054, +0.644] · 12% | -0.687 [-1.746, +0.452] · 31% | -9.310 [-13.506, -5.188] · 45% | -30.240 [-44.609, -17.250] · 49% |
| exceed_days_25 | +0.059 [+0.009, +0.113] · 0% | +0.029 [-0.155, +0.215] · 4% | -0.268 [-1.014, +0.474] · 15% | -3.967 [-7.943, -0.773] · 17% | -2.811 [-7.167, +0.805] · 9% |
| cdd10 | +3.446 [+2.321, +4.513] · 8% | +5.195 [+1.747, +8.516] · 26% | -15.748 [-25.866, -5.061] · 63% | -197.725 [-240.074, -155.793] · 92% | -853.701 [-1019.663, -692.509] · 98% |
| trend_slope | +0.052 [+0.036, +0.069] · 19% | +0.017 [-0.042, +0.072] · 41% | -0.035 [-0.116, +0.039] · 50% | -0.439 [-0.637, -0.270] · 82% | -5.273 [-5.938, -4.567] · 100% |

## 4. Flip crossings of the climatology-default benefit

Flip day = first horizon (log10-interpolated between the bracketing grid points) at which the mean benefit turns negative; the MAE row is the MAE-scale realized benefit.

| panel | row | flip day (d) | bracketing horizons | notes |
|---|---|---|---|---|
| first | MAE scale | 105.3 | 90-180 |  |
| first | annual_mean | 55.0 | 30-90 |  |
| first | summer_mean | 90.1 | 90-180 |  |
| first | amplitude | 42.4 | 30-90 |  |
| first | phase_doy | 15.9 | 7-30 | additional: recovery at 333 d |
| first | p90 | 44.5 | 30-90 |  |
| first | summer_max | 24.9 | 7-30 |  |
| first | exceed_days_20 | 68.5 | 30-90 |  |
| first | exceed_days_25 | 39.4 | 30-90 |  |
| first | cdd10 | 59.7 | 30-90 |  |
| first | trend_slope | 100.5 | 90-180 |  |
| second | MAE scale | 91.5 | 90-180 |  |
| second | annual_mean | 39.9 | 30-90 |  |
| second | summer_mean | 35.6 | 30-90 |  |
| second | amplitude | 46.0 | 30-90 |  |
| second | phase_doy | 45.8 | 30-90 |  |
| second | p90 | 34.3 | 30-90 |  |
| second | summer_max | 32.0 | 30-90 |  |
| second | exceed_days_20 | 41.8 | 30-90 |  |
| second | exceed_days_25 | 33.3 | 30-90 |  |
| second | cdd10 | 39.4 | 30-90 |  |
| second | trend_slope | 43.0 | 30-90 |  |

Family flip summaries per panel (member flip days, climatology default):

- first integral-type: median 60 d — annual_mean:55, summer_mean:90, p90:44, cdd10:60, trend_slope:101
- first threshold/peak-type: median 39 d — amplitude:42, phase_doy:16, summer_max:25, exceed_days_20:68, exceed_days_25:39
- second integral-type: median 39 d — annual_mean:40, summer_mean:36, p90:34, cdd10:39, trend_slope:43
- second threshold/peak-type: median 42 d — amplitude:46, phase_doy:46, summer_max:32, exceed_days_20:42, exceed_days_25:33

## 5. Linear default (Q2)

### 5.1 Benefit over the linear default (err_linear − err_recon)

| panel | horizon | annual_mean | summer_mean | amplitude | phase_doy | p90 | summer_max | exceed_days_20 | exceed_days_25 | cdd10 | trend_slope |
|---|---|---|---|---|---|---|---|---|---|---|---|
| first | 7 d | +0.00 | +0.00 | +0.01 | -0.06 | +0.00 | +0.00 | +0.02 | +0.00 | +0.36 | +0.00 |
| first | 30 d | +0.02 | +0.02 | +0.04 | +0.10 | +0.01 | +0.00 | +0.27 | +0.02 | +3.02 | +0.03 |
| first | 90 d | +0.08 | +0.07 | +0.19 | +1.38 | +0.07 | +0.04 | +0.87 | +0.06 | +15.10 | +0.08 |
| first | 180 d | +0.51 | +0.64 | +1.34 | +8.31 | +0.54 | +0.53 | +3.53 | +0.05 | +127.53 | +0.25 |
| first | 365 d | +1.64 | +2.72 | +4.84 | +78.96 | +2.42 | +3.31 | +16.72 | +0.92 | +357.53 | +3.13 |
| second | 7 d | +0.00 | +0.00 | +0.01 | +0.06 | +0.00 | +0.00 | +0.01 | +0.01 | +0.42 | +0.01 |
| second | 30 d | +0.02 | +0.01 | +0.05 | -0.02 | +0.01 | +0.01 | +0.18 | +0.01 | +2.62 | +0.06 |
| second | 90 d | +0.07 | +0.08 | +0.16 | +1.60 | +0.07 | +0.05 | +0.79 | +0.20 | +12.90 | +0.09 |
| second | 180 d | +0.42 | +0.63 | +1.11 | +10.28 | +0.47 | +0.56 | +2.38 | +1.24 | +82.97 | +0.24 |
| second | 365 d | +1.43 | +2.15 | +3.73 | +88.74 | +1.89 | +2.70 | +13.35 | +1.34 | +213.37 | +2.07 |

### 5.2 Where the linear default is worse than climatology

- first panel, metrics with err_linear > err_clim per horizon: 7 d: 0/10, 30 d: 2/10, 90 d: 10/10, 180 d: 10/10, 365 d: 10/10
- second panel, metrics with err_linear > err_clim per horizon: 7 d: 0/10, 30 d: 1/10, 90 d: 10/10, 180 d: 10/10, 365 d: 10/10

err_linear − err_clim per horizon (first / second panel; degC, days for phase_doy):

| metric | 7 d | 30 d | 90 d | 180 d | 365 d |
|---|---|---|---|---|---|
| annual_mean | -0.019 / -0.017 | -0.022 / -0.009 | +0.114 / +0.147 | +1.151 / +1.370 | +4.065 / +5.256 |
| amplitude | -0.068 / -0.067 | -0.010 / -0.048 | +0.299 / +0.312 | +3.036 / +3.700 | +12.831 / +14.552 |
| cdd10 | -2.315 / -3.025 | -3.963 / -2.580 | +19.273 / +28.651 | +277.679 / +280.698 | +1033.282 / +1067.071 |
| phase_doy | -0.289 / -0.537 | +0.274 / -0.610 | +1.882 / +2.541 | +14.288 / +20.390 | +78.054 / +96.165 |

### 5.3 No-fill context (annual_mean, degC)

Mean distortion of the three defaults and the reconstruction on annual_mean by horizon (panel's metric_error_summary: no-fill means are on the recon+missing support; the annual_mean default support equals the missing support at every horizon where no-fill is computable, so the columns are directly comparable for this metric; no-fill is uncomputable at 365 d).

| panel | horizon | recon | climatology | linear | no-fill |
|---|---|---|---|---|---|
| first | 7 d | 0.008 | 0.029 | 0.010 | 0.127 |
| first | 30 d | 0.043 | 0.082 | 0.059 | 0.532 |
| first | 90 d | 0.214 | 0.182 | 0.297 | 1.577 |
| first | 180 d | 0.997 | 0.353 | 1.503 | 2.802 |
| first | 365 d | 3.038 | 0.611 | 4.676 | uncomputable |
| second | 7 d | 0.010 | 0.030 | 0.013 | 0.140 |
| second | 30 d | 0.062 | 0.087 | 0.078 | 0.599 |
| second | 90 d | 0.265 | 0.192 | 0.338 | 1.772 |
| second | 180 d | 1.270 | 0.320 | 1.691 | 3.083 |
| second | 365 d | 4.442 | 0.612 | 5.868 | uncomputable |

## 6. Network-level correlation: MAE realized benefit vs downstream benefit

Spearman rho (per-network means) between the P0 MAE-scale realized benefit and the downstream climatology-default benefit err_clim − err_recon, per horizon and key metric, with the 2000-draw network-cluster CI (rows in `ci_tables.csv`).

### 6.1 first panel

| metric | 7 d | 30 d | 90 d | 180 d | 365 d |
|---|---|---|---|---|---|
| annual_mean | +0.83 [+0.66, +0.92] | +0.35 [+0.04, +0.63] | +0.74 [+0.54, +0.87] | +0.85 [+0.68, +0.93] | +0.71 [+0.44, +0.87] |
| amplitude | +0.58 [+0.30, +0.73] | -0.07 [-0.40, +0.25] | +0.58 [+0.35, +0.74] | +0.75 [+0.54, +0.87] | +0.91 [+0.80, +0.96] |
| cdd10 | +0.52 [+0.24, +0.76] | +0.57 [+0.30, +0.75] | +0.73 [+0.50, +0.86] | +0.80 [+0.61, +0.89] | +0.60 [+0.25, +0.83] |
| phase_doy | +0.20 [-0.14, +0.48] | -0.02 [-0.35, +0.31] | +0.44 [+0.13, +0.71] | +0.36 [+0.03, +0.63] | +0.28 [-0.09, +0.58] |

### 6.2 second panel

| metric | 7 d | 30 d | 90 d | 180 d | 365 d |
|---|---|---|---|---|---|
| annual_mean | +0.61 [+0.39, +0.77] | +0.47 [+0.24, +0.64] | +0.56 [+0.34, +0.73] | +0.79 [+0.65, +0.88] | +0.89 [+0.74, +0.96] |
| amplitude | +0.25 [-0.02, +0.52] | +0.39 [+0.12, +0.60] | +0.30 [+0.05, +0.52] | +0.66 [+0.45, +0.81] | +0.84 [+0.67, +0.93] |
| cdd10 | +0.45 [+0.18, +0.66] | +0.53 [+0.35, +0.68] | +0.40 [+0.13, +0.62] | +0.32 [+0.08, +0.55] | +0.63 [+0.36, +0.83] |
| phase_doy | -0.20 [-0.45, +0.08] | +0.01 [-0.27, +0.30] | +0.12 [-0.13, +0.39] | +0.31 [+0.05, +0.55] | -0.03 [-0.39, +0.35] |

## 7. Verdicts

**Q1 raw series (first panel).**

MAE-scale realized benefit over climatology (grid 7/14/30/60/90/180/365 d): 7 d +0.98 degC / 14 d +0.85 degC / 30 d +0.68 degC / 60 d +0.48 degC / 90 d +0.26 degC / 180 d -0.89 degC / 365 d -2.50 degC; log10-interpolated MAE flip at 105 d.
- annual_mean downstream (climatology default): 7 d +0.02 / 30 d +0.04 / 90 d -0.03 / 180 d -0.64 / 365 d -2.43 — flip at 55 d.
- amplitude downstream (climatology default): 7 d +0.08 / 30 d +0.05 / 90 d -0.11 / 180 d -1.70 / 365 d -8.00 — flip at 42 d.
- cdd10 downstream (climatology default): 7 d +2.67 / 30 d +6.98 / 90 d -4.18 / 180 d -150.15 / 365 d -675.75 — flip at 60 d.
- phase_doy downstream (climatology default): 7 d +0.23 / 30 d -0.18 / 90 d -0.50 / 180 d -5.98 / 365 d +0.90 — flip at 16 d.

**Q1 raw series (second panel).**

MAE-scale realized benefit over climatology (grid 7/14/30/60/90/180/365 d): 7 d +0.91 degC / 14 d +0.76 degC / 30 d +0.55 degC / 60 d +0.32 degC / 90 d +0.04 degC / 180 d -1.50 degC / 365 d -3.89 degC; log10-interpolated MAE flip at 91 d.
- annual_mean downstream (climatology default): 7 d +0.02 / 30 d +0.03 / 90 d -0.07 / 180 d -0.95 / 365 d -3.83 — flip at 40 d.
- amplitude downstream (climatology default): 7 d +0.08 / 30 d +0.09 / 90 d -0.15 / 180 d -2.59 / 365 d -10.82 — flip at 46 d.
- cdd10 downstream (climatology default): 7 d +3.45 / 30 d +5.19 / 90 d -15.75 / 180 d -197.72 / 365 d -853.70 — flip at 39 d.
- phase_doy downstream (climatology default): 7 d +0.59 / 30 d +0.59 / 90 d -0.94 / 180 d -10.11 / 365 d -7.43 — flip at 46 d.

### Q1 — does downstream distortion flip in the same window as the MAE benefit?

On the seven-point fitted grid the MAE-scale benefit is still positive at 90 d on both panels (+0.26 degC first, +0.04 degC second) and negative at 180 d (-0.89 / -1.50 degC); the log10-interpolated MAE crossing therefore sits at the upper edge of — not inside — the headline 30–90-day window: 105 d (first panel) and 91 d (second panel).  (The finer-grained ~60-day figure quoted in the manuscript comes from the internal sub-grid analysis; the five-point P4 grid brackets the first-panel flip between 90 and 180 d and places the second-panel flip essentially at 90 d.)
On the downstream side the distortion flips **within the same ~30–90-day window as the MAE benefit, and if anything earlier**: annual_mean flips at 55 d / 40 d, amplitude at 42 d / 46 d, cdd10 at 60 d / 39 d and phase_doy at 16 d / 46 d (first / second panel, climatology default).  8/10 metrics are already climatology-net-harmful at 90 d on the first panel and 10/10 on the second panel (still positive at 90 d: summer_mean, trend_slope first, none second; still positive at 180 d: none / none), so every metric of both panels is net-harmful by 180 d (first) / 90 d (second).  The unit-level harmful share of the climatology comparison is 56% / 72% at 90 d and 94% / 97% at 180 d (annual_mean, first / second panel), versus 27% / 47% on the MAE scale at 90 d.  No downstream metric remains reconstruction-favourable at or beyond the MAE crossing on either panel: the downstream distortion flips earlier than the MAE benefit for the mean-like metrics and is not delayed behind it for any metric, so the ~60–90-day operational rule is supported — and is conservative — on the downstream climatology-default comparison.

### Q2 — where does the linear-interpolation default sit, and does the default choice reverse the headline?

Versus the **linear default** the model is beneficial at every horizon on both panels: benefit err_linear − err_recon is positive in 98 of 100 panel × horizon × metric cells (two panels × five horizons × ten metrics for the linear default; the only non-positive cells: first 7 d phase_doy -0.06, second 30 d phase_doy -0.02), and it grows with the horizon.  The linear default therefore sits **below** the climatology default as a no-recovery baseline at the short horizons and **between climatology and no-fill** from ~90 d up: at 7 d the linear ramp is the better default for 10/10 metrics (first) and 10/10 (second panel), while at 90 d the climatology default is better for 10/10 (first) and 10/10 (second panel) metrics; err_linear − err_clim (annual_mean, first panel) is -0.02 degC at 7 d, -0.02 degC at 30 d, flips to +0.11 degC at 90 d and reaches +4.06 degC at 365 d.  The horizon where each metric's linear-vs-clim difference turns positive: first panel: 2/10 within 7-30 d, 8/10 within 30-90 d; second panel: 1/10 within 7-30 d, 9/10 within 30-90 d.  No-fill stays the worst default wherever it is computable (annual_mean at 180 d, first panel: no-fill error 2.80 degC vs linear 1.50 degC).

Consequence for the headline direction: the “do not reconstruct beyond ~60–90 days” rule is a statement about the climatology default. Where the manager's operational default is linear interpolation, the choice of default reverses the headline: reconstruction beats the linear ramp at every horizon on both panels, so under the linear default the climatology-default crossing does not exist within 7–365 d, while under the climatology default every metric crosses into net harm by 180 d on the first panel and by 90 d on the second.

### Q3 — do the flip thresholds differ between metric families?

**first panel:** integral-type (annual_mean, summer_mean, p90, cdd10, trend_slope) flips at a median 60 d — members: annual_mean:55, summer_mean:90, p90:44, cdd10:60, trend_slope:101.  Threshold/peak-type (exceed_days_20, exceed_days_25, summer_max, amplitude, phase_doy) flips at a median 39 d — members: amplitude:42, phase_doy:16, summer_max:25, exceed_days_20:68, exceed_days_25:39.
**second panel:** integral-type (annual_mean, summer_mean, p90, cdd10, trend_slope) flips at a median 39 d — members: annual_mean:40, summer_mean:36, p90:34, cdd10:39, trend_slope:43.  Threshold/peak-type (exceed_days_20, exceed_days_25, summer_max, amplitude, phase_doy) flips at a median 42 d — members: amplitude:46, phase_doy:46, summer_max:32, exceed_days_20:42, exceed_days_25:33.

Flip-interval distribution per family (grid intervals 7–30/30–90/90–180/180–365 d): first integral-type: 3 in 30-90, 2 in 90-180; first threshold/peak-type: 3 in 30-90, 2 in 7-30; second integral-type: 5 in 30-90; second threshold/peak-type: 5 in 30-90.

The flip thresholds **do differ between the families** on the first panel and coincide within the grid's resolution on the second.  First panel: integral-type median flip 60 d vs threshold/peak-type median 39 d — a 20-day separation, with the integral family's flips extending into the 90–180 interval and the threshold/peak family's into the 7–30 interval (interval distributions above).  Second panel: integral median 39 d vs threshold/peak median 42 d — every member of both families flips inside the single 30–90-day grid interval, so the family thresholds cannot be separated at this resolution (medians within 2 d).  The only non-monotone member is phase_doy on the first panel, whose benefit re-crosses to positive between 180 and 365 d (its 365-day benefit is +0.90 d; a whole-year gap leaves no annual cycle for either reconstruction or climatology to place a peak within).

### Q1–Q3 bottom line

The downstream distortion flips at the same ~30–90-day window as the MAE benefit, with the specific metric-family differences described above: downstream climatology-default crossings are annual_mean 55 d / 40 d, amplitude 42 d / 46 d, cdd10 60 d / 39 d and phase_doy 16 d / 46 d (first / second panel), all at or below the panels' MAE crossings (105 d first, 91 d second); integral-type members flip with median 60 d (first) / 39 d (second panel) and the threshold/peak-type members with median 39 d / 42 d — the threshold/peak-type family flips first on this panel (39 vs 60 d), while on the second panel the medians coincide within the single 30–90-day grid interval. The independent Johnson et al. (2021) m_max = 49-day reference lies below both panels' downstream crossings — inside the still reconstruction-favourable regime — consistent with its conservative “heed the data gap” purpose.  Under the linear-interpolation default, by contrast, the model beats the default at every horizon on both panels, so the ~60–90-day rule is a statement about the climatology default.

