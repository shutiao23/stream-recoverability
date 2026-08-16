# Information structure report

All thresholds and lag selection diagnostics use the training split only.
Step candidates are flagged for review and are not removed.
November 2018 is retained: 810 long-format rows, 808 quality-approved values.

## Train-only event thresholds

```text
station_id  train_count_T  train_count_F  T_q90_train  F_q90_train  F_q10_train
        B1           3652           3652         16.4       2280.0        256.0
        S2           3652           3652         18.1       2940.0        395.1
        P3           3652           3652         21.4       4030.0        511.0
```

## Strongest train-only cross-station lags

```text
source_station target_station variable selected_series  lag_days  selected_correlation
            B1             P3        F             raw         3              0.946796
            B1             P3        F         anomaly         3              0.801974
            B1             P3        L             raw         3              0.955619
            B1             P3        L         anomaly         3              0.770068
            B1             P3        T             raw         4              0.953867
            B1             P3        T         anomaly         3              0.312408
            B1             S2        F             raw         1              0.986672
            B1             S2        F         anomaly         1              0.951009
            B1             S2        L             raw         1              0.989979
            B1             S2        L         anomaly         1              0.948951
            B1             S2        T             raw         1              0.989993
            B1             S2        T         anomaly         1              0.709768
            S2             P3        F             raw         2              0.975978
            S2             P3        F         anomaly         1              0.893768
            S2             P3        L             raw         2              0.973372
            S2             P3        L         anomaly         1              0.849675
            S2             P3        T             raw         3              0.958427
            S2             P3        T         anomaly         2              0.322005
```

Positive lag means the source station leads the target station.
