# E2 — deployment on the incomplete archive

7,536 real station-years: 5,114 fully observed and 2,422 incomplete, of which 2,422 carry a climatological peak window and can be decided.

## E2a — do the rules disagree?

| incumbent                                     |   n_station_years |   length_admits_pct |   timing_admits_pct |   agree_admit |   agree_reject |   admitted_by_length_rejected_by_timing |   rejected_by_length_admitted_by_timing |   disagreement_pct |
|:----------------------------------------------|------------------:|--------------------:|--------------------:|--------------:|---------------:|----------------------------------------:|----------------------------------------:|-------------------:|
| Johnson unfilled, longest run <= 49 d         |              2422 |               83.24 |               81.21 |          1809 |            248 |                                     207 |                                     158 |              15.07 |
| Johnson with imputation, longest run <= 140 d |              2422 |               91.7  |               81.21 |          1954 |            188 |                                     267 |                                      13 |              11.56 |

|   retention |   disagreement_pct |   admitted_by_length_rejected_by_timing |   rejected_by_length_admitted_by_timing |   mean_peak_overlap_length_admitted |   mean_peak_overlap_timing_admitted |
|------------:|-------------------:|----------------------------------------:|----------------------------------------:|------------------------------------:|------------------------------------:|
|        0.5  |             39.8   |                                     482 |                                     482 |                             0.01222 |                            0        |
|        0.6  |             37.57  |                                     455 |                                     455 |                             0.01936 |                            0        |
|        0.7  |             29.89  |                                     362 |                                     362 |                             0.02592 |                            0        |
|        0.8  |             18.33  |                                     222 |                                     222 |                             0.03894 |                            0.005538 |
|        0.9  |              4.707 |                                      57 |                                      57 |                             0.05104 |                            0.0322   |
|        0.95 |              3.551 |                                      43 |                                      43 |                             0.07813 |                            0.07813  |

| provider   |   n_incomplete_station_years |   disagreement_pct |   admitted_by_length_rejected_by_timing |   rejected_by_length_admitted_by_timing |
|:-----------|-----------------------------:|-------------------:|----------------------------------------:|----------------------------------------:|
| usgs       |                         1361 |              15.8  |                                     111 |                                     104 |
| lubw       |                          538 |              15.06 |                                      63 |                                      18 |
| gkd_bayern |                          289 |              11.07 |                                      21 |                                      11 |
| nve_hydapi |                          105 |              12.38 |                                       4 |                                       9 |
| chmi       |                           65 |              13.85 |                                       2 |                                       7 |
| syke       |                           35 |              25.71 |                                       3 |                                       6 |
| arso       |                           20 |              20    |                                       1 |                                       3 |

## E2b — transported risk (extrapolation)

The risk model is fitted on development cases and its calibration checked on the reserved panel first: the largest decile miscalibration is 6.19 points.

|   decile |    n |   predicted |   actual |   difference_points |
|---------:|-----:|------------:|---------:|--------------------:|
|        0 | 1082 |   0.0001268 | 0        |             0.01268 |
|        1 | 1082 |   0.0003926 | 0        |             0.03926 |
|        2 | 1082 |   0.001331  | 0        |             0.1331  |
|        3 | 1082 |   0.005737  | 0.004621 |             0.1116  |
|        4 | 1082 |   0.01623   | 0.01294  |             0.3294  |
|        5 | 1082 |   0.04702   | 0.06285  |            -1.583   |
|        6 | 1082 |   0.1114    | 0.1488   |            -3.741   |
|        7 | 1082 |   0.222     | 0.2662   |            -4.415   |
|        8 | 1083 |   0.393     | 0.4127   |            -1.972   |
|        9 | 1081 |   0.6151    | 0.5532   |             6.186   |

| rule                                                                      |   retention_pct |   predicted_consequential_rate_pct |   predicted_rate_among_excluded_pct |
|:--------------------------------------------------------------------------|----------------:|-----------------------------------:|------------------------------------:|
| admit everything                                                          |          100    |                             4.215  |                              nan    |
| Johnson unfilled (<= 49 d)                                                |           83.24 |                             0.9774 |                               20.29 |
| Johnson with imputation (<= 140 d)                                        |           91.7  |                             1.849  |                               30.37 |
| peak window <= 10% hidden                                                 |           81.21 |                             0.2566 |                               21.33 |
| risk-ranked screen at the retention of Johnson unfilled (<= 49 d)         |           83.24 |                             0.1349 |                               24.48 |
| risk-ranked screen at the retention of Johnson with imputation (<= 140 d) |           91.7  |                             0.8895 |                               40.97 |
| risk-ranked screen at the retention of peak window <= 10% hidden          |           81.21 |                             0.1031 |                               21.99 |

## E2c — what changes in the archive

| rule                                          |   incomplete_years_admitted |   archive_station_years |   mean_annual_peak_c |   shift_vs_complete_only_c |   share_above_20c_pct |   share_shift_points |   admitted_with_any_peak_day_hidden |   admitted_with_half_the_peak_window_hidden |   admitted_with_peak_window_wholly_hidden |   mean_peak_overlap_admitted |
|:----------------------------------------------|----------------------------:|------------------------:|---------------------:|---------------------------:|----------------------:|---------------------:|------------------------------------:|--------------------------------------------:|------------------------------------------:|-----------------------------:|
| observed days, no screening (current default) |                        2294 |                    7408 |                19.71 |                     0.4545 |                 50.74 |                4.243 |                                 568 |                                         133 |                                        58 |                     0.07531  |
| repair everything, no screening               |                        2422 |                    7536 |                19.78 |                     0.5201 |                 51.05 |                4.548 |                                 696 |                                         261 |                                       186 |                     0.1242   |
| Johnson unfilled (<= 49 d)                    |                        2016 |                    7130 |                19.76 |                     0.5067 |                 51.14 |                4.636 |                                 437 |                                          45 |                                         2 |                     0.04066  |
| Johnson with imputation (<= 140 d)            |                        2221 |                    7335 |                19.78 |                     0.5279 |                 51.26 |                4.761 |                                 507 |                                          82 |                                        17 |                     0.05459  |
| peak window <= 10% hidden                     |                        1967 |                    7081 |                19.71 |                     0.4519 |                 50.67 |                4.171 |                                 241 |                                           0 |                                         0 |                     0.006931 |
