# E7 — is missingness informative?

6,472 real interior gaps.

## Flanking days, against the station's own day-of-year climatology

| length_class    |   n_gaps |   pre_anomaly_c |   pre_p_value |   post_anomaly_c |   post_p_value |   station_anomaly_sd_c |
|:----------------|---------:|----------------:|--------------:|-----------------:|---------------:|-----------------------:|
| 1-7 d           |     5246 |        0.01768  |       0.4422  |          0.02338 |         0.3075 |                  1.824 |
| 8-29 d          |      760 |        0.03784  |       0.5638  |          0.06772 |         0.3168 |                  1.843 |
| 30-89 d         |      282 |       -0.002432 |       0.9825  |          0.05741 |         0.5672 |                  1.807 |
| 90 d and longer |      184 |       -0.2154   |       0.08132 |          0.1282  |         0.3132 |                  1.626 |

## Donors recording through the gap, against their anomaly the rest of the record

| length_class    |   n_gaps |   donor_anomaly_difference_c |   p_value |   ci_low_c |   ci_high_c |
|:----------------|---------:|-----------------------------:|----------:|-----------:|------------:|
| 1-7 d           |     4374 |                      0.0632  |   0.01698 |     -3.609 |       3.515 |
| 8-29 d          |      666 |                     -0.06065 |   0.264   |     -3.116 |       2.662 |
| 30-89 d         |      235 |                     -0.03569 |   0.6525  |     -2.273 |       2.746 |
| 90 d and longer |      145 |                      0.1123  |   0.06611 |     -1.433 |       1.664 |

## Paired test on outage onset

{
  "n_gaps": 5420,
  "median_difference_c": 0.03824967675449651,
  "mean_difference_c": 0.04501057331978435,
  "wilcoxon_p": 0.015023867089399227
}

**Verdict.** missingness is weakly informative and the effect is detectable at this sample size -- donors run 0.063 C warm through gaps of a week or less (p = 0.017) -- but every effect is under half a tenth of the 0.5 C tolerance and under a seventh of the within-station anomaly scale. The transplant design is defensible on magnitude, not on a null result. The one class worth a limitation is outages of 90 days and longer, whose flanking days run 0.215 C cold (p = 0.081)
