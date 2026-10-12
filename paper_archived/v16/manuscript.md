# Conditional reconstruction of stream temperature

**Working title:** Using historical observations to decide when reconstruction improves a completed stream-temperature record

This draft is the WRR revision after `docs/reviews/wrr_2026_09_06/REVIEW.md`.
It does not claim a recoverability law, a model-family-independent station
threshold, or Johnson et al. (2021) as independent numerical validation of a
crossing day. Numbers are taken from `results/wrr_revision/` after parent
recalculation of the CSV artifacts.

**Status after the 2026-09-07 review and the 10-step program.** The
training-mismatch diagnosis in §3.1 stands. The 36 held-out IDs are not 36
river networks. A 3-parameter air2stream without daily discharge was fit on
the 17 POWER networks. On reserved unseen river complete years the calibrated
adopt/reject overlay does **not** beat the strong simple competitor. The
paper’s positive contribution is the training-mismatch diagnosis plus
simple-method applicability, not a new superior decision layer. Population,
truth, and success rules:
`results/wrr_revision/SUCCESS_CRITERION.json`,
`docs/reviews/wrr_2026_09_07/PROBLEM_DEFINITION.md`.

## Abstract

Filling a stream-temperature gap can make a completed archive worse for
thermal-regime judgment. The operational question is whether to adopt a
reconstruction or keep a default climatology, using only information that is
available after the outage has ended. Incremental benefit over climatology
remains the estimand. A sign change in that benefit is a property of a
recoverer, a training protocol, and an information set, not a station law.

On 42 development networks, the published neighbour-day trainer with a
gap-interpolated target boundary collapses at long gaps. The same algorithm
trained on long blocks, or any model that never uses the target boundary,
does not. Donor-only ridge stays beneficial at 180 and 365 days when donors
and both flanks exist, and becomes strongly harmful when donors are hidden.
A duration switch (neighbour-boundary ridge at 7 days, donor-only thereafter)
is frozen from this panel as a simple competitor, not as a new decision
layer. Held-out QC networks that were in neither design panel reproduce the
neighbour versus donor/long-block split. The v16 36-ID set is retrospective.
Reserved unseen river complete years (36 networks, 82 eval station-years)
show that always reconstructing donor-only when donors exist remains
beneficial, and that a historically calibrated adopt/reject overlay does not
beat that simple policy on mean hottest-30 benefit.

## 1. Question

After a logger failure, both flanking temperatures are again observed. The
analyst may write a reconstruction into the archive or leave the
climatological default. The primary loss is the absolute error of the hottest
consecutive 30-day mean on the completed station-year. Days above 20 °C are a
sensitivity setting. Daily MAE is a diagnostic.

Related work already covers adjacent pieces of this problem, and those
pieces are not interchangeable with the present estimand. Li et al. (2017)
fill consecutive stream-temperature gaps with a space–time air–water
relationship plus neighbouring stations and then evaluate downstream
clustering; they ask which interpolant is accurate, not whether adopting it
beats a climatological default on a complete-year thermal peak. Johnson et
al. (2021) constrain **unfilled** gap length for annual mean, phase, and
amplitude, report that filling can extend usable records to about 20 weeks,
and show that filling can harm groundwater-influenced sites. Their 49-day
unfilled limit is not a validation of a reconstruction-failure threshold.
Beaufort et al. (2022) already hide complete years, fill, and recompute heat
peaks; they measure the effect of filling, not a decision-time adopt/reject
rule. Reject-option regression (Zaoui et al., 2020) supplies a theoretical
adopt/reject machinery with a fixed rejection rate and a variance criterion;
that is not the same problem as maximising, or bounding the harm of,
incremental benefit over a named default on a completed thermal archive.
The increment claimed here is therefore narrower than “fill gaps” or
“reject uncertain predictions”: it is a historically calibrated
adopt/reject rule relative to climatology, scored on complete-year hottest-30
error, and it is allowed only if it beats strong simple methods on a valid
river panel. If it does not, the paper’s positive contribution is the
training-mismatch diagnosis plus simple-method applicability.

The second 57-network panel used in earlier drafts is descriptive. It
participated in design iteration and is not prospective confirmation.

## 2. Methods

The study population is river waterbodies with a fully observed calendar-year
reference. Seas, lakes, canals, and estuaries are a transfer list and are not
averaged into river confirmation (`results/wrr_revision/step1_universe/`).
Annual hottest-30 truth is defined only on those complete years; the reference
series is never imputed. The v16 36-ID confirmation set, including the
846-case river+complete-year subset, has been read and is not unseen
confirmation. Reserved unseen confirmation is the Step-1 `candidate_unseen`
pool (37 networks, 293 complete river station-years), unused for rule
selection.

Development uses first-panel river complete years. Default: training-period
day-of-year median. Actions: adopt a supported reconstruction or reject to
default. Support is method-specific: donors for donor regression, both flanks
for interpolation, air for air-driven models. Missing right boundary is an
information condition, not an automatic reject for donor-only. Zero action is
always legal. A 20% reconstruction budget is not imposed.

Fair recovery reuses archived evaluation placements on the 7–365 day grid and
adds 120 and 150 day windows. Training protocols cross neighbour-day versus
long-block training with versus without the target-boundary feature, and add
donor-only ridge, linear interpolation, and climatology. Air ridge, lagged-air
ridge, and 3-parameter air2stream (Almeida and Coelho, 2023; no daily
discharge) are an external-information group, scored only where NASA POWER
forcing exists, and are not mixed into the same-information ranking.

Benefit predictors are hierarchical means of historical paired errors. The
published `diff` estimator is identical to the seasonal empirical benefit
mean on complete cells (maximum absolute gap \(8.88\times10^{-16}\)); they
are not two methods.

The information-conditioned simple policy, frozen from the Step-4 factorial
on development networks, is: donor-only whenever synchronous donors are
observed (right flank optional); else air ridge when air exists, except
≤30 d gaps with both flanks where linear interpolation is competitive; else
smooth climatology. Partial-donor cells retrain the donor model on the
visible subset rather than imputing missing donor columns in the full model.

## 3. Results

### 3.1 Training protocol versus a duration threshold

On all 42 first-panel networks (`results/wrr_revision/step2_fair_recovery/`,
303,426 rows):

Mean MAE benefit (°C) on matched placements:

| days | xgb neighbour+B | ridge neighbour+B | xgb long-block+B | xgb no B | donor-only | linear interp |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | +1.00 | +1.01 | +0.91 | +0.91 | +0.94 | +0.83 |
| 90 | +0.37 | +0.36 | +0.87 | +0.88 | +0.90 | −0.20 |
| 180 | **−0.72** | **−0.76** | **+0.89** | **+0.91** | **+0.92** | −2.05 |
| 365 | **−2.16** | **−2.31** | **+0.92** | **+0.94** | **+0.95** | −4.55 |

Observed MAE-benefit crossing fraction: neighbour-boundary XGB 81%,
neighbour-boundary ridge 82%, long-block XGB 4%, donor-only 2%. Stations that
do not cross are right-censored at the last evaluated length. Hottest-30
benefit at 180 d: neighbour-boundary XGB −0.97 °C; donor-only +0.43 °C.

The previous “threshold” is a mismatched training protocol. It is withdrawn
as a station attribute and as a model-family-independent law.

Air temperature from NASA POWER, scored as a separate information group on
17 first-panel networks, remains beneficial at 180 d (+0.25 °C MAE) and does
not collapse, but is weaker than donor-only on the same gaps (+0.70 °C).
The 8-parameter air2stream was not fit because daily discharge was absent.
A 3-parameter air-only air2stream (Almeida and Coelho, 2023) **was** fit on
those 17 networks: mean MAE benefit +0.22 °C without donors, versus +0.28 °C
for air ridge and +0.04 °C for smooth climatology
(`results/wrr_revision/step4_information/`). It does not require discharge.

### 3.2 Benefit predictors are seasonal empirical means

On archived P0 placements for the published recoverer,
\(\max|\texttt{diff}-\texttt{seasonal empirical}|=8.88\times10^{-16}\) on both
panels. They are the same hierarchical mean.

A history-frozen rule “adopt if predicted MAE benefit \(>0\) and supported”
has pooled MAE net benefit +0.487 °C (first panel) and +0.409 °C (second)
versus 0 for all-default. All-reconstruct is +0.122 and **−0.111** on those
panels. On second-panel 180-day placements the same rule has net **−0.016 °C**
and does not beat all-default. Ranking the published trainer is useful on a
mixed-duration pool and is not a reliable sign classifier at 180 days.

On Step-2 scores of the repaired recoverers, always reconstructing donor-only
ridge already has MAE net about +0.92 °C; a \(\tau=0\) rule is almost the
same (+0.920 versus +0.922) because predicted benefit stays positive.
Adopt/reject is therefore not the source of gain once the recoverer no longer
collapses.

### 3.3 Faults

On the same 42 networks (`step5_failures/`, 52,140 rows): at archived 180 d
with donors present, donor-only MAE benefit is +0.92 °C (hottest-30 +0.43).
With every donor hidden on the same windows, donor-only is **−3.07 °C** and
long-block XGB is **−7.35 °C**. Left-only persistence versus climatology is
**−4.54 °C**. Transplanted historical gap geometry with donors still observed
keeps donor-only positive (+0.82 °C). Heatwave-overlapping gaps (fraction
\(\ge 0.5\)) do not uniquely reverse donor-only (hottest-30 +0.63 °C).

The decision contribution claimed in v16 was the donor and right-boundary
gates. Step 4 shows that donor-only does not use the right flank: on 25
development networks the prediction is identical when that observation is
hidden. Linear interpolation does need both flanks, and is useful only for
short gaps when donors are missing. Air ridge is the best simple method when
donors are missing on the POWER networks. Partial-donor cells on 40
development networks: imputing missing donor columns in the full ridge is
harmful (−1.56 °C MAE); retraining on the visible subset is beneficial
(+0.74). Weak donors only: the full model is −2.59 °C; air ridge is +0.26.
Support must be method-specific.

### 3.4 Complete-year thermal replay

The primary endpoint is hottest-30 absolute error on a fully observed
calendar year. Development uses 42 first-panel river networks and 918 eval
station-years (`step5_thermal_decision/`). Absolute default error is
**0.77 °C**. Always reconstructing the information-conditioned simple policy
has network-equal \(B_q\) **+0.329 °C** (CI 0.23–0.44), harm 0.22, and
absolute policy error 0.36 °C (overestimate 0.34, underestimate 0.47).
Always donor-only is +0.330. A year-level thermal \(\tau=0\) overlay is
+0.294 (Δ −0.035, inside ε = 0.05), harm 0.14, adopt 0.75. Same-adoption-rate
random is +0.231 and fails ε. Length/season ≤30 d JJA is +0.013. MAE labels
for the overlay are indistinguishable from always-simple. Remaining oracle
headroom is +0.07 °C.

On transplanted natural geometry (`step7_failure_replay/`), always-simple
remains +0.244 °C. When donors are co-missing, donor-only is unsupported
(\(B_q\) 0) and always-simple falls to +0.024.

High training-period donor synchrony keeps long-gap donor-only at +0.49 °C;
low synchrony is −0.08. Regulated GAGES networks have weaker simple-policy
benefit (+0.11) than unmatched networks (+0.46).

The v16 36-ID replay, including the 846-case river+complete-year subset, is
retrospective and is not unseen confirmation.

### 3.5 Unseen confirmation

Reserved `candidate_unseen` river complete years: 36 networks, 82 eval
station-years (`step10_unseen_confirmation/`). Absolute default error
**0.97 °C**. Always donor-only **+0.175 °C** (CI 0.07–0.31); always-simple
+0.146; frozen thermal overlay **+0.060** (Δ −0.086 versus simple, outside
ε). Overlay harm 0.06 versus simple 0.38, but adoption is only 0.16. Mean
non-inferiority fails. The overlay is not a confirmed risk-control rule.

Neighbour versus donor/long-block MAE crossing on the old 36-ID QC table
remains a retrospective diagnosis of the withdrawn trainer, not river
population confirmation.

### 3.6 Mechanism battery

A seasonal-mean plus residual AR(1) generator, with a structurally correct
AR(1) residual bridge, was used only to test whether a universal crossing
must appear. The structural recoverer does not cross in any of the four
predeclared systems. Neighbour-boundary training crosses in high-memory and
air-driven systems; long-block training does not. The law claim is dropped.

## 4. Interpretation

What the experiments support: under an offline repair protocol, with
synchronous donors, a recoverer that does not trust gap-wide interpolated
target boundaries remains useful at seasonal and annual gap lengths. The
published neighbour-boundary trainer does not, and that failure is a
correctable training mismatch, not a hydrologic recoverability limit. When
donors are missing, air ridge (or short-gap interpolation) is the simple
treatment; an imputed full donor model is harmful. Full default remains
legal. A 20% reconstruction budget is not imposed.

What they do not support: a model-family-independent duration threshold; a
precomputable station crossing; Johnson’s unfilled 49-day limit as
confirmation; the v16 36 IDs as 36 rivers with annual thermal truth; and a
claim that a new adopt/reject layer beats strong simple methods on a valid
unseen river panel.

The contribution is the training-mismatch diagnosis plus simple-method
applicability: use donor information when it is observed and well correlated,
retrain or switch when it is not, and do not add a historically calibrated
overlay unless it passes the pre-specified non-inferiority and harm tests.
On unseen complete years it did not.

## 5. Data and code

Problem definition and protocol:
`docs/reviews/wrr_2026_09_07/PROBLEM_DEFINITION.md`,
`EXPERIMENT_PROTOCOL.md`. Experiments:
`src/stream_recoverability/experiments/wrr_revision/` and
`scripts/160`–`176`. Artifacts: `results/wrr_revision/`.
