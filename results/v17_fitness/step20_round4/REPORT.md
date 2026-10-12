# Step 20 — four gaps a fourth reading finds

## 1. Does each endpoint's error scale with the covariate the mechanism names?

     metric missing_quartile             peak_overlap  mean_abs_error_c
  hottest30               Q1                     none            0.0087
  hottest30               Q1                    <half            0.1114
  hottest30               Q1                 most/all            0.2073
  hottest30               Q2                     none            0.0284
  hottest30               Q2                    <half            0.2071
  hottest30               Q2                 most/all            0.3717
  hottest30               Q3                     none            0.0336
  hottest30               Q3                    <half            0.2691
  hottest30               Q3                 most/all            0.5475
  hottest30               Q4                     none            0.1220
  hottest30               Q4                    <half            0.3119
  hottest30               Q4                 most/all            0.7260
  hottest30      RATIO Q4/Q1                 averaged            3.5424
  hottest30         averaged RATIO most-or-all / none            9.6121
annual_mean               Q1                     none            0.0117
annual_mean               Q1                    <half            0.0175
annual_mean               Q1                 most/all            0.0342
annual_mean               Q2                     none            0.0460
annual_mean               Q2                    <half            0.0546
annual_mean               Q2                 most/all            0.0650
annual_mean               Q3                     none            0.1044
annual_mean               Q3                    <half            0.1212
annual_mean               Q3                 most/all            0.1359
annual_mean               Q4                     none            0.1819
annual_mean               Q4                    <half            0.2004
annual_mean               Q4                 most/all            0.2638
annual_mean      RATIO Q4/Q1                 averaged           10.1779
annual_mean         averaged RATIO most-or-all / none            1.4501

## 2. Does a screen on the amplitude also beat the length rule?

```json
{
  "tolerance_c": 0.6421505999903545,
  "development": {
    "n_cases": 40704,
    "length_rule_at_70": 0.07370231284876988,
    "certificate_at_70": 0.027340048432948443,
    "points_saved": 4.636226441582143
  },
  "reserved": {
    "n_cases": 10820,
    "length_rule_at_70": 0.07499339846844467,
    "certificate_at_70": 0.03538420913651967,
    "points_saved": 3.9609189331925005
  }
}
```

## 3. The exceedance judgement, restricted to years where the call is close

                   subset            treatment  n_scored  misclassification_rate
             all retained    observed_days_all     10820                  0.0686
             all retained      reconstruct_all     10820                  0.0197
             all retained      length_screened      7984                  0.0153
             all retained certificate_screened      7305                  0.0036
truth within 1.0 °C of 20    observed_days_all      1894                  0.1684
truth within 1.0 °C of 20      reconstruct_all      1894                  0.0950
truth within 1.0 °C of 20      length_screened      1418                  0.0726
truth within 1.0 °C of 20 certificate_screened      1299                  0.0192
truth within 0.5 °C of 20    observed_days_all       953                  0.1910
truth within 0.5 °C of 20      reconstruct_all       953                  0.1312
truth within 0.5 °C of 20      length_screened       713                  0.1024
truth within 0.5 °C of 20 certificate_screened       650                  0.0338

## 4. Screening versus abstaining on the judgement itself

                                         policy  share_of_years_judged  n_judged  misclassification_rate  false_negative_rate
                 screen at the 0.5 °C tolerance                 0.6751      7305                  0.0036               0.0039
abstain only where the interval straddles 20 °C                 0.9266     10026                  0.0042               0.0064
                                           both                 0.6572      7111                  0.0008               0.0012
