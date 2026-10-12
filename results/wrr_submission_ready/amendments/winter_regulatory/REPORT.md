# F16(a) - can a cold-season support axis replace the length rule for the coldest 30-day mean?

Artifact: `results/wrr_submission_ready/amendments/winter_regulatory/cold_support_contrast.csv`. Script: `scripts/251_wrr_winter_regulatory_endpoints.py cold`.

## What was computable from the stored tables

The development case table already stores coldest-30 reconstruction error for six estimators (`abserr_coldest30_<estimator>`), so the cold endpoint does **not** need a new run for its error side. What no step of the pipeline ever stored is a missingness measure restricted to the cold window: the table has `warm_observed_fraction` and `peak_overlap` and nothing for the cold season. Two cold axes were therefore built:

* `cold_season_observed_fraction` - observed share of the non-warm calendar months (Oct-Apr), an exact algebraic function of stored `total_missing`, `missing_fraction`, `warm_observed_fraction` and `year` (the stored `missing_fraction = total_missing / n_days` recovers `n_days` exactly). It reproduces the mask-derived value to 1.1e-16.
* `cold_window_overlap` - share of the station's climatological coldest-30-day window that the outage hides, the mirror of the stored `peak_overlap`. It is not stored anywhere, so the outage realizations were regenerated from the v17 seeds. The regeneration reproduces 40,704 of 40,704 stored rows one-for-one, with maximum absolute deviation 0.0 on `longest_run`, `total_missing`, `peak_overlap` and `warm_observed_fraction`.

Both are decision-time visible: calendar plus the observed/hidden pattern, with the cold window estimated from every year but the target one, exactly as `peak_overlap` is.

## Result at 70% retention

n = 40,704 development cases, 110 networks, coldest-30 error through the information-conditioned policy of step 17 (whose warm-endpoint numbers this table reproduces to four decimals: hottest-30 peak overlap 0.8188, warm coverage 0.8204, length 0.7501).

| axis | AUC (0.5 C) | AUC (0.4717 sd = 0.377 C) | consequential-error rate at 70% (0.5 C) | rate (0.4717 sd) |
| --- | --- | --- | --- | --- |
| `cold_window_overlap` | 0.8761 | 0.8779 | 0.0054 | 0.0082 |
| `cold_season_observed_fraction` | 0.8966 | 0.8918 | 0.0045 | 0.0081 |
| `longest_run` | 0.8191 | 0.8034 | 0.0104 | 0.0175 |
| `missing_fraction` | 0.8312 | 0.8177 | 0.0099 | 0.0166 |
| `peak_overlap` | 0.4684 | 0.4473 | 0.0354 | 0.0529 |
| `warm_observed_fraction` | 0.6405 | 0.6187 | 0.0192 | 0.0301 |

Base rate of a consequential cold error: 0.0360 at 0.5 C, 0.0515 at 0.4717 sd.

| contrast (network-clustered bootstrap, 1200 draws) | point | 95% CI |
| --- | --- | --- |
| literal_0.5C__rate_gap_cold_window_minus_length | -0.00502 | (-0.00856, -0.00293) |
| literal_0.5C__rate_gap_cold_season_minus_length | -0.00590 | (-0.00901, -0.00482) |
| literal_0.5C__auc_gap_cold_window_minus_length | +0.05705 | (+0.03653, +0.08269) |
| equal_relative_0.4717sd__rate_gap_cold_window_minus_length | -0.00934 | (-0.01527, -0.00576) |
| equal_relative_0.4717sd__rate_gap_cold_season_minus_length | -0.00941 | (-0.01430, -0.00771) |
| equal_relative_0.4717sd__auc_gap_cold_window_minus_length | +0.07451 | (+0.05080, +0.10378) |

Positive rate gaps mean the cold axis does *worse* than the length rule; negative means better. The AUC gap is oriented so that positive means the cold window discriminates better.

## Does the cold axis add anything beyond gap length?

Out-of-fold grouped logistic AUC (5-fold, grouped by network):

| feature set | AUC (0.5 C) | AUC (0.4717 sd) |
| --- | --- | --- |
| `length only` | 0.8132 | 0.7981 |
| `length plus missing fraction` | 0.8275 | 0.8165 |
| `length plus cold window` | 0.9048 | 0.9050 |
| `length plus cold season` | 0.8977 | 0.8963 |

## Estimator sensitivity

| estimator | n | base rate | AUC cold window | AUC length | AUC warm coverage |
| --- | --- | --- | --- | --- | --- |
| `observed_days` | 40,691 | 0.1248 | 0.8907 | 0.7457 | 0.5535 |
| `doy_climatology` | 40,704 | 0.0757 | 0.8853 | 0.7552 | 0.5686 |
| `smooth_climatology` | 40,704 | 0.0751 | 0.8867 | 0.7593 | 0.5706 |
| `linear_interp` | 40,704 | 0.0776 | 0.9002 | 0.8150 | 0.6079 |
| `donor_ridge` | 31,787 | 0.0207 | 0.8830 | 0.7991 | 0.5996 |
| `air_ridge` | 921 | 0.0912 | 0.7783 | 0.7865 | 0.5824 |

## What the warm-season result actually implies for cold extremes

The manuscript makes two connected assertions. (i) In the subsection on Table 2 (`tab:axes`, the table headed 'The share of the support a gap hides orders every endpoint, and the ordering reverses'): *"peak-window overlap has an AUC of 0.447 for the cold extreme, because hiding the summer peak carries no information about the winter minimum"*. (ii) In 'What an agency should change, and in what order': *"keep length-based rules for annual means, cold extremes and the sine-fit regime parameters"*. Assertion (i) is reproduced here exactly (0.4473 at 0.4717 sd) and is true as stated - it is a statement about the warm-window axis. Assertion (ii) is the non-sequitur: it draws a rule for cold extremes from a measurement that cannot see the cold window, without ever measuring a cold-season axis. The stored tables measure why the inference fails:

* The climatological coldest-30-day window shares a mean of 0.0000 of its days with the climatological hottest-30-day window (maximum 0.0000 across cases), so the warm-season coverage axis is measuring a window that is disjoint from the cold support. It cannot be evidence about it either way.
* Spearman correlation between `warm_observed_fraction` and `cold_window_overlap` is 0.0007; between `longest_run` and `cold_window_overlap` it is 0.2852.
* Once a cold-season axis is measured directly, it beats the length rule on the cold endpoint: AUC 0.8779 vs 0.8034 (difference +0.0745, 95% CI +0.0508 to +0.1038) at the equal-relative tolerance, and 0.8761 vs 0.8191 at 0.5 C.
* At equal retention the consequential-error rate falls from 0.0104 under the length rule to 0.0054 under the cold-window rule at 0.5 C (-0.00502, 95% CI -0.00856 to -0.00293) and from 0.0175 to 0.0082 at 0.4717 sd.

The honest summary is therefore: **the warm-season result implies nothing about cold extremes without a cold-season axis**, and the manuscript's own stated mechanism (summer gaps cannot inform the winter minimum) is a reason to build that axis, not a reason to fall back on gap length. Once built, the axis works, and the cold extreme is on the same side of the extremes-versus-averages line as the warm extreme.

## Caveats recorded with the result

* The cold window is estimated, so the rule inherits its wander. Median circular spread of the climatological trough-window start across years: 1.6 days (mean 3.0, p90 6.9); the raw day-of-year standard deviation (median 2.0 days) is inflated by the 31 December wrap.
* 100.0% of distinct climatological cold windows fall entirely inside the Oct-Apr cold months, so the season-length axis and the window axis are measuring the same season, not two different ones.
* Rates at 70% retention break ties in the axis score with a uniform jitter, the convention step 17 used in `frontier_rate`. Coverage fractions are heavily tied, so an untied recomputation moves the cold-window rate from 0.0054 to about 0.0047 and the cold-season rate stays at 0.0045; the AUCs, the AUC-gap intervals and the conclusions are unaffected, and the bootstrap contrasts resample the same jittered scores throughout.
* This is a retrospective analysis on the opened development split. It is not a pre-registered confirmation and the sealed USGS panel was not re-scored.

* Per-estimator sensitivity: the cold-window axis beats gap length for five of the six estimators; the single exception is `air_ridge` (n = 921 cases only, where air forcing exists), AUC 0.7783 against 0.7865. The ordering is therefore a property of the endpoint, not of the policy's estimator choice.

# F16(b) - the sine-fit phase has no low-amplitude identifiability rule

Artifacts: `sine_phase_amplitude.csv`, `sine_phase_rule_sweep.csv`, `sine_phase_cases.parquet`, `summary.json`. Script: `scripts/251_wrr_winter_regulatory_endpoints.py sine`.

## The code path

`v18_closure/endpoints.py:sine_parameters` returns `sine_phase` whenever at least 30 finite days are present and the least-squares solve succeeds. `endpoint_rows` then computes `abserr_sine_phase` unconditionally, and `step17`/`e3_sine_endpoints` treat every such case as a scored observation. Nothing in the pipeline tests whether the fitted amplitude is distinguishable from zero, so a record whose seasonal cycle is flat - or an outage pattern that removes the cycle - contributes a phase drawn from noise to the reported AUC.

The noise scale is the residual sd of the same three-parameter fit; it is not returned by `sine_parameters`, so it was recomputed here. The recomputation is checked against the stored columns: $n$ = 40,704 development cases, 100.0% of them regenerated, maximum absolute deviation 0.00e+00 on `observed_sine_amplitude` and 0.00e+00 days on `observed_sine_phase`.

## How phase error grows as the amplitude shrinks

Phase error is the circular difference from the complete-year fit, in days; the study's own phase tolerance is 2.1218 days (0.4717 of the phase's interannual sd of 4.498 days). A phase drawn at random from the year has an expected absolute error of 91.3 days.

Protocol `repaired` (the manuscript's Table 3 row):

| fitted amplitude / residual sd | n | share | median abs phase error (d) | q90 (d) | noise-implied 95% half-width (d) | median error / implied | consequential rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [0.5, 1.0) | 2 | 0.0% | 3.2 | 3.8 | 11.25 | 0.57 | 1.000 |
| [1.0, 1.5) | 79 | 0.2% | 1.1 | 6.5 | 6.78 | 0.31 | 0.266 |
| [1.5, 2.0) | 230 | 0.6% | 1.1 | 7.1 | 5.32 | 0.40 | 0.330 |
| [2.0, 3.0) | 1,560 | 3.8% | 0.4 | 3.2 | 3.58 | 0.23 | 0.162 |
| [3.0, 4.0) | 5,486 | 13.5% | 0.2 | 2.1 | 2.60 | 0.17 | 0.096 |
| [4.0, 5.0) | 9,654 | 23.7% | 0.2 | 2.0 | 2.08 | 0.21 | 0.095 |
| [5.0, 8.0) | 19,966 | 49.1% | 0.2 | 2.2 | 1.62 | 0.29 | 0.105 |
| [8.0, inf) | 3,726 | 9.2% | 0.7 | 4.2 | 1.16 | 1.17 | 0.251 |

Protocol `observed_days_only` (Johnson et al.'s own protocol):

| fitted amplitude / residual sd | n | share | median abs phase error (d) | q90 (d) | noise-implied 95% half-width (d) | median error / implied | consequential rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [0.0, 0.5) | 14 | 0.0% | 81.5 | 154.6 | 52.56 | 3.10 | 1.000 |
| [0.5, 1.0) | 26 | 0.1% | 53.6 | 155.2 | 20.82 | 5.14 | 0.962 |
| [1.0, 1.5) | 112 | 0.3% | 3.9 | 84.2 | 7.24 | 1.07 | 0.679 |
| [1.5, 2.0) | 257 | 0.6% | 2.9 | 22.5 | 5.35 | 1.10 | 0.560 |
| [2.0, 3.0) | 1,818 | 4.5% | 1.4 | 14.0 | 3.62 | 0.80 | 0.425 |
| [3.0, 4.0) | 5,596 | 13.7% | 0.8 | 7.6 | 2.61 | 0.63 | 0.321 |
| [4.0, 5.0) | 9,391 | 23.1% | 0.7 | 7.1 | 2.08 | 0.66 | 0.276 |
| [5.0, 8.0) | 19,620 | 48.2% | 0.7 | 8.0 | 1.62 | 0.92 | 0.302 |
| [8.0, inf) | 3,869 | 9.5% | 3.4 | 26.7 | 1.16 | 5.93 | 0.598 |

## The proposed reporting rule, and why that threshold

**Rule.** Report the fitted phase only when the fitted amplitude exceeds $k$ times the residual sd of the same fit; otherwise report the amplitude (or the mean) and mark the phase unidentifiable. The threshold is not asserted: for a three-parameter sine fit the phase standard error is $\mathrm{se}(\hat\phi) = \sigma\sqrt{2/n}/A$ radians, so requiring the 95% interval ($\pm 2\,\mathrm{se}$) to be no wider than the study's own phase tolerance $\tau$ gives $A/\sigma \ge 2\sqrt{2/n}/\tau$. With the median $n$ = 305 observed days and $\tau$ = 0.0365 rad (2.1218 days) this is $k^\ast$ = 4.44.

Rounded to the nearest half, the applied rule is **report phase when $A/\sigma \ge 4.5$, suppress below**. The sweep shows the consequence of moving that line:

| k (A/sigma) | retained cases | share retained | consequential rate retained | consequential rate suppressed | share of all consequential errors suppressed |
| --- | --- | --- | --- | --- | --- |
| 0.00 | 40,703 | 100.0% | 0.119 | 1.000 | 0.0% |
| 1.00 | 40,701 | 100.0% | 0.119 | 1.000 | 0.1% |
| 2.00 | 40,392 | 99.2% | 0.117 | 0.321 | 2.1% |
| 3.00 | 38,832 | 95.4% | 0.115 | 0.189 | 7.3% |
| 4.00 | 33,346 | 81.9% | 0.119 | 0.119 | 18.2% |
| 4.50 | 28,790 | 70.7% | 0.122 | 0.111 | 27.4% |
| 5.00 | 23,692 | 58.2% | 0.128 | 0.105 | 37.1% |
| 6.00 | 13,607 | 33.4% | 0.154 | 0.101 | 56.7% |

## How many cases the missing rule would have caught

| protocol | A/sigma cut | cases below | share below | median abs phase error below (d) | consequential rate below | share of all consequential errors below |
| --- | --- | --- | --- | --- | --- | --- |
| repaired | 1.0 | 2 | 0.005% | 3.2 | 1.000 | 0.0% |
| repaired | 1.5 | 81 | 0.199% | 1.1 | 0.284 | 0.5% |
| repaired | 2.0 | 311 | 0.764% | 1.1 | 0.318 | 2.0% |
| repaired | 4.0 | 7,357 | 18.074% | 0.3 | 0.119 | 18.2% |
| observed_days_only | 1.0 | 40 | 0.098% | 60.1 | 0.975 | 0.3% |
| observed_days_only | 1.5 | 152 | 0.373% | 10.8 | 0.757 | 0.8% |
| observed_days_only | 2.0 | 409 | 1.005% | 3.9 | 0.633 | 1.9% |
| observed_days_only | 4.0 | 7,823 | 19.219% | 1.0 | 0.361 | 20.7% |

## Is the relationship monotone? No, and the rule has to say so

* `repaired`: Spearman rho between log(A/sigma) and the absolute phase error is +0.0674; between the fitted amplitude itself and the error, -0.1287; between the *true* seasonal amplitude and the error, -0.1224.
* `observed_days_only`: Spearman rho between log(A/sigma) and the absolute phase error is +0.0783; between the fitted amplitude itself and the error, -0.0866; between the *true* seasonal amplitude and the error, -0.1115.

The decline is confined to the low-amplitude end: the median error falls from 1.1 days in [1.0, 1.5) to 0.2 days in [3.0, 4.0), and the consequential rate falls from 0.266 to 0.095. Above that the relationship flattens and then turns up - median 0.22 days in [4.0, 5.0) against 0.68 days in [8.0, inf) - which is why the overall Spearman correlation between log(A/sigma) and the error is slightly *positive* rather than negative. Two readings are consistent with that, and they have different consequences:

1. The tail is not sampling noise. At the top bin the noise-implied 95% half-width is 1.16 days while the observed q90 error is 4.2 days - a factor 3.6 - against a factor of 1.0 in the [4.0, 5.0) bin, where the fit is closest to the sampling-theory prediction. If the rule were read as a claim that above the floor the phase error is pure sampling noise, the top bin rejects it.
2. The rise is therefore attributable to something the amplitude does not measure - most plainly sinusoidal misspecification, since a large A/sigma means a large, sharply seasonal cycle, and the snowmelt-driven and regulated rivers that have one are exactly where a single sinusoid is least adequate. This report does not test that mechanism, and the rule does not depend on it.

The practical consequence is that there are two defensible thresholds with different jobs, and the manuscript should say which one it adopts:

* an **identifiability floor** at $A/\sigma \ge 1$ (or 1.5) removes the cases whose phase is drawn from noise - 40 cases (0.10%) under the observed-days protocol, with a 97.5% consequential rate - and costs 0.20% of the repaired sample;
* a **precision floor** at $A/\sigma \ge 4.5$, which is what the tolerance derivation gives, additionally guarantees the phase's 95% interval fits inside this study's own tolerance, at the cost of 29.3% of the repaired sample with no improvement in the consequential-error rate (0.122 retained against 0.111 suppressed, i.e. the discarded cases were not the erroneous ones).

## What the rule does to the reported phase comparison

| population | n | base rate | AUC peak overlap | AUC transition | AUC missing fraction | AUC outage length | AUC influence-weighted | influence - missing fraction (95% CI) | influence - length (95% CI) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_cases | 40,704 | 0.1187 | 0.5829 | 0.8314 | 0.8346 | 0.8357 | 0.8474 | +0.0127 (+0.0091, +0.0175) | +0.0117 (+0.0088, +0.0159) |
| identifiable_only | 28,790 | 0.1219 | 0.5909 | 0.8347 | 0.8346 | 0.8375 | 0.8472 | +0.0126 (+0.0084, +0.0188) | +0.0097 (+0.0068, +0.0146) |
| identifiable_truth_noise_scale | 26,266 | 0.1050 | 0.5831 | 0.8435 | 0.8405 | 0.8439 | 0.8553 | +0.0148 (+0.0101, +0.0221) | +0.0114 (+0.0077, +0.0170) |

For reference, the published `e3_sine_endpoints` contrast on all development cases is +0.01275 (0.00899, 0.01711) for influence-weighted minus whole-year missing fraction; the `all_cases` row above reproduces it. The `identifiable_truth_noise_scale` row repeats the identifiable-only population with the complete-year residual sd in place of the observed-days residual sd, to bracket the noise scale (median observed/truth ratio 0.988).

## Verdict

The requirement is supported. The nuance that matters for how it is written up is that the unidentifiable cases are concentrated in the authors' own protocol rather than in the repaired one.

* The estimator does report a phase with no amplitude guard, so the published endpoint mixes identified and unidentified phases. Under the authors' own protocol (`observed_days_only`, which produces the 0.590 phase AUC quoted in the manuscript), 40 cases (0.10%) have a fitted amplitude below the residual sd; their median absolute phase error is 60.1 days against 91.3 days expected from a phase drawn at random, and 97.5% of them are consequential errors. Those cases carry no phase information and are currently scored.
* Under the repaired protocol the defect is latent rather than active: repair restores the seasonal cycle, so only 2 of 40,704 cases (0.0049%) fall below A/sigma = 1 and 81 (0.20%) below 1.5. The rule is still required, but it is not what rescues the repaired phase result.
* Applying the derived rule at k = 4.5 removes 29.3% of the repaired cases (n = 28,790 retained) and leaves the axis conclusion unchanged: influence-weighted beats the whole-year missing fraction by +0.0126 and outage length by +0.0097, both intervals excluding zero.

**Corrected statement for the manuscript.** The sine-fit phase is a reportable endpoint only where the fitted amplitude is distinguishable from the noise: report the phase when A/sigma >= 4.5 (the value implied by requiring the phase's 95% interval to be no wider than this study's own phase tolerance of 2.12 days), suppress it below that floor, and state that above the floor the residual phase error is no longer explained by sampling noise alone.
