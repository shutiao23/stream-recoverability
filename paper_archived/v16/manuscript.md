# Conditional reconstruction of stream temperature

**Working title:** Using historical observations to decide when reconstruction improves a completed stream-temperature record

This draft is the WRR revision after `docs/reviews/wrr_2026_09_06/REVIEW.md`.
It does not claim a recoverability law, a model-family-independent station
threshold, or Johnson et al. (2021) as independent numerical validation of a
crossing day. Numbers are taken from `results/wrr_revision/` after parent
recalculation of the CSV artifacts.

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
is frozen from this panel. Held-out QC networks that were in neither design
panel reproduce the neighbour versus donor/long-block split. On those
networks, always reconstructing when donors and both flanks exist already
matches a \(\tau=0\) ranker on hottest-30 loss. Adopt/reject is necessary
for the withdrawn trainer and for donor-missing faults; it is not a
substitute for using a recoverer that remains nested in the available
information.

## 1. Question

After a logger failure, both flanking temperatures are again observed. The
analyst may write a reconstruction into the archive or leave the
climatological default. The primary loss is the absolute error of the hottest
consecutive 30-day mean on the completed station-year. Days above 20 °C are a
sensitivity setting. Daily MAE is a diagnostic.

Johnson et al. (2021) constrain **unfilled** gap length for thermal metrics;
they also show that filling can extend usable records to about 20 weeks and
can harm groundwater-influenced sites. That 49-day unfilled limit is not a
validation of a reconstruction-failure threshold. Beaufort et al. (2022)
already hide complete years, fill, and recompute heat peaks. The increment
here is a pre-outage adopt/reject rule relative to a default, not the first
demonstration that filling changes thermal metrics.

The second 57-network panel used in earlier drafts is descriptive. It
participated in design iteration and is not prospective confirmation.

## 2. Methods

Development uses the 42 first-panel networks (219 stations with joint-complete
donors in the fair-recovery table). Confirmation uses QC networks that appear
in neither the first scored placement file nor the second-panel prediction
file (36 year-eligible held-out IDs). Default: training-period day-of-year
median. Actions: adopt reconstruction or reject to default. Unsupported
predictions, missing synchronous donors, and missing right boundaries reject.
A 20% budget is supplementary and need not be filled. Zero action is always a
legal competitor.

Fair recovery reuses archived evaluation placements on the 7–365 day grid and
adds 120 and 150 day windows. Training protocols cross neighbour-day versus
long-block training with versus without the target-boundary feature, and add
donor-only ridge, linear interpolation, and climatology. Air and air2stream
models are an external-information group, scored only where forcing exists,
and are not mixed into the same-information ranking.

Benefit predictors are hierarchical means of historical paired errors. The
published `diff` estimator is identical to the seasonal empirical benefit
mean on complete cells (maximum absolute gap \(8.88\times10^{-16}\)).

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
Discharge was not available there, so air2stream was not fit.

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

The decision contribution is the donor and right-boundary gates, not a more
elaborate ranker.

### 3.4 Station-year replay

Cases are station-years with a gap pattern. Actions may leave the budget
unused. All-default is scored as zero. Inner-year history covers the full
duration grid.

On the 42-network development panel (222 stations; 11,066 cases), always
reconstructing donor-only when donors and both flanks exist has hottest-30
benefit **+0.278 °C** versus 0 for all-default and +0.033 for a ≤30 d
seasonal rule. The ranked \(\tau=0\) frozen rule is **+0.194 °C** (adopt
0.70 versus 0.97). Mixed 30/90/180 patterns: ranked +0.272, always-donor
+0.431. At 180 d: ranked +0.339 versus always-donor +0.596. The ranker
discards beneficial long gaps.

On 36 held-out networks (70 stations; 2,512 cases), always-donor is
**+0.133 °C**, the ranked rule **+0.131 °C** (adopt 0.59 versus 0.67), and
the seasonal rule +0.020. Mixed 30/90/180 patterns: ranked +0.188,
always-donor +0.187. The ranked rule beats all-default and the seasonal
rule. It does not beat always reconstructing when the information gates
pass (difference −0.0025 °C).

The earlier 42-network replay that mixed long-block XGB with P0 predicted
benefits is withdrawn.

### 3.5 Confirmation

Held-out year-eligible QC networks (36 IDs, 70 stations, 56,232 rows) were
not in either scored design panel. On the 23 networks with donors at 180 d,
network-mean MAE benefit is **+0.71 °C** for donor-only and **−2.10 °C** for
neighbour-boundary XGB (hottest-30 +0.24 versus −1.59). Crossing fractions
over all stations: donor-only 3%, neighbour-boundary 89%. At 7 d,
neighbour-boundary ridge (+0.89) still beats donor-only (+0.71), which is
why the freeze keeps that short-gap exception. Single-station networks have
no donor-only model and reject to climatology under the freeze.

### 3.6 Mechanism battery

A seasonal-mean plus residual AR(1) generator, with a structurally correct
AR(1) residual bridge, was used only to test whether a universal crossing
must appear. The structural recoverer does not cross in any of the four
predeclared systems. Neighbour-boundary training crosses in high-memory and
air-driven systems; long-block training does not. The law claim is dropped.
The paper is a prediction-and-decision study of a correctable model failure
plus a donor/boundary reject rule.

## 4. Interpretation

What the experiments support: under an offline repair protocol, with
synchronous donors and both flanks, a recoverer that does not trust
gap-wide interpolated target boundaries remains useful at seasonal and annual
gap lengths. The published neighbour-boundary trainer does not, and that
failure is not a hydrologic recoverability limit. Adopt/reject over
climatology is the right task for the withdrawn trainer and for donor-missing
or open-outage cases. It is not required to “spend” a 20% reconstruction
budget.

What they do not support: a model-family-independent duration threshold; a
precomputable station crossing obtained by correlating climatology MAE with
the same-table crossing; Johnson’s unfilled 49-day limit as confirmation;
prospective status for the second panel; and a claim that MAE ranking
automatically improves thermal-regime endpoints.

The contribution is an applicability result: use donor (or long-block)
information, and refuse reconstruction when that information is absent. On
held-out data the ranked rule (+0.131 °C) and always-donor (+0.133 °C) are
indistinguishable; mixed-duration cases are tied. On the development panel
always-donor is clearly stronger (+0.278 versus +0.194). Ranking is not
required to beat all-default once the recoverer is repaired.

## 5. Data and code

Problem definition and protocol:
`docs/reviews/wrr_2026_09_06/PROBLEM_DEFINITION.md`,
`EXPERIMENT_PROTOCOL.md`. Experiments:
`src/stream_recoverability/experiments/wrr_revision/` and
`scripts/160`–`169`. Artifacts: `results/wrr_revision/`.
