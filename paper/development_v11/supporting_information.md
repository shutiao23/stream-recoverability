# Supporting Information for the v11 development manuscript

This document carries protocol history and audit detail so the main text can
follow the scientific chain H1 → H2 → H3. It is not a source of unreported
results.

## Text S1. Prior evidence and reason for redesign

The v9 open-network screen scored 44 public river networks. Network-level
Spearman was 0.67 for the partial operator and 0.80 for donor \(R^2\). A
recorded slice-specific increment over donor \(R^2\) was
\(6.88\times10^{-5}\). The intended
meteorological and hydraulic information coalitions were not connected across
that corpus. Placement exceeded the former 15% target in 2 of 10 rivers, and a
5% false-release setting yielded zero safe fills for both the operator and the
length-only comparator.

Twin E gave operator Spearman 0.936 and calibration slope 0.760, outside its
0.9--1.1 target. A later confirmation attempt performed QC on 40 candidate
networks, retained 32, and stopped before recovery scoring. It produced no
confirmed rank, calibration, incremental-value, placement, or triage result.

These are redesign inputs. V11 does not reinterpret them as a negative sealed
test or as support for either Route A or Route B.

## Text S2. Version and role history

Maintain a dated table for every analysis release with columns:

| Field | Content |
| --- | --- |
| Manuscript route | Route A or Route B |
| Data roles | Open development or new sealed confirmation |
| Independent network count | Candidate, QC-passed, and scored counts |
| Operator definition | Exact B/D/M/H variables and covariance window |
| Calibration definition | Family, fitting rule, and interval construction |
| Recovery outcome | Model rule, gap horizons, placements, and loss |
| Hypothesis thresholds | H1, H2, and H3 numerical criteria |
| Deviations | What changed, when, why, and which data had been examined |

Changes based on open development outcomes are allowed until the advancement
decision. The complete method is then recorded before the new confirmation is
scored. New confirmation outcomes do not select variables, calibration family,
gap horizons, recovery model, baseline, or figure metric.

## Text S3. Network membership and independence

List every network with provider, domain, role, stations, date range, common
days, climate class, network-size class, and regulation/groundwater metadata
when available. Whole networks remain in one role. Jinsha, Chattahoochee, the
previous 12-river pilot, all prior open roles, and every network touched during
the earlier QC attempt are ineligible for the new confirmation.

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
linear and isotonic calibration and give all open-development fold results.

For the 90% prediction interval, state the residual score, calibration unit,
finite-sample quantile, and whether coverage is marginal or conditional. Report
coverage and width at the station-gap and network-summary levels. Do not call a
rank statistic calibration.

## Text S6. Recovery model and mask construction

Document the fixed recovery-model roster, its open-development selection rule,
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
a nested chronological 70/30 split. A B+D XGBoost model with the same frozen
hyperparameters as the outer recovery family is fit on the earlier inner
years. Artificial gaps of 7, 30, 90, and 180 days are scored in the later
inner years after stratification into DJF, MAM, JJA, and SON, with at most 20
evenly spaced placements per cell. Prediction falls back from
station-horizon-season to station-horizon and then network-horizon only when
the finer cell has no eligible truth. The outer evaluation period is never
read while constructing the curve.

The resulting tables contain 47,408 fitting-period placement losses in 51
development networks and 52,989 in all 42 first-confirmation networks. They
support 823 and 780 outer station-gap predictions, respectively. Unsupported
14-, 60-, and 365-day cells are excluded from the empirical-baseline contrast,
not silently interpolated.

## Text S14. Recovery-family sensitivity

Three model families are scored on identical outer gaps:

| Family | Information | Fitting rule |
| --- | --- | --- |
| Seasonal-boundary ridge | annual harmonics and two gap boundaries | fitting-period median imputation, scaling, ridge coefficient |
| Donor covariance ridge | seasonal/boundary terms and synchronous donor temperatures | fitting-period median imputation, scaling, ridge coefficient |
| Gradient boosting | seasonal/boundary terms and synchronous donor temperatures | 300 trees, depth 4, learning rate 0.05, subsample and column sample 0.9 |

The sensitivity does not claim that these three families span all modern water-
temperature reconstruction methods. In particular, no recurrent neural model
was run. It tests whether the simple-descriptor ordering is unique to the
original gradient-boosting loss surface.

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
loss. The corrected candidate selector uses the realized matched-outcome roster
rather than a stale inventory flag; the resulting common roster contains 14
networks. Placement results remain open-development evidence.

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
| Canadian Coast Guard | official St. Lawrence ship-channel temperature page [@ccgtemperature2026] | four seasonal stations; provider states observations are not validated or checked | 16,244 values audited but excluded from strict confirmation |

Software is MIT licensed. The repository URL is a development host; the
archival DOI remains pending and must not be invented. A second independent
confirmation is governed by
`configs/route_a_second_confirmation_protocol.yaml` and cannot reuse any of
the 42 first-confirmation networks.
