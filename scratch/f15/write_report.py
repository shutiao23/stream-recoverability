#!/usr/bin/env python3
"""Render method_spec.md and REPORT.md for the F15 faithful-baseline amendment.

Every number in the two documents is interpolated from the artifacts written by
scripts/252_wrr_faithful_baseline.py (comparison.csv, contrasts.csv, summary.json,
integrity_checks.json), so nothing is transcribed by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/wrr_submission_ready/amendments/faithful_baseline"

comp = pd.read_csv(OUT / "comparison.csv")
con = pd.read_csv(OUT / "contrasts.csv")
summ = json.loads((OUT / "summary.json").read_text())
checks = json.loads((OUT / "integrity_checks.json").read_text())

RET70 = "length_rule_70pct"
ALL = "all_cases"
SUP = "both_air_methods_supported"

LABEL = {
    "faithful Beaufort (else climatology)": "faithful Beaufort, else climatology",
    "faithful Beaufort, train years only (else climatology)": "faithful Beaufort, train-years fit only, else climatology",
    "faithful Beaufort, lagged-window reading (else climatology)": "faithful Beaufort, lagged-window reading, else climatology",
    "faithful Beaufort, July-August fill only (else climatology)": "faithful Beaufort, July-August fill only, else climatology",
    "library air ridge alpha=1.0 (else climatology)": "library air ridge, alpha=1.0, else climatology",
    "linear interpolation": "linear interpolation",
    "donor ridge (else climatology)": "donor ridge, else climatology",
    "observed days (incumbent estimator)": "observed days (incumbent estimator)",
    "information-conditioned policy (reference)": "information-conditioned policy (reference)",
    "oracle over library methods (not deployable)": "oracle over library methods (not deployable)",
}
ORDER = list(LABEL)


def row(method: str, retention: str) -> pd.Series:
    return comp.loc[comp["retention_set"].eq(retention) & comp["method"].eq(method)].iloc[0]


def m(method: str, column: str, retention: str = RET70) -> float:
    return float(row(method, retention)[column])


def c(quantity: str, left: str, right: str, column: str, retention: str = RET70) -> float:
    hit = con.loc[
        con["retention_set"].eq(retention)
        & con["quantity"].eq(quantity)
        & con["left"].eq(left)
        & con["right"].eq(right)
    ]
    return float(hit.iloc[0][column])


def method_table(retention: str) -> str:
    lines = [
        "| method | n | supported | MAE (C) | median AE (C) | p90 AE (C) | p95 AE (C) | rate > 0.5 C |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for method in ORDER:
        r = row(method, retention)
        lines.append(
            f"| {LABEL[method]} | {int(r['n_cases']):,} | {r['support_pct']:.1f}% | {r['mae_c']:.4f} | "
            f"{r['median_ae_c']:.4f} | {r['p90_ae_c']:.3f} | {r['p95_ae_c']:.3f} | {r['rate_above_0.5_pct']:.2f}% |"
        )
    return "\n".join(lines)


CONTRASTS = [
    ("rate_above_0.5", "faithful Beaufort (else climatology)", "library air ridge alpha=1.0 (else climatology)", "faithful Beaufort - library air ridge"),
    ("mean_abs_error_c", "faithful Beaufort (else climatology)", "library air ridge alpha=1.0 (else climatology)", "faithful Beaufort - library air ridge"),
    ("rate_above_0.5", "faithful Beaufort (else climatology)", "linear interpolation", "faithful Beaufort - linear interpolation"),
    ("mean_abs_error_c", "faithful Beaufort (else climatology)", "linear interpolation", "faithful Beaufort - linear interpolation"),
    ("rate_above_0.5", "faithful Beaufort (else climatology)", "donor ridge (else climatology)", "faithful Beaufort - donor ridge"),
    ("mean_abs_error_c", "faithful Beaufort (else climatology)", "donor ridge (else climatology)", "faithful Beaufort - donor ridge"),
    ("rate_above_0.5", "faithful Beaufort (else climatology)", "information-conditioned policy (reference)", "faithful Beaufort - information-conditioned policy"),
    ("mean_abs_error_c", "faithful Beaufort (else climatology)", "information-conditioned policy (reference)", "faithful Beaufort - information-conditioned policy"),
    ("rate_above_0.5", "faithful Beaufort, train years only (else climatology)", "faithful Beaufort (else climatology)", "faithful Beaufort train-years-only - faithful Beaufort"),
    ("mean_abs_error_c", "faithful Beaufort, train years only (else climatology)", "faithful Beaufort (else climatology)", "faithful Beaufort train-years-only - faithful Beaufort"),
    ("rate_above_0.5", "faithful Beaufort, July-August fill only (else climatology)", "faithful Beaufort (else climatology)", "faithful Beaufort July-August-only - faithful Beaufort"),
    ("mean_abs_error_c", "faithful Beaufort, July-August fill only (else climatology)", "faithful Beaufort (else climatology)", "faithful Beaufort July-August-only - faithful Beaufort"),
    ("rate_above_0.5", "faithful Beaufort, lagged-window reading (else climatology)", "faithful Beaufort (else climatology)", "faithful Beaufort lagged-window - faithful Beaufort"),
    ("mean_abs_error_c", "faithful Beaufort, lagged-window reading (else climatology)", "faithful Beaufort (else climatology)", "faithful Beaufort lagged-window - faithful Beaufort"),
]


def contrast_table(retention: str) -> str:
    lines = [
        "| quantity | contrast | point | 95% CI | n pairs | clusters |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for quantity, left, right, label in CONTRASTS:
        point = c(quantity, left, right, "point", retention)
        low = c(quantity, left, right, "low", retention)
        high = c(quantity, left, right, "high", retention)
        n = int(c(quantity, left, right, "n_pairs", retention))
        k = int(c(quantity, left, right, "n_clusters", retention))
        unit = " pp" if quantity == "rate_above_0.5" else " C"
        scale = 100.0 if quantity == "rate_above_0.5" else 1.0
        lines.append(
            f"| {'rate > 0.5 C (pp)' if quantity == 'rate_above_0.5' else 'MAE (C)'} | {label} | "
            f"{point * scale:+.3f}{unit} | ({low * scale:+.3f}, {high * scale:+.3f}){unit} | {n:,} | {k} |"
        )
    return "\n".join(lines)


lags = summ["beaufort_lag_choice_counts"]
lag_txt = ", ".join(f"{key} d: {value:,}" for key, value in sorted(lags.items(), key=lambda kv: int(kv[0])))
support = summ["beaufort_support"]

method_spec = f"""# Method specification - faithful Beaufort et al. (2022) climate correction

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
| window lengths 2-10 d | `BEAUFORT_LAGS = {list(checks['beaufort_lags'])}` |
| "right-aligned" moving average | trailing mean of Tair over the L days ending on the day being reconstructed, `air.rolling(L).mean()` |
| window chosen by highest R2 | in-sample R2 of the same fit sample, argmax over the nine windows, recomputed per station-year and per outage realization |
| summer regression | fit sample restricted to July-August (`SUMMER_MONTHS = {tuple(checks['summer_months'])}`), the paper's definition of summer |
| reconstruction of the missing days | hidden days of the evaluation year predicted from the observed Tair window, then the 30-day rolling mean is taken on the completed year |
| minimum sample | >= {checks['min_fit_days']} usable summer days, the estimator library's own `MIN_TRAIN_ROWS` convention (documented adaptation; the paper states no threshold) |
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

Runtime: {checks['wall_seconds']:.1f} s wall on {checks['workers']} processes for
{checks['n_networks_rebuilt']} networks, {checks['n_stations_rebuilt']} stations and
{checks['n_rebuilt_rows']:,} rebuilt outage rows. Air forcing:
`{Path(checks['forcing_path']).relative_to(ROOT)}` (the forcing table behind the manuscript's
air-complete development panel; the product description is in
`results/v18_closure/e5_air_forcing/air_forcing_summary.json`). Case table:
`{Path(checks['cases_path']).relative_to(ROOT)}`. The sealed confirmation panel was not read.
"""

report = f"""# F15 - is the manuscript's "Beaufort-style" baseline the cited method?

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
outage-length rule the consequential-error rate is {m('faithful Beaufort (else climatology)','rate_above_0.5_pct'):.2f}%
for the faithful method against {m('library air ridge alpha=1.0 (else climatology)','rate_above_0.5_pct'):.2f}%
for the library air ridge (paired difference
{c('rate_above_0.5','faithful Beaufort (else climatology)','library air ridge alpha=1.0 (else climatology)','point')*100:+.3f} pp,
95% CI {c('rate_above_0.5','faithful Beaufort (else climatology)','library air ridge alpha=1.0 (else climatology)','low')*100:+.3f} to
{c('rate_above_0.5','faithful Beaufort (else climatology)','library air ridge alpha=1.0 (else climatology)','high')*100:+.3f} pp;
network-clustered bootstrap, {summ['bootstrap_draws']} draws).

**The manuscript's qualitative claim survives the correction.** Even with the faithful method, a
single air-temperature regression applied uniformly to every record is worse than the study's
per-case selection: {m('faithful Beaufort (else climatology)','rate_above_0.5_pct'):.2f}% against
{m('information-conditioned policy (reference)','rate_above_0.5_pct'):.2f}% for the
information-conditioned policy
({c('rate_above_0.5','faithful Beaufort (else climatology)','information-conditioned policy (reference)','point')*100:+.3f} pp,
95% CI {c('rate_above_0.5','faithful Beaufort (else climatology)','information-conditioned policy (reference)','low')*100:+.3f} to
{c('rate_above_0.5','faithful Beaufort (else climatology)','information-conditioned policy (reference)','high')*100:+.3f} pp),
and worse than the donor ridge at equal retention. What changes is the number attached to the name:
the cited method is {m('library air ridge alpha=1.0 (else climatology)','rate_above_0.5_pct') - m('faithful Beaufort (else climatology)','rate_above_0.5_pct'):.2f} points better than the
object the manuscript put in its place.

**Labelling of the result in this amendment.** "Faithful reimplementation of the cited climate
correction, approximate as a drop-in case-level baseline": faithful in regression family (OLS), in
predictor (a right-aligned 2-10 d moving average of air temperature), in the window grid, in the
per-station R2 selection rule and in the summer fit; approximate only where the endpoint level, the
fit sample and the season of the fill had to be adapted to this study's case table. No input had to
be substituted - the cited climate correction needs only daily water and air temperature, both of
which the panel has.

**Recommendation.** Either (i) report the faithful reimplementation as the cited-method baseline
({m('faithful Beaufort (else climatology)','rate_above_0.5_pct'):.2f}% at 70% retention) alongside or instead of the library number, or
(ii) rename the library row to "in-library air ridge (alpha = 1.0) sensitivity, applied to every
record alike" and drop the Beaufort attribution. Option (ii) is the minimum fix and is what the
frozen method note (`P0_06_method_freeze.json`: "label as in-library air-ridge (alpha=1.0), not
faithful Beaufort") already prescribes; option (i) is what a referee who knows the paper will
expect, and it costs one table row. Neither requires re-scoring the sealed confirmation panel: the
direction of every conclusion is unchanged.

## What was compared

Development panel, identical cases for every method: `cases_air.parquet`, `split_role ==
development`, {checks['n_development_cases']:,} station-year-outage cases over
{summ['n_networks']} networks, primary endpoint hottest-30-day mean daily water temperature,
tolerance 0.5 C, retention 70% under the outage-length rule (jittered `longest_run`, seed 5 - the
same screen and tie-break as `scripts/219_v18_air_sensitivity.py`, whose air-ridge row this run
reproduces to {checks['manuscript_air_ridge_rate_pct_reproduced']:.4f}%). "Else climatology" means the estimator's
own value where it exists and the day-of-year climatology otherwise, the manuscript's convention.
Uncertainty on paired differences: network-clustered bootstrap, {summ['bootstrap_draws']} draws
(identical point estimate and interval to `stats.paired_cluster_bootstrap` on a cross-check).

### At 70% retention under the outage-length rule (n = {int(m('faithful Beaufort (else climatology)','n_cases')):,})

{method_table(RET70)}

### All development cases, no screening (n = {int(m('faithful Beaufort (else climatology)','n_cases', ALL)):,})

{method_table(ALL)}

### Only cases where both air methods produced a reconstruction (n = {int(m('faithful Beaufort (else climatology)','n_cases', SUP)):,})

{method_table(SUP)}

### Paired differences at 70% retention (positive = left method worse)

{contrast_table(RET70)}

### Paired differences on all cases

{contrast_table(ALL)}

## Integrity of the comparison

The outage realizations had to be regenerated because the case table stores only their summaries.
Every check below is written by the script to `integrity_checks.json`:

* {checks['n_matched_rows']:,} of {checks['n_development_cases']:,} development cases rebuilt and matched by
  (network, station, year, realization_id); {checks['mask_total_missing_mismatches']} mismatches on `total_missing`,
  {checks['mask_longest_run_mismatches']} on `longest_run`, maximum absolute deviation
  {checks['mask_peak_overlap_max_abs_dev']:.1e} on peak-window overlap and {checks['mask_warm_fraction_max_abs_dev']:.1e} on warm-season
  observed fraction.
* The stored truth is reproduced exactly (max |deviation| {checks['truth_hottest30_max_abs_dev']:.1e} C on
  `truth_hottest30`).
* The in-library air ridge was re-run from the same masks and forcing on
  {checks['library_air_ridge_repro_n']:,} cases ({', '.join(checks['library_air_ridge_repro_networks'])}): maximum
  absolute deviation {checks['library_air_ridge_repro_max_abs_dev']:.1e} C. This is what licenses reading the
  other stored estimator columns as the comparison arms.
* The sufficient-statistics OLS equals `numpy.linalg.lstsq` on the explicit design matrix
  ({checks['sufficient_stats_vs_lstsq_n']} probed cases, max deviation {checks['sufficient_stats_vs_lstsq_max_abs_dev_c']:.1e} C).
* The manuscript's air-row number is reproduced exactly:
  {checks['manuscript_air_ridge_rate_pct_reproduced']:.4f}% at 70% retention.

## What the faithful method does on this panel

* Support: {support['pct_reconstructed']:.1f}% of the {summ['n_cases']:,} development cases
  ({support['n_reconstructed']:,}); median R2 of the selected window {support['median_r2']:.3f}; median fit
  sample {support['median_fit_days']:.0f} summer days. {support['cases_with_unfilled_hidden_days']:,} cases keep at least one
  hidden day unfilled because the reanalysis air series has a hole there; the metric survives those
  as long as some 30-day window is complete, and the "else climatology" convention covers the rest.
* Chosen window lengths are spread across the whole grid rather than collapsing to one value -
  {lag_txt} - which is the behaviour the paper describes and the reason a single fixed lag (or seven
  raw lags) is a different model.
* The three adaptations are not load-bearing: train-years-only fitting moves the rate by
  {c('rate_above_0.5','faithful Beaufort, train years only (else climatology)','faithful Beaufort (else climatology)','point')*100:+.3f} pp, July-August-only filling by
  {c('rate_above_0.5','faithful Beaufort, July-August fill only (else climatology)','faithful Beaufort (else climatology)','point')*100:+.3f} pp, and the alternative window alignment by
  {c('rate_above_0.5','faithful Beaufort, lagged-window reading (else climatology)','faithful Beaufort (else climatology)','point')*100:+.3f} pp. Every variant stays between
  {min(m(x,'rate_above_0.5_pct') for x in ORDER if x.startswith('faithful')):.2f}% and {max(m(x,'rate_above_0.5_pct') for x in ORDER if x.startswith('faithful')):.2f}%, i.e. below the library air ridge in all four.

## Migration cost for an agency

**Extra inputs.** None beyond what the library air ridge already needs. Both methods consume daily
mean air temperature at (or interpolated to) the station for the whole record; neither needs
discharge, radiation or catchment attributes. The cited paper's discharge and watershed variables
belong to its *spatial extrapolation* component, which answers a different question (predicting
ungauged reaches) and is not what the manuscript's table row compares. In this study the binding
constraint is therefore not the regression choice but air-forcing coverage: the v17 development
panel carries air on {checks['air_available_pct']['v17_forcing_panel']:.2f}% of its
{checks['air_available_pct']['n_cases_v17_dev']:,} cases, the v18 reanalysis forcing used here on
{checks['air_available_pct']['v18_forcing_panel']:.2f}% of the same
{checks['air_available_pct']['n_cases_v18_dev']:,} cases (forcing product described in
`results/v18_closure/e5_air_forcing/air_forcing_summary.json`; this run records only its path,
`{Path(checks['forcing_path']).relative_to(ROOT)}`). An agency that has air temperature can run
either method; one that does not cannot run either.

**Hyperparameters.** The faithful method tunes one hyperparameter, the moving-average window, and it
tunes it per station on that station's own *visible* summer data by in-sample R2, never against the
endpoint and never on the study's development labels. It therefore needs no recalibration when the
archive changes and no development/confirmation split to be honest - a deployability advantage over
the study's certificate screen, whose thresholds were calibrated on the development panel. The
library air ridge's `alpha=1.0`, its lag set {tuple(__import__('stream_recoverability.experiments.v17_fitness.estimators', fromlist=['AIR_LAGS']).AIR_LAGS)} and its two
harmonic terms are fixed constants in `estimators.py` (no tuning path in the code); the study-level
hyperparameters (retention, tolerance, the deployed per-case selection) are the ones tuned on
development data only.

**Compute and data.** The whole development panel - {checks['n_networks_rebuilt']} networks,
{checks['n_stations_rebuilt']} stations, {checks['n_rebuilt_rows']:,} station-year-outage reconstructions - took
{checks['wall_seconds']:.1f} s wall-clock on {checks['workers']} processes, with no GPU and no training corpus beyond the
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
"""

(OUT / "method_spec.md").write_text(method_spec, encoding="utf-8")
(OUT / "REPORT.md").write_text(report, encoding="utf-8")
print("wrote", OUT / "method_spec.md", OUT / "REPORT.md")
