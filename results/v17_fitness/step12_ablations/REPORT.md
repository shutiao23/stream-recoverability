# Step 12 — adversarial ablations of the certificate

Development cases, out-of-fold, at 70% retention. Lower is better; the incumbent is the first row.

                                variant                    kind  rate_above_0.5_at_70  mean_abs_error_at_70  points_vs_incumbent
         outage-length rule (incumbent)                baseline                0.0924                0.1536               0.0000
         three-variable logistic screen                baseline                0.0553                0.0988              -3.7132
                      peak-overlap rule                baseline                0.0562                0.1007              -3.6219
                                   full             certificate                0.0293                0.0658              -6.3068
                     full (screen only) certificate_screen_only                0.0311                0.0680              -6.1278
              drop_observed_peak_margin             certificate                0.0313                0.0682              -6.1103
drop_observed_peak_margin (screen only) certificate_screen_only                0.0339                0.0737              -5.8471
                    drop_donor_features             certificate                0.0378                0.0732              -5.4645
      drop_donor_features (screen only) certificate_screen_only                0.0387                0.0743              -5.3697
               geometry_and_timing_only             certificate                0.0486                0.0916              -4.3765
 geometry_and_timing_only (screen only) certificate_screen_only                0.0493                0.0928              -4.3063
                         three_features             certificate                0.0489                0.0922              -4.3484
           three_features (screen only) certificate_screen_only                0.0498                0.0933              -4.2642

## Contrast against the outage-length rule, network-clustered

```json
{
  "full": {
    "point": -0.06345418172884568,
    "low": -0.07124099253119637,
    "high": -0.05561923903542943,
    "se": 0.00412049861255886,
    "n_clusters": 110,
    "retention": 0.7,
    "tolerance_c": 0.5
  },
  "drop_observed_peak_margin": {
    "point": -0.06148878671954515,
    "low": -0.06883852836872778,
    "high": -0.054226342681382586,
    "se": 0.0037069027666352646,
    "n_clusters": 110,
    "retention": 0.7,
    "tolerance_c": 0.5
  },
  "drop_donor_features": {
    "point": -0.055031060260414835,
    "low": -0.06270688839942311,
    "high": -0.047824317122875146,
    "se": 0.003808974920148554,
    "n_clusters": 110,
    "retention": 0.7,
    "tolerance_c": 0.5
  },
  "geometry_and_timing_only": {
    "point": -0.04415119503035833,
    "low": -0.05195973966094257,
    "high": -0.03686356082980612,
    "se": 0.0038669390544391587,
    "n_clusters": 110,
    "retention": 0.7,
    "tolerance_c": 0.5
  },
  "three_features": {
    "point": -0.04387042431474397,
    "low": -0.05145526675999195,
    "high": -0.03548940181151721,
    "se": 0.003984706919342939,
    "n_clusters": 110,
    "retention": 0.7,
    "tolerance_c": 0.5
  }
}
```

## Conformal coverage within individual reserved networks

```json
{
  "n_networks": 36,
  "mean": 0.9035332414215907,
  "median": 0.9132716049382716,
  "q10": 0.8396892795491974,
  "min": 0.7777777777777778,
  "share_below_0.80": 0.027777777777777776,
  "share_below_0.85": 0.1388888888888889
}
```
