# Supporting Information for the v11 development manuscript

This document carries protocol history, deviations, exclusions, and secondary
analyses so the main text can follow the scientific chain from empirical
transfer to mechanism and decision boundaries. It is not a source of
unreported results.

## Text S1. Prior evidence and reason for redesign

The v9 open-network screen scored 44 public river networks. Network-level
Spearman was 0.67 for the partial operator and 0.80 for donor \(R^2\). A
recorded slice-specific increment over donor \(R^2\) was
\(6.88\times10^{-5}\). The intended
meteorological and hydraulic information coalitions were not connected across
that corpus. Placement exceeded the former 15% target in 2 of 10 rivers, and a
5% false-release setting yielded zero safe fills for both the operator and the
length-only comparator.

That earlier development corpus also catalogued 1,470 natural outage segments,
including 309 lasting at least 14 days. Planting 351 truth-bearing gaps with
those observed geometries across 11 networks produced Spearman 0.69. The
exercise was developmental, used a different corpus and risk construction, and
did not establish that artificial-gap performance transfers to the non-random
timing or causes of field outages. It is retained as a boundary, not pooled
with the v11 confirmation evidence.

A later T4-style development stress test bound observed-outage geometries to
2,355 truth-bearing planted counterparts across 67 networks. Under its own
model and weighting, network-level Spearman was -0.394 for the natural-geometry
score and -0.011 for the artificial-stress score (65 networks). The planned
network interval was not estimated because fewer than 100 networks were
available. Actual missing days were never scored because their truth is
unobserved. The T4 manifest marks direct comparability to the v11 empirical
predictor as false: its model, weights, and estimand differ. It therefore
partially tests observed outage geometry but does not resolve selection in
actual field failures or provide a matched v11 main experiment.

Twin E gave operator Spearman 0.936 and calibration slope 0.760, outside its
0.9--1.1 target. A later confirmation attempt performed QC on 40 candidate
networks, retained 32, and stopped before recovery scoring. It produced no
confirmed rank, calibration, incremental-value, placement, or triage result.

These are redesign inputs. V11 does not reinterpret them as an evaluated
confirmatory test or as support for either candidate model family.

## Text S2. Version and role history

Maintain a dated table for every analysis release with columns:

| Field | Content |
| --- | --- |
| Candidate model family | Simple-descriptor or conditional-covariance model |
| Data roles | Development or independent confirmation |
| Independent network count | Candidate, QC-passed, and scored counts |
| Operator definition | Exact B/D/M/H variables and covariance window |
| Calibration definition | Family, fitting rule, and interval construction |
| Recovery outcome | Model rule, gap horizons, placements, and loss |
| Hypothesis thresholds | H1, H2, and H3 numerical criteria |
| Deviations | What changed, when, why, and which data had been examined |

Changes based on development outcomes are allowed until model selection. The
complete confirmatory method is then preregistered before outcomes in a new
panel are scored. Confirmation outcomes do not select variables, calibration
family, gap horizons, recovery model, baseline, or figure metric.

## Text S3. Network membership and independence

List every network with provider, domain, role, stations, date range, common
days, climate class, network-size class, and regulation/groundwater metadata
when available. Whole networks remain in one role. Jinsha, Chattahoochee, the
previous 12-river pilot, all prior open roles, and every network touched during
the earlier QC attempt are ineligible for the new confirmation.

That exclusion statement governs construction of the first 42-network scored
panel. The later v2 amendment for the second evaluation excludes every
development and first-panel recovery-scored network, while allowing three
source/QC-only records with no opened recovery outcome; their reuse is reported
in Text S18.

Provide a network-flow table with every exclusion reason. The primary sample
size is the number of scored networks, not stations, masks, years, or gaps.

## Text S4. Variable provenance and temporal availability

For temperature, meteorology, and hydraulics, report provider, product,
variable, unit, daily-time convention, quality field, retrieval date, missing
days, and eligible common years. Specify whether an auxiliary measurement
inside an artificial temperature gap would have been available during the
offline reconstruction task. Online-causal recovery, if analyzed, is a
separate workload with its own availability rules.

Static basin attributes do not substitute for time-varying meteorology or
hydraulics. Absent discharge or gage-height records define a prespecified
information condition and coverage stratum.

## Text S5. Operator and calibration details

Give the covariance estimator, anomaly definition, fitting window, lag basis,
coalition matrices, dimensionality, and transformation from conditional
variance to raw risk. Describe nested leave-one-network-out selection between
linear and isotonic calibration and give all development fold results.

For the 90% prediction interval, state the residual score, calibration unit,
finite-sample quantile, and whether coverage is marginal or conditional. Report
coverage and width at the station-gap and network-summary levels. Do not call a
rank statistic calibration.

## Text S6. Recovery model and mask construction

Document the prespecified recovery-model roster, its development selection rule,
hyperparameters, climatology baseline, loss definitions, and the number of
placements per cell. Natural gaps contribute geometry only when their truth is
missing; truth-bearing observed intervals provide scored counterparts. Keep
the common artificial grid separate from empirical geometry in tables.

## Text S7. H2 ablation and simple baselines

Report identical folds and outcomes for gap/season, ACF, donor \(R^2\), nearest
donor correlation/distance, the additive \(d/4\) heuristic, the strongest
simple combination, B+D, B+D+M, and B+D+M+H. Include fold-level paired effects
and coefficient/calibration summaries. The chosen simple-combined model must
not use confirmation outcomes.

## Text S8. H3 placement and regret

List the focal objective and every comparator exactly. For greedy mutual
information, specify the covariance variables, candidate sensor set, budget,
and log-determinant objective. For the focal rule, specify how predicted loss
is aggregated across targets and gaps. Define the oracle and regret before
showing results. Publish network-level values for every feasible budget.

## Text S9. Nonstationarity analysis

Give the state-change detector, minimum pre/post support, common fitting and
evaluation windows, and modifiers measured independently of recovery loss.
Report sensitivity to change-date uncertainty. A state transition may be
consistent with regulation, groundwater, climate, or channel change without
identifying which mechanism caused it.

## Text S10. Cross-domain analysis

Describe provider differences in day boundary, unit, observation approval,
station grouping, and common-period completeness. Apply the selected US
development mapping unchanged in the primary cross-domain test. Report each
domain separately even if the pooled result is favorable.

Post-confirmation heterogeneity summaries are descriptive. For the simple
model, multi-network provider slopes were 0.648 for ARSO (12 networks), 0.826
for GKD Bayern (nine), and 0.954 for USGS (17). Slopes across network-size
groups were 0.809 for 3--4 stations, 0.772 for 5--7, and 0.800 for 8 or more;
network-level Spearman was 0.402, 0.714, and 0.817, respectively. For the
complete-panel empirical predictor, corresponding network-level Spearman was
0.803, 0.829, and 0.100. The sparse provider cells and non-random network sizes
preclude causal attribution. Complete rows, including thermal-state strata,
are in `heterogeneity_metrics.csv`.

## Text S11. Confirmation conduct

Start with at least 55 wholly new candidate networks. Complete source and
schema checks without using recovery outcomes to alter the model. Report QC
attrition before performance. If fewer than 40 networks or fewer than 10
outside the original US domain survive, do not run or interpret H1--H3 as the
planned confirmation. Close that study as underpowered. Any later recruitment
belongs to a separately recorded confirmation rather than an extension chosen
after seeing this panel's attrition.

After the sample floor is met, run the recorded pipeline once for the planned
analysis and report all H1--H3 outputs, including unfavorable and domain-
specific results. Corrections to data or analysis after viewing outcomes are
reported as new analyses, not substituted silently for the planned result.

## Text S12. Reporting boundary

The main paper contains scientific hypotheses, estimands, comparisons, and
results. This SI contains data-role history, version changes, exclusion tables,
protocol deviations, secondary horizons, sensitivity models, and complete
per-network output. The separation prevents workflow vocabulary from
interrupting the main argument while retaining a reproducible record.

## Text S13. Fitting-period empirical-transfer construction

The empirical baseline uses only the outer fitting years. Those years receive
a nested chronological 70/30 split. A B+D XGBoost model with the same prespecified
hyperparameters as the outer recovery family is fit on the earlier inner
years. Artificial gaps of 7, 30, 90, and 180 days are scored in the later
inner years after stratification into DJF, MAM, JJA, and SON, with at most 20
evenly spaced placements per cell. Prediction falls back from
station-horizon-season to station-horizon and then network-horizon only when
the finer cell has no eligible truth. If an evaluation horizon has no
within-horizon curve, prediction uses the mean of all fitting-period empirical
losses in that network. The outer evaluation period is never read while
constructing any fallback.

The resulting tables contain 47,408 fitting-period placement losses in 51
development networks and 52,989 in all 42 first-confirmation networks. They
support 823 and 780 outer station-gap predictions, respectively. Unsupported
14-, 60-, and 365-day cells are excluded from the empirical-baseline contrast,
not silently interpolated in that contrast. A separate complete-panel audit
assigns 780 first-panel units to a within-horizon training curve and 660 to the
network-mean fallback. All 1,440 units have a finite prediction. On the full
panel, empirical pooled Spearman is 0.633, network-level Spearman is 0.767,
\(R^2=0.145\), calibration slope is 0.829, and RMSE is 1.156 °C. The
corresponding simple-model values are 0.803, 0.563, and 0.603 for pooled
Spearman, network-level Spearman, and \(R^2\), respectively. Thus fallback
preserves a network-level ordering advantage but not the supported-horizon
pooled-rank or magnitude advantage.

## Text S14. Recovery-family sensitivity

Three model families are scored on identical outer gaps:

| Family | Information | Fitting rule |
| --- | --- | --- |
| Seasonal-boundary ridge | annual harmonics and two gap boundaries | fitting-period median imputation, scaling, ridge coefficient |
| Donor covariance ridge | seasonal/boundary terms and synchronous donor temperatures | fitting-period median imputation, scaling, ridge coefficient |
| Gradient boosting | seasonal/boundary terms and synchronous donor temperatures | 300 trees, depth 4, learning rate 0.05, subsample and column sample 0.9 |

The full-roster sensitivity does not claim that these three families span all
modern water-temperature reconstruction methods. It tests whether the
simple-descriptor ordering is unique to the original gradient-boosting loss
surface. No full-roster recurrent model or air-temperature--discharge hybrid
such as air2stream was run [@toffolon2015air2stream].

A subsequent bounded recurrent sensitivity selected one scored network from
each of six first-panel providers, using the fewest-eligible-stations rule and
then lexical network ID. The repository-local BRITS imputer uses GRU-style
recurrence with hidden size 16, four epochs, at most 48 fitting windows per
network, and artificial blocks drawn only from outer fitting years. Evaluation
covered 7-, 30-, and 90-day gaps, at most three placements per station-gap, 75
station-gap units, and 225 placements. XGBoost versus BRITS loss had
station-gap Spearman 0.317; empirical-transfer prediction versus BRITS loss had
station-gap Spearman 0.384 and network-summary Spearman 0.600 across six
networks. This post-confirmation analysis is exploratory. It is neither a
state-of-the-art LSTM benchmark nor a full-roster or independent confirmation,
and it provides no provider-specific inference.

A separate development-only process proxy used air temperature, approved flow,
seasonal and local gap-boundary terms in a ridge model. Fifty networks and
1,076 station-gap units had complete aligned inputs. XGBoost loss versus proxy
loss had station-gap Spearman 0.373 and network-level Spearman 0.343. The proxy
is not the published air2stream differential-equation model
[@toffolon2015air2stream]. Timestamp-aligned air temperature and approved flow
are unavailable on the first and second confirmation rosters, so this analysis
does not satisfy the requested air2stream benchmark or supply cross-network
confirmation for a process model.

## Text S15. Interval and risk-control details

The original interval radius is 3.2472146649 °C and is constant for every
first-confirmation cell. It is the 90th-percentile, higher-method quantile of
the maximum absolute residual in each inner held-out development network.

The additional Mondrian analysis uses absolute development LONO residuals and
fixed horizon bins 7--14, 30--60, 90--180, and 365 days. A bin with fewer than
20 calibration rows uses the global split-conformal radius. The finite-sample
rank is \(\lceil(n+1)(1-\alpha)\rceil\), capped at \(n\). This interval is a
post-confirmation redesign and its first-confirmation metrics are diagnostic.

The learn-then-test triage orders labelled calibration rows by predicted risk.
For every prefix it computes the one-sided 95% Clopper--Pearson upper bound on
the rate of realized MAE above 0.5 °C. It releases the largest prefix whose
upper bound is at most 0.05. Calibration and evaluation networks are disjoint
within every resample. A rule that cannot certify a prefix releases nothing.

## Text S16. Real-data placement replay

The replay uses 90-day outer evaluation gaps. Each directed target--donor pair
is fit from training-period seasonal, boundary, and donor features and scored
on observed gap truth. A network enters the policy comparison only when a
complete directed matrix exists for at least five stations. Policies use only
the fitting-period correlation matrix; the outcome oracle alone sees replay
loss. The candidate selector uses the realized matched-outcome roster; the
resulting common roster contains 14 development networks. Averaged over their
feasible budgets, simple-risk minimax regret was 0.553 °C, compared with 0.607
for greedy mutual information, 0.569 for QR pivoting, 0.681 for even spacing,
and 0.658 for random placement. These exploratory results appear only as
Figure S1 and do not establish a station-removal benefit.

## Text S17. Provider access and redistribution status

The study accessed each provider through its official public service or
download surface. Public access does not by itself grant redistribution. The
archive candidate therefore contains scripts, request metadata, aggregate
losses, and source-QC summaries; provider daily values are omitted unless the
provider's terms explicitly permit redistribution.

| Provider | Official access used | Resolution/QC role | Redistribution treatment |
| --- | --- | --- | --- |
| USGS | Water Data daily-values API | approved daily mean | US Government data; request metadata and derived aggregates releasable |
| ARSO | `vode.arso.gov.si/hidarhiv/` | reviewed daily river archive | raw values omitted pending an explicit redistribution statement |
| CHMI | official hydrological yearbook/download tables | provider daily values | raw values omitted pending an explicit redistribution statement |
| GKD Bayern | official Gewässerkundlicher Dienst downloads | provider daily values | raw values omitted pending an explicit redistribution statement |
| LUBW | official Daten- und Kartendienst session workbook | published daily temperature | raw values omitted; reproducible session route documented |
| RWS | WaterWebservices `OphalenCatalogus` and `OphalenWaarnemingen` | raw observations aggregated to daily mean | raw values omitted pending an explicit redistribution statement |
| FOEN | official water-observation GraphQL service | validated/final daily mean | raw values omitted pending an explicit redistribution statement |
| ECCC | official automated hydrometric/temperature service | no network qualified for the first panel | source-QC metadata only |
| eHYD | official surface-water package and documentation | monthly temperature only; excluded | source-QC metadata only |
| SYKE | official Finnish surface-water temperature source | no network qualified for the first panel | source-QC metadata only |
| NVE | official HydAPI, parameter 1003, daily mean [@nvehydapi2026] | measured river series; quality codes 2--3 and correction code 0 only | NLOD open-data license; 10 second-confirmation networks qualified |
| Canadian Coast Guard | official St. Lawrence ship-channel temperature page [@ccgtemperature2026] | four seasonal stations; provider states observations are not validated or checked | 16,244 values assessed but excluded from strict confirmation |

Software is MIT licensed. The repository URL is a development host; the
archival DOI remains pending and must not be invented. A second independent
confirmation follows the analysis protocol and its dated v2 eligibility
amendment. Before recovery scoring, the amendment recorded the unavailable
validated Canadian source, substituted the Czech and Norwegian validation
domains, and bound the eligible 60-network roster and inputs by hash. The v2
amendment and eventual outcomes are included in the same repository commit,
not a separate public pre-outcome checkpoint; its timing is therefore an
internal provenance claim rather than externally verifiable preregistration.
The analysis cannot reuse any of the 42 first-panel scored networks; source/QC-
only histories are disclosed separately below.

## Text S18. Second-confirmation result and provenance

The v2 roster attempted 60 networks: 35 US, 15 Czech, and 10 Norwegian. Three
US networks had no scoreable B+D evaluation gap, leaving 57 networks and 1,446
station-gap units. The simple model had station-gap Spearman 0.819,
network-level Spearman 0.614, and equal-network calibration slope 1.017. Its
constant interval achieved 91.2% simultaneous network coverage with mean width
6.49 °C.

At the four directly supported horizons, the empirical predictor covered 874
units and had station-gap Spearman 0.945, network-level Spearman 0.805, and
calibration slope 0.938. The other 572 units used the fitting-period network
mean. Across all 1,446 units, empirical station-gap Spearman was 0.740,
network-level Spearman was 0.715, and calibration slope was 0.950. Its
network-block interval achieved 100% row and simultaneous network coverage,
but median width was 8.40 times median loss and mean width was 8.78 °C.

The exact 5% false-release rule, calibrated only on development networks,
certified no nonempty threshold for either the simple or empirical predictor.
Both released zero second-confirmation units, so the triage endpoint failed.

All 13 second-panel networks with at least five stations retained complete
directed 90-day placement matrices; none attrited. Simple-risk minimax mean
regret was 0.241 °C versus 0.256 °C for random placement, a difference of
0.015 °C or 6.0%. Although directionally lower, the protocol contained no
prespecified margin or significance threshold for placement utility. The
result therefore does not establish a confirmatory placement benefit or
support station removal.

No scored second-confirmation network overlaps development or the 42 scored
first-panel networks. Three roster members had appeared in first-panel
source/QC processing but had no recovery outcomes scored there. The outcomes
are therefore independent, while the source-QC history is not wholly new. The
v2 amendment and results share one commit, as disclosed in Text S17.
