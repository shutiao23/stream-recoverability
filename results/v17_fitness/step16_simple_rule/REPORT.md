# Step 16 — the deployable three-variable rule

Fitted on development networks, applied unchanged to the reserved panel.

```json
{
  "form": "risk score = 1 / (1 + exp(-(b0 + b1*peak_overlap + b2*warm_observed_fraction + b3*longest_run_days)))",
  "intercept_b0": -1.30211,
  "coefficients": {
    "peak_overlap": 2.070406,
    "warm_observed_fraction": -2.411588,
    "longest_run": -0.00187
  },
  "definitions": {
    "peak_overlap": "share of the station's climatological hottest-30 window that the outage hides, from training years only, 0-1",
    "warm_observed_fraction": "share of May-September days that remain observed, 0-1",
    "longest_run_days": "length in days of the longest consecutive outage"
  },
  "use": "rank station-years by the score and retain the lowest; or pick a cut-off from the retention your archive can afford",
  "fitted_on": "110 development networks; scored unchanged on 36 reserved networks"
}
```

In the contrast rows, the three numeric columns are the point estimate and the
two interval ends, in percentage points.

      panel                                         screen  rate_above_0.5_at_70  mean_abs_error_at_70  severe_underestimate_at_70
development                            three-variable rule                0.0550                0.0982                      0.0122
development                             outage-length rule                0.0925                0.1535                      0.0235
development contrast: three-variable minus length (points)               -3.7483               -4.5378                     -3.0429
   reserved                            three-variable rule                0.0417                0.0752                      0.0063
   reserved                             outage-length rule                0.0961                0.1491                      0.0194
   reserved contrast: three-variable minus length (points)               -5.4397               -6.8475                     -3.9587
