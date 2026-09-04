# P3: Second-panel training-vs-evaluation thermal drift covariates

Supports PLAN.md §6.1: stratifying the 57 scored second-panel networks into
stable / moderate / drift so differential-curve advantage can be tested within
each layer. One row per network, produced by
`scripts/141_run_p3_network_drift.py`; companion CSV:
`network_drift_covariates.csv`.

## Data sources

* Scored network / station ground truth:
  `results/development_v11/second_confirmation/scoring/placement_losses.csv`
  (57 networks: 15 `chmi_*` czechia, 10 `nve_basin_*` norway, 32 `usgs2_*`
  united_states; donors from its `donor_station_ids` column).
* Daily wide temperature panels (`date` + one column per station):
  `results/development_v11/second_confirmation/daily_qc/networks/{id}/daily_wide_temperature.csv`,
  falling back to
  `results/development_v11/confirmation_daily_qc/networks/{id}/daily_wide_temperature.csv`
  (the 15 chmi panels), read with
  `development_recovery.read_temperature_panel` (missing calendar days are
  inserted as NaN).
* Route-A convention reference:
  `results/development_v11/route_a_confirmation/thermal_state_changes.csv`,
  written by `scripts/118_stratify_route_a_confirmation.py`
  (`route_a_confirmation.thermal_state_changes`).

## Split convention

Identical to route A: `development_recovery.year_split` over the panel index —
sorted unique calendar years, first 70% (rounded, `round(n*0.7)`) = training,
remainder = evaluation. Verified to reproduce the archived per-placement
`training_years`/`evaluation_years` of `placement_losses.csv` on all 57
networks (0 mismatches).

## Per-station covariate definitions (route-A columns)

For each scored station, `train`/`eval` = the station's daily values (NaN
dropped, route A style) inside training / evaluation years. If either period is
empty the station is skipped.

* `training_thermal_range` / `evaluation_thermal_range` =
  p95 − p5 (numpy quantiles 0.95/0.05) of the period values.
* `thermal_range_relative_change` = `evaluation_thermal_range /
  training_thermal_range − 1`.
* `training_acf30` / `evaluation_acf30` = pandas `Series.autocorr(30)` of the
  period values (NaN if < 31 values or zero variance). Identical to route A's
  `_lag_correlation(..., 30.0)` (integer lag, NaN-free series) — verified
  bit-for-bit (≤1e-12) against `route_a_confirmation.thermal_state_changes`
  on 31 stations across 9 networks.
* `acf30_change` = `evaluation_acf30 − training_acf30`.
* `thermal_state_shift` (route A flag) = `|range_change| ≥ 0.25` OR
  `|acf30_change| ≥ 0.20`; NaN comparisons evaluate False (route A behavior).

## New per-station drift covariates (PLAN §6.1)

* `annual_mean_diff` = `mean(eval values) − mean(train values)` (°C).
* `variance_ratio` = `log2(var_eval / var_train)` with sample variance
  (`ddof=1`); NaN when either variance ≤ 0 or < 2 values.
* `donor_corr_train` / `donor_corr_eval` = Pearson correlation between the
  station series and its mean donor series, computed on pairwise-finite
  aligned days within each period. Donor set = union of `donor_station_ids`
  (split on `|`) across the station's placement rows, restricted to panel
  columns, station itself excluded; mean donor series = row-wise mean over
  those columns (all-NaN day → NaN). Correlation requires ≥ 30 aligned finite
  pairs, else NaN. No donors available → NaN for both.

## Network-level aggregation (`network_drift_covariates.csv`)

All `mean_*` columns = arithmetic mean of the per-station values over the
network's measured scored stations (`n_stations`, 3–8 here). NaN entries are
excluded from the mean (`nanmean`); a column is NaN only if every station is
NaN.

* `donor_corr_change` = `mean_donor_corr_eval − mean_donor_corr_train`
  (negative = donor-correlation decay toward evaluation).
* `n_shift_stations` = count of route-A `thermal_state_shift = True` stations;
  `fraction_shift_stations` = `n_shift_stations / n_stations`.

## Stratum rule (implemented as the `stratum` column)

Three dimensionless drift-magnitude signals per network (PLAN §6.1 triplet):

```
s_annual   = |mean_annual_mean_diff| / max(mean_training_thermal_range, 1e-6)
s_variance = |mean_variance_ratio|
s_donor    = max(0, mean_donor_corr_train − mean_donor_corr_eval)   # decay
```

Each signal is standardized across the 57 networks, `z = (s − mean)/sd`
(sd < 1e-9 → z = 0); missing signals (NaN) are dropped. `composite` = mean of
the available z values (≥ 1). Rank tertiles with stable tie-breaking map the
lowest third to `stable`, middle to `moderate`, top to `drift` (19 / 19 / 19
networks; ties are broken by rank so counts are exact). A network with no
signal at all would receive `unknown` (does not occur here; donor coverage is
complete).

## Counts

* 57 networks: czechia 15, norway 10, united_states 32.
* Stratum: stable 19, moderate 19, drift 19.
* Domain × stratum:
  czechia {stable 3, moderate 4, drift 8}; norway {stable 5, moderate 4,
  drift 1}; united_states {stable 11, moderate 11, drift 10}.

No per-network missing covariate values; all 57 rows complete.
