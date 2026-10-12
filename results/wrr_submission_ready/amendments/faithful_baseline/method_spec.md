# Method specification - faithful Beaufort et al. (2022) climate correction

Amendment for adversarial finding **F15** (`results/wrr_submission_ready/F_FINDINGS_CLOSURE_AUDIT.csv`:
"air_ridge not faithful Beaufort"). Implemented in `scripts/252_wrr_faithful_baseline.py`;
all numbers in this file come from that script's artifacts in this directory.

## 1. The cited method

Beaufort, A., Diamond, J. S., Sauquet, E., & Moatar, F. (2022). *Spatial extrapolation of stream
thermal peaks using heterogeneous time series at a national scale.* Hydrology and Earth System
Sciences, 26(13), 3477-3495. DOI [10.5194/hess-26-3477-2022](https://doi.org/10.5194/hess-26-3477-2022),
full text <https://hess.copernicus.org/articles/26/3477/2022/>. Read from the published PDF on
2026-10-12 (all quotations below are from that version).

The paper has two components. Only the first is comparable to this study's task, and only the first
is implemented here.

**(a) The thermal peak and its climate correction (their Sect. 2.2-2.3).** The endpoint is the
"thermal peak" `Tp`, "the interannual average of the mean temperature of the 30 hottest consecutive
days of each year (`Tw,30`)i" (their Eq. 1). Because the contributing station-years are
heterogeneous and incomplete, they introduce what they call the climate correction:

> "The climate correction is achieved by first calculating station-specific regressions during
> summer between daily Tw and a right-aligned moving average of Tair at lags ranging from 2-10 d.
> The moving average lag whose regression produced the highest coefficient of determination was
> then used to fill gaps in the time series of Tw for each station."

So: an ordinary least-squares regression (no penalty, no harmonics, not a machine-learning model),
one predictor - a *moving average* of air temperature, not individual lagged days - window lengths
2-10 d, window length selected **per station** by highest R2 on that station's own summer data, and
the fit used to reconstruct the missing summer water temperatures. Their Fig. B2 caption confirms
the search grid and the selection rule: "Daily lags for Tair that produce the highest R2 ... for a
regression between Tw and a right-aligned moving average of Tair at each site ... only integer lag
values were possible ... within each possible lag (2-10 d)." They note that stations with watershed
area > 1000 km2 "tended to have the best R2 at the longest lags".

**Seasonal handling.** The regression is a *summer* regression and the reconstruction is a *summer*
reconstruction: "we focused on the two hottest stream temperature months, July and August
(hereafter referred to as summer)". They verified that this window contains the annual maximum
("the hottest day of the year always occurred within the approximate 30 d period between 28 July
and 30 August (mean 12 August, SD 16 d), and only 3% of site years had their hottest 30 d outside
of this period"), which licensed the use of sub-annual July-August records held by fishing agencies.

**Reported performance metric.** For the climate correction the paper reports a permutation test
on the 30 stations with complete 2009-2017 records: artificial annual gaps of 1-9 years were
introduced, backfilled with the same regression, and compared against the reference thermal peak.
The statistic is the absolute bias |Tp,fill - Tp,ref| against |Tp,gap - Tp,ref|: "growing from a
median of 0.03 C with 1 year of gaps to 0.25 C with 8 years of gaps. Climate-corrected biases
remained below 0.25 C for 75% of the stations with up to 6 years of introduced gaps. There was no
systematic bias". The spatial-model performance (NSE, RMSE, bias, 100x 80/20 station
cross-validation) belongs to component (b) and is not the metric for this step.

**(b) Spatial extrapolation to the whole network (their Sect. 2.4).** Four models (multiple linear
regression, ANN, random forest, multi-model combination) on 16 climatic, hydrologic and
watershed variables extrapolate `Tp` to 114,600 reaches, and `Tp,air` is computed from reanalysis
air temperature alone as the "simplest and most widely available stream temperature proxy". This
component needs discharge, specific discharge minima, concavity index, hydrologic regime,
elevation, slope, riparian cover, weir and pond density, precipitation and snowfall - inputs this
study does not have, and a *spatial* task (predicting ungauged reaches) that is not the task of the
manuscript's table row. It is **not** implemented here, and nothing in this amendment depends on it.

## 2. What is implemented here, exactly

| paper element | implementation in `scripts/252_wrr_faithful_baseline.py` |
| --- | --- |
| per-station regression of Tw on a moving average of Tair | OLS with intercept, one predictor, fitted from sufficient statistics (`_fit_from_sums`) |
| window lengths 2-10 d | `BEAUFORT_LAGS = [2, 3, 4, 5, 6, 7, 8, 9, 10]` |
| "right-aligned" moving average | trailing mean of Tair over the L days ending on the day being reconstructed, `air.rolling(L).mean()` |
| window chosen by highest R2 | in-sample R2 of the same fit sample, argmax over the nine windows, recomputed per station-year and per outage realization |
| summer regression | fit sample restricted to July-August (`SUMMER_MONTHS = (7, 8)`), the paper's definition of summer |
| reconstruction of the missing days | hidden days of the evaluation year predicted from the observed Tair window, then the 30-day rolling mean is taken on the completed year |
| minimum sample | >= 120 usable summer days, the estimator library's own `MIN_TRAIN_ROWS` convention (documented adaptation; the paper states no threshold) |
| endpoint | the year's hottest-30-day mean daily water temperature, this study's primary endpoint |

Implementation variants (all scored, all reported):

* `beaufort` (primary) - fit sample: every **visible** summer day of the station's record, i.e. all
  other years plus the non-outage days of the evaluation year. This is the closest analogue of
  "all available summer data at the station" and uses only decision-time visible data.
* `beaufort_trainonly` - fit sample restricted to years other than the evaluation year, which is the
  information budget of the in-library estimators. Difference from primary: see REPORT.md.
* `beaufort_jja` - only the hidden July-August days are reconstructed, the strict summer-only
  reading of the paper; hidden days outside summer stay missing.
* `beaufort_lagshift` - the alternative reading of "right-aligned moving average ... at lag L": the
  window's right edge sits L-1 days before the reconstructed day (`rolling(L).mean().shift(L-1)`)
  instead of ending on it.

All four use the study's fallback convention for the scored table: the reconstruction where it is
available, otherwise the day-of-year climatology - the same convention as the manuscript's
"always air regression, else climatology" row.

## 3. What is adapted, and what that means for the label

Nothing had to be substituted: the cited climate correction needs only daily mean water
temperature and daily mean air temperature, both of which this study's panel has. The method as
implemented is faithful in regression family, predictor, window grid, selection rule, season and
fitting data. Three adaptations remain, and each is carried as a scored sensitivity rather than an
assumption:

1. **Endpoint level.** The paper's `Tp` is an interannual mean over a station's years; the
   manuscript's endpoint is one annual value per station-year. A per-year analogue is the only one
   that fits this study's case table, and it is the paper's own `(Tw,30)i` before averaging.
2. **Fit sample.** Visible days of the evaluation year are included in the primary variant, because
   the paper fits on whatever summer data the station has while a gap year is being reconstructed.
   The train-years-only variant bounds the effect.
3. **Season of the fill.** The paper reconstructs summer; this study's years contain outages in all
   months and the endpoint can in principle see a non-summer day, so the primary fills every hidden
   day with the summer regression. The July-August-only variant bounds the effect.

Because of these, the result is labelled in REPORT.md as a **faithful reimplementation of the cited
climate correction, approximate as a drop-in case-level baseline**. It is not labelled with the
paper's own accuracy figures (0.03-0.25 C), which measure |Tp,fill - Tp,ref| over 1-9 gap years at
30 reference stations and are not comparable to a retention curve over 40,704 station-year-outage
cases.

## 4. How to reproduce

```
PYTHONPATH=src python3 scripts/252_wrr_faithful_baseline.py --workers 24 --draws 1200 --verify-networks 2
```

Runtime: 30.7 s wall on 24 processes for
110 networks, 354 stations and
40,704 rebuilt outage rows. Air forcing:
`data/interim/v18_air_forcing.parquet` (the forcing table behind the manuscript's
air-complete development panel; the product description is in
`results/v18_closure/e5_air_forcing/air_forcing_summary.json`). Case table:
`results/v17_fitness/step3_cases/cases_air.parquet`. The sealed confirmation panel was not read.
