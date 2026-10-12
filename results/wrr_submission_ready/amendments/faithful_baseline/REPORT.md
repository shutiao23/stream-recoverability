# F15 - is the manuscript's "Beaufort-style" baseline the cited method?

Amendment to adversarial finding F15. Script: `scripts/252_wrr_faithful_baseline.py`.
Artifacts: `comparison.csv`, `contrasts.csv`, `summary.json`, `case_errors.parquet`,
`integrity_checks.json`, `method_spec.md` (all in this directory).

## Verdict

**The label is not defensible as written.** The row the manuscript calls an air regression "in the
manner of Beaufort et al. (2022)" is `abserr_air_ridge` from the v17 estimator library: a
`Ridge(alpha=1.0)` on seven individual air lags (0, 1, 2, 3, 5, 7, 14 d) plus two annual harmonics,
fitted over the whole year. The cited method is an ordinary least-squares regression on a *single*
right-aligned 2-10 d moving average of air temperature, the window chosen per station by highest
R2 and fitted on July-August only (`method_spec.md`, Sect. 1). The two objects share the input
(daily air temperature) and nothing else structural.

A faithful reimplementation now exists and was scored on the identical cases. It is **better** than
the library object the manuscript attributed to the cited paper: at 70% retention under the
outage-length rule the consequential-error rate is 12.76%
for the faithful method against 15.16%
for the library air ridge (paired difference
-2.404 pp,
95% CI -3.199 to
-1.620 pp;
network-clustered bootstrap, 1200 draws).

**The manuscript's qualitative claim survives the correction.** Even with the faithful method, a
single air-temperature regression applied uniformly to every record is worse than the study's
per-case selection: 12.76% against
9.00% for the
information-conditioned policy
(+3.759 pp,
95% CI +2.738 to
+4.760 pp),
and worse than the donor ridge at equal retention. What changes is the number attached to the name:
the cited method is 2.40 points better than the
object the manuscript put in its place.

**Labelling of the result in this amendment.** "Faithful reimplementation of the cited climate
correction, approximate as a drop-in case-level baseline": faithful in regression family (OLS), in
predictor (a right-aligned 2-10 d moving average of air temperature), in the window grid, in the
per-station R2 selection rule and in the summer fit; approximate only where the endpoint level, the
fit sample and the season of the fill had to be adapted to this study's case table. No input had to
be substituted - the cited climate correction needs only daily water and air temperature, both of
which the panel has.

**Recommendation.** Either (i) report the faithful reimplementation as the cited-method baseline
(12.76% at 70% retention) alongside or instead of the library number, or
(ii) rename the library row to "in-library air ridge (alpha = 1.0) sensitivity, applied to every
record alike" and drop the Beaufort attribution. Option (ii) is the minimum fix and is what the
frozen method note (`P0_06_method_freeze.json`: "label as in-library air-ridge (alpha=1.0), not
faithful Beaufort") already prescribes; option (i) is what a referee who knows the paper will
expect, and it costs one table row. Neither requires re-scoring the sealed confirmation panel: the
direction of every conclusion is unchanged.

## What was compared

Development panel, identical cases for every method: `cases_air.parquet`, `split_role ==
development`, 40,704 station-year-outage cases over
110 networks, primary endpoint hottest-30-day mean daily water temperature,
tolerance 0.5 C, retention 70% under the outage-length rule (jittered `longest_run`, seed 5 - the
same screen and tie-break as `scripts/219_v18_air_sensitivity.py`, whose air-ridge row this run
reproduces to 15.1616%). "Else climatology" means the estimator's
own value where it exists and the day-of-year climatology otherwise, the manuscript's convention.
Uncertainty on paired differences: network-clustered bootstrap, 1200 draws
(identical point estimate and interval to `stats.paired_cluster_bootstrap` on a cross-check).

### At 70% retention under the outage-length rule (n = 28,493)

| method | n | supported | MAE (C) | median AE (C) | p90 AE (C) | p95 AE (C) | rate > 0.5 C |
| --- | --- | --- | --- | --- | --- | --- | --- |
| faithful Beaufort, else climatology | 28,493 | 100.0% | 0.2031 | 0.0000 | 0.621 | 0.979 | 12.76% |
| faithful Beaufort, train-years fit only, else climatology | 28,493 | 100.0% | 0.2059 | 0.0000 | 0.630 | 0.991 | 13.01% |
| faithful Beaufort, lagged-window reading, else climatology | 28,493 | 100.0% | 0.2171 | 0.0000 | 0.669 | 1.049 | 13.90% |
| faithful Beaufort, July-August fill only, else climatology | 28,493 | 100.0% | 0.2071 | 0.0000 | 0.637 | 1.011 | 13.07% |
| library air ridge, alpha=1.0, else climatology | 28,493 | 98.5% | 0.2314 | 0.0000 | 0.740 | 1.201 | 15.16% |
| linear interpolation | 28,493 | 100.0% | 0.2774 | 0.0000 | 0.867 | 1.520 | 16.02% |
| donor ridge, else climatology | 28,493 | 83.1% | 0.1597 | 0.0000 | 0.482 | 0.840 | 9.57% |
| observed days (incumbent estimator) | 28,493 | 100.0% | 0.4483 | 0.0000 | 1.549 | 2.528 | 22.13% |
| information-conditioned policy (reference) | 28,493 | 100.0% | 0.1505 | 0.0000 | 0.457 | 0.783 | 9.00% |
| oracle over library methods (not deployable) | 28,493 | 100.0% | 0.0759 | 0.0000 | 0.212 | 0.402 | 3.62% |

### All development cases, no screening (n = 40,704)

| method | n | supported | MAE (C) | median AE (C) | p90 AE (C) | p95 AE (C) | rate > 0.5 C |
| --- | --- | --- | --- | --- | --- | --- | --- |
| faithful Beaufort, else climatology | 40,704 | 100.0% | 0.2941 | 0.0300 | 0.834 | 1.260 | 18.47% |
| faithful Beaufort, train-years fit only, else climatology | 40,704 | 100.0% | 0.2972 | 0.0305 | 0.845 | 1.271 | 18.74% |
| faithful Beaufort, lagged-window reading, else climatology | 40,704 | 100.0% | 0.3145 | 0.0349 | 0.907 | 1.371 | 20.06% |
| faithful Beaufort, July-August fill only, else climatology | 40,704 | 100.0% | 0.3014 | 0.0259 | 0.867 | 1.309 | 18.98% |
| library air ridge, alpha=1.0, else climatology | 40,704 | 98.4% | 0.3257 | 0.0321 | 1.019 | 1.537 | 21.43% |
| linear interpolation | 40,704 | 100.0% | 1.0172 | 0.0175 | 2.824 | 6.332 | 26.67% |
| donor ridge, else climatology | 40,704 | 78.1% | 0.2443 | 0.0167 | 0.740 | 1.236 | 14.98% |
| observed days (incumbent estimator) | 40,691 | 100.0% | 1.3052 | 0.0442 | 4.077 | 7.808 | 31.88% |
| information-conditioned policy (reference) | 40,704 | 100.0% | 0.2246 | 0.0153 | 0.674 | 1.103 | 13.97% |
| oracle over library methods (not deployable) | 40,704 | 100.0% | 0.1304 | 0.0035 | 0.377 | 0.665 | 7.19% |

### Only cases where both air methods produced a reconstruction (n = 40,052)

| method | n | supported | MAE (C) | median AE (C) | p90 AE (C) | p95 AE (C) | rate > 0.5 C |
| --- | --- | --- | --- | --- | --- | --- | --- |
| faithful Beaufort, else climatology | 40,052 | 100.0% | 0.2714 | 0.0299 | 0.813 | 1.223 | 18.15% |
| faithful Beaufort, train-years fit only, else climatology | 40,052 | 100.0% | 0.2746 | 0.0303 | 0.820 | 1.231 | 18.42% |
| faithful Beaufort, lagged-window reading, else climatology | 40,052 | 100.0% | 0.2921 | 0.0348 | 0.884 | 1.321 | 19.75% |
| faithful Beaufort, July-August fill only, else climatology | 40,052 | 100.0% | 0.2789 | 0.0258 | 0.844 | 1.260 | 18.66% |
| library air ridge, alpha=1.0, else climatology | 40,052 | 100.0% | 0.3245 | 0.0319 | 1.014 | 1.532 | 21.33% |
| linear interpolation | 40,052 | 100.0% | 1.0148 | 0.0177 | 2.820 | 6.323 | 26.67% |
| donor ridge, else climatology | 40,052 | 78.8% | 0.2426 | 0.0165 | 0.731 | 1.227 | 14.82% |
| observed days (incumbent estimator) | 40,039 | 100.0% | 1.3016 | 0.0441 | 4.068 | 7.793 | 31.86% |
| information-conditioned policy (reference) | 40,052 | 100.0% | 0.2231 | 0.0152 | 0.668 | 1.094 | 13.82% |
| oracle over library methods (not deployable) | 40,052 | 100.0% | 0.1286 | 0.0035 | 0.367 | 0.654 | 7.04% |

### Paired differences at 70% retention (positive = left method worse)

| quantity | contrast | point | 95% CI | n pairs | clusters |
| --- | --- | --- | --- | --- | --- |
| rate > 0.5 C (pp) | faithful Beaufort - library air ridge | -2.404 pp | (-3.199, -1.620) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort - library air ridge | -0.028 C | (-0.046, -0.010) C | 28,493 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort - linear interpolation | -3.260 pp | (-4.267, -1.986) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort - linear interpolation | -0.074 C | (-0.098, -0.045) C | 28,493 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort - donor ridge | +3.187 pp | (+2.022, +4.429) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort - donor ridge | +0.043 C | (+0.024, +0.068) C | 28,493 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort - information-conditioned policy | +3.759 pp | (+2.738, +4.760) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort - information-conditioned policy | +0.053 C | (+0.038, +0.070) C | 28,493 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort train-years-only - faithful Beaufort | +0.256 pp | (+0.173, +0.359) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort train-years-only - faithful Beaufort | +0.003 C | (+0.002, +0.004) C | 28,493 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort July-August-only - faithful Beaufort | +0.309 pp | (+0.010, +0.578) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort July-August-only - faithful Beaufort | +0.004 C | (-0.000, +0.008) C | 28,493 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort lagged-window - faithful Beaufort | +1.144 pp | (+0.735, +1.487) pp | 28,493 | 110 |
| MAE (C) | faithful Beaufort lagged-window - faithful Beaufort | +0.014 C | (+0.009, +0.019) C | 28,493 | 110 |

### Paired differences on all cases

| quantity | contrast | point | 95% CI | n pairs | clusters |
| --- | --- | --- | --- | --- | --- |
| rate > 0.5 C (pp) | faithful Beaufort - library air ridge | -2.953 pp | (-3.946, -1.957) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort - library air ridge | -0.032 C | (-0.062, +0.007) C | 40,704 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort - linear interpolation | -8.198 pp | (-9.697, -6.469) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort - linear interpolation | -0.723 C | (-0.876, -0.600) C | 40,704 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort - donor ridge | +3.491 pp | (+1.857, +5.388) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort - donor ridge | +0.050 C | (+0.008, +0.103) C | 40,704 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort - information-conditioned policy | +4.506 pp | (+3.124, +5.936) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort - information-conditioned policy | +0.069 C | (+0.041, +0.110) C | 40,704 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort train-years-only - faithful Beaufort | +0.268 pp | (+0.177, +0.387) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort train-years-only - faithful Beaufort | +0.003 C | (+0.002, +0.004) C | 40,704 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort July-August-only - faithful Beaufort | +0.504 pp | (+0.062, +0.971) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort July-August-only - faithful Beaufort | +0.007 C | (+0.001, +0.014) C | 40,704 | 110 |
| rate > 0.5 C (pp) | faithful Beaufort lagged-window - faithful Beaufort | +1.587 pp | (+0.908, +2.137) pp | 40,704 | 110 |
| MAE (C) | faithful Beaufort lagged-window - faithful Beaufort | +0.020 C | (+0.012, +0.027) C | 40,704 | 110 |

## Integrity of the comparison

The outage realizations had to be regenerated because the case table stores only their summaries.
Every check below is written by the script to `integrity_checks.json`:

* 40,704 of 40,704 development cases rebuilt and matched by
  (network, station, year, realization_id); 0 mismatches on `total_missing`,
  0 on `longest_run`, maximum absolute deviation
  0.0e+00 on peak-window overlap and 0.0e+00 on warm-season
  observed fraction.
* The stored truth is reproduced exactly (max |deviation| 0.0e+00 C on
  `truth_hottest30`).
* The in-library air ridge was re-run from the same masks and forcing on
  643 cases (arso_bistrica, arso_drava): maximum
  absolute deviation 0.0e+00 C. This is what licenses reading the
  other stored estimator columns as the comparison arms.
* The sufficient-statistics OLS equals `numpy.linalg.lstsq` on the explicit design matrix
  (25 probed cases, max deviation 1.7e-13 C).
* The manuscript's air-row number is reproduced exactly:
  15.1616% at 70% retention.

## What the faithful method does on this panel

* Support: 100.0% of the 40,704 development cases
  (40,704); median R2 of the selected window 0.619; median fit
  sample 1102 summer days. 582 cases keep at least one
  hidden day unfilled because the reanalysis air series has a hole there; the metric survives those
  as long as some 30-day window is complete, and the "else climatology" convention covers the rest.
* Chosen window lengths are spread across the whole grid rather than collapsing to one value -
  2 d: 6,626, 3 d: 6,662, 4 d: 5,774, 5 d: 2,653, 6 d: 3,487, 7 d: 3,309, 8 d: 3,185, 9 d: 2,641, 10 d: 6,367 - which is the behaviour the paper describes and the reason a single fixed lag (or seven
  raw lags) is a different model.
* The three adaptations are not load-bearing: train-years-only fitting moves the rate by
  +0.256 pp, July-August-only filling by
  +0.309 pp, and the alternative window alignment by
  +1.144 pp. Every variant stays between
  12.76% and 13.90%, i.e. below the library air ridge in all four.

## Migration cost for an agency

**Extra inputs.** None beyond what the library air ridge already needs. Both methods consume daily
mean air temperature at (or interpolated to) the station for the whole record; neither needs
discharge, radiation or catchment attributes. The cited paper's discharge and watershed variables
belong to its *spatial extrapolation* component, which answers a different question (predicting
ungauged reaches) and is not what the manuscript's table row compares. In this study the binding
constraint is therefore not the regression choice but air-forcing coverage: the v17 development
panel carries air on 2.26% of its
40,704 cases, the v18 reanalysis forcing used here on
98.64% of the same
40,704 cases (forcing product described in
`results/v18_closure/e5_air_forcing/air_forcing_summary.json`; this run records only its path,
`data/interim/v18_air_forcing.parquet`). An agency that has air temperature can run
either method; one that does not cannot run either.

**Hyperparameters.** The faithful method tunes one hyperparameter, the moving-average window, and it
tunes it per station on that station's own *visible* summer data by in-sample R2, never against the
endpoint and never on the study's development labels. It therefore needs no recalibration when the
archive changes and no development/confirmation split to be honest - a deployability advantage over
the study's certificate screen, whose thresholds were calibrated on the development panel. The
library air ridge's `alpha=1.0`, its lag set (0, 1, 2, 3, 5, 7, 14) and its two
harmonic terms are fixed constants in `estimators.py` (no tuning path in the code); the study-level
hyperparameters (retention, tolerance, the deployed per-case selection) are the ones tuned on
development data only.

**Compute and data.** The whole development panel - 110 networks,
354 stations, 40,704 station-year-outage reconstructions - took
30.7 s wall-clock on 24 processes, with no GPU and no training corpus beyond the
station's own record and the air series. Operationally that is one nine-window OLS calibration per
station-year: trivially cheap next to the data-acquisition cost of the air series itself. The
library air ridge is comparably cheap, so compute does not discriminate between the two.

## Caveats

* This amendment decomposes nothing. The faithful method differs from the library air ridge in three
  ways at once (single selected moving-average window vs seven raw lags; OLS vs alpha = 1.0 ridge;
  summer-only fit vs whole-year fit). The improvement reported here is the effect of the bundle;
  which component carries it is not established by this run.
* The R2 window selection is in-sample, exactly as in the cited paper. It is the paper's design, but
  it means the selected window is not chosen for out-of-sample skill.
* The endpoint is this study's annual hottest-30 mean, not the paper's interannual mean thermal
  peak, and the metric is a retention curve, not the paper's |Tp,fill - Tp,ref| permutation test.
  No number here should be compared with the paper's 0.03-0.25 C.
* Air forcing is NASA POWER daily T2M reanalysis, not the SAFRAN reanalysis used in the paper, and
  it is the same forcing that produces the manuscript's air-complete panel; the comparison between
  methods is therefore internally consistent.
* Development panel only. The sealed USGS confirmation panel
  (`results/wrr_submission_ready/p0_07_sealed_confirmation/`) was not read or re-scored, and this
  amendment makes no claim about it.
* The outage-length screen used to fix 70% retention resolves ties with a fixed random jitter
  (seed 5). A different tie-break moves individual cases but not the screen's composition materially;
  the screen choice itself (length vs certificate) is the subject of the main manuscript, not of
  this amendment.
