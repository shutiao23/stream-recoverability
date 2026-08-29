# REPORT.md — revision v12 t04: continuous support-aware risk surface (agent B)

## Model

Hierarchical linear model of fitting-period empirical MAE, fitted by REML on artificial-gap placements (confirmation + development fit-loss panels):

`log(1+MAE) = network RE + station(network) RE + monotone linear spline f(log gap) + Fourier g(DOY) [2 harmonics] + covariates`

Covariates (z-scored): station climatology error (placement-mean), donor R2, ACF (acf_only), nearest-donor correlation. Spline = monotone linear spline in log gap (knots at the interior fitting durations 30/90 d; basis restricted so it is identifiable on the 4 observed fitting durations 7/30/90/180 d), all slope coefficients constrained >= 0 (SLSQP GLS refit, RE variances fixed at REML) so f is monotone nondecreasing; durations 14/60 are interpolated by the continuous curve, 365 is extrapolated (flagged, interval widened by (1 + extrapolation factor), abstention rule). Back-transformation uses Duan smearing (log-smear factor 0.042); predictive intervals are 90% on the log1p scale, lower bound clipped at 0.

Support context: the second panel's 57 networks / 224 stations have ZERO overlap with the fitting panels (93 networks / 376 stations), so every second-panel unit is an out-of-network, out-of-station transfer; the old network-mean fallback is therefore a CONSTANT (global fit mean) for all 1,446 units, and its pooled Spearman / network-level Spearman are undefined (NaN). RMSE/R2 remain defined and are reported.

Fit rows: 52,989 confirmation + 47,408 development (networks 93, stations 376).

### Variance components (log1p scale)
- network_random_intercept: var=0.0122 share=0.153
- station_random_intercept: var=0.0129 share=0.161
- residual: var=0.0547 share=0.686
- total: var=0.0798 share=1.000

Seasonal amplitude: 1st harmonic 0.0642, 2nd 0.0619 (log1p MAE units); unconstrained spline monotone on 7..365: True; constrained spline monotone: True (total rise 1.184 log1p).

### Fixed effects (REML, unconstrained baseline)

| term | coef | se | z | p |
|---|---|---|---|---|
| Intercept | 0.1248 | 0.0147 | 8.49 | 2.01e-17 |
| doy_sin1 | 0.0051 | 0.0010 | 4.82 | 1.43e-06 |
| doy_cos1 | -0.0640 | 0.0011 | -60.58 | 0.00e+00 |
| doy_sin2 | -0.0579 | 0.0010 | -55.34 | 0.00e+00 |
| doy_cos2 | -0.0220 | 0.0011 | -20.82 | 3.00e-96 |
| clim_error | 0.1041 | 0.0085 | 12.25 | 1.63e-34 |
| donor_r2_only | -0.0442 | 0.0184 | -2.41 | 1.61e-02 |
| acf_only | -0.0283 | 0.0023 | -12.49 | 8.66e-36 |
| nearest_donor_correlation | -0.0184 | 0.0179 | -1.03 | 3.03e-01 |
| log_gap_lin | 0.1289 | 0.0020 | 65.75 | 0.00e+00 |
| hinge1 | 0.0668 | 0.0028 | 24.19 | 3.17e-129 |
| hinge2 | 0.3614 | 0.0046 | 78.18 | 0.00e+00 |

Constrained (monotone) refit spline coefficients: 0.1294, 0.0668, 0.3612 (>= 0 enforced).

## Second panel (1,446 units) — complete panel

| predictor | pooled Spearman | network Spearman (mean) | cal slope | R2 | RMSE |
|---|---|---|---|---|---|
| risk_surface | 0.883 | 0.908 | 1.401 | 0.715 | 0.808 |
| empirical_transfer | 0.740 | 0.695 | 0.964 | 0.238 | 1.320 |
| network_mean_fallback | nan | nan | 0.718 | -0.098 | 1.585 |

## Interpolation (14, 60) and extrapolation (365)

| subset | predictor | n | pooled Spearman | cal slope | R2 | RMSE |
|---|---|---|---|---|---|---|
| interpolation_14_60 | risk_surface | 448 | 0.727 | 0.911 | 0.484 | 0.305 |
| interpolation_14_60 | empirical_transfer | 448 | 0.451 | 0.509 | -0.667 | 0.548 |
| interpolation_14_60 | network_mean_fallback | 448 | nan | 0.409 | -0.215 | 0.468 |
| extrapolation_365 | risk_surface | 124 | 0.349 | 0.683 | -0.798 | 2.173 |
| extrapolation_365 | empirical_transfer | 124 | 0.507 | 2.978 | -5.765 | 4.216 |
| extrapolation_365 | network_mean_fallback | 124 | nan | 2.422 | -6.646 | 4.482 |
| in_range_7_30_90_180 | risk_surface | 874 | 0.886 | 1.292 | 0.675 | 0.601 |
| in_range_7_30_90_180 | empirical_transfer | 874 | 0.945 | 0.944 | 0.813 | 0.455 |
| in_range_7_30_90_180 | network_mean_fallback | 874 | nan | 0.634 | -0.077 | 1.093 |

## Abstention rule

Abstain score = extrapolation factor (0 within [7,180] d, 0.22 at 365 d) + support distance / 90th percentile distance to nearest fitted station in standardized covariate space. Units with score > threshold abstain. Recommended default: abstain score > 1.08 (~8% of units; n released 1,332, network Spearman 0.919, pooled 0.900, calibration slope 1.471, RMSE 0.789).

| threshold | fraction abstained | n released | network Spearman | cal slope | pooled Spearman | RMSE |
|---|---|---|---|---|---|---|
| 0.142 | 0.976 | 34.0 | 0.962 | 1.036 | 0.868 | 0.423 |
| 0.193 | 0.947 | 76.0 | 0.970 | 1.408 | 0.894 | 0.515 |
| 0.237 | 0.923 | 112.0 | 0.952 | 1.308 | 0.886 | 0.451 |
| 0.249 | 0.902 | 142.0 | 0.959 | 1.280 | 0.891 | 0.429 |
| 0.279 | 0.849 | 218.0 | 0.963 | 1.259 | 0.893 | 0.473 |
| 0.315 | 0.800 | 289.0 | 0.957 | 1.274 | 0.897 | 0.447 |
| 0.344 | 0.746 | 367.0 | 0.948 | 1.279 | 0.902 | 0.439 |
| 0.381 | 0.703 | 429.0 | 0.944 | 1.359 | 0.898 | 0.490 |
| 0.414 | 0.647 | 510.0 | 0.949 | 1.342 | 0.903 | 0.480 |
| 0.454 | 0.601 | 577.0 | 0.945 | 1.365 | 0.907 | 0.514 |
| 0.485 | 0.551 | 649.0 | 0.940 | 1.386 | 0.904 | 0.535 |
| 0.513 | 0.500 | 723.0 | 0.942 | 1.421 | 0.911 | 0.583 |
| 0.538 | 0.451 | 794.0 | 0.938 | 1.458 | 0.914 | 0.616 |
| 0.584 | 0.396 | 873.0 | 0.942 | 1.454 | 0.916 | 0.656 |
| 0.620 | 0.352 | 937.0 | 0.944 | 1.456 | 0.919 | 0.652 |
| 0.670 | 0.301 | 1011.0 | 0.940 | 1.474 | 0.917 | 0.675 |
| 0.765 | 0.248 | 1087.0 | 0.940 | 1.521 | 0.919 | 0.767 |
| 0.840 | 0.203 | 1152.0 | 0.937 | 1.508 | 0.918 | 0.787 |
| 0.879 | 0.149 | 1230.0 | 0.925 | 1.500 | 0.904 | 0.781 |
| 1.025 | 0.099 | 1303.0 | 0.922 | 1.494 | 0.903 | 0.782 |
| 1.204 | 0.050 | 1373.0 | 0.918 | 1.460 | 0.900 | 0.789 |
| 2.193 | 0.001 | 1445.0 | 0.907 | 1.417 | 0.883 | 0.807 |

## First panel (1,440 units) — refit on confirmation fit losses only

| predictor | pooled Spearman | network Spearman (mean) | cal slope | R2 | RMSE |
|---|---|---|---|---|---|
| risk_surface | 0.857 | 0.894 | 1.141 | 0.744 | 0.633 |
| empirical_transfer | 0.633 | 0.617 | 0.792 | 0.145 | 1.156 |
| network_mean_fallback | 0.290 | nan | 0.640 | -0.015 | 1.259 |

Total runtime 0.2 min.

## Files
- `second_panel_predictions.csv`: per-unit surface predictions (mean, 90% interval, extrapolation factor, support distance, abstain score) for all 1,446 units
- `first_panel_predictions.csv`: per-unit predictions for the 1,440-unit cross-check
- `surface_fixed_effects.csv`, `surface_variance_components.csv`, `surface_duration_curve.csv`
- `evaluation_metrics_second_panel.csv`, `evaluation_metrics_subsets.csv`, `evaluation_metrics_first_panel.csv`
- `abstention_curve.csv`
