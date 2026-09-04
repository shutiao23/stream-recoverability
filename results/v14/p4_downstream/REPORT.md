# P4 — Downstream thermal-regime metrics at 7/30/90/180/365-day gaps

**Namespace:** `results/v14/p4_downstream/`
**Script:** `scripts/145_run_p4_downstream.py` (copy in `run_script_145.py`)
**Run:** 24 s scoring, 29 s total wall; 24 workers; XGBOOST_PARAMETERS unchanged (n_jobs = 1 inside workers).

## 1. Setup

- **Networks:** all 42 first-panel networks with archived B_union_D evaluation placements (placement_losses.csv) — the full route_a_confirmation first panel; panels read from confirmation_daily_qc/networks/<id>/daily_wide_temperature.csv.
- **Horizons:** 7/30/90/180/365 days. The archive has rows at all five horizons; the previous downstream run (agent_b, revision_v12) covered only 7/30/90 days on 15 networks.
- **Model:** the frozen XGBoost B_union_D recovery pipeline (development_recovery.XGBOOST_PARAMETERS, boundary temperature + donor columns, n_jobs = 1), retrained on the outer training years only (70% chronological year split, >= 365 training days). Per-placement reconstruction MAE reproduces the archived placement_losses values on identical placements to ~1e-12 (sanity_checks.txt), confirming the refit matches the archived runs.
- **Defaults on identical gaps:** (1) calendar-day climatology (day-of-year medians from the outer training years); (2) linear interpolation between the two flanking observed days (_boundary_values; note this ramp is also the model's boundary feature, so the linear default is the model's own minimal sub-model); (3) no-fill (gap days dropped, agent_b's uncomputable handling).
- **Placements:** archived evaluation geometry (B_union_D rows), evenly sampled at most 5 per (station, gap_length) across the archived placements of each cell.  All sampled placements were verified (observed truth and donors over the gap, observed boundary days, gap fully inside the evaluation years); violations are skipped and counted in sanity_checks.txt.
- **Metrics and window:** the ten thermal-regime metrics and the 365-day window centred on the gap middle day (+/- 182 days; the window coincides with the gap exactly for 365-day gaps) are imported unchanged from the agent_b script (scripts/rev_v12_t08_downstream_metrics_b.py).  Per-placement truth series = observed values; recon/clim/linear series replace the gap days; missing drops them.  Phase error is the circular day difference; station-gap phase aggregation uses the circular mean.
- **P0 join:** placement_predictions_first.csv joined 1:1 on (network_id, station_id, gap_length, placement, gap_start); the join has no duplicate keys and no unmatched placements.

## 2. Scale per horizon

- 7 d: 42 networks / 219 stations / 219 station-gap units / 1095 placements
- 30 d: 42 networks / 219 stations / 219 station-gap units / 1095 placements
- 90 d: 42 networks / 219 stations / 219 station-gap units / 1095 placements
- 180 d: 39 networks / 201 stations / 201 station-gap units / 993 placements
- 365 d: 32 networks / 144 stations / 144 station-gap units / 720 placements

Total: 4998 placements, 42 networks, 1002 station-gap units across the five horizons.

No-fill (missing) is uncomputable for every 365-day placement: the gap-centred 365-day window coincides exactly with the gap, so dropping the gap days empties the record (agent_b's uncomputable handling). Recon-vs-no-fill ratios therefore exist only for the 7/30/90/180-day horizons (and only per metric where month-swallowing gaps leave e.g. amplitude undefined); recon-vs-climatology and recon-vs-linear are reported for all five horizons.

## 3. Model benefit over the defaults (station-gap units)

Unit errors are means over placements (circular mean for phase). Benefit = mean(default error) - mean(recon error) on the same paired units (metric_error_summary.csv); positive means reconstruction reduces distortion relative to the default.

| horizon | metric | mean err recon | mean err clim | mean err linear | benefit over clim | benefit over linear | recon/clim | recon/linear | n units |
|---|---|---|---|---|---|---|---|---|---|
| 7 | annual_mean | 0.008 | 0.029 | 0.010 | +0.022 | +0.003 | 0.26 | 0.73 | 219 |
| 7 | amplitude | 0.025 | 0.104 | 0.036 | +0.079 | +0.010 | 0.24 | 0.71 | 218 |
| 7 | cdd10 | 1.184 | 3.858 | 1.544 | +2.675 | +0.360 | 0.31 | 0.77 | 219 |
| 7 | phase_doy | 0.252 | 0.478 | 0.189 | +0.226 | -0.063 | 0.53 | 1.34 | 219 |
| 7 | p90 | 0.008 | 0.027 | 0.010 | +0.019 | +0.003 | 0.29 | 0.74 | 219 |
| 30 | annual_mean | 0.043 | 0.082 | 0.059 | +0.039 | +0.017 | 0.52 | 0.72 | 219 |
| 30 | amplitude | 0.110 | 0.159 | 0.149 | +0.048 | +0.039 | 0.69 | 0.74 | 218 |
| 30 | cdd10 | 7.903 | 14.888 | 10.925 | +6.984 | +3.022 | 0.53 | 0.72 | 219 |
| 30 | phase_doy | 0.899 | 0.724 | 0.998 | -0.176 | +0.099 | 1.24 | 0.90 | 219 |
| 30 | p90 | 0.053 | 0.081 | 0.065 | +0.028 | +0.012 | 0.66 | 0.81 | 219 |
| 90 | annual_mean | 0.214 | 0.182 | 0.297 | -0.032 | +0.082 | 1.17 | 0.72 | 219 |
| 90 | amplitude | 0.521 | 0.415 | 0.714 | -0.106 | +0.193 | 1.26 | 0.73 | 218 |
| 90 | cdd10 | 41.301 | 37.126 | 56.399 | -4.176 | +15.097 | 1.11 | 0.73 | 219 |
| 90 | phase_doy | 4.379 | 3.875 | 5.757 | -0.505 | +1.377 | 1.13 | 0.76 | 219 |
| 90 | p90 | 0.273 | 0.224 | 0.345 | -0.050 | +0.072 | 1.22 | 0.79 | 219 |
| 180 | annual_mean | 0.997 | 0.353 | 1.503 | -0.645 | +0.506 | 2.83 | 0.66 | 201 |
| 180 | amplitude | 2.724 | 1.026 | 4.061 | -1.699 | +1.337 | 2.66 | 0.67 | 201 |
| 180 | cdd10 | 237.354 | 87.203 | 364.881 | -150.151 | +127.527 | 2.72 | 0.65 | 201 |
| 180 | phase_doy | 15.168 | 9.186 | 23.474 | -5.983 | +8.306 | 1.65 | 0.65 | 201 |
| 180 | p90 | 1.586 | 0.680 | 2.127 | -0.906 | +0.541 | 2.33 | 0.75 | 201 |
| 365 | annual_mean | 3.038 | 0.611 | 4.676 | -2.427 | +1.638 | 4.97 | 0.65 | 144 |
| 365 | amplitude | 9.349 | 1.354 | 14.184 | -7.995 | +4.835 | 6.91 | 0.66 | 144 |
| 365 | cdd10 | 817.715 | 141.964 | 1175.246 | -675.751 | +357.531 | 5.76 | 0.70 | 144 |
| 365 | phase_doy | 15.922 | 16.827 | 94.880 | +0.904 | +78.958 | 0.95 | 0.17 | 144 |
| 365 | p90 | 5.638 | 1.266 | 8.057 | -4.373 | +2.418 | 4.46 | 0.70 | 144 |

## 4. The 180- and 365-day numbers missing before

| horizon | metric | n units | recon | clim | linear | benefit clim | benefit linear | recon/clim | recon/linear |
|---|---|---|---|---|---|---|---|---|---|
| 180 | annual_mean | 201 | 0.997 | 0.353 | 1.503 | -0.645 | +0.506 | 2.83 | 0.66 |
| 180 | summer_mean | 201 | 1.410 | 0.595 | 2.052 | -0.814 | +0.642 | 2.37 | 0.69 |
| 180 | amplitude | 201 | 2.724 | 1.026 | 4.061 | -1.699 | +1.337 | 2.66 | 0.67 |
| 180 | phase_doy | 201 | 15.168 | 9.186 | 23.474 | -5.983 | +8.306 | 1.65 | 0.65 |
| 180 | p90 | 201 | 1.586 | 0.680 | 2.127 | -0.906 | +0.541 | 2.33 | 0.75 |
| 180 | summer_max | 201 | 1.835 | 0.797 | 2.362 | -1.038 | +0.527 | 2.30 | 0.78 |
| 180 | exceed_days_20 | 201 | 15.282 | 8.180 | 18.809 | -7.102 | +3.527 | 1.87 | 0.81 |
| 180 | exceed_days_25 | 201 | 1.491 | 1.278 | 1.543 | -0.212 | +0.053 | 1.17 | 0.97 |
| 180 | cdd10 | 201 | 237.354 | 87.203 | 364.881 | -150.151 | +127.527 | 2.72 | 0.65 |
| 180 | trend_slope | 201 | 0.644 | 0.447 | 0.891 | -0.197 | +0.247 | 1.44 | 0.72 |
| 365 | annual_mean | 144 | 3.038 | 0.611 | 4.676 | -2.427 | +1.638 | 4.97 | 0.65 |
| 365 | summer_mean | 144 | 5.240 | 1.138 | 7.962 | -4.102 | +2.722 | 4.60 | 0.66 |
| 365 | amplitude | 144 | 9.349 | 1.354 | 14.184 | -7.995 | +4.835 | 6.91 | 0.66 |
| 365 | phase_doy | 144 | 15.922 | 16.827 | 94.880 | +0.904 | +78.958 | 0.95 | 0.17 |
| 365 | p90 | 144 | 5.638 | 1.266 | 8.057 | -4.373 | +2.418 | 4.46 | 0.70 |
| 365 | summer_max | 144 | 7.150 | 2.089 | 10.455 | -5.060 | +3.306 | 3.42 | 0.68 |
| 365 | exceed_days_20 | 144 | 37.432 | 14.674 | 54.149 | -22.758 | +16.717 | 2.55 | 0.69 |
| 365 | exceed_days_25 | 144 | 3.985 | 2.283 | 4.908 | -1.701 | +0.924 | 1.75 | 0.81 |
| 365 | cdd10 | 144 | 817.715 | 141.964 | 1175.246 | -675.751 | +357.531 | 5.76 | 0.70 |
| 365 | trend_slope | 144 | 5.910 | 1.184 | 9.041 | -4.727 | +3.130 | 4.99 | 0.65 |

### 4.1 Where the model is net-harmful versus a default

Net-harmful = unit-mean |recon error| > unit-mean |default error| for that horizon x metric (same paired units, so benefit < 0).
- horizon 30 d vs climatology: phase_doy (-0.18 days); summer_max (-0.00 degC)
- horizon 90 d vs climatology: annual_mean (-0.03 degC); amplitude (-0.11 degC); phase_doy (-0.50 days); p90 (-0.05 degC); summer_max (-0.11 degC); exceed_days_20 (-0.17 count); exceed_days_25 (-0.17 count); cdd10 (-4.18 degC-days)
- horizon 180 d vs climatology: annual_mean (-0.64 degC); summer_mean (-0.81 degC); amplitude (-1.70 degC); phase_doy (-5.98 days); p90 (-0.91 degC); summer_max (-1.04 degC); exceed_days_20 (-7.10 count); exceed_days_25 (-0.21 count); cdd10 (-150.15 degC-days); trend_slope (-0.20 degC/yr)
- horizon 365 d vs climatology: annual_mean (-2.43 degC); summer_mean (-4.10 degC); amplitude (-8.00 degC); p90 (-4.37 degC); summer_max (-5.06 degC); exceed_days_20 (-22.76 count); exceed_days_25 (-1.70 count); cdd10 (-675.75 degC-days); trend_slope (-4.73 degC/yr)
- horizon 7 d vs linear: phase_doy (-0.06 days)

Reading: versus the climatology default the model is net-harmful from 90-day gaps upward on most metrics, and at 180/365 days it is net-harmful on every metric except phase at 365 days.  Versus the linear default the model is net-harmful only marginally (phase at 7 days, -0.06 d; summer_max at 30 days, ~0; nothing beyond), and the benefit over linear grows with the horizon.  Several 7/30-day entries are small in absolute terms (phase ~0.1-0.5 d, summer_max ~0.0-0.1 degC); the 90/180/365-day entries are large on every scale.

### 4.2 Model daily reconstruction MAE (context)

Mean |prediction - truth| over the gap days themselves (mae_deg_c in placement_metrics.csv), reproducing the archived placement_losses values exactly:

- 7 d: 0.43 degC (n = 1095)
- 30 d: 0.69 degC (n = 1095)
- 90 d: 1.08 degC (n = 1095)
- 180 d: 2.23 degC (n = 993)
- 365 d: 4.00 degC (n = 720)

### 4.3 No-fill comparison (where no-fill is computable)

Mean recon error vs mean no-fill error on the paired support (n_missing_units units; recon recomputed on that support); ratio < 1 means reconstruction repairs the truncated record.
| horizon | metric | n missing units | recon (paired) | no-fill | recon/no-fill |
|---|---|---|---|---|---|
| 7 | annual_mean | 219 | 0.008 | 0.127 | 0.06 |
| 7 | summer_mean | 218 | 0.009 | 0.033 | 0.25 |
| 7 | amplitude | 218 | 0.025 | 0.099 | 0.26 |
| 7 | phase_doy | 219 | 0.252 | 0.477 | 0.53 |
| 7 | p90 | 219 | 0.008 | 0.060 | 0.13 |
| 7 | summer_max | 218 | 0.012 | 0.013 | 0.96 |
| 7 | exceed_days_20 | 219 | 0.090 | 0.889 | 0.10 |
| 7 | exceed_days_25 | 219 | 0.032 | 0.168 | 0.19 |
| 7 | cdd10 | 219 | 1.184 | 21.134 | 0.06 |
| 7 | trend_slope | 219 | 0.019 | 0.111 | 0.17 |
| 30 | annual_mean | 219 | 0.043 | 0.532 | 0.08 |
| 30 | summer_mean | 218 | 0.042 | 0.101 | 0.41 |
| 30 | amplitude | 218 | 0.023 | 0.057 | 0.39 |
| 30 | phase_doy | 219 | 0.899 | 1.318 | 0.68 |
| 30 | p90 | 219 | 0.053 | 0.213 | 0.25 |
| 30 | summer_max | 218 | 0.044 | 0.047 | 0.94 |
| 30 | exceed_days_20 | 219 | 0.661 | 3.310 | 0.20 |
| 30 | exceed_days_25 | 219 | 0.231 | 0.477 | 0.48 |
| 30 | cdd10 | 219 | 7.903 | 92.048 | 0.09 |
| 30 | trend_slope | 219 | 0.080 | 0.491 | 0.16 |
| 90 | annual_mean | 219 | 0.214 | 1.577 | 0.14 |
| 90 | summer_mean | 218 | 0.165 | 0.288 | 0.57 |
| 90 | amplitude | 211 | 0.042 | 0.082 | 0.50 |
| 90 | phase_doy | 219 | 4.379 | 6.845 | 0.64 |
| 90 | p90 | 219 | 0.273 | 0.960 | 0.28 |
| 90 | summer_max | 218 | 0.259 | 0.308 | 0.84 |
| 90 | exceed_days_20 | 219 | 3.053 | 10.715 | 0.28 |
| 90 | exceed_days_25 | 219 | 0.689 | 1.183 | 0.58 |
| 90 | cdd10 | 219 | 41.301 | 291.161 | 0.14 |
| 90 | trend_slope | 219 | 0.196 | 1.853 | 0.11 |
| 180 | annual_mean | 201 | 0.997 | 2.802 | 0.36 |
| 180 | summer_mean | 201 | 0.509 | 0.702 | 0.73 |
| 180 | amplitude | 15 | 0.609 | 0.510 | 1.19 |
| 180 | phase_doy | 201 | 15.168 | 25.504 | 0.59 |
| 180 | p90 | 201 | 1.586 | 2.803 | 0.57 |
| 180 | summer_max | 201 | 0.542 | 0.570 | 0.95 |
| 180 | exceed_days_20 | 201 | 15.282 | 23.187 | 0.66 |
| 180 | exceed_days_25 | 201 | 1.491 | 1.807 | 0.82 |
| 180 | cdd10 | 201 | 237.354 | 633.044 | 0.37 |
| 180 | trend_slope | 201 | 0.644 | 2.974 | 0.22 |

## 5. Budget within horizon (budget_within_horizon.csv)

Top-20% placement budgets within each horizon (treatment = fill the gap with the model). Per metric: mean over the treated placements of err_clim - err_recon and err_linear - err_recon (model benefit over the climatology and the linear default, on the metric's own scale) and the harmful-rate shares (treated placements where the model is worse than the default). Policies: by P0 diff_prediction, by duration_only_prediction, by risk_prediction, and random (mean over 100 draws, seed 0; sd over draws in the *_sd columns). The duration-only predictor is undefined at 365 days in the P0 tables (no directly supported 365-day units), so that policy exists only at 7/30/90/180.

### 5.1 annual_mean

| horizon | policy | n pool | n treated | benefit clim | harmful clim | benefit linear | harmful linear |
|---|---|---|---|---|---|---|---|
| 7 | diff | 1095 | 219 | +0.026 | 0.151 | +0.005 | 0.242 |
| 7 | duration | 1095 | 219 | +0.025 | 0.105 | +0.002 | 0.333 |
| 7 | risk | 1095 | 219 | +0.024 | 0.196 | +0.002 | 0.329 |
| 7 | random | 1095 | 219 | +0.022 | 0.142 | +0.003 | 0.283 |
| 30 | diff | 1095 | 219 | +0.059 | 0.269 | +0.025 | 0.164 |
| 30 | duration | 1095 | 219 | +0.047 | 0.283 | +0.017 | 0.260 |
| 30 | risk | 1095 | 219 | +0.051 | 0.370 | +0.019 | 0.228 |
| 30 | random | 1095 | 219 | +0.039 | 0.299 | +0.017 | 0.210 |
| 90 | diff | 1095 | 219 | +0.028 | 0.452 | +0.117 | 0.100 |
| 90 | duration | 1095 | 219 | +0.024 | 0.470 | +0.069 | 0.132 |
| 90 | risk | 1095 | 219 | -0.101 | 0.653 | +0.081 | 0.137 |
| 90 | random | 1095 | 219 | -0.033 | 0.530 | +0.083 | 0.127 |
| 180 | diff | 993 | 199 | -0.661 | 0.779 | +0.719 | 0.030 |
| 180 | duration | 993 | 199 | -0.467 | 0.734 | +0.383 | 0.055 |
| 180 | risk | 993 | 199 | -1.072 | 0.889 | +0.519 | 0.040 |
| 180 | random | 993 | 199 | -0.650 | 0.806 | +0.507 | 0.046 |
| 365 | diff | 720 | 144 | -1.566 | 0.889 | +1.793 | 0.049 |
| 365 | risk | 720 | 144 | -2.754 | 0.917 | +1.200 | 0.042 |
| 365 | random | 720 | 144 | -2.435 | 0.914 | +1.629 | 0.033 |

### 5.2 amplitude

| horizon | policy | n pool | n treated | benefit clim | harmful clim | benefit linear | harmful linear |
|---|---|---|---|---|---|---|---|
| 7 | diff | 923 | 185 | +0.078 | 0.027 | +0.011 | 0.065 |
| 7 | duration | 923 | 185 | +0.086 | 0.027 | +0.013 | 0.114 |
| 7 | risk | 923 | 185 | +0.061 | 0.027 | +0.005 | 0.086 |
| 7 | random | 923 | 185 | +0.080 | 0.044 | +0.010 | 0.086 |
| 30 | diff | 932 | 186 | +0.050 | 0.075 | +0.040 | 0.038 |
| 30 | duration | 932 | 186 | +0.068 | 0.091 | +0.041 | 0.091 |
| 30 | risk | 932 | 186 | +0.062 | 0.124 | +0.021 | 0.113 |
| 30 | random | 932 | 186 | +0.050 | 0.127 | +0.039 | 0.082 |
| 90 | diff | 978 | 196 | -0.020 | 0.270 | +0.282 | 0.036 |
| 90 | duration | 978 | 196 | -0.040 | 0.367 | +0.209 | 0.117 |
| 90 | risk | 978 | 196 | -0.221 | 0.362 | +0.183 | 0.184 |
| 90 | random | 978 | 196 | -0.102 | 0.339 | +0.193 | 0.106 |
| 180 | diff | 919 | 184 | -1.647 | 0.723 | +1.874 | 0.038 |
| 180 | duration | 919 | 184 | -1.535 | 0.777 | +0.950 | 0.054 |
| 180 | risk | 919 | 184 | -3.396 | 0.842 | +1.448 | 0.060 |
| 180 | random | 919 | 184 | -1.703 | 0.767 | +1.361 | 0.052 |
| 365 | diff | 720 | 144 | -8.029 | 0.958 | +6.612 | 0.000 |
| 365 | risk | 720 | 144 | -10.156 | 0.993 | +4.044 | 0.007 |
| 365 | random | 720 | 144 | -7.996 | 0.979 | +4.820 | 0.001 |

## 6. Consistency with the archived agent_b run (15 networks)

agent_b (revision_v12, horizons 7/30/90) used the same 15-network reviewer-completion roster; its 351 station-gap cells are exactly the archived route_a_confirmation cells of those networks, so every one recurs here (only the sampled gap starts differ: our even <=5 subsample of the 20 archived placements per cell versus agent_b's own evenly spread 5 over all candidate windows).

agent_b's station-gap errors are means over the placements where the metric is defined under reconstruction AND no-fill (its common support).  We compare against our means on the same support (`support_b`: recon and no-fill errors both finite) and also report our default support (`support_a`: recon/clim/linear finite), which additionally includes the month-swallowing placements for which no-fill amplitude is undefined (excluded by agent_b).  The two supports coincide for every no-fill-insensitive metric.

| horizon | metric | shared units | agent_b mean recon | P4 mean recon (A) | ratio A/agent_b | rho A | P4 mean recon (B) | ratio B/agent_b | rho B |
|---|---|---|---|---|---|---|---|---|---|
| 7 | annual_mean | 117 | 0.007 | 0.007 | 0.99 | 0.67 | 0.007 | 0.99 | 0.67 |
| 7 | summer_mean | 117 | 0.005 | 0.005 | 0.94 | 0.15 | 0.005 | 0.94 | 0.15 |
| 7 | amplitude | 117 | 0.022 | 0.024 | 1.11 | 0.74 | 0.024 | 1.11 | 0.74 |
| 7 | phase_doy | 117 | 0.044 | 0.026 | 0.58 | 0.39 | 0.026 | 0.58 | 0.39 |
| 7 | p90 | 117 | 0.004 | 0.008 | 1.82 | 0.01 | 0.008 | 1.82 | 0.01 |
| 7 | summer_max | 117 | 0.003 | 0.009 | 2.52 | -0.05 | 0.009 | 2.52 | -0.05 |
| 7 | exceed_days_20 | 117 | 0.074 | 0.074 | 1.00 | 0.24 | 0.074 | 1.00 | 0.24 |
| 7 | exceed_days_25 | 117 | 0.031 | 0.015 | 0.50 | 0.52 | 0.015 | 0.50 | 0.52 |
| 7 | cdd10 | 117 | 1.187 | 0.910 | 0.77 | 0.34 | 0.910 | 0.77 | 0.34 |
| 7 | trend_slope | 117 | 0.016 | 0.016 | 1.00 | 1.00 | 0.016 | 1.00 | 1.00 |
| 30 | annual_mean | 117 | 0.050 | 0.042 | 0.84 | 0.80 | 0.042 | 0.84 | 0.80 |
| 30 | summer_mean | 117 | 0.076 | 0.039 | 0.51 | 0.66 | 0.039 | 0.51 | 0.66 |
| 30 | amplitude | 117 | 0.021 | 0.095 | 4.64 | 0.50 | 0.019 | 0.92 | 0.00 |
| 30 | phase_doy | 117 | 1.275 | 0.445 | 0.35 | 0.13 | 0.445 | 0.35 | 0.13 |
| 30 | p90 | 117 | 0.064 | 0.049 | 0.77 | 0.44 | 0.049 | 0.77 | 0.44 |
| 30 | summer_max | 117 | 0.089 | 0.020 | 0.23 | -0.10 | 0.020 | 0.23 | -0.10 |
| 30 | exceed_days_20 | 117 | 1.099 | 0.557 | 0.51 | 0.45 | 0.557 | 0.51 | 0.45 |
| 30 | exceed_days_25 | 117 | 0.289 | 0.241 | 0.83 | 0.82 | 0.241 | 0.83 | 0.82 |
| 30 | cdd10 | 117 | 11.048 | 7.259 | 0.66 | 0.58 | 7.259 | 0.66 | 0.58 |
| 30 | trend_slope | 117 | 0.079 | 0.080 | 1.01 | 0.98 | 0.080 | 1.01 | 0.98 |
| 90 | annual_mean | 117 | 0.223 | 0.215 | 0.96 | 0.81 | 0.215 | 0.96 | 0.81 |
| 90 | summer_mean | 117 | 0.212 | 0.236 | 1.11 | 0.50 | 0.193 | 0.91 | 0.45 |
| 90 | amplitude | 108 | 0.077 | 0.433 | 5.64 | -0.02 | 0.052 | 0.67 | 0.11 |
| 90 | phase_doy | 117 | 5.765 | 4.300 | 0.75 | 0.40 | 4.300 | 0.75 | 0.40 |
| 90 | p90 | 117 | 0.354 | 0.298 | 0.84 | 0.60 | 0.298 | 0.84 | 0.60 |
| 90 | summer_max | 117 | 0.280 | 0.382 | 1.36 | 0.35 | 0.300 | 1.07 | 0.18 |
| 90 | exceed_days_20 | 117 | 5.509 | 3.350 | 0.61 | 0.81 | 3.350 | 0.61 | 0.81 |
| 90 | exceed_days_25 | 117 | 1.227 | 0.750 | 0.61 | 0.68 | 0.750 | 0.61 | 0.68 |
| 90 | cdd10 | 117 | 52.928 | 43.499 | 0.82 | 0.83 | 43.499 | 0.82 | 0.83 |
| 90 | trend_slope | 117 | 0.154 | 0.153 | 0.99 | 0.87 | 0.153 | 0.99 | 0.87 |

Reading: the overlap is complete (all 351 agent_b cells recur; 117 per horizon).  On the agent_b-comparable support (B), the per-horizon mean recon errors agree well for the integrated, no-fill-insensitive metrics - annual_mean ratios 0.99/0.84/0.96 and trend_slope ratios 1.00/1.01/0.99 at 7/30/90 d, cdd10 0.77/0.66/0.82 - and unit-level Spearman is strong for these metrics (annual_mean 0.67-0.81, trend_slope 0.87-1.00).  Larger relative deviations concentrate in metrics whose distortion is set by a few days inside the gap (single hottest day, month-swallowing geometry, peak day): each cell contributes a mean over only ~5 sampled placements, so for summer_max, amplitude, phase and p90 (at 7 d) the per-cell means are placement-sample noise even though both runs reconstruct identically.  The default support (A) additionally includes the month-swallowing placements agent_b excluded by its no-fill common-support rule, which is why amplitude means lie far above agent_b's on A (90 d: 0.433 vs 0.077) while agreeing on B (0.052 vs 0.077); the magnitude of the gap is itself informative - month-swallowing gaps are where amplitude distortion concentrates.

## 7. Conventions and decisions where the archived code left room

- **365-day metric window:** agent_b centres a 365-day window on the gap's middle day (+/- 182 days). For a 365-day gap this window coincides exactly with the gap (no flanking days), and that rule was kept verbatim; consequence: no-fill is uncomputable for every 365-day placement (the record is empty), so recon-vs-no-fill exists only up to 180 days.
- **Station-gap aggregation supports:** agent_b aggregated each metric over placements where the metric is defined under every scenario (its common support). Here the recon/clim/linear unit columns use the default support (placements where those three errors are defined) and err_missing uses the recon+missing support; the paired recon-vs-no-fill comparison is recomputed on that support in metric_error_summary.csv. The two supports coincide except where no-fill is uncomputable (month-swallowing amplitude, whole-window gaps), i.e. exactly the places agent_b silently dropped.
- **Placement sampling:** at most 5 archived placements per (station, gap_length), chosen evenly (np.linspace) over the archived rows sorted by gap_start; cells with fewer archived placements keep all of them (n_placements in station_gap_metrics.csv).
- **Budget random policy:** 100 draws of a top-20% treated set with numpy default_rng(seed 0), mean +/- sd over draws; deterministic policies use nlargest(k) with k = max(1, round(0.2 n)).  Budget pools are per-horizon placements with the metric's recon/clim/linear errors defined; the duration-only policy is absent at 365 days because P0 defines no duration-only prediction there.
- **Season column** is derived from the archived gap_start month with agent_b's season_label and matches the P0 season on every placement (0 mismatches).

## 8. Deliverables

- `run_script_145.py`
- `placement_metrics.csv`
- `station_gap_metrics.csv`
- `metric_error_summary.csv`
- `budget_within_horizon.csv`
- `agent_b_overlap_comparison.csv`
- `sanity_checks.txt`
- `REPORT.md`
