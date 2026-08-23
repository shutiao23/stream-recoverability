# Chattahoochee feasibility and train-only prediction

The frozen five-site panel was acquired for coverage inspection. No model was
trained, no performance metric was computed, and no once-lock was created.

- Feasibility status: passed
- Frozen scenarios constructible: 60/60
- Date axis: 2012-01-01 through 2025-12-31 (5,114 days)
- Training-period temperature coverage: 0.915--0.995
- Validation-period temperature coverage: 0.995--1.000
- Confirmatory-period temperature coverage: 0.958--0.999

The analytic prediction read only `splits/train.parquet` (2012--2020). Site
`02334430` was memory-dominated at 30 days; sites `02335000`, `02335450`,
`02336000`, and `02337170` were donor-dominated. Predicted skill at 30 days was
0.644--0.763. At 365 days the four donor-dominated sites retained predicted
skill 0.630--0.733, whereas `02334430` declined to 0.314.

These values are predictions from training covariance, not measured recovery
performance. The 2023--2025 outcomes remain unused for scoring.
