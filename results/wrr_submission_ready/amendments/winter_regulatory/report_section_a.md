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

