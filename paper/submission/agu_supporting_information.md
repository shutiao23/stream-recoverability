---
title: "Supporting Information"
author:
  - "[Authors must match the main manuscript]"
date: "Draft built from repository evidence"
---

# Supporting Information

This Supporting Information accompanies “A Case-Study Covariance Heuristic for Stream-Temperature Recoverability in Two Regulated River Networks.” The submission build expands Texts S1--S15 and embeds supplementary figures and compact tables into one self-contained package.

# Text S1. Extended Methods

## Study area and data

We treated the upper Jinsha River observations as a three-station case study rather than as a spatially representative river-network benchmark. The hydrological stations, ordered from upstream to downstream, were Batang (B1; 29.8500 degrees N, 99.0833 degrees E), Shigu (S2; 26.9067 degrees N, 99.9478 degrees E), and Panzhihua (P3; 26.6386 degrees N, 101.7447 degrees E). Their documented drainage areas were 187,507, 214,184, and 259,177 square kilometres, respectively. The supplied daily records covered 1 January 2006 through 31 December 2020. Published studies identify the corresponding stream-temperature and discharge records as products of the *Annual Hydrological Report of the People's Republic of China, Volume VI: Hydrological Data of the Changjiang River Basin* [@wei2026flowcomposition; @wang2024yangtzetemperature]. A related Figshare archive was used only for provenance reconciliation and was not substituted for the supplied daily files [@wei2026figshare].

The primary response was daily mean stream temperature, denoted $T$ (degrees C). Daily mean discharge $F$ (cubic metres per second) and daily mean water level $L$ (m) were secondary recovery targets and potential auxiliary information for $T$. The main meteorological channels paired with each hydrological station are daily mean air temperature $T_a$ (degrees C), daily precipitation $P$ (mm per day), daily mean wind speed $W$ (m per second), daily mean relative humidity $RH$ (%), and daily all-sky surface shortwave radiation $R_s$ (MJ m$^{-2}$ day$^{-1}$; NASA POWER `ALLSKY_SFC_SW_DWN`). Jinsha bright-sunshine duration $DH$ (h) remains a sensitivity-only channel and is not the main Group D meteorology. The station reconciliation linked B1 to Batang WMO/GSOD 56247099999, S2 to Lijiang 56651099999, and P3 to Huili 56671099999. Supplied `TEMP` values were already expressed in degrees C. Valid `WDSP` values were converted from knots using a factor of 0.514444, and valid `PRCP` values were converted from inches using a factor of 25.4. NOAA Global Surface Summary of the Day documentation supported the wind and precipitation field interpretation [@noaa2025gsod], whereas the `RHMEAN` and `DH` labels were reconciled to the China Surface Climate Daily Value Dataset V3.0 [@nmic2012chinadaily].

The internal study panel is restricted to B1, S2, and P3. Leave-one-station-out and network-failure analyses within this panel are internal spatial-transfer diagnostics, not external validation. Guanyinyan Dam is 27 km upstream of P3, has weekly regulation, passed its impoundment-stage environmental inspection in 2014, began first-unit generation on 20 December 2014, and completed five-unit commissioning in 2016 [@mee2014guanyinyan; @cdt2026guanyinyan]. A separate held-out external protocol was frozen before 2023--2025 performance was observed. It covers five USGS sites on **one** Upper-to-Middle Chattahoochee mainstem panel (02334430, 02335000, 02335450, 02336000, and 02337170; HUC8 03130001 and 03130002, not Lower 03130004), with USGS daily $T$, $F$, and $L$ and nearest-cell NASA POWER meteorology. Site 02334430 is 366 m below Buford Dam, whose hydropower releases draw cold water from near the reservoir bottom [@usgs1973buford; @usace2017buford]. This panel is not five independent basins and not an external copy of nested-point M1.

## Quality control and provenance

The raw station files were ingested through `scripts/01_audit_data.py` and `scripts/02_prepare_data.py`, using the variable definitions in `metadata/data_dictionary.csv` and source notes in `metadata/source_documentation/README.md`. Dates were normalised to calendar days, and duplicate station-date-variable rows or non-numeric measurement values caused an explicit error. A complete daily calendar was constructed before conversion to a long table and a date-indexed wide table. The supplied files did not contain time-zone metadata or the hydrological-day cut-off, so the analysis preserves their reported calendar dates without claiming a midnight-to-midnight aggregation convention.

Confirmed source missing codes were `WDSP = 999.9` and `PRCP = 99.99`. These literals were retained in `raw_value`, converted to missing values in the analysis field, and assigned `natural_observed = false`, `quality_approved = false`, and `qc_status = source_missing`. All other finite supplied measurements were labelled `observed_unflagged` and were eligible for artificial hiding. Here, `quality_approved` is an analysis eligibility flag, not evidence that the provider individually approved every value. The source files contained no per-value quality codes, and no source statement established whether any published daily values had previously been interpolated. We therefore refer to the retained data as published, unflagged values, not as fully traceable raw sensor samples.

The three Jinsha hydrological channels $T$, $F$, and $L$ were finite at every station on all 5,479 dates. Artificial outages therefore define controlled information interventions, not a fitted model of natural failure frequency or duration. Point, block, compound-channel, and station-outage geometries were chosen to separate operationally distinct information losses while preserving known truth.

The audit summarised range, missingness, date continuity, repeated-value runs, abrupt changes, and yearly $F$--$L$ dependence. Candidate steps and constant runs were flagged for review but were not automatically corrected or removed. In particular, B1 water level contains an approximately 8.48 m datum shift at 1 January 2019 without a corresponding discharge shift. The datum change and the November 2018 high-flow episode were retained. Year-specific diagnostics show a near-deterministic rating-curve-like dependence between $F$ and $L$, while the B1 datum change weakens a single full-period relationship. We therefore treat $F$ and $L$ as one hydraulic information family in independence arguments and do not interpret their simultaneous use as two independent information sources. Models using $L$ at B1 inherit the uncorrected datum limitation.

As an external provenance check, monthly aggregates from the Figshare record agreed with most B1 months, whereas S2 showed a 2013--2019 year-order discrepancy. The supplied daily series was retained unchanged, and this mismatch remains a provenance limitation. No outlier was deleted merely because it was hydrologically extreme or because it affected a fitted relationship.

`scripts/14_build_data_versions.py` freezes non-interchangeable internal analysis versions. `published_v1` remains a historical published-reference version. The executable primary version is `published_v2`: published values plus split QC fields (`analysis_eligible`, `provider_qc_status`, `known_issue_flag`). `observed_unflagged` rows are analysis-eligible with `provider_qc_status=unknown` and must not be rewritten as provider-approved. B1 level from 2019-01-01 and S2 hydrology for 2013--2019 carry explicit known-issue flags on the main version. `no_s2_suspect_v2` excludes S2 hydrology for 2013--2019 without reordering it; `b1_no_level_v2` excludes B1 water level; and `b1_shift_sensitivity_v2` applies a hypothetical minus 8.48 m adjustment to B1 level from 2019 onward. Every version has its own artifact hashes and design hash. Primary and sensitivity runs are registered and aggregated separately, and the frozen analysis requires all three sensitivity versions rather than selecting one after observing outcomes.

## Temporal partition, scaling, and analysis windows

We used a fixed chronological partition: 2006--2015 for fitting, 2016--2017 for validation and early stopping, and 2018--2020 for development evaluation. The evidence-facing label for the last interval is `development_test`; the prepared tables retain `test` only as a stored-data split alias. Outcomes from 2018--2020 had been visible before `design_freeze_v1` was written. They are therefore not described as a previously unseen test set and may not be used for further model or protocol tuning. The unified runner fits conventional and machine-learning models on the training interval only; validation data determine early stopping and the small internal-LOSO ridge-penalty choice.

All learned transformations were fitted without development-test information. The prepared-data scaler stores a separate training mean and population standard deviation for every station-variable channel. The official reference adapters and proposed model estimate their feature statistics from eligible training values and store the scaler axes and values in each checkpoint; predicted $T$ quantiles are transformed back to degrees C before scoring. Regression pipelines fit feature medians and standardisation on training rows. The unified runner also derives the 0.10 and 0.90 thresholds, interquartile range, and population standard deviation for each station-variable pair from finite, quality-eligible training observations. Calendar covariates comprise leap-aware sine and cosine terms for day of year and month; no response values are used to construct them.

The principal sequence length was 368 days, with 184- and 736-day window sensitivities. Windows were constructed separately within each temporal split, so no training window crossed into validation or development evaluation. Deep-model training windows used a half-window stride and included a final right-aligned window. At offline inference, the official references, development-only neural baselines, and proposed model used the condition-specific window, a stride of half the window length, and a final right-aligned window; predictions from overlapping windows were averaged only at artificially hidden cells. Window sensitivity therefore changes both the fitted training context and the bounded inference context.

## Validation-only selection and evidence boundary

Model selection is confined to a frozen validation funnel with seven strata at each of the three internal stations: a 30% $T$ point mask; 10-, 30-, 90-, and 180-day $T$ blocks; a synchronized 90-day $T+F+L$ block; and a 90-day hydrological station outage. Each condition is evaluated at five immutable station-specific anchors. Historical `published_v1` selection uses `metadata/validation_anchors.csv`. The executable `published_v2` selection uses `metadata/validation_anchors_v2.csv`. This gives 21 conditions and 105 validation mask units. These artifacts are labelled `model_selection_only`, set `formal_evidence = false`, and cannot enter development or confirmatory performance tables. A required Stage 3 seed that hits the 400-epoch cap is `budget_unstable` and cannot enter the roster.

The first stage evaluates nine traditional candidates. The second stage evaluates official PyPOTS BRITS, SAITS, and CSDI and the proposed model at seed 11, then applies finite-prediction, finite-validation-score, checkpoint, and convergence diagnostics. Candidates retained within the frozen skill tolerance enter a three-seed stability stage with seeds 11, 22, and 33. A model is excluded when any required seed hits the epoch cap (`budget_unstable`) or selects its best checkpoint before epoch 50 (`training_unstable`). The latter is a v5 validity amendment made after validation stability evidence and before a dense aggregate. CSDI is restricted to a seed-11 probabilistic diagnostic at 7, 30, 90, and 180 days and is never a formal frontier model. Affected runs cannot support a general claim about deep-model utility.

## Artificial missingness and experiment suites

Artificial masks had shape date by station by variable and could hide only finite, quality-eligible values. Every selected channel was removed from the input tensor or data frame before prediction, preventing a model from using hidden truth through another feature path. The twenty formal mask seeds were 101--120. The nested-frontier catalog contains twenty fixed, season-balanced centers for every internal station--target pair (five per meteorological season); shorter and longer block masks at one anchor share a center. The point-mask generator uses one season-balanced seeded ranking whose 10%, 30%, and 50% selections are exact prefixes, so lower-rate cells are subsets of higher-rate cells. An anchor that is unavailable under a sensitivity data version is reported rather than replaced by a new draw. The last calendar row was not selected for ordinary offline scenarios, preserving a right-hand observation for two-sided interpolation without borrowing beyond the recorded period. Masks were stored as compact packed bit arrays with a shared axis file and per-scenario metadata.

The executable experiment grid is defined jointly by `study_manifest.yaml`, `configs/experiments.yaml`, and `src/stream_recoverability/experiments/grid.py`:

- **M1, nested points.** For each station, 10%, 30%, or 50% of jointly eligible dates were hidden synchronously for one of $T$, $F$, $L$, or $T+F+L$. The selected date count was the nearest attainable integer count, and all three rates use prefixes of the same seed-specific season-balanced ranking.
- **M2, one continuous block.** A centered 10-, 30-, 90-, or 180-day block was hidden for $T$, $T+F$, $T+L$, or $T+F+L$ at each station. Formal frontier-eligible instances are bound to the frozen anchor catalog rather than independently relocated at each length.
- **M3, separated blocks with a fixed total budget.** The station, variable patterns, and total budgets matched M2, but the budget was divided into $3+3+4$, $10+10+10$, $30+30+30$, or $60+60+60$ days. Successive segments were separated by at least 30 unmasked days.
- **M4, station outage.** One station lost either its hydrological channels $T+F+L$ or all eight measurement channels for 10, 30, 90, or 180 consecutive days.
- **M5, secondary targets.** $F$, $L$, and $F+L$ were hidden at each station under both single-block and fixed-budget multiblock layouts at the four principal lengths. For $F$, the same-site rating-curve model and the explicitly $L$-free flow model separate operational recovery from recovery without the near-duplicate hydraulic channel.
- **M6a, same-station variable asynchrony.** At one station, equal-length component gaps were applied to $T+F$, $T+L$, $F+L$, or $T+F+L$ with requested overlap ratios 1.0, 0.5, or 0.0 and lengths 10, 30, 90, or 180 days. Across three stations, this gives 144 conditions and 2,880 scenarios. The asynchronous axis is the variable, so this design is not a disguised station-pair outage.
- **M6b, cross-station asynchrony.** Each of the three station pairs lost $T+F+L$ under the same four lengths and three overlap ratios. This gives 36 conditions and 720 scenarios. The asynchronous axis is the station; full overlap is synchronous, whereas partial and zero overlap use fixed staggered component blocks.
- **M7a, deterministic aggregate event stress.** For each station and each of high temperature, rapid warming, flood, and low flow, all cells satisfying the frozen train-referenced event definition were hidden once. These 12 aggregate stresses use mask seed 0 because replicating a deterministic 100% event mask under seeds 101--120 would create false replication.
- **M7b, event episodes and matched controls.** High-temperature episodes use train-only day-of-year-local anomaly thresholds; rapid-warming and flow thresholds are station-season specific. Minimum durations, merge rules, flood audit windows, and boundary-context requirements are frozen in `event_catalog_v2`. Each analysis-eligible episode is paired with an exact-length, same-station, same-season non-event control, and both positions are fixed before model evaluation. The committed catalog contains 355 pairs, of which 352 pass the context contract; the 352 eligible pairs produce 704 seed-0 scenarios, one episode and one control per pair.
- **M8, window sensitivity.** The 184-, 368-, and 736-day windows were applied to five B1 anchors: $T$ blocks of 30, 90, and 180 days and hydrological station outages of 90 and 180 days. This is a compact anchor analysis, not a replication of every M1--M7 condition at every window length.
- **M9, block-length extrapolation.** Each station was tested on a 180-day $T$ block under `seen_length` and `unseen_length` training protocols. The former allows training blocks of 10, 30, 90, and 180 days; the latter allows only 10, 30, and 90 days. The current M9 implementation tests unseen length only; paired-station and event-shape extrapolation remain covered by M6 and M7 rather than by a separate M9 training protocol.
- **M10, internal LOSO.** All eligible development-test $T$ values at one held-out station were hidden. A pooled seasonal ridge model was fitted using $T$ labels from the other two stations and their $T_a$, $F$, and $L$ predictors. Its ridge penalty was chosen from 0.1, 1, and 10 on validation rows from those donor stations, after which it predicted the held-out station from the held-out station's $T_a$, $F$, and $L$. Held-out-station $T$ labels from training and validation were not used. M10 is explicitly labelled `exploratory_internal_loso_not_external_validation`; its three deterministic scenarios are not independent replicates.

M1--M4 comprise 156 conditions and yield 3,120 core scenarios. The executable smoke grid contains four conditions and four scenarios, one each from M1--M4. A `full` grid built without an event catalog contains 444 conditions and 8,595 scenarios, but this object is not a formal full suite. The formal published-v2 grid requires `metadata/event_episode_catalog_v2.csv`; with its 704 M7b event/control scenarios it contains 1,148 conditions and 9,299 scenarios. M7a, M7b, and M10 are deterministic singletons as described above; other conditions use twenty mask seeds. Conventional models are evaluated once per scenario. Trainable models use seeds 11, 22, 33, 44, and 55, with a fitted checkpoint reused across compatible masks sharing its training protocol and window.

<!-- protocol-grid-counts: smoke=4/4 core=156/3120 full_catalog=1148/9299 full_without_catalog=444/8595 m6a=144/2880 m6b=36/720 m7a=12/12 m7b=704/704 dense=93/1860 compensation=12/240 resilience=96/1920 retrained=9/180 external=60/60 -->

The dedicated `SCI_DENSE` grid expands the declared block lengths of 1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, and 365 days for $T$, and 3, 10, 30, 60, 90, 120, 180, and 365 days for each of $F$ and $L$. Across three stations this gives 93 single-block conditions and 1,860 scenarios. Every `SCI_DENSE` condition uses a fixed 736-day context and the frozen nested anchors. `SCI_COMPENSATION` contains 12 conditions and 240 base mask scenarios, `SCI_NET` contains 96 conditions and 1,920 scenarios, and the retrained-information grid contains nine 30/90/180-day station--gap conditions and 180 base mask scenarios. Information coalitions and training seeds are run-unit axes and are not included in these scenario counts. Frontier analysis accepts only `SCI_DENSE` and reports no numerical frontier, confidence interval, or breakpoint for a design group that lacks any predeclared gap or required finite value.

## Recovery baselines

The training-period day-of-year climatology was the common reference model. It predicts the median training value within a circular plus or minus seven-day day-of-year neighbourhood, with a training median fallback. Recoverability skill was defined relative to this model. Offline temporal baselines comprised two-sided linear interpolation, shape-preserving piecewise cubic Hermite interpolation without extrapolation, and a local-linear-trend Kalman smoother whose parameters were estimated from training data. The final day exclusion described above avoids an unidentified right edge for the two interpolators.

Regression baselines included a seasonal ridge model using $T_a$ and its interactions with three Fourier harmonics (`air_only`), the same model augmented with same-site $F$ and $L$ (`air_hydro`), and donor regression using the same target at the other two stations plus same-site $T_a$. Donor lags from -30 through +30 days were selected using absolute training correlation only; negative lags are therefore permitted only in the offline task. Random forest and XGBoost models used all available non-target station-variable channels plus seasonal harmonics. Current code defaults are 200 trees with a minimum leaf size of two for the random forest and 300 trees, maximum depth four, learning rate 0.05, row subsampling 0.9, and column subsampling 0.9 for XGBoost. Missing predictors were replaced by training feature medians.

For discharge, a quadratic same-site $L$-to-$F$ rating-curve baseline represents operational recovery when level remains available. The `independent_flow` seasonal ridge excludes the target station's $L$ by construction and uses other-station $F$ together with same-site meteorology. If same-site $L$ is hidden, the rating-curve run is recorded as a structured skip rather than silently imputing its required input.

Formal neural references use the official PyPOTS 1.5 implementations of BRITS, SAITS, and CSDI [@cao2018brits; @du2023saits]. The adapter verifies both the exact installed version and each imported class's PyPOTS module origin and fails closed rather than falling back to a local approximation. BRITS uses recurrent width 64 and target-only masked-imputation weight 1.0. SAITS uses two layers, model width 64, four heads with 16-dimensional keys and values, feed-forward width 128, zero architectural and attention dropout, and equal observed- and masked-reconstruction weights. CSDI uses four layers, eight heads, 64 channels, 50 diffusion steps under the frozen quadratic schedule, 10 validation samples, and 100 formal prediction samples. All three use the same train-only scaling, frozen artificial-missingness curriculum, half-window stride, fixed four-scenario validation score, and checkpoint contract as defined by `design_freeze_v4`. The common formal budget is Adam with learning rate 0.001, batch size eight, at most 400 epochs, patience 20, and gradient clipping at 1.0; selected epochs and complete diagnostics are read from validated checkpoints rather than inferred from the ceiling. Hitting the epoch cap is recorded as `hit_epoch_limit` and labelled `budget_unstable`; such a candidate cannot enter Stage 2 retention or the roster. The cap is not raised again. Compact local BRITS-lite and SAITS-lite implementations remain available only for development and smoke checks and are not formal reference results.

## Missing-aware multisource quantile model

The proposed offline imputer contains a permanent baseline branch S0 and four switchable information groups. S0 contains leap-aware calendar features, a training-only target climatology, and static station identity. Group A is local temporal information: the target value where observed, its availability mask, and normalised distances to the preceding and following observed target, encoded by a bidirectional GRU. Group B is same-station hydraulic information from $F$ and $L$. Group C is other-station $T$, $F$, and $L$, pooled through availability-masked attention over donor stations. Group D is same-station $T_a$, $P$, $W$, $RH$, and $R_s$ only; calendar information is not counted again in D. The architecture token is `s0_abcd_rs_v1` because Group D identity and units changed from sunshine-duration $DH$ hours. Jinsha $DH$ remains sensitivity-only. Each value encoder receives the value, an availability indicator, and a variable embedding. Station embeddings enter the branch encoders, source gate, and output head.

Availability is computed as `natural_observed AND NOT artificial_mask AND finite`. A branch can therefore contribute only when its source exists and its information group is enabled. A learned gate combines available branches; source dropout independently removes A--D during training with probability 0.20 while ensuring that at least one branch remains. The cross-station component is masked attention over the two other stations. It uses no adjacency matrix, message-passing layer, or learned graph and must not be described as a graph neural network or as a GRIN implementation [@cini2022grin]. Attention weights are retained as diagnostics only, not treated as causal information attribution.

The output head produces $q_{0.05}$, $q_{0.25}$, $q_{0.50}$, $q_{0.75}$, and $q_{0.95}$. It predicts a median and positive inner and outer distances through softplus transforms, which guarantees strict ordering of all five quantiles. Training uses equal-weight Huber loss at the median and pinball loss averaged across all five quantiles, only at finite, quality-eligible, artificially hidden $T$ cells; the observed-value consistency term is disabled. Quantile regression and probabilistic scoring follow the usual pinball-loss and proper-scoring-rule framework [@koenker1978quantiles; @gneiting2007scoringrules]. The frozen architecture has hidden width 32, station embeddings of width eight, variable embeddings of width four, bidirectional temporal width 16 per direction, and architectural dropout 0.10. Source dropout remains 0.20. The proposed model uses the common Adam, 400-epoch, patience-20, and gradient-clipping protocol and restores the finite best-validation checkpoint. A seed that hits the epoch cap is `budget_unstable` and cannot enter the roster.

S0 is produced by the proposed checkpoint itself; it is not replaced after inference by a standalone climatology. Its target climatology uses a stable leap-year month--day key, a circular plus or minus seven-day training median, a training-global median fallback, and a distinct 29 February key. The operational compensation estimand evaluates the checkpoint's S0 output plus all 15 non-empty subsets of A--D, giving 16 coalition values on identical hidden cells.

## Offline imputation and online causal recovery

Offline imputation is the primary task. It permits observations on both sides of an artificial gap and therefore includes linear and PCHIP interpolation, Kalman smoothing, bidirectional recurrent processing, and the proposed model's forward/backward time gaps. All channels selected by a scenario are hidden before any model receives the input. Observed development-period covariates outside the artificial gap remain available because the task is reconstruction under a specified monitoring outage, not forecasting.

The secondary online protocol is strictly causal and is implemented separately in `scripts/10_run_online.py`. It disallows future values, backward interpolation, and smoothing. The online references are training day-of-year climatology and last-observation persistence, the latter using training means when no prior observation exists. A forward-only causal GRU consumes masked normalised values, current availability indicators, and elapsed time since each channel was last observed. Its hidden state is propagated chronologically and detached only between optimisation chunks; prediction never reverses the sequence. The model is fitted on training-only artificial point masks, selected on a fixed validation mask, and evaluated on the fixed development-period mask library. Online error is also stratified by days since the last observation into `no_history`, 1, 2--3, 4--7, 8--30, 31--90, and 91+ day bins.

Offline and online results are not pooled into one ranking. In particular, an offline smoother's access to a right boundary is a different information condition from causal recovery at the same nominal gap length.

## Temporally held-out external evaluation

The frozen external protocol uses **one** Upper-to-Middle Chattahoochee mainstem network panel (not five independent basins and not internal nested-point M1) and three non-overlapping intervals: 2012--2020 for fitting, 2021--2022 for validation-only early stopping, and 2023--2025 for confirmation. USGS daily values use statistic code 00003 for water temperature (parameter 00010), discharge (00060), and gauge height (00065). Meteorological covariates are nearest-cell NASA POWER `T2M`, `PRECTOTCORR`, `WS2M`, `RH2M`, and `ALLSKY_SFC_SW_DWN`, stored as $T_a$, $P$, $W$, $RH$, and $R_s$ (MJ m$^{-2}$ day$^{-1}$). Approved and estimated-flagged USGS values are retained, whereas provisional values are excluded under the frozen quality rule.

NASA POWER requests keep `time_standard=UTC` and validate that header in the response. USGS daily values are station-local civil-day statistics; POWER without an override defaults to LST. The UTC versus local/LST mismatch is a calendar-day label-alignment issue, not hydraulic travel time. Lags $\{-1,0,+1\}$ are predeclared under `meteorology_alignment_v1` and must not be selected using confirmatory or development-test performance.

At each site, the confirmatory grid contains a 30% $T$ point mask, 30-, 90-, and 180-day $T$ blocks, and 90- and 180-day hydrological station outages. Each of the six designs is evaluated with full auxiliary information and with group-D meteorology hidden over the target gap, giving 60 conditions and 60 deterministic mask scenarios. The hash-verified validation roster supplies the exact models and the frozen seeds and hyperparameters; trainable architectures are retrained on external training data and use external validation only for early stopping. This is external temporal replication, not zero-shot geographic transfer.

Confirmatory data acquisition is forbidden until `finalized_model_roster_v1` exists. `scripts/19_build_confirmatory_data.py` builds an immutable, source-logged data bundle but never computes performance. `scripts/20_run_confirmatory_evaluation.py --feasibility-only` constructs all 60 masks and checks approved finite $T$ truth without training, scoring, or creating a once-lock. Evaluate-once creates the persistent once-lock only after that dry-run succeeds and cannot be rerun as a tuning opportunity. Ordinary `scripts/08_run_experiments.py` cannot target confirmatory splits. The completed execution contains all 540 expected model--scenario run units, a complete atomic manifest, and a completed once-lock. The frozen best-roster envelope is preserved as a descriptive estimand because it selects the maximum observed performance within a scored cell.

## External validation-period placement diagnostic

The 2021--2022 validation period is used after the frozen analysis to estimate mask-placement scale without reopening confirmation. Five stations, three full-information block lengths, nine roster models, and seeds 101--120 give 2,700 event cells. A restricted local copy physically excludes dates after 31 December 2022. The diagnostic code rejects confirmatory paths, does not read the once-lock, and records `confirmatory_outcomes_read=false`, `confirmatory_metric_uses=0`, and `once_lock_modified=false`. Sample SD uses ddof 1. For the non-oracle main sensitivity, one model per site is selected by mean skill across all 60 validation gap--placement cells and then scored unchanged on 2023--2025. This rule was formulated after the once-open envelope result, so it is post-hoc rather than preregistered. Best-roster envelopes remain descriptive only.

## Independently frozen nationwide regulation panel

`configs/regulation_panel_freeze_v1.yaml` was sealed before national temperature outcomes were read and prohibits any Chattahoochee path. The 2000--2019 panel discovers primary USGS daily-mean water-temperature series, restricts to stream sites exactly matched to GAGES-II, never splices series, and requires at least 10 calendar years with 300 approved days. The observation-only features are the already defined circular-climatology anomaly SD, acf30/acf90, seasonal variance fraction, annual amplitude, observed range, and memory--range index. GAGES-II `MAJ_NDAMS_2009 >= 1` is the routed upstream-major-dam label; NID point proximity is not substituted for watershed routing [@falcone2011gagesii; @usgs2026waterapi; @usace2026nid].

The primary model is `upstream_major_dam_2009 ~ z_memory_range_index`, with HC1 Wald uncertainty. Generalization is the pooled ROC AUC of leave-one-GAGES-II-aggregated-ecoregion-out probabilities; 2,000 ecoregion-cluster bootstrap draws give its interval. Pooled leave-one-ecoregion-out AUC is the frozen primary generalization metric; an AUC near 0.5 does not reopen the freeze. Frozen sensitivities add log drainage area and ecoregion fixed effects and summarize regulated-site nearest-major-dam distance bins.

A post-hoc diagnosis computed AUC inside each held-out ecoregion because pooled out-of-fold AUC under leave-one-group-out can attribute intercept and base-rate mismatch to discrimination. Single-predictor logistic intercepts are calibrated on complementary folds whose dam rate is near 60%, then scored on held-out ecoregions whose dam rates range from 0 to 0.95. This diagnosis does not replace or reopen the freeze.

The modern USGS API returned HTTP 429 after 26/56 atomic batches. Before any panel metric, `regulation_panel_transport_amendment_v1` froze the official legacy daily-values service for stations with exactly one primary series. Multiple-series stations are excluded. Parser qualifier `A:*` is retained as approved. The legacy fallback exactly matches all 1,662,961 approved station-dates present in completed modern batches. The output is labelled transport-limited and reports the API blocker, exclusions, source hashes, cache bootstrap status, and static/runtime confirmatory-isolation audit.

## Information compensation, Shapley attribution, and information metrics

For any event table that contains an explicit `information_combination` (or accepted alias), the analysis converts the error metric into a higher-is-better value function; for MAE, $v(S)=-\mathrm{MAE}(S)$. Controlled removal gains compare the full coalition with the coalition lacking one source and also average that source's marginal gain over all paired coalitions. Exact Shapley contributions are then computed by enumerating every subset of A--D [@shapley1953value]. The calculation is accepted only when all 16 finite coalition values are present within the same scenario, mask seed, training seed, station, target, gap, window, protocol, and model unit; incomplete units return a reason and missing contribution rather than an approximation. Shapley values describe allocation under the chosen value function and coalitions, not causal effects.

The `compensation` entry point in `scripts/12_run_science_experiments.py` writes coalition-labelled predictions for the checkpoint's S0 branch and all 15 non-empty A--D subsets on the same artificial $T$ cells. Hidden truth is replaced by missing input before model inference, which uses the overlapping-window procedure described above. Each scenario-by-training-seed unit is accepted only when all 16 combinations have the same scored cells, all five model quantiles are finite and ordered, MAE and RMSE are finite, and the current input, profile, mask, and checkpoint contract matches. Exact Shapley contributions and four-source interactions are computed only for this complete one-checkpoint operational-dropout estimand. Partial or invalid units are excluded from the aggregate and cannot establish a compensation result merely because the entry point exists.

The separately labelled retrained upper-bound estimand fits one checkpoint per declared coalition and seed using train-only fitting and validation-only early stopping, then evaluates the frozen development masks. Its nine coalitions are S0, S0+A, S0+B, S0+C, S0+D, S0+A+B, S0+A+C, S0+A+D, and S0+A+B+C+D. Because these are only nine of the sixteen possible coalitions and each changes the fitted model, the analysis reports predeclared contrasts and never computes an exact Shapley allocation from them. Operational dropout and retrained upper bounds are stored, aggregated, and analysed separately. Both are formally not applicable when the validation decision is `framework_only`.

The fixed descriptive information metrics use only finite, quality-eligible training observations. By default, each series is converted to an exact month-day training anomaly on a stable leap-year calendar before continuous mutual information is estimated with a five-neighbour k-nearest-neighbour estimator [@shannon1948communication; @kraskov2004mutualinformation]. Directional transfer entropy independently discretises source and target into four empirical-quantile bins and evaluates lags 1, 2, 3, and 7 in both directions. Its null distribution uses 199 circular shifts of the source-bin sequence, preserving source serial dependence while breaking alignment with the target; the permutation $p$-value uses a plus-one correction [@schreiber2000transferentropy]. Reciprocal display rows representing the same directed source--response--lag relation share one hypothesis identifier, estimate, null calculation, and random seed. Benjamini--Hochberg adjustment is applied once to the 288 unique finite transfer-entropy hypotheses, then mapped back to all 312 display rows, including 24 duplicate displays. These measures describe association and directional predictive information, remain sensitive to serial dependence, discretisation, common drivers, missingness, and sample size, and do not establish causality [@jeung2026informationquality].

## Covariance recoverability heuristic

The prediction uses only the fitting period. For each station, exact
calendar-day training medians are subtracted from target and donor temperature.
An ordinary least-squares regression of target anomalies on simultaneous donor
anomalies gives $R^2_{\mathrm{donor}}$. Target-anomaly autocorrelation supplies
local memory at $d/4$, the mean distance from an interior point of a two-sided
block of length $d$ to its nearest observed boundary. One day is the minimum
identifiable lag; fractional lags above one day are linearly interpolated.

The available fraction and implied MAE skill approximation are

$$R^2_{\mathrm{avail}}=R^2_{\mathrm{donor}}+
(1-R^2_{\mathrm{donor}})\rho^2(d/4),$$

$$\widehat{\mathrm{skill}}=1-\sqrt{1-R^2_{\mathrm{avail}}}.$$

The 30-day decomposition classifies a station as donor-dominated when its donor
component is at least its memory component, and memory-dominated otherwise.
The classification is also recomputed at 14, 60, and 90 days. The additive form
does not empirically orthogonalize donor and boundary signals, and the MAE
conversion assumes a common location--scale residual shape. It is therefore a
screening heuristic rather than a physical heat budget, theorem, or information
ceiling.
`recoverability_prediction_v1` was written before a dense development aggregate
existed. It contains no validation, development-test, or confirmatory outcome.

## Hydrothermal state and post-hoc stationarity diagnostics

Annual temperature minima, maxima, means, and amplitudes are calculated in
degrees C. A circular plus or minus seven-day fitting-period climatology defines
anomalies for period summaries. We report anomaly mean, sample SD, lag-30 and
lag-90 autocorrelation, skewness, and excess kurtosis. Across networks, the
descriptive memory--range index is lag-30 anomaly autocorrelation divided by the
fitting-period observed temperature range. It has no universal threshold.

Reviewer-triggered stationarity analyses leave the frozen prediction unchanged.
The heuristic is recalculated over 2016--2017 and, descriptively, 2016--2020. Fixed
development predictions are also re-scored against a 2016--2020 circular
climatology. Because that period includes evaluated outcomes, the latter is a
post-hoc denominator diagnostic rather than predictive evidence. A separate
low-frequency sensitivity subtracts the truth and prediction anomaly mean
independently within each scenario--model--calendar-year unit before computing
MAE and climatology-relative skill. One-day/year units with a denominator at or
below 0.05 degrees C are withheld.

## Recoverability frontiers and monitoring-network resilience

For an event $e$ at gap length $d$, recoverability skill is

\[
\mathrm{Skill}_e(d)=1-\frac{\mathrm{MAE}_{e,\,\mathrm{model}}}
{\mathrm{MAE}_{e,\,\mathrm{climatology}}},
\]

computed on common quality-eligible artificial cells. Skill is withheld when the climatology MAE is non-finite or no greater than half the published measurement resolution: 0.05 degrees C for $T$, 0.5 cubic metres per second for $F$, and 0.005 m for $L$. Formal frontier analysis is restricted to `SCI_DENSE` single blocks at the fixed 736-day window and keeps only complete fixed-anchor curves with finite values at every predeclared gap. Training seeds are collapsed within model--mask--anchor units before inference. Confidence intervals jointly resample whole cross-gap anchor curves within station--year strata, using connected mask-overlap clusters where required; individual hidden days are never treated as independent replicates. The frozen analysis uses 2,000 replicates, seed 20260815, and a 95% interval. Weighted PAVA supplies the non-increasing curve, and a weighted one-hinge fit supplies the predeclared breakpoint diagnostic. The statistical frontier is the first loss of a lower skill confidence bound above zero, with interpolation only between adjacent tested gaps. Frontiers below the smallest or beyond the largest tested gap are labelled left- or right-censored rather than treated as observed crossings. This recoverability event is frozen in `design_freeze_v4` as `statistics.statistical_recoverability` and is not an application or regulatory threshold.

An application frontier requires domain thresholds declared before outcomes are analysed, for example a maximum MAE, maximum extreme-event error, or minimum interval coverage. `design_freeze_v4` declares no such threshold. Consequently, the application boundary is emitted as `withheld_no_predeclared_application_threshold`; no operational tolerance or recoverability boundary is inferred after observing results. Recoverability skill is reported twice: relative to climatology and relative to the validation-selected best simple baseline. A model that beats only climatology does not support a superiority claim.

The dedicated `SCI_NET` design crosses each of three target stations and four target-$T$ gap lengths with the exact eight-element powerset of failures among B1, S2, and P3, giving 96 conditions and 1,920 scenarios over twenty mask seeds. For a fixed target, gap length, and mask seed, every failure subset shares the same target gap; failed stations lose their hydrological $T$, $F$, and $L$ channels over that interval. Resilience analysis accepts only replicate units containing each failure subset exactly once with finite inputs. Mean skill is normalised by the matching positive zero-failure value and integrated over failure fraction only when the curve spans zero to one.

Main-text node importance is cross-fitted by anchor year. Within every target, gap, and failure set, the lowest-mean-MAE roster model is selected on two evaluation years and scored on the held-out third year; climatology is an ordinary candidate and no event-wise error cap is applied. Full- and singleton-failure policies are paired on target-gap id, mask seed, gap, and held-out year before aggregation. A 2,000-draw matched-anchor bootstrap resamples within year. This is explicitly post-hoc because the selection folds belong to development evaluation. The former event-wise best-available estimator with a climatology cap is retained only as a descriptive oracle sensitivity. Because only three internal stations are available, neither estimator defines a general river-network resilience law.

## Evaluation, statistical inference, and scientific diagnostics

Every metric uses the common selection rule

\[
I = \mathrm{quality\_approved}\ \cap\ \mathrm{artificial\_mask}
\ \cap\ \mathrm{finite}(y)\ \cap\ \mathrm{finite}(\hat y).
\]

The common metrics are MAE, RMSE, bias, Pearson and Spearman correlation, NMAE, NRMSE, climatology-relative skill, and left/right gap-boundary jumps. NMAE and NRMSE use the finite, quality-eligible training interquartile range and population standard deviation for the corresponding station-variable pair. The unified runner stores these references with each event row; it does not substitute the evaluated development subset when a training normaliser is unavailable.

Temperature diagnostics include high-temperature MAE and bias, peak magnitude error, threshold-day bias, longest-hot-run error, daily-change MAE, and annual peak magnitude and timing errors. Flow diagnostics include log-MAE, volume bias, PBIAS, NSE, KGE, high- and low-flow MAE, and peak magnitude and timing errors. Level diagnostics include high-level MAE, duration bias, peak-level error, and peak timing. The unified runner passes the finite, quality-eligible training 0.10 and 0.90 thresholds to event scoring and records `threshold_reference_split = train`; missing training thresholds remain unavailable rather than being estimated from development outcomes. No ecological threshold is predeclared, so ecological-threshold diagnostics are explicitly unavailable. Sequence-dependent temperature diagnostics are reported only when a complete development-period reconstruction is present.

For probabilistic $T$, we report pinball loss at each of the five quantiles, empirical coverage and mean width of the $q_{0.05}$--$q_{0.95}$ interval, quantile-crossing rate, and approximate CRPS obtained by trapezoidal integration of pinball loss over the five levels [@gneiting2007scoringrules]. Deterministic models carry only their median prediction and are excluded from interval calibration when lower and upper quantiles are absent. Calibration is first computed within each scenario, mask seed, and training seed without pooling distinct experiment, failure, window, protocol, or information-combination regimes. Uncertainty growth is then assessed across at least three distinct gap lengths within one such regime.

Statistical comparisons use a site-year or connected overlap component, never an individual day and never an overlapping anchor inside one component. Replicate training seeds are first averaged within the same model--scenario unit before models or information conditions are paired. Both frontier denominators now use the same joint cross-gap overlap-aware implementation; the climatology portion of `dual_frontier_comparison.csv` is asserted identical to `statistical_frontiers.csv`. Two-sided Wilcoxon signed-rank tests are computed only when at least five independent clusters are available. Each Jinsha station has one overlap component and three evaluation years, so the 24 model-versus-climatology contrasts are emitted as `withheld_insufficient_independent_clusters`. Climatology self-comparisons remain `reference_not_tested`. Multiplicity control is still defined for the nine named families, but Benjamini--Hochberg is applied only to finite, claim-allowed p-values. An unidentifiable or incomplete family is emitted with an explicit unavailable reason rather than filled with a degenerate $p$ value. Cross-fitted node-importance confidence intervals are withheld under the same five-cluster floor.

Scientific-preservation diagnostics reuse the variable-specific extreme, timing, threshold, and water-balance metrics. Mann--Kendall trend direction and significance and Sen slope are compared between truth and reconstruction [@mann1945trend; @sen1968slope]. Exact all-pair Sen slopes are used up to two million pairs; larger inputs use a declared deterministic sampled-pair estimate. Long-term trend fields are populated only for a complete development-period reconstruction and are accompanied by `long_term_trend_available`, `trend_scope`, and `trend_reason`. Ordinary daily prediction tables contain only artificial cells, so they are labelled `masked_period_local_shape_only`: only explicitly named local slopes are reported, while long-term trend and sequence-dependent metrics remain unavailable. These local summaries are not interpreted as evidence that a recovered full record preserves a long-term trend.

## Reproducibility and implementation status

The project targets Python 3.10 or later, with dependencies declared in `pyproject.toml`; formal reference execution additionally requires exactly `pypots==1.5`. Data preparation, versioning, mask-catalog construction, validation selection, formal execution, aggregation, analysis, and external confirmation are all script-driven. The principal protocol entry points are:

```bash
python scripts/01_audit_data.py
python scripts/02_prepare_data.py
python scripts/07_run_eda.py
python scripts/14_build_data_versions.py
python scripts/16_generate_frontier_anchors.py
python scripts/17_build_event_catalog.py audit
python scripts/18_generate_validation_anchors.py
python scripts/15_run_validation_funnel.py --help
python scripts/08_run_experiments.py --help
python scripts/12_run_science_experiments.py --help
python scripts/21_build_formal_suite_registry.py --help
python scripts/13_aggregate_formal_results.py --help
python scripts/09_analyze_results.py --help
python scripts/19_build_confirmatory_data.py plan
python scripts/20_run_confirmatory_evaluation.py --help
```

The unified runner supports deterministic sharding, atomic per-scenario Parquet output, compact reusable masks, deduplication by scenario/model/training-seed/date/target keys, and resumable execution. Every completed unit is tied to its suite, training profile, model protocol, data-version inputs, mask, checkpoint, frozen design, and relevant source identity; stale or retryable rows are excluded from aggregation. Development-test core/full and dedicated science suites require the hash-verified finalized roster, and an explicit `--models` list cannot override it. A formal full suite additionally requires the frozen event catalog. The run manifest sets `formal_design_complete` only when every expected run unit has contracted finite daily and event evidence or an allowed structural skip, all required seeds are present, and every required checkpoint validates. A directory or manifest labelled `full` is therefore not evidence merely because a shard or `--max-scenarios` invocation finished.

`scripts/21_build_formal_suite_registry.py` constructs one immutable registry from explicitly named completed manifests and performs no historical-tree discovery. The primary registry must provide the `core_full`, `dense_frontier`, `network_resilience`, and `event_uncertainty` roles. It must also provide `operational_dropout` and `retrained_upper_bound` when the proposed model is formally authorized, or explicit not-applicable records when the paper is `framework_only`. Each non-primary data-version registry separately requires `sensitivity_core_T` and `sensitivity_dense_frontier`, plus `sensitivity_operational_dropout` or its explicit not-applicable record. `scripts/13_aggregate_formal_results.py` validates those registries, the exact runner inventories, artifact hashes, roster authorization, anchors, event catalog, data versions, and source identities before replacing an aggregate. The frozen analysis consumes one complete top-level aggregate and rejects incomplete evidence roles, mixed data versions, or unregistered outputs.

Smoke modes remain implementation checks. The unified smoke suite selects one M1, M2, M3, and M4 condition, one mask seed, and one training seed. `scripts/05_train_deep_baselines.py --smoke` exercises only local lite implementations; `scripts/06_train_proposed.py` is synthetic-only; and `scripts/10_run_online.py --smoke` uses a reduced causal protocol. None may be cited as a formal experiment. Current numerical findings are populated only from the complete internal analysis manifest, the complete external confirmation manifest and once-lock, and the post-freeze revision manifest. `scripts/34_run_major_revision.py` reproduces hydrothermal-state, stationarity, absolute-MAE, regulation-fingerprint, corrected node-importance, and external-summary artifacts without modifying the frozen prediction.


# Text S2. Independence and Matching Audits

These tables document **temporal overlap, matching balance, and pseudo-replication** in frozen catalogs. They are **not** validation-funnel ranks, MAE, skill, or formal recoverability results.

Regenerate with:

```bash
PYTHONPATH=src python scripts/22_audit_anchor_independence.py
PYTHONPATH=src python scripts/23_audit_event_matching.py
```

Machine-readable copies live under `results/audits/`.

## S1.1 Validation anchors (P0-5)

The ranking design has 105 apparent units (3 stations × 5 anchors × 7 strata). Those units are **not iid**. Every station’s five 180-day anchors occupy only calendar years 2016 and 2017 (`n_years=2 ≠ n_anchors=5`).

Named findings:

1. **B1-R0105 (2016-12-02) and B1-R0101 (2016-12-19)** share a 163-day window (Jaccard 0.827).
2. Seven of 30 same-station pairs have Jaccard ≥ 0.5.
3. Per-station effective sample size (union days / 180): B1 2.34, S2 2.49, P3 2.97.
4. **B1-R0102 and S2-R0105** share the identical centre date 2017-03-27.

Frontier 365-day windows collapse to effective *n* about 2.6–3.0. That is an overlap note, not a performance frontier.

Placeholder ranking CSVs keep `pending_validation_results=true` and do not invent ranks.

## S1.2 M7b event/control catalog (P0-6)

M7a aggregate stress is excluded from this table.

1. Controls match on station, season, and exact length only. Year and day-of-year are ranking distances, not hard constraints.
2. 296 of 355 pairs abut (gap = 0; fraction 0.834).
3. Pre-event T/F/Ta standardised mean differences are `not_in_catalog`, not invented.
4. 20 strata have *n*<5; 7 station/event/season cells are empty.
5. 12 same-type flood window-overlap pairs; date-overlap clustering yields effective *n* = 80 versus 355 episodes.

## S1.3 Consequence for later statistics

Cluster bootstrap and overlap-aware effective *n* are required. Daily cells are not independent replicates. These audits do not authorise a model roster.


# Text S3. Validation-only model funnel

Official BRITS, SAITS, CSDI, and the proposed multisource quantile model were evaluated with train-only scaling and the frozen 400-epoch budget. Required seeds with `best_epoch < 50` or an epoch-cap hit were labelled `training_unstable` or `budget_unstable` and excluded from the formal roster. The early-epoch rule is a v5 validity amendment, not independent evidence that early convergence is scientifically invalid. Rankings, checkpoint histories, and stability diagnoses are `model_selection_only`, `formal_evidence=false`, and do not support a “deep learning is ineffective” claim. Persistence and climatology remain the only simple baselines that share the same information budget as the formal roster; Air2stream, process-guided deep learning, and graph imputers are declared in the locked comparison protocol and were not run for this revision.

# Text S4. Proposed-model information groups

S0 is permanent calendar climatology. Group A is target history and boundary distance, B is same-site hydraulics, C is other-site hydrology and temperature, and D is same-site meteorology. These are predictive information contracts, not a heat-balance decomposition. Validation branch-removal deltas are retained only as mechanism diagnostics. The architecture uses masked attention over the two other Jinsha stations and must not be described as a graph neural network.

# Text S5. Hydrothermal state and P3 change-date sensitivity

The files `results/revision/annual_thermal_metrics.csv` and `results/revision/period_thermal_metrics.csv` contain every annual P3 minimum and amplitude and the pre/post anomaly SD, acf30, acf90, skewness, and excess kurtosis used in the manuscript. `results/revision/p3_change_point_summary.csv` reports Pettitt and least-squares single-break dates, iid reference p values, dependence-aware calendar-year permutation p values, and 365-day residual-block bootstrap intervals. The primary Pettitt interval does not cover commissioning; the least-squares sensitivity interval does. Neither date identifies a causal reservoir effect.

# Text S6. Stationarity and low-frequency controls

`stationarity_controlled_budgets.csv`, `budget_evaluation_summary.csv`, and `dense_skill_sensitivities.csv` distinguish the frozen 2006--2015 prediction from post-hoc 2016--2017, 2016--2020, and annual-demeaned diagnostics. The 2016--2020 climatology overlaps evaluation years and is a denominator diagnosis, not a new test.

# Text S7. Omitted-covariate budget

`expanded_covariate_budget.csv` adds same-site air temperature, discharge, and level and donor-site air temperature and discharge to the anomaly regression. The P3 long-gap skill approximation rose only from 0.055 to 0.077, so omission of measured air temperature and hydraulics is not a sufficient explanation of the memory-dominated label.

# Text S8. Frontier-path repair and withheld inference

Both frontier denominators now use the canonical overlap-aware implementation. After this revision, p-values and confidence intervals are withheld wherever the independent site-year or overlap-cluster count is below five. The climatology rows of `dual_frontier_comparison.csv` still match `statistical_frontiers.csv` cell for cell, including the withheld fields. Descriptive skill and MAE curves remain. The former 10^{-6} Wilcoxon p-values are not scientific results.

# Text S9. Corrected hypothesis family

The model-versus-climatology family still contains 24 candidate contrasts and three `reference_not_tested` climatology rows. Because each station has one overlap component and three evaluation years, every finite test is now `withheld_insufficient_independent_clusters`. Benjamini--Hochberg adjustment is therefore applied to an empty finite family. No main-text significance claim uses these rows.

# Text S10. Cross-fitted node importance

`node_importance_cross_fitted.csv` selects models on other evaluation years and scores the held-out year. The former event-wise best-available table is a descriptive oracle sensitivity only. The 80 nested gap/anchor events are not independent. With only three evaluation years, bootstrap confidence intervals are withheld. Point estimates, including the 0.105 °C S2-to-B1 mean, remain descriptive post-hoc sensitivities and are not a station-protection ranking.

# Text S11. Donor falsification

Same-day, lag, lead, identity-permutation, and seasonal-residual contrasts are in `donor_c_falsification_effects.csv`. The decision remains `falsified_network_propagation` and the permitted language is `correlated_predictive_source_only`. The previously reported Wilcoxon p value on 60 paired units is not treated as independent-sample confirmation.

# Text S12. Temporally held-out external evaluation

The complete 540-unit output is bound to the external once-lock. Train-only type labels and predicted curves were frozen before 2023--2025 outcomes. The main-text fixed XGBoost scores use a model-selection rule formulated after the confirmatory envelope had been observed. They are a labelled post-hoc sensitivity, not preregistered confirmation. Fixed-model SDs use 20 validation placements and are descriptive noise scales, not confidence intervals for the single held-out placement. A sealed multi-network protocol for a future confirmatory experiment is in `configs/confirmatory_multi_network_protocol_v1.yaml`.

# Text S13. Data and software rights

`DATA_RIGHTS.md` and `metadata/data_rights.csv` govern restricted Jinsha and public USGS/NASA materials. Restricted daily values are not SI data. Jinsha source quality remains incomplete: per-value quality codes, instrument/calibration records, time zone, hydrological-day cut-off, and a statement that published daily temperatures were never interpolated are all unavailable. Dates that cannot be shown to be uninterpolated must not be treated as fully traceable artificial-mask truth. The submission gate remains `NO-GO` until editor approval, GEMS upload, author metadata, and a software DOI exist.

# Text S14. Independently frozen national regulation panel

The independently frozen national panel remains `regulation_panel_v1_legacy_transport`. The frozen primary pooled leave-one-ecoregion-out AUC of 0.407 is retained as a preregistered defective diagnostic: it mixes fold intercept and base-rate mismatch with discrimination. It is not a valid standalone generalization metric and is not the paper headline. Adjusted ecoregion coefficients that explode under complete separation are suppressed. A Firth unadjusted odds ratio and a 62-station common-period coverage sensitivity are reported in `results/revision/national_valid_metrics.json`. No independent national holdout was opened.

# Text S15. Post-hoc within-fold leave-one-ecoregion-out AUC

After the freeze, AUC was computed inside each held-out ecoregion. The post-hoc mean within-fold AUC is 0.526 and the median is 0.513 (nine defined folds). This macro-AUC is the valid fold-comparable level. It still finds no national skill. The post-hoc correlation between fold base rate and fold out-of-fold probability median is $-0.671$. Alaska is not defined ($n=6$, all unregulated). Northeast 0.755 and Southeast Plains 0.132 are labelled post-hoc and have no independent verification. This diagnosis does not replace or reopen the freeze.

# Figure S1. P3 Change-Date Sensitivity

![P3 change-date sensitivity](/home/lzq/workspace/parttime/stream-recoverability/results/revision/p3_change_point_diagnostic.png){ width=95% }

*Figure S1. Daily fitting-period anomalies, Pettitt and least-squares single-break diagnostics, dependence-aware bootstrap intervals, first-unit operation, and annual endpoints. Only the least-squares sensitivity interval covers 20 December 2014.*


## Table S1. Recoverability-type sensitivity across classification horizons
| network                     | station_id   |   gap_length |   donor_component |   memory_component | recoverability_type   |
|:----------------------------|:-------------|-------------:|------------------:|-------------------:|:----------------------|
| Upper Jinsha                | B1           |           14 |             0.464 |              0.222 | donor_dominated       |
| Upper Jinsha                | B1           |           30 |             0.464 |              0.058 | donor_dominated       |
| Upper Jinsha                | B1           |           60 |             0.464 |              0.022 | donor_dominated       |
| Upper Jinsha                | B1           |           90 |             0.464 |              0.009 | donor_dominated       |
| Upper Jinsha                | P3           |           14 |             0.106 |              0.714 | memory_dominated      |
| Upper Jinsha                | P3           |           30 |             0.106 |              0.553 | memory_dominated      |
| Upper Jinsha                | P3           |           60 |             0.106 |              0.434 | memory_dominated      |
| Upper Jinsha                | P3           |           90 |             0.106 |              0.361 | memory_dominated      |
| Upper Jinsha                | S2           |           14 |             0.47  |              0.252 | donor_dominated       |
| Upper Jinsha                | S2           |           30 |             0.47  |              0.079 | donor_dominated       |
| Upper Jinsha                | S2           |           60 |             0.47  |              0.017 | donor_dominated       |
| Upper Jinsha                | S2           |           90 |             0.47  |              0.008 | donor_dominated       |
| Upper--Middle Chattahoochee | 02334430     |           14 |             0.367 |              0.515 | memory_dominated      |
| Upper--Middle Chattahoochee | 02334430     |           30 |             0.367 |              0.507 | memory_dominated      |
| Upper--Middle Chattahoochee | 02334430     |           60 |             0.367 |              0.452 | memory_dominated      |
| Upper--Middle Chattahoochee | 02334430     |           90 |             0.367 |              0.398 | memory_dominated      |
| Upper--Middle Chattahoochee | 02335000     |           14 |             0.853 |              0.043 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335000     |           30 |             0.853 |              0.043 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335000     |           60 |             0.853 |              0.038 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335000     |           90 |             0.853 |              0.029 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335450     |           14 |             0.913 |              0.027 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335450     |           30 |             0.913 |              0.027 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335450     |           60 |             0.913 |              0.022 | donor_dominated       |
| Upper--Middle Chattahoochee | 02335450     |           90 |             0.913 |              0.016 | donor_dominated       |
| Upper--Middle Chattahoochee | 02336000     |           14 |             0.925 |              0.025 | donor_dominated       |
| Upper--Middle Chattahoochee | 02336000     |           30 |             0.925 |              0.019 | donor_dominated       |
| Upper--Middle Chattahoochee | 02336000     |           60 |             0.925 |              0.014 | donor_dominated       |
| Upper--Middle Chattahoochee | 02336000     |           90 |             0.925 |              0.01  | donor_dominated       |
| Upper--Middle Chattahoochee | 02337170     |           14 |             0.868 |              0.045 | donor_dominated       |
| Upper--Middle Chattahoochee | 02337170     |           30 |             0.868 |              0.031 | donor_dominated       |
| Upper--Middle Chattahoochee | 02337170     |           60 |             0.868 |              0.02  | donor_dominated       |
| Upper--Middle Chattahoochee | 02337170     |           90 |             0.868 |              0.015 | donor_dominated       |
## Table S2. P3 change-date sensitivity
| role               | method                                   | series                                                         | point_date   | ci_lower_date   | ci_upper_date   | event_date   | event_in_95pct_bootstrap_ci   | earliest_admissible_point_date   | latest_admissible_point_date   | ci_lower_hits_admissible_boundary   | ci_upper_hits_admissible_boundary   |      statistic | signed_statistic   | asymptotic_p_value_iid   |   iid_permutation_p_value |   iid_permutation_exceedances |   calendar_year_block_permutation_p_value |   calendar_year_block_permutation_exceedances |   n_permutations |   n_bootstrap |   bootstrap_block_length_days |   min_segment_days |   n_daily_observations |   first_segment_level_degC |   second_segment_level_degC |   level_change_degC |
|:-------------------|:-----------------------------------------|:---------------------------------------------------------------|:-------------|:----------------|:----------------|:-------------|:------------------------------|:---------------------------------|:-------------------------------|:------------------------------------|:------------------------------------|---------------:|:-------------------|:-------------------------|--------------------------:|------------------------------:|------------------------------------------:|----------------------------------------------:|-----------------:|--------------:|------------------------------:|-------------------:|-----------------------:|---------------------------:|----------------------------:|--------------------:|
| primary            | pettitt_rank_location_change             | P3 daily temperature minus frozen-training circular DOY median | 2013-05-26   | 2011-05-14      | 2013-10-22      | 2014-12-20   | False                         | 2007-01-01                       | 2015-01-01                     | False                               | False                               |    1.31743e+06 | -1317432.0         | 0.0                      |                         0 |                             0 |                                     0.009 |                                            87 |             9999 |          5000 |                           365 |                365 |                   3652 |                     -0.2   |                       0.7   |               0.9   |
| robust_sensitivity | single_binary_segmentation_least_squares | P3 daily temperature minus frozen-training circular DOY median | 2014-10-18   | 2014-04-16      | 2015-01-01      | 2014-12-20   | True                          | 2007-01-01                       | 2015-01-01                     | False                               | True                                | 1207.65        | undefined          | undefined                |                         0 |                             0 |                                     0.012 |                                           116 |             9999 |          5000 |                           365 |                365 |                   3652 |                     -0.073 |                       1.693 |               1.767 |
## Table S3. State sensitivity of the covariance heuristic
| analysis                            | station_id   |   correlation |   mean_absolute_skill_error |   best_exceeds_budget_count |   best_lower_ci_exceeds_budget_count |   comparison_cells |
|:------------------------------------|:-------------|--------------:|----------------------------:|----------------------------:|-------------------------------------:|-------------------:|
| bridge_2016_2017_climatology        | B1           |         0.695 |                       0.068 |                           4 |                                    0 |                 15 |
| bridge_2016_2017_climatology        | P3           |         0.824 |                       0.263 |                          11 |                                   10 |                 15 |
| bridge_2016_2017_climatology        | S2           |         0.885 |                       0.06  |                           4 |                                    0 |                 15 |
| original_training_climatology       | B1           |         0.722 |                       0.077 |                           4 |                                    0 |                 15 |
| original_training_climatology       | P3           |         0.953 |                       0.122 |                          15 |                                    9 |                 15 |
| original_training_climatology       | S2           |         0.94  |                       0.085 |                           1 |                                    0 |                 15 |
| state_matched_2016_2020_climatology | B1           |         0.571 |                       0.18  |                           0 |                                    0 |                 15 |
| state_matched_2016_2020_climatology | P3           |         0.979 |                       0.236 |                           4 |                                    1 |                 15 |
| state_matched_2016_2020_climatology | S2           |         0.93  |                       0.177 |                           0 |                                    0 |                 15 |
## Table S4. Cross-fitted singleton-failure effects
| station_id   | failed_station_id   |   full_network_value |   failed_value |   impact | impact_ci_lower   | impact_ci_upper   |   n_events |
|:-------------|:--------------------|---------------------:|---------------:|---------:|:------------------|:------------------|-----------:|
| B1           | B1                  |                0.52  |          0.497 |   -0.023 | undefined         | undefined         |         80 |
| B1           | P3                  |                0.52  |          0.507 |   -0.013 | undefined         | undefined         |         80 |
| B1           | S2                  |                0.52  |          0.625 |    0.105 | undefined         | undefined         |         80 |
| P3           | B1                  |                0.489 |          0.547 |    0.058 | undefined         | undefined         |         80 |
| P3           | P3                  |                0.489 |          0.5   |    0.011 | undefined         | undefined         |         80 |
| P3           | S2                  |                0.489 |          0.543 |    0.054 | undefined         | undefined         |         80 |
| S2           | B1                  |                0.487 |          0.51  |    0.023 | undefined         | undefined         |         80 |
| S2           | P3                  |                0.487 |          0.482 |   -0.005 | undefined         | undefined         |         80 |
| S2           | S2                  |                0.487 |          0.494 |    0.007 | undefined         | undefined         |         80 |
## Table S5. Held-out Chattahoochee fixed-model evaluation
|   station_id | predicted_type   | validation_selected_model   |   observed_selected_skill_30d |   observed_selected_skill_90d |   observed_selected_skill_180d | qualitative_prediction_consistent   |
|-------------:|:-----------------|:----------------------------|------------------------------:|------------------------------:|-------------------------------:|:------------------------------------|
|     02334430 | memory_dominated | xgboost                     |                        -0.209 |                        -0.38  |                         -0.3   | True                                |
|     02335000 | donor_dominated  | xgboost                     |                         0.47  |                         0.626 |                          0.726 | True                                |
|     02335450 | donor_dominated  | xgboost                     |                         0.513 |                         0.626 |                          0.555 | True                                |
|     02336000 | donor_dominated  | xgboost                     |                         0.447 |                         0.889 |                          0.746 | True                                |
|     02337170 | donor_dominated  | xgboost                     |                         0.84  |                         0.8   |                          0.724 | True                                |
## Table S6. Regulated-site distance profile
| distance_bin_km   |   distance_lower_km |   distance_upper_km |   station_count |   median_memory_range_index_per_degC |   median_memory_range_index_per_degC_ci_low |   median_memory_range_index_per_degC_ci_high |   median_acf30 |   median_acf30_ci_low |   median_acf30_ci_high |   median_annual_amplitude_degC |   median_annual_amplitude_degC_ci_low |   median_annual_amplitude_degC_ci_high |
|:------------------|--------------------:|--------------------:|----------------:|-------------------------------------:|--------------------------------------------:|---------------------------------------------:|---------------:|----------------------:|-----------------------:|-------------------------------:|--------------------------------------:|---------------------------------------:|
| [0,5)             |                   0 |                   5 |              83 |                                0.011 |                                       0.007 |                                        0.016 |          0.262 |                 0.179 |                  0.327 |                         21.5   |                                  16.7 |                                  23.85 |
| [5,20)            |                   5 |                  20 |              61 |                                0.007 |                                       0.004 |                                        0.013 |          0.172 |                 0.116 |                  0.263 |                         23.5   |                                  19.5 |                                  26.2  |
| [20,50)           |                  20 |                  50 |              50 |                                0.006 |                                       0.004 |                                        0.009 |          0.157 |                 0.106 |                  0.174 |                         23.375 |                                  19.2 |                                  26.3  |
| [50,100)          |                  50 |                 100 |              14 |                                0.005 |                                       0.003 |                                        0.008 |          0.135 |                 0.082 |                  0.163 |                         25.375 |                                  19.3 |                                  27.65 |
| [100,inf)         |                 100 |                 inf |               1 |                                0.002 |                                       0.002 |                                        0.002 |          0.07  |                 0.07  |                  0.07  |                         27.2   |                                  27.2 |                                  27.2  |
## Table S7. National-panel regression estimates with separated terms suppressed
| model                           | term                  | coefficient_log_odds   | robust_se   | wald_p_value   | coefficient_ci_low   | coefficient_ci_high   | odds_ratio   | odds_ratio_ci_low   | odds_ratio_ci_high   | complete_separation_flag   | reporting_status               |
|:--------------------------------|:----------------------|:-----------------------|:------------|:---------------|:---------------------|:----------------------|:-------------|:--------------------|:---------------------|:---------------------------|:-------------------------------|
| primary_unadjusted              | const                 | 0.513                  | 0.114       | 0.0            | 0.29                 | 0.735                 | 1.67         | 1.337               | 2.086                | False                      | reported                       |
| primary_unadjusted              | z_memory_range_index  | 0.204                  | 0.14        | 0.144          | -0.07                | 0.478                 | 1.227        | 0.933               | 1.614                | False                      | reported                       |
| adjusted_ecoregion_and_drainage | const                 | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | z_memory_range_index  | 0.923                  | 0.386       | 0.017          | 0.167                | 1.679                 | 2.517        | 1.182               | 5.36                 | False                      | reported                       |
| adjusted_ecoregion_and_drainage | z_log1p_drainage_area | 2.361                  | 0.255       | 0.0            | 1.862                | 2.86                  | 10.603       | 6.437               | 17.464               | False                      | reported                       |
| adjusted_ecoregion_and_drainage | ecoregion_CntlPlains  | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_EastHghlnds | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_MxWdShld    | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_NorthEast   | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_SECstPlain  | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_SEPlains    | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_WestMnts    | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_WestPlains  | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
| adjusted_ecoregion_and_drainage | ecoregion_WestXeric   | undefined              | undefined   | undefined      | undefined            | undefined             | undefined    | undefined           | undefined            | True                       | suppressed_complete_separation |
## Table S8. Post-hoc within-fold leave-one-ecoregion-out AUC
| held_out_ecoregion   |   n |   n_regulated |   n_unregulated |   base_rate |   oof_probability_median | within_fold_auc   |
|:---------------------|----:|--------------:|----------------:|------------:|-------------------------:|:------------------|
| NorthEast            |  33 |            24 |               9 |       0.727 |                    0.592 | 0.755             |
| EastHghlnds          |  31 |            22 |               9 |       0.71  |                    0.596 | 0.742             |
| CntlPlains           |  22 |            13 |               9 |       0.591 |                    0.609 | 0.667             |
| MxWdShld             |  15 |            11 |               4 |       0.733 |                    0.591 | 0.614             |
| WestMnts             | 123 |            74 |              49 |       0.602 |                    0.708 | 0.513             |
| WestXeric            |  16 |            13 |               3 |       0.812 |                    0.602 | 0.487             |
| WestPlains           |  20 |            19 |               1 |       0.95  |                    0.559 | 0.421             |
| SECstPlain           |   6 |             1 |               5 |       0.167 |                    0.609 | 0.4               |
| SEPlains             |  63 |            32 |              31 |       0.508 |                    0.652 | 0.132             |
| Alaska               |   6 |             0 |               6 |       0     |                    0.722 | undefined         |

# Evidence Boundaries

Validation-only model rankings are not manuscript performance evidence. State-matched, annual-demeaned, cross-fitted node-importance, external fixed-model, and within-fold leave-one-ecoregion-out AUC analyses are post-hoc sensitivities. The frozen primary national metric remains the pooled leave-one-ecoregion-out AUC, now labelled a preregistered defective diagnostic. The valid post-hoc level is the macro within-fold AUC. The Chattahoochee panel is one temporal/network evaluation, not five independent basins. No ecological, application, or regulatory safe-fill threshold was declared. Data and software are archived separately and are not Supporting Information.
