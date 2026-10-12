# E5 — air forcing for every station

## Estimator support

| split       | forcing     |   air_available_pct |   supported_air_ridge_pct |   supported_donor_ridge_pct |
|:------------|:------------|--------------------:|--------------------------:|----------------------------:|
| development | v17 forcing |              2.263  |                    2.263  |                       78.09 |
| development | v18 forcing |             98.64   |                   98.4    |                       78.09 |
| reserved    | v17 forcing |              0.8503 |                    0.8503 |                       80.73 |
| reserved    | v18 forcing |            100      |                   99.77   |                       80.73 |

## How large is the problem, with and without the field's own method

| forcing     | donor_regime   |   n_cases |   observed_days_mae_c |   doy_climatology_mae_c |   air_ridge_mae_c |   policy_mae_c |   oracle_mae_c |   policy_rate_above_0.5_pct |
|:------------|:---------------|----------:|----------------------:|------------------------:|------------------:|---------------:|---------------:|----------------------------:|
| v17 forcing | all            |     40704 |                 1.305 |                  0.4015 |            0.2998 |         0.2416 |         0.1651 |                       14.87 |
| v17 forcing | none           |      2512 |                 1.335 |                  0.3761 |            0.8527 |         0.3404 |         0.2439 |                       23.85 |
| v17 forcing | sparse         |     12617 |                 1.396 |                  0.4115 |            0.3574 |         0.2378 |         0.1539 |                       15.8  |
| v17 forcing | rich           |     25575 |                 1.257 |                  0.399  |            0.2011 |         0.2338 |         0.163  |                       13.53 |
| v18 forcing | all            |     40704 |                 1.305 |                  0.4015 |            0.3245 |         0.2246 |         0.1304 |                       13.97 |
| v18 forcing | none           |      2512 |                 1.335 |                  0.3761 |            0.3566 |         0.3635 |         0.1953 |                       23.45 |
| v18 forcing | sparse         |     12617 |                 1.396 |                  0.4115 |            0.3592 |         0.2368 |         0.1332 |                       15.53 |
| v18 forcing | rich           |     25575 |                 1.257 |                  0.399  |            0.305  |         0.205  |         0.1227 |                       12.27 |

## Does the axis conclusion depend on the estimator library?

| forcing     |   base_rate |   auc_peak_overlap |   auc_warm_observed_fraction |   auc_longest_run |   auc_missing_fraction |   timing_minus_length |
|:------------|------------:|-------------------:|-----------------------------:|------------------:|-----------------------:|----------------------:|
| v17 forcing |      0.1487 |             0.819  |                       0.8194 |            0.7488 |                 0.7427 |               0.07023 |
| v18 forcing |      0.1397 |             0.8166 |                       0.8083 |            0.7358 |                 0.7302 |               0.08088 |

## Was the incumbent handicapped? Development cases at 70% retention

| screen             | reconstruction                                           |   rate_above_0.5_pct |   mean_abs_error_c |
|:-------------------|:---------------------------------------------------------|---------------------:|-------------------:|
| outage-length rule | information-conditioned policy                           |                8.999 |            0.1505  |
| outage-length rule | always air regression (Beaufort-style), else climatology |               15.16  |            0.2314  |
| outage-length rule | always donor ridge, else climatology                     |                9.571 |            0.1597  |
| outage-length rule | always smooth climatology                                |               19.79  |            0.288   |
| outage-length rule | oracle over methods (NOT deployable)                     |                3.622 |            0.07586 |
| calibrated screen  | deployable estimators it selects itself                  |                2.867 |            0.06496 |

Estimator chosen by the screen, % of cases: {"donor_ridge": 53.11517295597484, "air_ridge": 20.005404874213838, "linear_interp": 14.499803459119498, "doy_climatology": 7.9156839622641515, "smooth_climatology": 4.463934748427674}
