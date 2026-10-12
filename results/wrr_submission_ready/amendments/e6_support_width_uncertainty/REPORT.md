# E6 support-width law — uncertainty and construction dependence (F05)

**Evidence class: `exploratory_post_open`.** This is a post-hoc stress test of an exploratory claim (`results/v18_closure/e6_support_width/`). It is not a confirmation, it touches no sealed artifact, and it must not be headlined in the manuscript. The reserved panel appears only as `reserved_open`: v17's confirmation already unblinded it and script 215 already reported its crossover, so nothing new is unblinded here.

## What was tested

1. The nine-point width sweep was rebuilt into one **joint network-clustered bootstrap** (2000 draws, seed 20261012): every width, axis and contrast is evaluated on the same resampled networks, so the curve and the crossover statistic inherit the correlations between widths.
2. The crossover — the width at which a conditioning axis stops beating the whole-year missing fraction — is reported with a CI, both as a discrete grid crossing and as the frozen script's log-interpolated value, together with the probability that a replicate has **no crossover at all**.
3. The pre-registered falsification test in `P0_06_method_freeze.json` — *fixed-centre dilation vs re-seeking wide window, development only* — was run. The v17 outage realizations were regenerated from the frozen seeds; the regenerated windows reproduce the stored `support_hidden_k` columns exactly (40704 development cases, 110 networks), so both axes sit on identical cases.

## Validation

* stored endpoint table vs frozen case tables: `all_shared_columns_identical = True` (51524 rows, 0 unmatched).
* the frozen sweep is reproduced from the stored table: max abs difference vs `e6_support_width/summary.json` = 0.00e+00 (e.g. the development fixed-peak-window advantage at 90 days is +0.0016 AUC, identical to the frozen summary).
* regenerated masks vs stored columns: `all_identical = True`, max abs difference 2.72e-03.
* the dilation family reduces to the re-seeking family at the reference width 30, and the raw-peak dilation reduces to `peak_overlap` at width 30 — both checked in the same block, so the comparison is apples to apples.
* caveat inherited from the frozen pipeline: in a 366-day year the width-365 re-seeking window covers 365 days, so it is not exactly the whole-year missing fraction there (10918 development cases). That is why the width-365 point contrast is -0.0006 rather than exactly zero.


## Headline numbers

* **The reported crossover** (a *fixed* 30-day peak window against the whole-year missing fraction, label widening with the endpoint): development 91.0 days, bootstrap 95% CI [77, 107], P(no crossover) = 0.000; opened reserved panel 118.9 days, CI [104, 136]. The two intervals overlap.
* **The support-restricted axis** against the whole-year missing fraction never loses its advantage until the trivial k = 365 coincidence: point crossover 359 days, CI [351, 364], P(no crossover) = 0.072. It is a hump, not a decay: it peaks near 60 days.
* **Fixed-centre dilation** against the whole-year missing fraction: point crossover 359 days, CI [345, 364], P(no crossover) = 0.115. The raw-peak dilation has no crossover on the point curve at all (P(no crossover) = 0.913).
* **At the 90-day grid point the three constructions disagree completely.** Fixed 30-day window: +0.0016 AUC, 95% CI [-0.0180, +0.0255], positive in 55% of 2000 replicates. Fixed-centre dilation: +0.0599 AUC, 95% CI [+0.0447, +0.0784], positive in 100% of 2000 replicates. Re-seeking window: +0.0654 AUC, 95% CI [+0.0502, +0.0836], positive in 100% of 2000 replicates.
* **At the 182-day grid point** the fixed 30-day window is -0.0946 AUC against whole-year missingness while the dilation is +0.0214: the sign of the 'support width' effect at a given width depends entirely on whether the conditioning window is dilated or held fixed.
* **A single universal conditioning window** in the 60-90 day band costs at most 0.0004 AUC against the per-endpoint optimum for every endpoint up to 90 days, but 0.0825 AUC at the 365-day endpoint. It is a defensible single rule for the paper's seasonal endpoint family and false as a statement about the continuum.
* **The crossover also moves with the declared tolerance**: across the frozen sweep's own tolerance grid the reported contrast crosses at 101.6 days (0.25 sd), 91.0 days (0.47 sd) and 84.6 days (1.0 sd).
* **Dilation versus re-seeking is statistically detectable but tiny**: the largest absolute paired difference across all nine widths is 0.0078 AUC.

## 1. The curve, with intervals

Primary tolerance (0.5 C expressed as 0.5/1.06 of each endpoint's own interannual standard deviation), development panel. `point` is the full-sample AUC recomputed from the stored table; `low`/`high` are percentile intervals over network-clustered replicates; `P(AUC>0.5)` is the share of replicates in which the axis beats chance.

| axis                   |   width_days |   point |    low |   high |     se |   p_at_or_above_null |
|:-----------------------|-------------:|--------:|-------:|-------:|-------:|---------------------:|
| longest_run            |            1 |  0.7565 | 0.7282 | 0.7802 | 0.0135 |               1.0000 |
| longest_run            |            3 |  0.7517 | 0.7211 | 0.7771 | 0.0146 |               1.0000 |
| longest_run            |            7 |  0.7520 | 0.7211 | 0.7770 | 0.0147 |               1.0000 |
| longest_run            |           15 |  0.7495 | 0.7176 | 0.7749 | 0.0148 |               1.0000 |
| longest_run            |           30 |  0.7501 | 0.7186 | 0.7747 | 0.0148 |               1.0000 |
| longest_run            |           60 |  0.7711 | 0.7422 | 0.7935 | 0.0133 |               1.0000 |
| longest_run            |           90 |  0.7947 | 0.7676 | 0.8156 | 0.0122 |               1.0000 |
| longest_run            |          182 |  0.8264 | 0.8044 | 0.8438 | 0.0099 |               1.0000 |
| longest_run            |          365 |  0.8453 | 0.8230 | 0.8616 | 0.0094 |               1.0000 |
| missing_fraction       |            1 |  0.7509 | 0.7213 | 0.7761 | 0.0143 |               1.0000 |
| missing_fraction       |            3 |  0.7462 | 0.7133 | 0.7733 | 0.0155 |               1.0000 |
| missing_fraction       |            7 |  0.7460 | 0.7128 | 0.7728 | 0.0156 |               1.0000 |
| missing_fraction       |           15 |  0.7434 | 0.7097 | 0.7698 | 0.0157 |               1.0000 |
| missing_fraction       |           30 |  0.7441 | 0.7106 | 0.7703 | 0.0158 |               1.0000 |
| missing_fraction       |           60 |  0.7652 | 0.7341 | 0.7899 | 0.0145 |               1.0000 |
| missing_fraction       |           90 |  0.7901 | 0.7616 | 0.8133 | 0.0133 |               1.0000 |
| missing_fraction       |          182 |  0.8227 | 0.7989 | 0.8413 | 0.0109 |               1.0000 |
| missing_fraction       |          365 |  0.8447 | 0.8221 | 0.8618 | 0.0100 |               1.0000 |
| peak_window_30         |            1 |  0.8245 | 0.8105 | 0.8376 | 0.0070 |               1.0000 |
| peak_window_30         |            3 |  0.8241 | 0.8111 | 0.8362 | 0.0064 |               1.0000 |
| peak_window_30         |            7 |  0.8227 | 0.8090 | 0.8352 | 0.0067 |               1.0000 |
| peak_window_30         |           15 |  0.8209 | 0.8074 | 0.8332 | 0.0066 |               1.0000 |
| peak_window_30         |           30 |  0.8188 | 0.8062 | 0.8306 | 0.0062 |               1.0000 |
| peak_window_30         |           60 |  0.8154 | 0.8044 | 0.8260 | 0.0054 |               1.0000 |
| peak_window_30         |           90 |  0.7917 | 0.7789 | 0.8028 | 0.0061 |               1.0000 |
| peak_window_30         |          182 |  0.7282 | 0.7109 | 0.7425 | 0.0079 |               1.0000 |
| peak_window_30         |          365 |  0.6720 | 0.6476 | 0.6899 | 0.0108 |               1.0000 |
| support_reseeking      |            1 |  0.7600 | 0.7445 | 0.7749 | 0.0079 |               1.0000 |
| support_reseeking      |            3 |  0.7662 | 0.7507 | 0.7810 | 0.0077 |               1.0000 |
| support_reseeking      |            7 |  0.7784 | 0.7622 | 0.7931 | 0.0079 |               1.0000 |
| support_reseeking      |           15 |  0.8022 | 0.7863 | 0.8167 | 0.0078 |               1.0000 |
| support_reseeking      |           30 |  0.8270 | 0.8140 | 0.8391 | 0.0063 |               1.0000 |
| support_reseeking      |           60 |  0.8545 | 0.8408 | 0.8659 | 0.0063 |               1.0000 |
| support_reseeking      |           90 |  0.8555 | 0.8400 | 0.8674 | 0.0069 |               1.0000 |
| support_reseeking      |          182 |  0.8510 | 0.8334 | 0.8640 | 0.0077 |               1.0000 |
| support_reseeking      |          365 |  0.8441 | 0.8217 | 0.8609 | 0.0099 |               1.0000 |
| warm_observed_fraction |            1 |  0.8324 | 0.8113 | 0.8496 | 0.0101 |               1.0000 |
| warm_observed_fraction |            3 |  0.8267 | 0.8037 | 0.8455 | 0.0109 |               1.0000 |
| warm_observed_fraction |            7 |  0.8244 | 0.8007 | 0.8433 | 0.0111 |               1.0000 |
| warm_observed_fraction |           15 |  0.8206 | 0.7961 | 0.8406 | 0.0115 |               1.0000 |
| warm_observed_fraction |           30 |  0.8204 | 0.7973 | 0.8394 | 0.0110 |               1.0000 |
| warm_observed_fraction |           60 |  0.8352 | 0.8136 | 0.8526 | 0.0099 |               1.0000 |
| warm_observed_fraction |           90 |  0.8470 | 0.8276 | 0.8630 | 0.0091 |               1.0000 |
| warm_observed_fraction |          182 |  0.8479 | 0.8304 | 0.8618 | 0.0081 |               1.0000 |
| warm_observed_fraction |          365 |  0.8181 | 0.7961 | 0.8340 | 0.0097 |               1.0000 |

Contrasts on the same resamples (paired; the interval is of the difference):

| axis                                          |   width_days |   point |     low |    high |   p_at_or_above_null |
|:----------------------------------------------|-------------:|--------:|--------:|--------:|---------------------:|
| fixed_peak_window_30_minus_missing_fraction   |            1 |  0.0736 |  0.0538 |  0.0994 |               1.0000 |
| fixed_peak_window_30_minus_missing_fraction   |            3 |  0.0780 |  0.0559 |  0.1059 |               1.0000 |
| fixed_peak_window_30_minus_missing_fraction   |            7 |  0.0767 |  0.0545 |  0.1045 |               1.0000 |
| fixed_peak_window_30_minus_missing_fraction   |           15 |  0.0775 |  0.0550 |  0.1067 |               1.0000 |
| fixed_peak_window_30_minus_missing_fraction   |           30 |  0.0747 |  0.0503 |  0.1063 |               1.0000 |
| fixed_peak_window_30_minus_missing_fraction   |           60 |  0.0502 |  0.0288 |  0.0785 |               1.0000 |
| fixed_peak_window_30_minus_missing_fraction   |           90 |  0.0016 | -0.0180 |  0.0255 |               0.5490 |
| fixed_peak_window_30_minus_missing_fraction   |          182 | -0.0946 | -0.1122 | -0.0761 |               0.0000 |
| fixed_peak_window_30_minus_missing_fraction   |          365 | -0.1727 | -0.1914 | -0.1563 |               0.0000 |
| support_restricted_minus_fixed_peak_window_30 |            1 | -0.0645 | -0.0701 | -0.0594 |               0.0000 |
| support_restricted_minus_fixed_peak_window_30 |            3 | -0.0579 | -0.0643 | -0.0520 |               0.0000 |
| support_restricted_minus_fixed_peak_window_30 |            7 | -0.0443 | -0.0499 | -0.0393 |               0.0000 |
| support_restricted_minus_fixed_peak_window_30 |           15 | -0.0187 | -0.0239 | -0.0139 |               0.0000 |
| support_restricted_minus_fixed_peak_window_30 |           30 |  0.0082 |  0.0061 |  0.0100 |               1.0000 |
| support_restricted_minus_fixed_peak_window_30 |           60 |  0.0391 |  0.0323 |  0.0442 |               1.0000 |
| support_restricted_minus_fixed_peak_window_30 |           90 |  0.0639 |  0.0565 |  0.0703 |               1.0000 |
| support_restricted_minus_fixed_peak_window_30 |          182 |  0.1228 |  0.1111 |  0.1358 |               1.0000 |
| support_restricted_minus_fixed_peak_window_30 |          365 |  0.1721 |  0.1559 |  0.1904 |               1.0000 |
| support_restricted_minus_missing_fraction     |            1 |  0.0091 | -0.0085 |  0.0316 |               0.8220 |
| support_restricted_minus_missing_fraction     |            3 |  0.0200 |  0.0008 |  0.0448 |               0.9795 |
| support_restricted_minus_missing_fraction     |            7 |  0.0324 |  0.0131 |  0.0570 |               1.0000 |
| support_restricted_minus_missing_fraction     |           15 |  0.0589 |  0.0384 |  0.0862 |               1.0000 |
| support_restricted_minus_missing_fraction     |           30 |  0.0829 |  0.0591 |  0.1132 |               1.0000 |
| support_restricted_minus_missing_fraction     |           60 |  0.0893 |  0.0715 |  0.1127 |               1.0000 |
| support_restricted_minus_missing_fraction     |           90 |  0.0654 |  0.0502 |  0.0836 |               1.0000 |
| support_restricted_minus_missing_fraction     |          182 |  0.0282 |  0.0190 |  0.0392 |               1.0000 |
| support_restricted_minus_missing_fraction     |          365 | -0.0006 | -0.0014 |  0.0002 |               0.0720 |

The other two tolerance fractions (0.25 and 1.00 of the interannual sd, matching the frozen sweep's own robustness grid) are in `curve_with_ci.csv` under `tolerance_fraction_name` `quarter` and `one`.

## 2. Crossover statistics

| contrast | panel | fraction | point (interp.) | frozen rule | nearest non-positive grid | bootstrap median | 95% CI | P(no crossover) | no crossover: never positive | no crossover: gained later | no crossover: positive throughout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| support_restricted_minus_missing_fraction | development | primary | 359.4 | 359.4 | 365 | 358.9 | [350.6, 364.5] | 0.072 | 0.000 | 0.005 | 0.067 |
| support_restricted_minus_missing_fraction | development | quarter | 363.6 | 363.6 | 365 | 362.5 | [357.2, 364.9] | 0.298 | 0.000 | 0.000 | 0.298 |
| support_restricted_minus_missing_fraction | development | one | 355.5 | 4.3 | 1 | 354.9 | [343.5, 363.9] | 0.058 | 0.000 | 0.052 | 0.005 |
| fixed_peak_window_30_minus_missing_fraction | development | primary | 91.0 | 91.0 | 182 | 90.9 | [77.1, 107.0] | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed_peak_window_30_minus_missing_fraction | development | quarter | 101.6 | 101.6 | 182 | 101.4 | [87.9, 117.9] | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed_peak_window_30_minus_missing_fraction | development | one | 84.6 | 84.6 | 90 | 84.8 | [70.7, 100.6] | 0.000 | 0.000 | 0.000 | 0.000 |
| support_restricted_minus_fixed_peak_window_30 | development | primary | nan | 24.3 | 1 | nan | [nan, nan] | 1.000 | 0.000 | 1.000 | 0.000 |
| support_restricted_minus_fixed_peak_window_30 | development | quarter | nan | 25.2 | 1 | nan | [nan, nan] | 1.000 | 0.000 | 1.000 | 0.000 |
| support_restricted_minus_fixed_peak_window_30 | development | one | nan | 22.6 | 1 | nan | [nan, nan] | 1.000 | 0.000 | 1.000 | 0.000 |
| longest_run_minus_missing_fraction | development | primary | nan | nan | nan | 276.8 | [102.9, 359.5] | 0.569 | 0.000 | 0.000 | 0.569 |
| longest_run_minus_missing_fraction | development | quarter | nan | nan | nan | 275.1 | [139.3, 361.0] | 0.798 | 0.000 | 0.000 | 0.798 |
| longest_run_minus_missing_fraction | development | one | 277.3 | 277.3 | 365 | 202.9 | [25.4, 353.8] | 0.259 | 0.002 | 0.000 | 0.257 |
| support_restricted_minus_missing_fraction | reserved_open | primary | nan | nan | nan | 360.7 | [348.6, 364.7] | 0.520 | 0.000 | 0.000 | 0.520 |
| fixed_peak_window_30_minus_missing_fraction | reserved_open | primary | 118.9 | 118.9 | 182 | 117.9 | [104.5, 136.3] | 0.000 | 0.000 | 0.000 | 0.000 |
| support_restricted_minus_fixed_peak_window_30 | reserved_open | primary | nan | 25.7 | 1 | nan | [nan, nan] | 1.000 | 0.000 | 1.000 | 0.000 |
| fixed_centre_dilation_minus_reseeking | development | primary | 30.0 | 30.0 | 30 | 30.0 | [30.0, 30.0] | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed_centre_dilation_minus_reseeking | development | quarter | 30.0 | 30.0 | 30 | 30.0 | [30.0, 30.0] | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed_centre_dilation_minus_reseeking | development | one | 30.0 | 30.0 | 30 | 30.0 | [1.4, 30.0] | 0.023 | 0.008 | 0.015 | 0.000 |
| fixed_centre_dilation_mirror_minus_reseeking | development | primary | 30.0 | 30.0 | 30 | 30.0 | [30.0, 30.0] | 0.000 | 0.000 | 0.000 | 0.000 |
| fixed_centre_dilation_mirror_minus_reseeking | development | quarter | 30.0 | 30.0 | 30 | 30.0 | [30.0, 30.0] | 0.000 | 0.000 | 0.001 | 0.000 |
| fixed_centre_dilation_mirror_minus_reseeking | development | one | 30.0 | 30.0 | 30 | 30.0 | [1.3, 30.0] | 0.112 | 0.027 | 0.085 | 0.000 |
| fixed_centre_dilation_raw_peak_minus_reseeking | development | primary | 17.6 | 17.6 | 30 | 17.7 | [8.6, 21.7] | 0.032 | 0.000 | 0.033 | 0.000 |
| fixed_centre_dilation_raw_peak_minus_reseeking | development | quarter | 18.1 | 18.1 | 30 | 18.1 | [8.5, 21.6] | 0.032 | 0.001 | 0.032 | 0.000 |
| fixed_centre_dilation_raw_peak_minus_reseeking | development | one | 2.9 | 2.9 | 3 | 16.4 | [1.2, 21.2] | 0.355 | 0.012 | 0.343 | 0.000 |
| fixed_centre_dilation_minus_missing_fraction | development | primary | 358.7 | 358.7 | 365 | 357.8 | [345.1, 364.4] | 0.115 | 0.000 | 0.006 | 0.108 |
| fixed_centre_dilation_minus_missing_fraction | development | quarter | 363.7 | 363.7 | 365 | 362.2 | [354.8, 364.8] | 0.336 | 0.000 | 0.000 | 0.336 |
| fixed_centre_dilation_minus_missing_fraction | development | one | 349.2 | 3.5 | 1 | 348.3 | [320.2, 363.0] | 0.045 | 0.000 | 0.029 | 0.015 |
| fixed_centre_dilation_raw_peak_minus_missing_fraction | development | primary | nan | nan | nan | 363.1 | [355.4, 364.9] | 0.913 | 0.000 | 0.159 | 0.754 |
| fixed_centre_dilation_raw_peak_minus_missing_fraction | development | quarter | nan | nan | nan | 363.8 | [359.4, 364.9] | 0.879 | 0.000 | 0.001 | 0.878 |
| fixed_centre_dilation_raw_peak_minus_missing_fraction | development | one | 361.2 | 4.3 | 1 | 357.0 | [322.0, 364.6] | 0.315 | 0.000 | 0.277 | 0.038 |
| fixed_centre_dilation_mirror_minus_missing_fraction | development | primary | 358.9 | 358.9 | 365 | 358.0 | [345.4, 364.4] | 0.122 | 0.000 | 0.010 | 0.112 |
| fixed_centre_dilation_mirror_minus_missing_fraction | development | quarter | 363.9 | 363.9 | 365 | 362.3 | [355.1, 364.8] | 0.365 | 0.000 | 0.001 | 0.364 |
| fixed_centre_dilation_mirror_minus_missing_fraction | development | one | 349.8 | 3.9 | 1 | 348.8 | [320.1, 362.8] | 0.053 | 0.000 | 0.041 | 0.013 |

`P(no crossover)` is the quantity the original analysis was missing: it is the probability that a replicate drawn from the same network population has no crossover anywhere in the swept width range.

A third reading note on the `frozen rule` column: `scripts/215_v18_support_width.py::crossover` fires on any sign change, not on the loss of an advantage. On curves that start negative (the support axis against the fixed 30-day window does, and so does the whole `one`-tolerance block) it returns a number for a crossing that runs the other way — 4.3 or 24.3 days — which is why those cells disagree with the restricted rule. That fragility is itself part of the finding: the frozen helper is not a well-posed estimator of the quantity it is quoted for.

The crossover also moves with the declared tolerance: across the frozen sweep's own tolerance grid (0.25, 0.47 and 1.0 interannual sd) the reported contrast crosses at 101.6, 91.0 and 84.6 days respectively.

Two reading notes. (i) The row that reproduces the reported 91-day / 119-day number is `fixed_peak_window_30_minus_missing_fraction`: a **fixed** 30-day peak-window axis scored against the label at each endpoint width. That contrast is not about window width — the axis never changes — so its 'crossover' is where the fixed 30-day window stops predicting errors in a widening endpoint, which is a different claim from the support-width law. (ii) `fixed_centre_dilation_minus_reseeking` crosses at exactly 30 days in every replicate by construction, because the two axes are the same window at width 30; its crossover row is degenerate and the per-width paired intervals in `dilation_vs_reseek.csv` are the object to read.

Leave-one-network-out jackknife on the two primary contrast curves (does one network carry the crossover?):

| contrast                                    |   replicates |   P(no crossover) |   LOO min |   LOO median |   LOO max |   jackknife SE | jackknife 95% CI   |
|:--------------------------------------------|-------------:|------------------:|----------:|-------------:|----------:|---------------:|:-------------------|
| support_restricted_minus_missing_fraction   |          110 |              0.00 |    358.44 |       359.37 |    361.66 |           3.98 | [352, 367]         |
| fixed_peak_window_30_minus_missing_fraction |          110 |              0.00 |     86.86 |        91.04 |     94.63 |           8.06 | [75, 107]          |

The raw leave-one-out range is **not** a confidence interval — each replicate still contains 109 of the 110 networks — so read the jackknife SE column. Its normal CI is the uncertainty from single-network influence; the network-resampling bootstrap CI in section 2 is the one to quote.

## 3. Fixed-centre dilation vs re-seeking (development only)

`re-seek` is the stored axis: the hottest k-day window of the station's smoothed training-year climatology, re-chosen at every k. `dilate` holds the window centre at that same climatology's 30-day peak centre and grows the window symmetrically to width k (`dilate (mirror)` breaks the odd-width half-day tie the other way). `dilate (raw peak)` instead dilates the raw training-year climatological peak window — the window `peak_overlap` uses. Every centre is computed from training years only: no truth enters, so this is decision-time visible.

|   width_days |   auc_support_reseeking |   auc_fixed_centre_dilation |   auc_fixed_centre_dilation_raw_peak |   auc_missing_fraction |   contrast_fcd_minus_reseeking |   contrast_fcd_minus_reseeking_low |   contrast_fcd_minus_reseeking_high |   abs_centre_shift_days_mean |   windows_differ_mean |
|-------------:|------------------------:|----------------------------:|-------------------------------------:|-----------------------:|-------------------------------:|-----------------------------------:|------------------------------------:|-----------------------------:|----------------------:|
|       1.0000 |                  0.7600 |                      0.7644 |                               0.7614 |                 0.7504 |                         0.0044 |                            -0.0002 |                              0.0095 |                       4.5271 |                0.9249 |
|       3.0000 |                  0.7661 |                      0.7716 |                               0.7700 |                 0.7456 |                         0.0055 |                             0.0004 |                              0.0117 |                       4.4858 |                0.9254 |
|       7.0000 |                  0.7783 |                      0.7861 |                               0.7834 |                 0.7453 |                         0.0078 |                             0.0035 |                              0.0127 |                       4.2229 |                0.9148 |
|      15.0000 |                  0.8020 |                      0.8081 |                               0.8046 |                 0.7425 |                         0.0061 |                             0.0023 |                              0.0106 |                       3.3209 |                0.8700 |
|      30.0000 |                  0.8269 |                      0.8269 |                               0.8187 |                 0.7432 |                         0.0000 |                             0.0000 |                              0.0000 |                       0.0000 |                0.0000 |
|      60.0000 |                  0.8542 |                      0.8479 |                               0.8459 |                 0.7644 |                        -0.0063 |                            -0.0086 |                             -0.0036 |                       4.7121 |                0.9336 |
|      90.0000 |                  0.8551 |                      0.8497 |                               0.8487 |                 0.7895 |                        -0.0054 |                            -0.0079 |                             -0.0031 |                       6.2186 |                0.9636 |
|     182.0000 |                  0.8505 |                      0.8436 |                               0.8433 |                 0.8223 |                        -0.0069 |                            -0.0115 |                             -0.0032 |                       9.2133 |                0.9727 |
|     365.0000 |                  0.8435 |                      0.8436 |                               0.8447 |                 0.8441 |                         0.0001 |                            -0.0001 |                              0.0003 |                      26.2859 |                0.2625 |

Dilation against the whole-year missing fraction — the same comparison the reported crossover is built on. `reseek` is the support-restricted axis, `dilate` the fixed-centre dilation, `peak30` the fixed 30-day window whose crossover is the reported 91-day figure:

|   width_days |   contrast_peak30_minus_missing |   contrast_peak30_minus_missing_low |   contrast_peak30_minus_missing_high |   contrast_fcd_minus_missing |   contrast_fcd_minus_missing_low |   contrast_fcd_minus_missing_high |   contrast_reseek_minus_missing |   contrast_reseek_minus_missing_low |   contrast_reseek_minus_missing_high |
|-------------:|--------------------------------:|------------------------------------:|-------------------------------------:|-----------------------------:|---------------------------------:|----------------------------------:|--------------------------------:|------------------------------------:|-------------------------------------:|
|       1.0000 |                          0.0740 |                              0.0538 |                               0.0994 |                       0.0140 |                          -0.0059 |                            0.0392 |                          0.0096 |                             -0.0085 |                               0.0316 |
|       3.0000 |                          0.0785 |                              0.0559 |                               0.1059 |                       0.0260 |                           0.0035 |                            0.0541 |                          0.0206 |                              0.0008 |                               0.0448 |
|       7.0000 |                          0.0773 |                              0.0545 |                               0.1045 |                       0.0408 |                           0.0185 |                            0.0679 |                          0.0330 |                              0.0131 |                               0.0570 |
|      15.0000 |                          0.0782 |                              0.0550 |                               0.1067 |                       0.0656 |                           0.0426 |                            0.0939 |                          0.0595 |                              0.0384 |                               0.0862 |
|      30.0000 |                          0.0755 |                              0.0503 |                               0.1063 |                       0.0836 |                           0.0591 |                            0.1132 |                          0.0836 |                              0.0591 |                               0.1132 |
|      60.0000 |                          0.0510 |                              0.0288 |                               0.0785 |                       0.0834 |                           0.0636 |                            0.1077 |                          0.0898 |                              0.0715 |                               0.1127 |
|      90.0000 |                          0.0021 |                             -0.0180 |                               0.0255 |                       0.0602 |                           0.0447 |                            0.0784 |                          0.0657 |                              0.0502 |                               0.0836 |
|     182.0000 |                         -0.0946 |                             -0.1122 |                              -0.0761 |                       0.0213 |                           0.0120 |                            0.0327 |                          0.0282 |                              0.0190 |                               0.0392 |
|     365.0000 |                         -0.1732 |                             -0.1914 |                              -0.1563 |                      -0.0005 |                          -0.0014 |                            0.0003 |                         -0.0006 |                             -0.0014 |                               0.0002 |

* `development | fixed_centre_dilation_minus_missing_fraction`: point crossover 358.7 days, bootstrap median 357.8, 95% CI [345.1, 364.4], P(no crossover) = 0.115.
* `development | fixed_centre_dilation_raw_peak_minus_missing_fraction`: point crossover nan days, bootstrap median 363.1, 95% CI [355.4, 364.9], P(no crossover) = 0.913.
* `development | fixed_centre_dilation_mirror_minus_missing_fraction`: point crossover 358.9 days, bootstrap median 358.0, 95% CI [345.4, 364.4], P(no crossover) = 0.122.

How far the re-seeking window actually moves away from the fixed centre, and how often the two windows are not the same set of days:

|   width_days |   abs_centre_shift_days_mean |   centre_shift_days_mean |   windows_differ_mean |   hidden_difference_fcd_minus_reseek_mean |
|-------------:|-----------------------------:|-------------------------:|----------------------:|------------------------------------------:|
|        1.000 |                        4.527 |                   -0.706 |                 0.925 |                                     0.001 |
|        3.000 |                        4.486 |                   -0.653 |                 0.925 |                                     0.001 |
|        7.000 |                        4.223 |                   -0.588 |                 0.915 |                                     0.000 |
|       15.000 |                        3.321 |                   -0.347 |                 0.870 |                                     0.001 |
|       30.000 |                        0.000 |                    0.000 |                 0.000 |                                     0.000 |
|       60.000 |                        4.712 |                   -2.311 |                 0.934 |                                    -0.001 |
|       90.000 |                        6.219 |                   -3.095 |                 0.964 |                                    -0.002 |
|      182.000 |                        9.213 |                   -6.033 |                 0.973 |                                    -0.004 |
|      365.000 |                       26.286 |                  -24.382 |                 0.262 |                                    -0.000 |

## 4. Conditioning width and the refit tolerance

For each endpoint width, the re-seeking axis evaluated at every conditioning width. `separated` counts the competing conditioning widths whose paired AUC difference from the best is resolved (CI excludes zero); if it is small, the argmax is not identified.

|   endpoint_width_days |   best_conditioning_width_days |   auc_at_best |   auc_at_own_support |   gap_to_second_best |   gap_to_own_support |   separated_from |   competing_widths |
|----------------------:|-------------------------------:|--------------:|---------------------:|---------------------:|---------------------:|-----------------:|-------------------:|
|                1.0000 |                        90.0000 |        0.8613 |               0.7600 |               0.0004 |               0.1013 |           7.0000 |             8.0000 |
|                3.0000 |                        60.0000 |        0.8578 |               0.7661 |               0.0003 |               0.0917 |           7.0000 |             8.0000 |
|                7.0000 |                        90.0000 |        0.8547 |               0.7783 |               0.0004 |               0.0764 |           7.0000 |             8.0000 |
|               15.0000 |                        60.0000 |        0.8524 |               0.8020 |               0.0004 |               0.0504 |           7.0000 |             8.0000 |
|               30.0000 |                        90.0000 |        0.8511 |               0.8269 |               0.0001 |               0.0242 |           7.0000 |             8.0000 |
|               60.0000 |                        90.0000 |        0.8593 |               0.8542 |               0.0051 |               0.0051 |           8.0000 |             8.0000 |
|               90.0000 |                        90.0000 |        0.8551 |               0.8551 |               0.0083 |               0.0000 |           8.0000 |             8.0000 |
|              182.0000 |                       182.0000 |        0.8505 |               0.8505 |               0.0280 |               0.0000 |           8.0000 |             8.0000 |
|              365.0000 |                       365.0000 |        0.8435 |               0.8435 |               0.0201 |               0.0000 |           8.0000 |             8.0000 |

What a *single universal* conditioning window would cost, in AUC, relative to each endpoint's own best conditioning width (0.0000 means the universal window is the best one for that endpoint):

|   endpoint_width_days |   best_conditioning_width_days |   universal_30d_penalty |   universal_60d_penalty |   universal_90d_penalty |   universal_182d_penalty |
|----------------------:|-------------------------------:|------------------------:|------------------------:|------------------------:|-------------------------:|
|                1.0000 |                        90.0000 |                  0.0279 |                  0.0004 |                  0.0000 |                   0.0347 |
|                3.0000 |                        60.0000 |                  0.0252 |                  0.0000 |                  0.0003 |                   0.0356 |
|                7.0000 |                        90.0000 |                  0.0240 |                  0.0004 |                  0.0000 |                   0.0340 |
|               15.0000 |                        60.0000 |                  0.0233 |                  0.0000 |                  0.0004 |                   0.0348 |
|               30.0000 |                        90.0000 |                  0.0242 |                  0.0001 |                  0.0000 |                   0.0329 |
|               60.0000 |                        90.0000 |                  0.0349 |                  0.0051 |                  0.0000 |                   0.0253 |
|               90.0000 |                        90.0000 |                  0.0542 |                  0.0153 |                  0.0000 |                   0.0083 |
|              182.0000 |                       182.0000 |                  0.1136 |                  0.0674 |                  0.0369 |                   0.0000 |
|              365.0000 |                       365.0000 |                  0.1635 |                  0.1156 |                  0.0825 |                   0.0201 |

Reading: a universal window in the 60-90 day band costs at most 0.0153 AUC for every endpoint up to 90 days — that band is a defensible single rule for the paper's endpoint family — but it costs 0.0825 AUC at the 365-day endpoint, where only conditioning on the whole year works. So 'one universal conditioning window' is supportable for local/seasonal endpoints and false as a statement about the whole continuum.

Re-estimating the tolerance scale inside each replicate (instead of fixing it at each endpoint's full-development interannual sd) moves the primary AUCs by at most:

|   width_days | axis                   |   mean_difference |     low |   high | ci_excludes_zero   |
|-------------:|:-----------------------|------------------:|--------:|-------:|:-------------------|
|          182 | warm_observed_fraction |            0.0052 | -0.0032 | 0.0149 | False              |
|          365 | support_reseeking      |            0.0049 | -0.0067 | 0.0175 | False              |
|          365 | missing_fraction       |            0.0048 | -0.0069 | 0.0174 | False              |
|          182 | peak_window_30         |            0.0045 | -0.0050 | 0.0154 | False              |
|          182 | support_reseeking      |            0.0041 | -0.0037 | 0.0140 | False              |
|            1 | peak_window_30         |            0.0040 | -0.0010 | 0.0096 | False              |

* refit tolerance, `support_restricted_minus_missing_fraction`: point crossover 359.4 days, bootstrap median 360.1, 95% CI [351.8, 364.6], P(no crossover) = 0.125.
* refit tolerance, `fixed_peak_window_30_minus_missing_fraction`: point crossover 91.0 days, bootstrap median 94.5, 95% CI [80.5, 111.0], P(no crossover) = 0.000.

## Verdict

**Is an exact crossover day supportable? No.**

The reported 91.0-day figure is reproduced exactly (91.0 days from the stored table, max difference 0 against the frozen summary), so the arithmetic is not in question. As an estimate it is not identified. Its value also moves with the declared tolerance (101.6 to 84.6 days across the frozen sweep's own tolerance grid). The network-clustered 95% interval for that same crossover is [77, 107] days, with P(no crossover in the swept range) = 0.000. The opened reserved panel's 118.9-day figure behaves the same way (118.9 days point, 95% CI [104, 136], P(no crossover) = 0.00); the two panels' intervals overlap, so the difference between 91 and 119 days is not a panel difference either. Leave-one-network-out replicates span 87 to 95 days. The point value is an interpolation across a nine-point grid and the grid interval it interpolates across is the flat one: at the 90-day grid point the contrast is +0.0016 AUC (95% CI [-0.0180, +0.0255]), positive in only 55% of replicates, and the first non-positive grid point is 182 days. A sharp-looking 91.05 is being read off a value that is statistically zero. A single day cannot be defended; an interval (76-107 days here) can.

**Is a single universal conditioning window supportable? No.**

The best conditioning width is 60 or 90 days for every endpoint at or below 60 days, and the gap between those two is at most 0.005 AUC there: the argmax flips between them across endpoints on differences that are operationally meaningless, so the *identity* of an optimum window is not identified even where the paired bootstrap can resolve the ordering. At the same time a universal window inside that 60-90 day band costs at most 0.0004 AUC against each narrow endpoint's own optimum, so the band is a defensible single rule — for the paper's seasonal endpoint family. It is not a universal rule: for the 365-day endpoint it costs 0.0825 AUC, where only conditioning on the whole year works, and for the 182-day endpoint it costs 0.0369 AUC. The supportable statement is therefore a range, not a day count, and not one number for the whole continuum.

**Dilation vs re-seeking.**

At 90 days the fixed-centre dilation differs from the re-seeking window by -0.0054 AUC (95% CI [-0.0079, -0.0031]); the two are identical at width 30 by construction and differ by at most ~0.008 AUC anywhere, so the *statistical* penalty for not re-seeking is small. What is not small is what the two constructions say about the crossover. The reported 91-day crossover belongs to the **fixed** 30-day window: held at 30 days, that axis is -0.095 AUC against whole-year missingness at a 182-day endpoint. Dilate the same window to the endpoint's own width and the sign flips: +0.0213 AUC at 182 days (95% CI [+0.0120, +0.0327]) for the dilation family and +0.0282 for the re-seeking family. Both dilation families keep their advantage over whole-year missingness out to about 359 days — the raw-peak dilation never turns non-positive on the point curve at all (P(no crossover) = 0.91) — and only the trivial k = 365 coincidence ends it.

So the 91-day number is not the width at which the support idea stops working. It is the width at which a *narrow, un-dilated* window stops predicting errors in a widening estimand. That is a real and useful statement about the v17 screen, whose axis really is a fixed 30-day window; it is not evidence for a support-width law with a crossover knob at 91 days.

**What the law can and cannot carry.**

Supportable, as exploratory evidence: that conditioning on a window restricted to (or dilated around) the estimand's support beats whole-year missingness across a broad band of widths, that the advantage is a hump — it peaks near 60 days at +0.089 AUC and is still +0.028 at 182 days — and that a *fixed* narrow window loses that advantage as the estimand widens, crossing zero somewhere between 60 and 182 days.

Not supportable: an exact crossover day; any claim that the crossover is a property of the support width rather than of holding the conditioning window fixed; any single universal conditioning window (the re-seeking contrast's own crossover is [351, 364] days with P(no crossover) = 0.07, i.e. the trivial k = 365 coincidence, not a support boundary); any claim of monotone decay (the frozen summary's own P1 fails: the advantage is a hump); and any use of the 91/119-day numbers in an abstract or a headline. The quotable objects are the intervals, the no-crossover probabilities and the per-width paired intervals in `crossover.json` and `dilation_vs_reseek.csv`.

## Files and provenance

```json
{
  "script": "scripts/248_wrr_support_width_bootstrap.py",
  "command": "/home/lzq/anaconda3/bin/python3 scripts/248_wrr_support_width_bootstrap.py --draws 2000 --workers 32 --skip-masks",
  "label": "exploratory_post_open",
  "generated_utc": "2026-10-12T10:27:50Z",
  "python": "3.11.7",
  "platform": "Linux-6.6.20-x86_64-with-glibc2.35",
  "pandas": "2.1.4",
  "numpy": "1.26.4",
  "draws": 2000,
  "seed": 20261012,
  "workers": 32,
  "widths_days": [
    1,
    3,
    7,
    15,
    30,
    60,
    90,
    182,
    365
  ],
  "tolerance_fraction_primary": 0.4716981132075471,
  "tolerance_fractions": {
    "primary": 0.4716981132075471,
    "quarter": 0.25,
    "one": 1.0
  },
  "inputs": {
    "endpoint_cases": {
      "path": "results/v18_closure/endpoint_cases.parquet",
      "sha256": "b5112ef8e548f15de6b9774df3349f17ada132f281fe74ad9f5125a6c323428f"
    },
    "cases_development": {
      "path": "results/v17_fitness/step3_cases/cases.parquet",
      "sha256": "845ca7f91ede1315d69683f85b5d6902ac04ecae93e2d94c59caec6db5c6e097"
    },
    "cases_reserved_open": {
      "path": "results/v17_fitness/step10_confirmation/reserved_cases.parquet",
      "sha256": "51b5771520fc599f7319f9b017e5e954c6bf7d4a4bd74d7ae146f526d5610730"
    },
    "frozen_summary": "results/v18_closure/e6_support_width/summary.json"
  },
  "n_development_cases": 40704,
  "n_development_networks": 110,
  "n_reserved_open_cases": 10820,
  "n_reserved_open_networks": 36,
  "elapsed_seconds": 290.88788771629333
}
```

