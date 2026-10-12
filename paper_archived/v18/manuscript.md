# Measure missingness where the statistic lives: a continuous screening law for gap-affected stream-temperature records

<!-- numbers:start -->
```json
{
  "networks": 146,
  "stations": 457,
  "complete_station_years": 5114,
  "incomplete_station_years": 2422,
  "cases": 51524,
  "development_cases": 40704,
  "reserved_cases": 10820,
  "reserved_networks": 36,
  "crossover_support_width_days": 91.05,
  "certificate_at_70_reserved": 0.0253,
  "length_rule_at_70_reserved": 0.0966,
  "confirmation_contrast_points": -7.1297,
  "marginal_coverage": 0.9085,
  "archive_disagreement_pct": 15.07,
  "archive_admitted_by_length_rejected_by_timing": 207,
  "archive_wholly_hidden_peak_admitted_at_140d": 17,
  "spring_calendar_penalty_points": 4.43,
  "autumn_calendar_saving_points": 3.88,
  "air_support_development_pct": 98.64,
  "balancing_price_points": 0.31
}
```
<!-- numbers:end -->

## Key points

- Whether a data gap matters depends on how much the target statistic depends
  on the days it hides. Sweeping the width of the statistic's support from one
  day to a full year, the governing axis turns over smoothly from *when* the
  outage fell to *how much* of the record it removed, and the crossover is at a
  support of **91 days**.
- The rule that follows is deployable and it changes real decisions: on 2,422
  genuinely incomplete station-years from nine agencies, screening on the
  station's climatological peak window rather than on gap length reverses the
  admission decision for **15.1%** of them, and removes the 17 station-years
  that published completeness guidance admits with the peak window entirely
  unobserved.
- Screening is not the only lever and not the largest. Real outages of three
  months or more begin in autumn and winter, which protects the summer peak by
  accident; moving maintenance into spring would cost **4.4 percentage points**
  of consequential error and moving it into autumn would save **3.9**, against
  a screening gain of 6.3.

## Abstract

Thermal archives are screened before use, almost always by a threshold on
record completeness: a minimum share of the year, or a maximum consecutive gap.
Both thresholds measure the *size* of an outage, and both are applied to
whichever statistic an analyst happens to want. We show that the relevant
quantity is neither the size nor the timing of an outage as such, but the share
of the target statistic's own support that the outage hides, and that the
familiar contrast between "timing" and "length" is the two ends of one
continuous scale. On 5,114 fully observed river station-years from 146 networks
and nine agencies, with 51,524 outage realizations, we sweep the support of the
estimand from a single day to the whole year: the advantage of a peak-window
axis over a whole-year completeness axis decays from +0.074 AUC and crosses zero
at a support of 91 days, after which the completeness axis wins by up to 0.173.
The same law reproduces, on the three sine-fit parameters used by the standing
guidance, the pattern that guidance reported as inconsistent. Because a
statistic's support has to be located before it can be conditioned on, and its
location wanders between years by a median of 7 to 17 days, the conditioning set
that performs best is the support *dilated* by that wander: one climatological
window of 60 to 90 days is near-optimal for every endpoint from the annual
maximum to the half-year mean. Acting on the law, a pre-registered screen scored
once on 36 reserved networks cuts the consequential-error rate from 9.7% to 2.5%
at equal retention. We then take the rule to the part of the archive the study
cannot score: on 2,422 real incomplete station-years it reverses the admission
decision for 15.1%, and the published guideline it replaces admits 17
station-years whose annual peak was never observed. Two boundaries are reported
as prominently: under the outage geometry these networks actually experience the
screening gain is not resolvable, because real long outages begin in autumn; and
a screen that selects on difficulty selects against high-elevation, donor-poor
catchments, which costs 0.31 points of error to correct and should be corrected.

## 1. Introduction

Stream temperature is measured to answer questions about thermal regime: was
this summer stressful for cold-water fish, is the annual peak rising, how many
years exceeded a criterion. Those questions are answered from derived statistics
computed on a completed calendar year, and the records they are computed from
have holes in them. Loggers fail, are buried by ice, are lost to floods, or are
simply not visited. Before a station-year enters an analysis, an analyst must
decide whether its statistic can be trusted.

That decision is made today with a completeness rule, and the rules in use are
of two kinds. Agency monitoring standards specify what must be present:
Mauger et al. (2015), writing minimum standards for a state whose records feed
regional analyses, require a minimum sampling duration of one calendar month
and recommend a deployment period of 1 June to 31 August "to capture the thermal
maxima". Published quantitative guidance instead constrains what may be absent:
Johnson et al. (2021) report that "datasets with less than seven weeks of
consecutively missing data enabled estimation of all annual signal parameters
with reasonable accuracy" and that "imputation of missing data expanded this
range to approximately 20 weeks". Analysts then apply thresholds of this second
kind to whatever statistic they want. Mauger et al. (2017), for example, retain
a site-year for a mean July temperature only "when at least 90% of the days were
captured", and then report the maximum weekly maximum temperature from the same
records. Neither kind of rule has been tested against an alternative on a large
panel where the truth is known.

Two things are worth saying plainly about that guidance before we depart from
it. Johnson et al. estimate a *sine-fit* mean, phase and amplitude; they do not
compute a hottest 30-day mean and they make no claim about warm-season extremes.
And the Alaska standards already condition on season rather than on size, which
is closer to what we will argue for than a completeness threshold is. The target
of this paper is therefore not the guidance but the habit of carrying a
completeness threshold across to an estimand it was not derived for.

**The estimands do not depend on the record in the same way.** An annual mean is
a sum over days: removing *k* days removes *k* terms and it matters little
which. A hottest 30-day mean is an extreme living in a specific window: if the
outage misses that window the statistic is recoverable almost exactly however
long the outage is, and if the outage covers it the statistic must be inferred
however short the outage is. Stated that way the contrast looks like a dichotomy
between timing and length, and that is how we first reported it. It is not one.
Both statements are instances of a single quantity — the share of the estimand's
own support that the outage hides — and the apparent dichotomy is what that
quantity looks like when you evaluate it at a 30-day support and at a 365-day
support and nowhere in between.

**The insight of this paper is one sentence: a record-screening rule should
condition on the share of the target statistic's support that the outage hides,
and because that support is a property of the statistic rather than of the
record, the governing axis moves continuously with the statistic's form.**
Figure 1 states the argument; Figure 5a measures it. Sweeping the hottest-*k*-day
mean from *k* = 1 to *k* = 365 traces the whole scale, and the crossover between
the two regimes is a number we can report: 91 days.

Two consequences run through the rest of the paper. The first is practical: a
support has to be *located* before it can be conditioned on, and a station's
hottest window moves between years. Conditioning on the estimand's own support
is therefore not optimal for a narrow estimand; conditioning on that support
dilated by the year-to-year wander of its location is, and one 60-to-90-day
window serves every endpoint we examined. The second is that screening is not
the only lever available, and on our panel it is not the largest one: when real
outages happen turns out to matter about as much as which of them are screened
out.

Existing work cannot settle this, for structural rather than incidental reasons.
Guidance measures tolerance along one axis, so it cannot compare axes.
Gap-filling studies optimise the accuracy of the interpolated series rather than
the admissibility of the completed year (Mohseni et al., 1998; Li et al., 2017).
Beaufort et al. (2022) come closest: they gap-fill incomplete summer records
with air-temperature regressions precisely so that a thermal peak can be
computed, and they use the same statistic we do — the mean of the thirty hottest
consecutive days — validating the filling on fully monitored reference sites. But
their object is spatial extrapolation across 105,800 reaches; the filling is a
fixed preprocessing treatment applied to every record alike, and no station-year
is ever declined. Large-sample thermal databases (Isaak et al., 2017) and the
machine-learning stream-temperature literature — 57 studies between 2020 and
2024 by the count of Corona and Hogue (2025) — optimise prediction skill at
daily or reach scale and rarely propagate to a derived annual statistic, let
alone to an admission decision. What is common to all of them is that the
screening decision is never conditioned on what the target statistic actually
depends on.

Our contributions are at five levels.

1. **A law with a measured parameter.** The share of the estimand's support that
   an outage hides governs the error of the reported statistic; the familiar
   timing-versus-length contrast is its behaviour at the two ends of a scale,
   and the crossover sits at a support width of 91 days.
2. **A correction to the law that makes it deployable.** The support must be
   dilated by the year-to-year wander of its own location, which we measure; one
   60-to-90-day climatological window is near-optimal for every endpoint from
   the annual maximum to the half-year mean.
3. **An explanation of the standing guidance's own anomaly, on its own
   estimands.** Reproducing Johnson et al.'s sine-fit mean, phase and amplitude
   on our panel, the three have three different supports, and a timing effect
   appears for one and not the others — which is what "inconsistent in space and
   time" looks like from inside.
4. **A rule taken to the records it is for.** Pre-registered, scored once on 36
   reserved networks, and then applied to 2,422 genuinely incomplete
   station-years that carry no truth and have never been decided before.
5. **Two boundaries stated as prominently as the result.** The operational gain
   is regime-dependent and is not resolvable under the outage geometry these
   networks currently experience, and the reason is a finding in itself; and a
   screen that selects on difficulty selects against mountain catchments unless
   it is stratified, which we price.

## 2. Related work: a map of what is being optimised

The literature this paper intervenes in is not one conversation but five, and
they differ in what they optimise, on what unit they decide, and along which
axis they condition.

| body of work | optimises | decision unit | conditioning axis | reports uncertainty on the derived metric |
|---|---|---|---|---|
| record-completeness guidance (Johnson et al., 2021) | tolerable amount of missing data | station-year | outage size | no |
| agency collection standards (Mauger et al., 2015) | comparability across a monitoring programme | deployment | season and duration | no |
| gap filling and record extension (Mohseni et al., 1998; Li et al., 2017) | accuracy of the filled series | day | air temperature, donors | rarely |
| thermal-peak reconstruction and extrapolation (Beaufort et al., 2022) | spatial coverage of the thermal peak | reach | air-temperature regression, applied uniformly | validation against reference sites, not per case |
| large-sample thermal databases and models (Isaak et al., 2017; Corona and Hogue, 2025) | prediction skill | day or reach | meteorology, catchment attributes | occasionally, at daily scale |
| reject-option and selective prediction (Geifman and El-Yaniv, 2017; Zaoui et al., 2020) | error rate at a fixed rejection rate | case | model confidence | as a rejection rate, not in physical units |
| **this work** | **error of the derived metric among retained station-years** | **station-year** | **the share of the estimand's support the outage hides** | **yes, as a calibrated interval in °C** |

Four consequences follow from the map. First, no existing line compares
screening axes, because each fixes one. Second, uncertainty on the *derived*
statistic — the number a manager reads — is essentially unreported; daily skill
is reported instead, and the two are not interchangeable for an extreme. Third,
the selective-prediction literature supplies decision machinery whose control
variable is a rejection rate, whereas an analyst needs a tolerance in degrees on
the quantity they report. Fourth, and least often said, the missing-data
literature already contains the object we need: the influence function of an
estimator (Hampel, 1974) says exactly how much each observation moves the
estimate, and whether missingness is ignorable depends on the mechanism that
produced it (Rubin, 1976). What has not been done is to use either as a
screening rule for archived environmental records. This paper occupies the row
that is otherwise empty.

## 3. Problem formulation

Let a station-year be a sequence \(y = (y_1, \dots, y_T)\) of daily mean water
temperatures, \(T \in \{365, 366\}\), and let \(q(\cdot)\) be the derived
statistic of interest — here the hottest consecutive *k*-day mean,
\(q_k(y) = \max_{t} \frac{1}{k}\sum_{i=t}^{t+k-1} y_i\), which is the annual
maximum at \(k = 1\) and the annual mean at \(k = T\), together with the sine-fit
mean, phase and amplitude as alternatives.

An outage is a binary mask \(m \in \{0,1\}^T\); the analyst observes
\(y_{\bar m}\), the days where \(m_t = 0\). A *reconstruction* \(\hat y = R(y_{\bar
m}, Z)\) completes the year using side information \(Z\) — synchronous donor
stations, air temperature, the station's own history — and the analyst reports
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
*where* the outage fell relative to the part of the record \(q\) depends on.

### 3.1 The support of an estimand, and the hidden mass

Write \(w^q_t = \bigl|\partial q(y) / \partial y_t\bigr|\) for how much day *t*
moves the statistic — the discrete influence function of \(q\) at \(y\). The
**hidden mass** of an outage is the share of that influence the outage removes,

\[
h_q(m) \;=\; \frac{\sum_{t: m_t = 1} w^q_t}{\sum_t w^q_t}.
\]

For the annual mean every \(w_t\) is equal and \(h_q\) is the missing fraction.
For the hottest *k*-day mean the influence is concentrated on the *k* days that
achieve the maximum, and \(h_q\) is the share of that window the outage hides.
For the sine-fit parameters the weights are smooth functions of day of year: a
constant for the fitted mean, \(|\sin(\theta_t - \phi)|\) for the amplitude,
which is largest at both extremes, and \(|\cos(\theta_t - \phi)|\) for the phase,
which is largest a quarter-year from the peak. The central hypothesis is about
this quantity.

> **H1.** \(\Pr(L > \tau)\) is governed by \(h_q\). As the support of \(q\)
> widens from a single day to the whole year, the discriminating power of a
> fixed narrow window decays, crosses that of a whole-year completeness measure,
> and ends below it.

H1 is falsifiable in several places at once: it fails if a fixed peak window
discriminates equally well at every support width, if the crossing does not
occur, if the ordering is not stable in \(\tau\), or if \(h_q\) computed from the
influence function does not beat both hand-chosen axes where the influence is
not uniform.

### 3.2 Estimated supports, and why the right conditioning set is wider

\(h_q\) as written is not available at decision time, because the influence
weights depend on \(y\), including the days the outage hides. What an analyst
has is the *climatological* support: the window the station's other complete
years say the maximum should fall in. That is an estimate, and it has an error.
Writing \(\hat W_q\) for the estimated support and \(\sigma\) for the
year-to-year wander of its location, conditioning on \(\hat W_q\) alone
under-weights days that the true support may have reached. The correction is to
dilate: condition on \(\hat W_q\) widened by a multiple of \(\sigma\). §5.3
measures \(\sigma\) and the dilation that follows from it, and the result is that
a single window serves the whole family.

## 4. Data and study design

Figure 3 gives the design as a whole.

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
supplies no truth. Stations with fewer than four fully observed calendar years
are excluded because the estimator protocol requires them. The full denominator
with every exclusion and its count is in the supporting information.

This leaves **146 networks, 457 stations and 5,114 fully observed
station-years**. The same 457 stations contribute **2,422 further station-years
that are genuinely incomplete**. Those carry no truth and are therefore not part
of the scored population; §5.8 decides them anyway, because they are the
population a screening rule exists for.

Station coordinates were assembled for all 457 stations — from the providers'
own catalogues where the repository held them, from the USGS NWIS site service
for 195 United States gauges, and from ARSO's public station feed — and daily
2 m air temperature was joined from NASA POWER for the whole panel, 1981 to
2026. The v17 programme had air temperature for 2.3% of development cases; it
now has it for **98.6%**, which matters because air-temperature regression is
the reconstruction this field actually uses (§5.6).

For the United States subset, basin characteristics were joined from GAGES-II
(Falcone, 2011) on the eight-digit gauge identifier, matching **140 of 204**
eligible stations across 57 networks and supplying baseflow index, subsurface
contact time, drainage area, site elevation, basin slope and upstream dam
storage. These are used in §5.4 and §5.9 to ask which rivers are hard and which
rivers a screen keeps; they are deliberately *not* used inside the screening
rule, because they are unavailable for the other eight agencies.

### 4.2 Split

Networks — never station-years — were split into development and reserved,
stratified on provider and on donor regime (no synchronous donors, one to two,
three or more), with the seed recorded before any scoring. This gives **110
development and 36 reserved networks** with all three donor regimes present in
both. The reserved panel was opened once, after the analysis was frozen, and the
model was not retuned. Everything added after that opening — the support sweep,
the sine endpoints, the archive deployment, the representativeness analysis, the
air forcing — is reported on development cases, with reserved numbers shown only
where they are informative and labelled as no longer blind.

### 4.3 Endpoints and their natural scale

The primary endpoint is the hottest consecutive 30-day mean. For the support
sweep it is generalised to the hottest consecutive *k*-day mean for
*k* ∈ {1, 3, 7, 15, 30, 60, 90, 182, 365}; the coldest 30-day mean, the annual
amplitude, and the three sine-fit parameters are scored alongside.

A tolerance in degrees means nothing without a scale, so each endpoint is scored
against a tolerance equal to the same fraction — 0.47 — of *its own* interannual
standard deviation at the same stations. For the annual peak that scale is
**1.06 °C**, giving a primary tolerance of **0.50 °C**; the scale falls
monotonically with support width, from 1.18 °C at *k* = 1 to 0.55 °C at
*k* = 365. The fraction is swept at 0.25, 0.47 and 1.0 and no conclusion about
which axis wins is claimed unless it is invariant across the sweep.

The reference series carries instrument error of roughly 0.1–0.2 °C, so the
primary tolerance is about three times sensor accuracy; §5.10 perturbs the
reference by 0.15 °C and repeats the analysis.

### 4.4 Outage design

A case is one station-year under one outage realization. Two arms are used and
reported separately, because they are not one population. The **empirical** arm
samples real outage runs — length and start month — from the same network's own
records and transplants them onto fully observed years. The **stratified** arm
crosses outage length {14, 30, 60, 90, 120, 180, 270 days} with the overlap
between the outage and the station's climatological peak window, so that the
response surface is estimable rather than accidental. The design yields **51,524
cases**, 40,704 development and 10,820 reserved.

Both arms transplant a mask onto a year whose values were observed, which
assumes the mask is uninformative about the values it hides. §5.10 tests that
assumption against the archive rather than asserting it. Outages are placed
inside one calendar year; failures that straddle New Year damage two annual
statistics while hiding neither warm season, and the design cannot represent
that case.

### 4.5 Estimators

Every case is completed by each supported estimator: the statistic computed from
recorded days alone (current practice), a day-of-year median climatology, a
smoothed climatology, linear interpolation where both flanks exist, ridge
regression on the visible subset of synchronous donors, and an air-driven ridge
with lagged air temperature and harmonics. Estimators are fit leave-one-year-out
within the station, which is what offline archive repair permits; §5.10 repeats
the study under the stricter protocol in which only prior years are available.
Support is declared per method: donor regression does not read a flanking
observation, so requiring one would discard usable cases, and absent donor
columns are never imputed but the model is refit on the visible subset.

### 4.6 The screening rule

Figure 2 is the architecture. For each case the screen predicts an upper bound
on the absolute error each supported estimator would produce, selects the
estimator with the smallest bound, and emits a conformal interval on the
statistic together with an admission decision at an analyst-chosen tolerance.
Its inputs are outage geometry, hidden mass on the estimated support,
warm-season coverage, the margin by which the observed days already constrain
the annual maximum, donor count and coverage and training-period deseasonalised
correlation, and station history. No input may read a day the outage hides, and
that restriction is enforced in code.

Calibration is split conformal with two properties that matter. It is
*selection-conditional* — the bound is calibrated after the estimator is chosen,
because taking the smallest of several bounds is a winner's curse that
per-estimator calibration cannot see — and *multiplicative*, because the error
scale spans an order of magnitude between an outage that misses the peak window
and one that covers it. Fitting, calibration and test networks are always
disjoint.

### 4.7 Action-space screening before rule fitting

Before any rule was fit we measured, on development cases, how much a rule with
perfect foresight could win inside each candidate action space, and compared it
with the margin the reserved panel can resolve. Two natural framings of this
problem — adopt or reject a fixed reconstruction, and choose among reconstruction
methods — have ceilings of +0.038 °C and +0.080 °C against a threshold of
0.136 °C, and were not pursued. Retain-or-exclude clears its gate by a factor of
five and is the action space studied here. We recommend the check as standard
practice: a decision experiment whose ceiling is below its own resolvable margin
cannot produce evidence in either direction, and running one consumes a reserved
panel for nothing.

### 4.8 Inference

Every interval resamples whole networks, because station-years within a network
are not independent and reusing a station-year under several outage realizations
does not create independent observations. The pre-registered primary criterion,
frozen before the reserved panel was opened, is that at the retention of the
matched length rule the screen must reduce the consequential-error rate by at
least five percentage points with a network-clustered interval excluding zero.
Precision was computed in advance: the reserved panel resolves 1.44 points, so
the declared effect is 3.5 times the resolution.

Where several endpoints are compared, the direction of each contrast was
predicted in advance from the form of the statistic, which is the defence
against multiplicity; the comparisons are confirmatory of a stated prediction
rather than a search for the favourable cell. Three of the predictions declared
for this round were not met, and §5.3 and §5.5 report them as failures rather
than reshaping them into successes.

## 5. Results

Results are organised by research question. RQ0 asks whether the problem exists,
RQ1 tests the law and RQ1b tests it on the standing guidance's own estimands,
RQ2 asks which rivers are hard, RQ3 to RQ5 evaluate acting on the law, RQ6 takes
the rule to records that really have holes in them, and RQ7 to RQ9 establish
where it fails.

### 5.1 RQ0 — Does the problem exist, and how large is it?

Before proposing any rule, we measure what current practice costs. On
development cases, computing the annual peak from recorded days alone — the
default once a station-year passes a completeness screen — gives a mean absolute
error of **1.305 °C, or 1.23 interannual standard deviations** of the quantity
being measured, with **24.9%** of station-years wrong by more than 1.0 °C.
Substituting a day-of-year climatology over the outage gives 0.402 °C; the best
supported reconstruction gives 0.225 °C once air forcing is available for the
whole panel (0.242 °C without it); an oracle over the estimator set gives
0.130 °C.

The problem is therefore real and large, and its largest single component is not
any decision rule: it is that thermal statistics are routinely computed on
records with holes in them. Everything that follows concerns the smaller,
second-order question of which of the remaining station-years to trust.

### 5.2 RQ1 — What governs the error, and does it move with the estimand?

**The dichotomy first.** Table 1 reports, for five endpoints, how well each
candidate axis discriminates a consequential error, with the contrast between
the best timing axis and outage length carried by a network-clustered bootstrap.

**Table 1.** Discrimination of a consequential error by axis, development cases,
each endpoint at 0.47 of its own interannual standard deviation.

| endpoint | peak-window overlap | warm-season coverage | outage length | AUC(timing) − AUC(length), 95% CI | governing axis |
|---|---:|---:|---:|---:|---|
| hottest 7-day mean | 0.823 | 0.824 | 0.752 | **+0.072 (0.063, 0.096)** | timing |
| hottest 30-day mean | 0.819 | 0.820 | 0.750 | **+0.070 (0.061, 0.098)** | timing |
| amplitude | 0.758 | 0.792 | 0.768 | **+0.024 (0.015, 0.037)** | timing |
| annual mean | 0.672 | 0.818 | **0.845** | **−0.027 (−0.036, −0.018)** | length |
| coldest 30-day mean | **0.447** | 0.619 | **0.803** | **−0.184 (−0.228, −0.156)** | length |

All five intervals exclude zero and the ordering reverses, as the support
account predicts. The ordering is also invariant to where the tolerance is
drawn: at 0.25, 0.47 and 1.0 interannual standard deviations the winning axis is
unchanged for every endpoint.

Two features deserve emphasis. The **seven-day peak has the largest timing
advantage of any endpoint**, which the mechanism predicted before it was
measured: a shorter extreme is more localised in time. And **peak-window overlap
has an AUC of 0.447 for the cold extreme** — hiding the summer peak carries no
useful information about the winter minimum, exactly as it should not.

**Now the continuum.** Table 1 evaluates the law at two points and reads the gap
between them as a dichotomy. Sweeping the hottest-*k*-day mean from *k* = 1 to
*k* = 365 evaluates it everywhere (Figure 5a).

**Table 2.** The governing axis as a function of the support of the estimand,
development cases.

| support width *k* (days) | interannual SD (°C) | AUC, 30-day peak window | AUC, whole-year missing fraction | difference, 95% CI |
|---:|---:|---:|---:|---:|
| 1 | 1.18 | 0.825 | 0.751 | **+0.074 (0.053, 0.097)** |
| 3 | 1.17 | 0.824 | 0.746 | **+0.078 (0.055, 0.104)** |
| 7 | 1.16 | 0.823 | 0.746 | **+0.077 (0.053, 0.104)** |
| 15 | 1.12 | 0.821 | 0.743 | **+0.078 (0.053, 0.106)** |
| 30 | 1.08 | 0.819 | 0.744 | **+0.075 (0.049, 0.104)** |
| 60 | 1.02 | 0.815 | 0.765 | **+0.050 (0.028, 0.078)** |
| 90 | 0.94 | 0.792 | 0.790 | +0.002 (−0.018, 0.027) |
| 182 | 0.74 | 0.728 | 0.823 | **−0.095 (−0.111, −0.077)** |
| 365 | 0.55 | 0.672 | 0.845 | **−0.173 (−0.192, −0.157)** |

The advantage of the fixed peak window is flat at about +0.075 AUC for every
estimand whose support is a month or less, decays through +0.050 at a two-month
support, and **crosses zero at a support width of 91 days**; beyond that the
whole-year completeness axis wins, by 0.095 AUC at a half-year support and 0.173
at the annual mean. Every interval excludes zero except the one at *k* = 90,
which is where the crossing is. There is no dichotomy to explain. There is one
scale with a measured crossover, and the two regimes the previous account named
are its ends.

**Is the mechanism a measurement?** Binning development cases on both covariates
simultaneously and measuring the growth of error along each axis with the other
averaged out:

| endpoint | error ratio, most days missing vs fewest | error ratio, peak window hidden vs untouched |
|---|---:|---:|
| hottest 30-day mean | 3.5× | **9.6×** |
| annual mean | **10.2×** | 1.5× |

The two ratios swap by roughly an order of magnitude in each direction. For the
peak, once timing is in the model, outage length adds nothing measurable: its
permutation importance is **−0.004** against 0.194 for peak overlap (Figure 4c),
and nested feature sets grouped by network rise from AUC 0.742 with length alone
to 0.845 adding timing, 0.858 adding the observed-peak margin and 0.884 adding
donor quality (Figure 4b). Two qualifications belong with that. Length is not
irrelevant: holding peak overlap at zero, the consequential-error rate still
rises from 0.6% at 1–30 days to 8.7% at 121–200 days. And in a linear score that
already contains warm-season coverage the length term takes a small negative
weight, which is collinearity — the two correlate at −0.86 — and not evidence
that longer outages are safer. That correlation is also why the previous
labelling was wrong: warm-season coverage is a *count of missing days restricted
to a window*, which is a length measure with a domain restriction, and it is the
domain restriction rather than the timing that does the work.

Donor information enters through quality rather than quantity. Halving the donor
set by training-period correlation while holding the count fixed costs
**+0.082 °C** (95% interval 0.061–0.112). Replacing donor anomalies with
phase-shuffled surrogates while preserving each donor's seasonal cycle costs
**+0.234 °C** (0.164–0.288), so donors supply synchronous anomaly information and
not merely a seasonal shape (Figure 11b).

### 5.3 RQ1b — Two predictions that failed, and what they buy

Two of the predictions declared for this round were not met. Both failures are
informative and both are reported here rather than in a supplement.

**A narrow estimand is best screened on a window wider than itself.** We
predicted that the axis restricted to the estimand's own support would be at
least as good as any hand-chosen axis at every *k*. It is not: for supports of
15 days or less the fixed 30-day peak window beats the estimand's own support,
by 0.064 AUC at *k* = 1. Table 3 gives the whole matrix of estimands against
conditioning windows and the reason.

**Table 3.** Which climatological window a screen should condition on,
development cases. The diagonal is the estimand's own support.

| estimand, hottest *k*-day mean | best conditioning window (days) | AUC there | AUC on its own support | gain from widening | year-to-year wander of the support's location (days) |
|---:|---:|---:|---:|---:|---:|
| 1 | 90 | 0.862 | 0.760 | +0.102 | 16.7 |
| 3 | 60 | 0.858 | 0.766 | +0.092 | 16.3 |
| 7 | 90 | 0.855 | 0.778 | +0.077 | 16.5 |
| 15 | 60 | 0.853 | 0.802 | +0.051 | 15.3 |
| 30 | 90 | 0.852 | 0.827 | +0.025 | 13.7 |
| 60 | 90 | 0.860 | 0.855 | +0.005 | 9.4 |
| 90 | 90 | 0.856 | 0.856 | 0 | 7.4 |
| 182 | 182 | 0.851 | 0.851 | 0 | 6.9 |
| 365 | 365 | 0.844 | 0.844 | 0 | — |

The gain from widening tracks the wander almost exactly: it is largest where the
climatological window is the worst estimate of where this year's window will
fall, and vanishes once the support is wide enough to contain its own location
error. A screening rule does not condition on the support; it conditions on the
support *dilated by the uncertainty in the support's location*, and a dilation of
roughly two location standard deviations on each side is what the data choose.
One practical consequence stands out: **AUC at the best conditioning window is
between 0.85 and 0.86 for every estimand from the annual maximum to the half-year
mean.** An agency needs one climatological window of 60 to 90 days, not one per
metric. It also means the screen deployed in §5.6, which conditions on a 30-day
window, is leaving 0.025 AUC on the table for its own endpoint.

**A hand-chosen transition window is not enough for a phase.** We predicted that
for the sine-fit phase — whose influence is largest a quarter-year from the peak
— two 61-day windows around the spring and autumn limbs would beat both peak
overlap and outage length. They beat peak overlap decisively (+0.249 AUC, 95% CI
0.231 to 0.270) and they do not beat outage length (0.831 against 0.836). The
phase's influence is spread over half the year in two broad lobes, so a
hand-drawn window discards too much of it. Weighting every day by the influence
function itself recovers the advantage: 0.847, which beats the whole-year missing
fraction by +0.013 (0.009, 0.017) and peak overlap by +0.265 (0.249, 0.285). The
lesson is that "condition on the support" is exact and "condition on a window
near the support" is an approximation whose quality depends on how concentrated
the influence is.

### 5.4 RQ1c — The standing guidance's own estimands

Johnson et al. (2021) fit a sine wave by linear regression and take a mean, a
phase and an amplitude. Reproducing that estimator on our panel puts our claim
and their guidance on the same footing for the first time (Figure 5c).

**Table 4.** Axis comparison on the sine-fit parameters, development cases,
each at 0.47 of its own interannual standard deviation.

| estimand | 30-day peak window | whole-year missing fraction | outage length | influence-weighted hidden mass | best axis |
|---|---:|---:|---:|---:|---|
| fitted mean | 0.672 | 0.845 | **0.845** | 0.845 | outage length |
| amplitude | 0.724 | 0.812 | 0.815 | **0.831** | influence-weighted |
| phase | 0.583 | 0.835 | 0.836 | **0.847** | influence-weighted |

Three things follow, and the first is the most important for how this paper
should be read. **On the estimands the guidance was derived for, the guidance is
right.** A completeness threshold is the correct axis for the fitted mean and is
within 0.02 AUC of the best axis for the phase. Our earlier framing — that the
incumbent rule "gets an ordering exactly backwards" — is true only for
warm-season extremes, which Johnson et al. never studied. What we are correcting
is the transfer of a threshold across estimands, not the threshold.

Second, the ordering is the same under the authors' own protocol, in which the
sine is fitted to whatever days are present with no repair at all: peak overlap
0.667, 0.743 and 0.590 against whole-year missingness 0.902, 0.842 and 0.898 for
the mean, amplitude and phase. The base rate is far higher — 32% to 34% of
station-years consequential, against 10% to 12% after repair — which is a
separate argument for repairing before screening.

Third, this explains the anomaly the guidance reported. Johnson et al. observed
that the timing of missing data mattered "inconsistently in space and time".
They were observing three parameters at once whose supports are a constant, a
pair of lobes at both extremes, and a pair of lobes at the transitions. A timing
effect appears for the amplitude and not for the mean, and a peak-window effect
appears for none of them. Inconsistency is what a mixture of three different
supports looks like from inside. We do not contradict the observation; we
decompose it, and we can now say in advance which of their parameters should
show a timing effect.

### 5.5 RQ2 — Which rivers are hard?

The mechanism above is a property of estimators and estimands and would hold for
any time series. This section asks the hydrological question. For the 140 United
States stations matched to GAGES-II across 57 networks, we regressed donor
synchrony and completed-year error on basin attributes, with the expected
direction of each effect declared before the regressions were run (Figure 13).

**Topography, not geology, predicts difficulty.** Site elevation and basin slope
both reduce donor synchrony (Spearman ρ = **−0.29**, 95% CI −0.46 to −0.08, and
ρ = **−0.31**, −0.51 to −0.07), and site elevation raises both completed-year
error (ρ = +0.24, 0.06 to 0.43) and the consequential-error rate (ρ = +0.25, 0.08
to 0.43). Mountain stations are harder because their neighbours are less
exchangeable: steeper lapse rates, snowmelt timing, aspect and shading make two
nearby gauges less alike.

**The groundwater prediction from the literature is not reproduced, and the
reason is instructive.** Johnson et al. report that filling can harm
groundwater-influenced sites, which predicts that a high baseflow index implies
larger completed-year error. Baseflow index does reduce donor synchrony in the
predicted direction, from 0.70 in the lowest tertile to 0.59 in the highest,
although the rank correlation interval includes zero (ρ = −0.19, −0.42 to 0.10).
But the error moves the *other* way: high-baseflow stations are **−0.043 °C**
easier than low-baseflow stations (95% CI −0.081 to −0.004).

Two opposing effects explain it, and the second is larger. Groundwater
contribution makes donors less informative, but it also damps the thermal regime
itself: across baseflow tertiles the mean annual peak falls from 22.7 °C to
18.1 °C (ρ = **−0.47**, −0.60 to −0.26) and its interannual standard deviation
from 0.98 °C to 0.76 °C. A damped regime is a smaller and steadier target, and
that outweighs the loss of donor information (Figure 13c). We therefore do not
contradict the earlier observation so much as decompose it: groundwater influence
degrades the *information* available for reconstruction while simultaneously
reducing the *difficulty* of the quantity being reconstructed.

**Regulation does not make station-years harder** for this endpoint: reference
and non-reference basins differ by +0.004 °C (95% CI −0.051 to +0.093).

**Catchment attributes explain a modest share of the variation** — a standardised
linear model reaches R² = 0.22 for donor synchrony and 0.13 for completed-year
error — and **no attribute predicts how much the screen gains**: every
correlation between a basin attribute and the per-station screening benefit has
an interval containing zero. The screening problem is therefore governed mainly
by outage geometry rather than by catchment physics, which is why basin
attributes are reported here as an explanation and are excluded from the
screening rule. They return in §5.9, where the question is not what the screen
gains but whom it keeps.

### 5.6 RQ3 — Does screening on the governing axis pay?

At 70% retention on development cases, the share of retained station-years with
a peak error above 0.5 °C is 2.9% for the calibrated screen, 5.6% for a rule on
peak overlap alone, 9.2% for the outage-length rule and 15.0% for random
retention (Figure 6a). On the **36 reserved networks, opened once with the frozen
rule and no retuning**, the screen gives 2.5% against 9.7% for the length rule
(Figure 6b): a contrast of **−7.13 points, 95% network-clustered interval −8.97
to −5.36**, against a pre-registered effect of five points and a resolvable
margin of 1.44 points. Both pre-registered conditions are met, in every donor
regime (none −6.6, sparse −6.7, rich −7.2, all excluding zero).

Placed at the operating points the published guidance actually implies, and not
at an arbitrary retention: at the seven-week unfilled limit (49 days, 49.2%
retention on the reserved panel) the length rule leaves 5.2% and the screen 0.3%;
at the twenty-week imputed limit (140 days, 85.1% retention) the length rule
leaves 11.3% and the screen 6.9%. The second of those numbers is new to this
version and it matters: the v17 manuscript placed this comparison at 91 days,
having mis-stated the imputed limit as thirteen weeks rather than twenty. The
corrected limit is far more permissive — it admits 85% of cases rather than 74% —
and the screen's advantage there is 4.4 points rather than 6.2.

**Table 5.** Reserved panel at 70% retention, across tolerances.

| screen | > 0.25 °C | > 0.5 °C | > 1.0 °C | underestimate > 1 °C |
|---|---:|---:|---:|---:|
| outage-length rule | 17.2% | 9.7% | 3.4% | **2.0%** |
| peak-overlap rule | 9.2% | 4.2% | 1.2% | 0.7% |
| calibrated screen | 7.1% | 2.5% | 0.4% | **0.3%** |
| random | 23.9% | 14.4% | 5.6% | 3.7% |

Understating a summer peak by more than a degree converts a thermally stressful
year into an unremarkable one. The screen reduces that rate sevenfold relative to
the incumbent.

The panel is unbalanced — one provider contributes 56 of the 110 development
networks — so the contrast was recomputed with each unit weighted equally. On the
reserved panel: case-equal −7.01, provider-equal −6.29, network-equal −5.82,
station-equal −5.54 points. Every weighting clears the declared five points and
every interval excludes zero. Across individual reserved networks the median
contrast is −5.0 points, **83% of networks favour the screen**, and the worst is
+2.8.

### 5.7 RQ3b — Was the incumbent handicapped, including by the absence of the field's own method?

A screening comparison can be rigged by pairing the incumbent with a weak
reconstruction, and the v17 estimator library had a specific weakness: air
temperature was available for 2.3% of development cases, so the reconstruction
this field actually uses was effectively absent. With coordinates joined for all
457 stations and NASA POWER pulled for the whole panel, air forcing now covers
**98.6%** of development cases and the comparison can be rerun.

**Table 6.** Development cases at 70% retention, with air forcing available
throughout.

| screen | reconstruction | error rate above 0.5 °C |
|---|---|---:|
| length rule | information-conditioned policy (used throughout) | 9.00% |
| length rule | **always air regression (Beaufort-style), else climatology** | **15.16%** |
| length rule | always donor ridge, else climatology | 9.57% |
| length rule | always smooth climatology | 19.79% |
| length rule | **oracle over methods, not deployable** | **3.62%** |
| calibrated screen | deployable estimators it selects itself | **2.87%** |

The screen beats the incumbent armed with a reconstruction nobody can run, and
the reconstruction paired with the incumbent throughout is the strongest of the
deployable options rather than the weakest. Pairing the incumbent with a
Beaufort-style air regression applied to every record alike makes it *worse*, not
better, which is the same point from the other side: a reconstruction that is
right on average is not right per case.

Three further observations belong here. First, the axis conclusion does not
depend on the estimator library — the timing-minus-length AUC contrast is +0.070
with the old forcing and +0.081 with the new. It is a claim about which cases are
hard, not about how well they are repaired. Second, the screen uses the new
information: it selects the air-driven estimator for **20.0%** of cases, against
0.07% in v17, and donor regression for 53.1%. Third, and least comfortable, the
*fixed* information-conditioned policy gets slightly worse at donor-less stations
when air becomes available (0.340 °C to 0.364 °C), because its preference order
was written when air was rare and it now prefers an air regression to a
climatology at sites where the climatology is better. A fixed ladder over
estimators is not robust to a change in what is available; a per-case selection
is. That is an argument for the method of this paper rather than against it, and
we report it because it was not the result we expected.

The pre-registered confirmation is **not** re-scored against the new forcing. It
stands as reported in §5.6; this section is a development-panel sensitivity
analysis.

### 5.8 RQ4 — What does each component contribute?

**Table 7.** Component ablation, development cases at 70% retention, each variant
re-run through the full out-of-fold pipeline.

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
therefore the conditioning set, and the calibrated machinery is a refinement on
it; we report the simple rule as a deliverable rather than as an ablation. Fitted
on development networks and applied unchanged to the reserved panel,

    risk = logistic( −1.302 + 2.070 · peak_overlap
                            − 2.412 · warm_observed_fraction
                            − 0.00187 · longest_run_days )

gives 4.2% against the length rule's 9.6% at 70% retention, a contrast of
**−5.44 points (−6.85, −3.96)**, and cuts severe underestimation of the peak from
1.9% to 0.6%. Three quantities an analyst can compute in a spreadsheet clear the
effect size this study pre-registered for its full method.

One interpretable piece of the remainder: the screen selects linear interpolation
for 25.0% of reserved cases against 5.7% under a presence-conditioned rule, and
interpolation carries the lowest error of any choice when selected (0.10 °C). For
short outages with both flanks observed, interpolation beats donor regression.

### 5.9 RQ5 — Where is the advantage absent, and why?

The pre-registered test was run on the pooled case set, which mixes two outage
arms whose base rates differ by an order of magnitude. They must be reported
apart.

**Table 8.** Decomposition by outage arm.

| panel | arm | cases | base rate, retain all | length rule at 70% | screen at 70% | contrast (95% CI) |
|---|---|---:|---:|---:|---:|---:|
| development | empirical | 14,995 | 7.4% | 2.52% | 0.38% | −2.13 (−3.45, −1.26) |
| development | stratified | 25,709 | 19.3% | 14.58% | 6.17% | −8.39 (−9.25, −7.47) |
| reserved | empirical | 4,041 | 4.2% | 0.74% | 0.11% | **−0.71 (−2.36, +0.05)** |
| reserved | stratified | 6,779 | 20.8% | 16.59% | 7.78% | −8.68 (−10.46, −6.51) |

The declared five-point effect is met on the pooled and stratified populations
and **not** on the empirical arm, where the reserved interval includes zero. The
headline −7.1 points is therefore an effect on a mixture that includes a designed
arm, and it is not an estimate of what any agency will experience next year. The
mechanism is general; the operational gain is regime-dependent.

**Why the empirical arm is null is itself a result.** The v17 manuscript reported
the null and left it unexplained. Across the 6,472 real interior gaps in this
archive, gaps shorter than 30 days and gaps of 30 to 89 days are close to uniform
in start month (χ² = 4.0 on 11 df, p = 0.97 for the 30–89 day class). Gaps of 90
days or more are not: **72.3% of them begin between September and January and
17.9% between March and July** (χ² = 86.1, p = 9.5 × 10⁻¹⁴). The outages long
enough to destroy a summer peak are seasonal shutdowns, and they start after the
warm season has been recorded. Agencies are already protecting the summer peak,
by a calendar nobody chose for that reason. Under that calendar little is at
risk, so little can be screened out: 4.2% of reserved empirical cases exceed the
tolerance with no screening at all.

Figure 7 shows that calendar and what it is worth.

The screen earns its place in the regime that motivates screening — long outages
overlapping the warm season — and §5.10 shows how much of a real archive falls
in it.

### 5.10 RQ6 — What the rule does to records that really have holes

Every number above is computed on a complete station-year with a synthetic hole
punched in it, which is the only way to have a truth. The same archive contains
**2,422 genuinely incomplete station-years**, a third of the total; they carry no
truth and have never been decided. They are the population a screening rule
exists for, and three things can be asked of them without inventing a truth
(Figure 8).

**They are not a marginal population.** The median incomplete year is missing 9
days and the 90th percentile 127. **28.7%** of them have at least one day of the
station's climatological peak window missing, and 261 have more than half of it
missing.

**The two rules disagree on a sixth of them.** At the seven-week unfilled limit
the length rule admits 83.2% and a peak-window rule at 10% hidden admits 81.2% —
near-equal retention, which is the comparison this paper insists on — and they
**disagree on 15.1%** of station-years: **207 are admitted by the incumbent and
rejected on timing**, and 158 are rejected by the incumbent and admitted on
timing. At the twenty-week imputed limit the incumbent admits 91.7% and the
disagreement is 11.6%, of which 267 are in the dangerous direction and 13 in the
wasteful one. The disagreement is present in every provider with more than 20
incomplete station-years, from 11.1% (GKD Bayern) to 25.7% (SYKE).

**Table 9.** Archive composition under each admission rule, on the 2,422 real
incomplete station-years.

| rule | admitted | admitted with any peak-window day hidden | with more than half hidden | with the peak window wholly hidden |
|---|---:|---:|---:|---:|
| repair everything, no screening | 2,422 | 696 | 261 | **186** |
| length ≤ 140 d (published, with imputation) | 2,221 | 507 | 82 | **17** |
| length ≤ 49 d (published, unfilled) | 2,016 | 437 | 45 | 2 |
| peak window ≤ 10% hidden | 1,967 | 241 | **0** | **0** |

The last two columns are the practical case for the paper, and they need no
truth. The published guideline that agencies are most likely to apply — the
twenty-week limit, which exists because imputation is assumed — admits 17
station-years whose annual peak was never observed at all and 82 whose peak
window is mostly gone. Each of those contributes an annual peak to an archive
that was inferred rather than measured, and nothing in the record marks it.

**Transporting the risk model.** A model of P(consequential error) fitted on
development cases from decision-time features only, and checked for calibration
on the reserved panel first (largest decile miscalibration 6.2 points, and under
1.6 points in nine of ten deciles), predicts a consequential-error rate of
**0.98%** among the years the unfilled limit admits, **1.85%** among those the
imputed limit admits, and **0.26%** among those the peak-window rule admits at
essentially the same retention. This is an extrapolation from scored cases to
unscored records and is labelled as one; §5.12 tests the exchangeability it
assumes.

**What changes in the regional picture is small.** Admitting incomplete years at
all raises the archive's mean annual peak by about half a degree relative to the
complete-year subset, and the choice of rule moves that by less than 0.1 °C:
+0.52 °C repairing everything, +0.51 °C under the unfilled limit, +0.53 °C under
the imputed limit and +0.45 °C under the peak-window rule. The share of
station-years above 20 °C moves from +4.55 points to +4.17 points across the same
four rules. We report this because it deflates a claim we might have made: at the
level of a regional aggregate, the decision that matters is whether to repair,
not which rule screens afterwards. The rule matters per station-year, and it
matters for who is in the archive (§5.11), not for the mean.

### 5.11 RQ7 — What changes downstream

**Per-year judgements.** On reserved networks the misclassification rate of a
20 °C exceedance is 6.86% when the statistic is computed on recorded days, 1.97%
when every year is reconstructed and not screened, 1.53% under length screening
and **0.36%** under the screen. Because most station-years sit nowhere near the
threshold, we restrict the judgement to years where the call is close.

**Table 10.** Exceedance misclassification, reserved panel.

| subset | observed days | reconstruct all | length-screened | screened |
|---|---:|---:|---:|---:|
| all retained | 6.86% | 1.97% | 1.53% | **0.36%** |
| truth within 1.0 °C of the threshold | 16.84% | 9.50% | 7.26% | **1.92%** |
| truth within 0.5 °C of the threshold | 19.10% | 13.12% | 10.24% | **3.38%** |

The advantage survives the restriction and is proportionally larger where the
call is hard — a 67% reduction against length screening within half a degree of
the threshold. The result is not an artefact of the threshold: swept from 14 °C
to 24 °C, the screen's misclassification stays between 0.18% and 0.37% while the
length rule stays between 0.84% and 1.53% (Figure 12c). The bias in the count of
years above 20 °C falls from −0.76 years per station under recorded days and
−0.32 under length screening to +0.06.

The 20 °C threshold is a modelling choice and is swept for that reason; the
regulatory literature uses a seven-day average of daily maxima with criteria that
differ by several degrees between jurisdictions and designated uses — 16 °C for
core cold-water salmonid habitat, 13 °C for salmonid spawning (WAC 173-201A-020)
— which is why we also report the seven-day endpoint throughout and sweep the
threshold across that range.

**Screening is not the only action the calibrated object supports, and for a
threshold judgement it is not the best one.** Discarding a station-year is a
blunt response to uncertainty about a single call. The alternative is to keep
every year and decline only the judgement the interval cannot support.

**Table 11.** Two action spaces on the reserved panel.

| policy | years judged | misclassification | missed exceedances |
|---|---:|---:|---:|
| screen at the 0.5 °C tolerance | 67.5% | 0.36% | 0.39% |
| abstain where the interval straddles the threshold | **92.7%** | 0.42% | 0.64% |
| both | 65.7% | **0.08%** | 0.12% |

Keeping 93% of station-years rather than 68% at essentially the same error rate
matters to anyone assembling a regional archive. The two action spaces answer
different questions — screening decides what enters an archive, abstention
decides what one judgement may say — and the same calibrated object serves both.

**Multi-year trends.** Theil–Sen slopes of the annual peak have RMSE
0.143 °C yr⁻¹ on recorded days, 0.044 with reconstruction and no screening, 0.048
under length screening and 0.041 under the screen. The panel averages eleven
complete years per station, which is too short to resolve a decadal trend; we
report the slope error as a diagnostic of the reconstruction rather than as a
trend estimate, and the only claim we make from it is that reconstructing at all
is the dominant step.

### 5.12 RQ8 — Whom does the screen keep?

A rule that lowers the average error by discarding hard station-years has bought
accuracy with representativeness. §5.5 asked whether basin attributes predict how
much the screen *gains* and found that none does. That is not the question an
agency asks. The question is which stations the screen *keeps*, and in this
application the hard sites are not a random subset: they are high-elevation,
steep, donor-poor catchments, which are the cold-water headwaters the summer
endpoint exists to describe.

At 70% retention the calibrated screen's per-station retention correlates with
site elevation at Spearman ρ = **−0.26 (p = 0.011)** on development and
**−0.27 (p = 0.077)** on the reserved panel. The incumbent length rule is
elevation-neutral: ρ = −0.05 (p = 0.60) and −0.10 (p = 0.52). On the reserved
panel the screen retains **77.7%** of station-years in the lowest elevation
tertile and **66.9%** in the highest, a spread of 10.8 points, against 1.7 points
for the length rule. By donor regime the same pattern appears on development
cases: the screen keeps 57.1% of station-years at donor-less stations and 72.5%
at donor-rich ones, a 15.4-point spread, while the length rule tilts the other
way. Dispersion of per-station retention roughly doubles, from 0.075 to 0.149.

**Table 12.** Error against representativeness, reserved panel at 70% retention
(Figure 9).

| rule | consequential-error rate | ρ(retention, elevation) | donor-regime retention spread | per-station retention SD |
|---|---:|---:|---:|---:|
| outage-length rule | 8.81% | −0.10 | 4.5 pts | 0.075 |
| peak-overlap rule | 3.75% | +0.16 | 2.4 pts | 0.104 |
| calibrated screen, global threshold | **2.53%** | **−0.27** | 4.3 pts | 0.149 |
| calibrated screen, balanced within donor regime | 2.52% | −0.27 | **0.1 pts** | 0.148 |
| calibrated screen, balanced within elevation tertile | 2.85% | **+0.08** | 4.6 pts | 0.148 |
| calibrated screen, balanced within both | 2.84% | +0.07 | **0.1 pts** | 0.144 |

The fix is cheap and it should be the default. Applying the screen's threshold
*within* stratum rather than globally costs **0.31 points** of consequential-error
rate on development cases and 0.30 on the reserved panel, and it removes both
distortions: retention becomes flat across elevation tertiles and across donor
regimes by construction. Stratifying on donor regime alone does not fix the
elevation tilt, and stratifying on elevation alone does not fix the donor tilt,
so an agency that cares about both must declare both. We therefore recommend
that a screening rule for a public archive be specified with its strata, and that
retention by catchment attribute be reported alongside the error rate, because a
rule that silently removes the mountain stations from a national thermal archive
has done damage that no error rate will show.

### 5.13 RQ9 — Does the result survive its assumptions?

**Is missingness informative?** Every case in this study transplants a mask onto
a year whose values were observed, which is valid only if the mask is independent
of the values it hides. Loggers are lost to floods, buried by ice and fouled in
low flow, and all three coincide with anomalous conditions. Across the 6,472 real
gaps in the archive, the mean anomaly of the seven days preceding a gap, relative
to the station's own day-of-year climatology, is +0.018 °C for gaps of a week or
less (p = 0.44), +0.038 °C for 8–29 days (p = 0.56), −0.002 °C for 30–89 days
(p = 0.98) and −0.215 °C for 90 days and longer (p = 0.081). Donors recording
through a gap run +0.063 °C warm during short gaps, which is detectable at this
sample size (p = 0.017) and is 3% of the within-station anomaly scale and an
eighth of a tenth of the tolerance. The design's exchangeability is defensible on
magnitude rather than on a null result, and the one class that warrants a
limitation is outages of three months and longer.

**Instrument error in the reference.** Perturbing the reference series by 0.15 °C
of normal noise — the upper end of logger accuracy — moves the development
contrast from 6.32 to 6.21 points and the reserved contrast from 7.06 to 6.67
points, and the mean absolute error from 0.2416 to 0.2418 °C (Figure 12b). The
conclusion is not inside the measurement error.

**Estimators that may see only prior years.** Under the stricter protocol in
which only years before the outage are available, the panel falls to 33,633
development cases on 3,337 station-years, reconstruction error rises from
0.242 °C to 0.270 °C, and the contrast moves from −6.35 (−7.12, −5.52) to
**−5.92 points (−6.72, −4.99)**, with coverage 0.906.

**Transfer across agencies.** Under leave-one-provider-out inside the development
pool, the contrast is negative and its interval excludes zero for **all nine
agencies**, ranging from −11.6 points (Finland) to −1.2 (Switzerland). Conformal
coverage under provider transfer stays between 0.82 and 0.96.

**Is the uncertainty honest?** On the reserved networks the nominal 90% interval
covers **90.9%** of cases marginally, within the pre-declared band of 0.87–0.93,
and 86.3% to 94.9% within every pre-declared stratum (Figure 10a). Median widths
adapt from 0.06 °C when the peak window is untouched to 1.87 °C when most of it
is hidden. Those strata pool across networks, and conformal validity assumes an
exchangeability that fails between river networks. Coverage inside individual
reserved networks has mean 0.904 and median 0.913 but a minimum of **0.778**,
with five of 36 networks below 0.85. The pooled interval is an honest statement
about a population of networks and is **not** a guarantee at a single new site.
Calibrating on the per-network conformal quantiles at the 0.9 level puts no
network below 0.85 for a 1.5-fold widening, and **the screening result is
identical under every calibration** to four decimal places, because the rank
order the screen uses is a monotone transform of the bound and a change of scale
cannot reorder it. A reader who distrusts the intervals need not distrust the
frontier.

## 6. Discussion

**What an agency should change, and in what order.** Figure 14 is the procedure,
end to end. The first recommendation is
not to adopt a model and not even to change a screening rule. It is to look at
the maintenance calendar. Holding the real distribution of outage lengths fixed
and changing only when outages begin, a calendar concentrated in March to July
would raise the consequential-error rate of the annual peak from 8.7% to
**13.2%**, and one concentrated in September to January would lower it to
**4.9%**. Those are swings of +4.4 and −3.9 percentage points, against a
screening gain of 6.3 points at 70% retention — the same order of magnitude, and
available before any data are lost rather than after. Our archives happen to sit
near the good end of that range for outages of three months and more, and near
the indifferent middle for everything shorter, so the headroom is real. Servicing
loggers, replacing batteries and scheduling site visits in autumn converts
recoverable outages into harmless ones; doing it in late spring does the reverse.
Redundancy follows the same logic: our donor experiments show that a second
station is worth having in proportion to its synchronous anomaly correlation with
the target rather than its mere existence, and our catchment analysis shows that
synchrony is lowest at high-elevation, steep sites, which is where a redundant
gauge buys the most.

**The second recommendation is to change the axis, and the third is to stratify
the change.** An agency that screens station-years for warm-season extremes on
maximum gap length should screen instead on how much of the station's
climatological warm window the outage hides — widened, per §5.3, to 60 to 90 days
rather than the 30 days of the metric itself, because one window of that width
serves every warm-season endpoint and absorbs the year-to-year wander of the
peak's position. On our reserved panel that substitution takes the
consequential-error rate from 9.7% to 4.2% at equal retention with three
variables and to 2.5% with the calibrated screen. But the threshold should be
applied within strata, not globally, or the archive quietly loses its mountain
stations; §5.12 prices that at a third of a percentage point. Equally, agencies
should **keep** their length-based rules for annual means and cold extremes, and
for the sine-fit parameters the standing guidance was written for, where our
evidence says completeness is the better axis.

**Why the standing guidance saw an inconsistency.** Johnson et al. reported that
the timing of missing data affected thermal-signal estimates inconsistently in
space and time. Their three estimands have three different supports — a constant
for the fitted mean, two lobes at the extremes for the amplitude, two lobes at
the transitions for the phase — and only one of the three has a support narrow
enough for a timing effect to appear. Observing all three at once, inconsistency
is the only thing one could see. Our result does not contradict the observation;
it decomposes it, and it predicts in advance which of their parameters should
show a timing effect.

**What generalises beyond rivers.** The law is a statement about estimators and
estimands, and its ingredients — an influence function and a mask — exist wherever
a derived statistic is computed from an incomplete record. What does not
generalise is the numerical crossover at 91 days: that depends on how
concentrated a river's thermal year is and on how far the peak wanders between
years, both of which are properties of this climate and this variable. What we
would expect to transfer is the shape of the argument and the measurement
protocol: locate the estimand's support, measure how far its location moves
between periods, dilate by that amount, and condition on the result.

**On uncertainty for derived statistics.** The field reports daily prediction
skill and almost never reports uncertainty on the annual statistic that is
actually used. The two are not interchangeable for an extreme: a model with
excellent daily RMSE can be badly wrong about a 30-day maximum if its errors are
correlated within the peak window. Calibrated intervals on the derived statistic
are cheap to produce once the problem is posed this way, and §5.13 shows they can
be made honest either for a population of sites or for a single site, with the
price stated.

## 7. Limitations

The operational benefit depends on the outage regime: under the geometry these
networks actually experience the reserved-panel interval includes zero (§5.9),
and the headline contrast is computed on a mixture that includes a designed arm.
The deployment analysis in §5.10 decides real incomplete records but cannot score
them; its risk numbers are a labelled extrapolation from scored cases. The
archive-level consequence of changing rules is small — the choice of rule moves a
regional mean annual peak by less than 0.1 °C — and we do not claim otherwise.
The pooled conformal interval is not valid at a single new site unless the
cluster calibration is used, and that costs width. The screen uses a station's
own history, so nothing here applies to ungauged sites. Outages that straddle a
calendar year are outside the design, and the law implies they should be nearly
harmless for both peaks and costly for both means — a prediction we have not
tested. Fully observed calendar years are, by selection, the better-instrumented
part of an archive. Catchment attribution and the representativeness analysis are
restricted to the United States subset where GAGES-II applies, and 140 of 204
stations match. Missingness is weakly informative and the transplant design is
defended on the magnitude of that effect rather than on its absence (§5.13); the
defence is weakest for outages of 90 days and longer. The primary tolerance is a
modelling choice at 0.47 interannual standard deviations rather than an
ecological threshold, which is why the frontier is reported at 0.25, 0.5 and
1.0 °C and the exceedance threshold is swept from 14 °C to 24 °C. Eleven complete
years per station is too short for a decadal trend claim, and none is made.

## 8. Conclusion

Whether a data gap matters depends on how much the statistic being computed
depends on the days it hides. Measuring that share — the hidden mass on the
estimand's support — orders the regimes that a completeness threshold cannot see,
and it does so continuously: sweeping the support of a warm-season mean from one
day to a full year, the advantage of a peak-window axis over a completeness axis
decays from +0.074 AUC and crosses zero at 91 days. Because a support has to be
located before it can be conditioned on, and a river's hottest window wanders by
one to two weeks between years, the conditioning set that works is the support
widened by that wander; one climatological window of 60 to 90 days is
near-optimal for every warm-season endpoint we examined. On the estimands the
standing guidance was written for, that same law says the guidance is right,
which is why the correction is to the transfer of a threshold rather than to the
threshold.

Acting on it is cheap. Screening on the governing axis, pre-registered and scored
once on 36 networks reserved before any analysis, reduces the consequential-error
rate by 7.1 percentage points relative to published guidance at equal retention
and reduces severe underestimation of the summer peak sevenfold; most of that is
obtained by three variables in a logistic regression. Taken to the 2,422 real
incomplete station-years the study could not score, the rule reverses the
admission decision for one in six of them and removes the 17 station-years that
published guidance admits with the annual peak never observed.

Two things should be said as loudly. The gain is regime-dependent, and under the
outage calendar these agencies currently keep it is not resolvable — because long
outages already begin in autumn, which is itself the most actionable finding
here: moving maintenance into spring would cost more than the screening rule
saves. And a screen that selects on difficulty selects against high, steep,
donor-poor catchments unless its threshold is applied within strata, which costs
a third of a percentage point and should be standard. Keep length-based
completeness rules for averages and for sine-fit regime parameters; replace them
with support-based rules for warm-season extremes; and schedule the loggers.

## Figures

Figures 1, 2, 3 and 14 are schematics, drawn in draw.io; their editable sources
are in `figures/v17/drawio/` and the PDFs are exported from those sources by
`make figures-drawio`. Figures 4, 6, 10, 11, 12 and 13 are produced from the
analysis artifacts by `scripts/188_v17_figures.py` and
`scripts/204_v17_figures_q1.py`; Figures 5, 7, 8 and 9 by
`scripts/220_v18_figures.py`. Figures marked SI are supporting information.

| # | file | what it shows |
|---|---|---|
| 1 | `figures/v17/f0_problem_frame.pdf` | Why one completeness threshold cannot serve two estimands: the same station-year and outage mask feed an annual mean and a hottest 30-day mean, the two have different supports and therefore different governing axes, and the measured error gradients along each are quoted. |
| 2 | `figures/v17/f1_system_architecture.pdf` | The screening system: visible features under an information barrier, the estimator library with per-case support, the risk model, selection-conditional multiplicative conformal calibration, and the two action spaces. |
| 3 | `figures/v17/f2_experiment_design.pdf` | Study design and data flow, from nine providers to the single opening of the reserved panel, with the quality-control exclusions, the network-level stratified split, the §4.7 gate and the pre-registered freeze in execution order. |
| 4 | `figures/v17/fig1_mechanism.pdf` | Mechanism: the length-by-overlap reversal (a), nested feature sets (b), permutation importance (c), endpoint dependence (d). |
| 5 | `figures/v18/figv3_support_law.pdf` | The law. (a) The advantage of a fixed 30-day peak window over whole-year completeness against the support width of the estimand, with network-clustered intervals and the crossover at 91 days. (b) AUC for every estimand against every conditioning window; the best window is 60–90 days for every estimand narrower than that, and the black square marks the estimand's own support. (c) The three sine-fit parameters Johnson et al. use, by axis. |
| 6 | `figures/v17/fig2_frontier.pdf` | Retention–error frontier on development cases (a) and on the reserved panel (b). |
| 7 | `figures/v18/figv1_outage_seasonality.pdf` | (a) Start month of 6,472 real interior gaps by length class; outages of 90 days and longer begin in autumn and winter. (b) What the maintenance calendar is worth: the consequential-error rate under four placement calendars, holding the real outage-length distribution fixed. |
| 8 | `figures/v18/figv2_archive_deployment.pdf` | The rules on 2,422 real incomplete station-years. (a) Agreement and disagreement at each published limit. (b) Transported risk of each admitted set. (c) Station-years admitted with the peak window more than half, or wholly, unobserved. |
| 9 | `figures/v18/figv4_representativeness.pdf` | (a) Consequential-error rate against the correlation between station retention and site elevation, reserved panel. (b) Retention by elevation tertile under three rules. |
| 10 | `figures/v17/fig3_calibration.pdf` | Conformal coverage by stratum (a), interval width against peak-window overlap (b), and the price of site-level validity (c). |
| 11 | `figures/v17/fig4_consequence.pdf` | Multi-year trend error (a) and the donor controls (b). |
| 12 | `figures/v17/fig5_robustness.pdf` | Clustered intervals on the axis contrasts (a), reference-noise perturbation (b), exceedance-threshold sweep (c). |
| 13 | `figures/v17/fig6_hydrology.pdf` | Catchment attribution on the United States subset, and the decomposition of the baseflow effect (c). |
| 14 | `figures/v17/f4_deployment_workflow.pdf` | What an agency does with the result, including the representativeness guardrail. |
| SI-1 | `figures/v17/f3_evidence_chain.pdf` | The evidence chain by research question, and which links this version closes. |

## References

Beaufort, A., Diamond, J. S., Sauquet, E., and Moatar, F. (2022). Spatial
extrapolation of stream thermal peaks using heterogeneous time series at a
national scale. *Hydrology and Earth System Sciences*, 26(13), 3477–3495.
https://doi.org/10.5194/hess-26-3477-2022

Caissie, D. (2006). The thermal regime of rivers: a review. *Freshwater
Biology*, 51(8), 1389–1406.
https://doi.org/10.1111/j.1365-2427.2006.01597.x

Corona, C. R., and Hogue, T. S. (2025). Machine learning in stream and river
water temperature modeling: a review and metrics for evaluation. *Hydrology and
Earth System Sciences*, 29(12), 2521–2549.
https://doi.org/10.5194/hess-29-2521-2025

Falcone, J. A. (2011). *GAGES-II: Geospatial Attributes of Gages for Evaluating
Streamflow*. U.S. Geological Survey.
https://doi.org/10.3133/70046617

Geifman, Y., and El-Yaniv, R. (2017). Selective classification for deep neural
networks. *Advances in Neural Information Processing Systems*, 30.

Hampel, F. R. (1974). The influence curve and its role in robust estimation.
*Journal of the American Statistical Association*, 69(346), 383–393.
https://doi.org/10.1080/01621459.1974.10482962

Isaak, D. J., Wenger, S. J., Peterson, E. E., Ver Hoef, J. M., Nagel, D. E.,
Luce, C. H., Hostetler, S. W., Dunham, J. B., Roper, B. B., Wollrab, S. P.,
Chandler, G. L., Horan, D., and Payne, S. L. (2017). The NorWeST summer stream
temperature model and scenarios for the western U.S.: a crowd-sourced database
and new geospatial tools foster a user community and predict broad climate
warming of rivers and streams. *Water Resources Research*, 53(11), 9181–9205.
https://doi.org/10.1002/2017WR020969

Johnson, Z. C., Johnson, B. G., Briggs, M. A., Snyder, C. D., Hitt, N. P., and
Devine, W. D. (2021). Heed the data gap: guidelines for using incomplete
datasets in annual stream temperature analyses. *Ecological Indicators*, 122,
107229. https://doi.org/10.1016/j.ecolind.2020.107229

Kratzert, F., Nearing, G., Addor, N., Erickson, T., Gauch, M., Gilon, O.,
Gudmundsson, L., Hassidim, A., Klotz, D., Nevo, S., Shalev, G., and Matias, Y.
(2023). Caravan — a global community dataset for large-sample hydrology.
*Scientific Data*, 10, 61. https://doi.org/10.1038/s41597-023-01975-w

Lei, J., G'Sell, M., Rinaldo, A., Tibshirani, R. J., and Wasserman, L. (2018).
Distribution-free predictive inference for regression. *Journal of the American
Statistical Association*, 113(523), 1094–1111.
https://doi.org/10.1080/01621459.2017.1307116

Li, H., Deng, X., and Smith, E. (2017). Missing data imputation for paired
stream and air temperature sensor data. *Environmetrics*, 28(2), e2426.
https://doi.org/10.1002/env.2426

Mauger, S., Shaftel, R., Trammell, E. J., Geist, M., and Bogan, D. (2015).
Stream temperature data collection standards for Alaska: minimum standards to
generate data useful for regional-scale analyses. *Journal of Hydrology:
Regional Studies*, 4, 431–438. https://doi.org/10.1016/j.ejrh.2015.07.008

Mauger, S., Shaftel, R., Leppi, J. C., and Rinella, D. J. (2017). Summer
temperature regimes in southcentral Alaska streams: watershed drivers of
variation and potential implications for Pacific salmon. *Canadian Journal of
Fisheries and Aquatic Sciences*, 74(5), 702–715.
https://doi.org/10.1139/cjfas-2016-0076

Mohseni, O., Stefan, H. G., and Erickson, T. R. (1998). A nonlinear regression
model for weekly stream temperatures. *Water Resources Research*, 34(10),
2685–2692. https://doi.org/10.1029/98WR01877

NASA Langley Research Center (2026). *POWER Daily Data, T2M (MERRA-2)*.
Prediction Of Worldwide Energy Resources project.
https://power.larc.nasa.gov

Rubin, D. B. (1976). Inference and missing data. *Biometrika*, 63(3), 581–592.
https://doi.org/10.1093/biomet/63.3.581

Washington State Department of Ecology. Water quality standards for surface
waters of the State of Washington, WAC 173-201A-020 (definitions, including the
seven-day average of daily maximum temperatures) and WAC 173-201A-200
(aquatic-life temperature criteria).

Zaoui, A., Denis, C., and Hebiri, M. (2020). Regression with reject option and
application to kNN. *Advances in Neural Information Processing Systems*, 33.

## Data and code availability

Daily temperature records are from the nine public providers listed in the
supporting information. Station coordinates are from those providers' own
catalogues, the USGS NWIS site service, and ARSO's public station feed; daily
air temperature is from NASA POWER. Basin characteristics are from GAGES-II
(Falcone, 2011). All analysis code, artifacts, figures, draw.io figure sources
and the frozen pre-registration are in the accompanying repository;
`results/v17_fitness/evidence_ledger.csv` and `paper/v18/claims_v18.md` map each
claim to the script, artifact and digest behind it, and every table in this
article is re-derived from those artifacts by an automated audit that runs in
the test suite.
