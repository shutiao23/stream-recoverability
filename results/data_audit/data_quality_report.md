# Data quality audit

## Scope

This audit covers the B1, S2, and P3 daily source files. Unit and variable rules were loaded from `metadata/data_dictionary.csv`.

## Date continuity

| station_id | start_date | end_date | unique_date_count | duplicate_date_count | missing_date_count | is_daily_continuous |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | 2006-01-01 00:00:00 | 2020-12-31 00:00:00 | 5479 | 0 | 0 | True |
| P3 | 2006-01-01 00:00:00 | 2020-12-31 00:00:00 | 5479 | 0 | 0 | True |
| S2 | 2006-01-01 00:00:00 | 2020-12-31 00:00:00 | 5479 | 0 | 0 | True |

## Confirmed missing codes

| station_id | raw_name | missing_code | code_type | count |
| --- | --- | --- | --- | --- |
| B1 | PRCP | 99.99 | confirmed_special_code | 16 |
| B1 | WDSP | 999.9 | confirmed_special_code | 11 |
| P3 | PRCP | 99.99 | confirmed_special_code | 17 |
| P3 | WDSP | 999.9 | confirmed_special_code | 16 |
| S2 | PRCP | 99.99 | confirmed_special_code | 5 |
| S2 | WDSP | 999.9 | confirmed_special_code | 5 |

Confirmed special codes are retained in `raw_value`, converted to NaN in `value`, and marked `natural_observed=false`, `quality_approved=false`, and `qc_status=source_missing`.

## Unit conversion

| raw_name | raw_unit | unit | unit_conversion |
| --- | --- | --- | --- |
| WDSP | knot | m/s | 0.514444 |
| PRCP | inch | mm/day | 25.4 |

## FLOW–WLEVEL diagnostic

| station_id | suspected_year_fraction |
| --- | --- |
| B1 | 0.933 |
| P3 | 1.0 |
| S2 | 1.0 |

The yearly diagnostics and standard hydrological compilation practice indicate a rating-curve-like dependence, but the supplied files contain no derivation flag. FLOW and WLEVEL are therefore treated as one hydraulic information group in independence analyses without claiming the exact production method for each value.

## Known B1 events retained

B1 WLEVEL changes from 2478.86 to 2487.34 on 2019-01-01 (a +8.48 m step), consistent with a datum/baseline change requiring downstream treatment rather than deletion. The B1 November 2018 high-flow event is also retained (monthly peak FLOW=5760 on 2018-11-14). Both remain `observed_unflagged` and `quality_approved=true`; neither is silently removed by this pipeline.

## Quality limitation

The source CSV files contain no per-value quality flags. Consequently, `quality_approved` only excludes literal source missing values and the confirmed WDSP=999.9 / PRCP=99.99 codes. It must not be interpreted as proof that every remaining value was individually approved by the provider.

`DH` is documented as daily sunshine duration in hours and is retained as a meteorological channel.

An external monthly record independently agrees with most B1 monthly means. S2 agrees through 2012 but has a 2013–2019 year-order discrepancy; the supplied daily series is retained unchanged and the mismatch is carried as a provenance limitation.
