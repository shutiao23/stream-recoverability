# Step 5 — mechanism (H1)

## Outage length is a weak axis once peak-window overlap is conditioned on

length_bucket overlap_bucket    n  mean_abs_error  rate_above_tolerance
         1-30              0 9385          0.0178                0.0064
         1-30          0-0.5 5350          0.1274                0.0591
         1-30          0.5-1  831          0.3132                0.2190
         1-30              1 1382          0.2950                0.1823
        31-60              0 3189          0.0213                0.0113
        31-60          0-0.5 1291          0.2271                0.1325
        31-60          0.5-1 1095          0.4054                0.2548
        31-60              1 1514          0.4765                0.3223
       61-120              0 3620          0.0345                0.0157
       61-120          0-0.5 1577          0.2883                0.1756
       61-120          0.5-1 1441          0.4179                0.2762
       61-120              1 2883          0.6219                0.4017
      121-200              0 1619          0.1438                0.0871
      121-200          0-0.5 1027          0.3053                0.1908
      121-200          0.5-1  779          0.4663                0.3004
      121-200              1 1438          0.7692                0.4680
         201+          0-0.5   27          0.9438                0.5556
         201+          0.5-1   65          0.6867                0.4000
         201+              1 2191          0.7893                0.4989

## Single-variable discrimination of a consequential error (> 0.5 °C)

               feature    auc       direction     n
warm_observed_fraction 0.8194  lower is worse 40704
          peak_overlap 0.8190 higher is worse 40704
  observed_peak_margin 0.7678  lower is worse 40691
           longest_run 0.7488 higher is worse 40704
      missing_fraction 0.7427 higher is worse 40704
         total_missing 0.7420 higher is worse 40704
       train_metric_sd 0.5873 higher is worse 40704
        donor_corr_max 0.5840  lower is worse 38192
   donor_coverage_mean 0.5757  lower is worse 39517
                n_runs 0.5745  lower is worse 40704
        train_resid_sd 0.5724 higher is worse 40704
       donor_corr_mean 0.5574  lower is worse 38192
    seasonal_amplitude 0.5310 higher is worse 40704
      n_visible_donors 0.5210  lower is worse 40704

## Nested feature sets, grouped five-fold CV clustered by network

           feature_set  n_features  grouped_cv_auc
           length only           2          0.7420
              + timing           4          0.8453
+ observed-peak margin           5          0.8578
       + donor quality          14          0.8836

## Permutation importance on out-of-fold predictions

Out-of-fold R² = 0.3459 (n = 40,704, 110 networks)

               feature  permutation_r2_drop
  observed_peak_margin               0.3492
          peak_overlap               0.1941
warm_observed_fraction               0.0998
        donor_corr_max               0.0953
        train_resid_sd               0.0511
       train_metric_sd               0.0503
   donor_coverage_mean               0.0329
      n_visible_donors               0.0289
       donor_corr_mean               0.0195
    seasonal_amplitude               0.0129
                n_runs              -0.0000
      missing_fraction              -0.0013
         total_missing              -0.0020
           longest_run              -0.0043
