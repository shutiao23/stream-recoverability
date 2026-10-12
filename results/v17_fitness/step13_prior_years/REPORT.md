# Step 13 — estimators fit on strictly prior years

The main protocol is leave-one-year-out within the station, which is what offline archive repair actually permits. This is the stricter alternative: only years before the outage are available, so at least two prior complete years are required and the earliest years of every station drop out.

                          protocol  cases  station_years  policy_mean_abs_error_c  length_rule_at_70  certificate_at_70  contrast_points  ci_low  ci_high  coverage
         leave_one_year_out (main)  40704           4045                   0.2416             0.0924             0.0293          -6.3454 -7.1203  -5.5247    0.8973
strictly_prior_years (sensitivity)  33633           3337                   0.2700             0.0947             0.0355          -5.9211 -6.7173  -4.9891    0.9055

```json
[
  {
    "protocol": "leave_one_year_out (main)",
    "n_cases": 40704,
    "n_networks": 110,
    "n_station_years": 4045,
    "length_rule_at_70": {
      "rate_above_0.5": 0.09240866177657671,
      "mean_abs_error_c": 0.15393020426995727
    },
    "certificate_at_70": {
      "rate_above_0.5": 0.02934053978170077,
      "mean_abs_error_c": 0.06582251658199491
    },
    "contrast_points": -6.3454181728845676,
    "ci_points": [
      -7.12031069874207,
      -5.524692276175337
    ],
    "johnson91_retention": 0.7063924921383647,
    "johnson91_rate": 0.09334678120543943,
    "certificate_at_johnson_retention": 0.030292491218307654,
    "mean_abs_error_policy_c": 0.24157744533035794,
    "coverage": 0.8973319575471698
  },
  {
    "protocol": "strictly_prior_years (sensitivity)",
    "n_cases": 33633,
    "n_networks": 110,
    "n_station_years": 3337,
    "length_rule_at_70": {
      "rate_above_0.5": 0.0946778235568959,
      "mean_abs_error_c": 0.16440557488238222
    },
    "certificate_at_70": {
      "rate_above_0.5": 0.035467017797222104,
      "mean_abs_error_c": 0.07309455695175675
    },
    "contrast_points": -5.9210805759673795,
    "ci_points": [
      -6.7173101910190285,
      -4.989113915658897
    ],
    "johnson91_retention": 0.7032973567627033,
    "johnson91_rate": 0.09503678024858375,
    "certificate_at_johnson_retention": 0.03614610636678786,
    "mean_abs_error_policy_c": 0.26998077240036195,
    "coverage": 0.9054500044599054
  }
]
```
