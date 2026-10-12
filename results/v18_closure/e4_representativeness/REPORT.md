# E4 — representativeness of the retained archive

At 70% retention.

| split       | rule                                                   |   error_rate_pct |   points_vs_global_screen |   rho_ELEV_SITE_M |   donor_regime_spread_points |   station_retention_sd |   peak_shift_c |
|:------------|:-------------------------------------------------------|-----------------:|--------------------------:|------------------:|-----------------------------:|-----------------------:|---------------:|
| development | length rule (incumbent)                                |            8.879 |                   5.945   |          -0.05331 |                      4.832   |                0.09541 |       0.01025  |
| development | peak-overlap rule                                      |            5.303 |                   2.369   |          -0.2287  |                      2.986   |                0.08696 |       0.04007  |
| development | calibrated screen, global threshold                    |            2.934 |                   0       |          -0.2587  |                     15.4     |                0.1513  |       0.1767   |
| development | calibrated screen, balanced within donor_regime        |            3.166 |                   0.2317  |          -0.2351  |                      0.01672 |                0.1464  |       0.1641   |
| development | calibrated screen, balanced within elevation_tertile   |            2.976 |                   0.04201 |          -0.1259  |                     15.36    |                0.1508  |       0.1673   |
| development | calibrated screen, balanced within donor_and_elevation |            3.246 |                   0.3122  |          -0.1174  |                      0.02309 |                0.1452  |       0.1333   |
| reserved    | length rule (incumbent)                                |            8.806 |                   6.271   |          -0.1009  |                      4.453   |                0.07473 |       0.07676  |
| reserved    | peak-overlap rule                                      |            3.75  |                   1.215   |           0.1588  |                      2.416   |                0.1041  |       0.1649   |
| reserved    | calibrated screen, global threshold                    |            2.535 |                   0       |          -0.2729  |                      4.27    |                0.1491  |       0.004646 |
| reserved    | calibrated screen, balanced within donor_regime        |            2.522 |                  -0.0132  |          -0.2729  |                      0.06136 |                0.1478  |       0.01169  |
| reserved    | calibrated screen, balanced within elevation_tertile   |            2.852 |                   0.3169  |           0.07609 |                      4.627   |                0.1477  |      -0.04586  |
| reserved    | calibrated screen, balanced within donor_and_elevation |            2.839 |                   0.3037  |           0.0663  |                      0.0744  |                0.1437  |      -0.0403   |

## Retention by elevation tertile

| split       | rule                                                 |   retention_low |   retention_middle |   retention_high |   retention_unmatched |   high_minus_low_points |
|:------------|:-----------------------------------------------------|----------------:|-------------------:|-----------------:|----------------------:|------------------------:|
| development | length rule (incumbent)                              |          0.7479 |             0.7381 |           0.751  |                0.6868 |                0.3132   |
| development | calibrated screen, global threshold                  |          0.7334 |             0.6593 |           0.6933 |                0.7014 |               -4.009    |
| development | calibrated screen, balanced within elevation_tertile |          0.7001 |             0.7001 |           0.7001 |                0.7    |                0.007291 |
| reserved    | length rule (incumbent)                              |          0.6984 |             0.7064 |           0.6811 |                0.7027 |               -1.735    |
| reserved    | calibrated screen, global threshold                  |          0.7771 |             0.7071 |           0.6689 |                0.6888 |              -10.81     |
| reserved    | calibrated screen, balanced within elevation_tertile |          0.6999 |             0.6999 |           0.7    |                0.7001 |                0.01443  |

## The price of balancing

Balancing the screen within donor regime and elevation tertile costs +0.31 points of consequential-error rate on development cases and removes the donor-regime spread of 15.4 points.
