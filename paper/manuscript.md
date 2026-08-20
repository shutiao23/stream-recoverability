# Recoverability of Daily Stream Temperature under Structured Monitoring Gaps: A Multisource Upper Jinsha River Case Study

## 1. Introduction

Continuous daily stream-temperature records are difficult to maintain, yet gaps can distort estimates of thermal magnitude, timing, extremes, and trend. The problem is not limited to predicting isolated missing points. Monitoring failures often remove continuous blocks, disable several variables at one station, or affect multiple stations at once. The consequences depend on gap duration and on which other observations remain available. Guidance for annual stream-temperature analysis therefore emphasises the structure and duration of missing periods, not only the overall fraction missing [@johnson2021datagap]. Existing stream-temperature reconstruction methods show the value of paired air temperature, discharge, seasonal structure, and neighbouring sensors [@li2017streamairimputation; @bal2023streamtemperature], but their performance in one setting does not establish how long or information-poor a gap can become before useful reconstruction is lost.

Time-series imputation has advanced through bidirectional recurrent models, mask-aware self-attention, probabilistic diffusion, and graph-based spatial models [@cao2018brits; @du2023saits; @tashiro2021csdi; @cini2022grin]. At the same time, benchmark studies have shown why comparisons based only on independent random deletion may poorly represent operational failures [@du2024tsibench; @toye2025realworldbenchmark]. Hydrological applications add a second difficulty: auxiliary inputs such as flow, level, meteorology, or donor-station measurements may be unavailable together with the target [@gauch2025missinginputs]. Treating these sources as permanently observed can overstate practical recoverability.

We use *recoverability* to mean the ability to reconstruct a predeclared missing target under a stated gap geometry and information condition, relative to a training-period climatology and, separately, relative to the validation-selected best simple baseline. This definition separates four questions that a single average-error ranking cannot answer. First, how does performance change from points to long blocks and station outages? Second, which combinations of local history, same-station hydraulics, other stations, and meteorology compensate for missing target information? Third, how does the monitoring network degrade as stations fail? Fourth, do reconstructions preserve extremes, timing, uncertainty calibration, and scientifically relevant temporal summaries rather than only pointwise accuracy? Related multi-station stream-temperature work has jointly modelled discharge and temperature, compared river-network graph models under unseen conditions, injected process knowledge into temperature models, and studied compressed-sensing recoverability of monitoring series [@sadler2022multitask; @topp2023shifting; @read2019pgdl; @zhang2023compressedsensing]. The remaining gap is not that missing values are unstudied. It is that structured gap length, auxiliary-information failure, station failure, calibration, and an independent temporal replication have not been quantified under one leakage-controlled contract. Information quantity and predictive information can help describe these patterns, but they are sensitive to data quality and do not by themselves identify causal mechanisms [@jeung2026informationquality].

This study develops a fixed, leakage-controlled evaluation for daily temperature, discharge, and level at three upper Jinsha River stations from 2006 to 2020. It compares conventional interpolation and regression, official PyPOTS 1.5 recurrent, attention, and diffusion references, and a missing-aware multisource quantile model under deterministic artificial gaps. Local compact BRITS-lite and SAITS-lite adapters are implementation checks only. Dense gap-length experiments define statistical recoverability frontiers; exact source coalitions support Shapley allocation; transfer-entropy and mutual-information estimates provide descriptive information diagnostics; and a complete station-failure powerset tests internal network redundancy. A separate forward-only protocol distinguishes offline reconstruction, which may use both gap boundaries, from causal online recovery. The study is deliberately a three-station case study: its leave-one-station-out analysis is internal and is not external validation.

## 2. Methods

### 2.1 Study records and data integrity

The study stations, ordered downstream, were Batang (B1), Shigu (S2), and Panzhihua (P3). Supplied daily hydrological records covered 1 January 2006 through 31 December 2020. The primary target was mean stream temperature, $T$ (degrees C); discharge, $F$ (m$^3$ s$^{-1}$), and water level, $L$ (m), were secondary targets and potential auxiliaries. Station-matched meteorological channels were mean air temperature, precipitation, wind speed, relative humidity, and surface shortwave radiation ($R_s$; NASA POWER `ALLSKY_SFC_SW_DWN`). Jinsha bright-sunshine duration ($DH$, hours) is a sensitivity-only channel and is not the main Group D meteorology. Published studies identify the hydrological records as products of the *Annual Hydrological Report of the People's Republic of China, Volume VI* [@wei2026flowcomposition; @wang2024yangtzetemperature]. A related Figshare archive was used only to reconcile provenance and was not substituted for the supplied daily files [@wei2026figshare]. Meteorological field interpretations were checked against NOAA GSOD and the China Surface Climate Daily Value Dataset V3.0 [@noaa2025gsod; @nmic2012chinadaily].

Dates were normalised to a complete daily calendar. Duplicate station-date-variable rows and non-numeric measurements caused an error. Confirmed wind and precipitation source-missing codes were retained in a raw-value field, converted to missing analysis values, and excluded from artificial hiding. Other finite supplied measurements were labelled `observed_unflagged`; this is an analysis eligibility label, not evidence of provider-level quality approval. The source files contained neither per-value quality codes nor documentation establishing whether published values had previously been interpolated. Candidate steps, constant runs, and extremes were audited but not automatically altered. A B1 level datum shift near 1 January 2019 and a 2013--2019 year-order discrepancy between supplied S2 values and a provenance-check archive were retained as limitations. Because discharge and level showed rating-curve-like dependence, they were treated as one hydraulic information family in independence arguments.

No external station panel with a reusable, comparable daily temperature record was established. Natural missing values remained missing and were never used as artificial test targets. All primary inference therefore concerns published, unflagged values at B1, S2, and P3.

### 2.2 Temporal separation, scaling, and artificial gaps

The fixed chronological split used 2006--2015 for fitting, 2016--2017 for validation and early stopping, and 2018--2020 for evaluation. Models were fitted on the training interval rather than refitted on training plus validation. Feature scalers, medians, climatologies, event thresholds, and normalising interquartile ranges and standard deviations were estimated only from finite, quality-eligible training observations. High-temperature and flood thresholds were training 0.90 quantiles, low-flow thresholds were training 0.10 quantiles, and rapid warming used the training 0.90 quantile of eligible daily temperature differences. Missing training references remained unavailable rather than being estimated from test values.

Artificial masks could hide only finite, eligible values and were removed from every model input path before prediction. Twenty fixed mask seeds (101--120) generated random points, single and separated blocks, single- and paired-station outages, secondary-target gaps, event-conditioned gaps, window sensitivities, block-length extrapolation, and internal leave-one-station-out transfer. The authoritative executable inventory is produced by the current grid builders: 156 core conditions and 3,120 scenarios, and 1,148 formal-full conditions and 9,299 scenarios when the frozen event catalog is included. Older 300-condition / 6,000-scenario wording is retired. The internal leave-one-station-out model used labels only from the two donor stations for fitting and validation; replicated labels of its deterministic test mask were not treated as independent evidence.

The principal sequence length was 368 days, with 184- and 736-day sensitivities. Windows never crossed temporal splits. Deep-model training used a half-window stride and a final right-aligned window. At offline inference, the deep baselines and proposed model used the condition-specific window, a stride of $W/2$, and a final right-aligned window; overlapping predictions were averaged only at artificially hidden cells.

### 2.3 Comparison models and multisource quantile imputer

The common reference was a training-only, circular plus or minus seven-day day-of-year median climatology with a training median fallback. Offline temporal comparators were linear interpolation, shape-preserving cubic interpolation, and a training-fitted local-linear-trend Kalman smoother. Regression comparators comprised air-temperature seasonal ridge, the same model with same-site hydraulics, donor-station regression, random forest, and XGBoost. Discharge analyses additionally included a same-site level-to-flow rating curve and a level-free seasonal ridge. A model whose required source was hidden produced a structured skip rather than silently imputing that source.

Formal neural references are the official PyPOTS 1.5 BRITS, SAITS, and CSDI implementations [@cao2018brits; @du2023saits; @tashiro2021csdi]. Compact local BRITS-lite and SAITS-lite adapters remain development and smoke checks only and are not formal evidence. All three official references used train-only scaling, the frozen missingness curriculum, a half-window stride, and restoration of the best finite validation checkpoint. The common formal budget is Adam with learning rate 0.001, batch size eight, at most 400 epochs, patience 20, and gradient clipping at 1.0. A required seed that hits the epoch cap is labelled `budget_unstable` and cannot enter the roster. The cap is not raised again. Smoke checks used at most three epochs and were excluded from scientific evidence.

The proposed offline model encoded a permanent calendar baseline S0 and four switchable information groups: A, local target history and observation-gap distances; B, same-station $F$ and $L$; C, other-station $T$, $F$, and $L$ pooled by availability-masked attention; and D, same-station $T_a$, $P$, $W$, $RH$, and $R_s$ only. Calendar terms belong to S0 and are not counted again in D. Availability required a naturally observed, finite, unmasked value. A learned gate combined available branches, and source dropout removed information groups during training while retaining at least one branch. The cross-station component did not use an adjacency matrix or message passing and is not described as a graph neural network or GRIN implementation [@cini2022grin].

The output comprised strictly ordered $q_{0.05}$, $q_{0.25}$, $q_{0.50}$, $q_{0.75}$, and $q_{0.95}$ estimates. Training combined median Huber loss with equal-weight pinball loss across all five quantiles on eligible artificially hidden temperature cells [@koenker1978quantiles; @gneiting2007scoringrules]. The proposed model used the same 400-epoch, patience-20 protocol and restored the best finite validation checkpoint. Formal trainable models used five training seeds (11, 22, 33, 44, and 55). Validation-only selection used seed 11, then seeds 11, 22, and 33 for retained deep finalists.

### 2.4 Offline and causal recovery protocols

Offline reconstruction was the primary task and could use observations on both sides of a gap. This information condition admits two-sided interpolation, smoothing, bidirectional recurrence, and forward and backward observation-gap distances. The secondary online protocol prohibited future values, backward interpolation, and smoothing. Its references were training climatology and last-observation persistence, and its forward-only GRU propagated state chronologically from masked values, availability indicators, and elapsed times. Online errors were stratified by time since the last observation. Offline and online results were analysed separately because their information sets differ.

### 2.5 Predeclared science experiments

The `SCI_DENSE` design used single blocks of 15 declared lengths from 1 to 365 days for $T$ and eight declared lengths from 3 to 365 days for each of $F$ and $L$. Across three stations, this yielded 93 conditions and 1,860 mask scenarios, all with a fixed 736-day context. Recoverability skill at gap length $d$ was $1-\mathrm{MAE}_{\mathrm{model}}(d)/\mathrm{MAE}_{\mathrm{climatology}}(d)$ on common artificial cells. Frontier analysis retained only complete mask-seed-by-training-seed curves across all predeclared gaps. A non-increasing envelope defined the first loss of a lower skill confidence bound above zero; a separate mean-skill crossing and two-line minimum-error breakpoint were also estimated. Crossings outside the tested range were censored. Application frontiers were computed only for thresholds specified before analysis and required finite values at every requested gap.

Information compensation used a separate S0 coalition: a training-only, stable-calendar, circular plus or minus seven-day month-day climatology with a training median fallback. S0 and the 15 non-empty subsets of A--D supplied all 16 coalition values on identical hidden cells. Exact Shapley contributions were accepted only for a complete, finite coalition set within the same scenario, mask seed, training seed, station, target, gap, window, protocol, and model unit [@shapley1953value]. The model's learned empty-branch prior was not relabelled as S0.

Descriptive information metrics used finite training observations and exact month-day anomalies on a stable leap-year calendar. Continuous mutual information used a five-neighbour estimator [@shannon1948communication; @kraskov2004mutualinformation]. Transfer entropy discretised each series into four empirical-quantile bins and tested lags 1, 2, 3, and 7 in both directions [@schreiber2000transferentropy]. Null distributions used 199 circular shifts of the source sequence, plus-one permutation $p$-values, and joint Benjamini--Hochberg adjustment. These measures were not interpreted causally.

The `SCI_NET` design crossed three target stations, four target-temperature gap lengths, and the exact eight-element powerset of failures among B1, S2, and P3: 96 conditions and 1,920 mask scenarios. Within a target-gap-mask unit, all failure subsets shared the same target gap, and a failed station lost $T$, $F$, and $L$. Resilience curves required every subset exactly once with finite inputs. Skill was normalised by the matching positive no-failure value and integrated over failure fraction only across the complete zero-to-one domain. Node importance was singleton-failure MAE minus matching no-failure MAE.

### 2.6 Evaluation and statistical inference

Metrics were restricted to cells that were quality eligible, artificially masked, and finite in both truth and prediction. Common outcomes were MAE, RMSE, bias, Pearson and Spearman correlation, training-scale-normalised errors, climatology-relative skill, and gap-boundary jumps. Variable-specific diagnostics covered thermal extremes and changes, flow and level magnitude and timing, water balance, and threshold exceedance. Sequence-dependent diagnostics were reported only for a complete test-period reconstruction. No ecological threshold was predeclared, so ecological-threshold outputs remained unavailable.

Probabilistic evaluation comprised pinball loss at all five quantiles, $q_{0.05}$--$q_{0.95}$ coverage and width, crossing rate, and approximate CRPS from trapezoidal integration over the five levels [@gneiting2007scoringrules]. Calibration was first calculated within a fixed experiment, failure, window, protocol, and information-combination regime. Uncertainty growth required at least three gap lengths in the same regime.

The inferential unit was a mask event, not a day. Training seeds were first averaged within scenario, after which model-minus-climatology differences were assessed by paired event-level bootstrap intervals and Wilcoxon signed-rank tests with Holm adjustment. Frontier intervals used 2,000 cluster-bootstrap resamples of complete cross-gap units. Trend diagnostics compared Mann--Kendall direction and Sen slope only when a complete reconstruction existed [@mann1945trend; @sen1968slope]. Ordinary masked-cell tables were labelled `masked_period_local_shape_only`; they could report named local slopes but not long-term trend preservation.

### 2.7 Reproducibility and evidence gate

The workflow uses deterministic masks and seeds, atomic scenario outputs, checkpoint contracts, and run manifests. A formal design is considered complete only when every expected run has contracted daily and event evidence or an allowed structural skip, all required training seeds, and the fixed mask-seed design. Smoke, truncated, stale, retryable, or partially completed outputs are implementation evidence only. Numerical claims in this manuscript will be populated solely from current outputs whose relevant manifest reports a complete fixed design.

## 3. Results: preregistered reporting structure

No formal numerical result is reported in this draft. Each subsection below fixes the reporting denominator and comparison before result values are inserted.

### 3.1 Evidence-set completeness and data eligibility

The evidence denominator will be established before any model ranking, with formal and structurally skipped runs separated from failed, stale, or incomplete outputs.

<!-- RESULTS_PENDING: R1_FORMAL_COMPLETENESS — Report each relevant manifest's formal_design_complete status, expected and completed scenario/model/training-seed counts, structural skips, exclusion reasons, and eligible target-cell counts. Do not populate downstream claims for an incomplete design. -->

### 3.2 Reconstruction accuracy across missingness regimes

Results will be organised by target, gap geometry, gap length, information pattern, and offline or online protocol. Comparisons will use paired mask events and report effect estimates with uncertainty rather than a rank alone.

<!-- RESULTS_PENDING: R2_OVERALL_ACCURACY — Insert the primary MAE, RMSE, bias, and climatology-relative skill results for M1--M10, including paired intervals, multiplicity-adjusted tests, structured skips, and references to the final table and figure numbers. -->

### 3.3 Dense gap-length recoverability frontiers

Frontiers will be reported only from complete `SCI_DENSE` curves, with statistical, mean-skill, and application definitions kept distinct and censoring shown explicitly.

<!-- RESULTS_PENDING: R3_RECOVERABILITY_FRONTIERS — Insert model-by-target frontier estimates, confidence intervals, breakpoint estimates, left/right censoring, and any unavailable application frontiers; identify the exact complete-unit denominator. -->

### 3.4 Probabilistic calibration and scientific preservation

Point accuracy, interval calibration, extremes, timing, and local-shape diagnostics will be reported separately. Long-term trend fields will appear only for complete reconstructions.

<!-- RESULTS_PENDING: R4_PROBABILISTIC_DIAGNOSTICS — Insert five-quantile pinball loss, approximate CRPS, 90% interval coverage and width, crossing rate, and within-regime uncertainty growth, with final display references. -->

<!-- RESULTS_PENDING: R5_SCIENTIFIC_PRESERVATION — Insert extreme, timing, threshold, water-balance, and boundary diagnostics. Report long-term trend comparisons only where long_term_trend_available is true; otherwise retain the masked_period_local_shape_only label and local-slope interpretation. -->

### 3.5 Information compensation and descriptive information metrics

Coalition results will use only complete 16-value units. Shapley allocation, controlled-removal gains, mutual information, and transfer entropy will remain descriptive and will not be presented as causal effects.

<!-- RESULTS_PENDING: R6_COMPENSATION — Insert S0 and A--D coalition performance, exact Shapley contributions, controlled-removal gains, completeness denominators, uncertainty, and final display references. -->

<!-- RESULTS_PENDING: R7_INFORMATION_METRICS — Insert mutual-information estimates and lag-specific bidirectional transfer entropy with adjusted p-values, then report their prespecified descriptive association with recovery outcomes without causal wording. -->

### 3.6 Monitoring-network resilience

Resilience will be evaluated only for complete `SCI_NET` powersets, with no-failure normalisation distinguished from raw error.

<!-- RESULTS_PENDING: R8_NETWORK_RESILIENCE — Insert failure-fraction curves, resilience AUC, singleton-failure MAE increments, node-importance summaries, completeness denominators, and final display references. -->

### 3.7 Causal online recovery and internal spatial transfer

Online and offline estimates will not be pooled. Internal leave-one-station-out transfer will be labelled exploratory and will not be described as external validation.

<!-- RESULTS_PENDING: R9_ONLINE_AND_LOSO — Insert online error by time-since-last-observation, paired offline/online contrasts under matched masks where available, and held-out-station LOSO estimates with their non-independent mask-copy limitation. -->

## 4. Discussion

### 4.1 Interpretation framework

The eventual interpretation will prioritise the predeclared questions: where recoverability is lost as gaps lengthen, whether gains persist when auxiliary sources fail, whether predictive intervals remain calibrated, and which internal station failures most reduce recovery. Statistical significance alone will not establish operational importance; effect magnitude, uncertainty, baseline performance, and censoring will be considered together.

<!-- RESULTS_PENDING: D1_PRIMARY_INTERPRETATION — Summarise only manifest-complete primary findings, including negative or inconclusive results, and relate each claim to a reported effect estimate rather than to model rank. -->

<!-- RESULTS_PENDING: D2_INFORMATION_TRADEOFFS — Interpret the observed compensation, uncertainty, and resilience patterns without treating Shapley values, attention weights, mutual information, or transfer entropy as causal attribution. -->

### 4.2 Scope of inference

The study contains three stations on one river system over 2006--2020. Their shared geography, regulation history, climate, and observation practices limit transportability. The `SCI_NET` analysis quantifies redundancy within this small case-study network; it does not establish a general river-network resilience law. Similarly, leave-one-station-out evaluation with the other two study stations is an internal spatial-transfer diagnostic, not independent external validation. Generalisation requires testing on stations, periods, climates, and network layouts that did not contribute to this design.

### 4.3 Observation and provenance limitations

Artificial masks provide known truth for evaluation but address recoverability of published, unflagged cells rather than natural gaps, for which truth is absent. The supplied files had no per-value quality codes, hydrological-day convention, or evidence resolving prior provider interpolation. Retaining the B1 level datum shift avoids an undocumented correction but can affect models that use level. The S2 discrepancy with the monthly provenance check remains unresolved. Discharge and level are also closely related, so simultaneous access to both should not be interpreted as two independent physical information sources.

### 4.4 Design and model limitations

Offline reconstruction can use observations after a gap and should not be interpreted as real-time forecasting. The separate online protocol is causal but uses a compact forward GRU and does not exhaust possible operational forecasters. Formal neural references are the official PyPOTS 1.5 BRITS, SAITS, and CSDI cores; local compact BRITS-lite and SAITS-lite adapters are development checks only and are not formal evidence. The proposed cross-station attention has no supplied graph, and attention weights are diagnostics rather than explanations. Group A--D labels are predictive information contracts, not fitted heat-budget terms. A simplified transport picture is used only to motivate the contracts: local memory and gap boundaries (A), hydraulic state (B), other-station heat and flow (C), and atmospheric exchange proxies (D), with unobserved cascade-reservoir operations as a shared driver. Donor-C claims require the predeclared lag and permutation tests and remain predictive attribution. Results may also depend on the fixed temporal split, mask library, context windows, training budgets, and climatology reference. Application frontiers remain undefined unless domain tolerances are specified before analysis. The executable freeze is `design_freeze_v3`.

### 4.5 Statistical and scientific limitations

Repeated mask and training seeds quantify design and optimisation variation but do not create new rivers or independent historical periods. Event-level pairing and cluster bootstrap preserve the intended replicate structure, yet uncertainty remains conditional on this mask library. Multiple comparisons are adjusted within the declared analysis, but exploratory contrasts should remain labelled as such. Transfer entropy is sensitive to discretisation, lag choice, serial dependence, common drivers, missingness, and finite sample size. Approximate CRPS is derived from only five quantiles. Finally, masked-cell local slopes cannot demonstrate preservation of a full-record long-term trend; such claims require a complete reconstruction and must account for trend-test sensitivity to autocorrelation and seasonality.

<!-- RESULTS_PENDING: D3_CONCLUSION — Add a concise conclusion stating what the completed evidence supports, what remains uncertain, and the narrow operational implication for monitoring-gap recovery; do not generalise beyond the three-station case study. -->

## 5. Data and Code Availability

The analysed daily hydrological files were supplied to the project. Their provenance is documented, but the materials available to this study did not establish permission to redistribute those exact files; they should therefore not be described as openly available. A related public Figshare record is available [@wei2026figshare], but it was used only for provenance reconciliation and is not a substitute for the analysed daily files. Meteorological source products remain subject to the access and use terms of NOAA/NCEI and the China Meteorological Administration [@noaa2025gsod; @nmic2012chinadaily].

The project repository contains data-audit and preparation logic, deterministic mask generation, model runners, analysis code, metadata, and manuscript sources. Smoke and partial outputs are not scientific evidence; only archived outputs with complete current manifests may support reported results.

Independence and matching audits of the frozen validation anchors and M7b event catalog are reported in Supporting Information S1. Those tables document overlap and pseudo-replication. They are not model-performance evidence. The SI index, AGU Key Points, and plain-language summary are `paper/si.md`, `paper/key_points.md`, and `paper/plain_language_summary.md`. Extended methods are `paper/methods.md`.

<!-- RESULTS_PENDING: A1_CODE_ARCHIVE — At submission, insert the public repository URL, immutable release tag or commit, software license, and archival DOI after those identifiers exist. -->

<!-- RESULTS_PENDING: A2_RESULT_ARTIFACTS — List only the manifest-complete result tables, figures, compact masks, and derived data that are actually archived, together with access restrictions for any non-redistributable inputs. -->

## 6. Open Research

**Software.** Original code is MIT-licensed (`LICENSE`). `CITATION.cff` cites the software only. No archival software DOI has been minted (`doi` unset). The public GitHub host `https://github.com/shutiao23/stream-recoverability` is a development URL, not an AGU archive.

**Restricted Jinsha working tree.** Daily hydrological columns `T`/`F`/`L` come from the *Annual Hydrological Report of the People's Republic of China, Volume VI*. Redistribution permission was not established (`redistribution_allowed=false`). CMA `RH`/`DH` are member-service with no transfer. `TEMP`/`WDSP`/`PRCP` independently match NOAA GSOD at WMO/CMA stations and remain contested under WMO Resolution 40. Reviewer access is through AGU GEMS Data Files for Peer Review with editor-mediated confidentiality, not “available upon request.” Presence of those columns on public GitHub is a remaining hosting defect, not an open-data release (`DATA_RIGHTS.md`).

**NASA POWER $R_s$.** Internal all-sky shortwave (`ALLSKY_SFC_SW_DWN`, UTC) is requested from the NASA POWER daily point API at hydrological-station coordinates. That product is generally publishable after acquisition and citation. Jinsha sunshine duration $DH$ remains a sensitivity-only channel and is not renamed to $R_s$.

**USGS confirmatory hydrology and NASA POWER meteorology for the Upper–Middle Chattahoochee panel** remain `not_opened` until a hash-verified `finalized_model_roster_v1` authorises the evaluate-once path.

**What this draft does not claim.** No current-protocol MAE, skill, frontier day, or “proposed exceeds baseline” statement is reported. Pre-freeze files under `results/formal/` are invalid for inference (`results/formal/PRE_FREEZE_INVALID.md`).
