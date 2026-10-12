# E1 — the seasonality of real outages

6,472 real interior gaps across 364 stations. 
Median gap 2 d, 95th percentile 43 d.

## Start month by length class

| length_class    |   n_gaps |   share_protected_sep_to_jan |   share_exposed_mar_to_jul |   chi2_uniformity |   p_uniformity |
|:----------------|---------:|-----------------------------:|---------------------------:|------------------:|---------------:|
| 1-7 d           |     5246 |                       0.4053 |                     0.4333 |            58.76  |      1.572e-08 |
| 8-29 d          |      760 |                       0.3803 |                     0.4474 |            48.07  |      1.385e-06 |
| 30-89 d         |      282 |                       0.4504 |                     0.3901 |             4.043 |      0.9687    |
| 90 d and longer |      184 |                       0.7228 |                     0.1793 |            86.13  |      9.515e-14 |

## Long gaps by provider

| provider   |   n_long_gaps |   share_protected_sep_to_jan |   share_exposed_mar_to_jul |   median_length_days |
|:-----------|--------------:|-----------------------------:|---------------------------:|---------------------:|
| syke       |            18 |                       0.7778 |                     0.2222 |                 61   |
| chmi       |            30 |                       0.7333 |                     0.1333 |                333.5 |
| usgs       |           252 |                       0.5833 |                     0.2738 |                 63.5 |
| lubw       |            75 |                       0.4933 |                     0.3333 |                 60   |
| gkd_bayern |            33 |                       0.4848 |                     0.3636 |                 52   |
| nve_hydapi |            28 |                       0.4643 |                     0.5    |                 96   |
| arso       |            14 |                       0.4286 |                     0.5    |                 41.5 |
| foen       |            16 |                       0.3125 |                     0.5    |                 53.5 |

## What the calendar is worth

The real outage-length distribution is held fixed and only the placement changes; the consequential-error rate of each placement is read off the designed arm's length-by-overlap surface.

| calendar          |   n_placements |   mean_peak_overlap |   share_hitting_peak_window |   share_hiding_half_the_window |   consequential_rate |   points_vs_observed |
|:------------------|---------------:|--------------------:|----------------------------:|-------------------------------:|---------------------:|---------------------:|
| observed          |          32240 |             0.1644  |                     0.2349  |                        0.1591  |              0.08749 |               0      |
| uniform           |          32240 |             0.1748  |                     0.2488  |                        0.1686  |              0.09084 |               0.3349 |
| spring_mar_to_jul |          32240 |             0.3014  |                     0.4065  |                        0.2951  |              0.1318  |               4.434  |
| autumn_sep_to_jan |          32240 |             0.04595 |                     0.07258 |                        0.04324 |              0.04869 |              -3.88   |
