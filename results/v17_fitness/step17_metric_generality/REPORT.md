# Step 17 — does the finding hold for other thermal metrics?

Each metric is scored against a tolerance equal to 0.47 of its own interannual standard deviation, so the four endpoints are compared on equal terms.

     metric  interannual_sd  tolerance_c     n  base_rate  auc_peak_overlap  auc_warm_coverage  auc_longest_run  auc_missing_fraction  grouped_auc_length_only  grouped_auc_length_plus_timing  rate_at_70_length_rule  rate_at_70_peak_overlap_rule  rate_at_70_three_variable_rule  rate_at_70_random  points_saved_three_variable
   hottest7          1.1561       0.5453 40704     0.1663            0.8227             0.8244           0.7520                0.7460                   0.7424                          0.8498                  0.1032                        0.0637                          0.0625             0.1660                       4.0677
  hottest30          1.0811       0.5100 40704     0.1456            0.8188             0.8204           0.7501                0.7441                   0.7456                          0.8460                  0.0899                        0.0549                          0.0537             0.1447                       3.6149
annual_mean          0.5454       0.2573 40704     0.0991            0.6720             0.8181           0.8453                0.8447                   0.8283                          0.8311                  0.0325                        0.0612                          0.0335             0.0974                      -0.0983
  coldest30          0.7993       0.3770 40704     0.0515            0.4473             0.6187           0.8034                0.8177                   0.7912                          0.8966                  0.0175                        0.0528                          0.0095             0.0519                       0.7967
amplitude30          1.3639       0.6434 40704     0.1311            0.7583             0.7923           0.7678                0.7650                   0.7547                          0.8128                  0.0732                        0.0607                          0.0582             0.1302                       1.4986

## Which axis wins, across tolerances

     metric  tolerance_fraction_of_sd  tolerance_c  base_rate  auc_peak_overlap  auc_warm_coverage  auc_longest_run winning_axis
   hottest7                    0.2500       0.2890     0.2413            0.8411             0.8323           0.7475       timing
   hottest7                    0.4717       0.5453     0.1663            0.8227             0.8244           0.7520       timing
   hottest7                    1.0000       1.1561     0.0811            0.8146             0.8353           0.7741       timing
  hottest30                    0.2500       0.2703     0.2348            0.8317             0.8208           0.7373       timing
  hottest30                    0.4717       0.5100     0.1456            0.8188             0.8204           0.7501       timing
  hottest30                    1.0000       1.0811     0.0607            0.8057             0.8281           0.7715       timing
annual_mean                    0.2500       0.1364     0.1998            0.6597             0.8024           0.8402       length
annual_mean                    0.4717       0.2573     0.0991            0.6720             0.8181           0.8453       length
annual_mean                    1.0000       0.5454     0.0274            0.7117             0.8648           0.8845       length
  coldest30                    0.2500       0.1998     0.0903            0.4344             0.5930           0.7802       length
  coldest30                    0.4717       0.3770     0.0515            0.4473             0.6187           0.8034       length
  coldest30                    1.0000       0.7993     0.0171            0.4870             0.6773           0.8374       length
amplitude30                    0.2500       0.3410     0.2383            0.7516             0.7786           0.7596       timing
amplitude30                    0.4717       0.6434     0.1311            0.7583             0.7923           0.7678       timing
amplitude30                    1.0000       1.3639     0.0495            0.7642             0.8152           0.7895       timing

## Three-variable rule minus length rule, at 70% retention, clustered by network

```json
{
  "hottest7": {
    "point": -0.04067665742463061,
    "low": -0.04843712245762238,
    "high": -0.033904675038807466,
    "se": 0.003798549886097129,
    "n_clusters": 110
  },
  "hottest30": {
    "point": -0.036149229635349035,
    "low": -0.04388498403415374,
    "high": -0.029072352135688064,
    "se": 0.0037368789266504594,
    "n_clusters": 110
  },
  "annual_mean": {
    "point": 0.0009826975046502637,
    "low": -0.0012095365694894961,
    "high": 0.002555797105440015,
    "se": 0.0009855226525129644,
    "n_clusters": 110
  },
  "coldest30": {
    "point": -0.007966869055557504,
    "low": -0.01179491237182771,
    "high": -0.006264486262548647,
    "se": 0.0014042612840396845,
    "n_clusters": 110
  },
  "amplitude30": {
    "point": -0.014986136945916544,
    "low": -0.020799361578153507,
    "high": -0.009891231040113824,
    "se": 0.0029191252021809485,
    "n_clusters": 110
  }
}
```

```json
{
  "question": "does the timing-over-length finding hold for metrics other than the annual peak?",
  "tolerance_rule": "0.472 of each metric's own interannual standard deviation",
  "timing_beats_length_marginally": {
    "hottest7": true,
    "hottest30": true,
    "annual_mean": false,
    "coldest30": false,
    "amplitude30": true
  },
  "three_variable_rule_beats_length_rule": {
    "hottest7": true,
    "hottest30": true,
    "annual_mean": false,
    "coldest30": true,
    "amplitude30": true
  },
  "points_saved": {
    "hottest7": 4.07,
    "hottest30": 3.61,
    "annual_mean": -0.1,
    "coldest30": 0.8,
    "amplitude30": 1.5
  },
  "winning_axis_is_stable_across_tolerances": {
    "amplitude30": [
      "timing"
    ],
    "annual_mean": [
      "length"
    ],
    "coldest30": [
      "length"
    ],
    "hottest30": [
      "timing"
    ],
    "hottest7": [
      "timing"
    ]
  }
}
```
