# Fitting-period error curves improve network-level risk ranking for stream-temperature gaps

## Key Points

- At directly supported horizons, artificial gaps placed wholly inside fitting
  years predicted later recovery loss better than simple structural
  descriptors or conditional covariance at the network level.
- Conditional-covariance risk saturated with gap length while realized loss
  continued to grow, explaining why the analytic operator added little.
- Loss ordering persisted across three statistical recovery models but weakened
  for a bounded BiLSTM, an air2stream-equivalent process model, and planted
  field-outage geometries.

## Plain Language Summary

Managers often need to judge a missing stream-temperature interval before they
can fit and compare elaborate recovery models. We tested three options: a
formula based on covariance, a small set of descriptors such as gap length and
neighbor similarity, and direct trial gaps inserted into the earlier part of
each record. The trial-gap error curve was the clearest guide to later error.
The covariance formula reached a ceiling for long gaps and therefore missed
the growing effects of seasonal change and model error. Simple descriptors
still sorted easier from harder gaps across countries and three statistical
recovery models, but transfer was weaker for a bounded BiLSTM and a process
model driven by air temperature and flow. Trial-gap ranking also degraded when
we planted the timing and duration of observed field outages into periods with
known truth. When no same-duration trial curve was available, a network average
preserved some network ordering but poorly predicted individual gaps. These
results support fitting-period stress tests as a screening tool. They do not
support automatic filling or removal of monitoring stations without local
calibration.

## Abstract

Equal-length stream-temperature outages can have different recovery losses,
yet monitoring decisions must often be made before missing truth is available
or an operational recovery model is selected.
We compared three fitting-period predictors of later loss: simple outage and
redundancy descriptors, an analytic conditional-covariance risk, and an
empirical curve obtained from seasonally stratified artificial gaps.
Development used 55 river networks, and a first panel of 42 new networks was
used for post-confirmation method development. A second outcome panel scored 57
networks from North America and Europe. On 874 units at the four directly
supported horizons, fitting-period transfer reached network-level Spearman
0.805. Extending the predictor across all horizons with a network-mean fallback
substantially weakened pooled ranking and magnitude accuracy.
Conditional-covariance risk saturated with gap length while realized loss
continued to increase, explaining why the analytic lower bound contributed
little beyond empirical and simple
predictors. The direction of loss ordering persisted across three statistical
recovery families but weakened for a bounded BiLSTM, an air2stream-equivalent
process model, and planted field-outage geometries; absolute calibration,
simultaneous interval coverage, safe-fill control, and station-placement
benefit did not transfer as
operational guarantees. Fitting-period error curves are therefore the
strongest tested pre-evaluation screen, but their use for absolute error or
management thresholds requires local labels. An internally hash-bound second
evaluation reproduced direct-horizon ordering and near-unit calibration, but
its intervals remained inefficient and exact triage released nothing. Its
amendment lacks a separate public pre-outcome commit.

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

Artificial or trial gaps are established tools for stress-testing recovery
methods, particularly in flux-monitoring studies [@moffat2007gap;
@richardson2007longgaps]. We do not propose the trial-gap idea itself as new.
Our contribution is to test whether a fitting-period error curve transfers as
a quantitative recoverability ranking to entirely unseen river networks, to
identify why an analytic conditional-covariance alternative loses information
at long horizons, and to carry both results to explicit cross-domain and
decision boundaries. This sequence—empirical transfer, saturation mechanism,
and limits on operational use—is the paper's claim structure.

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
four-coalition conditional-covariance operator add useful information, and how
does its horizon response differ from realized loss? Third, does loss ordering
persist across recovery-model families, provider domains, and planted field-
outage geometries? Fourth, can the result support uncertainty intervals,
safe-fill triage, or station placement?
The river network is the primary extrapolation unit throughout (Figure 1).

## 2. Methods

### 2.1 Study phases and data

The development collection combined 55 networks, 217 stations, and 1,260
station-gap units for which temperature, meteorology, hydraulics, analytic
risk, and recovery outcome used identical fitting rosters. The first
confirmation began with 165 candidate river groups from 11 providers. Daily
source and concurrency checks identified 60 qualifying stream networks; the
preregistered first panel contained 45, of which 42 produced scoreable
gaps. Those 42 networks included 17 in the United States and 25 from European
provider domains and contributed 1,440 station-gap units.

Daily mean stream temperature was the target. Calendar years were ordered and
the first 70% used for fitting; the remaining years supplied observed truth for
7-, 14-, 30-, 60-, 90-, 180-, and 365-day artificial gaps. Each station-gap
cell used up to 20 placements distributed across eligible evaluation windows.
The primary loss was mean absolute error in degrees Celsius. Stations and gaps
were repeated observations nested within networks.

### 2.2 Recovery-model roster

The preregistered recovery condition was gradient boosting with local gap
boundaries and synchronous donor temperatures; the matched development
operator experiment additionally supplied meteorology and hydraulics. To
separate information availability from model-specific error, we scored the
same gaps with two additional families. A seasonal-boundary ridge regression
used three annual harmonics and linear interpolation between the two observed
gap boundaries. A donor covariance regression added synchronous neighboring
temperatures with ridge stabilization. Median feature imputation, scaling, and
all coefficients were fit using fitting years only. The third family was the
prespecified gradient-boosting model (300 trees, depth 4, learning rate 0.05).

After the first-panel analysis, we added a bounded bidirectional LSTM
sensitivity. A mask-aware `torch.nn.LSTM` used artificial blocks only from
fitting years, up to five epochs, and at most three placements per station-gap.
The deterministic, outcome-blind subset contained 14 networks from eight
providers and seven countries, 165 station-gap units, and 495 placements. This
is not a reimplementation of a published stream-temperature LSTM, a
state-of-the-art training budget, or a complete roster evaluation.

We also implemented the published eight-parameter air2stream state equation
and Crank--Nicolson update [@toffolon2015air2stream] in Python. Calibration used
train-only bounded multistart least squares rather than the original particle
swarm optimizer. The outcome-blind subset was the lexically first 12
non-attrited US second-panel networks, followed by strict input QC: same-site
approved USGS daily discharge had to be positive and complete, and NASA POWER
daily air temperature at the exact station coordinates had to be finite.
Fourteen stations in eight networks
supported 89 station-gap units and 1,750 placements. This is a
published-equation equivalent, not the original executable; it is US-only, and
POWER local-solar versus USGS local-civil daily windows share date labels but
not identical 24-hour boundaries.

### 2.3 Fitting-period empirical transfer

We nested a second chronological split inside the outer fitting years. The
first 70% of those years fit the same gradient-boosting recovery family; the
remaining fitting years supplied observed artificial-gap truth. For 7-, 30-,
90-, and 180-day gaps, candidate starts were divided into DJF, MAM, JJA, and
SON and up to 20 placements were selected per season. Their mean MAE formed a
station-by-horizon-by-season empirical curve before the outer evaluation
period began. When a station-season cell lacked support, prediction fell back
first to the station-horizon mean and then to the network-horizon mean. For an
evaluation horizon with no fitting-period curve, prediction used the mean of
all fitting-period empirical losses in that network. We classify the first
three sources as direct within-horizon support and the last as a network-mean
fallback. No outer evaluation loss entered any source.

### 2.4 Matched planted outage geometry

To test geometry rather than actual missing values, we planted catalogued
field-outage timing and duration into later observed periods. Each natural-
geometry item was paired with an artificial-grid item from the same network and
station at the nearest log-gap horizon, with ties assigned to the shorter
horizon. The matched roster contained 1,327 truth-bearing items from 167
stations in 49 development networks. Actual missing days have no truth and were
never scored. Network bootstrap intervals and paired rank differences used
2,000 network resamples.

### 2.5 Simple descriptors and analytic lower bound

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

### 2.6 Inference, calibration, and intervals

All development predictions left out complete networks. Results report
network-level Spearman first, followed by pooled and within-network rank as
diagnostics. Calibration intercept and slope used weights inversely
proportional to the number of station-gap rows in each network. Network
bootstrap intervals resampled rivers.

Post-confirmation US heterogeneity models combined development and both outcome
panels. They included 104 networks for simple descriptors and 100 for empirical
transfer, with a network random intercept and random prediction slope. Fixed
effects interacted predicted loss with broad HUC2 climate group or the 2009
GAGES-II major-dam stratum and retained analysis-phase interactions. GAGES-II
status was known for 89 empirical networks. These are descriptive effect-
modification models, not causal estimates of climate or regulation.

The preregistered 90% interval used the 90th percentile of each development
network's largest absolute leave-one-network-out residual, giving a constant
half-width of 3.247 °C in confirmation. We additionally evaluated split
conformal absolute-residual intervals within fixed horizon bins (7--14,
30--60, 90--180, and 365 days), with a global fallback for sparse bins.
Coverage is reported both by row and as the fraction of networks for which
every station-gap row was covered.

### 2.7 Decision analyses

Safe-fill triage defined loss above 0.5 °C as unsafe and allowed at most 5%
false releases. The preregistered threshold was evaluated unchanged. A
post-confirmation learn-then-test analysis then added labelled networks until
budgets of 25, 50, 100, or 200 station-gap rows were reached and used an exact
one-sided Clopper--Pearson bound. Because this analysis uses confirmation
labels, it estimates adaptation cost and is not confirmation evidence.

Real-data placement replay used development networks with at least five
stations and a complete directed station-pair loss matrix. Policies retained
\(k\) donor
stations using fitting-period information and reconstructed every unretained
target over observed 90-day evaluation gaps. We compared simple-risk minimax,
greedy mutual information, QR pivoting, even spacing, and random placement.
An outcome oracle defined regret as excess worst-target MAE.

### 2.8 Evidence roles and second-confirmation rule

The analysis plan and thresholds for the simple-descriptor model were
preregistered before outcomes in the 42-network panel were evaluated. The
empirical-transfer baseline, recovery-roster sensitivity, conformal redesign,
and real-data replay were specified after that first evaluation and are
reported as method development, not as independent confirmation. For the
second independent confirmation, the analysis plan requires 60--80 wholly new
scored networks,
with a minimum of 40 after attrition and the specified domain minima. Its v2
eligibility amendment was internally frozen and hash-bound to the exact roster
before recovery scoring. Because the amendment and outcomes enter version
control in the same commit, we do not describe v2 as externally preregistered.
All development networks and all 42 first-panel networks with scored recovery
outcomes are ineligible. Records used only for source and quality checks, with
no recovery outcome opened, may be re-screened and are disclosed separately.

## 3. Results

### 3.1 Empirical transfer was the strongest tested baseline

The fitting-period empirical curve produced 823 directly supported development
and 780 directly supported first-panel station-gap predictions at the four
prespecified horizons. On those 780 units, its primary network-level Spearman
was 0.922; pooled Spearman was 0.934, \(R^2\) was 0.812, and RMSE was 0.362 °C.
Its equal-network calibration intercept was 0.107 °C and slope was 0.864. On
the same units, the simple model had network-level Spearman 0.687, pooled
Spearman 0.785, and \(R^2=0.563\).

The complete-panel analysis assigned a fitting-period-only prediction to all
1,440 units: 780 used a within-horizon training curve and 660 used the
network-mean fallback, with no missing predictions. Network-level Spearman
remained higher for the empirical predictor than for the simple model (0.767
versus 0.563). However, empirical pooled Spearman fell to 0.633 versus 0.803
for the simple model, and empirical \(R^2\) fell to 0.145 versus 0.603. Its
full-panel calibration slope was 0.829 and RMSE was 1.156 °C. Thus direct
empirical support was the strongest tested predictor at its prespecified
horizons, whereas a network-wide mean was a weak substitute when same-horizon
fitting evidence was unavailable.

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

### 3.3 Rank direction weakened for BiLSTM and air2stream-equivalent losses

Simple descriptors ranked loss in all three confirmation recovery families.
Pooled Spearman was 0.733 for donor covariance regression, 0.841 for
seasonal-boundary regression, and 0.808 for gradient boosting. Network-level
Spearman was 0.387, 0.430, and 0.565, respectively. Calibration did not
transport: slopes were 0.830, 0.862, and 0.760. Thus the qualitative rank
finding was not unique to XGBoost, but neither magnitude nor network-level
strength was roster invariant.

The bounded BiLSTM sensitivity was materially weaker. Across 165 station-gap
units in 14 networks, empirical risk versus BiLSTM loss had station-gap
Spearman 0.338 and network-level Spearman 0.631; XGBoost loss versus BiLSTM
loss reached 0.314 and 0.411, respectively. All training histories were finite,
but 92.9% reached the five-epoch cap. These values do not establish optimizer
convergence, state-of-the-art LSTM performance, or full-roster transfer.

The independent air2stream-equivalent sensitivity was weaker still. Across 89
station-gap units in eight second-panel US networks, empirical risk versus
air2stream loss had station-gap Spearman 0.173 and network-level Spearman
0.238. At the four directly supported horizons, the corresponding values were
0.072 and 0.310. XGBoost loss versus air2stream loss reached 0.039 and 0.286.
The published-equation process baseline therefore closes the earlier
implementation gap on a fixed independent subset, but the weak ranks, US-only
coverage, alternate optimizer, and day-boundary mismatch preclude a broad
model-family transfer claim.

### 3.4 Planted field-outage geometry weakened empirical transfer

On 1,327 matched items from 49 networks, empirical network-level Spearman was
0.566 (95% network-bootstrap interval 0.338--0.732) under planted field-outage
geometry, compared with 0.734 (0.535--0.868) on matched artificial-grid gaps.
The paired difference was -0.168 (-0.328 to -0.012). Natural-geometry
calibration slope was only 0.401. Moreover, 85.8% of natural-geometry items
used the network-mean fallback rather than a same-horizon empirical curve.
Observed geometry therefore retained moderate network ordering but materially
reduced rank and magnitude transfer. This experiment does not score actual
missing days or identify the selection process that caused them.

### 3.5 Pooled rank was not a between-network artifact

For the original simple model, pooled confirmation Spearman was 0.803. After
removing each network's predicted and observed means, within-network Spearman
was 0.862; between-network Spearman was 0.563 (95% network-bootstrap interval
0.293--0.752). The strong pooled ordering was therefore not produced solely by
differences among network means. The network-level primary planning criterion
was nevertheless not met (Figure 2).

### 3.6 Absolute calibration and decision guarantees did not transfer

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
rule. Operational triage therefore remained unsupported (Figure 4).

The cross-phase US mixed models identified heterogeneity for simple descriptors
but not a stable empirical modifier (Figure 5). For the simple predictor, the
adjusted maritime slope was 0.649 versus 1.160 in the arid/semiarid reference
group; the prediction-by-maritime interaction had \(p = 0.0024\). Empirical
prediction interactions with broad climate groups were not significant. Among
the 89 empirical networks with known GAGES-II status, adjusted slopes were
0.887 for regulated and 0.741 for unregulated networks, but their interaction
was not significant (\(p = 0.119\)). HUC2 climate bands are broad, major-dam
presence is not a causal treatment, QC regimes differ by phase, and empirical
mixed-model diagnostics included boundary warnings. These results are
descriptive effect modification, not attribution to climate or regulation.

The station-placement replay was also post-confirmation method development.
Only 14 development networks had complete directed loss matrices and at least
five stations. We therefore report its policy comparison in Supporting
Information rather than treating it as main-text evidence for station removal.

### 3.7 Second independent confirmation reproduced network rank but not decision efficiency

The internally frozen v2 roster attempted 60 networks. Three had no scoreable
evaluation gap, leaving 57 networks and 1,446 station-gap units, above the
minimum of 40. The simple model reached station-gap Spearman 0.819,
network-level Spearman 0.614, and equal-network calibration slope 1.017. Its
constant interval covered every row simultaneously in 91.2% of networks, but
mean width remained 6.49 °C.

At the four directly supported horizons, the empirical predictor covered 874
units and reached station-gap Spearman 0.945, network-level Spearman 0.805, and
calibration slope 0.938. Across all 1,446 units, 572 network-mean fallbacks
reduced these values to 0.740, 0.715, and 0.950, respectively. Its network-block
interval covered all rows in all networks, but median width was 8.40 times the
median loss (mean width 8.78 °C). Thus the empirical predictor again improved
network-level ordering over the simple model, while the simple model retained
stronger station-gap ordering and neither interval was operationally efficient.

The fixed exact 5% triage rule certified no release for either the simple or
empirical predictor and released zero second-confirmation units. The
decision-level endpoint therefore failed despite the reproduced ranking and
calibration results.

All 13 second-panel networks with at least five stations produced complete
90-day placement matrices. Simple-risk minimax mean regret was 0.241 °C versus
0.256 °C for random placement, a directional reduction of 0.015 °C (6.0%).
The protocol specified no margin or significance criterion for placement
utility, so this small directional difference is not a confirmatory benefit and
does not support station removal.

Three roster members had undergone source and quality checks in the first
panel but had no recovery outcome scored there. Overlap with all development
networks and with the 42 first-panel scored networks was zero. The evaluation
therefore uses independent recovery outcomes, but its source-QC history is not
entirely untouched. The v2 eligibility amendment was internally hash-bound
before recovery scoring, yet the amendment and outcomes enter version control
in the same commit; it is not externally verifiable preregistration.

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

The matched geometry analysis adds a distinct warning. Empirical ranking did
not disappear when observed outage shapes were planted into truth-bearing
periods, but both rank and calibration degraded relative to matched artificial
gaps. Most items lacked a same-horizon curve and used a network mean. Managers
should therefore match trial-gap duration and season to their observed outage
portfolio rather than treating a generic stress curve as field-gap evidence.

The placement analysis evaluates policies on observed leave-station-out
outcomes and includes mutual-information and QR-pivot comparators
[@krause2008sensor; @oh2025sensors]. The 14-network development replay favored
minimax placement, and the 13-network second-panel replay showed 6.0% lower mean
regret than random placement. Because the protocol supplied no utility margin
or significance criterion, this directional difference does not establish a
placement benefit or support sensor removal.

Several limitations remain. The empirical curve was directly supported only at
four horizons; using a network-wide mean elsewhere preserved between-network
ordering but sharply reduced pooled rank and magnitude accuracy. The recovery
roster spans three statistical families. The 14-network BiLSTM sensitivity hit
its epoch cap in 92.9% of networks and is neither a converged state-of-the-art
benchmark nor a full roster. The air2stream sensitivity implements the
published equation, but replaces the original optimizer, covers only eight US
networks, and joins differing daily time conventions. The matched planted-
geometry experiment still does not observe truth on actual missing days or
identify failure-process selection. HUC2 and GAGES-II heterogeneity strata are
broad and descriptive, while provider-specific QC and day definitions may
contribute to domain shifts. Thermal-state-change evidence remains sparse. The
second evaluation tested the
redesigned interval and triage procedures: the interval was inefficient and
exact triage released nothing. Placement was directionally favorable but had
no prespecified utility criterion. Independent evaluation therefore closed the
protocol loop with negative decision endpoints rather than an operational
recommendation.

Recruitment for the second evaluation began with 242 candidates and yielded 60
networks meeting the internally prespecified quality criteria (35 US, 15 Czech,
and 10 Norwegian). The original Canadian requirement could not be met because
the only identified multi-station daily source labels its 16,244 observations
from four St. Lawrence locations as not validated or checked. The pre-scoring
amendment therefore substituted the two available non-US validation domains,
Czechia and Norway. Section 3.7 reports the outcome and its provenance limits.

The earlier Chattahoochee case study provides a concrete example of the same
boundary: the station below Buford Dam had predicted skill 0.414 but observed
skill -0.300 after a thermal-state shift, and a national Southeast Plains
diagnostic reversed direction. These examples do not establish a reservoir
cause; they show why stable fitting-period covariance need not transport
through a changed thermal regime.

## 5. Conclusions

Fitting-period empirical error curves were the strongest tested predictor of
later stream-temperature recovery loss. Direct-horizon network-level Spearman
was 0.805 across 57 networks in the second evaluation, after reaching 0.922 in
the first-panel method-development analysis. Conditional variance saturated
while long-gap loss continued to grow, so an analytic information bound should not
be treated as a substitute for stress-testing the intended recovery pipeline.
Weak transfer to bounded BiLSTM and air2stream-equivalent losses, together with
the decline under planted field-outage geometry, shows that the screen must be
matched to the recovery family and outage portfolio.
For monitoring managers, the supported action is to use fitting-period trial
gaps to rank which outages warrant attention, while retaining simple
descriptors when records are too short for stratified trials. Absolute error
promises should not be based on a network-mean fallback where no same-horizon
trial curve exists. Automatic safe filling and station removal require local
labels and independent decision-level validation; neither is supported by the
present evidence. In the second outcome-independent evaluation, empirical
network-level Spearman remained higher than the simple model (0.715 versus
0.614), but its interval width was eight times the median loss; replication of
rank did not create a usable decision guarantee, and neither predictor
certified a nonempty safe-fill set.

## Open Research

Code, analysis configurations, provider request metadata, source-QC summaries,
derived station-gap losses, and figure inputs are organized in the public
repository described by the package manifest. Provider daily observations are
not redistributed unless the provider's terms explicitly permit it; official
retrieval routes and omission decisions are documented in Supporting
Information Text S17. The archival release and DOI have not yet been created.
Before submission, the authors must deposit the permitted package in a
persistent repository, insert the minted DOI in the manuscript and repository
metadata, and verify that every linked artifact resolves to the deposited
version. No placeholder DOI should be cited as an archived record.
