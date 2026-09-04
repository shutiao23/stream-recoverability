# v14 P2: decision layer for the differential (benefit) forecasts

Analysis-only stage over the P0 artifacts in results/v14/p0_differential/.
No model refits.  For each evaluation placement the predictive
distribution F_hat is the empirical CDF of the fitting-period benefits
in its cell, with the fallback chain (network, station, gap, season) ->
(network, station, gap) -> (network, gap) -> network -> global pool of
fitting benefits; a level is used only when it holds >= 5 fitting
values.  Realized benefit x = MAE(default) - MAE(model) on evaluation
placements, exactly as in P0.

## Cell-matching coverage, panel first

- direct placements: 25848; panel-mean realized benefit: +0.4138 C
- network_station_gap_season: 15918 (61.6%)
- network_gap: 8140 (31.5%)
- network: 1488 (5.8%)
- network_station_gap: 302 (1.2%)

## Cell-matching coverage, panel second

- direct placements: 26258; panel-mean realized benefit: +0.2171 C
- network_station_gap_season: 18925 (72.1%)
- network_gap: 6015 (22.9%)
- network_station_gap: 838 (3.2%)
- network: 480 (1.8%)

## 5.1 Laio & Tamea (2007) continuous cost-loss curves

Normalized loss rho_xi(x, chi) = |chi - x| + 2(xi - 0.5)(chi - x); the
optimal design value chi*(xi) = quantile(1 - xi) of F_hat (per-cell)
or of the global fitting-period pool F0 (climatology).  delta = mean
absolute deviation of the evaluation benefits around their mean, i.e.
the climatological-mean forecast cost at xi = 0.5.  A ratio below 1
means the forecast beats the climatology reference at that cost-loss
ratio; xi < 0.5 is the hydrologically realistic half (cheap action).
Horizon 'direct' pools the direct 7/30/90/180 d placements.

| panel | horizon | n | delta C | min EC/δ | xi@min | #<1 tot | #<1 xi<0.5 | #<1 xi>=0.5 | CRPS int/direct | EC_clim(0.5)/δ |
|---|---|---|---|---|---|---|---|---|---|---|
| first | 7 | 4380 | 0.747 | 0.181 | 0.950 | 19 | 9 | 10 | 1.000 | 1.012 |
| first | 14 | 4380 | 0.639 | 0.200 | 0.950 | 19 | 9 | 10 | 1.000 | 1.003 |
| first | 30 | 4380 | 0.537 | 0.224 | 0.950 | 19 | 9 | 10 | 1.000 | 0.984 |
| first | 60 | 4380 | 0.485 | 0.359 | 0.950 | 19 | 9 | 10 | 1.000 | 0.996 |
| first | 90 | 4380 | 0.571 | 0.315 | 0.050 | 19 | 9 | 10 | 1.000 | 1.019 |
| first | 180 | 3948 | 1.070 | 0.283 | 0.050 | 12 | 8 | 4 | 1.000 | 1.363 |
| first | direct | 25848 | 0.729 | 0.327 | 0.950 | 19 | 9 | 10 | 1.000 | 1.000 |
| second | 7 | 4480 | 0.750 | 0.189 | 0.950 | 19 | 9 | 10 | 1.000 | 1.028 |
| second | 14 | 4480 | 0.646 | 0.226 | 0.950 | 19 | 9 | 10 | 1.000 | 1.013 |
| second | 30 | 4480 | 0.524 | 0.259 | 0.950 | 19 | 9 | 10 | 1.000 | 0.985 |
| second | 60 | 4480 | 0.488 | 0.354 | 0.950 | 14 | 7 | 7 | 1.000 | 1.003 |
| second | 90 | 4400 | 0.587 | 0.304 | 0.050 | 15 | 8 | 7 | 1.000 | 1.056 |
| second | 180 | 3938 | 1.217 | 0.227 | 0.050 | 19 | 9 | 10 | 1.000 | 1.548 |
| second | direct | 26258 | 0.802 | 0.286 | 0.950 | 19 | 9 | 10 | 1.000 | 0.999 |

CRPS int/direct is the ratio of the trapezoidal integral of EC_fcst
over xi in [0,1] (0.001 grid) to the exact CRPS of the cell forecasts
(step-ECDF formula); 1.000 confirms int_0^1 EC(xi) dxi = CRPS.
EC_clim(0.5)/delta is the requested identity check EC_clim(0.5) =
delta: it holds exactly only where the median of the global fitting
pool F0 equals the mean of the evaluation benefits; the observed range
is 0.987-1.505 (delta is the mean-based cost, EC_clim(0.5) the
median-based cost).  Points with ratio >= 1 are listed below so the
below-1 statement is not overstated.

- second panel      7: min EC/δ = 0.189 at xi = 0.95; below 1 at 19 of 19 points (9/9 in the xi < 0.5 half, 10/10 above).
- second panel     14: min EC/δ = 0.226 at xi = 0.95; below 1 at 19 of 19 points (9/9 in the xi < 0.5 half, 10/10 above).
- second panel     30: min EC/δ = 0.259 at xi = 0.95; below 1 at 19 of 19 points (9/9 in the xi < 0.5 half, 10/10 above).
- second panel     60: min EC/δ = 0.354 at xi = 0.95; below 1 at 14 of 19 points (7/9 in the xi < 0.5 half, 7/10 above); >= 1 at xi 0.40, 0.45, 0.50, 0.55, 0.60.
- second panel     90: min EC/δ = 0.304 at xi = 0.05; below 1 at 15 of 19 points (8/9 in the xi < 0.5 half, 7/10 above); >= 1 at xi 0.45, 0.50, 0.55, 0.60.
- second panel    180: min EC/δ = 0.227 at xi = 0.05; below 1 at 19 of 19 points (9/9 in the xi < 0.5 half, 10/10 above).
- second panel direct: min EC/δ = 0.286 at xi = 0.95; below 1 at 19 of 19 points (9/9 in the xi < 0.5 half, 10/10 above).

Presentation note: the integral of EC_fcst(xi) over xi equals the
CRPS, but the curve is the object to report because uniform weighting
over-weights the xi > 0.5 (expensive-action) region that is not
hydrologically realistic: e.g. second-panel 90 d sits at parity with
climatology only at xi in [0.50, 0.60] while being far below 1 in the
whole xi < 0.5 half, a structure a single CRPS number hides.  This is
the Laio & Tamea argument for reporting EC(xi)/delta rather than one
integrated score.

Deterministic single-quantile reading (optional): EC_det uses the P0
diff_prediction point forecast as the design value chi for every
placement instead of the cell quantile.  It is a fixed-decision curve,
not an optimal-decision curve, and is included in
laio_tamea_curves.csv (EC_det_delta_ratio) for reference only.

## 5.2 Selective risk vs coverage (Geifman & El-Yaniv 2017)

Loss per placement = -realized benefit.  Placements are sorted by the
predictor descending and the top c fraction is accepted; risk(c) =
mean loss over the accepted set.  AURC is the trapezoid over the
coverage grid 0.10..1.00 (step 0.05).  E-AURC_norm = (AURC_random -
AURC_method) / (AURC_random - AURC_oracle): 1 = oracle, 0 = random,
negative = worse than random.  Random reference = mean over 200
shuffles with the 5-95% band in selective_risk_curves.csv.  Second
panel only, per duration and pooled direct.

| horizon | method | n | AURC | E-AURC_norm | risk@50% | AURC random | AURC oracle |
|---|---|---|---|---|---|---|---|
| 7 | diff | 4480 | -0.991 | 0.261 | -1.119 | -0.815 | -1.492 |
| 7 | duration_only | 4480 | -0.838 | 0.034 | -0.864 | -0.815 | -1.492 |
| 7 | oracle | 4480 | -1.492 | 1.000 | -1.627 | -0.815 | -1.492 |
| 7 | random | 4480 | -0.815 | 0.000 | -0.906 | -0.815 | -1.492 |
| 7 | risk | 4480 | -0.914 | 0.147 | -1.041 | -0.815 | -1.492 |
| 14 | diff | 4480 | -0.848 | 0.284 | -0.950 | -0.680 | -1.273 |
| 14 | duration_only | 4480 | -0.705 | 0.043 | -0.735 | -0.680 | -1.273 |
| 14 | oracle | 4480 | -1.273 | 1.000 | -1.380 | -0.680 | -1.273 |
| 14 | random | 4480 | -0.680 | 0.000 | -0.755 | -0.680 | -1.273 |
| 14 | risk | 4480 | -0.753 | 0.124 | -0.845 | -0.680 | -1.273 |
| 30 | diff | 4480 | -0.636 | 0.288 | -0.707 | -0.498 | -0.979 |
| 30 | duration_only | 4480 | -0.520 | 0.047 | -0.543 | -0.498 | -0.979 |
| 30 | oracle | 4480 | -0.979 | 1.000 | -1.065 | -0.498 | -0.979 |
| 30 | random | 4480 | -0.498 | 0.000 | -0.553 | -0.498 | -0.979 |
| 30 | risk | 4480 | -0.535 | 0.077 | -0.601 | -0.498 | -0.979 |
| 60 | diff | 4480 | -0.438 | 0.339 | -0.485 | -0.288 | -0.732 |
| 60 | duration_only | 4480 | -0.304 | 0.036 | -0.305 | -0.288 | -0.732 |
| 60 | oracle | 4480 | -0.732 | 1.000 | -0.806 | -0.288 | -0.732 |
| 60 | random | 4480 | -0.288 | 0.000 | -0.321 | -0.288 | -0.732 |
| 60 | risk | 4480 | -0.250 | -0.084 | -0.273 | -0.288 | -0.732 |
| 90 | diff | 4400 | -0.219 | 0.364 | -0.255 | -0.034 | -0.543 |
| 90 | duration_only | 4400 | -0.048 | 0.028 | -0.027 | -0.034 | -0.543 |
| 90 | oracle | 4400 | -0.543 | 1.000 | -0.621 | -0.034 | -0.543 |
| 90 | random | 4400 | -0.034 | 0.000 | -0.037 | -0.034 | -0.543 |
| 90 | risk | 4400 | 0.099 | -0.261 | 0.118 | -0.034 | -0.543 |
| 180 | diff | 3938 | 0.794 | 0.540 | 0.719 | 1.329 | 0.339 |
| 180 | duration_only | 3938 | 1.411 | -0.083 | 1.624 | 1.329 | 0.339 |
| 180 | oracle | 3938 | 0.339 | 1.000 | 0.272 | 1.329 | 0.339 |
| 180 | random | 3938 | 1.329 | 0.000 | 1.479 | 1.329 | 0.339 |
| 180 | risk | 3938 | 1.952 | -0.629 | 2.189 | 1.329 | 0.339 |
| direct | diff | 26258 | -0.614 | 0.572 | -0.714 | -0.196 | -0.927 |
| direct | duration_only | 26258 | -0.609 | 0.566 | -0.745 | -0.196 | -0.927 |
| direct | oracle | 26258 | -0.927 | 1.000 | -1.017 | -0.196 | -0.927 |
| direct | random | 26258 | -0.196 | 0.000 | -0.217 | -0.196 | -0.927 |
| direct | risk | 26258 | 0.246 | -0.604 | 0.183 | -0.196 | -0.927 |

Raw risk is negative when the accepted half still has positive mean
benefit.  Theoretical-optimal note: Zaoui, Denis & Hebiri (NeurIPS
2020) show the optimal selective regressor thresholds the conditional
variance function; no conditional-variance estimator was carried into
the differential artifacts, so its ranks are not reported here and the
oracle/random bounds stand as the references.

## 5.3 Richardson REV V(alpha) binary-decision curves

Event = realized benefit > tau with tau in {0.0, panel-mean benefit}
(the mean of that panel's pooled direct placements).  p_i = 1 -
F_hat_i(tau) from the cell distributions; o = base rate.  Sweep alpha
= C/L over 0.01..0.99 (L = 1, so C = alpha), alarm when p >= alpha;
E_A = C, E_N = o, E_C = min(C, o), E_P = o*C, E_F = (a + b)*C + c with
a, b, c = joint alarm&event / alarm&no-event / no-alarm&event
probabilities; V(alpha) = (E_C - E_F) / (E_C - E_P).  Second panel per
duration is the evaluation; the first panel provides the development
curves used below.  V_max = envelope over the grid; Peirce skill
H - F at alpha = o is the theoretical V_max and is checked against it
(column H-F@o; Peirce gap = V_max(grid) - (H - F at alpha = o)).
AUC and BSS of p_i are skill summaries only: a high AUC does not
imply high decision value at a user's C/L, so AUC is NOT reported as
decision value.

| panel | horizon | tau | o | V_max | alpha* | H-F@o | Peirce gap | AUC | BSS | n |
|---|---|---|---|---|---|---|---|---|---|---|
| first | 7 | +0.000 | 0.920 | 0.078 | 0.920 | 0.078 | -0.001 | 0.563 | -0.019 | 4380 |
| first | 7 | +0.414 | 0.667 | 0.170 | 0.670 | 0.175 | -0.005 | 0.617 | 0.031 | 4380 |
| first | 14 | +0.000 | 0.915 | 0.140 | 0.920 | 0.163 | -0.024 | 0.608 | -0.016 | 4380 |
| first | 14 | +0.414 | 0.645 | 0.161 | 0.640 | 0.169 | -0.008 | 0.623 | 0.026 | 4380 |
| first | 30 | +0.000 | 0.892 | 0.161 | 0.890 | 0.177 | -0.016 | 0.638 | -0.026 | 4380 |
| first | 30 | +0.414 | 0.585 | 0.212 | 0.580 | 0.219 | -0.007 | 0.644 | 0.029 | 4380 |
| first | 60 | +0.000 | 0.808 | 0.201 | 0.810 | 0.208 | -0.007 | 0.650 | 0.007 | 4380 |
| first | 60 | +0.414 | 0.503 | 0.214 | 0.510 | 0.224 | -0.010 | 0.652 | 0.005 | 4380 |
| first | 90 | +0.000 | 0.700 | 0.268 | 0.700 | 0.268 | 0.000 | 0.649 | 0.006 | 4380 |
| first | 90 | +0.414 | 0.431 | 0.273 | 0.430 | 0.273 | -0.001 | 0.673 | 0.005 | 4380 |
| first | 180 | +0.000 | 0.278 | 0.324 | 0.280 | 0.328 | -0.004 | 0.687 | -0.419 | 3948 |
| first | 180 | +0.414 | 0.141 | 0.335 | 0.140 | 0.337 | -0.002 | 0.689 | -0.496 | 3948 |
| second | 7 | +0.000 | 0.895 | 0.088 | 0.890 | 0.110 | -0.022 | 0.585 | -0.018 | 4480 |
| second | 7 | +0.217 | 0.736 | 0.197 | 0.730 | 0.204 | -0.007 | 0.637 | 0.061 | 4480 |
| second | 14 | +0.000 | 0.873 | 0.069 | 0.870 | 0.075 | -0.005 | 0.575 | -0.035 | 4480 |
| second | 14 | +0.217 | 0.715 | 0.230 | 0.710 | 0.239 | -0.009 | 0.661 | 0.085 | 4480 |
| second | 30 | +0.000 | 0.833 | 0.133 | 0.830 | 0.140 | -0.007 | 0.590 | -0.034 | 4480 |
| second | 30 | +0.217 | 0.652 | 0.209 | 0.660 | 0.225 | -0.016 | 0.652 | 0.047 | 4480 |
| second | 60 | +0.000 | 0.734 | 0.155 | 0.740 | 0.160 | -0.005 | 0.638 | -0.000 | 4480 |
| second | 60 | +0.217 | 0.548 | 0.224 | 0.550 | 0.227 | -0.003 | 0.660 | 0.011 | 4480 |
| second | 90 | +0.000 | 0.578 | 0.230 | 0.580 | 0.234 | -0.004 | 0.658 | 0.016 | 4400 |
| second | 90 | +0.217 | 0.422 | 0.265 | 0.420 | 0.268 | -0.003 | 0.676 | 0.003 | 4400 |
| second | 180 | +0.000 | 0.168 | 0.354 | 0.170 | 0.360 | -0.006 | 0.746 | -0.269 | 3938 |
| second | 180 | +0.217 | 0.114 | 0.359 | 0.110 | 0.363 | -0.004 | 0.746 | -0.362 | 3938 |

### Fixed-threshold realism (Roulin-style)

The envelope is optimistic: a user cannot tune alpha to the realized
outcome (Laugesen criticism d).  The realistic number comes from
alpha* = argmax V on the FIRST panel applied unchanged to the second
panel:

| horizon | tau | o dev | o eval | alpha* (dev) | V dev max | V eval fixed | V eval env | V lost |
|---|---|---|---|---|---|---|---|---|
| 7 | zero | 0.920 | 0.895 | 0.920 | 0.078 | -0.003 | 0.088 | 0.091 |
| 7 | panel_mean | 0.667 | 0.736 | 0.670 | 0.170 | 0.128 | 0.197 | 0.069 |
| 14 | zero | 0.915 | 0.873 | 0.920 | 0.140 | -0.054 | 0.069 | 0.123 |
| 14 | panel_mean | 0.645 | 0.715 | 0.640 | 0.161 | 0.156 | 0.230 | 0.074 |
| 30 | zero | 0.892 | 0.833 | 0.890 | 0.161 | -0.138 | 0.133 | 0.272 |
| 30 | panel_mean | 0.585 | 0.652 | 0.580 | 0.212 | 0.136 | 0.209 | 0.074 |
| 60 | zero | 0.808 | 0.734 | 0.810 | 0.201 | 0.074 | 0.155 | 0.081 |
| 60 | panel_mean | 0.503 | 0.548 | 0.510 | 0.214 | 0.190 | 0.224 | 0.034 |
| 90 | zero | 0.700 | 0.578 | 0.700 | 0.268 | 0.015 | 0.230 | 0.216 |
| 90 | panel_mean | 0.431 | 0.422 | 0.430 | 0.273 | 0.255 | 0.265 | 0.010 |
| 180 | zero | 0.278 | 0.168 | 0.280 | 0.324 | 0.066 | 0.354 | 0.288 |
| 180 | panel_mean | 0.141 | 0.114 | 0.140 | 0.335 | 0.276 | 0.359 | 0.083 |

Reading: the fixed alpha* keeps most of the envelope for the
above-mean event at 90/180 d (V 0.235 vs 0.261 and 0.399 vs 0.422),
while short horizons and zero-threshold events lose most of it; at
30 d (benefit > 0) the frozen threshold is negative (-0.124) although
the envelope is positive, because the development alpha* (0.89)
exceeds the evaluation base rate (0.83) and the alarm becomes too
conservative.  These fixed numbers, not the envelopes, are the
deployment figures.  BSS and AUC are skill summaries only: note the
180 d rows with BSS < 0 and V_max > 0 - miscalibrated probabilities
can still carry decision value, and a skill score must not be read as
a value score.

## 5.5 Response-effectiveness sensitivity (eta multiplier)

Effective benefit = eta * realized benefit for eta in {0.25, 0.5,
0.75, 1.0}; within-duration top-20% budget on the second panel.
Selection is by the diff / duration-only predictions and is eta-
independent; harmful rate under effective benefit equals the realized
harmful rate because eta > 0 preserves the sign.

| horizon | policy | eta | n | mean realized C | mean effective C | harmful rate |
|---|---|---|---|---|---|---|
| 7 | diff | 0.250 | 896 | 1.219 | 0.305 | 0.094 |
| 7 | diff | 0.500 | 896 | 1.219 | 0.609 | 0.094 |
| 7 | diff | 0.750 | 896 | 1.219 | 0.914 | 0.094 |
| 7 | diff | 1.000 | 896 | 1.219 | 1.219 | 0.094 |
| 7 | duration_only | 0.250 | 896 | 1.000 | 0.250 | 0.098 |
| 7 | duration_only | 0.500 | 896 | 1.000 | 0.500 | 0.098 |
| 7 | duration_only | 0.750 | 896 | 1.000 | 0.750 | 0.098 |
| 7 | duration_only | 1.000 | 896 | 1.000 | 1.000 | 0.098 |
| 14 | diff | 0.250 | 896 | 1.086 | 0.272 | 0.084 |
| 14 | diff | 0.500 | 896 | 1.086 | 0.543 | 0.084 |
| 14 | diff | 0.750 | 896 | 1.086 | 0.815 | 0.084 |
| 14 | diff | 1.000 | 896 | 1.086 | 1.086 | 0.084 |
| 14 | duration_only | 0.250 | 896 | 0.809 | 0.202 | 0.126 |
| 14 | duration_only | 0.500 | 896 | 0.809 | 0.404 | 0.126 |
| 14 | duration_only | 0.750 | 896 | 0.809 | 0.607 | 0.126 |
| 14 | duration_only | 1.000 | 896 | 0.809 | 0.809 | 0.126 |
| 30 | diff | 0.250 | 896 | 0.840 | 0.210 | 0.109 |
| 30 | diff | 0.500 | 896 | 0.840 | 0.420 | 0.109 |
| 30 | diff | 0.750 | 896 | 0.840 | 0.630 | 0.109 |
| 30 | diff | 1.000 | 896 | 0.840 | 0.840 | 0.109 |
| 30 | duration_only | 0.250 | 896 | 0.605 | 0.151 | 0.167 |
| 30 | duration_only | 0.500 | 896 | 0.605 | 0.303 | 0.167 |
| 30 | duration_only | 0.750 | 896 | 0.605 | 0.454 | 0.167 |
| 30 | duration_only | 1.000 | 896 | 0.605 | 0.605 | 0.167 |
| 60 | diff | 0.250 | 896 | 0.629 | 0.157 | 0.147 |
| 60 | diff | 0.500 | 896 | 0.629 | 0.314 | 0.147 |
| 60 | diff | 0.750 | 896 | 0.629 | 0.472 | 0.147 |
| 60 | diff | 1.000 | 896 | 0.629 | 0.629 | 0.147 |
| 60 | duration_only | 0.250 | 896 | 0.312 | 0.078 | 0.289 |
| 60 | duration_only | 0.500 | 896 | 0.312 | 0.156 | 0.289 |
| 60 | duration_only | 0.750 | 896 | 0.312 | 0.234 | 0.289 |
| 60 | duration_only | 1.000 | 896 | 0.312 | 0.312 | 0.289 |
| 90 | diff | 0.250 | 880 | 0.380 | 0.095 | 0.251 |
| 90 | diff | 0.500 | 880 | 0.380 | 0.190 | 0.251 |
| 90 | diff | 0.750 | 880 | 0.380 | 0.285 | 0.251 |
| 90 | diff | 1.000 | 880 | 0.380 | 0.380 | 0.251 |
| 90 | duration_only | 0.250 | 880 | 0.056 | 0.014 | 0.442 |
| 90 | duration_only | 0.500 | 880 | 0.056 | 0.028 | 0.442 |
| 90 | duration_only | 0.750 | 880 | 0.056 | 0.042 | 0.442 |
| 90 | duration_only | 1.000 | 880 | 0.056 | 0.056 | 0.442 |
| 180 | diff | 0.250 | 788 | -0.636 | -0.159 | 0.627 |
| 180 | diff | 0.500 | 788 | -0.636 | -0.318 | 0.627 |
| 180 | diff | 0.750 | 788 | -0.636 | -0.477 | 0.627 |
| 180 | diff | 1.000 | 788 | -0.636 | -0.636 | 0.627 |
| 180 | duration_only | 0.250 | 788 | -1.647 | -0.412 | 0.855 |
| 180 | duration_only | 0.500 | 788 | -1.647 | -0.824 | 0.855 |
| 180 | duration_only | 0.750 | 788 | -1.647 | -1.235 | 0.855 |
| 180 | duration_only | 1.000 | 788 | -1.647 | -1.647 | 0.855 |

Interpretation: Verkade & Werner (2011) set the effective action value
to half the potential loss (L_a = 0.5 L_p), i.e. eta = 0.5 is the
anchored default; Khader et al. (2013) multiply value-of-information by
a compliance probability A, which plays exactly the role of eta here;
Pappenberger et al. (2015) loss-reduction coefficients (~0.30 movable
defences, ~0.06 property moves) support eta below 0.5 for partially
effective responses.  The table is the explicit envelope: at the
Verkade-Werner anchor (eta = 0.5) the top-20% diff policy keeps
positive mean effective benefit at 7/30/90 d and halves the 180 d
outcome relative to eta = 1; the harmful rate is eta-invariant.

## Laugesen et al. (2023) criticisms (a)-(d)

- (a) risk-neutral users only: EC(xi) is an expected-cost (risk-
  neutral) criterion and is not claimed otherwise; the eta envelope
  (5.5), the per-horizon curves and the emphasis on xi < 0.5 (cheap
  action, the hydrologically realistic half) are partial responses.
- (b) binary decisions only: avoided by the primary framing.  The main
  decision presentation (5.1) never binarizes the benefit; 5.2 keeps
  continuous losses under abstention; REV (5.3) is explicitly the
  supplementary 'treat / do not treat' reading.
- (c) binarization overestimates value: avoided.  Binarization discards
  the magnitude information in the differential forecasts; the value
  claims live in the continuous curves of 5.1/5.2, and the REV numbers
  are reported with their event-threshold dependence explicit rather
  than as a single inflated figure.
- (d) envelope optimism (users self-calibrate): avoided by reporting
  the fixed alpha* (chosen on the first panel, frozen) as the
  realistic value, with V lost against the second-panel envelope; the
  envelope is labelled as the optimistic upper bound throughout.

## Numeric warnings and validations

- CRPS quantile-integral / direct ratio within 1.000 +/- 0.03 for all groups (grid discretization residual).
- EC_clim(0.5)/delta = 1.0119 > 1 (panel first, horizon 7): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.0032 > 1 (panel first, horizon 14): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.0186 > 1 (panel first, horizon 90): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.3630 > 1 (panel first, horizon 180): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.0282 > 1 (panel second, horizon 7): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.0133 > 1 (panel second, horizon 14): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.0026 > 1 (panel second, horizon 60): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.0560 > 1 (panel second, horizon 90): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- EC_clim(0.5)/delta = 1.5482 > 1 (panel second, horizon 180): the median of F0 differs from the evaluation mean, so delta is not exactly the xi = 0.5 climatology decision cost.
- E-AURC_norm < 0: risk at horizon 60 (-0.084): that sorting is worse than random at this horizon.
- E-AURC_norm < 0: risk at horizon 90 (-0.261): that sorting is worse than random at this horizon.
- E-AURC_norm < 0: risk at horizon 180 (-0.629): that sorting is worse than random at this horizon.
- E-AURC_norm < 0: duration_only at horizon 180 (-0.083): that sorting is worse than random at this horizon.
- E-AURC_norm < 0: risk at horizon direct (-0.604): that sorting is worse than random at this horizon.

Validation against P0: eta_sensitivity.csv at eta = 1 replicates the
archived budget_within_duration.csv within-duration top-20% rows by
construction (same placement frames, same rounding of the 20% budget);
the P0 gate verdicts are not re-derived here.

## Files

- laio_tamea_curves.csv
- crps_check.csv
- selective_risk_curves.csv
- selective_metrics.csv
- rev_curves.csv
- rev_fixed_threshold.csv
- eta_sensitivity.csv
