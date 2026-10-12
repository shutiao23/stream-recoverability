# F17 - the regulatory illustration uses daily means, but the criterion is 7-DADMax

Artifacts: `dadmax_comparison.csv`, `threshold_class_change.csv`, `summary.json`, `daily_max_availability.csv`, `raw_cache/` (hashes in `raw_cache_manifest.csv`). Script: `scripts/251_wrr_winter_regulatory_endpoints.py dadmax`.

## The definition used

WAC 173-201A-020 (definition of 7-DADMax) and WAC 173-201A-200(1)(c) Table 200(1)(c) (aquatic life temperature criteria, column 'Highest 7-DADMax'):

> '7-DADMax' or '7-day average of the daily maximum temperatures' is the arithmetic average of seven consecutive measures of daily maximum temperatures. The 7-DADMax for any individual day is calculated by averaging that day's daily maximum temperature with the daily maximum temperatures of the three days prior and the three days after that date.

The criteria table's column header is **Highest 7-DADMax**, so the annual statistic is the maximum over the year of the rolling seven-day average of daily maxima. This report computes exactly that from USGS daily values with `parameterCd=00010`, `statCd=00001` (Maximum), and compares it, station-year by station-year, with the manuscript's statistic: the maximum of the rolling seven-day average of `statCd=00003` (daily Mean). Both series pass through the repository's own confirmation QC (`ingest_qc.qc_long_frame` / `clean_long_frame`), so the comparison is not contaminated by different treatment of provisional or out-of-range values.

## Availability of daily maxima at the 91 confirmation stations

* stations requested: 91; with a daily-maximum time series in the NWIS series catalog: **90**; with a daily-mean series: 91.
* stations with a daily mean but no daily maximum: ['09383100']; with a daily maximum but no daily mean: none.
* after QC, 90 stations contribute a daily-maximum series and 91 a daily-mean series.
* raw responses and hashes: 182 files, 49,094,897 bytes, in `raw_cache/`.
* Provenance check on the download: the freshly downloaded daily-mean series (`statCd=00003`) were compared day-by-day with the sealed confirmation panel's own input files. Across 706,665 common station-days at 91 stations the maximum absolute difference is 0.0 C and 100.0% of the values are exactly equal, so the daily-maximum series fetched from the same service in the same way is the same vintage and treatment as the panel.

## The comparison

Station-years with at least 330 valid days in **both** series: **n = 1,591** station-years at 89 stations, 1975-2025. A further 786 station-years have both series complete day-for-day and tell the same story (median difference +1.686 C against +1.571 C on the coverage-filtered set). 852 of the analysed station-years are also in the sealed USGS confirmation panel; the sealed panel itself was not re-scored.

Distribution of `7-DADMax - hottest-7 daily mean` over the same station-years:

| statistic | value (C) |
| --- | --- |
| mean | +1.939 |
| standard deviation | +1.369 |
| median | +1.571 |
| 5th percentile | +0.486 |
| 25th percentile | +1.014 |
| 75th percentile | +2.443 |
| 95th percentile | +4.429 |
| minimum | +0.000 |
| maximum | +12.729 |
| share where 7-DADMax > hottest-7 mean | 99.9% |
| share exactly equal | 0.1% |
| share where 7-DADMax < hottest-7 mean | 0.00% |

The direction of the mismatch is uniform: 7-DADMax is greater than or equal to the hottest-7 daily mean in every one of the 1,591 station-years (99.9% strictly greater, 0.06% tied, 0.00% below). That is what daily max >= daily mean implies for annual extremes taken over the same window, and it means the daily-mean surrogate never manufactures a false exceedance - it only misses real ones.

The size of the mismatch, however, is essentially a constant offset rather than a level-dependent term: regressing the difference on the daily-mean level gives a slope of -0.002 C per C with Pearson r = -0.009, against a mean difference of +1.94 C and a standard deviation of 1.37 C. That distinction matters for how the finding is closed out, so it is spelled out rather than asserted:

* Because the offset is near-constant, a *rate-matching* defence exists: **lowering** the daily-mean threshold would approximately reproduce the count of exceedances, since the surrogate is biased low. The table above reports the daily-mean threshold that matches the 7-DADMax exceedance count at each grid value (`equal_count_threshold_c`): 14.63 C for the 16 C criterion, 16.21 C for 18 C and 18.27 C for 20 C, i.e. shifts of -1.73 C and -1.37 C at the two ends of the grid.
* It does not rescue the illustration. A criterion is a fixed legal number, not a free parameter; the station-year calls still disagree in 10.43% of cases at 20 C because the offset has a standard deviation of 1.37 C; and every number the manuscript reports from this illustration - misclassification rate, retention trade-off, bias in the count of warm years (reported as -0.76 years per station under recorded days) - was computed on the surrogate, so it inherits the mismatch rather than being cancelled by a threshold move.

The seven-day peak also moves: the two statistics select the same peak day in 47.9% of station-years and within a week in 85.0% (median absolute shift 0 days).

## Would the threshold decision change?

The 16/18/20 C grid is the manuscript's own (`step22_robustness/threshold_sweep.csv`). "mean only" means the daily-mean statistic calls an exceedance that the 7-DADMax does not; "7-DADMax only" is the reverse.

| threshold (C) | n | exceed: 7-DADMax | exceed: hottest-7 mean | class changes | missed exceedances | false exceedances | true exceedances missed | Cohen's kappa | count-matching daily-mean threshold (C) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 1,591 | 1,338 | 1,250 | **88** (5.53%) | **88** | 0 | 6.58% | 0.819 | 14.63 |
| 18 | 1,591 | 1,237 | 1,169 | **68** (4.27%) | **68** | 0 | 5.50% | 0.884 | 16.21 |
| 20 | 1,591 | 1,159 | 993 | **166** (10.43%) | **166** | 0 | 14.32% | 0.765 | 18.27 |

The same over the whole swept grid:

| threshold (C) | exceed: 7-DADMax | exceed: hottest-7 mean | class-change rate | mean only | 7-DADMax only |
| --- | --- | --- | --- | --- | --- |
| 14 | 1,450 | 1,374 | 4.78% | 0 | 76 |
| 16 | 1,338 | 1,250 | 5.53% | 0 | 88 |
| 17 | 1,277 | 1,208 | 4.34% | 0 | 69 |
| 18 | 1,237 | 1,169 | 4.27% | 0 | 68 |
| 19 | 1,204 | 1,105 | 6.22% | 0 | 99 |
| 20 | 1,159 | 993 | 10.43% | 0 | 166 |
| 21 | 1,113 | 906 | 13.01% | 0 | 207 |
| 22 | 1,033 | 840 | 12.13% | 0 | 193 |
| 24 | 862 | 616 | 15.46% | 0 | 246 |

Recorded rather than assumed: across all 2,204 paired station-years (including the low-coverage ones excluded from the analysis), 7-DADMax falls below the hottest-7 daily mean in 4 cases; within the 1,591 analysed station-years the count is 0. Where it happens it is traceable to the annual maximisation selecting different peak windows, or to QC dropping different days from the two series, never to a daily violation of max >= mean.

## Verdict

**No - the current hottest-7 daily-mean illustration cannot stand as a regulatory-aligned example.** It substitutes a different input statistic, biased low by +1.57 C at the median (+1.94 C on average, 5th-95th percentile +0.49 to +4.43 C), and on the manuscript's own 16/18/20 C grid it changes the exceedance classification in 88 / 68 / 166 station-years (5.53% / 4.27% / 10.43%), always by missing a real exceedance rather than by inventing one. The bias is close to a constant offset (slope -0.002 C per C, r = -0.009), so a threshold shift could match the *counts* - the table gives the matching threshold at each grid value - but it cannot match the *decisions* (the offset has an sd of 1.37 C), and a criterion is not a free parameter. The illustration must be recomputed on the 7-DADMax or relabelled.

**Corrected statement.** Replace the illustration with one of two claims:

1. *Preferred, and now computable.* Where an archive is screening a WAC-style criterion, the endpoint must be the highest 7-DADMax built from daily maxima, and the screening results reported for the hottest-7 daily mean should be recomputed on that endpoint. This amendment supplies the daily-maximum input and the station-year join for the 91 confirmation stations (`dadmax_comparison.csv`), so the recomputation is a re-run of the existing screen against a different target column, not a new data campaign.
2. *If the illustration is kept.* Relabel it as a daily-mean illustration of a seven-day endpoint, stating explicitly that the WAC 7-DADMax criterion is built from daily maxima, that the daily-mean surrogate is biased low by a median of +1.57 C (5th-95th percentile +0.49 to +4.43 C), that at 20 C it misses 166 of 1,159 exceedances (14.3%) while creating none, and that the manuscript's misclassification numbers are therefore not compliance numbers for WAC 173-201A-200.

Nothing here contradicts the mechanism claim: the screen's advantage over gap length is a property of the estimator and the gap geometry, not of the units. The finding is narrower and harder to argue with - the endpoint must match the regulation before the numbers may be called regulatory.

