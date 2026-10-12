# Historical block stress tests rank future model-specific reconstruction error across stream-temperature networks

Key Points and the Plain Language Summary are maintained in
`paper/development_v13/aux_text_v13_a.md` (this file's companion).

## Abstract

Word count: 250.

Equal-length stream-temperature outages produce recovery losses that are
specific to the recovery model. We framed the problem as model-conditional
historical stress testing: cut seasonally stratified artificial gaps into
the fitting years of a record, recover them with the intended model, and
use the curve to rank that model's future loss. Development used 55
networks; a first panel of 42 was used for method development; a second,
outcome-disjoint panel of 57 networks (32 US, 15 Czech, 10 Norwegian)
provided evaluation. On the 874 units at directly supported horizons (7,
30, 90, 180 days), the stress test ranked later loss with network-level
Spearman 0.80 and station-gap Spearman 0.945. A station-by-horizon
historical mean from the same record nearly matched it (pooled 0.942
versus 0.945; paired network difference +0.042, 95% CI straddling zero),
so the increment beyond station history is modest. Ranking is carried by
exact station-by-season curves; network-mean fallbacks weaken it, and a
continuous surface interpolates unsupported 14- and 60-day horizons well
but fails at extrapolated 365 days (rank 0.27; coverage 46.8%). Difficulty
ordering transfers across engineered-regression families but not across
architecture families or missingness mechanisms; the two mechanism-matrix
implementations are not harmonized. For fixed-budget triage the frozen
predictor is the worst non-random policy (CapturedLoss@20% 0.337 versus
0.512); with per-unit support and abstention, selection regret drops to
0.0067 on 8.5% of units. Downstream benefit is baseline-dependent:
reconstruction cuts distortion versus no-fill (12-14% for integrated
metrics) but exceeds climatology-fill distortion for threshold extremes.
These are model-conditional screening tools; independent preregistered
validation is required.

## 1. Introduction

A failed logger can leave weeks or months of missing stream temperature
while boundary observations, neighboring stations, weather records, and
discharge remain available, and the manager must act before the missing
truth arrives. The gap geometry is known at onset (its duration may not
be), the donor network and its boundaries are visible, and the default
handling is fixed by the downstream workflow: leave the gap empty, fill it
with a climatological expectation, or reconstruct it with a model. The
manager's question is therefore not which imputation method is best on
average, but which action is best for this outage geometry and this
recovery model: how much recovery error should be expected before the
missing truth becomes available, and whether acting on that expectation
improves whatever the downstream user will compute. The answer is
inherently model-specific: a reconstruction family's error on a given gap
is a property of that family's fit, its features, and its sensitivity to
the outage, not a property of the gap alone. This paper develops and
evaluates one answer: a historical block stress test, in which artificial
gaps are cut into the already-observed fitting years of the record and the
intended recovery model is scored on them, so that the resulting curve
inherits the model's own error structure.

Several mature literatures bear on predicting recovery error, but none
answers this question for a specific model on a specific future gap.
Gap-filling studies compare reconstruction models on their imputation
quality [@li2017streamairimputation; @bal2023streamtemperature]. Gaussian
posterior variance, kriging variance, mutual information, and value of
information have long been used to design monitoring networks
[@caselton1984monitoring; @pardo1998gauges; @krause2008sensor;
@alfonso2012voi], and recent hydrological sensor design uses rank-revealing
QR decomposition validated by reconstruction [@oh2025sensors]. Flux-network
studies use stratified artificial gaps and show that uncertainty grows with
gap length and season [@moffat2007gap; @richardson2007longgaps]. What these
traditions do not provide is a quantitative link between a pre-outage risk
estimate and the realized recovery loss of a specific model on unseen river
networks: analytic variance is not validated against model error, and
trial-gap experiments are rarely carried through to rank or decision
metrics on outcome-disjoint networks.

The knowledge gap is prospective and model-conditional: the fitting-period
failure record of a model is evidence about that model's future failures on
the same stations, seasons, and donors, but nobody has tested whether that
record actually ranks future recovery loss on networks whose outcomes were
never used to build anything. Artificial or trial gaps themselves are
established tools for stress-testing recovery methods
[@moffat2007gap; @richardson2007longgaps]; we do not propose the trial-gap
idea as new. Our contribution is the model-conditional evaluation: whether
a fitting-period error curve ranks the same model's future error across a
panel of wholly unseen networks, why the ranking is strong where it is and
fails where it fails, and what that implies for decisions. Uncertainty
metrics can mislead precisely because they are not realized model error:
classical kriging variance can understate prediction variance when
covariance parameters are estimated [@denhertog2006kriging], a
value-independent variance need not represent local error dispersion
[@yamamoto2000kriging], and hydrological conformal prediction shows that
local information may be insufficient for extremes [@auer2024uncertainty].
A valid test must therefore connect a pre-evaluation risk to observed
recovery loss of the same model, leave out whole river networks, and carry
the result through calibration and decisions.

Our design is within-network historical stress testing replicated across an
outcome-disjoint network panel, with five features that delimit the claim.
First, stress is model-specific: for each network, seasonally stratified
artificial gaps are placed wholly inside the fitting years and recovered
with the intended model, so the curve measures local donor behavior,
seasonal dynamics, and model error in the same units as the target loss.
Second, support is explicit: every prediction carries a support tier (exact
station x duration x season, station-duration, network-duration,
network-mean fallback, unavailable), and a continuous support-aware risk
surface provides interpolated predictions at unsupported durations with
intervals. Third, the comparison is against the strongest fitting-record
baseline available to a manager: the station-by-horizon historical mean of
the network's own trial gaps, plus simple structural descriptors, not just
against gap geometry or a global mean. Fourth, decision value is framed as
incremental benefit over the default handling (no-fill or climatology) at
prespecified coverage, not as raw rank magnitude. Fifth, evidence roles are
labeled: the second panel is internally frozen but not externally
preregistered, all revision analyses are post-hoc method development on
already-scored panels, and only a future externally registered protocol
v4 panel can confirm any endpoint.

We ask three questions. RQ1: does a model-specific fitting-period stress
curve predict later recovery loss of the same model on outcome-disjoint
networks beyond the strongest fitting-record baseline (the station-by-
horizon historical mean), and where does any increment live: at exact
support tiers, across horizons, and within networks? RQ2: how do support
(exact, interpolated, extrapolated), model family, missingness mechanism,
and the analytic covariance alternative bound the ranking, and how does
difficulty transfer across architecture families? RQ3: at prespecified
coverage, does a support-aware selector reduce recovery-model regret and
downstream thermal distortion relative to the default handling, and what
does abstention cost? The river network is the primary extrapolation unit
throughout (Figure 1).

## 2. Methods

### 2.1 Study phases and data

The development collection combined 55 river networks, 217 stations, and
1,260 station-gap units for which temperature, meteorology, hydraulics,
analytic risk, and recovery outcome used identical fitting rosters. The
first confirmation panel contained 42 scoreable networks from North America
and Europe contributing 1,440 station-gap units, used for post-confirmation
method development. The second, outcome-disjoint panel scored 57 networks
(32 US, 15 Czech, and 10 Norwegian; 1,446 units); no second-panel network
appeared in the development or first-panel outcome sets. Daily mean stream
temperature was the target. Calendar years were ordered and the first 70%
used for fitting; the remaining years supplied observed truth for 7-, 14-,
30-, 60-, 90-, 180-, and 365-day artificial gaps, with up to 20 placements
per station-gap cell. The primary loss was mean absolute error (MAE) in
degrees Celsius. Stations and gaps were repeated observations nested within
networks.

### 2.2 Recovery-model roster

The prespecified recovery condition was gradient boosting (300 trees, depth
4, learning rate 0.05) with local gap boundaries and synchronous donor
temperatures; the matched development operator experiment additionally
supplied meteorology and hydraulics. To separate information availability
from model-specific error, the same gaps were scored with two additional
families: a seasonal-boundary ridge regression (three annual harmonics and
linear interpolation between observed gap boundaries) and a donor covariance
regression (synchronous neighboring temperatures with ridge stabilization).
Median feature imputation, scaling, and all coefficients were fit using
fitting years only. Two further families delimit model conditionality. A
mask-aware bidirectional LSTM (hidden size 16, early stopping on a nested
fitting-period validation split, patience 12, three seeds) was trained on 12
networks; the median best epoch was 68 and 28% of runs reached the epoch
cap, replacing an earlier bounded run that hit its cap in most networks. We
also implemented the published eight-parameter air2stream state equation and
Crank--Nicolson update [@toffolon2015air2stream], calibrated on train-only
bounded multistart least squares; the outcome-blind subset was eight
second-panel US networks with 89 station-gap units. The air2stream
equivalent is US-only, and its daily time conventions differ from the
provider-native windows.

### 2.3 Model-conditional empirical transfer, support tiers, and the strongest fitting-record comparator

We nested a second chronological split inside the outer fitting years. The
first 70% of those years fit the same gradient-boosting recovery family; the
remaining fitting years supplied observed artificial-gap truth. For 7-, 30-,
90-, and 180-day gaps, candidate starts were divided into DJF, MAM, JJA,
and SON seasons and up to 20 placements were selected per season; their mean
MAE formed a station-by-duration-by-season empirical curve before the outer
evaluation period began. Each prediction carries one of five support tiers,
from most to least specific: exact local support (station x duration x
season), station-duration support (season collapsed), network-duration
support (station collapsed), network-mean fallback (a network-wide mean of
all fitting-period losses), and unavailable. Units at unsupported horizons
(14, 60, 365 days) always fall to the network-mean tier. No outer evaluation
loss entered any source. Throughout, the curve is model-conditional: it is
built with the same recovery model whose future error it ranks.

The primary fitting-record comparator is the station x horizon historical
mean (ladder rung r6): the mean of the network's own fitting-period trial
losses by station and gap duration, season collapsed. This is the strongest
information a manager can obtain from the fitting record alone without a
model: it uses the same station, the same gap length, and the same recovery
pipeline's fitting-period outcomes, and it needs no covariates and no
cross-network transfer. For second-panel evaluation it was computed from
the same fitting-period placements as the empirical curve and frozen before
comparison (post-hoc v13 development of the comparison itself, on the
already-scored panel; the predictor is frozen). Additional comparators are
the gap-length mean, the network historical mean (r4), the network x
horizon mean (r5), the simple-descriptor model (r8; linear in gap length,
target autocorrelation, donor R2, an additive-d/4 heuristic, and
nearest-donor correlation, coefficients fit on fitting-period data only),
and the hierarchical risk surface (r11). All paired comparisons compute
both predictors on identical unit subsets and bootstrap the differences by
paired network resampling (Section 2.8).

### 2.4 Continuous support-aware risk surface

To replace the network-mean fallback with a prediction at any duration, we
fit a hierarchical model of fitting-period MAE on the pooled development and
first-panel fitting placements (100,397 rows, 93 networks, 376 stations):
log(1 + MAE) ~ network random intercept + station(network) random intercept
+ exactly monotone quadratic B-spline f(log duration) + two cyclic Fourier
harmonics of day-of-year + seven station covariates (temperature SD and IQR,
climatology error, lag-1 and lag-gap autocorrelation, daily gradient, donor
R2), estimated by exact REML. The second panel's 57 networks are new levels,
so their random effects are shrunk to zero: every second-panel prediction is
pure transfer of the shared surface. Predictions on the 14- and 60-day
horizons are interpolations of the monotone duration curve; the 365-day
horizon is flagged extrapolation, and its 90% log-scale Gaussian interval is
widened by a factor of 1.435. We evaluated the surface on the second panel
and cross-checked it by refitting on first-panel fit losses only.

### 2.5 Rolling-origin and history-length stability

Ranking stability was tested by moving the outer chronological cutoff to
60, 70, and 80% of each record on a 20-network first-panel subset, rebuilding
the stress curve strictly inside each training block (10 placements per
season), and comparing predicted network ranks across cutoffs with Kendall's
W. A history-length learning curve fit the stress model on the first 2, 4,
6, 8, and full years of the record on 20 networks with fixed evaluation
windows. Training-length comparability was tested by building deployment-
matched curves with the full 70% training block and comparing them with the
standard 49%-length stress curves on the same 635 supported cells.

### 2.6 Downstream thermal-regime metrics and the incremental-benefit design

On 15 first-panel networks (1,755 placements at 7-, 30-, and 90-day gaps in
one implementation; 1,965 placements in the companion implementation), each
reconstruction was inserted into the evaluation-period daily record and ten
thermal-regime metrics were recomputed: annual mean, summer (JJA) mean,
amplitude (July minus January mean), phase (day of peak), 90th percentile,
summer maximum, days above 20 and 25 C, degree days above 10 C, and trend
slope. Distortion was the absolute difference from the truth record. The
design prespecifies three untreated defaults against which reconstruction
benefit is measured: no-fill (gap days dropped, the status quo for many
downstream users), climatological fill (the seasonal expectation used by
operational workflows), and linear interpolation between gap boundaries.
The two analyses completed for this revision implement no-fill and
climatology fill; the interpolation leg is registered as part of the v13
development program and is not yet reported. The design target is
incremental benefit B = D(default) - D(model) - lambda*C, where D is the
aggregate thermal-metric distortion of a treatment over a budget of treated
gaps, C is the treatment cost (for example, the loss mass of the treated
set), and lambda converts cost into distortion units; raw MAE is an input
to B, not the decision objective. We correlated the fitting-period risk
score with per-metric distortion and ran a budget experiment protecting the
top 20% of gaps by risk, by gap length, and at random, reporting reduction
in aggregate distortion relative to each untreated default.

### 2.7 Decision experiments with coverage floors

Part 1 (second panel, 1,446 units, 57 networks): units were ranked by seven
scores--raw gap length, a duration-plus-season fit, the simple-descriptor
model, the frozen empirical predictor, the hierarchical surface, random,
and an observed-loss oracle--and the top 5, 10, 20, and 30% of units were
awarded their observed loss. CapturedLoss@B was the fraction of total loss
in the top-B set; NDCG@B the position-discounted normalized gain; paired
differences used a 2,000-draw network bootstrap. This experiment is a
reported negative diagnostic: the frozen empirical predictor is expected
to be a poor loss-capturing triage instrument, and the manuscript reports
it as such rather than as a claim.

Part 2 (first panel, 1,440 units, 42 networks): for each of three recovery
families (seasonal-boundary ridge, donor ridge, XGBoost), a per-family
fitting-period stress curve was built (unit-level curves where placements
exist, pooled duration curves otherwise), recalibrated to the outer-loss
scale, and penalized by family-specific interval width (penalized risk =
risk + lambda x width; lambda = 0.5 in the primary reading). The selector
picked the family with the lowest penalized risk and could abstain when (i)
the two best penalized risks were within 10% (ambiguity) or (ii) any family
lacked unit-level stress support. Regret was the network-balanced mean of
(selected loss - best-family loss); comparators were best-fixed-family,
global leave-one-network-out CV, per-network average CV (an in-sample,
non-deployable benchmark), a gap-length rule, and random. The v12 result
released only 123 of 1,440 units (8 of 42 networks; 8.5% coverage) and is
therefore a proof of concept, not a deployable claim. The v13 design adds
mandatory coverage floors (at least 50% of units and 60% of networks
released at the primary operating point, with a 70% design target) and
evaluates the full coverage-regret curve; the protocol-level rules,
success criteria, and the power analysis for the fixed-coverage comparison
against the strongest deployable comparator are frozen in protocol v4
(Section 2.10, Open Research).

### 2.8 Inference, calibration, and intervals

All predictions left out complete networks. Results report network-level
Spearman (over network means) first, followed by pooled station-gap and
within-network rank as diagnostics. Calibration intercept and slope used
weights inversely proportional to the number of station-gap rows in each
network. Network bootstrap intervals resampled rivers (2,000 draws). The
same-unit paired comparisons of Section 3.1 computed both predictors on
identical unit subsets and paired the bootstrap differences within
resampled networks.

### 2.9 Model-family and missingness matrices: definitions and harmonization status

Recoverability difficulty was measured in a model-source x model-target
matrix: each cell is the network-level Spearman between a fitting-period
stress curve of the source family and the outer-evaluation losses of the
target family on the same networks (engineered block: linear/PCHIP
boundary, seasonal-boundary ridge, donor ridge, XGBoost; plus BiLSTM and
air2stream rows). Missingness mechanisms were generated on 12 networks with
a mechanism's own placement distribution and recovered with the same
XGBoost family, building a mechanism-matched station-by-horizon curve;
evaluation gaps used the same mechanism. Mechanisms were: uniform single
block; multi-block; summer-biased; high-temperature-biased;
donor-synchronous (target and all donors masked); target-plus-primary-
covariate; and online left-boundary recovery. A mismatch experiment applied
the uniform-block curve to every other mechanism's evaluation gaps.

Harmonization status (post-hoc v13 development): the model matrix is
broadly consistent across the two independent implementations for the
engineered block (self-transfer 0.91-0.98 versus 0.90-0.96 at the network
level) but differs in the BiLSTM row, whose "self-transfer" values of
0.29-0.69 combine two different instances of the BiLSTM family (source =
the newly trained mask-aware BiLSTM; target = the older frozen bounded-run
predictions). We therefore relabel any BiLSTM-family cell as cross-instance
transfer and report both conventions. The missingness matrix is not
harmonized: the two implementations used different 12-network panels (only
5 of 12 networks shared) and different forcing definitions (target plus
strongest donor masked with weaker donors remaining, versus target plus
air-temperature forcing), and their matched donor-synchronous transfer
differs materially (0.979 versus 0.490 at the network level). Until the
panels and forcing definitions are unified, the missingness matrix is
supporting information, not a main claim; no single matched-transfer value
is asserted in this manuscript. The analytic conditional-covariance
operator is also demoted to supporting information (Section 3.7).

### 2.10 Evidence roles and protocol v4

Evidence-role labels are applied throughout. (1) Frozen: the second-panel
outcomes, the empirical predictor as originally frozen, and the second-panel
scoring are internal and hash-bound, but because their amendment and
outcomes entered version control in the same commit they are not externally
verifiable preregistration. (2) Post-hoc v13 development: every analysis in
this revision--the baseline ladder, paired comparisons, support hierarchy,
risk surface, model and missingness matrices, rolling-origin and history
checks, downstream metrics, decision experiments, and the covariance
re-reading--reuses already-scored panels; none is independent confirmation.
(3) Future preregistered: only a third panel scored under protocol v4 can
confirm or refute the endpoints. Protocol v4 (drafted in this revision
folder; to be consolidated at `paper/development_v13/protocol_v4.md`)
replaces protocol v3. Its primary endpoint is the fixed-coverage
network-balanced selection-regret difference between the proposed
support-aware selector and the strongest deployable comparator (a
leave-one-network-out nested-CV selector computable for any target
network), evaluated at coverage floors of at least 50% of units and 60% of
networks released (70% design target), with success criteria of a paired
network-bootstrap 95% CI below zero and at least a 20% relative regret
reduction, and with the power analysis recomputed by simulation on the
regret endpoint (the v3 rank-correlation anchor is not reused). Rank
comparisons are demoted to secondary endpoints with r6 as the baseline;
365-day units are scored only with real same-horizon fitting-period support
and otherwise forced-abstained; downstream endpoints use the incremental-
benefit form B = D(default) - D(model) - lambda*C against climatology and
interpolation defaults. All margins and the roster are frozen before
outcomes in a separate public commit, with external OSF/Zenodo
registration (Section Open Research).

## 3. Results

### 3.1 Strongest-baseline external comparison (second and first panels)

[Frozen second panel; comparison developed post-hoc on the already-scored
panel.] At the four directly supported horizons, the empirical predictor
covered 874 second-panel units and reached station-gap Spearman 0.945,
network-level Spearman 0.805, equal-network calibration slope 0.938, and R2
0.813. The station x horizon historical mean of the same networks' own
fitting-period losses (r6) nearly matched it on the same units: pooled
Spearman 0.942 versus 0.945 and network Spearman 0.763 versus 0.805
(Figure 2). The paired network-level difference was +0.042 (2,000-draw
network bootstrap 95% CI [-0.0006, +0.1154]) and the pooled difference
+0.0029 (95% CI [-0.0004, +0.0068]); the two predictors correlate 0.992
(Pearson; Spearman 0.996) on these units. The empirical curve is therefore
not meaningfully more informative than a station's own history at the
rank level; the claim is prospective utility and model conditionality, not
rank-magnitude superiority over this baseline. The increment over the
simple-descriptor model remains large and significant on the same 874
units: +0.552 (95% CI [0.309, 0.814]) at the network level and +0.098
([0.059, 0.142]) at the station-gap level, with simple descriptors at
0.846 pooled and 0.248 network-level (slope 1.157); the empirical predictor
won the within-network rank comparison in 41 of 57 networks (0.719). The
hierarchical surface, which lacks each network's own fitting curves,
reached 0.898 pooled and 0.689 network-level on the same units--above
simple descriptors and below the empirical curve and r6 at the network
level. Per horizon, empirical network Spearman was 0.932 (7 d), 0.916
(30 d), 0.865 (90 d), and 0.659 (180 d), against 0.374, 0.153, 0.043, and
0.164 for the simple model; the advantage is largest at short horizons and
remains positive at 180 days. On the first panel (direct_858 units, 42
networks), the empirical curve again matched r6 (pooled 0.825 versus
0.825; network 0.801 versus 0.798; paired network difference +0.0024, 95%
CI [-0.0239, +0.0262]).

Across all 1,446 units, the empirical predictor reached 0.740 pooled and
0.715 network-level against 0.835 pooled and 0.605 network-level for simple
descriptors; the paired network-level difference was directionally positive
(+0.109, 95% CI [-0.126, 0.356]) but included zero, and the station-gap
difference was negative (-0.095, [-0.158, -0.028]): the 596 network-mean
fallback rows are constant within a network, destroy within-network
ordering, and drag pooled rank below the simple model (r6 reaches 0.735
pooled and 0.726 network-level on the full panel; the network historical
mean r4 reaches 0.772 network-level). The full-panel comparison is an
artifact-driven diagnostic; the same-unit paired comparison at directly
supported horizons is the claim.

### 3.2 Support and duration: exact, interpolated, extrapolated

[Frozen panel; support accounting developed post-hoc.] The direct-horizon
ranking is overwhelmingly carried by exact station x duration x season
curves: 841 of the 874 units (96.2%) had exact local support, and that tier
alone reaches network Spearman 0.887 and pooled Spearman 0.968. The
station-duration tier held only 9 units (2 networks) and the network-
duration tier 0 units in the second panel; 24 additional direct-horizon
units fell back to the network mean, so the fallback tier totals 596 units
(572 horizon-unsupported plus 24 direct-horizon without a station curve).
In the fallback tier, network Spearman fell to 0.562 and pooled Spearman to
0.339, and within-network rank is undefined by construction. First-panel
and development panels show the same structure (exact 673 and 635 units;
network-duration 107 and 183; fallback 660 and 637). Support quality
degrades monotonically with distance from the exact cell: on the second
panel, exact-local units reach network Spearman 0.931, station-level
(distance < 100) 0.629, and network-level 0.758. A pure network-difficulty
control--the network historical mean of its own fitting losses--ranked the
full panel at 0.772, above the empirical predictor's 0.715, confirming that
the empirical advantage is carried by within-network ordering rather than
by separating persistent network difficulty.

The continuous support-aware surface fixes most of the fallback deficit
[post-hoc v13 development]. On the second panel, its full-panel pooled
Spearman was 0.893 (versus 0.740 for the old predictor), R2 0.475 (0.238),
and RMSE 1.096 C (1.320). On the 572 previously unsupported horizon units
it raised network Spearman from 0.597 to 0.846, pooled from 0.388 to 0.879,
and R2 from -0.03 to 0.38. The 448 interpolated 14- and 60-day units were
well calibrated (pooled Spearman 0.774, calibration slope 1.025), in
contrast to the old constant fallback (0.451 and 0.509). The 365-day
horizon is the hard boundary: rank on the 124 extrapolated units was 0.270
(network-level) and 90% interval coverage was 46.8% despite the
pre-specified widening (overall coverage 92.5%; direct 96.0%; interpolated
98.2%). Abstaining the 124 extrapolated units--8.6% of units carrying 28.9%
of total loss--raised released-unit network Spearman to 0.691 and R2 to
0.663; the abstention is justified for point-release decisions, not for
loss-capturing budgets (Section 3.4). Pure-transfer predictions are
underdispersed (calibration slopes 1.3-2.3), so absolute magnitudes require
external recalibration. Cross-checking on the first panel, where both
models fit from the same fit losses, the surface beat the old predictor on
every metric (network Spearman 0.898 versus 0.767), including its 660
fallback cells (0.874 versus 0.504).

### 3.3 Within-network and temporal stability

[Frozen panel; decomposition and stability analyses developed post-hoc.]
The network-level 0.805 is not an artifact of persistent network difficulty:
a predictor that perfectly separates network means reaches pooled Spearman
of only 0.326 in-sample, while the empirical predictor's network-demeaned
pooled Spearman is 0.936 on the direct subset and its median within-network
Spearman is 0.965. The ranking lives inside stations and horizons, not
between networks, and it is stable in time. Moving the outer cutoff from 60
to 70 to 80% of each record reproduced supported-only network Spearman of
0.947, 0.922, and 0.949 (the 60% leg attrites to 14 networks because early
years lack complete donor rosters; 70% and 80% legs use 20 networks), and
the predicted network ranks agreed across cutoffs with Kendall's W of
0.81-0.92 across implementations (0.811, tie-adjusted, 13 networks, in the
canonical implementation; 0.917 in the agent_a re-run). History length
matters: network Spearman rose from 0.608 with 2 years of fitting history
to 0.872 at 4 years, 0.916 at 6, 0.938 at 8, and 0.944 with the full
record, implying a minimum usable fitting history of roughly 4 years. The
concern that the stress model trains on less record than the deployed
recovery model (49% versus 70% of years) is empirically negligible: paired
MAE difference 0.013 C and Spearman 0.989 between the two stress curves on
the same cells.

### 3.4 Decision experiment: coverage-regret, abstention cost, and the fixed-budget triage negative

[Frozen panels; decision analyses developed post-hoc.] For model selection
on the first panel (1,440 units, 42 networks), without abstention the
risk-based selector adds nothing: network-balanced regret was 0.084 versus
0.081 for a development-chosen best family and for global leave-one-network-
out CV (the winning families are nearly tied in mean loss, donor ridge
1.270 versus XGBoost 1.274), and per-network average CV--an in-sample
benchmark--reached 0.038. With abstention the picture reverses, but only as
a proof of concept: when every candidate family has unit-level fitting-
period stress support (8 of 42 networks, 123 units, 8.5% of the panel) and
ambiguity abstention is applied, the selector's network-balanced regret
drops to 0.0067 (95% CI [0.0019, 0.0120]), an order of magnitude below
every comparator on the same released units (best fixed 0.151, global CV
0.151, per-network CV 0.164, gap-length rule 0.145, random 0.341).
Ambiguity abstention alone does not help--near-ties are cheap (985 released
units, regret 0.100)--the sharp lever is the support rule: selection is only
meaningful where per-unit fitting-period stress exists for all candidates.
The full coverage-regret curve (Figure 4) shows regret declining with the
fraction abstained; the 8.5%-coverage operating point is not deployable, and
protocol v4 sets coverage floors of at least 50% of units and 60% of
networks at the primary operating point, with the fixed-coverage regret
difference as the primary endpoint.

For fixed-budget prioritization on the full second panel, the frozen
empirical predictor is the worst non-random policy; this is a reported
negative diagnostic. At a 20% budget, CapturedLoss was 0.512 (95% CI
[0.485, 0.537]) for the simple-descriptor model, 0.504 for duration-plus-
season, 0.500 for the surface, 0.498 for raw gap length, and 0.337
([0.302, 0.380]) for the empirical predictor (random 0.200, oracle 0.529);
NDCG@20% was 0.908 for simple and 0.617 for empirical. The paired bootstrap
differences were -0.174 ([-0.198, -0.140]) for empirical minus simple and
-0.012 ([-0.031, +0.003]) for surface minus simple. The failure is
structural: the network-mean fallback tier under-ranks the 365-day loss
mass (mean prediction 1.33 C versus observed 5.27 C), which carries 28.9%
of total loss in 8.6% of units. Abstention does not rescue loss-capturing
budgets--abstaining the 124 extrapolated units removes 8.6% of units
carrying 28.9% of total loss--but it is justified for point-release
decisions, where the same abstention raises released-unit network Spearman
to 0.691 and R2 to 0.663 (Section 3.2).

### 3.5 Downstream thermal outcomes: both untreated baselines

[Frozen panels; downstream analyses developed post-hoc; the two baselines
come from two independent implementations and both are reported.] Against
the no-fill default (gap days dropped), reconstruction substantially
reduces distortion of integrated metrics: reconstructed error was 12-14% of
no-fill error for degree days, annual mean, and trend slope (ratios 0.138,
0.124, 0.126), and 30-37% for the 90th percentile, amplitude, and days
above 20 C. Single-event metrics were barely distorted at all (zero
reconstruction error in 88-95% of placements for days above 25 C, summer
maximum, and phase), and reconstruction restored computability: no-fill
leaves amplitude undefined in 20.9% of placements, while reconstruction
always returns a value. Against the climatology-fill default, the picture
inverts for extreme and threshold metrics: treating the top 20% of gaps by
the empirical risk score (or by gap length) made aggregate distortion
worse than the climatology default for degree days (-17.9%), days above
20 C (-22.2%), days above 25 C (-42.5%), amplitude (-33.8%), summer mean
(-23.0%), phase (-10.8%), and the 90th percentile (-13.0%), with only the
annual mean slightly better (+2.2%); the combined distortion reduction was
-17.7%. The no-fill and climatology defaults therefore lead to opposite
conclusions about the value of risk-targeted reconstruction for
threshold-extreme metrics, and no single number can be reported without
stating the untreated baseline. Read through the incremental-benefit form
B = D(default) - D(model) - lambda*C, the no-fill leg shows a positive
benefit for integrated metrics and the climatology leg does not; the design
target is B, not raw MAE, and the interpolation default remains to be
scored. The fitting-period risk score predicts distortion of the integrated
metrics at the network level (annual mean 0.764, degree days 0.743, phase
0.729, 90th percentile 0.668) but not of amplitude (0.089) or summer
maximum (0.250), whose distortion is governed by gap geometry rather than
reconstruction error. In the no-fill budget experiment (top 20% of gaps),
risk targeting beat random on every metric except amplitude: degree-day
error was reduced 39.5% (risk) versus 34.4% (gap length) versus 17.1%
(random), and days-above-25-C error 10.9% versus 2.1% versus 3.6%.

### 3.6 Model-family boundaries: cross-instance transfer

[Post-hoc v13 development on already-scored panels; cells resting on 4-8
networks are fragile and reported with their counts.] Recoverability
difficulty is shared within the engineered-feature block (linear/PCHIP
boundary, seasonal-boundary ridge, donor ridge, XGBoost): self-transfer
network Spearman was 0.91-0.98 and cross-transfer within the block
0.72-0.98, with the XGBoost stress curve predicting the outer losses of the
boundary and ridge families almost as well as its own. The bidirectional
LSTM row is different: its self-transfer values of 0.29-0.69 are
cross-instance transfer, because the source is a newly trained mask-aware
BiLSTM (12 networks, three seeds, median best epoch 68, 28% reaching the
epoch cap) and the target is the older frozen bounded-run predictions
(agent_a convention 0.28; agent_b convention 0.68 at the network level). Its
cross-transfer to the engineered block was -0.24 to +0.28 across the two
implementations' conventions, and its fitting-period stress correlated only
0.067 with the XGBoost stress on the same networks--the two families
disagree about which networks are hard. The air2stream-equivalent process
model showed weak self-transfer (0.64 on 8 networks) and null-to-negative
cross-transfer (about 0.24 from XGBoost). Overall, the diagonal (self-
transfer, mean 0.783) exceeds the off-diagonal (mean 0.434; one-sided
Mann-Whitney p = 0.033), but that gap is driven entirely by the neural and
process rows: inside the engineered block the off-diagonal cells are nearly
saturated.

### 3.7 Missingness mechanisms: demoted to supporting information

[Post-hoc v13 development; not harmonized between implementations.] Two
independent implementations of the missingness-mechanism matrix disagree,
so the matrix is supporting information rather than a main claim. The
agent_a implementation (12 networks: Slovenian, German, Swiss, and US
networks) found strong mechanism-matched transfer--donor-synchronous 0.979,
multi-block 0.944, online left-boundary 0.930, target-plus-primary-
covariate 0.881, uniform 0.531, summer-biased 0.594, high-temperature-
biased 0.580 at the network level--with matched calibration slopes
0.89-1.01, and found that applying the uniform-block curve to
support-destroying mechanisms collapses rank (donor-synchronous 0.979 to
0.294, target-plus-primary-covariate 0.881 to 0.196, online 0.930 to 0.399)
and under-predicts loss by 1.1-2.3 C. The agent_b implementation (12
different networks, only 5 shared, including Czech, Dutch, and US networks;
different forcing definitions) found matched donor-synchronous transfer of
only 0.490, with uniform-block matched transfer 0.944 and a much milder
uniform-on-donor-synchronous mismatch (0.524). The two implementations
differ in their 12-network panels and in the forcing definition (target
plus strongest donor masked with weaker donors remaining, versus target
plus air-temperature forcing). Until the panels, mechanisms, and forcing
are unified, no mechanism-matched transfer value is asserted; the
mechanism-dependence direction--matched curves beat mismatched curves, and
mismatch is asymmetric--is consistent across implementations and is
reported with the full divergence documented in Supporting Information.
The analytic conditional-covariance operator is likewise demoted to
Supporting Information: the quantity previously reported as a
"conditional-variance lower bound" is code-defined as the expected Gaussian
MAE, sqrt(2/pi) times the mean per-day conditional standard deviation. Its
mean conditional SD rose only from 0.475 C at 7 days to 0.565 C at 365
days while realized MAE grew from 0.544 to 4.719 C; the incremental R2
added after the simple model was 0.0171 (linear) and 0.701 to 0.704
(learned nonlinear model), far below the planned 0.05 threshold. The
saturation mechanism is real, but the bound is an optimal Gaussian
benchmark, not a general lower bound on recovery error.

## 4. Discussion

Four judgments organize what this revision can and cannot claim.

First, historical error persistence is real. Fitting-period block stress
curves, built and applied model-conditionally inside the fitting record,
ranked that same model's future recovery error on outcome-disjoint networks
at directly supported horizons (network-level Spearman 0.80; station-gap
0.945), and the ordering is a within-network property: network-demeaned
pooled Spearman 0.936, median within-network Spearman 0.965, while a
network-difficulty benchmark reaches only 0.326 pooled. The ordering is
stable across rolling-origin cutoffs (Kendall's W 0.81-0.92), requires
roughly four years of fitting history, and is essentially unaffected by the
shorter training length of the stress model relative to deployment. A
network's risk profile cannot be read off a network mean; it has to be
scored station by station and horizon by horizon.

Second, the incremental value beyond a station's own history is modest. The
station x horizon historical mean of the network's own fitting-period
losses nearly matches the full season-stratified curve on the same 874
units (pooled 0.942 versus 0.945), with a paired network-level difference of
+0.042 whose 95% CI straddles zero, and the two predictors correlate 0.992.
The empirical curve's large advantage is over simple structural descriptors
(+0.552 paired network-level), not over the station-by-horizon record, and
on the full panel even the network historical mean out-ranks the empirical
curve at the network level. The contribution of the season-stratified curve
is therefore prospective utility, model conditionality, and interpolation
of unsupported durations--not rank-magnitude superiority over the strongest
fitting-record baseline. This must be stated plainly in every summary,
including the abstract, and the v4 protocol accordingly compares against
deployable comparators rather than repeating a rank-superiority claim.

Third, prediction does not automatically translate into intervention value.
The same predictor that ranks future loss well fails as a fixed-budget
triage instrument (CapturedLoss@20% 0.337 versus 0.512 for simple
descriptors; paired -0.174): a high predicted MAE is not a high treatment
benefit, because the treated set is evaluated on loss captured or on
downstream distortion relative to a default, not on prediction error, and
the fallback tier under-ranks the 365-day loss mass (predicted 1.33 C
versus observed 5.27 C) that dominates any budget. Downstream, the
direction of the benefit flips with the untreated baseline: reconstruction
reduces integrated-metric distortion by 12-14% relative to no-fill but
worsens threshold-extreme distortion by 18-43% relative to climatology
fill. Any decision instrument must therefore be designed against the
default handling actually used downstream, in the incremental-benefit form
B = D(default) - D(model) - lambda*C, with cost on the same scale as
distortion.

Fourth, support and model matching determine when decisions can be
released. Where no same-duration, same-season curve exists, the network-
mean fallback destroys within-network ordering and the 365-day
extrapolation fails (coverage 46.8%); the continuous surface repairs the
interpolation range and provides honest intervals, but its pure-transfer
predictions are underdispersed and its extrapolation boundary is explicit.
Model selection helps only with per-unit stress support for every
candidate and explicit abstention--regret 0.0067 at 8.5% coverage, an
order of magnitude below comparators--and coverage floors are required
before that result is deployable. Stress curves are model-conditional
instruments: they transfer across engineered-regression families but not
across architecture families (BiLSTM cross-instance transfer 0.29-0.69
with a 0.067 correlation to the regression stress axis), and the
missingness-mechanism matrix, while directionally consistent, is not yet
harmonized between implementations. Environmental shifts add a further
boundary: fitting-period covariance need not transport through changed
thermal regimes, as the earlier Chattahoochee case illustrated (predicted
skill 0.414, observed -0.300 after a thermal-state shift).

Several limitations remain. The direct-support ranking claim is strong only
where the exact station-season tier exists (841 of 874 units in the second
panel); station- and network-duration tiers are nearly empty in that panel,
the network-mean fallback is weak, and the 365-day horizon is unusable
without real fitting-period support. The surface was tuned on four fit
durations, its absolute calibration requires external recalibration, and
its 365-day widening was insufficient. The model matrix rests on 12
networks for the neural row and 8 for the process row, and the BiLSTM row
mixes two instances of the family. The missingness matrix uses 12 networks
per implementation with conflicting panels and forcing definitions, and a
drought/low-flow mechanism could not be run for lack of discharge data in
the confirmation panels. Downstream metrics were scored on 15 networks with
one reconstruction family and two of three prespecified defaults; the
climatology-default leg is implementation-specific and the interpolation
leg is unscored. Heterogeneity strata (HUC2 climate bands, GAGES-II
major-dam presence) are broad and descriptive, and provider-specific QC and
day definitions may contribute to domain shifts. Finally, every revision
analysis reuses already-scored panels; none is independent confirmation,
and the second panel itself is internally hash-bound but not externally
preregistered.

## 5. Conclusions

Historical block stress tests, built and applied model-conditionally, are
informative screens for future stream-temperature recovery error at
directly supported horizons, not the strongest tested screen overall. On
the outcome-disjoint second panel, direct-support network Spearman was 0.80
and station-gap Spearman 0.945, carried by exact station-season curves
(0.887) and reflecting within-network station-horizon ordering that
persists across horizons, cutoff choices, and fitting histories of at least
four years. The signal is persistence-driven: a station-by-horizon
historical mean from the same record nearly matched the full curve (pooled
0.942 versus 0.945; paired network difference +0.042 with CI straddling
zero), so the seasonal increment over station history is modest. Four
conditions bound every use of the screen. First, support must be explicit:
network-mean fallbacks weaken pooled ranking, the 365-day horizon is
extrapolation that fails (coverage 46.8%) and is supported only by real
same-horizon fitting curves, and stress curves must be matched to the
missingness mechanism (directionally, in a matrix not yet harmonized
between implementations). Second, the screen is model-conditional: it
transfers across engineered-regression families but not across architecture
families, so per-model curves are required for selection. Third, decision
value is conditional and partly negative: fixed-budget triage with the
frozen empirical predictor is the worst non-random policy (CapturedLoss@20%
0.337), model selection reaches regret 0.0067 only at 8.5% coverage as a
proof of concept, and downstream benefit depends on the untreated baseline
(12-14% distortion reduction versus no-fill for integrated metrics but
18-43% worse than climatology for threshold extremes). Fourth, every
analysis to date is post-hoc development on already-scored panels; only an
externally registered third panel under protocol v4, with coverage floors
of at least 50% of units and 60% of networks, a fixed-coverage
selection-regret primary endpoint against the strongest deployable
comparator, and power recomputed on that endpoint, can confirm the
selective benefit. No automatic filling or station removal is supported by
the present evidence.

## Open Research

Code, analysis configurations, provider request metadata, source-QC
summaries, derived station-gap losses, and figure inputs are organized in
the public repository described by the package manifest. Provider daily
observations are not redistributed unless the provider's terms explicitly
permit it; official retrieval routes and omission decisions are documented
in Supporting Information. The archival release and DOI have not yet been
minted: TODO BEFORE SUBMISSION--deposit the permitted package in a
persistent repository, insert the minted DOI in the manuscript and
repository metadata, and verify that every linked artifact resolves to the
deposited version. No placeholder DOI should be cited as an archived
record.

The third confirmation follows protocol v4 (drafted in this revision
folder; to be consolidated at `paper/development_v13/protocol_v4.md`),
which replaces protocol v3 after review. Protocol v4 fixes the provenance
flaw of the internally hash-bound second panel (whose amendment and
outcomes shared one version-control commit) by requiring, before any
third-panel outcome is opened: (i) a separate public commit containing the
protocol, the exact roster, endpoint definitions, margins, and the power
analysis; (ii) an external OSF/Zenodo registration of that content with a
minted handle; and (iii) an outcome-scoring commit referencing the
registration. The target is 80-120 outcome-disjoint scored networks with
the same domain quotas as v3. The primary endpoint is the fixed-coverage
network-balanced selection-regret difference between the support-aware
selector and the strongest deployable comparator (a leave-one-network-out
nested-CV selector), evaluated at coverage floors of at least 50% of units
and 60% of networks (70% design target), with success criteria of a paired
network-bootstrap 95% CI below zero and at least 20% relative regret
reduction, and power computed by simulation on the regret endpoint. Rank
comparisons against the station x horizon baseline are secondary with a
zero margin (direction-replication); the 365-day horizon is scored only
with real same-horizon fitting-period support and otherwise
forced-abstained; downstream endpoints use B = D(default) - D(model) -
lambda*C against climatology and interpolation defaults. All margins are
frozen before outcomes; amendments require a new external registration.

## Figure captions

Figure 1. Design, support tiers, and evidence provenance. Nested temporal
design (outer 70% fitting / 30% evaluation split; nested split inside the
fitting years; four stress durations with seasonal placement strata), the
five-level support hierarchy, the interpolation and extrapolation regions
of the continuous surface, and the evidence-role labels (frozen /
post-hoc v13 development / future preregistered protocol v4) attached to
every reported quantity. Caption: "Historical block stress tests are
measured inside the fitting record of the same recovery model they rank;
support tiers and evidence labels make the provenance of every prediction
explicit."

Figure 2. Strongest-baseline external comparison (second panel, 874 direct
units). Left: observed versus predicted loss for the empirical curve, the
station x horizon historical mean (r6), simple descriptors, and the
hierarchical surface on identical units, with equal-network calibration
lines (empirical slope 0.938, R2 0.813; r6 slope 0.924, R2 0.789; simple
slope 1.157, R2 0.648; surface slope 1.326, R2 0.656). Right: paired
2,000-network bootstrap distributions of DeltaRho (empirical minus r6;
mean +0.042, CI [-0.0006, +0.1154]) and (empirical minus simple; +0.552,
CI [0.309, 0.814]), with the full-panel diagnostics inset (+0.109
[-0.126, 0.356] network; -0.095 [-0.158, -0.028] station-gap) labeled as
fallback-artifact. Caption: "On the same units, the stress test ranks
future loss well at directly supported horizons, but the station-by-horizon
historical mean nearly matches it; the large paired advantage is over
simple descriptors, and it disappears where the network-mean fallback
applies."

Figure 3. Duration and support. Common-axis plot of mean realized loss
versus gap duration (7-365 days) with the surface's monotone duration
curve (14- and 60-day interpolation flagged; 365-day extrapolation
flagged), the tier structure (exact 841 units, network Spearman 0.887;
fallback 596 units, 0.562), the 365-day tail (90% coverage 46.8% versus
92.5% overall), and the abstention trade-off (8.6% of units carrying 28.9%
of loss; released-unit network Spearman 0.691, R2 0.663). Caption:
"Support degrades monotonically with distance from the exact
station-by-season cell; interpolation works, and extrapolation beyond 180
days fails."

Figure 4. Coverage-regret (decision experiment). Left: model-selection
network-balanced regret versus fraction of units released under the
ambiguity x support-any abstention rule (operating point: 123 units, 8
networks, 8.5% coverage, regret 0.0067), with comparators re-evaluated on
the same released sets and the protocol-v4 coverage floors (>=50% units,
>=60% networks) marked. Right: Part-1 budget curves (CapturedLoss@B, B =
5/10/20/30%; empirical 0.337 at 20% versus simple 0.512, surface 0.500,
gap length 0.498, random 0.200, oracle 0.529) with bootstrap bands.
Caption: "Decision value is conditional: selection gains require per-unit
support and abstention and remain a proof of concept below the coverage
floors; the frozen empirical predictor is the worst non-random fixed-
budget triage policy."

Figure 5. Downstream incremental benefit. Per-metric aggregate distortion
reduction at a 20% treatment budget for risk, gap-length, and random
policies relative to each untreated default (no-fill: degree days 39.5%
versus 34.4% versus 17.1%; climatology fill: degree days -17.9%, days
above 25 C -42.5%, amplitude -33.8%, summer mean -23.0%, annual mean
+2.2%), read through B = D(default) - D(model) - lambda*C. Caption:
"Downstream benefit is baseline-dependent: reconstruction protects
integrated metrics relative to no-fill but can exceed climatology-fill
distortion for threshold extremes; the design target is incremental benefit
over the default handling, not raw MAE."

## References

See the repository bibliography; citations use the keyed reference list
maintained with the manuscript.

---

## Editorial note: review-text versus artifact discrepancies (v13_a)

This manuscript was written against the artifact CSVs under
`results/revision_v12/`; every number above was verified against those
files. The following discrepancies between the review text (and the v12
manuscript) and the artifacts were found and resolved as stated:

1. Network-count bug (review item 8). The v12 manuscript stated the second
panel contains "35 US, 15 Czech, and 10 Norwegian" (=60). The artifact
`t01_paired_comparison/agent_a/predictions.csv` (1,446 rows) shows 57
networks: 32 US (703 units), 15 Czech (478 units), 10 Norwegian (265
units). Adopted: 32/15/10 everywhere.

2. Paired DeltaRho (empirical minus r6) confidence interval on direct_874.
The v12 manuscript printed +0.042 with CI [0.0001, 0.1117] (excluding
zero). The agent_a artifact `t03_baseline_ladder/agent_a/paired_bootstrap.
csv` gives mean +0.041749 with CI [-0.000588, +0.115431] (straddling
zero); the agent_b artifact `paired_delta_vs_r6_station_x_horizon.csv`
gives mean +0.041916 with CI [0.000065, 0.111694] (excluding zero). The
two implementations agree on the mean but disagree on the CI; the review
adopted the agent_a CI. Adopted: mean +0.042, CI [-0.0006, +0.1154]
(straddling zero), with the implementation divergence noted.

3. Predictor correlation. Review text says the empirical predictor and r6
"correlate approx. 0.992". Computed on the 874 direct units from
`unit_predictions_second.csv`: Pearson 0.9917, Spearman 0.9959. Adopted:
"0.992 (Pearson; Spearman 0.996)".

4. CapturedLoss@20% point values. Review text: 0.338 (empirical) versus
0.512 (simple). The point estimates in `utility_table_part1.csv` are
0.3367 and 0.5145; the bootstrap means in `bootstrap_part1.csv` are
0.3377 and 0.5119 with CIs [0.3019, 0.3799] and [0.4852, 0.5372]. Adopted:
0.337 and 0.512 (bootstrap means), CIs [0.302, 0.380] and [0.485, 0.537];
paired difference -0.174 [-0.198, -0.140] verified exactly.

5. Rolling-origin network Spearman. The v12 manuscript reported 0.984,
0.944, 0.911 at 60/70/80% cutoffs; those values could not be reproduced
from the artifacts. The agent_a artifact `t07_rolling_origin/agent_a/
rolling_origin_metrics.csv` (supported-only) gives 0.947 (14 networks),
0.922 (20), 0.949 (20); Kendall's W is 0.811 (agent_b,
`rolling_origin_rank_stability.csv`, tie-adjusted, 13 networks) to 0.917
(agent_a). Adopted: 0.947/0.922/0.949 with the 60% attrition and the W
range 0.81-0.92 reported.

6. Missingness donor-synchronous transfer. The v12 manuscript asserted
0.979 without qualification. The two implementations disagree:
`t06_missingness_matrix/agent_a/mechanism_metrics.csv` gives 0.979
(network-level, 12 networks) while `t06_missingness_matrix/agent_b/
mechanism_metrics.csv` gives 0.490 (supported network-level, 12 networks).
The panels share only 5 of 12 networks (verified against
`network_panel.csv` and `provenance.json`), and the forcing definitions
differ (agent_a: target + strongest donor masked, weaker donors remain;
agent_b: target + air-temperature forcing). Adopted: no single value
asserted; the matrix is demoted to Supporting Information with both
implementations documented.

7. BiLSTM "self-transfer" relabeling (review item 6). The 0.29-0.69 range
combines two instances of the BiLSTM family: agent_a convention 0.2848
(`matrix_network_spearman.csv`, target = newly trained mask-aware BiLSTM)
and agent_b convention 0.6848 (`agent_b/matrix_network_spearman.csv`,
target = older frozen bounded-run predictions). Adopted: relabeled
"cross-instance BiLSTM-family transfer" with both conventions reported;
median best epoch 68 (68.5 over 36 runs) and 27.8% epoch-cap rate verified
from `neural_source_stress.csv`.

8. 365-day extrapolation rank. Review text: rank 0.270, 90% coverage
46.8%. Verified: `t04_risk_surface/agent_a/evaluation_second_panel.csv`
gives network Spearman 0.2699 (pooled 0.4111) on the 124 extrapolated
units; coverage 46.8% (overall 92.5%, direct 96.0%, interpolated 98.2%) is
reported in `t04_risk_surface/agent_a/REPORT.md` (not in a CSV; noted).
Adopted: 0.270 (network-level) and 46.8%.

9. First-panel direct comparison (858 units, 42 networks). Review text:
paired DeltaRho approx. +0.0024 with CI [-0.0239, +0.0262]. Verified
exactly from `t03_baseline_ladder/agent_a/paired_bootstrap.csv` (mean
+0.002444, CI [-0.023881, +0.026164]); ladder r6 pooled 0.824966 /
network 0.798396 and empirical pooled 0.825422 / network 0.800502 verified
from `master_ladder_table.csv`.

10. Downstream baseline-dependence (review item 5). The v12 manuscript
reported only the no-fill-baseline results. The agent_a climatology-fill
results in `t08_downstream_metrics/agent_a/budget_combined.csv` verify the
review's numbers exactly: degree days -17.9%, days > 20 C -22.2%, days >
25 C -42.5%, amplitude -33.8%, summer mean -23.0%, annual mean +2.2%,
combined -17.7%. Adopted: both baselines reported; no-fill ratios 0.124-
0.138 (12-14%) verified from `agent_b/metric_error_summary.csv`; zero-error
fractions 88.9/95.3/88.4% and the 20.9% amplitude uncomputability verified
from `placement_metrics.csv` and `uncomputable_no_fill.csv`.

11. Model-selection numbers (review item 3). Verified exactly:
no-abstention regret 0.084 (0.0838) versus best-fixed 0.081 and global CV
0.081 (`bootstrap_part2.csv` 0.0815); per-network CV 0.038 (0.0383); with
ambiguity+support-any abstention (lambda = 0.5) regret 0.0067 (0.006720)
with CI [0.0019, 0.0120], 123 released units, 8 of 42 networks, 8.5%
coverage (replicated from `selection_predictions_part2.csv`: released =
not ambiguous and all families unit-supported). The 365-day fallback
under-prediction (mean 1.326 C predicted versus 5.265 C observed; 28.9%
of total loss in 8.6% of units) verified from `predictions.csv`.

12. First-panel and development composition. 42 networks / 1,440 units
(first) and 55 networks / 217 stations / 1,260 units (development) carried
from the v12 manuscript; the first-panel counts are consistent with
`master_ladder_table.csv` (direct_858, all_1440) and
`selection_predictions_part2.csv` (1,440 rows). The development
station-gap count is not re-derivable from the revision_v12 artifacts and
is flagged as carried over.

13. Surface and tier numbers (review item 1 context). Verified from
`master_ladder_table.csv` (r6 direct_874: pooled 0.942387, network
0.763223, slope 0.923549, R2 0.789317, RMSE 0.483624; all_1446: pooled
0.735288, network 0.725564), `t02_support_hierarchy/agent_a/
tier_metrics_second.csv` (exact 841 / 0.887 / 0.968; fallback 596 / 0.562
/ 0.339), and `t04_risk_surface/agent_a/evaluation_second_panel.csv`
(surface full 0.893 pooled / 0.674 network / R2 0.475; fallback 572:
0.846/0.879/0.38; interpolated 448: pooled 0.774, slope 1.025;
first-panel cross-check 0.898 versus 0.767).
