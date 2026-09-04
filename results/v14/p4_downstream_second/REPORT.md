# P4 — Downstream thermal-regime metrics at 7/30/90/180/365-day gaps (second panel)

**Namespace:** `results/v14/p4_downstream_second/`
**Script:** `scripts/146_run_p4_downstream_second.py` (copy in `run_script_146.py`)
**Run:** 19 s scoring, 23 s total wall; 24 workers; XGBOOST_PARAMETERS unchanged (n_jobs = 1 inside workers).

## 1. Setup

- **Networks:** all 57 second-panel networks with archived B_union_D evaluation placements (placement_losses.csv) — the full second_confirmation scoring roster (15 chmi_*, 10 nve_basin_*, 32 usgs2_*); panels read from second_confirmation/daily_qc/networks/<id>/daily_wide_temperature.csv with fallback to confirmation_daily_qc/networks/<id>/ (the 15 chmi_* panels live there).
- **Horizons:** 7/30/90/180/365 days. The archive also carries horizons 14/60, which are excluded here exactly as in the first-panel script (P4 horizons only).
- **Model:** the frozen XGBoost B_union_D recovery pipeline (development_recovery.XGBOOST_PARAMETERS, boundary temperature + donor columns, n_jobs = 1), retrained on the outer training years only (70% chronological year split, >= 365 training days). Per-placement reconstruction MAE reproduces the archived placement_losses values on identical placements to ~1e-12 (sanity_checks.txt), confirming the refit matches the archived runs.
- **Defaults on identical gaps:** (1) calendar-day climatology (day-of-year medians from the outer training years); (2) linear interpolation between the two flanking observed days (_boundary_values; note this ramp is also the model's boundary feature, so the linear default is the model's own minimal sub-model); (3) no-fill (gap days dropped, agent_b's uncomputable handling).
- **Placements:** archived evaluation geometry (B_union_D rows), evenly sampled at most 5 per (station, gap_length) across the archived placements of each cell.  All sampled placements were verified (observed truth and donors over the gap, observed boundary days, gap fully inside the evaluation years); violations are skipped and counted in sanity_checks.txt.
- **Metrics and window:** the ten thermal-regime metrics and the 365-day window centred on the gap middle day (+/- 182 days; the window coincides with the gap exactly for 365-day gaps) are imported unchanged from the agent_b script (scripts/rev_v12_t08_downstream_metrics_b.py).  Per-placement truth series = observed values; recon/clim/linear series replace the gap days; missing drops them.  Phase error is the circular day difference; station-gap phase aggregation uses the circular mean.
- **P0 join:** placement_predictions_second.csv joined 1:1 on (network_id, station_id, gap_length, placement, gap_start); the join has no duplicate keys and no unmatched placements (the second-panel placements are shared with P0 by construction).

## 2. Scale per horizon

- 7 d: 57 networks / 224 stations / 224 station-gap units / 1120 placements
- 30 d: 57 networks / 224 stations / 224 station-gap units / 1120 placements
- 90 d: 56 networks / 220 stations / 220 station-gap units / 1100 placements
- 180 d: 53 networks / 206 stations / 206 station-gap units / 1008 placements
- 365 d: 30 networks / 124 stations / 124 station-gap units / 600 placements

Total: 4948 placements, 57 networks, 998 station-gap units across the five horizons.

No-fill (missing) is uncomputable for every 365-day placement: the gap-centred 365-day window coincides exactly with the gap, so dropping the gap days empties the record (agent_b's uncomputable handling). Recon-vs-no-fill ratios therefore exist only for the 7/30/90/180-day horizons (and only per metric where month-swallowing gaps leave e.g. amplitude undefined); recon-vs-climatology and recon-vs-linear are reported for all five horizons.

## 3. Model benefit over the defaults (station-gap units)

Unit errors are means over placements (circular mean for phase). Benefit = mean(default error) - mean(recon error) on the same paired units (metric_error_summary.csv); positive means reconstruction reduces distortion relative to the default.

| horizon | metric | mean err recon | mean err clim | mean err linear | benefit over clim | benefit over linear | recon/clim | recon/linear | n units |
|---|---|---|---|---|---|---|---|---|---|
| 7 | annual_mean | 0.010 | 0.030 | 0.013 | +0.020 | +0.003 | 0.34 | 0.80 | 224 |
| 7 | amplitude | 0.032 | 0.110 | 0.043 | +0.078 | +0.011 | 0.29 | 0.74 | 224 |
| 7 | cdd10 | 1.761 | 5.208 | 2.182 | +3.446 | +0.421 | 0.34 | 0.81 | 224 |
| 7 | phase_doy | 0.221 | 0.815 | 0.278 | +0.594 | +0.057 | 0.27 | 0.80 | 224 |
| 7 | p90 | 0.010 | 0.026 | 0.013 | +0.016 | +0.003 | 0.39 | 0.79 | 224 |
| 30 | annual_mean | 0.062 | 0.087 | 0.078 | +0.026 | +0.017 | 0.70 | 0.78 | 224 |
| 30 | amplitude | 0.175 | 0.269 | 0.220 | +0.094 | +0.045 | 0.65 | 0.79 | 223 |
| 30 | cdd10 | 9.961 | 15.156 | 12.576 | +5.195 | +2.615 | 0.66 | 0.79 | 224 |
| 30 | phase_doy | 0.890 | 1.481 | 0.871 | +0.591 | -0.018 | 0.60 | 1.02 | 224 |
| 30 | p90 | 0.056 | 0.077 | 0.067 | +0.021 | +0.010 | 0.72 | 0.84 | 224 |
| 90 | annual_mean | 0.265 | 0.192 | 0.338 | -0.074 | +0.073 | 1.38 | 0.78 | 220 |
| 90 | amplitude | 0.670 | 0.522 | 0.834 | -0.147 | +0.164 | 1.28 | 0.80 | 219 |
| 90 | cdd10 | 53.136 | 37.388 | 66.040 | -15.748 | +12.904 | 1.42 | 0.80 | 220 |
| 90 | phase_doy | 5.471 | 4.529 | 7.071 | -0.942 | +1.599 | 1.21 | 0.77 | 220 |
| 90 | p90 | 0.387 | 0.232 | 0.458 | -0.155 | +0.071 | 1.67 | 0.84 | 220 |
| 180 | annual_mean | 1.270 | 0.320 | 1.691 | -0.950 | +0.420 | 3.97 | 0.75 | 206 |
| 180 | amplitude | 3.499 | 0.911 | 4.611 | -2.588 | +1.111 | 3.84 | 0.76 | 205 |
| 180 | cdd10 | 269.227 | 71.503 | 352.201 | -197.725 | +82.974 | 3.77 | 0.76 | 206 |
| 180 | phase_doy | 19.939 | 9.827 | 30.217 | -10.112 | +10.279 | 2.03 | 0.66 | 206 |
| 180 | p90 | 2.002 | 0.517 | 2.469 | -1.485 | +0.467 | 3.87 | 0.81 | 206 |
| 365 | annual_mean | 4.442 | 0.612 | 5.868 | -3.831 | +1.426 | 7.26 | 0.76 | 124 |
| 365 | amplitude | 11.913 | 1.089 | 15.641 | -10.825 | +3.727 | 10.94 | 0.76 | 124 |
| 365 | cdd10 | 989.923 | 136.223 | 1203.294 | -853.701 | +213.371 | 7.27 | 0.82 | 124 |
| 365 | phase_doy | 22.857 | 15.426 | 111.592 | -7.430 | +88.735 | 1.48 | 0.20 | 124 |
| 365 | p90 | 7.711 | 1.012 | 9.598 | -6.699 | +1.886 | 7.62 | 0.80 | 124 |

## 4. The 180- and 365-day numbers missing before

| horizon | metric | n units | recon | clim | linear | benefit clim | benefit linear | recon/clim | recon/linear |
|---|---|---|---|---|---|---|---|---|---|
| 180 | annual_mean | 206 | 1.270 | 0.320 | 1.691 | -0.950 | +0.420 | 3.97 | 0.75 |
| 180 | summer_mean | 206 | 2.049 | 0.461 | 2.682 | -1.588 | +0.633 | 4.44 | 0.76 |
| 180 | amplitude | 205 | 3.499 | 0.911 | 4.611 | -2.588 | +1.111 | 3.84 | 0.76 |
| 180 | phase_doy | 206 | 19.939 | 9.827 | 30.217 | -10.112 | +10.279 | 2.03 | 0.66 |
| 180 | p90 | 206 | 2.002 | 0.517 | 2.469 | -1.485 | +0.467 | 3.87 | 0.81 |
| 180 | summer_max | 206 | 2.523 | 0.717 | 3.080 | -1.806 | +0.557 | 3.52 | 0.82 |
| 180 | exceed_days_20 | 206 | 15.152 | 5.842 | 17.536 | -9.310 | +2.384 | 2.59 | 0.86 |
| 180 | exceed_days_25 | 206 | 5.895 | 1.928 | 7.132 | -3.967 | +1.237 | 3.06 | 0.83 |
| 180 | cdd10 | 206 | 269.227 | 71.503 | 352.201 | -197.725 | +82.974 | 3.77 | 0.76 |
| 180 | trend_slope | 206 | 0.867 | 0.428 | 1.104 | -0.439 | +0.238 | 2.02 | 0.78 |
| 365 | annual_mean | 124 | 4.442 | 0.612 | 5.868 | -3.831 | +1.426 | 7.26 | 0.76 |
| 365 | summer_mean | 124 | 7.258 | 0.852 | 9.410 | -6.406 | +2.152 | 8.52 | 0.77 |
| 365 | amplitude | 124 | 11.913 | 1.089 | 15.641 | -10.825 | +3.727 | 10.94 | 0.76 |
| 365 | phase_doy | 124 | 22.857 | 15.426 | 111.592 | -7.430 | +88.735 | 1.48 | 0.20 |
| 365 | p90 | 124 | 7.711 | 1.012 | 9.598 | -6.699 | +1.886 | 7.62 | 0.80 |
| 365 | summer_max | 124 | 9.387 | 1.773 | 12.084 | -7.614 | +2.697 | 5.29 | 0.78 |
| 365 | exceed_days_20 | 124 | 42.071 | 11.831 | 55.421 | -30.240 | +13.350 | 3.56 | 0.76 |
| 365 | exceed_days_25 | 124 | 5.039 | 2.227 | 6.377 | -2.811 | +1.339 | 2.26 | 0.79 |
| 365 | cdd10 | 124 | 989.923 | 136.223 | 1203.294 | -853.701 | +213.371 | 7.27 | 0.82 |
| 365 | trend_slope | 124 | 6.494 | 1.220 | 8.567 | -5.273 | +2.073 | 5.32 | 0.76 |

### 4.1 Where the model is net-harmful versus a default

Net-harmful = unit-mean |recon error| > unit-mean |default error| for that horizon x metric (same paired units, so benefit < 0).
- horizon 90 d vs climatology: annual_mean (-0.07 degC); summer_mean (-0.14 degC); amplitude (-0.15 degC); phase_doy (-0.94 days); p90 (-0.16 degC); summer_max (-0.23 degC); exceed_days_20 (-0.69 count); exceed_days_25 (-0.27 count); cdd10 (-15.75 degC-days); trend_slope (-0.04 degC/yr)
- horizon 180 d vs climatology: annual_mean (-0.95 degC); summer_mean (-1.59 degC); amplitude (-2.59 degC); phase_doy (-10.11 days); p90 (-1.49 degC); summer_max (-1.81 degC); exceed_days_20 (-9.31 count); exceed_days_25 (-3.97 count); cdd10 (-197.72 degC-days); trend_slope (-0.44 degC/yr)
- horizon 365 d vs climatology: annual_mean (-3.83 degC); summer_mean (-6.41 degC); amplitude (-10.82 degC); phase_doy (-7.43 days); p90 (-6.70 degC); summer_max (-7.61 degC); exceed_days_20 (-30.24 count); exceed_days_25 (-2.81 count); cdd10 (-853.70 degC-days); trend_slope (-5.27 degC/yr)
- horizon 30 d vs linear: phase_doy (-0.02 days)

Reading: versus the climatology default the model is net-harmful from 90-day gaps upward on most metrics, and at 180/365 days it is net-harmful on every metric with a computable comparison (see rows above for the exact per-metric signs on this panel; the first-panel exception was phase at 365 days, where the model recovered its advantage).  Versus the linear default the model is net-harmful only marginally (see rows above), and the benefit over linear grows with the horizon.  Several 7/30-day entries are small in absolute terms (phase ~0.1-0.5 d, summer_max ~0.0-0.1 degC); the 90/180/365-day entries are large on every scale.

### 4.2 Model daily reconstruction MAE (context)

Mean |prediction - truth| over the gap days themselves (mae_deg_c in placement_metrics.csv), reproducing the archived placement_losses values exactly:

- 7 d: 0.53 degC (n = 1120)
- 30 d: 0.88 degC (n = 1120)
- 90 d: 1.33 degC (n = 1100)
- 180 d: 2.76 degC (n = 1008)
- 365 d: 5.28 degC (n = 600)

### 4.3 No-fill comparison (where no-fill is computable)

Mean recon error vs mean no-fill error on the paired support (n_missing_units units; recon recomputed on that support); ratio < 1 means reconstruction repairs the truncated record.
| horizon | metric | n missing units | recon (paired) | no-fill | recon/no-fill |
|---|---|---|---|---|---|
| 7 | annual_mean | 224 | 0.010 | 0.140 | 0.07 |
| 7 | summer_mean | 224 | 0.008 | 0.030 | 0.28 |
| 7 | amplitude | 224 | 0.031 | 0.078 | 0.39 |
| 7 | phase_doy | 224 | 0.221 | 0.552 | 0.40 |
| 7 | p90 | 224 | 0.010 | 0.066 | 0.15 |
| 7 | summer_max | 224 | 0.017 | 0.019 | 0.92 |
| 7 | exceed_days_20 | 224 | 0.122 | 1.004 | 0.12 |
| 7 | exceed_days_25 | 224 | 0.029 | 0.410 | 0.07 |
| 7 | cdd10 | 224 | 1.761 | 25.841 | 0.07 |
| 7 | trend_slope | 224 | 0.033 | 0.175 | 0.19 |
| 30 | annual_mean | 224 | 0.062 | 0.599 | 0.10 |
| 30 | summer_mean | 224 | 0.038 | 0.114 | 0.33 |
| 30 | amplitude | 223 | 0.025 | 0.034 | 0.72 |
| 30 | phase_doy | 224 | 0.890 | 1.463 | 0.61 |
| 30 | p90 | 224 | 0.056 | 0.257 | 0.22 |
| 30 | summer_max | 224 | 0.036 | 0.038 | 0.95 |
| 30 | exceed_days_20 | 224 | 0.646 | 3.825 | 0.17 |
| 30 | exceed_days_25 | 224 | 0.219 | 1.631 | 0.13 |
| 30 | cdd10 | 224 | 9.961 | 103.209 | 0.10 |
| 30 | trend_slope | 224 | 0.185 | 0.641 | 0.29 |
| 90 | annual_mean | 220 | 0.265 | 1.772 | 0.15 |
| 90 | summer_mean | 220 | 0.211 | 0.305 | 0.69 |
| 90 | amplitude | 212 | 0.106 | 0.100 | 1.07 |
| 90 | phase_doy | 220 | 5.471 | 8.242 | 0.66 |
| 90 | p90 | 220 | 0.387 | 1.028 | 0.38 |
| 90 | summer_max | 220 | 0.212 | 0.221 | 0.96 |
| 90 | exceed_days_20 | 220 | 3.459 | 14.065 | 0.25 |
| 90 | exceed_days_25 | 220 | 1.315 | 5.001 | 0.26 |
| 90 | cdd10 | 220 | 53.136 | 347.898 | 0.15 |
| 90 | trend_slope | 220 | 0.312 | 2.511 | 0.12 |
| 180 | annual_mean | 206 | 1.270 | 3.083 | 0.41 |
| 180 | summer_mean | 179 | 0.469 | 0.520 | 0.90 |
| 180 | amplitude | 15 | 0.787 | 0.497 | 1.58 |
| 180 | phase_doy | 206 | 20.031 | 32.564 | 0.62 |
| 180 | p90 | 206 | 2.002 | 3.233 | 0.62 |
| 180 | summer_max | 179 | 0.346 | 0.351 | 0.99 |
| 180 | exceed_days_20 | 206 | 15.152 | 30.396 | 0.50 |
| 180 | exceed_days_25 | 206 | 5.895 | 10.315 | 0.57 |
| 180 | cdd10 | 206 | 269.227 | 759.770 | 0.35 |
| 180 | trend_slope | 206 | 0.865 | 3.960 | 0.22 |

## 5. Budget within horizon (budget_within_horizon.csv)

Top-20% placement budgets within each horizon (treatment = fill the gap with the model). Per metric: mean over the treated placements of err_clim - err_recon and err_linear - err_recon (model benefit over the climatology and the linear default, on the metric's own scale) and the harmful-rate shares (treated placements where the model is worse than the default). Policies: by P0 diff_prediction, by duration_only_prediction, by risk_prediction, and random (mean over 100 draws, seed 0; sd over draws in the *_sd columns). The duration-only predictor is undefined at 365 days in the P0 tables (no directly supported 365-day units), so that policy exists only at 7/30/90/180.

### 5.1 annual_mean

| horizon | policy | n pool | n treated | benefit clim | harmful clim | benefit linear | harmful linear |
|---|---|---|---|---|---|---|---|
| 7 | diff | 1120 | 224 | +0.026 | 0.170 | +0.005 | 0.237 |
| 7 | duration | 1120 | 224 | +0.017 | 0.170 | +0.001 | 0.429 |
| 7 | risk | 1120 | 224 | +0.022 | 0.223 | +0.004 | 0.295 |
| 7 | random | 1120 | 224 | +0.019 | 0.183 | +0.003 | 0.345 |
| 30 | diff | 1120 | 224 | +0.040 | 0.339 | +0.028 | 0.188 |
| 30 | duration | 1120 | 224 | +0.019 | 0.344 | +0.011 | 0.290 |
| 30 | risk | 1120 | 224 | +0.025 | 0.384 | +0.026 | 0.170 |
| 30 | random | 1120 | 224 | +0.026 | 0.356 | +0.017 | 0.256 |
| 90 | diff | 1100 | 220 | +0.002 | 0.477 | +0.112 | 0.159 |
| 90 | duration | 1100 | 220 | -0.117 | 0.645 | +0.059 | 0.155 |
| 90 | risk | 1100 | 220 | -0.177 | 0.668 | +0.071 | 0.159 |
| 90 | random | 1100 | 220 | -0.073 | 0.586 | +0.073 | 0.153 |
| 180 | diff | 1008 | 202 | -0.570 | 0.817 | +0.524 | 0.050 |
| 180 | duration | 1008 | 202 | -0.972 | 0.901 | +0.306 | 0.045 |
| 180 | risk | 1008 | 202 | -1.575 | 0.946 | +0.465 | 0.010 |
| 180 | random | 1008 | 202 | -0.935 | 0.869 | +0.421 | 0.050 |
| 365 | diff | 600 | 120 | -3.092 | 0.950 | +1.981 | 0.017 |
| 365 | risk | 600 | 120 | -4.568 | 0.950 | +1.252 | 0.025 |
| 365 | random | 600 | 120 | -3.794 | 0.941 | +1.408 | 0.031 |

### 5.2 amplitude

| horizon | policy | n pool | n treated | benefit clim | harmful clim | benefit linear | harmful linear |
|---|---|---|---|---|---|---|---|
| 7 | diff | 900 | 180 | +0.095 | 0.044 | +0.019 | 0.056 |
| 7 | duration | 900 | 180 | +0.060 | 0.078 | +0.004 | 0.178 |
| 7 | risk | 900 | 180 | +0.068 | 0.072 | +0.017 | 0.072 |
| 7 | random | 900 | 180 | +0.075 | 0.066 | +0.010 | 0.143 |
| 30 | diff | 903 | 181 | +0.130 | 0.094 | +0.057 | 0.066 |
| 30 | duration | 903 | 181 | +0.095 | 0.105 | +0.015 | 0.138 |
| 30 | risk | 903 | 181 | +0.035 | 0.138 | +0.050 | 0.083 |
| 30 | random | 903 | 181 | +0.092 | 0.137 | +0.044 | 0.130 |
| 90 | diff | 918 | 184 | -0.005 | 0.321 | +0.279 | 0.114 |
| 90 | duration | 918 | 184 | -0.216 | 0.446 | +0.214 | 0.201 |
| 90 | risk | 918 | 184 | -0.439 | 0.402 | +0.142 | 0.152 |
| 90 | random | 918 | 184 | -0.154 | 0.365 | +0.162 | 0.144 |
| 180 | diff | 899 | 180 | -1.377 | 0.744 | +1.321 | 0.072 |
| 180 | duration | 899 | 180 | -2.544 | 0.872 | +0.837 | 0.050 |
| 180 | risk | 899 | 180 | -5.076 | 0.967 | +1.201 | 0.017 |
| 180 | random | 899 | 180 | -2.541 | 0.862 | +1.124 | 0.061 |
| 365 | diff | 600 | 120 | -9.061 | 1.000 | +5.056 | 0.008 |
| 365 | risk | 600 | 120 | -12.906 | 1.000 | +3.307 | 0.008 |
| 365 | random | 600 | 120 | -10.676 | 1.000 | +3.739 | 0.003 |

## 6. Consistency with the archived agent_b run (not applicable)

The first-panel script (145) cross-checked its recon errors against the archived agent_b run (revision_v12, horizons 7/30/90) on the 351 shared station-gap cells of agent_b's 15 networks.  That comparison does not apply to the second panel: agent_b scored 15 first-panel networks (arso/gkd/foen/lubw/rws/huc8/usgs_missouri_river_huc10/usgs_snake_river_huc4_1706), and none of them recurs among the 57 second-panel networks (chmi_*/nve_basin_*/usgs2_*).  The recon-MAE reproduction against the archived placement_losses.csv (sanity_checks.txt) is the fidelity check for this panel: the refit reproduces the archived per-placement MAE values to ~1e-15 on every scored placement, and the metric definitions themselves are imported from the agent_b script, so the conventions are shared with the archived run by construction.
## 7. Conventions and decisions where the archived code left room

- **365-day metric window:** agent_b centres a 365-day window on the gap's middle day (+/- 182 days). For a 365-day gap this window coincides exactly with the gap (no flanking days), and that rule was kept verbatim; consequence: no-fill is uncomputable for every 365-day placement (the record is empty), so recon-vs-no-fill exists only up to 180 days.
- **Station-gap aggregation supports:** agent_b aggregated each metric over placements where the metric is defined under every scenario (its common support). Here the recon/clim/linear unit columns use the default support (placements where those three errors are defined) and err_missing uses the recon+missing support; the paired recon-vs-no-fill comparison is recomputed on that support in metric_error_summary.csv. The two supports coincide except where no-fill is uncomputable (month-swallowing amplitude, whole-window gaps), i.e. exactly the places agent_b silently dropped.
- **Placement sampling:** at most 5 archived placements per (station, gap_length), chosen evenly (np.linspace) over the archived rows sorted by gap_start; cells with fewer archived placements keep all of them (n_placements in station_gap_metrics.csv).
- **Budget random policy:** 100 draws of a top-20% treated set with numpy default_rng(seed 0), mean +/- sd over draws; deterministic policies use nlargest(k) with k = max(1, round(0.2 n)).  Budget pools are per-horizon placements with the metric's recon/clim/linear errors defined; the duration-only policy is absent at 365 days because P0 defines no duration-only prediction there.
- **Panel resolution:** each network's daily_wide_temperature.csv is read from second_confirmation/daily_qc/networks/<id>/ when present; the 15 chmi_* networks have no panel there and fall back to confirmation_daily_qc/networks/<id>/, the same directory the first-panel run read its panels from (read_temperature_panel applies identical day-insertion and numeric coercion in both cases).
- **Season column** is derived from the archived gap_start month with agent_b's season_label and matches the P0 season on every placement (0 mismatches).

## 8. Deliverables

- `run_script_146.py`
- `placement_metrics.csv`
- `station_gap_metrics.csv`
- `metric_error_summary.csv`
- `budget_within_horizon.csv`
- `sanity_checks.txt`
- `REPORT.md`
