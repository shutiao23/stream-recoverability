# Step 22 — endpoint, threshold and reference-series robustness

## Which axis wins, with clustered intervals on the contrast

Positive means timing beats outage length. The seven-day peak is the
regulatory-style window; the mechanism predicts the timing effect is
stronger there than at thirty days, because a shorter extreme is more
localised in time.

     metric  tolerance_c     n  base_rate  auc_timing_minus_length  ci_low  ci_high  timing_wins  length_wins
   hottest7       0.5443 40704     0.1664                   0.0723  0.0632   0.0960         True        False
  hottest30       0.5090 40704     0.1458                   0.0702  0.0607   0.0977         True        False
amplitude30       0.6422 40704     0.1314                   0.0244  0.0145   0.0370         True        False
annual_mean       0.2568 40704     0.0993                  -0.0270 -0.0362  -0.0179        False         True
  coldest30       0.3763 40704     0.0518                  -0.1844 -0.2275  -0.1563        False         True

## Reference series perturbed by 0.15 °C of instrument error

```json
{
  "development": {
    "sensor_noise_c": 0.15,
    "mean_abs_error_clean_c": 0.24157744533035794,
    "mean_abs_error_noisy_c": 0.24176944931490021,
    "length_rule_at_70_clean": 0.09254904713438389,
    "length_rule_at_70_noisy": 0.0931456849050644,
    "certificate_at_70_clean": 0.02934053978170077,
    "certificate_at_70_noisy": 0.031095356754290527,
    "contrast_clean_points": 6.320850735268311,
    "contrast_noisy_points": 6.205032815077388
  },
  "reserved": {
    "sensor_noise_c": 0.15,
    "mean_abs_error_clean_c": 0.21873752327323404,
    "mean_abs_error_noisy_c": 0.21866706312368175,
    "length_rule_at_70_clean": 0.09598626881436494,
    "length_rule_at_70_noisy": 0.09466596250330077,
    "certificate_at_70_clean": 0.025349881172432004,
    "certificate_at_70_noisy": 0.02799049379456034,
    "contrast_clean_points": 7.063638764193294,
    "contrast_noisy_points": 6.667546870874043
  }
}
```

## Exceedance misclassification across ecological thresholds, reserved panel

treatment    certificate_screened  length_screened  observed_days  reconstruct_all
threshold_c                                                                       
14.0                       0.0037           0.0084         0.0714           0.0117
16.0                       0.0018           0.0096         0.0741           0.0118
17.0                       0.0033           0.0138         0.0749           0.0181
18.0                       0.0026           0.0119         0.0757           0.0157
19.0                       0.0036           0.0138         0.0753           0.0186
20.0                       0.0036           0.0153         0.0686           0.0197
21.0                       0.0031           0.0120         0.0554           0.0177
22.0                       0.0034           0.0100         0.0499           0.0137
24.0                       0.0031           0.0100         0.0330           0.0143
