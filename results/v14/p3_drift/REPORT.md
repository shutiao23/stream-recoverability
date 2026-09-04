# v14 P3: drift-stratum comparison - report

Reproduced by scripts/144_run_p3_strata_comparison.py (2000 draws, seed 20260903).  Strata from network_drift_covariates.csv (19/19/19).

## Directional hypothesis (PLAN 6.1): diff advantage over r6-diff is
larger in the drift stratum than in the stable stratum

- T1 (mean over durations of per-duration placement-level contrast): +0.009
- T2 (pooled placement level): +0.005 [-0.007, +0.017], P(>0) = 0.79
- T3 (pooled network level): -0.016 [-0.184, +0.101], P(>0) = 0.45

Verdict: the hypothesis is NOT CLEARLY SUPPORTED on this panel; the
honest published conclusion is the stationarity boundary (see
stratum_comparison.csv and direction_test.json for all numbers).

