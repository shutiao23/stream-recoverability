# E6 — support width as a continuous knob

Development cases, each endpoint scored at 0.47 of its own interannual standard deviation.

|   support_width_days |   interannual_sd_c |   base_rate |   auc_support_restricted |   auc_peak_overlap |   auc_missing_fraction |   auc_longest_run |   support_minus_missing_fraction |   fixed_peak_window_minus_missing_fraction |   support_minus_best_hand_chosen |
|---------------------:|-------------------:|------------:|-------------------------:|-------------------:|-----------------------:|------------------:|---------------------------------:|-------------------------------------------:|---------------------------------:|
|                    1 |             1.176  |     0.1794  |                   0.76   |             0.8245 |                 0.7509 |            0.7565 |                        0.009125  |                                   0.07362  |                        -0.0645   |
|                    3 |             1.167  |     0.1741  |                   0.7662 |             0.8241 |                 0.7462 |            0.7517 |                        0.02002   |                                   0.07797  |                        -0.05794  |
|                    7 |             1.156  |     0.1663  |                   0.7784 |             0.8227 |                 0.746  |            0.752  |                        0.03239   |                                   0.07667  |                        -0.04428  |
|                   15 |             1.122  |     0.1561  |                   0.8022 |             0.8209 |                 0.7434 |            0.7495 |                        0.05885   |                                   0.07754  |                        -0.01869  |
|                   30 |             1.081  |     0.1456  |                   0.827  |             0.8188 |                 0.7441 |            0.7501 |                        0.08292   |                                   0.07468  |                         0.008231 |
|                   60 |             1.018  |     0.1315  |                   0.8545 |             0.8154 |                 0.7652 |            0.7711 |                        0.08931   |                                   0.05019  |                         0.03912  |
|                   90 |             0.9399 |     0.1265  |                   0.8555 |             0.7917 |                 0.7901 |            0.7947 |                        0.06544   |                                   0.001581 |                         0.06083  |
|                  182 |             0.7415 |     0.1185  |                   0.851  |             0.7282 |                 0.8227 |            0.8264 |                        0.02823   |                                  -0.09457  |                         0.02454  |
|                  365 |             0.5454 |     0.09913 |                   0.8441 |             0.672  |                 0.8447 |            0.8453 |                       -0.0006441 |                                  -0.1727   |                        -0.001272 |

## Network-clustered contrast, fixed peak window against whole-year missing fraction

|   support_width_days |     point |      low |     high | excludes_zero   |
|---------------------:|----------:|---------:|---------:|:----------------|
|                    1 |  0.07362  |  0.05253 |  0.09723 | True            |
|                    3 |  0.07797  |  0.05459 |  0.1036  | True            |
|                    7 |  0.07667  |  0.05314 |  0.1044  | True            |
|                   15 |  0.07754  |  0.05316 |  0.1062  | True            |
|                   30 |  0.07468  |  0.04917 |  0.1039  | True            |
|                   60 |  0.05019  |  0.02843 |  0.07845 | True            |
|                   90 |  0.001581 | -0.01778 |  0.02691 | False           |
|                  182 | -0.09457  | -0.1111  | -0.07745 | True            |
|                  365 | -0.1727   | -0.1921  | -0.157   | True            |

## Which conditioning window a screen should actually use

Rows are the estimand; columns are the climatological window the axis conditions on. The diagonal is the estimand's own support.

|   endpoint_width_days |   best_conditioning_width_days |   auc_at_best |   auc_at_own_support |   gain_from_widening |   median_support_location_sd_days |
|----------------------:|-------------------------------:|--------------:|---------------------:|---------------------:|----------------------------------:|
|                     1 |                             90 |        0.8615 |               0.76   |             0.1015   |                            16.66  |
|                     3 |                             60 |        0.8581 |               0.7662 |             0.09191  |                            16.34  |
|                     7 |                             90 |        0.8551 |               0.7784 |             0.07675  |                            16.5   |
|                    15 |                             60 |        0.8528 |               0.8022 |             0.05059  |                            15.25  |
|                    30 |                             90 |        0.8516 |               0.827  |             0.02456  |                            13.66  |
|                    60 |                             90 |        0.8597 |               0.8545 |             0.005229 |                             9.366 |
|                    90 |                             90 |        0.8555 |               0.8555 |             0        |                             7.43  |
|                   182 |                            182 |        0.851  |               0.851  |             0        |                             6.873 |
|                   365 |                            365 |        0.8441 |               0.8441 |             0        |                           nan     |

## Verdicts

```json
{
  "P1_monotone_decay": {
    "prediction": "the support-restricted advantage decays monotonically in k",
    "outcome": false,
    "advantage_by_width": {
      "1": 0.009125382819104133,
      "3": 0.020024084492161864,
      "7": 0.03239400608627219,
      "15": 0.0588513174446359,
      "30": 0.08291501846636284,
      "60": 0.08931095532770195,
      "90": 0.06544346327287731,
      "182": 0.028226131133407106,
      "365": -0.0006440921654089493
    },
    "advantage_at_365": -0.0006440921654089493
  },
  "P2_crossover": {
    "prediction": "the fixed 30-day peak window loses its advantage as the support widens",
    "crossover_width_days": 91.04832050492402,
    "advantage_by_width": {
      "1": 0.07362219453603314,
      "3": 0.07796863449048974,
      "7": 0.07667204731016408,
      "15": 0.07754332326011915,
      "30": 0.07468427878658634,
      "60": 0.05019419882667442,
      "90": 0.001581163836111954,
      "182": -0.09456603238723094,
      "365": -0.17274298158045565
    }
  },
  "P3_support_axis_dominates": {
    "prediction": "the support-restricted axis is at least as good as the best hand-chosen axis at every k",
    "minimum_margin": -0.064496811716929,
    "outcome": false,
    "margin_by_width": {
      "1": -0.064496811716929,
      "3": -0.05794454999832788,
      "7": -0.044278041223891895,
      "15": -0.018692005815483248,
      "30": 0.0082307396797765,
      "60": 0.03911675650102753,
      "90": 0.060830635854881576,
      "182": 0.024536332752609136,
      "365": -0.001271919735557181
    }
  },
  "P1_and_P3_diagnosis": {
    "observation": "the support-restricted advantage is a hump peaking near a 60-day support rather than a monotone decay, and below a 30-day support the fixed 30-day window beats the estimand's own support",
    "explanation": "the axis conditions on the CLIMATOLOGICAL hottest-k window, which is an estimate of where this year's window will fall. For a narrow estimand that estimate is poor, so the right conditioning set is the support dilated by the year-to-year wander of its own location",
    "best_conditioning_width_by_endpoint": {
      "1": 90,
      "3": 60,
      "7": 90,
      "15": 60,
      "30": 90,
      "60": 90,
      "90": 90,
      "182": 182,
      "365": 365
    },
    "support_location_sd_days": {
      "1": 16.65683140401892,
      "3": 16.335605263840574,
      "7": 16.498111866458576,
      "15": 15.246939354572232,
      "30": 13.659295541698866,
      "60": 9.366405487315083,
      "90": 7.430309432627253,
      "182": 6.872741063376723,
      "365": null
    },
    "gain_from_widening_auc": {
      "1": 0.10153996200263049,
      "3": 0.09191277540469,
      "7": 0.07674647079386276,
      "15": 0.050593145860988065,
      "30": 0.024561992394277032,
      "60": 0.005228659896074683,
      "90": 0.0,
      "182": 0.0,
      "365": 0.0
    }
  }
}
```
