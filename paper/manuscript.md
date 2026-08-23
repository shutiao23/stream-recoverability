# A Covariance Budget Predicts Stream-Temperature Recoverability Shape but Not Its Ceiling

## 1. Introduction

Continuous daily stream-temperature records are difficult to maintain, yet gaps can distort estimates of thermal magnitude, timing, extremes, and trend. The problem is not limited to predicting isolated missing points. Monitoring failures often remove continuous blocks, disable several variables at one station, or affect multiple stations at once. The consequences depend on gap duration and on which other observations remain available. Guidance for annual stream-temperature analysis therefore emphasises the structure and duration of missing periods, not only the overall fraction missing [@johnson2021datagap]. Existing stream-temperature reconstruction methods show the value of paired air temperature, discharge, seasonal structure, and neighbouring sensors [@li2017streamairimputation; @bal2023streamtemperature], but their performance in one setting does not establish how long or information-poor a gap can become before useful reconstruction is lost.

Time-series imputation has advanced through bidirectional recurrent models, mask-aware self-attention, probabilistic diffusion, and graph-based spatial models [@cao2018brits; @du2023saits; @tashiro2021csdi; @cini2022grin]. At the same time, benchmark studies have shown why comparisons based only on independent random deletion may poorly represent operational failures [@du2024tsibench; @toye2025realworldbenchmark]. Hydrological applications add a second difficulty: auxiliary inputs such as flow, level, meteorology, or donor-station measurements may be unavailable together with the target [@gauch2025missinginputs]. Treating these sources as permanently observed can overstate practical recoverability.

We use *recoverability* to mean the ability to reconstruct a predeclared missing target under a stated gap geometry and information condition, relative to a training-period climatology and, separately, relative to the validation-selected best simple baseline. The paper is organised around one question:

> Can a monitoring network's recoverability be predicted analytically from its observed covariance structure before any imputation model is trained?

We decompose the available information into a seasonal component, simultaneous donor-station anomaly covariance, and local anomaly memory that decays with distance from a gap boundary. This produces three falsifiable predictions: donor-dominated stations should have nearly flat long-gap skill, memory-dominated stations should decay with gap length, and a proposed analytic ceiling should bound stable learners. Models are tests of those predictions rather than the scientific object.

Related multi-station stream-temperature work has jointly modelled discharge and temperature, compared river-network graph models under unseen conditions, and injected process knowledge into temperature models [@sadler2022multitask; @topp2023shifting; @read2019pgdl]. The remaining gap is not another imputation benchmark. It is a portable rule for estimating recoverability, sensor priority, and useful outage duration from data already observed by a network.

This study is a three-station Upper Jinsha case study for 2006--2020. Conventional interpolation and regression, official PyPOTS 1.5 references, and a missing-aware multisource quantile model are used to probe the same frozen masks. Discharge and level are retained as auxiliary information and secondary checks; their full frontiers, an online causal protocol, mutual information, transfer entropy, and Shapley allocation are supporting or SI analyses and are not additional main-text claims. An evaluate-once Upper-to-Middle Chattahoochee panel tests whether the internal recoverability patterns transfer. Leave-one-station-out analysis within the Jinsha panel is internal and is not external validation.

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

Neural candidates use the official PyPOTS 1.5 BRITS, SAITS, and CSDI implementations [@cao2018brits; @du2023saits; @tashiro2021csdi]. Compact local BRITS-lite and SAITS-lite adapters remain development and smoke checks only. The official candidates used train-only scaling, the frozen missingness curriculum, a half-window stride, and restoration of the best finite validation checkpoint. The common budget is Adam with learning rate 0.001, batch size eight, at most 400 epochs, patience 20, and gradient clipping at 1.0. A required seed that hits the cap is `budget_unstable`; one selecting before epoch 50 is `training_unstable`. Either label excludes the model from the formal roster. CSDI is additionally restricted to a reduced probabilistic diagnostic and does not define the frontier.

The proposed offline model encoded a permanent calendar baseline S0 and four switchable information groups. These groups are predictive-information contracts, not a fitted heat-budget decomposition:

| Group | What the model may use | Hydrological reading |
| --- | --- | --- |
| A | Local target history and distances to the nearest observed target | Local thermal memory, seasonal evolution, and gap-boundary information |
| B | Same-station $F$ and $L$ | Discharge, channel storage, and a thermal-capacity state |
| C | Other-station $T$, $F$, and $L$ | Shared climate or regulation, and possible upstream--downstream transport |
| D | Same-station $T_a$, $P$, $W$, $RH$, and $R_s$ | Atmospheric heat exchange and weather forcing |
| Unobserved | Reservoir releases, depth, shading, groundwater exchange, channel form | Not identified; not claimed as causal residuals |

Calendar terms belong to S0 and are not counted again in D. The models test whether these process-linked information classes have predictive value for recovery; they do not estimate a complete river heat balance. Availability required a naturally observed, finite, unmasked value. A learned gate combined available branches, and source dropout removed information groups during training while retaining at least one branch. The cross-station component did not use an adjacency matrix or message passing and is not described as a graph neural network or GRIN implementation [@cini2022grin]. Strong donor-regression performance is treated as a mechanism question, not as proof of river-network transport, until the predeclared lag, lead, identity-permutation, and seasonal-residual tests are complete.

The output comprised strictly ordered $q_{0.05}$, $q_{0.25}$, $q_{0.50}$, $q_{0.75}$, and $q_{0.95}$ estimates. Training combined median Huber loss with equal-weight pinball loss across all five quantiles on eligible artificially hidden temperature cells [@koenker1978quantiles; @gneiting2007scoringrules]. The proposed model used the same 400-epoch, patience-20 protocol and restored the best finite validation checkpoint. Formal trainable models used five training seeds (11, 22, 33, 44, and 55). Validation-only selection used seed 11, then seeds 11, 22, and 33 for retained deep finalists.

### 2.4 Offline recovery protocol

Offline reconstruction is the primary task and may use observations on both sides of a gap. This information condition admits two-sided interpolation, smoothing, bidirectional recurrence, and forward and backward observation-gap distances. A compact forward-only protocol exists in the repository as a later or SI contrast; it is not part of the main recoverability claims because historical reconstruction and real-time emergency recovery are different scientific objects.

### 2.5 Analytic recoverability budget

For target station $s$, surviving donor set $I$, and block length $d$, exact calendar-day medians fitted on 2006--2015 were subtracted from target and donor temperatures. Simultaneous donor anomalies were regressed on the target anomaly to obtain $R^2_{\mathrm{donor}}(s,I)$. Local memory was the target-anomaly autocorrelation $\rho_s$ at the average distance from a point inside a two-sided block to its nearest boundary, $d/4$; one day was the minimum identifiable lag and fractional lags were linearly interpolated. The frozen budget was

$$R^2_{\mathrm{avail}}(d,s,I)=R^2_{\mathrm{donor}}+(1-R^2_{\mathrm{donor}})\rho_s^2(d/4),$$

$$\widehat{\mathrm{skill}}(d,s,I)=1-\sqrt{1-R^2_{\mathrm{avail}}(d,s,I)}.$$

No model was trained and no 2016--2020 outcome entered this calculation. Station type was declared at 30 days: donor-dominated when the donor component was at least the memory component, otherwise memory-dominated. The complete prediction was written before a dense aggregate existed.

### 2.6 Predeclared science experiments

The main `SCI_DENSE` design used single temperature blocks of 15 declared lengths from 1 to 365 days at the three stations, with a fixed 736-day context and frozen anchors. Recoverability skill at gap length $d$ was $1-\mathrm{MAE}_{\mathrm{model}}(d)/\mathrm{MAE}_{\mathrm{climatology}}(d)$ on common artificial cells. A second, validation-selected simple-baseline relative skill is required by `design_freeze_v4`. Frontier analysis retained only complete mask-seed-by-training-seed curves across all predeclared gaps. A non-increasing envelope defined the first loss of a lower skill confidence bound above zero; a separate mean-skill crossing and two-line minimum-error breakpoint were also estimated. Crossings outside the tested range were censored. No ecological or regulatory error threshold was declared, so reported frontiers are statistical, not safe-to-impute limits. Complete $F$ and $L$ frontiers remain SI or secondary checks.

Donor-C falsification is a primary mechanism experiment, not an add-on. Same-day donor information is compared with past-only, lagged, implausible-lead, station-identity permutation, and seasonal-residual permutation contrasts, and upstream versus downstream donors are labelled before seeing outcomes. Mutual information, transfer entropy, and exact Shapley allocation are used only if they explain a retained donor result; otherwise they remain SI diagnostics and are not interpreted causally [@shapley1953value; @shannon1948communication; @kraskov2004mutualinformation; @schreiber2000transferentropy].

The `SCI_NET` design crossed three target stations, four target-temperature gap lengths, and the exact eight-element powerset of failures among B1, S2, and P3: 96 conditions and 1,920 mask scenarios. Within a target-gap-mask unit, all failure subsets shared the same target gap, and a failed station lost $T$, $F$, and $L$. Resilience curves required every subset exactly once with finite inputs. Skill was normalised by the matching positive no-failure value and integrated over failure fraction only across the complete zero-to-one domain. Node importance was singleton-failure MAE minus matching no-failure MAE.

### 2.7 Evaluation and statistical inference

Metrics were restricted to cells that were quality eligible, artificially masked, and finite in both truth and prediction. Common outcomes were MAE, RMSE, bias, Pearson and Spearman correlation, training-scale-normalised errors, climatology-relative skill, and gap-boundary jumps. Variable-specific diagnostics covered thermal extremes and changes, flow and level magnitude and timing, water balance, and threshold exceedance. Sequence-dependent diagnostics were reported only for a complete test-period reconstruction. No ecological threshold was predeclared, so ecological-threshold outputs remained unavailable.

Probabilistic evaluation comprised pinball loss at all five quantiles, $q_{0.05}$--$q_{0.95}$ coverage and width, crossing rate, and approximate CRPS from trapezoidal integration over the five levels [@gneiting2007scoringrules]. Calibration was first calculated within a fixed experiment, failure, window, protocol, and information-combination regime. Uncertainty growth required at least three gap lengths in the same regime.

The inferential unit was a mask event, not a day. Training seeds were first averaged within scenario, after which paired event-level bootstrap intervals and Wilcoxon signed-rank tests were computed. Multiplicity was controlled by Benjamini--Hochberg adjustment within each declared hypothesis family. Frontier intervals used 2,000 cluster-bootstrap resamples of complete cross-gap units. Trend diagnostics compared Mann--Kendall direction and Sen slope only when a complete reconstruction existed [@mann1945trend; @sen1968slope]. Ordinary masked-cell tables were labelled `masked_period_local_shape_only`; they could report named local slopes but not long-term trend preservation.

Two claim rules were frozen before Stage 3 aggregation and before any formal 2018--2020 frontier is computed. First, a temperature gap remains statistically recoverable relative to a named baseline only while the 95% lower confidence bound on event-level skill is strictly above zero. The reported frontier is the first loss of that bound, with interpolation only between adjacent tested gaps (`monotone_first_loss_lower_confidence_bound`). The dual baselines are climatology and the validation-selected best simple model. Beating climatology alone is not a model-superiority claim. No application, operational, or regulatory MAE threshold is declared.

Second, the proposed model is compared with donor regression on validation events only. The comparison unit is mean skill within each difficult stratum and station: proposed means are further split by training seed, and donor means are pooled across seeds at the same stratum--station cell. Proposed is better only when that mean is strictly larger than the donor mean; ties are not wins. The difficult strata are 90-day and 180-day temperature blocks, 90-day joint T+F+L blocks, and 90-day hydrological station outages. The claim is `supporting_contribution` only if every required seed (11, 22, 33) and station (B1, S2, P3) cell is strictly above donor; `conditional` if at least one difficult cell is strictly above donor; otherwise `no_superiority`. This rule does not create formal 2018--2020 evidence.

### 2.8 Evidence completeness

A formal design is complete only when every expected run has contracted daily and event evidence or an allowed structural skip, all required training seeds, and the fixed mask-seed design. Smoke, truncated, stale, or partial outputs are not scientific evidence. Numerical claims will be populated only from current outputs whose relevant manifest reports a complete fixed design.

## 3. Results

The complete formal bundle contains 134,359 contracted run units, including 116,994 evidence units and 17,365 declared structural skips. It combines the full M1--M10 suite, 900 dense temperature scenarios, 1,920 network-resilience scenarios, 6,720 donor-falsification scenarios, and three independently aggregated sensitivity versions. Confirmatory recovery performance remains unopened.

### 3.1 Validation-only model selection

On the frozen 105-unit validation funnel, donor regression had the highest equal-stratum mean skill (0.240), followed by XGBoost (0.204), random forest (0.199), official BRITS (0.183), and the proposed model (0.127). Air-only regression (0.082) beat climatology (0). Official SAITS (−0.066) and CSDI (−0.157) were negative relative to climatology and are retained as diagnostic results if their official adapters, masks, scaling, and scored cells are correct. Donor regression also led on long gaps (0.225) and 90-day station outages (0.224). The proposed model was weaker overall than donor regression, but its long-gap (0.151) and outage (0.167) means were higher than its overall mean and higher than BRITS on those hard strata. Proposed worst-station mean skill was negative (−0.022). These values are `model_selection_only` and `formal_evidence=false`. They support one working hypothesis, not a paper-winning model claim: on this connected, seasonally coherent, reservoir-influenced reach, simple neighbour information may be the main recovery resource, and a multisource nonlinear model is a candidate only for specific compound or long outages.

Stage 3 exposed a validity boundary. Proposed seed 22 had overall skill -0.667 and selected epoch 33, versus epochs 214 and 173 for seeds 11 and 33. BRITS and CSDI also contained required seeds selecting before epoch 50. The validation objective covered point, short-block, long-block, and station-outage masks and all recorded losses were finite; scaling was train-only and seed-independent. The v5 amendment therefore labels any model with a required `best_epoch < 50` as `training_unstable` and excludes it from the formal roster. This rule was added after validation stability evidence and before a dense aggregate; affected runs cannot support a claim that deep learning is ineffective. CSDI is separately demoted to a seed-11 probabilistic diagnostic at 7, 30, 90, and 180 days.

The proposed model lost to donor regression in 27 of 36 difficult validation cells. Because its seed-22 checkpoint was training-unstable, this withdraws the proposed-performance claim but does not establish that deep models are generally ineffective.

### 3.2 Frozen analytic prediction

The train-only donor anomaly $R^2$ was 0.464 at B1, 0.470 at S2, and 0.106 at P3. At 30 days, predicted skill was 0.309, 0.328, and 0.416; at 90 days it was 0.274, 0.278, and 0.270. B1 and S2 were donor-dominated, so their predicted curves approached flat long-gap floors. P3 was memory-dominated and declined from predicted skill 0.771 at one day to 0.061 at 365 days.

Against the completed best-model envelope, prediction correlations were 0.72 at B1, 0.94 at S2, and 0.95 at P3; mean absolute skill errors were 0.077, 0.085, and 0.122. Thus the decomposition predicted broad curve shape. It did not define an upper bound: the best stable model exceeded the prediction in 20 of 45 station-gap cells, and its 95% lower confidence bound exceeded the prediction in eight P3 cells. The information-ceiling hypothesis is therefore rejected.

### 3.3 Temperature recoverability frontiers

No fixed model dominated all stations and lengths. Random forest and XGBoost retained a positive climatology-relative lower confidence bound through 365 days at B1 and S2; XGBoost did so at P3. Linear, PCHIP, and Kalman frontiers crossed in range at approximately 7--9 days at B1, 21--23 days at S2, and 93--160 days at P3. Donor-regression skill was poor at the shortest gaps and increased later, so the predeclared non-increasing frontier labelled it left-censored even where its long-gap mean became positive. No fixed model had positive mean skill against the validation-selected best-simple family across the complete dense curve.

### 3.4 Donor information and information-source mechanism

Observed same-day donor information exceeded the station-identity permutation by 0.057 skill across 60 paired units ($p=0.000179$). However, the gain also survived permutation and implausible lags under the predeclared decision rule. The resulting interpretation is `falsified_network_propagation`; allowed claim language is `correlated_predictive_source_only`.

### 3.5 Network resilience

Network dependence was directional and target-specific. Across gap lengths, removing S2 increased B1 donor-regression MAE by 2.42 degrees C on average, whereas removing B1 increased S2 MAE by 1.98 degrees C. P3 donor dependence was much smaller and mixed. Sensor-protection priorities therefore follow target-specific dependencies: protect S2 for B1 recovery and B1 for S2 recovery rather than applying one global station ranking.

### 3.6 Data-quality and hydrological-state robustness

Across target-$T$ paired units, mean MAE differences relative to `published_v2` were +0.026 degrees C for `no_s2_suspect_v2`, -0.047 degrees C for `b1_no_level_v2`, and -0.042 degrees C for `b1_shift_sensitivity_v2`; model- and regime-specific ranges were wider. The meteorology -1/0/+1-day alignment suite was not implemented, so no alignment claim is made.

### 3.7 External replication

Chattahoochee feasibility passed all 60 frozen scenarios without training, scoring, or creating a once-lock. A prediction using only 2012--2020 classified site 02334430 as memory-dominated and the other four sites as donor-dominated. Predicted 30-day skill ranged from 0.644 to 0.763. At 365 days, the four donor-dominated sites retained predicted skill from 0.630 to 0.733, whereas 02334430 declined to 0.314. These are external train-only predictions, not measured replication; the 2023--2025 recovery outcomes remain unopened for scoring.

<!-- RESULTS_PENDING: R6_EXTERNAL — After roster freeze and evaluate-once, report whether recoverability patterns and information dependencies replicate, transfer with basin-dependent frontier locations, replicate only for some outage types, or fail. Do not change stations, years, or the model roster after seeing the result. -->

## 4. Discussion

### 4.1 Recoverability as a property of information

The analytic budget is useful because it predicted best-envelope shape with no model fitting, especially the P3 decay and the B1/S2 long-gap plateau. Its failure as a ceiling is equally informative. Two-sided boundary interpolation, nonlinear covariates, and gap-specific model switching contain information not represented by simultaneous donor $R^2$ plus one autocorrelation value. Recoverability is partly a property of observed information structure, but the decomposition needs empirical calibration before network-design use. Donor falsification further restricts the physical reading: other-station observations are a correlated predictive source, not an identified transport mechanism.

### 4.2 Station, season, and regulation differences

A single mean skill hides station and regime differences. P3 supplied the strongest counterexample to the ceiling: eight best-model lower confidence bounds exceeded the prediction. B1 and S2 instead showed the expected long-gap plateau, but their best models were random forest or XGBoost rather than donor regression alone. The S2 provenance exclusion and B1 level sensitivities changed some model-specific errors without reversing the need for station-specific interpretation.

### 4.3 When automatic fill should stop

No ecological or management error threshold was declared before analysis. The paper therefore cannot say that a 90-day gap is safe to fill. It can say, after the frontier exists, that a statistical advantage relative to a named baseline is or is not supported by a confidence interval beyond a stated gap. High-uncertainty reconstructions should be labelled rather than silently written into a published series.

The results support statistical, model-specific boundaries only. Random forest and XGBoost were right-censored at 365 days in several stations, whereas interpolation and Kalman methods crossed much earlier. These are advantages over climatology, not declarations that an imputed value is operationally safe.

### 4.4 Scope, masks, and one-network limits

The study contains three stations on one river system over 2006--2020. Artificial masks give known truth for published, unflagged cells; they estimate recoverability under controlled outages, not the probability of real faults. The `SCI_NET` analysis quantifies redundancy inside this small panel, not a general river-network law. The central conclusion is narrower than the proposed theory: a train-only covariance budget can anticipate recoverability shape and station class, but it is not an information ceiling. Monitoring design can use it as rapid screening, followed by calibration with structured masks. The executable freeze is `design_freeze_v4` with the recorded v5 amendment.

## 5. Data and Code Availability

The analysed daily hydrological files were supplied to the project. Their provenance is documented, but the materials available to this study did not establish permission to redistribute those exact files; they should therefore not be described as openly available. A related public Figshare record is available [@wei2026figshare], but it was used only for provenance reconciliation and is not a substitute for the analysed daily files. CMA humidity and sunshine columns, and WMO/CMA series that independently match NOAA GSOD, remain restricted. Reviewer access to the restricted Jinsha working files is through AGU GEMS Data Files for Peer Review, not “available upon request.” NASA POWER all-sky shortwave used as the internal Group D radiation channel is a generally citable US-government product. USGS confirmatory hydrology is not opened until a finalized model roster exists. The rights matrix is `DATA_RIGHTS.md` and `metadata/data_rights.csv`.

The project repository contains data-audit and preparation logic, deterministic mask generation, model runners, analysis code, metadata, and manuscript sources. Smoke and partial outputs are not scientific evidence; only archived outputs with complete current manifests may support reported results. File hashes, CI, and release gates are implementation aids and are not scientific contributions.

Independence and matching audits of the frozen validation anchors and M7b event catalog are reported in Supporting Information S1. Those tables document overlap and pseudo-replication. They are not model-performance evidence. The SI index, AGU Key Points, and plain-language summary are `paper/si.md`, `paper/key_points.md`, and `paper/plain_language_summary.md`. Extended methods are `paper/methods.md`.

<!-- RESULTS_PENDING: A1_CODE_ARCHIVE — At submission, insert the public repository URL, immutable release tag or commit, software license, and archival DOI after those identifiers exist. -->

<!-- RESULTS_PENDING: A2_RESULT_ARTIFACTS — List only the manifest-complete result tables, figures, compact masks, and derived data that are actually archived, together with access restrictions for any non-redistributable inputs. -->

## 6. Open Research

**Software.** Original code is MIT-licensed (`LICENSE`). `CITATION.cff` cites the software only. No archival software DOI has been minted (`doi` unset). The public GitHub host `https://github.com/shutiao23/stream-recoverability` is a development URL, not an AGU archive.

**Restricted Jinsha working tree.** Daily hydrological columns `T`/`F`/`L` come from the *Annual Hydrological Report of the People's Republic of China, Volume VI*. Redistribution permission was not established (`redistribution_allowed=false`). CMA `RH`/`DH` are member-service with no transfer. `TEMP`/`WDSP`/`PRCP` independently match NOAA GSOD at WMO/CMA stations and remain contested under WMO Resolution 40. Reviewer access is through AGU GEMS Data Files for Peer Review with editor-mediated confidentiality, not “available upon request.” Presence of those columns on public GitHub is a remaining hosting defect, not an open-data release (`DATA_RIGHTS.md`).

**NASA POWER $R_s$.** Internal all-sky shortwave (`ALLSKY_SFC_SW_DWN`, UTC) is requested from the NASA POWER daily point API at hydrological-station coordinates. That product is generally publishable after acquisition and citation. Jinsha sunshine duration $DH$ remains a sensitivity-only channel and is not renamed to $R_s$.

**USGS confirmatory hydrology and NASA POWER meteorology for the Upper–Middle Chattahoochee panel** were acquired after roster finalization for coverage feasibility. No confirmatory recovery metric was computed and no once-lock was created.

**What this draft does not claim.** It does not claim an analytic information ceiling, a generally superior proposed model, an operationally safe fill length, a meteorology-alignment effect, or external replication. Pre-freeze files under `results/formal/` remain invalid for inference (`results/formal/PRE_FREEZE_INVALID.md`).
