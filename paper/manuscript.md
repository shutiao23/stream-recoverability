# Recoverability of Daily Stream Temperature under Structured Monitoring Gaps: A Multisource Upper Jinsha River Case Study

## 1. Introduction

Continuous daily stream-temperature records are difficult to maintain, yet gaps can distort estimates of thermal magnitude, timing, extremes, and trend. The problem is not limited to predicting isolated missing points. Monitoring failures often remove continuous blocks, disable several variables at one station, or affect multiple stations at once. The consequences depend on gap duration and on which other observations remain available. Guidance for annual stream-temperature analysis therefore emphasises the structure and duration of missing periods, not only the overall fraction missing [@johnson2021datagap]. Existing stream-temperature reconstruction methods show the value of paired air temperature, discharge, seasonal structure, and neighbouring sensors [@li2017streamairimputation; @bal2023streamtemperature], but their performance in one setting does not establish how long or information-poor a gap can become before useful reconstruction is lost.

Time-series imputation has advanced through bidirectional recurrent models, mask-aware self-attention, probabilistic diffusion, and graph-based spatial models [@cao2018brits; @du2023saits; @tashiro2021csdi; @cini2022grin]. At the same time, benchmark studies have shown why comparisons based only on independent random deletion may poorly represent operational failures [@du2024tsibench; @toye2025realworldbenchmark]. Hydrological applications add a second difficulty: auxiliary inputs such as flow, level, meteorology, or donor-station measurements may be unavailable together with the target [@gauch2025missinginputs]. Treating these sources as permanently observed can overstate practical recoverability.

We use *recoverability* to mean the ability to reconstruct a predeclared missing target under a stated gap geometry and information condition, relative to a training-period climatology and, separately, relative to the validation-selected best simple baseline. The paper is organised around one question:

> Under realistic continuous, multivariate, and multi-station outages, when can daily stream-temperature records still be recovered, and how do gap length, surviving information, and station-network structure jointly set that boundary?

That question has three operational parts. First, how does recovery skill decay as a temperature gap lengthens from 1 to 365 days? Second, how much compensation is provided by local thermal memory, same-station hydraulics, other-station hydrology, and meteorology? Third, which station failures most reduce network recoverability? Models are instruments for locating those boundaries. Whether any one model ranks first is not the scientific object.

Related multi-station stream-temperature work has jointly modelled discharge and temperature, compared river-network graph models under unseen conditions, and injected process knowledge into temperature models [@sadler2022multitask; @topp2023shifting; @read2019pgdl]. The remaining gap is not that missing values are unstudied. It is that structured gap length, surviving-information failure, and station failure have not been quantified together under one leakage-controlled contract.

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

Formal neural references are the official PyPOTS 1.5 BRITS, SAITS, and CSDI implementations [@cao2018brits; @du2023saits; @tashiro2021csdi]. Compact local BRITS-lite and SAITS-lite adapters remain development and smoke checks only and are not formal evidence. All three official references used train-only scaling, the frozen missingness curriculum, a half-window stride, and restoration of the best finite validation checkpoint. The common formal budget is Adam with learning rate 0.001, batch size eight, at most 400 epochs, patience 20, and gradient clipping at 1.0. A required seed that hits the epoch cap is labelled `budget_unstable` and cannot enter the roster. The cap is not raised again. Smoke checks used at most three epochs and were excluded from scientific evidence.

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

### 2.5 Predeclared science experiments

The main `SCI_DENSE` design used single temperature blocks of 15 declared lengths from 1 to 365 days at the three stations, with a fixed 736-day context and frozen anchors. Recoverability skill at gap length $d$ was $1-\mathrm{MAE}_{\mathrm{model}}(d)/\mathrm{MAE}_{\mathrm{climatology}}(d)$ on common artificial cells. A second, validation-selected simple-baseline relative skill is required by `design_freeze_v4`. Frontier analysis retained only complete mask-seed-by-training-seed curves across all predeclared gaps. A non-increasing envelope defined the first loss of a lower skill confidence bound above zero; a separate mean-skill crossing and two-line minimum-error breakpoint were also estimated. Crossings outside the tested range were censored. No ecological or regulatory error threshold was declared, so reported frontiers are statistical, not safe-to-impute limits. Complete $F$ and $L$ frontiers remain SI or secondary checks.

Donor-C falsification is a primary mechanism experiment, not an add-on. Same-day donor information is compared with past-only, lagged, implausible-lead, station-identity permutation, and seasonal-residual permutation contrasts, and upstream versus downstream donors are labelled before seeing outcomes. Mutual information, transfer entropy, and exact Shapley allocation are used only if they explain a retained donor result; otherwise they remain SI diagnostics and are not interpreted causally [@shapley1953value; @shannon1948communication; @kraskov2004mutualinformation; @schreiber2000transferentropy].

The `SCI_NET` design crossed three target stations, four target-temperature gap lengths, and the exact eight-element powerset of failures among B1, S2, and P3: 96 conditions and 1,920 mask scenarios. Within a target-gap-mask unit, all failure subsets shared the same target gap, and a failed station lost $T$, $F$, and $L$. Resilience curves required every subset exactly once with finite inputs. Skill was normalised by the matching positive no-failure value and integrated over failure fraction only across the complete zero-to-one domain. Node importance was singleton-failure MAE minus matching no-failure MAE.

### 2.6 Evaluation and statistical inference

Metrics were restricted to cells that were quality eligible, artificially masked, and finite in both truth and prediction. Common outcomes were MAE, RMSE, bias, Pearson and Spearman correlation, training-scale-normalised errors, climatology-relative skill, and gap-boundary jumps. Variable-specific diagnostics covered thermal extremes and changes, flow and level magnitude and timing, water balance, and threshold exceedance. Sequence-dependent diagnostics were reported only for a complete test-period reconstruction. No ecological threshold was predeclared, so ecological-threshold outputs remained unavailable.

Probabilistic evaluation comprised pinball loss at all five quantiles, $q_{0.05}$--$q_{0.95}$ coverage and width, crossing rate, and approximate CRPS from trapezoidal integration over the five levels [@gneiting2007scoringrules]. Calibration was first calculated within a fixed experiment, failure, window, protocol, and information-combination regime. Uncertainty growth required at least three gap lengths in the same regime.

The inferential unit was a mask event, not a day. Training seeds were first averaged within scenario, after which paired event-level bootstrap intervals and Wilcoxon signed-rank tests were computed. Multiplicity was controlled by Benjamini--Hochberg adjustment within each declared hypothesis family. Frontier intervals used 2,000 cluster-bootstrap resamples of complete cross-gap units. Trend diagnostics compared Mann--Kendall direction and Sen slope only when a complete reconstruction existed [@mann1945trend; @sen1968slope]. Ordinary masked-cell tables were labelled `masked_period_local_shape_only`; they could report named local slopes but not long-term trend preservation.

Two claim rules were frozen before Stage 3 aggregation and before any formal 2018--2020 frontier is computed. First, a temperature gap remains statistically recoverable relative to a named baseline only while the 95% lower confidence bound on event-level skill is strictly above zero. The reported frontier is the first loss of that bound, with interpolation only between adjacent tested gaps (`monotone_first_loss_lower_confidence_bound`). The dual baselines are climatology and the validation-selected best simple model. Beating climatology alone is not a model-superiority claim. No application, operational, or regulatory MAE threshold is declared.

Second, the proposed model is compared with donor regression on validation events only. The comparison unit is mean skill within each difficult stratum and station: proposed means are further split by training seed, and donor means are pooled across seeds at the same stratum--station cell. Proposed is better only when that mean is strictly larger than the donor mean; ties are not wins. The difficult strata are 90-day and 180-day temperature blocks, 90-day joint T+F+L blocks, and 90-day hydrological station outages. The claim is `supporting_contribution` only if every required seed (11, 22, 33) and station (B1, S2, P3) cell is strictly above donor; `conditional` if at least one difficult cell is strictly above donor; otherwise `no_superiority`. This rule does not create formal 2018--2020 evidence.

### 2.7 Evidence completeness

A formal design is complete only when every expected run has contracted daily and event evidence or an allowed structural skip, all required training seeds, and the fixed mask-seed design. Smoke, truncated, stale, or partial outputs are not scientific evidence. File hashes, CI, and release gates record that completeness; they are not a research contribution. Numerical claims will be populated only from current outputs whose relevant manifest reports a complete fixed design.

## 3. Results

Formal 2018--2020 numbers are not reported in this draft. The only completed numerical evidence is validation-only model selection on 2016--2017. Those ranks decide which models may later enter the roster; they are not development-test or confirmatory results.

### 3.1 Validation-only model selection

On the frozen 105-unit validation funnel, donor regression had the highest equal-stratum mean skill (0.240), followed by XGBoost (0.204), random forest (0.199), official BRITS (0.183), and the proposed model (0.127). Air-only regression (0.082) beat climatology (0). Official SAITS (−0.066) and CSDI (−0.157) were negative relative to climatology and are retained as diagnostic results if their official adapters, masks, scaling, and scored cells are correct. Donor regression also led on long gaps (0.225) and 90-day station outages (0.224). The proposed model was weaker overall than donor regression, but its long-gap (0.151) and outage (0.167) means were higher than its overall mean and higher than BRITS on those hard strata. Proposed worst-station mean skill was negative (−0.022). These values are `model_selection_only` and `formal_evidence=false`. They support one working hypothesis, not a paper-winning model claim: on this connected, seasonally coherent, reservoir-influenced reach, simple neighbour information may be the main recovery resource, and a multisource nonlinear model is a candidate only for specific compound or long outages.

Stage 3 (seeds 11, 22, 33) and the proposed-versus-donor decision are not complete. A required seed that hits the 400-epoch cap is `budget_unstable` and cannot enter the roster. SAITS was not selected for Stage 3. CSDI remains a predeclared diagnostic finalist; negative Stage 2 skill does not remove it, and it will be excluded later only for budget instability or after the stability table is written.

<!-- RESULTS_PENDING: R1_STAGE3_STABILITY — Insert the Stage 3 model-by-seed table: overall skill, long-gap skill, outage skill, worst station, coverage, and hit-cap status. State the proposed-versus-donor claim as supporting, conditional, or withdrawn. -->

### 3.2 Temperature recoverability frontiers

<!-- RESULTS_PENDING: R2_T_FRONTIERS — From complete SCI_DENSE T curves only, report skill against climatology and against the validation-selected simple baseline by station and gap. State the first day the climatology-relative lower confidence bound is not above zero, whether any complex model still beats donor regression, whether station frontiers agree, and whether the curve is left-censored, right-censored, or crossed in range. Main display: Figure 2 and Table 2. -->

### 3.3 Donor information and information-source mechanism

<!-- RESULTS_PENDING: R3_DONOR_FALSIFICATION — Report same-day, past-only, lagged, implausible-lead, identity-permutation, and seasonal-residual contrasts by target--donor pair, with 95% CI and upstream/downstream labels. Use the predeclared language: network-specific predictive information, mixed predictive attribution, or correlated seasonal/regional source. Do not upgrade a surviving correlation into a transport mechanism. -->

### 3.4 Network resilience

<!-- RESULTS_PENDING: R4_NETWORK_RESILIENCE — From complete SCI_NET powersets, report which station failure costs most, whether single- and dual-station losses are approximately additive, whether upstream and downstream information differ, and whether station importance changes from 10-day to 180-day gaps. Main display: Figure 4 and Table 3. The management sentence is which stations and information channels to keep, not that a powerset benchmark was run. -->

### 3.5 Data-quality and hydrological-state robustness

<!-- RESULTS_PENDING: R5_ROBUSTNESS — Report whether ranking, frontier location, or donor value changes after excluding the S2 suspect period, excluding B1 level, shifting B1 level, shifting meteorology by -1/0/+1 day, and stratifying by season, flow state, and extreme heat or flood. State which conclusions depend on a data version. -->

### 3.6 External replication

2018--2020 is a formal development-period evaluation, not an independent test. The Upper-to-Middle Chattahoochee panel is the external object.

<!-- RESULTS_PENDING: R6_EXTERNAL — After roster freeze and evaluate-once, report whether recoverability patterns and information dependencies replicate, transfer with basin-dependent frontier locations, replicate only for some outage types, or fail. Do not change stations, years, or the model roster after seeing the result. -->

## 4. Discussion

### 4.1 Why neighbour information can dominate

The validation ranking makes donor regression the result that has to be explained. Shared seasonality, shared meteorological forcing, basin-scale reservoir operations, true upstream--downstream transport, similar preprocessing, and stable statistical correlation can all produce that pattern. The falsification suite is therefore the mechanism section, not a supplement. Until those contrasts exist, the correct sentence is that other-station observations are a major predictive source on this panel, not that a river-network heat-transport mechanism has been identified.

<!-- RESULTS_PENDING: D1_DONOR_MECHANISM — Interpret the completed donor contrasts without causal overreach. -->

### 4.2 Station, season, and regulation differences

A single mean skill hides station and regime differences. Formal results must say which station pulls the proposed worst-station skill negative, and whether that is associated with the more distant P3 meteorological pairing, the S2 2013--2019 provenance issue, the B1 2019 level datum change, or a change in cascade-reservoir operations. Those are hydrological explanations, not model-tuning notes.

<!-- RESULTS_PENDING: D2_HETEROGENEITY — Relate station and season differences to known data and regulation limitations. -->

### 4.3 When automatic fill should stop

No ecological or management error threshold was declared before analysis. The paper therefore cannot say that a 90-day gap is safe to fill. It can say, after the frontier exists, that a statistical advantage relative to a named baseline is or is not supported by a confidence interval beyond a stated gap. High-uncertainty reconstructions should be labelled rather than silently written into a published series.

<!-- RESULTS_PENDING: D3_OPERATIONAL_STOP — State the statistical stop rule actually supported by the frontier CIs. -->

### 4.4 Scope, masks, and one-network limits

The study contains three stations on one river system over 2006--2020. Artificial masks give known truth for published, unflagged cells; they estimate recoverability under controlled outages, not the probability of real faults. The `SCI_NET` analysis quantifies redundancy inside this small panel. It is not a general river-network resilience law. External non-replication would itself be a result: single-network reconstruction studies can overstate transferability. The executable freeze is `design_freeze_v4`.

<!-- RESULTS_PENDING: D4_CONCLUSION — State what the completed evidence supports, what remains uncertain, and the narrow implication for which information and stations to keep. -->

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

**USGS confirmatory hydrology and NASA POWER meteorology for the Upper–Middle Chattahoochee panel** remain `not_opened` until a hash-verified `finalized_model_roster_v1` authorises the evaluate-once path.

**What this draft does not claim.** No current-protocol MAE, skill, frontier day, or “proposed exceeds baseline” statement is reported. Pre-freeze files under `results/formal/` are invalid for inference (`results/formal/PRE_FREEZE_INVALID.md`).
