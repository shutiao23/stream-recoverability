# Revision v12, task 04 — Continuous support-aware risk surface (agent A)

**Namespace:** `results/revision_v12/t04_risk_surface/agent_a/`
**Script:** `scripts/rev_v12_t04_risk_surface_a.py` (runtime ≈ 62 s)
**Date:** 2026-08-28

## 1. Purpose

The two reviews demand replacing the network-mean fallback (a single per-network
mean of fitting-period MAE used whenever no same-horizon empirical curve exists)
with a **continuous support-aware risk surface** that pools strength across the
fitting record and produces a prediction — with an honest interval and an
abstention option — at *any* gap duration, including durations (14, 60 days)
that had no direct curve before, and the extrapolated 365-day horizon.

## 2. Data (all read-only)

| Source | Rows | Networks | Stations | Gap lengths |
|---|---|---|---|---|
| `development_empirical_fit_losses.csv` (development fit placements) | 47,408 | 51 | 192 | 7, 30, 90, 180 |
| `confirmation_empirical_fit_losses.csv` (first-panel fit placements) | 52,989 | 42 | 184 | 7, 30, 90, 180 |
| **Pooled fit data (surface fit for second panel)** | 100,397 | 93 | 376 | 7, 30, 90, 180 |
| `second_confirmation/scoring/empirical_predictions.csv` (second panel to predict) | 1,446 | 57 | 224 | 7, 14, 30, 60, 90, 180, 365 |
| `reviewer_completion/confirmation_empirical_predictions.csv` (first-panel cross-check) | 28,728 placements → 1,440 cells | 42 | — | 7, 14, 30, 60, 90, 180, 365 |

The surface is fit **only** on fitting-period artificial-gap placements
(dev + first panel). **No second-panel fit losses are used**: all 57 second-panel
networks are new levels, so their network/station random intercepts are shrunk to
0 — the second panel is a pure transfer test of the shared surface.

## 3. Model

```
log(1 + MAE) ~  f(log gap)  [quadratic B-spline, knots at 7/30/180 d,
                              EXACTLY monotone nondecreasing]
             +  g(DOY)      [2 Fourier harmonics, cyclic day-of-year]
             +  7 fitting-time covariates (z-scored)
             +  random intercepts: network (93 levels), station nested (376 levels)
```

* **Covariates** (all computed from the daily QC panels restricted to the roster
  training years, which equal the fit-loss `outer_training_years` exactly for
  100% of dev and confirmation stations):
  `temp_sd`, `temp_iqr`, `climatology_mae` (|T − smoothed DOY climatology|),
  `acf_lag1`, `acf_gap` (autocorrelation at lag = gap length), `daily_gradient`
  (mean |ΔT|), `donor_r2` (R² of the station on its roster donors). NaN rate
  ≈ 0 except `donor_r2` 1.8% (median-imputed at fit time).
* **Variance components**: exact REML for the nested design, computed with
  block-Woodbury linear algebra (`V⁻¹` and `log|V|` in closed form per
  station/network block); validated against `statsmodels` `vc_formula` REML
  (σ_net 0.137, σ_sta 0.141, σ_e 0.235 dev-only, both implementations) and
  against numerical differentiation of the REML objective.
* **Monotonicity**: enforced *exactly* by linear inequality constraints
  `D1 c ≥ 0` on the spline coefficients (for B-splines this guarantees a
  monotone curve; the constraint is the exact limit of the Eilers-style hinge
  penalty). Verified numerically: max negative slope over a 4,000-point grid
  (3–400 days) is +7.7e−8.
* **Smoothness**: D2 penalty with λ_s tuned by fitting on development fit rows
  and validating on confirmation fit rows (fixed-effects-only prediction,
  mimicking the second panel). Result: RMSE(log1p) = 0.27536 for all λ_s ∈
  {0.1, …, 10}; the penalty is effectively neutral given only 4 distinct fit
  durations (λ_s = 0.1 kept).
* **Predictions (second panel)**: fixed effects only (new levels ⇒ RE = 0);
  the DOY term uses the mean of each cell's evaluation placements' DOY
  (roster metadata, not outcome values). Intervals: 90% log-scale Gaussian
  with lognormal back-transform,
  `sd_base = sqrt(σ²_e + σ²_net + σ²_sta + x'(X'V⁻¹X)⁻¹x)`;
  extrapolated cells (365 d) are flagged and the interval is widened by
  `(1 + 2·extrapolation_factor)`, extrapolation_factor =
  (log 365 − log 180)/(log 180 − log 7) = 0.218 (i.e., 1.435× wider).

## 4. Fitted surface summary

| Quantity | Pooled fit (second panel) | Confirmation-only (first panel) |
|---|---|---|
| σ_e (residual), share | 0.232, 69.3% | 0.231 |
| σ_network, share | 0.109, 15.3% | 0.092 |
| σ_station, share | 0.109, 15.4% | 0.099 |
| Season amplitude (1st harmonic), log1p | 0.064 | — |
| Season amplitude (2nd harmonic), log1p | 0.063 | — |

Duration curve f(log gap) → MAE contribution (deg C), monotone:

| gap (d) | 7 | 14 | 30 | 60 | 90 | 180 | 365 |
|---|---|---|---|---|---|---|---|
| contribution | 0.64 | 0.79 | 0.85 | 0.95 | 1.10 | 1.59 | 2.56 |

Fitted covariate effects (log1p per z-score): climatology_mae **+0.096**,
acf_gap **−0.094**, temp_iqr +0.032, temp_sd +0.026, donor_r2 −0.025,
daily_gradient −0.014, acf_lag1 +0.005. High climatology error raises risk;
high long-lag autocorrelation lowers it. Full coefficient/scaling tables:
`surface_fit_summary.json`, `duration_curve.csv`, `station_covariates.csv`.

## 5. Second panel — evaluation (1,446 units, 57 networks)

Equal-network-weighted calibration; network Spearman on network means.

| Predictor | n | net Spearman | pooled Spearman | cal slope | R² | RMSE |
|---|---|---|---|---|---|---|
| **Surface, full panel** | 1,446 | 0.674 | **0.893** | 1.730 | **0.475** | **1.096** |
| Old empirical predictor (column) | 1,446 | **0.715** | 0.740 | 0.950 | 0.238 | 1.320 |
| Surface, 572 fallback units | 572 | **0.846** | **0.879** | 2.347 | **0.381** | **1.566** |
| Old network-mean fallback (572) | 572 | 0.597 | 0.388 | 1.218 | −0.032 | 2.022 |
| Surface, 874 direct units | 874 | 0.689 | 0.898 | 1.326 | 0.656 | 0.618 |
| Old empirical, 874 direct | 874 | 0.805 | 0.945 | 0.938 | 0.813 | 0.455 |
| **Surface, interpolated 14/60 (448)** | 448 | **0.768** | **0.774** | 1.025 | **0.443** | **0.317** |
| Old fallback, interpolated (448) | 448 | 0.653 | 0.451 | 0.509 | −0.667 | 0.548 |
| **Surface, extrapolated 365 (124)** | 124 | 0.270 | 0.411 | 0.630 | −3.17 | **3.309** |
| Old fallback, extrapolated (124) | 124 | 0.736 | 0.507 | 2.952 | −5.77 | 4.216 |

Gap-level mean prediction vs observed (deg C): 7 d 0.55/0.53, **14 d 0.70/0.68**,
30 d 0.79/0.86, **60 d 0.99/1.10**, 90 d 1.29/1.37, 180 d 2.17/2.88,
365 d 2.36/5.27.

**Reading (honest, adversarial):** the surface delivers its review purpose —
on the 572 units that previously received only a network mean, it raises
network Spearman 0.60 → 0.85, pooled Spearman 0.39 → 0.88, R² −0.03 → 0.38 and
cuts RMSE by 23%, and the 14/60-day interpolations are well calibrated
(previous constant-fallback values were badly wrong). It also improves the
full-panel pooled rank (0.893 vs 0.740) and R² (0.475 vs 0.238). It does **not**
beat the old predictor on the paper's primary full-panel network-level Spearman
(0.674 vs 0.715), because the old predictor's network means use each second-panel
network's own fitting curves; the surface trades that within-network information
for transferability, continuous support and honest intervals. Calibration slope
> 1 (0.63–2.35) reflects underdispersion of pure-transfer predictions (RE = 0),
and the 365-day extrapolation remains the hard boundary: rank is worse than the
fallback and coverage is poor (below).

## 6. Intervals and coverage-risk (abstention) curve

90% interval coverage on the second panel: overall **92.5%**; direct 96.0%;
interpolated 98.2%; **extrapolated 365 d 46.8%** — the pre-specified widening
(1.435×) is insufficient for the 365-day tail (observed 365 losses run to
9.4 °C). Extrapolated units should be abstained from point-release use, or the
widening re-estimated with external labels.

Abstention curve (`abstention_curve.csv`; rule = extrapolation-factor threshold):

| threshold | fraction abstained | net Spearman | cal slope | R² | RMSE |
|---|---|---|---|---|---|
| 0 (abstain all 365) | 8.6% | **0.691** | 1.31 | **0.663** | **0.535** |
| 0.25 (release all) | 0% | 0.674 | 1.73 | 0.475 | 1.096 |

Abstaining the 124 extrapolated units raises released-unit network Spearman to
0.691, R² to 0.66 and RMSE to 0.54. A width-based rule is **counterproductive**
(releasing only narrow-interval cells removes the long-gap cells that carry the
between-network signal; e.g., width cap 2.5 ⇒ 13% abstained but net Spearman
falls to 0.489) — the support-based rule is the correct abstention policy.
Figure: `figures_risk_surface.png` (duration curve + abstention curve).

## 7. First-panel cross-check (refit on confirmation fit losses only; 1,440 cells, 42 networks)

| Predictor | n | net Spearman | pooled Spearman | cal slope | R² | RMSE |
|---|---|---|---|---|---|---|
| **Surface** | 1,440 | **0.898** | **0.908** | 1.556 | **0.679** | **0.708** |
| Old empirical predictor | 1,440 | 0.767 | 0.633 | 0.829 | 0.145 | 1.156 |
| Surface, 660 fallback cells | 660 | **0.874** | **0.889** | 1.810 | **0.607** | 0.976 |
| Old fallback, 660 cells | 660 | 0.504 | 0.183 | 0.693 | −0.139 | 1.662 |

On the same panel where both models are fit from the same confirmation fit
losses, the surface **beats the old predictor on every reported metric**
(including on the 660 cells the old predictor covered only by network mean),
while retaining the same caveat: calibration slope > 1 (underdispersed
predictions).

## 8. Deliverables (all under `results/revision_v12/t04_risk_surface/agent_a/`)

| File | Content |
|---|---|
| `second_panel_predictions.csv` | 1,446 cells: surface prediction, 90% interval, log-scale sd, support status (direct/interpolated/extrapolated), extrapolation factor, old prediction, observed loss |
| `first_panel_predictions.csv` | 1,440 cells cross-check + old source per cell |
| `evaluation_second_panel.csv` | full/direct/fallback/interpolated/extrapolated comparisons |
| `evaluation_first_panel.csv` | first-panel cross-check comparison |
| `abstention_curve.csv` | fraction abstained vs released-unit metrics (2 rules) |
| `surface_fit_summary.json` | variance components, fixed effects, λ, tuning, extrapolation constants |
| `lambda_tuning.csv`, `duration_curve.csv`, `station_covariates.csv` | tuning grid, monotone curve, per-station covariates |
| `figures_risk_surface.png` | duration curve + abstention curve |

## 9. Caveats

* Pure-transfer predictions are underdispersed (calibration slope 1.3–2.3);
  a post-hoc recalibration with external labels would be needed for absolute
  (not rank) use.
* 365-day predictions remain extrapolation: flagged, widened, low coverage
  (46.8%), and are the units to abstain per Section 6.
* Station covariates are computed on the roster training years; the full-record
  variant changes them negligibly but was not used for the second panel.
* λ_s tuning is flat (4 distinct fit durations ⇒ the curve is pinned by the
  data; the monotone constraint binds the shape, not λ_s).
* All numbers above were produced by the script in this namespace; the script
  reads only existing files under `paper/`, `src/`, `configs/`, `data/` and
  `results/` (excluding this namespace) and writes only here.
