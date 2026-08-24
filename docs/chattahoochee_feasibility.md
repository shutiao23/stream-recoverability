# Chattahoochee feasibility, frozen prediction, and evaluate-once result

The five-site panel passed the pre-performance feasibility gate for all 60
scenarios. The date axis is 2012--2025; fitting, validation, and confirmatory
periods are 2012--2020, 2021--2022, and 2023--2025.

Before confirmatory performance was opened, the train-only covariance budget
classified site 02334430 as memory-dominated and sites 02335000, 02335450,
02336000, and 02337170 as donor-dominated. The full predicted curves were
written to `results/predictions/chattahoochee_recoverability_prediction_v1.json`.

The evaluate-once run subsequently created the persistent once-lock and
completed all 540 expected model--scenario units. For full-information
temperature blocks, the observed best envelope was:

| Site | Type | 30-day skill | 90-day skill | 180-day skill | Best 180-day model |
| --- | --- | ---: | ---: | ---: | --- |
| 02334430 | memory | 0.536 | 0.156 | 0.141 | Kalman |
| 02335000 | donor | 0.470 | 0.626 | 0.726 | XGBoost |
| 02335450 | donor | 0.513 | 0.626 | 0.555 | XGBoost |
| 02336000 | donor | 0.447 | 0.889 | 0.746 | XGBoost |
| 02337170 | donor | 0.840 | 0.801 | 0.729 | random forest |

Site 02334430 is 366 m below Buford Dam. It has the largest 30-to-180-day
decline and the lowest 180-day skill. The four donor sites all retain higher
long-gap recovery. This confirms the frozen qualitative type ordering, but
absolute predicted skill is not calibrated across all external cells.

No site, model, or mask was changed after outcomes were opened, and no numeric
effect threshold is retroactively described as preregistered. Compact tables
are in `results/revision/external_confirmation_*.csv`; the immutable completion
manifest and once-lock are the authoritative evidence.
