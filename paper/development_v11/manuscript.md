# Fitting-period error curves outperform structural risk estimates for stream-temperature gaps

## Key Points

- Artificial gaps placed wholly inside fitting years predicted later recovery
  loss better than either simple structural descriptors or conditional
  covariance.
- Conditional-covariance risk saturated with gap length while realized loss
  continued to grow, explaining why the analytic operator added little.
- Loss ordering generalized across recovery models, but magnitude calibration,
  simultaneous coverage, and safe-fill decisions remained domain dependent.

## Plain Language Summary

Managers often need to judge a missing stream-temperature interval before they
can fit and compare elaborate recovery models. We tested three options: a
formula based on covariance, a small set of descriptors such as gap length and
neighbor similarity, and direct trial gaps inserted into the earlier part of
each record. The trial-gap error curve was the clearest guide to later error.
The covariance formula reached a ceiling for long gaps and therefore missed
the growing effects of seasonal change and model error. Simple descriptors
still sorted easier from harder gaps across countries and across three recovery
models, but the numerical error scale changed by data domain. These results
support fitting-period stress tests as a screening tool. They do not support
automatic filling or removal of monitoring stations without local calibration.

## Abstract

Equal-length stream-temperature outages can have different recovery losses,
yet monitoring decisions must often be made before a recovery model is fit.
We compared three fitting-period predictors of later loss: simple outage and
redundancy descriptors, an analytic conditional-covariance risk, and an
empirical curve obtained from seasonally stratified artificial gaps. Open
development included 55 river networks and 1,260 station-gap units; a first
confirmation included 42 new networks and 1,440 units from North America and
Europe. On the four prespecified empirical-curve horizons, fitting-period
transfer achieved confirmation Spearman 0.934 and explained 81.2% of loss
variance. The analytic operator added only 0.017 in development \(R^2\) beyond
simple descriptors. Across seasonal-boundary regression, donor covariance
regression, and gradient boosting, simple-descriptor loss ranks transferred,
but confirmation calibration slopes ranged from 0.760 to 0.862. Analytic risk
rose from 0.379 to 0.451 °C between 7- and 365-day gaps on a fixed 61-station
roster, whereas realized loss rose from 0.544 to 4.719 °C. Fitting-period error
curves therefore provide the strongest tested pre-evaluation screen. Their
operational calibration and decision guarantees still require domain-specific
labels and a second independent confirmation.

## 1. Introduction

A failed logger can leave weeks or months of missing stream temperature while
boundary observations, neighboring stations, weather records, and discharge
remain available. Gap-filling studies usually ask which model reconstructs
the missing values best [@li2017streamairimputation; @bal2023streamtemperature].
A monitoring manager faces an earlier question: how much error should be
expected for this outage geometry before committing to a recovery model or a
station-retention decision?

Several mature literatures bear on this question. Gaussian posterior variance,
kriging variance, mutual information, and value of information have long been
used to design monitoring networks [@caselton1984monitoring;
@pardo1998gauges; @krause2008sensor; @alfonso2012voi]. Recent hydrological
sensor design uses rank-revealing QR decomposition and validates placement by
reconstruction [@oh2025sensors]. Separately, flux-network studies use
stratified artificial gaps and show that uncertainty grows with gap length and
season [@moffat2007gap; @richardson2007longgaps]. These traditions motivate
distinct predictors: an analytic information bound, readily observed
structural descriptors, and direct fitting-period recovery errors.

Analytic variance is not automatically realized model error. Classical
kriging variance can understate prediction variance when covariance parameters
are estimated [@denhertog2006kriging], and a value-independent variance need
not represent local error dispersion [@yamamoto2000kriging]. Hydrological
conformal prediction similarly distinguishes point prediction from calibrated
uncertainty and shows that local information may be insufficient for extremes
[@auer2024uncertainty]. A valid test must therefore connect a pre-evaluation
risk to observed recovery loss, leave out whole river networks, and carry the
result through calibration and decisions.

We ask four questions. First, do fitting-period empirical error curves or
simple descriptors rank later recovery loss on unseen networks? Second, does a
four-coalition conditional-covariance operator add useful information? Third,
does the ranking persist across recovery-model families? Fourth, can the
result support uncertainty intervals, safe-fill triage, or station placement?
The river network is the primary extrapolation unit throughout (Figure 1).

## 2. Methods

### 2.1 Study phases and data

The open-development collection combined 55 networks, 217 stations, and 1,260
station-gap units for which temperature, meteorology, hydraulics, analytic
risk, and recovery outcome used identical fitting rosters. The first
confirmation began with 165 candidate river groups from 11 providers. Daily
source and concurrency checks identified 60 qualifying stream networks; the
prospectively fixed first panel contained 45, of which 42 produced scoreable
gaps. Those 42 networks included 17 in the United States and 25 from European
provider domains and contributed 1,440 station-gap units.

Daily mean stream temperature was the target. Calendar years were ordered and
the first 70% used for fitting; the remaining years supplied observed truth for
7-, 14-, 30-, 60-, 90-, 180-, and 365-day artificial gaps. Each station-gap
cell used up to 20 placements distributed across eligible evaluation windows.
The primary loss was mean absolute error in degrees Celsius. Stations and gaps
were repeated observations nested within networks.

### 2.2 Recovery-model roster

The original recovery condition was gradient boosting with local gap
boundaries and synchronous donor temperatures; the matched development
operator experiment additionally supplied meteorology and hydraulics. To
separate information availability from model-specific error, we scored the
same gaps with two additional families. A seasonal-boundary ridge regression
used three annual harmonics and linear interpolation between the two observed
gap boundaries. A donor covariance regression added synchronous neighboring
temperatures with ridge stabilization. Median feature imputation, scaling, and
all coefficients were fit using fitting years only. The third family was the
fixed gradient-boosting model (300 trees, depth 4, learning rate 0.05).

### 2.3 Fitting-period empirical transfer

We nested a second chronological split inside the outer fitting years. The
first 70% of those years fit the same gradient-boosting recovery family; the
remaining fitting years supplied observed artificial-gap truth. For 7-, 30-,
90-, and 180-day gaps, candidate starts were divided into DJF, MAM, JJA, and
SON and up to 20 placements were selected per season. Their mean MAE formed a
station-by-horizon-by-season empirical curve before the outer evaluation
period began. When a station-season cell lacked support, prediction fell back
first to the station-horizon mean and then to the network-horizon mean. No
outer evaluation loss entered this predictor.

### 2.4 Simple descriptors and analytic lower bound

Simple fitting-period descriptors comprised gap length, target autocorrelation,
year-block donor \(R^2\), the earlier additive \(d/4\) heuristic, nearest-donor
correlation, and seasonal sine/cosine. Candidate linear combinations were
selected within nested leave-one-network-out folds using equal network weight.

For target gap \(G\) and observed information \(O\), the analytic operator was

\[
\Sigma_{G\mid O}=\Sigma_{GG}-\Sigma_{GO}\Sigma_{OO}^{+}\Sigma_{OG}.
\]

The information set comprised gap boundaries \(B\), donor temperatures \(D\),
meteorology \(M\), and hydraulics \(H\). Mean conditional standard deviation
over the gap was treated as a Gaussian optimal-prediction lower bound, not as
recovery MAE. We tested its incremental value after the strongest simple model
and after a learned nonlinear error model.

### 2.5 Inference, calibration, and intervals

All development predictions left out complete networks. Confirmation reports
network-level Spearman first, followed by pooled and within-network rank as
diagnostics. Calibration intercept and slope used weights inversely
proportional to the number of station-gap rows in each network. Network
bootstrap intervals resampled rivers.

The original 90% interval used the 90th percentile of each development
network's largest absolute leave-one-network-out residual, giving a constant
half-width of 3.247 °C in confirmation. We additionally evaluated split
conformal absolute-residual intervals within fixed horizon bins (7--14,
30--60, 90--180, and 365 days), with a global fallback for sparse bins.
Coverage is reported both by row and as the fraction of networks for which
every station-gap row was covered.

### 2.6 Decision analyses

Safe-fill triage defined loss above 0.5 °C as unsafe and allowed at most 5%
false releases. The original fixed threshold was evaluated unchanged. A
post-confirmation learn-then-test analysis then added labelled networks until
budgets of 25, 50, 100, or 200 station-gap rows were reached and used an exact
one-sided Clopper--Pearson bound. Because this analysis uses confirmation
labels, it estimates adaptation cost and is not confirmation evidence.

Real-data placement replay used open networks with at least five stations and
a complete directed station-pair loss matrix. Policies retained \(k\) donor
stations using fitting-period information and reconstructed every unretained
target over observed 90-day evaluation gaps. We compared simple-risk minimax,
greedy mutual information, QR pivoting, even spacing, and random placement.
An outcome oracle defined regret as excess worst-target MAE.

### 2.7 Evidence roles and second-confirmation rule

The 42-network result is the first confirmation of the simple descriptor
model. Empirical transfer, recovery-roster sensitivity, conformal redesign,
and real-data replay are subsequent method-development analyses. A second
confirmation requires 60--80 wholly new scored networks, with an
attrition-tolerant minimum of 40 and at least 10 networks per required domain.
Networks used here are ineligible.

## 3. Results

### 3.1 Empirical transfer was the strongest tested baseline

The fitting-period empirical curve produced 823 supported development and 780
supported confirmation station-gap predictions. In confirmation, its pooled
Spearman was 0.934, network-level Spearman was 0.922, \(R^2\) was 0.812, and
RMSE was 0.362 °C. Its equal-network calibration intercept was 0.107 °C and
slope was 0.864. On the same 780 units, the simple model had pooled Spearman
0.785, network Spearman 0.687, and \(R^2=0.563\). The empirical baseline
therefore displaced simple-descriptor sufficiency as the primary positive
result (Figure 2).

### 3.2 Complexity beyond empirical and simple predictors added little

Across all development units, the completed conditional-covariance operator
increased \(R^2\) by 0.0171 after the selected simple model, below the planned
0.05 threshold. In a network-random-intercept model its marginal \(R^2\)
increment was 0.0090. A nonlinear learned error model on the empirical and
simple predictors attained leave-one-network-out \(R^2=0.701\); adding the
operator raised this to 0.704 while Spearman changed from 0.827 to 0.827.

The mechanism analysis explains this weak increment. On the same 61 stations
at every horizon, conditional risk increased only from 0.379 °C at 7 days to
0.451 °C at 365 days. Realized loss increased from 0.544 to 4.719 °C. The
remainder between the lower bound and realized loss grew from 0.165 to 4.268
°C, consistent with accumulating model error and nonstationary seasonal drift
(Figure 3).

### 3.3 Rank direction persisted across recovery families

Simple descriptors ranked loss in all three confirmation recovery families.
Pooled Spearman was 0.733 for donor covariance regression, 0.841 for
seasonal-boundary regression, and 0.808 for gradient boosting. Network-level
Spearman was 0.387, 0.430, and 0.565, respectively. Calibration did not
transport: slopes were 0.830, 0.862, and 0.760. Thus the qualitative rank
finding was not unique to XGBoost, but neither magnitude nor network-level
strength was roster invariant.

### 3.4 Pooled rank was not a between-network artifact

For the original simple model, pooled confirmation Spearman was 0.803. After
removing each network's predicted and observed means, within-network Spearman
was 0.862; between-network Spearman was 0.563 (95% network-bootstrap interval
0.293--0.752). The strong pooled ordering was therefore not produced solely by
differences among network means. The network-level primary planning criterion
was nevertheless not met.

### 3.5 Narrower intervals lost whole-network protection

The original constant-width interval covered 99.2% of rows and all rows in
85.7% of networks, but its mean width was 6.49 °C. Horizon-Mondrian conformal
intervals reduced mean width to 1.99 °C and median width to 1.15 °C, 1.39 times
the median loss. Row coverage fell to 86.2%, and only 40.5% of networks had
simultaneous coverage. Conditionalization improved efficiency but did not meet
the joint coverage endpoint.

Using the stronger empirical predictor and one maximum scaled residual per
development network restored simultaneous coverage to 92.9% on its 780
supported confirmation units. Median width was 1.68 °C, or 2.22 times median
loss, narrowly above the planned efficiency ceiling of 2.0. No tested interval
met coverage and width requirements simultaneously.

The US first-confirmation subset had simple-model calibration slope 0.954,
whereas 25 non-US networks had slope 0.753. Using labelled networks after
confirmation, a requested budget of 100 station-gap rows returned evaluation
slope to 0.9--1.1 in 50% of cross-domain resamples. No tested budget up to 200
rows certified a nonempty 5% false-release set with the exact risk-control
rule. Operational triage therefore remained unsupported (Figure 5).

### 3.6 Real-data placement replay was promising but sparse

Fourteen open networks retained at least five stations with a complete
directed replay matrix, so placement results remain developmental. Averaged
over their feasible budgets, simple-risk minimax regret was 0.553 °C, compared
with 0.607 for greedy mutual information, 0.569 for QR pivoting, 0.681 for even
spacing, and 0.658 for random placement. The direction favors gap-specific
minimax placement, but confirmation on an untouched panel remains necessary
(Figure 4).

## 4. Discussion

The decisive result is methodological rather than algebraic: test the recovery
pipeline inside the fitting record. Empirical curves captured gap length,
season, local donor behavior, and model error in the same units as the target
loss. The conditional covariance captured an optimal Gaussian information
bound but saturated as boundaries became distant, while realized long-gap loss
continued to accumulate. This is the observed counterpart of established
warnings that plug-in kriging variance can understate actual predictive
variance [@denhertog2006kriging; @yamamoto2000kriging].

Simple descriptors remain useful when the fitting record is too short to
support stratified trial gaps. Their high within-network rank across three
model families makes them a practical coarse screen. They should not be
presented as calibrated error or as a universal substitute for empirical
testing. The cross-domain slope difference and the failure of finite-sample
risk control show that an operational threshold needs local labels.

The placement analysis closes an earlier implementation gap by evaluating
policies on observed withheld-station outcomes and by including mutual
information and QR-pivot comparators [@krause2008sensor; @oh2025sensors]. Its
14-network roster is no longer merely an implementation check, but it remains
open development. The result supports confirmation, not station removal.

Several limitations remain. The empirical curve was supported only at four
horizons and sometimes required a network-horizon fallback. The recovery
roster spans three statistical families but not a recurrent neural model.
Provider-specific QC and day definitions may contribute to domain shifts.
Thermal-state-change evidence remains sparse. Finally, all interval and
decision redesigns after the first confirmation are method development and
require new independent evaluation.

Recruitment for that evaluation now exceeds the quantitative floor: 242
candidate networks yielded 60 strict-QC arrivals (35 US, 15 Czech, and 10
Norwegian). Scoring remains withheld because the predeclared Canadian stratum
has no validated arrival. The only identified multi-station Canadian daily
source supplied 16,244 observations from four St. Lawrence locations but
explicitly labels them as not validated or checked; fail-closed QC retained
none. This is an external source-quality condition, not a reason to drop the
domain after seeing availability.

The earlier Chattahoochee case study provides a concrete example of the same
boundary: the station below Buford Dam had predicted skill 0.414 but observed
skill -0.300 after a thermal-state shift, and a national Southeast Plains
diagnostic reversed direction. These examples do not establish a reservoir
cause; they show why stable fitting-period covariance need not transport
through a changed thermal regime.

## 5. Conclusions

Fitting-period empirical error curves were the strongest tested predictor of
later stream-temperature recovery loss, reaching network Spearman 0.922 on 42
new networks at supported horizons. Simple descriptors retained useful
within-network ordering across three recovery families. The saturation of
conditional variance explained why the analytic operator added little beyond
those observations. No tested result authorizes gap filling or station removal
outside the evaluated loss threshold and domains. The remaining scientific
question is how many labelled networks each new provider domain needs for
calibrated, finite-sample decision control; the registered second-confirmation
design targets that question.
