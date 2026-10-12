# Historical block stress tests rank future model-specific reconstruction error across stream-temperature networks

## Key Points

- Within-network historical block stress tests, built and applied
  model-conditionally inside the fitting record, ranked that same recovery
  model's future reconstruction error on an outcome-disjoint panel of 57
  networks at directly supported horizons (network-level Spearman 0.805,
  paired +0.55 against simple descriptors on the same 874 units).
- The ranking is carried by exact station-by-season curves: the exact
  station-by-duration-by-season tier alone reaches network Spearman 0.887,
  while network-mean fallbacks and 365-day extrapolation weaken or fail, and
  a continuous support-aware surface interpolates well but cannot
  extrapolate.
- Difficulty ordering is shared within an engineered-regression block of
  recovery models but is pipeline-specific across architecture families and
  missingness mechanisms; decision value emerges only with support-aware
  abstention and requires external validation.

## Plain Language Summary

A failed logger can leave weeks of missing stream temperature while nearby
stations and weather data remain available. Managers need to know how much
recovery error a gap will cause before the truth for that gap exists. We
tested the recovery model itself: we cut artificial gaps into the earlier,
already-observed part of each record, measured how well the model recovered
them, and asked whether that historical stress curve predicts the model's
error on real future gaps. On 57 river networks not used to build anything,
the stress curve ranked future recovery error best at the gap lengths and
seasons where a same-record trial curve existed (network Spearman 0.805).
Most of that strength comes from exact station-season curves; a network
average is a weak substitute and 365-day predictions are extrapolation that
fails. The ordering is shared among regression-style recovery models but not
with neural or process-based models, and a stress curve built for one kind of
missingness (for example, gaps that also take down neighboring stations)
badly misranks other kinds. These results support using historical stress
tests as model-conditional screening tools. They do not support automatic
filling or removal of monitoring stations, and decision use requires
explicit support checks, calibrated abstention, and independent validation.

## Abstract

Equal-length stream-temperature outages can have very different recovery
losses, and that loss is specific to the recovery model: the error a
gradient-boosting reconstruction will make is not the error a neural or
process-based model will make. We therefore framed the problem as
model-conditional historical stress testing: cut seasonally stratified
artificial gaps into the fitting years of a record, measure the intended
recovery model's error on them, and use that curve to rank the model's
future recovery loss. Development used 55 river networks and a first panel
of 42 networks for method development; a second, outcome-disjoint panel of
57 networks from North America and Europe provided independent evaluation.
On the 874 units at the four directly supported horizons (7, 30, 90, and
180 days), the stress test ranked later loss with network-level Spearman
0.805 and station-gap Spearman 0.945, versus 0.248 and 0.846 for the
simple-descriptor model on the very same units (paired differences +0.55,
95% CI [0.31, 0.81], and +0.098 [0.06, 0.14]). The ranking is carried by
exact station-by-season curves (841 of 874 units; network Spearman 0.887).
Across all 1,446 units, the network-level advantage shrank to +0.109
(CI [-0.13, 0.36]) because the 596 network-mean fallback units destroy
within-network ordering, and a continuous support-aware surface interpolated
the unsupported 14- and 60-day horizons well (calibration slope 1.03) but
failed at the extrapolated 365-day horizon (90% coverage 46.8%). Stress
curves transferred across engineered-regression recovery families (self- and
cross-transfer 0.72-0.98) but not to a properly trained bidirectional LSTM
or an air2stream-equivalent process model, and a uniform-grid curve applied
to support-destroying missingness mechanisms collapsed rank (0.88-0.98 to
0.20-0.40). The analytic conditional-covariance risk saturated with gap
length while realized loss continued to grow, and its value after simple or
empirical predictors was negligible. For fixed-budget prioritization the
empirical predictor was the worst non-random policy (CapturedLoss at a 20%
budget 0.338 versus 0.512 for simple descriptors), but with per-model stress
support and explicit abstention, risk-based model selection achieved
network-balanced regret 0.0067, an order of magnitude below fixed selection.
Historical block stress tests are therefore model-conditional screening
tools whose decision value requires model-specific curves, support-aware
abstention, and independent validation; no automatic filling or station
removal is supported.

## 1. Introduction

A failed logger can leave weeks or months of missing stream temperature
while boundary observations, neighboring stations, weather records, and
discharge remain available. Gap-filling studies usually ask which model
reconstructs missing values best [@li2017streamairimputation;
@bal2023streamtemperature]. A monitoring manager faces an earlier question:
for this outage geometry and this recovery model, how much error should be
expected before the missing truth becomes available? The answer is
inherently model-specific: a reconstruction family's error on a given gap is
a property of that family's fit, its features, and its sensitivity to the
outage, not a property of the gap alone. This paper develops and evaluates
one answer to that question: a historical block stress test, in which
artificial gaps are cut into the already-observed fitting years of the
record and the intended recovery model is scored on them, so that the
resulting curve inherits the model's own error structure.

Several mature literatures bear on predicting recovery error. Gaussian
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
metrics on outcome-disjoint networks. Artificial or trial gaps are
established tools for stress-testing recovery methods
[@moffat2007gap; @richardson2007longgaps]; we do not propose the trial-gap
idea itself as new. Our contribution is the model-conditional evaluation:
whether a fitting-period error curve ranks the same model's future error
across a panel of wholly unseen networks, why the ranking is strong where
it is and fails where it fails, and what that implies for decisions.

Uncertainty metrics can mislead precisely because they are not realized
model error. Classical kriging variance can understate prediction variance
when covariance parameters are estimated [@denhertog2006kriging], and a
value-independent variance need not represent local error dispersion
[@yamamoto2000kriging]. Hydrological conformal prediction similarly
distinguishes point prediction from calibrated uncertainty and shows that
local information may be insufficient for extremes [@auer2024uncertainty].
A valid test must therefore connect a pre-evaluation risk to observed
recovery loss of the same model, leave out whole river networks, and carry
the result through calibration and decisions.

Our design is within-network historical stress testing replicated across an
outcome-disjoint network panel. For each network, seasonally stratified
artificial gaps are placed wholly inside the fitting years of the record and
recovered with the intended model; the resulting station-by-duration-by-
season curve is the predictor. Because the curve is measured on the same
stations, same seasons, and same recovery model as the evaluation gaps, it
captures local donor behavior, seasonal dynamics, and model error in the
same units as the target loss. Support is explicit: exact local curves,
station- and network-duration fallbacks, a network-mean fallback, and a
continuous support-aware risk surface replace the earlier binary
supported/fallback split, so every prediction carries its support tier.
Three recovery-model families, a neural model, a process model, seven
missingness mechanisms, and two decision experiments delimit the claim.

We ask three questions. First, does a fitting-period stress curve rank later
recovery loss of the same model on outcome-disjoint networks, and where does
the ranking live: at exact support tiers, across horizons, and within
networks? Second, how model-conditional is the difficulty ordering: does it
transfer across recovery-model families and across missingness mechanisms,
and how do the analytic covariance alternative and a continuous risk
surface compare? Third, what is the decision value: fixed-budget
prioritization, model selection with abstention, and protection of
downstream thermal-regime metrics, and what external validation would
certify it? The river network is the primary extrapolation unit throughout
(Figure 1).

## 2. Methods

### 2.1 Study phases and data

The development collection combined 55 river networks, 217 stations, and
1,260 station-gap units for which temperature, meteorology, hydraulics,
analytic risk, and recovery outcome used identical fitting rosters. The
first confirmation panel contained 42 scoreable networks from North America
and Europe contributing 1,440 station-gap units, used for post-confirmation
method development. The second, outcome-disjoint panel scored 57 networks
(35 US, 15 Czech, and 10 Norwegian) contributing 1,446 units; no second-
panel network appeared in the development or first-panel outcome sets.

Daily mean stream temperature was the target. Calendar years were ordered
and the first 70% used for fitting; the remaining years supplied observed
truth for 7-, 14-, 30-, 60-, 90-, 180-, and 365-day artificial gaps. Each
station-gap cell used up to 20 placements distributed across eligible
evaluation windows. The primary loss was mean absolute error (MAE) in
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
fitting years only.

Two further families delimit the model conditionality of the stress test.
A bounded bidirectional LSTM sensitivity used artificial blocks only from
fitting years, up to five epochs, at most three placements per station-gap,
and was previously reported to hit its epoch cap in 92.9% of networks
without convergence. For this revision we trained a properly regularized
mask-aware bidirectional LSTM (hidden size 16, early stopping on a nested
fitting-period validation split, patience 12, three seeds) on 12 networks;
the median best epoch was 68 and only 28% of runs reached the epoch cap.
We also implemented the published eight-parameter air2stream state equation
and Crank--Nicolson update [@toffolon2015air2stream] in Python, calibrated
on train-only bounded multistart least squares; the outcome-blind subset was
eight second-panel US networks with 89 station-gap units. The air2stream
equivalent is US-only, and POWER local-solar versus USGS local-civil daily
windows share date labels but not identical 24-hour boundaries.

### 2.3 Model-conditional empirical transfer and support tiers

We nested a second chronological split inside the outer fitting years. The
first 70% of those years fit the same gradient-boosting recovery family; the
remaining fitting years supplied observed artificial-gap truth. For 7-, 30-,
90-, and 180-day gaps, candidate starts were divided into DJF, MAM, JJA, and
SON seasons and up to 20 placements were selected per season. Their mean MAE
formed a station-by-duration-by-season empirical curve before the outer
evaluation period began. Each prediction carries one of five support tiers,
from most to least specific: exact local support (station x duration x
season curve), station-duration support (season collapsed), network-duration
support (station collapsed), network-mean fallback (a network-wide mean of
all fitting-period losses), and unavailable. Units at unsupported horizons
(14, 60, 365 days) always fall to the network-mean tier. No outer evaluation
loss entered any source. Throughout, the curve is model-conditional: it is
built with the same recovery model whose future error it ranks, and its
transferability is evaluated per model in Section 3.4.

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
horizon is flagged extrapolation, and its 90% log-scale Gaussian interval
(width from sigma_e, sigma_network, sigma_station, and the fixed-effect
variance) is widened by a factor of 1.435. We evaluated the surface on the
second panel and cross-checked it by refitting on first-panel fit losses
only.

### 2.5 Missingness-mechanism matrix

On 12 first-panel networks (87 stations, 80,409 scored placements across
seven mechanisms), trial gaps were generated with a mechanism's own placement
distribution and recovered with the same XGBoost family, building a
mechanism-matched station-by-horizon curve; evaluation gaps (up to 20
placements per station-horizon) used the same mechanism. Mechanisms were:
uniform single block; multi-block (total length split into 2-8 blocks
separated by short observed runs); summer-biased; high-temperature-biased;
donor-synchronous (target and all donors masked); target-plus-primary-
covariate (target and strongest donor masked, weaker donors remain); and
online left-boundary recovery. A mismatch experiment then applied the
uniform-block curve to every other mechanism's evaluation gaps, quantifying
both rank and magnitude consequences.

### 2.6 Rolling-origin and history-length stability

Ranking stability was tested by moving the outer chronological cutoff to
60, 70, and 80% of each record on a 20-network first-panel subset, rebuilding
the stress curve strictly inside each training block (10 placements per
season), and comparing predicted network ranks across cutoffs with Kendall's
W. A history-length learning curve fit the stress model on the first 2, 4,
6, 8, and full years of the record on 20 networks with fixed evaluation
windows. Training-length comparability was tested by building deployment-
matched curves with the full 70% training block and comparing them with the
standard 49%-length stress curves on the same 635 supported cells.

### 2.7 Downstream thermal-regime metrics

On 15 first-panel networks (1,755 placements at 7-, 30-, and 90-day gaps),
each reconstruction was inserted into the evaluation-period daily record and
ten thermal-regime metrics were recomputed: annual mean, summer (JJA) mean,
amplitude (July minus January mean), phase (day of peak), 90th percentile,
summer maximum, days above 20 and 25 C, degree days above 10 C, and trend
slope. Distortion was the absolute difference from the truth record; the
no-fill alternative dropped gap days (the status quo for downstream users).
We correlated the fitting-period empirical risk score with per-metric
distortion at the network level and ran a budget experiment protecting the
top 20% of gaps by risk, by gap length, and at random, reporting reduction
in aggregate distortion relative to no treatment.

### 2.8 Decision experiments

Part 1 (second panel, 1,446 units, 57 networks): units were ranked by seven
scores--raw gap length, a duration-plus-season fit, the simple-descriptor
model, the frozen empirical predictor, the hierarchical surface, random,
and an observed-loss oracle--and the top 5, 10, 20, and 30% of units were
awarded their observed loss. CapturedLoss@B was the fraction of total loss
in the top-B set; NDCG@B the position-discounted normalized gain; paired
differences used a 2,000-draw network bootstrap.

Part 2 (first panel, 1,440 units, 42 networks): for each of three recovery
families (seasonal-boundary ridge, donor ridge, XGBoost), a per-family
fitting-period stress curve was built (unit-level curves where placements
exist, pooled duration curves otherwise), recalibrated to the outer-loss
scale, and penalized by family-specific interval width. The selector picked
the family with the lowest penalized risk and could abstain when (i) the two
best penalized risks were within 10% (ambiguity) or (ii) any family lacked
unit-level stress support. Regret was the network-balanced mean of
(selected loss - best-family loss); comparators were best-fixed-family,
global leave-one-network-out CV, per-network average CV, a gap-length rule,
and random.

### 2.9 Inference, calibration, and intervals

All predictions left out complete networks. Results report network-level
Spearman (over network means) first, followed by pooled station-gap and
within-network rank as diagnostics. Calibration intercept and slope used
weights inversely proportional to the number of station-gap rows in each
network. Network bootstrap intervals resampled rivers (2,000 draws). The
same-unit paired comparisons of Section 3.1 computed both predictors on
identical unit subsets and paired the bootstrap differences within
resampled networks.

### 2.10 Evidence roles and third-confirmation rule

The first-panel analyses and the second panel were confirmed or developed in
sequence as previously reported: the second panel was internally frozen and
hash-bound before its outcomes were scored, but because its amendment and
outcomes entered version control in the same commit, it is not externally
verifiable preregistration. All revision analyses (paired comparisons,
support hierarchy, risk surface, model and missingness matrices, rolling-
origin, downstream metrics, decision experiments) are method development on
already-scored panels and are not independent confirmation. A third
confirmation protocol (protocol v3) is drafted: 80-120 scored networks
outcome-disjoint from all previous panels, endpoints and margins frozen
before outcomes, and external timestamping via a separate public pre-
outcome commit and OSF/Zenodo registration (Section Open Research).

## 3. Results

### 3.1 Outcome-disjoint panel: same-unit paired comparisons

At the four directly supported horizons, the empirical predictor covered
874 second-panel units and reached station-gap Spearman 0.945, network-level
Spearman 0.805, and equal-network calibration slope 0.938. On the same 874
units, the simple-descriptor model refit on fitting-period data only reached
0.846 station-gap, 0.248 network-level, and slope 1.157. The paired
difference within a 2,000-draw network bootstrap was +0.552 (95% CI
[0.309, 0.814]) at the network level and +0.098 ([0.059, 0.142]) at the
station-gap level, both excluding zero; the empirical predictor won the
within-network rank comparison in 41 of 57 networks (0.719). Per horizon,
empirical network Spearman was 0.932 (7 d), 0.916 (30 d), 0.865 (90 d), and
0.659 (180 d), against 0.374, 0.153, 0.043, and 0.164 for the simple model;
the advantage is largest at short horizons and remains positive at 180 days.

The strongest fitting-record comparator--the station-by-horizon mean of the
network's own trial gaps--nearly matched the empirical curve in pooled
ordering on the direct subset (0.942 versus 0.945) while the paired
network-level difference remained directionally positive (+0.042, 95% CI
[0.0001, 0.1117]); the simple-descriptor model, by contrast, ranked below
gap-only baselines at the network level on these units.

Across all 1,446 units, the empirical predictor reached 0.740 pooled and
0.715 network-level (slope 0.950) against 0.835 pooled and 0.605
network-level (slope 1.150) for the simple model. The paired network-level
difference was directionally positive (+0.109, 95% CI [-0.126, 0.356]) but
included zero, and the station-gap difference was negative (-0.095,
[-0.158, -0.028]): the 596 network-mean fallback rows are constant within a
network, destroy within-network ordering, and drag pooled rank below the
simple model. The full-panel comparison is therefore an artifact-driven
diagnostic, not the paper's claim; the same-unit paired comparison at
directly supported horizons is.

### 3.2 Support hierarchy and the continuous risk surface

The direct-horizon ranking is overwhelmingly carried by exact station x
duration x season curves: 841 of the 874 units (96.2%) had exact local
support, and that tier alone reaches network Spearman 0.887 and pooled
Spearman 0.968. The station-duration tier held only 9 units (2 networks) and
the network-duration tier 0 units in the second panel; 24 additional
direct-horizon units fell back to the network mean, so the fallback tier
totals 596 units (572 horizon-unsupported plus 24 direct-horizon without a
station curve), correcting the earlier count of 572. In the fallback tier,
network Spearman fell to 0.562 and pooled Spearman to 0.339, and
within-network rank is undefined by construction. First-panel and
development panels show the same structure (exact 673 and 635 units;
network-duration 107 and 183; fallback 660 and 637). Support quality
degrades monotonically with distance from the exact cell: on the second
panel, distance-0 units reach network Spearman 0.931, station-level
(distance < 100) 0.629, and network-level 0.759. A pure network-difficulty
control--the network historical mean of its own fitting losses--ranked the
full panel at 0.772, above the empirical predictor's 0.715, confirming that
the empirical advantage is carried by within-network ordering rather than
by separating persistent network difficulty.

The continuous support-aware risk surface fixes most of the fallback
deficit. On the second panel, its full-panel pooled Spearman was 0.893
(versus 0.740 for the old predictor), R2 0.475 (0.238), and RMSE 1.096 C
(1.320). On the 572 previously unsupported horizon units it raised network
Spearman from 0.597 to 0.846, pooled from 0.388 to 0.879, and R2 from -0.03
to 0.38. The 448 interpolated 14- and 60-day units were well calibrated
(pooled Spearman 0.774, calibration slope 1.025), in contrast to the old
constant fallback (0.451 and 0.509). The 365-day horizon is the hard
boundary: rank on the 124 extrapolated units was 0.270 and 90% interval
coverage was 46.8% despite the pre-specified widening. Overall 90% coverage
was 92.5%; abstaining the 124 extrapolated units raised released-unit
network Spearman to 0.691 and R2 to 0.663. Pure-transfer predictions are
underdispersed (calibration slopes 1.3-2.3), so absolute magnitudes require
external recalibration. Cross-checking on the first panel, where both models
fit from the same fit losses, the surface beat the old predictor on every
metric (network Spearman 0.898 versus 0.767), including its 660 fallback
cells (0.874 versus 0.504).

### 3.3 Per-horizon, within-network, and historical stability

The network-level 0.805 is not an artifact of persistent network difficulty:
a predictor that perfectly separates network means reaches pooled Spearman
of only 0.326 in-sample, while the empirical predictor's network-demeaned
pooled Spearman is 0.936 on the direct subset and its median within-network
Spearman is 0.965. The ranking lives inside stations and horizons, not
between networks, and it is stable in time. Moving the outer cutoff from 60
to 70 to 80% of each record reproduced network Spearman of 0.984, 0.944, and
0.911 (the 60% leg attrites to 13 networks because early years lack complete
donor rosters), and the predicted network ranks agreed across cutoffs with
Kendall's W of 0.811. History length matters: network Spearman rose from
0.608 with 2 years of fitting history to 0.872 at 4 years, 0.916 at 6, 0.938
at 8, and 0.944 with the full record, implying a minimum usable fitting
history of roughly 4 years. The concern that the stress model trains on less
record than the deployed recovery model (49% versus 70% of years) is
empirically negligible: paired MAE difference 0.013 C and Spearman 0.989
between the two stress curves on the same cells.

### 3.4 Model-source by model-target transfer matrix

Recoverability difficulty is shared within architecture families but is
pipeline-specific across them. Within the engineered-feature block (linear/
PCHIP boundary, seasonal-boundary ridge, donor ridge, XGBoost), self-
transfer network Spearman was 0.93-0.98 and cross-transfer within the block
0.72-0.98: the XGBoost stress curve predicted the outer losses of the
boundary and ridge families almost as well as its own. A properly trained
bidirectional LSTM (early stopping, three seeds, 12 networks; median best
epoch 68, 28% hitting the epoch cap versus 92.9% for the old bounded run)
tells a different story: its self-transfer was 0.29-0.69 across granularity
conventions, its cross-transfer to the engineered block was -0.24 to +0.28,
and its fitting-period stress correlated only 0.067 with the XGBoost stress
on the same networks--the two families disagree about which networks are
hard. The air2stream-equivalent process model showed weak self-transfer
(0.64 on 8 networks) and null-to-negative cross-transfer (about 0.24 from
XGBoost). Overall, the diagonal (self-transfer, mean 0.783) exceeds the
off-diagonal (mean 0.434; one-sided Mann-Whitney p = 0.033), but that gap is
driven entirely by the neural and process rows: inside the engineered block
the off-diagonal cells are nearly saturated. Cells resting on 4-8 networks
are fragile and reported with their counts.

### 3.5 Missingness-mechanism matrix

Stress curves are mechanism-specific instruments, not generic curves. A
mechanism-matched curve transferred positively for every mechanism tested on
12 networks (80,409 placements): multi-block 0.944, donor-synchronous 0.979,
target-plus-primary-covariate 0.881, online left-boundary 0.930, uniform
0.531-0.622, summer-biased 0.594, and high-temperature-biased 0.580 at the
network level, with matched calibration slopes 0.89-1.01. The uniform-grid
curve applied to support-destroying mechanisms collapses: donor-synchronous
rank fell from 0.979 to 0.294, target-plus-primary-covariate from 0.881 to
0.196, and online from 0.930 to 0.399, under-predicting loss by 1.1-2.3 C;
the multi-block calibration slope collapsed from 0.90 to 0.14 (the uniform
curve over-predicts fragmented gaps about twofold). Seasonal placement bias
is the mildest mismatch, acting mostly as a shift that calibration absorbs;
the reverse direction (seasonal curve on uniform gaps) degrades from 0.53 to
0.31, so mismatch is asymmetric. A single uniform stress curve should not be
transferred across missingness mechanisms.

### 3.6 Covariance mechanism, estimand-corrected

The analytic conditional-covariance operator contributes little, and the
earlier mechanism narrative mislabeled its estimand. The quantity reported
as a "conditional-variance lower bound" is code-defined as the expected
Gaussian MAE, sqrt(2/pi) times the mean per-day conditional standard
deviation--neither a variance nor a standard deviation. Under the corrected
reading, mean conditional SD rose only from 0.475 C at 7 days to 0.565 C at
365 days, the expected Gaussian MAE from 0.379 to 0.451 C, while realized
MAE grew from 0.544 to 4.719 C (realized RMSE 0.631 to 5.755 C). The
remainder--MAE excess over the Gaussian bound--grew from 0.165 to 4.268 C,
but it is not identifiable as model error plus drift: it also contains
covariance misspecification, parameter-estimation error, non-Gaussianity,
aggregation, and finite-sample error (plug-in covariance is downward-biased
at small training sizes in simulation). The incremental-value conclusion is
unchanged: the operator added linear R2 of only 0.0171 after the simple
model and moved a learned nonlinear error model from 0.701 to 0.704, far
below the planned 0.05 threshold. The saturation mechanism is real--the
Gaussian bound flattens while realized long-gap loss accumulates--but the
bound is an optimal Gaussian benchmark, not a general lower bound on
recovery error.

### 3.7 Downstream thermal-regime metrics

Reconstruction substantially reduces distortion of ecologically relevant
metrics relative to no-fill. For integrated metrics, reconstructed error was
12-14% of no-fill error for degree days, annual mean, and trend slope, and
30-37% for the 90th percentile, amplitude, and days above 20 C. Single-event
metrics were barely distorted at all (zero reconstruction error in 88-95%
of placements for days above 25 C, summer maximum, and phase), and
reconstruction restored computability: no-fill leaves amplitude undefined
in 20.9% of placements, and reconstruction always returns a value. The
fitting-period risk score predicts distortion of the integrated metrics at
the network level (annual mean 0.764, degree days 0.743, phase 0.729, 90th
percentile 0.668) but not of amplitude (0.089) or summer maximum (0.250),
whose distortion is governed by gap geometry rather than reconstruction
error. In the budget experiment (top 20% of gaps), risk targeting beat
random by 1.9-4.0x on every metric except amplitude: degree-day error was
reduced 39.5% (risk) versus 34.4% (gap length) versus 17.1% (random), and
days-above-25-C error 10.9% versus 2.1% versus 3.6%. The risk score is
therefore a valid instrument for protecting integrated ecological metrics,
while threshold-extreme metrics on long summer gaps remain hard for any
MAE-type score.

### 3.8 Decision utility and abstention

For fixed-budget prioritization on the full second panel, the frozen
empirical predictor is the worst non-random policy. At a 20% budget,
CapturedLoss was 0.512 (95% CI [0.485, 0.537]) for the simple-descriptor
model, 0.504 for duration-plus-season, 0.500 for the surface, 0.498 for raw
gap length, and 0.338 ([0.302, 0.380]) for the empirical predictor (random
0.200, oracle 0.529); NDCG@20% was 0.908 for simple and 0.617 for empirical.
The paired bootstrap differences were -0.174 ([-0.198, -0.140]) for
empirical minus simple and -0.012 ([-0.031, +0.003]) for surface minus
simple. The failure is structural: the network-mean fallback tier under-ranks
the 365-day loss mass (mean prediction 1.33 C versus observed 5.27 C), which
carries 28.9% of total loss. Abstention does not rescue loss-capturing
budgets--abstaining the 124 extrapolated units removes 8.6% of units
carrying 28.9% of total loss--but it is justified for point-release
decisions, where the same abstention raises released-unit network Spearman
to 0.691 and R2 to 0.663.

For model selection (Part 2), on the full first panel the risk-based
selector does not beat a development-chosen fixed family or global
blocked CV (regret 0.084 versus 0.081; the winning families are nearly tied
in mean loss, donor ridge 1.270 versus XGBoost 1.274), and per-network
average CV (0.038) beats it. With abstention the picture reverses: when
every candidate family has unit-level fitting-period stress support (8 of
42 networks, 123 units, 8.5% of the panel) and ambiguity abstention is
applied, the selector's network-balanced regret drops to 0.0067
([0.0019, 0.0120]), an order of magnitude below every comparator on the
same released units (best fixed 0.151, global CV 0.151, per-network CV
0.164, gap-length rule 0.145, random 0.341). Ambiguity abstention alone
does not help--near-ties are cheap--the sharp lever is the support rule:
selection is only meaningful where per-unit fitting-period stress exists
for all candidates. Secondary heterogeneity (climate and regulation
effect modification) is reported in Supporting Information.

## 4. Discussion

The decisive result is methodological: test the intended recovery pipeline
inside its own fitting record, model-conditionally. Historical block stress
curves captured gap duration, season, local donor behavior, and model error
in the same units as the target loss, and on the outcome-disjoint second
panel they ranked that model's future error better than simple descriptors
on the same units (paired network-level difference +0.55). Three properties
of the result matter for practice.

First, historical difficulty persists, but it is a within-network property,
not a network-level one. The network-level Spearman 0.805 is the aggregated
expression of strong station-horizon ordering (network-demeaned pooled
Spearman 0.936; median within-network Spearman 0.965), while a network-
difficulty benchmark reaches only 0.326 pooled. The ordering is stable
across rolling-origin cutoffs (Kendall's W 0.811), requires roughly four
years of fitting history, and is essentially unaffected by the shorter
training length of the stress model relative to deployment. The practical
corollary is that a network's risk profile cannot be read off a network
mean; it has to be scored station by station and horizon by horizon.

Second, the difficulty ordering is model-conditional in a specific way: it
is shared across engineered-regression families (cross-transfer 0.72-0.98)
but not across architecture families. A properly trained LSTM and an
air2stream-equivalent process model define different difficulty axes, and
the neural family's fitting-period stress correlated only 0.067 with the
regression stress on the same networks. This is not a call for one
architecture over another; it is a constraint on how stress curves are
used. A stress curve is evidence about the model that produced it, and
model-selection or triage instruments must carry per-family curves rather
than a single generic score. The covariance alternative, by contrast,
saturates with gap length while realized loss grows, and its estimand is an
expected Gaussian MAE bound whose excess over realized loss is not
identifiable as any single component; it should not be presented as a
general lower bound on recovery error.

Third, support and mechanism matching are the binding constraints on
decision use. Where no same-duration, same-season curve exists, the network-
mean fallback destroys within-network ordering and the 365-day extrapolation
fails (46.8% coverage); the continuous surface repairs the interpolation
range and provides honest intervals, but its pure-transfer predictions are
underdispersed and its extrapolation boundary is explicit. And stress
curves are mechanism-specific instruments: a uniform-grid curve applied to
support-destroying missingness (donor-synchronous, forcing, online) both
misranks (rank 0.20-0.40) and under-predicts magnitude by 1.1-2.3 C. The
earlier planted field-outage geometry result--moderate retained ordering
with degraded calibration when most items lacked a same-horizon curve--is
the same phenomenon: trial gaps must be matched to the outage structure,
season, and the outage's effect on recovery information. Environmental
shifts add a further boundary: fitting-period covariance need not transport
through changed thermal regimes, as the earlier Chattahoochee case
illustrated (predicted skill 0.414, observed -0.300 after a thermal-state
shift).

Decision value is real but conditional. The empirical predictor is not a
good fixed-budget triage instrument on the full panel--CapturedLoss@20% of
0.338 is the worst non-random policy--and the surface and simple models are
statistically indistinguishable for loss capture. Model selection with
per-unit support for all candidates and explicit abstention reaches regret
0.0067, an order of magnitude below fixed selection; without abstention it
adds nothing. Abstention is justified for point-release decisions (the
extrapolated tail carries 28.9% of loss but cannot be ranked or covered),
not for loss-capturing budgets. Downstream, the risk score protects
integrated thermal metrics (degree days, annual mean) and restores
computability, but cannot order single-event metrics.

Several limitations remain. The direct-support ranking claim is strong
only where the exact station-season tier exists (841 of 874 units in the
second panel); station- and network-duration tiers are nearly empty in that
panel, the network-mean fallback is weak, and the 365-day horizon is
unusable. The surface was tuned on four fit durations, its absolute
calibration requires external recalibration, and its 365-day widening was
insufficient. The model matrix rests on 12 networks for the neural row and
8 for the process row; the air2stream equivalent replaces the original
optimizer and joins differing daily time conventions. The missingness
matrix uses 12 first-panel networks and one recovery family; a drought/low-
flow mechanism could not be run for lack of discharge data in the
confirmation panels. Downstream metrics were scored on 15 networks with one
reconstruction family. Heterogeneity strata (HUC2 climate bands, GAGES-II
major-dam presence) are broad and descriptive, and provider-specific QC and
day definitions may contribute to domain shifts. Finally, every revision
analysis reuses already-scored panels; none is independent confirmation.

## 5. Conclusions

Historical block stress tests, built and applied model-conditionally, were
the strongest tested screen for future stream-temperature recovery error.
On the outcome-disjoint second panel, direct-support network Spearman was
0.805 (paired +0.55 over simple descriptors on the same 874 units), carried
by exact station-season curves (0.887) and reflecting within-network
station-horizon ordering that persists across horizons, cutoff choices, and
fitting histories of at least four years. Three conditions bound the claim.
First, the screen is model-conditional: it transfers across engineered-
regression families but not across architecture families, so per-model
stress curves are required for selection. Second, support must be explicit:
network-mean fallbacks weaken pooled ranking, the 365-day horizon is
extrapolation that fails, and stress curves must be matched to the
missingness mechanism. Third, decision value requires model-specific
curves, calibrated abstention, and independent validation: fixed-budget
triage needs the support-aware surface or descriptor models, model selection
only helps with per-unit support and abstention, and no automatic filling
or station removal is supported by the present evidence. The third
confirmation panel, with endpoints and margins frozen before outcomes and
externally timestamped registration, is the required next test.

## Open Research

Code, analysis configurations, provider request metadata, source-QC
summaries, derived station-gap losses, and figure inputs are organized in
the public repository described by the package manifest. Provider daily
observations are not redistributed unless the provider's terms explicitly
permit it; official retrieval routes and omission decisions are documented
in Supporting Information. The archival release and DOI have not yet been
created: before submission, the authors must deposit the permitted package
in a persistent repository, insert the minted DOI in the manuscript and
repository metadata, and verify that every linked artifact resolves to the
deposited version. No placeholder DOI should be cited as an archived record.

The third confirmation follows protocol v3, drafted to fix the provenance
flaw of the internally hash-bound second panel (whose amendment and outcomes
shared one version-control commit). Protocol v3 requires, before any
third-panel outcome is opened: (i) a separate public commit containing the
protocol, the exact roster, endpoint definitions, and the power analysis;
(ii) an external OSF/Zenodo registration of that content with a minted
handle; and (iii) an outcome-scoring commit referencing the registration.
The target is 80-120 outcome-disjoint scored networks; the binding primary
endpoint is paired network-level DeltaRho on direct-support units (observed
+0.038; 80% power at N = 120), with additional endpoints for captured loss
at a 20% budget, NDCG at a 5% budget, and a thermal-metric protection floor.
Within-network superiority over the simple baseline on the full panel is
explicitly not claimed (observed DeltaRho -0.093) and is registered as a
margin-zero diagnostic. All margins are frozen before outcomes; amendments
require a new external registration.

## References

See the repository bibliography; citations use the keyed reference list
maintained with the manuscript.
