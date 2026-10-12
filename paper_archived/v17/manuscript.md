# Which property of a data gap matters depends on which thermal metric you want: outage timing governs warm-season extremes, outage length governs the annual mean

> **Superseded by `paper/v18/manuscript.md`.** This version is retained because
> the pre-registered confirmation it reports is the one that was scored, and
> because two of its statements were later found to be wrong: the imputed limit
> of the standing guidance is twenty weeks rather than thirteen (corrected in
> the two places below, with the operating point re-run), and the
> timing-versus-length dichotomy is the two ends of a continuum rather than a
> dichotomy. v18 also adds the deployment, representativeness, air-forcing and
> informative-missingness analyses this version lacks.

<!-- numbers:start -->
```json
{
  "networks": 146,
  "station_years": 5114,
  "cases": 51524,
  "development_cases": 40704,
  "reserved_cases": 10820,
  "reserved_networks": 36,
  "certificate_at_70_reserved": 0.0253,
  "length_rule_at_70_reserved": 0.0966,
  "confirmation_contrast_points": -7.1297,
  "marginal_coverage": 0.9085
}
```
<!-- numbers:end -->

## Key points

- Across 146 river networks in nine countries, whether an outage hides a
  station's climatological peak window governs the error of a warm-season
  extreme, while how many days are missing governs the error of the annual
  mean; the two orderings reverse, and which applies is predictable from the
  form of the metric.
- Published completeness guidance screens records on gap length, which is the
  weaker axis for the summer extreme used in cold-water habitat assessment: on
  36 networks never used for fitting, screening on timing cuts the share of
  retained station-years whose peak is wrong by more than 0.5 °C from 9.7% to
  4.2% using three variables, and to 2.5% with a calibrated screen.
- Computing a thermal metric from recorded days alone, the default once a year
  passes a completeness screen, carries a mean absolute error of 1.31 °C on the
  annual peak — larger than one interannual standard deviation of the quantity
  being measured.

## Abstract

Thermal archives are screened before use, almost always by a threshold on
record completeness: a minimum fraction of the year, or a maximum consecutive
gap. Two assumptions are built into that practice and are rarely stated — that
the relevant property of an outage is its size, and that one screening rule
serves every derived metric. We show that the second assumption makes the first
wrong half the time. A derived metric's error depends on whichever feature of
the record the metric is a function of: an annual mean is a sum over days, so
its error scales with how many days are missing; a warm-season extreme is
localised in a window, so its error scales with whether that window survived.
On 5,114 fully observed river station-years from 146 networks and nine
agencies, with 51,524 outage realizations, the prediction holds and reverses as
predicted. For the hottest 30-day and 7-day means and for the annual amplitude,
peak-window overlap dominates and outage length adds nothing measurable once
timing is included; for the annual mean and the coldest 30-day mean the
ordering reverses and length is the better axis. The separation survives a
sweep of the tolerance, instrument-scale perturbation of the reference series,
and clustered inference. Screening on the governing axis, pre-registered and
scored once on 36 reserved networks, reduces the consequential-error rate by
7.1 percentage points relative to the incumbent length rule at equal retention,
reduces severe underestimation of the summer peak sevenfold, and removes the
bias it imparts to counts of threshold exceedance. Most of the gain — 3.7 of
6.3 points — comes from changing the axis rather than from the model built on
it, and we give the three-variable rule that captures it. We recommend that
length-based completeness rules be retained for averages and replaced for
warm-season extremes.

## 1. Introduction

Stream temperature is measured to answer questions about thermal regime: was
this summer stressful for cold-water fish, is the annual peak rising, how many
years exceeded a criterion. Those questions are answered from derived
statistics computed on a completed calendar year, and the records they are
computed from have holes in them. Loggers fail, are buried by ice, are lost to
floods, or are simply not visited. Before a station-year enters an analysis, an
analyst must decide whether its statistic can be trusted.

That decision is made today with a completeness rule. Agency monitoring
standards specify a minimum share of the year that must be present. The most
widely cited quantitative guidance for annual stream-temperature metrics
constrains the longest consecutive gap instead: records missing less than seven
consecutive weeks support estimation of all annual signal parameters, and
imputation extends the tolerable window to approximately twenty weeks (Johnson
et al., 2021). Both are thresholds on the *size* of the outage, and both are
applied to whichever statistic the analyst happens to want. Neither assumption
has been tested against an alternative on a large panel where the truth is
known.

Both cannot be right, because the statistics do not depend on the record in the
same way. An annual mean is a sum over days: removing *k* days removes *k*
terms and it matters little which. A hottest 30-day mean is an extreme living
in a specific window: if the outage misses that window the statistic is
recoverable almost exactly however long the outage is, and if the outage covers
it the statistic must be inferred however short the outage is. The prediction
is sharp and directional — at fixed outage length, hiding the station's
climatological peak window should dominate the error of a warm-season extreme
and be nearly irrelevant to the annual mean — and it implies that the incumbent
rule gets an ordering exactly backwards: a 30-day outage over the peak should
be worse than a 200-day outage that misses it. Figure 4 shows that this is
what the data do: panel a is the reversal the incumbent axis cannot see, and
panel d is the endpoint dependence that makes one screening rule insufficient.

Existing work cannot settle this, for structural rather than incidental
reasons. Guidance measures tolerance along one axis, so it cannot compare axes;
Johnson et al. report that the *timing* of missing data mattered
"inconsistently in space and time" but had no covariate with which to explain
it. Gap-filling studies optimise the accuracy of the interpolated series rather
than the admissibility of the completed year (Li et al., 2017). Beaufort et al. (2022) come closest: they gap-fill incomplete summer records
with air-temperature regressions precisely so that a thermal peak can be
computed, and they use the same statistic we do — the mean of the thirty
hottest consecutive days — validating the filling on fully monitored reference
sites. But their object is spatial extrapolation across 105,800 reaches; the
filling is a fixed preprocessing treatment applied to every record alike, and
no station-year is ever declined. The recent machine-learning literature on
stream temperature — 57 studies between 2020 and 2024 by the count of Corona
and Hogue (2025) — optimises daily prediction skill and rarely propagates to a
derived annual statistic, let alone to an admission decision. What is common to all of them is that the screening decision is never
conditioned on what the target statistic actually depends on.

**The insight of this paper is one sentence: a record-screening rule should
condition on whichever feature of the record the target statistic is a function
of, and for warm-season extremes that feature is when the outage occurred, not
how long it lasted.** Figure 1 states the argument in one picture: the same
record, two estimands, two supports, and the measured error gradient along each
axis under each of them.

We test the prediction on 5,114 fully observed river station-years from 146
networks across nine national agencies, placing 51,524 outage realizations and
scoring five derived metrics against fully observed truth. We then act on it:
for the summer extreme, we build a screening rule on the governing axis, freeze
it with a pre-registered success criterion and a precision calculation, and
score it once on 36 networks reserved before any analysis. We ask in advance
which action spaces have room to move, and we report the catchment attributes
that make a river hard.

Our contributions are at four levels.

1. **A finding.** Which outage property governs a thermal metric's error is
   determined by the form of the metric, and the two regimes reverse. This
   resolves, rather than contradicts, the inconsistency the standing guidance
   reports.
2. **A reframing.** Record screening is a conditional decision problem whose
   conditioning set is dictated by the estimand, not a single completeness
   threshold applied uniformly.
3. **A method and a deployable rule.** A calibrated screen that emits a
   conformal interval on the completed-year metric and an admission decision at
   an analyst-chosen tolerance; and a three-variable logistic rule, given with
   its coefficients, that captures 59% of the benefit.
4. **Empirical bounds.** Out-of-sample confirmation across agencies, with the
   regimes in which the advantage is large, small, or absent stated explicitly,
   and with the catchment attributes that predict difficulty.

## 2. Related work: a map of what is being optimised

The literature this paper intervenes in is not one conversation but five, and
they differ in what they optimise, on what unit they decide, and along which
axis they condition.

| body of work | optimises | decision unit | conditioning axis | reports uncertainty on the derived metric |
|---|---|---|---|---|
| record-completeness guidance (Johnson et al., 2021; agency standards) | tolerable amount of missing data | station-year | outage size | no |
| gap filling and record extension (Li et al., 2017) | accuracy of the filled series | day | donor and air information | rarely |
| thermal-peak reconstruction and extrapolation (Beaufort et al., 2022) | spatial coverage of the thermal peak | reach | air-temperature regression, applied uniformly | validation against reference sites, not per case |
| machine-learning stream-temperature models (Corona and Hogue, 2025, reviewing 57 studies) | daily prediction skill | day | meteorology, catchment attributes | occasionally, at daily scale |
| reject-option and selective prediction (Zaoui et al., 2020) | error rate at a fixed rejection rate | case | model confidence | as a rejection rate, not in physical units |
| **this work** | **error of the derived metric among retained station-years** | **station-year** | **the feature the metric is a function of** | **yes, as a calibrated interval in °C** |

Three consequences follow from the map. First, no existing line compares
screening axes, because each fixes one. Second, uncertainty on the *derived*
statistic — the number a manager reads — is essentially unreported; daily
skill is reported instead, and the two are not interchangeable for an extreme.
Third, the selective-prediction literature supplies decision machinery whose
control variable is a rejection rate, whereas an analyst needs a tolerance in
degrees on the quantity they report. This paper occupies the row that is
otherwise empty.

## 3. Problem formulation

Let a station-year be a sequence \(y = (y_1, \dots, y_T)\) of daily mean water
temperatures, \(T \in \{365, 366\}\), and let \(q(\cdot)\) be the derived
statistic of interest — here the hottest consecutive 30-day mean,
\(q(y) = \max_{t} \frac{1}{30}\sum_{i=t}^{t+29} y_i\), with the annual mean, the
7-day peak, the cold extreme and the amplitude as alternatives.

An outage is a binary mask \(m \in \{0,1\}^T\); the analyst observes
\(y_{\bar m}\), the days where \(m_t = 0\). A *reconstruction* \(\hat y = R(y_{\bar
m}, Z)\) completes the year using side information \(Z\) — synchronous donor
stations, meteorology, the station's own history — and the analyst reports
\(q(\hat y)\). The quantity that matters is the error of the reported statistic,

\[
L = \bigl| q(\hat y) - q(y) \bigr|,
\]

and a station-year is *consequential* when \(L > \tau\) for a tolerance \(\tau\)
stated in the units of \(q\).

A **screening rule** is a map \(s: (m, Z) \mapsto \{\text{retain}, \text{exclude}\}\)
that must not read the hidden days \(y_m\). Any such rule traces a
retention–error frontier: at retention \(r = \mathbb{E}[s = \text{retain}]\), the
quantity of interest is \(\Pr(L > \tau \mid s = \text{retain})\). Two rules are
compared at equal \(r\), because a rule can always buy accuracy by discarding
more.

The incumbent is \(s_{\text{len}}(m) = \mathbb{1}\{\max \text{run}(m) \le \theta\}\),
a threshold on outage size. Its conditioning set contains no information about
*where* the outage fell relative to the support of \(q\).

The central hypothesis is about that conditioning set. Write \(W_q(y)\) for the
subset of days on which \(q\) depends most — for the 30-day peak, the window
achieving the maximum; for the annual mean, all days equally. Define the
*overlap* \(o = |W_q \cap \{t : m_t = 1\}| / |W_q|\), estimated at decision time
from the station's other years. Then:

> **H1.** For a statistic whose support is a narrow window, \(\Pr(L > \tau)\) is
> governed by \(o\) and only weakly by \(\|m\|_1\). For a statistic whose support
> is the whole year, the ordering reverses.

H1 is falsifiable in both halves, and it fails if the two axes discriminate
equally, if the ordering is not stable in \(\tau\), or if it does not reverse
between the extreme and the mean.

## 4. Data and study design

Figure 3 gives the design as a whole: the providers, the quality control that
defines the denominator, the network-level stratified split, the gate that
decided which action space was worth an experiment, the freeze, and the single
opening of the reserved panel.

### 4.1 Records and quality control

Daily water-temperature series were assembled from nine national providers:
ARSO (Slovenia), CHMI (Czechia), FOEN (Switzerland), GKD Bayern and LUBW
(Germany), NVE (Norway), Rijkswaterstaat (Netherlands), SYKE (Finland) and the
USGS (United States). A *network* is one provider's group of stations on a
common river system; it is the unit at which donor stations are available to one
another, and it is the clustering unit for every interval reported here, because
station-years within a network share weather, regulation and instrumentation.

Waterbody class was assigned per network and non-river objects — seas, lakes,
canals, estuaries, deltas — are excluded rather than averaged into a river
result. Reference series are never imputed: a calendar year with any missing day
supplies no truth and is used only as a source of realistic outage geometry.
Stations with fewer than four fully observed calendar years are excluded because
the estimator protocol requires them. The full denominator with every exclusion
and its count is in the supporting information.

This leaves **146 networks, 457 stations and 5,114 fully observed
station-years**.

For the United States subset, basin characteristics were joined from GAGES-II
(Falcone, 2011) on the eight-digit gauge identifier, matching **140 of 204**
eligible stations across 57 networks and supplying baseflow index, subsurface
contact time, drainage area, site elevation, basin slope and upstream dam
storage. These are used in §5.3 to ask which rivers are hard; they are
deliberately *not* used inside the screening rule, because they are unavailable
for the other eight agencies and a rule that required them could not be
recommended to them.

### 4.2 Split

Networks — never station-years — were split into development and reserved,
stratified on provider and on donor regime (no synchronous donors, one to two,
three or more), with the seed recorded before any scoring. This gives **110
development and 36 reserved networks** with all three donor regimes present in
both. The reserved panel was opened once, after the analysis was frozen, and
the model was not retuned.

### 4.3 Endpoints and their natural scale

Five derived statistics are scored: the hottest consecutive 30-day mean
(primary), the hottest consecutive 7-day mean (the window used by much
regulatory practice), the annual mean, the coldest consecutive 30-day mean, and
the amplitude between the warm and cold extremes.

A tolerance in degrees means nothing without a scale, so each endpoint is
scored against a tolerance equal to the same fraction — 0.47 — of *its own*
interannual standard deviation at the same stations. For the annual peak that
scale is **1.06 °C** (median 1.02, interquartile range 0.72–1.34, n = 457
stations), giving a primary tolerance of **0.50 °C**; the annual mean is
0.55 °C, the cold extreme 0.80 °C and the amplitude 1.36 °C. The fraction is
swept at 0.25, 0.47 and 1.0 and no conclusion about which axis wins is claimed
unless it is invariant across the sweep.

The reference series carries instrument error of roughly 0.1–0.2 °C, so the
primary tolerance is about three times sensor accuracy. Section 5.2 does not
assume this is comfortable but perturbs the reference by 0.15 °C and repeats
the analysis.

### 4.4 Outage design

A case is one station-year under one outage realization. Two arms are used and
reported separately, because they are not one population. The **empirical** arm
samples real outage runs — length and start month — from the same network's own
records and transplants them onto fully observed years, so that operational
numbers reflect what agencies experience. The **stratified** arm crosses outage
length {14, 30, 60, 90, 120, 180, 270 days} with the overlap between the outage
and the station's climatological peak window, so that the response surface is
estimable rather than accidental. The design yields **51,524 cases**, 40,704
development and 10,820 reserved.

Peak-window overlap is computed from the station's other years and is therefore
visible when the repair decision is made. Outages are placed inside one
calendar year; failures that straddle New Year damage two annual statistics
while hiding neither warm season, and the design cannot represent that case.

### 4.5 Estimators

Every case is completed by each supported estimator: the statistic computed
from recorded days alone (current practice), a day-of-year median climatology,
a smoothed climatology, linear interpolation where both flanks exist, ridge
regression on the visible subset of synchronous donors, and an air-driven ridge
where reanalysis forcing exists. Estimators are fit leave-one-year-out within
the station, which is what offline archive repair permits; §5.7 repeats the
study under the stricter protocol in which only prior years are available.
Support is declared per method: donor regression does not read a flanking
observation, so requiring one would discard usable cases, and absent donor
columns are never imputed but the model is refit on the visible subset.

### 4.6 The screening rule

Figure 2 is the architecture. For each case the screen predicts an upper bound on the absolute error each
supported estimator would produce, selects the estimator with the smallest
bound, and emits a conformal interval on the statistic together with an
admission decision at an analyst-chosen tolerance. Its inputs are outage
geometry, peak-window overlap, warm-season coverage, the margin by which the
observed days already constrain the annual maximum, donor count and coverage
and training-period deseasonalised correlation, and station history. No input
may read a day the outage hides, and that restriction is enforced in code.

Calibration is split conformal with two properties that matter. It is
*selection-conditional* — the bound is calibrated after the estimator is
chosen, because taking the smallest of several bounds is a winner's curse that
per-estimator calibration cannot see — and *multiplicative*, because the error
scale spans an order of magnitude between an outage that misses the peak window
and one that covers it. Fitting, calibration and test networks are always
disjoint.

### 4.7 Action-space screening before rule fitting

Before any rule was fit we measured, on development cases, how much a rule with
perfect foresight could win inside each candidate action space, and compared it
with the margin the reserved panel can resolve. Two natural framings of this
problem — adopt or reject a fixed reconstruction, and choose among
reconstruction methods — have ceilings of +0.038 °C and +0.080 °C against a
threshold of 0.136 °C, and were not pursued. Retain-or-exclude clears its gate
by a factor of five and is the action space studied here. We recommend the
check as standard practice: a decision experiment whose ceiling is below its
own resolvable margin cannot produce evidence in either direction, and running
one consumes a reserved panel for nothing.

### 4.8 Inference

Every interval resamples whole networks, because station-years within a network
are not independent and reusing a station-year under several outage
realizations does not create independent observations. The pre-registered
primary criterion, frozen before the reserved panel was opened, is that at the
retention of the matched length rule the screen must reduce the
consequential-error rate by at least five percentage points with a
network-clustered interval excluding zero. Precision was computed in advance:
the reserved panel resolves 1.44 points, so the declared effect is 3.5 times
the resolution.

Where several endpoints are compared, the direction of each contrast was
predicted in advance from the form of the statistic, which is the defence
against multiplicity; the comparisons are confirmatory of a stated prediction
rather than a search for the favourable cell.

## 5. Results

Results are organised by research question. RQ0 asks whether the problem
exists, RQ1 tests the central hypothesis, RQ2 asks which rivers are hard, RQ3
to RQ6 evaluate acting on the answer, and RQ7 to RQ8 establish where it fails.

### 5.1 RQ0 — Does the problem exist, and how large is it?

Before proposing any rule, we measure what current practice costs. On
development cases, computing the annual peak from recorded days alone — the
default once a station-year passes a completeness screen — gives a mean
absolute error of **1.305 °C, or 1.23 interannual standard deviations** of the
quantity being measured, with **24.9%** of station-years wrong by more than
1.0 °C. Substituting a day-of-year climatology over the outage gives 0.402 °C;
the best supported reconstruction gives 0.242 °C; an oracle over the estimator
set gives 0.165 °C.

The problem is therefore real and large, and its largest single component is
not any decision rule: it is that thermal statistics are routinely computed on
records with holes in them. Everything that follows concerns the smaller,
second-order question of which of the remaining station-years to trust.

### 5.2 RQ1 — Which outage property governs which metric?

Table 1 reports, for each endpoint, how well each candidate axis discriminates
a consequential error, with the contrast between the best timing axis and
outage length carried by a network-clustered bootstrap (Figure 8a).

**Table 1.** Discrimination of a consequential error by axis, development
cases, each endpoint at 0.47 of its own interannual standard deviation.

| endpoint | peak-window overlap | warm-season coverage | outage length | AUC(timing) − AUC(length), 95% CI | governing axis |
|---|---:|---:|---:|---:|---|
| hottest 7-day mean | 0.823 | 0.824 | 0.752 | **+0.072 (0.063, 0.096)** | timing |
| hottest 30-day mean | 0.819 | 0.820 | 0.750 | **+0.070 (0.061, 0.098)** | timing |
| amplitude | 0.758 | 0.792 | 0.768 | **+0.024 (0.015, 0.037)** | timing |
| annual mean | 0.672 | 0.818 | **0.845** | **−0.027 (−0.036, −0.018)** | length |
| coldest 30-day mean | **0.447** | 0.619 | **0.803** | **−0.184 (−0.228, −0.156)** | length |

All five intervals exclude zero and the ordering reverses between the two
regimes, as H1 predicts. The ordering is also invariant to where the tolerance
is drawn: at 0.25, 0.47 and 1.0 interannual standard deviations the winning
axis is unchanged for every endpoint. The direction of each contrast was
predicted in advance from the form of the statistic, which is the defence
against having run twelve comparisons.

Two features of Table 1 deserve emphasis. The **seven-day peak has the largest
timing advantage of any endpoint**, which the mechanism predicted before it was
measured: a shorter extreme is more localised in time, so whether its window
survived matters more. And **peak-window overlap has an AUC of 0.447 for the
cold extreme** — hiding the summer peak carries no useful information about the
winter minimum, exactly as it should not.

The mechanism is measurable, not merely plausible. Binning development cases on
both covariates simultaneously and measuring the growth of error along each
axis with the other averaged out:

| endpoint | error ratio, most days missing vs fewest | error ratio, peak window hidden vs untouched |
|---|---:|---:|
| hottest 30-day mean | 3.5× | **9.6×** |
| annual mean | **10.2×** | 1.5× |

The two ratios swap by roughly an order of magnitude in each direction. This is
the strongest single piece of evidence for H1 and it is a direct measurement of
the stated mechanism rather than an inference from discrimination.

For the peak, once timing is in the model, outage length adds nothing
measurable: its permutation importance is **−0.004** against 0.194 for peak
overlap (Figure 4c), and nested feature sets grouped by network rise from AUC
0.742 with length alone to 0.845 adding timing, 0.858 adding the observed-peak
margin and 0.884 adding donor quality (Figure 4b). Two qualifications belong
with that. Length is not irrelevant: holding peak overlap at zero, the
consequential-error rate still rises from 0.6% at 1–30 days to 8.7% at 121–200
days. And in a linear score that already contains warm-season coverage the
length term takes a small negative weight, which is collinearity — the two
correlate at −0.86 — and not evidence that longer outages are safer.

Donor information enters through quality rather than quantity. Halving the
donor set by training-period correlation while holding the count fixed costs
**+0.082 °C** (95% interval 0.061–0.112). Replacing donor anomalies with
phase-shuffled surrogates while preserving each donor's seasonal cycle costs
**+0.234 °C** (0.164–0.288), so donors supply synchronous anomaly information
and not merely a seasonal shape (Figure 7b).

### 5.3 RQ2 — Which rivers are hard?

The mechanism above is a property of estimators and estimands and would hold
for any time series. This section asks the hydrological question. For the 140
United States stations matched to GAGES-II across 57 networks, we regressed
donor synchrony and completed-year error on basin attributes, with the expected
direction of each effect declared before the regressions were run (Figure 9).

**Topography, not geology, predicts difficulty.** Site elevation and basin
slope both reduce donor synchrony (Spearman ρ = **−0.29**, 95% CI −0.46 to
−0.08, and ρ = **−0.31**, −0.51 to −0.07), and site elevation raises both
completed-year error (ρ = +0.24, 0.06 to 0.43) and the consequential-error rate
(ρ = +0.25, 0.08 to 0.43). Mountain stations are harder because their
neighbours are less exchangeable: steeper lapse rates, snowmelt timing, aspect
and shading make two nearby gauges less alike.

**The groundwater prediction from the literature is not reproduced, and the
reason is instructive.** Johnson et al. (2021) report that filling can harm
groundwater-influenced sites, which predicts that a high baseflow index implies
larger completed-year error. Baseflow index does reduce donor synchrony in the
predicted direction, from 0.70 in the lowest tertile to 0.59 in the highest,
although the rank correlation interval includes zero (ρ = −0.19, −0.42 to
0.10). But the error moves the *other* way: high-baseflow stations are
**−0.043 °C** easier than low-baseflow stations (95% CI −0.081 to −0.004).

Two opposing effects explain it, and the second is larger. Groundwater
contribution makes donors less informative, but it also damps the thermal
regime itself: across baseflow tertiles the mean annual peak falls from 22.7 °C
to 18.1 °C (ρ = **−0.47**, −0.60 to −0.26) and its interannual standard
deviation from 0.98 °C to 0.76 °C. A damped regime is a smaller and steadier
target, and that outweighs the loss of donor information (Figure 9c). We
therefore do not contradict the earlier observation so much as decompose it:
groundwater influence degrades the *information* available for reconstruction
while simultaneously reducing the *difficulty* of the quantity being
reconstructed.

**Regulation does not make station-years harder** for this endpoint: reference
and non-reference basins differ by +0.004 °C (95% CI −0.051 to +0.093).

**Catchment attributes explain a modest share of the variation** — a
standardised linear model reaches R² = 0.22 for donor synchrony and 0.13 for
completed-year error — and, critically, **no attribute predicts how much the
screen gains**: every correlation between a basin attribute and the per-station
screening benefit has an interval containing zero. The screening problem is
therefore governed mainly by outage geometry rather than by catchment physics,
which is why basin attributes are reported here as an explanation and are
deliberately excluded from the screening rule, whose inputs must be available
at every agency.

### 5.4 RQ3 — Does screening on the governing axis pay?

At 70% retention on development cases, the share of retained station-years with
a peak error above 0.5 °C is 2.9% for the calibrated screen, 5.6% for a rule on
peak overlap alone, 9.2% for the outage-length rule and 15.0% for random
retention (Figure 5a). On the **36 reserved networks, opened once with the
frozen rule and no retuning**, the screen gives 2.5% against 9.7% for the
length rule (Figure 5b): a contrast of **−7.13 points, 95% network-clustered interval
−8.97 to −5.36**, against a pre-registered effect of five points and a
resolvable margin of 1.44 points. Both pre-registered conditions are met, in
every donor regime (none −6.6, sparse −6.7, rich −7.2, all excluding zero).

Placed at the retention implied by the published twenty-week guideline with
imputation (140 days, 85.1% on the reserved panel), the length rule leaves 11.3%
and the screen 6.9%; at the seven-week unfilled limit (49 days, 49.2%
retention) the figures are 5.2% and 0.3%.

**Table 2.** Reserved panel at 70% retention, across tolerances.

| screen | > 0.25 °C | > 0.5 °C | > 1.0 °C | underestimate > 1 °C |
|---|---:|---:|---:|---:|
| outage-length rule | 17.2% | 9.7% | 3.4% | **2.0%** |
| peak-overlap rule | 9.2% | 4.2% | 1.2% | 0.7% |
| calibrated screen | 7.1% | 2.5% | 0.4% | **0.3%** |
| random | 23.9% | 14.4% | 5.6% | 3.7% |

Understating a summer peak by more than a degree converts a thermally stressful
year into an unremarkable one. The screen reduces that rate sevenfold relative
to the incumbent.

The panel is unbalanced — one provider contributes 56 of the 110 development
networks — so the contrast was recomputed with each unit weighted equally. On
the reserved panel: case-equal −7.01, provider-equal −6.30, network-equal
−5.82, station-equal −5.54 points. Every weighting clears the declared five
points and every interval excludes zero. Across individual reserved networks
the median contrast is −5.0 points, **83% of networks favour the screen**, and
the worst is +2.8.

### 5.5 RQ3b — Was the incumbent handicapped?

A screening comparison can be rigged by pairing the incumbent with a weak
reconstruction. We paired the length rule with every reconstruction in the
study, including one nobody can deploy: an oracle selecting the best estimator
per case with hindsight.

**Table 3.** Reserved panel at 70% retention.

| screen | reconstruction | error rate above 0.5 °C |
|---|---|---:|
| length rule | information-conditioned policy (used throughout) | 9.36% |
| length rule | always donor ridge, else climatology | 9.56% |
| length rule | always smooth climatology | 15.39% |
| length rule | **oracle over methods, not deployable** | **4.19%** |
| calibrated screen | deployable estimators it selects itself | **2.53%** |

The screen beats the incumbent armed with a reconstruction nobody can run, and
the reconstruction paired with the incumbent throughout is the strongest of the
deployable options rather than the weakest.

### 5.6 RQ4 — What does each component contribute?

**Table 4.** Component ablation, development cases at 70% retention, each
variant re-run through the full out-of-fold pipeline.

| screen | error rate | points vs the length rule |
|---|---:|---:|
| outage-length rule (incumbent) | 9.24% | — |
| three-variable logistic regression | 5.53% | −3.71 |
| peak-overlap alone, no fitting at all | 5.62% | −3.62 |
| three-feature gradient boosting | 4.89% | −4.35 |
| geometry and timing only (8 features) | 4.86% | −4.38 |
| drop donor features | 3.78% | −5.46 |
| drop the observed-peak margin | 3.13% | −6.11 |
| full screen | 2.93% | −6.31 |
| full screen, screening only (no method choice) | 3.11% | −6.13 |

**Fifty-nine per cent of the benefit is available from a logistic regression on
three variables, and 57% from peak-window overlap with no fitting at all.**
Method selection contributes 0.2 points. The contribution of this paper is
therefore the axis, and the calibrated machinery is a refinement on it; we
report the simple rule as a deliverable rather than as an ablation. Fitted on
development networks and applied unchanged to the reserved panel,

    risk = logistic( −1.302 + 2.070 · peak_overlap
                            − 2.412 · warm_observed_fraction
                            − 0.00187 · longest_run_days )

gives 4.2% against the length rule's 9.6% at 70% retention, a contrast of
**−5.44 points (−6.85, −3.96)**, and cuts severe underestimation of the peak
from 1.9% to 0.6%. Three quantities an analyst can compute in a spreadsheet
clear the effect size this study pre-registered for its full method.

One interpretable piece of the remainder: the screen selects linear
interpolation for 25.0% of reserved cases against 5.7% under a
presence-conditioned rule, and interpolation carries the lowest error of any
choice when selected (0.10 °C). For short outages with both flanks observed,
interpolation beats donor regression.

### 5.7 RQ5 — Where is the advantage absent?

The pre-registered test was run on the pooled case set, which mixes two outage
arms whose base rates differ by an order of magnitude. They must be reported
apart.

**Table 5.** Decomposition by outage arm.

| panel | arm | cases | base rate, retain all | length rule at 70% | screen at 70% | contrast (95% CI) |
|---|---|---:|---:|---:|---:|---:|
| development | empirical | 14,995 | 7.4% | 2.52% | 0.38% | −2.13 (−3.45, −1.26) |
| development | stratified | 25,709 | 19.3% | 14.58% | 6.17% | −8.39 (−9.25, −7.47) |
| reserved | empirical | 4,041 | 4.2% | 0.74% | 0.11% | **−0.71 (−2.36, +0.05)** |
| reserved | stratified | 6,779 | 20.8% | 16.59% | 7.78% | −8.68 (−10.46, −6.51) |

The declared five-point effect is met on the pooled and stratified populations
and **not** on the empirical arm, where the reserved interval includes zero.
Under the outage geometry these networks actually experience — mostly short
runs spread across the year — little needs screening because little goes wrong:
4.2% of reserved empirical cases exceed the tolerance with no screening at all,
and the screen's own operating point there retains 90% of station-years. The
screen earns its place in the regime that motivates screening, long outages
overlapping the warm season, and there the gain is large and unambiguous.

### 5.8 RQ6 — Is the uncertainty honest?

On the reserved networks the nominal 90% interval covers **90.9%** of cases
marginally, within the pre-declared band of 0.87–0.93, and 86.3% to 94.9%
within every pre-declared stratum (Figure 6a). Median widths adapt from 0.06 °C when the
peak window is untouched to 1.87 °C when most of it is hidden (Figure 6b).

Those strata pool across networks, and conformal validity assumes an
exchangeability that fails between river networks. Coverage inside individual
reserved networks has mean 0.904 and median 0.913 but a minimum of **0.778**,
with five of 36 networks below 0.85. The pooled interval is therefore an honest
statement about a population of networks and is **not** a guarantee at a single
new site. Calibrating on the per-network conformal quantiles fixes this, at a
price the analyst can choose.

**Table 6.** Calibration setting against site-level validity and interval width.

| calibration | marginal coverage | per-network minimum | networks below 0.85 | median width | error rate at 70% |
|---|---:|---:|---:|---:|---:|
| pooled | 0.909 | 0.778 | 13.9% | 0.54 °C | 2.53% |
| cluster, 0.7 level | 0.932 | 0.842 | 5.6% | 0.60 °C | 2.53% |
| cluster, 0.9 level | 0.964 | 0.852 | **0%** | 0.80 °C | 2.53% |

Site-level validity costs about a 1.5-fold widening and overshoots nominal
marginal coverage (Figure 6c). Critically, **the screening result is identical under every
calibration**, to four decimal places: the rank order the screen uses is a
monotone transform of the bound, so a change of scale cannot reorder it. A
reader who distrusts the intervals need not distrust the frontier.

### 5.9 RQ7 — What changes downstream?

**Per-year judgements.** On reserved networks the misclassification rate of a
20 °C exceedance is 6.86% when the statistic is computed on recorded days,
1.97% when every year is reconstructed and not screened, 1.53% under length
screening and **0.36%** under the screen. Because most station-years sit
nowhere near the threshold, we restrict the judgement to years where the call
is close.

**Table 7.** Exceedance misclassification, reserved panel.

| subset | observed days | reconstruct all | length-screened | screened |
|---|---:|---:|---:|---:|
| all retained | 6.86% | 1.97% | 1.53% | **0.36%** |
| truth within 1.0 °C of the threshold | 16.84% | 9.50% | 7.26% | **1.92%** |
| truth within 0.5 °C of the threshold | 19.10% | 13.12% | 10.24% | **3.38%** |

The advantage survives the restriction and is proportionally larger where the
call is hard — a 67% reduction against length screening within half a degree of
the threshold. The result is not an artefact of the threshold: swept from 14 °C
to 24 °C, the screen's misclassification stays between 0.18% and 0.37% while
the length rule stays between 0.84% and 1.53% (Figure 8c). The bias in the
count of years above 20 °C falls from −0.76 years per station under recorded
days and −0.32 under length screening to +0.06.

**Screening is not the only action the calibrated object supports, and for a
threshold judgement it is not the best one.** Discarding a station-year is a
blunt response to uncertainty about a single call. The alternative is to keep
every year and decline only the judgement the interval cannot support.

**Table 8.** Two action spaces on the reserved panel.

| policy | years judged | misclassification | missed exceedances |
|---|---:|---:|---:|
| screen at the 0.5 °C tolerance | 67.5% | 0.36% | 0.39% |
| abstain where the interval straddles the threshold | **92.7%** | 0.42% | 0.64% |
| both | 65.7% | **0.08%** | 0.12% |

Keeping 93% of station-years rather than 68% at essentially the same error rate
matters to anyone assembling a regional archive. The two action spaces answer
different questions — screening decides what enters an archive, abstention
decides what one judgement may say — and the same calibrated object serves
both.

**Multi-year trends.** Theil–Sen slopes of the annual peak have RMSE
0.143 °C yr⁻¹ on recorded days, 0.044 with reconstruction and no screening,
0.048 under length screening and 0.041 under the screen (Figure 7a shows the
per-year result the screen is claimed for). For decadal trends the
dominant gain is reconstructing at all rather than screening afterwards, and we
do not claim otherwise.

### 5.10 RQ8 — Does the result survive its assumptions?

**Instrument error in the reference.** Perturbing the reference series by
0.15 °C of normal noise — the upper end of logger accuracy — moves the
development contrast from 6.32 to 6.21 points and the reserved contrast from
7.06 to 6.67 points, and the mean absolute error from 0.2416 to 0.2418 °C
(Figure 8b). The conclusion is not inside the measurement error.

**Estimators that may see only prior years.** Under the stricter protocol in
which only years before the outage are available, the panel falls to 33,633
development cases on 3,337 station-years, reconstruction error rises from
0.242 °C to 0.270 °C, and the contrast moves from −6.35 (−7.12, −5.52) to
**−5.92 points (−6.72, −4.99)**, with coverage 0.906.

**Transfer across agencies.** Under leave-one-provider-out inside the
development pool, the contrast is negative and its interval excludes zero for
**all nine agencies**, ranging from −11.6 points (Finland) to −1.2
(Switzerland). Conformal coverage under provider transfer stays between 0.82
and 0.96.

## 6. Discussion

**What an agency should change.** Figure 10 is the procedure, end to end, for
an agency that wants to act on this. The immediate recommendation is not to adopt
a model. It is to change the axis. An agency that screens station-years for
warm-season extremes on maximum gap length should screen instead on how much of
the station's climatological peak window the outage hides, which is computable
from the station's own history with no additional data. On our reserved panel
that single substitution takes the consequential-error rate from 9.7% to 4.2%
at equal retention. The calibrated screen and its interval are worth adding
where an uncertainty statement is needed on the reported statistic, and the
three-variable rule is given explicitly for agencies that will not run code.
Equally, agencies should **keep** their length-based rules for annual means and
cold extremes, where our evidence says length is the better axis.

**Why the standing guidance saw an inconsistency.** Johnson et al. reported
that the timing of missing data affected thermal-signal estimates
inconsistently in space and time. Working across metrics that include the
annual mean, phase and amplitude, a mixture of two opposite regimes is exactly
what would look inconsistent. Our result does not contradict that observation;
it decomposes it, and it predicts in advance which metrics should show a timing
effect and which should not.

**Implications for monitoring design.** If what matters for a summer extreme is
whether the peak window survived, then maintenance scheduling is a design
variable, not an operational detail. A network that services loggers in late
spring converts recoverable outages into unrecoverable ones; one that services
them in autumn does the reverse. The same logic applies to redundancy: our
donor experiments show that a second station is worth having in proportion to
its synchronous anomaly correlation with the target, not merely its existence,
and our catchment analysis shows that synchrony is lowest at high-elevation,
steep sites, which is where a redundant gauge buys the most.

**On uncertainty for derived statistics.** The field reports daily prediction
skill and almost never reports uncertainty on the annual statistic that is
actually used. The two are not interchangeable for an extreme: a model with
excellent daily RMSE can be badly wrong about a 30-day maximum if its errors
are correlated within the peak window. Calibrated intervals on the derived
statistic are cheap to produce once the problem is posed this way, and §5.8
shows they can be made honest either for a population of sites or for a single
site, with the price stated.

## 7. Limitations

The absolute benefit depends on the outage regime; under the geometry these
networks actually experience the reserved-panel interval includes zero (§5.7).
The pooled interval is not valid at a single new site unless the cluster
calibration is used, and that costs width (§5.8). The screen uses a station's
own history, so nothing here applies to ungauged sites. Outages that straddle a
calendar year are outside the design, and the dichotomy predicts they should be
nearly harmless for both peaks and costly for both means — a prediction we have
not tested. Fully observed calendar years are, by selection, the
better-instrumented part of an archive. Catchment attribution is restricted to
the United States subset where GAGES-II applies, and explains a modest share of
the variation. The primary tolerance is a modelling choice at 0.47 interannual
standard deviations rather than an ecological threshold, which is why the
frontier is reported at 0.25, 0.5 and 1.0 °C and the exceedance threshold is
swept from 14 °C to 24 °C.

## 8. Conclusion

A data gap has more than one property, and which property matters depends on
what is being computed from the record. For warm-season extremes — the
statistics used in cold-water habitat assessment — the governing property is
whether the outage hid the station's climatological peak window; for annual
means and cold extremes it is how many days went missing. The two regimes
reverse, the reversal is predictable in advance from the form of the statistic,
and it is measurable as an order-of-magnitude swap in how error grows along
each axis.

Acting on it is cheap. Screening on the governing axis, pre-registered and
scored once on 36 networks reserved before any analysis, reduces the
consequential-error rate by 7.1 percentage points relative to published
guidance at equal retention, reduces severe underestimation of the summer peak
sevenfold, and removes the bias that length-based screening imparts to counts
of threshold exceedance. Most of that is obtained by three variables in a
logistic regression. The recommendation to practice is correspondingly simple:
keep length-based completeness rules for averages, and replace them with
timing-based rules for extremes.

## Figures

Figures 1 to 3 and Figure 10 are schematics, drawn in draw.io; their editable
sources are in `figures/v17/drawio/` and the PDFs are exported from those
sources by `make figures-drawio`. Figures 4 to 9 are produced from the analysis
artifacts by `scripts/188_v17_figures.py` and `scripts/204_v17_figures_q1.py`.

| # | file | what it shows |
|---|---|---|
| 1 | `figures/v17/f0_problem_frame.pdf` | Why one completeness threshold cannot serve two estimands. The same station-year and outage mask feed an annual mean and a hottest 30-day mean; the two estimands have different supports, and therefore different governing axes. The incumbent rule conditions on outage size alone, which matches the support of the mean and ignores the support of the extreme. Panels quote the measured error gradients: 10.2× along missing days and 1.5× along peak-window overlap for the mean, 3.5× and 9.6× for the peak. |
| 2 | `figures/v17/f1_system_architecture.pdf` | The screening system. Left: the features visible at decision time, grouped by what they measure, under an information barrier that forbids any feature from reading a day the outage hides. Centre: the estimator library with per-case support, the risk model, estimator selection, and the selection-conditional multiplicative conformal calibration. Bottom: the two action spaces the same calibrated object supports — admission and abstention. |
| 3 | `figures/v17/f2_experiment_design.pdf` | Study design and data flow, from nine providers to the single opening of the reserved panel, with the quality-control exclusions, the network-level stratified split, the §4.7 gate and the pre-registered freeze shown in the order they were executed. |
| 4 | `figures/v17/fig1_mechanism.pdf` | Mechanism: the length-by-overlap reversal (a), nested feature sets (b), permutation importance (c), and the endpoint dependence (d). |
| 5 | `figures/v17/fig2_frontier.pdf` | Retention–error frontier on development cases (a) and on the reserved panel (b). |
| 6 | `figures/v17/fig3_calibration.pdf` | Conformal coverage by stratum (a), interval width against peak-window overlap (b), and the price of site-level validity (c). |
| 7 | `figures/v17/fig4_consequence.pdf` | Downstream consequence: multi-year trend error (a) and the donor controls (b). |
| 8 | `figures/v17/fig5_robustness.pdf` | Clustered intervals on the axis contrasts (a), reference-noise perturbation (b), and the exceedance-threshold sweep (c). |
| 9 | `figures/v17/fig6_hydrology.pdf` | Catchment attribution on the United States subset: donor synchrony and completed-year error against basin attributes, and the decomposition of the baseflow effect (c). |
| 10 | `figures/v17/f4_deployment_workflow.pdf` | What an agency does with the result: which endpoint, where the peak window comes from, the three numbers, the deployable rule, the representativeness guardrail, and what the substitution buys on networks never used for fitting. |

## References

Beaufort, A., Diamond, J. S., Sauquet, E., and Moatar, F. (2022). Spatial
extrapolation of stream thermal peaks using heterogeneous time series at a
national scale. *Hydrology and Earth System Sciences*, 26(13), 3477–3495.
https://doi.org/10.5194/hess-26-3477-2022

Corona, C. R., and Hogue, T. S. (2025). Machine learning in stream and river
water temperature modeling: a review and metrics for evaluation. *Hydrology and
Earth System Sciences*, 29(12), 2521–2549.
https://doi.org/10.5194/hess-29-2521-2025

Falcone, J. A. (2011). *GAGES-II: Geospatial Attributes of Gages for Evaluating
Streamflow*. U.S. Geological Survey.
https://doi.org/10.3133/70046617

Johnson, Z. C., Johnson, B. G., Briggs, M. A., Snyder, C. D., Hitt, N. P., and
Devine, W. D. (2021). Heed the data gap: Guidelines for using incomplete
datasets in annual stream temperature analyses. *Ecological Indicators*, 122,
107229. https://doi.org/10.1016/j.ecolind.2020.107229

Li, H., Deng, X., and Smith, E. (2017). Missing data imputation for paired
stream and air temperature sensor data. *Environmetrics*, 28(2), e2426.
https://doi.org/10.1002/env.2426

Zaoui, A., Denis, C., and Hebiri, M. (2020). Regression with reject option and
application to kNN. *Advances in Neural Information Processing Systems*, 33.

## Data and code availability

Daily temperature records are from the nine public providers listed in the
supporting information. Basin characteristics are from GAGES-II (Falcone,
2011). All analysis code, artifacts, figures and the frozen pre-registration
are in the accompanying repository; `results/v17_fitness/evidence_ledger.csv`
maps each claim to the script, artifact and digest behind it, and every table
in this article is re-derived from those artifacts by an automated audit that
runs in the test suite.
