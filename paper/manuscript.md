# Reservoir Regulation Reshapes Recoverable Information in Daily Stream-Temperature Records: Evidence From the Upper Jinsha and Chattahoochee Rivers

## Abstract

Reservoirs alter downstream thermal seasonality and memory, but those changes are rarely connected to information for reconstructing monitoring outages. We use controlled gaps to probe that structure, not rank models. A covariance budget fitted to 2006--2015 daily observations at three Upper Jinsha stations separates donor anomalies from local thermal memory before model training. Batang (B1) and Shigu (S2) are donor-dominated, whereas Panzhihua (P3) is memory-dominated. P3 annual endpoints shift in 2015; formal daily break dates are method-sensitive. The frozen budget predicts best-model curve shape (correlations 0.72--0.95), but ceiling violations occur only at nonstationary P3. State-matched post-hoc scoring reduces lower-bound exceedances from nine to one. In evaluate-once Chattahoochee confirmation, the gauge below Buford Dam is independently memory-dominated and its best skill falls from 0.536 at 30 days to 0.141 at 180 days; downstream donor sites retain stronger long-gap skill. Their 180-day differences are 3.33--5.39 matched validation-period placement SDs. In a separately frozen 335-station US panel, the index alone does not classify upstream major-dam presence across ecoregions (AUC 0.407, 95% interval 0.222--0.515), but within regulated watersheds its median declines from 0.0110 within 5 km to 0.0046 at 50--100 km. Regulation therefore leaves a local covariance fingerprint whose interpretation requires geographic context and calibration.

## 1. Introduction

A monitoring network contains information even when none of its sensors has yet failed. The amount and arrangement of that information determine whether a future outage can be reconstructed from seasonality, neighbouring stations, atmospheric forcing, hydraulics, or observations at the edges of the gap. We call this property *recoverability*: performance on a predeclared missing target under a stated outage geometry and information condition, relative to a named baseline. Controlled masking supplies known truth and can therefore be used to measure the recoverable information carried by a network.

This framing differs from claiming that artificial gaps reproduce the frequency distribution of real sensor faults. Continuous gaps matter for annual thermal statistics [@johnson2021datagap], and existing reconstructions use air temperature, discharge, seasonal structure, and neighbouring sensors [@li2017streamairimputation; @bal2023streamtemperature]. Yet a good imputation model does not by itself explain why one river reach depends on neighbouring stations while another depends on its own past.

Reservoir operation provides a physical reason for that distinction. Storage and depth-selective releases can suppress seasonal and atmospheric temperature signals, elevate or depress seasonal extrema, and extend the persistence of a released water mass. We therefore ask whether regulation reorganizes the covariance structure available for recovery. Our central hypothesis is:

> Regulation-dominated reaches have compressed thermal seasonality and extended anomaly memory, shifting recoverability from simultaneous donor dependence toward local-memory dependence; this shift can be detected from observations without giving the covariance calculation a dam map.

We first froze a train-only analytic budget at three Upper Jinsha stations, then tested it with structured 2018--2020 outages and nine stable traditional methods. After observing the 2015 Panzhihua endpoint shift, we added explicitly post-hoc change-point, stationarity, and low-frequency controls without altering the frozen prediction. Finally, we opened a previously locked five-site Upper-to-Middle Chattahoochee panel exactly once. That panel begins immediately below Buford Dam and follows the downstream thermal re-equilibration reach. The study is thus a mechanism test across two river networks, not a claim that one imputation method is generally best.

## 2. Methods

### 2.1 Study networks and regulation setting

The Upper Jinsha stations, ordered downstream, were Batang (B1), Shigu (S2), and Panzhihua (P3). Daily temperature ($T$), discharge ($F$), and level ($L$) covered 1 January 2006 through 31 December 2020. Station-matched meteorology comprised air temperature, precipitation, wind, relative humidity, and NASA POWER all-sky shortwave radiation. The hydrological records are attributed to the *Annual Hydrological Report of the People's Republic of China, Volume VI* [@wei2026flowcomposition; @wang2024yangtzetemperature].

Guanyinyan is the last project in the planned middle-Jinsha cascade, has weekly regulation, and lies 27 km upstream of Panzhihua according to the national impoundment-stage environmental approval [@mee2014guanyinyan]. Its first unit began generation on 20 December 2014, three more units followed in 2015, and all five were operating in 2016 [@cdt2026guanyinyan; @nea2016powerreport]. We use those dates only to interpret an independently observed thermal transition; this observational design does not isolate the dam from every concurrent basin change.

The external panel comprised USGS sites 02334430, 02335000, 02335450, 02336000, and 02337170 on one Upper-to-Middle Chattahoochee mainstem network. Site 02334430 is 366 m below Buford Dam [@usgs1973buford]. Buford hydropower releases originate near the reservoir bottom and are cold relative to surface water during stratification [@usace2017buford]. External fitting, validation, and confirmatory periods were 2012--2020, 2021--2022, and 2023--2025.

### 2.2 Records, temporal separation, and controlled outages

Jinsha fitting, model-selection, and development-evaluation periods were 2006--2015, 2016--2017, and 2018--2020. The stored `test` label is a legacy alias of `development_test`; it is not an unseen confirmatory split. All scalers, climatologies, feature medians, and fitted models used the fitting period only.

The Jinsha $T$, $F$, and $L$ series contain no natural missing day in the 5,479-day study axis. Accordingly, we do not claim that the imposed outage-duration distribution estimates real failure frequency. Artificial masks are controlled interventions used to measure network information. They hide only finite eligible values, are removed from every model input path, and span point gaps, contiguous blocks, compound $T+F+L$ outages, and matched network failures. The primary dense design has 15 block lengths from 1 to 365 days, three stations, and 20 frozen anchors (900 scenarios). The network design crosses four target-gap lengths with all eight failure subsets of B1, S2, and P3 (1,920 scenarios). These geometries are stress tests motivated by operationally distinct point, block, channel, and station losses, not a fitted fault model.

### 2.3 Hydrothermal state and regulation fingerprint

We summarized annual minimum, maximum, mean, and amplitude directly in degrees C. Temperature anomalies subtract a fitting-period circular day-of-year median with a plus or minus seven-day window. For pre- and post-impoundment periods we report anomaly mean, standard deviation, lag-30 and lag-90 autocorrelation, skewness, and excess kurtosis.

We also estimated one post-hoc change in the complete 3,652-day P3 fitting-period anomaly series, requiring at least 365 days on each side. Pettitt's rank statistic was the primary estimator. Because lag-1 autocorrelation was 0.973, its iid asymptotic and day-permutation p values are reference calculations only; inference uses 9,999 permutations of intact calendar-year blocks. A segmentwise circular moving-block residual bootstrap with 5,000 draws and 365-day blocks supplies a date interval. Single least-squares binary segmentation under the same permutation and bootstrap settings is a method sensitivity. Annual minimum and amplitude Pettitt tests are reported separately, recognizing that the fitting period contains only one fully post-commissioning year.

For comparison across all eight stations, the data-derived memory--range index is

$$I_s=\frac{\operatorname{acf}_{30}(T'_s)}{\max(T_s)-\min(T_s)},$$

where the range and anomaly autocorrelation are computed only in the network's fitting period. This is a descriptive regulation fingerprint, not a universal classifier. We compare its within-network rank with the independently frozen donor/memory type and with distance or position relative to the regulating dam.

### 2.4 Frozen covariance budget

Exact calendar-day medians fitted within the declared calibration period were subtracted from target and donor temperatures. Simultaneous donor anomalies give $R^2_{\rm donor}$. Target anomaly memory at the mean distance from a uniformly distributed point inside a two-sided block to its nearest boundary is evaluated at $d/4$. The frozen budget is

$$R^2_{\rm avail}(d)=R^2_{\rm donor}+(1-R^2_{\rm donor})\rho^2(d/4),$$

$$\widehat{\operatorname{skill}}(d)=1-\sqrt{1-R^2_{\rm avail}(d)}.$$

The $d/4$ distance follows directly from averaging the nearest-boundary distance over a continuous block. The second expression maps unexplained variance to MAE under a common location--scale residual shape; it is not a Gaussian theorem or a physical heat-budget identity. We therefore report anomaly skewness and excess kurtosis and treat the conversion as an approximation. At 30 days, a station is donor-dominated when the donor component is at least the memory component, and memory-dominated otherwise. The original 2006--2015 prediction was written before dense aggregation and was never altered.

To test omitted-variable sensitivity, we expanded the linear anomaly regression with same-site air temperature, $F$, and $L$, and donor-site air temperature and $F$. To test state dependence, we recalculated the budget for 2016--2017 (a leakage-free but short bridge) and for 2016--2020 (a post-hoc state-matched diagnostic that overlaps evaluation and is not predictive evidence).

### 2.5 Recovery models and evidence roster

The common baseline was a training-only circular plus or minus seven-day median climatology. The formal roster contained linear and PCHIP interpolation, a local-linear-trend Kalman smoother, air-only and air-plus-hydraulics ridge regressions, donor regression, random forest, and XGBoost. Offline recovery may use both boundaries of a historical gap.

Official BRITS, SAITS, and CSDI implementations and a multisource quantile model were evaluated during validation. Under the frozen stability rule, required seeds selecting before epoch 50 or hitting the 400-epoch cap could not enter the formal roster. None of the deep candidates entered; their architecture, training diagnostics, validation-only rankings, and information-group ablations are reported only in Supporting Information. No conclusion about the capability of deep imputation follows from excluded unstable runs.

### 2.6 Skill, absolute error, stationarity controls, and inference

For event $e$, skill relative to a named baseline is

$$\operatorname{skill}_e=1-\frac{\operatorname{MAE}_{e,\rm model}}{\operatorname{MAE}_{e,\rm baseline}}.$$

Every main curve and table also reports model MAE and baseline MAE in degrees C. The climatology denominator was withheld at or below 0.05 degrees C. The statistical frontier is the first gap at which the non-increasing 95% lower confidence curve ceases to exceed zero. It is not an ecological or operational safety threshold.

The two frontier denominators--climatology and the validation-selected best simple baseline--now pass through one anchor/year, overlap-aware bootstrap implementation. A previous independent code path resampled scenario identifiers and produced contradictory censoring. That path is no longer used for manuscript evidence; all 27 climatology frontier cells are asserted identical between the summary and dual-denominator tables.

Training seeds were averaged before inference. Frontier curves use 2,000 joint cross-gap resamples stratified by station and anchor year, with connected overlap components retained as blocks. For the model-versus-climatology family, one cross-gap mean per anchor/year is tested by the frozen two-sided Wilcoxon rule. Climatology self-comparisons are labelled `reference_not_tested`; they do not receive artificial $p=1$ values. Benjamini--Hochberg correction is applied across the 24 actual hypotheses.

Two post-hoc robustness scores address the P3 transition. First, fixed model predictions are re-scored against a 2016--2020 state-matched climatology while the budget is recalibrated to the same state. Because this climatology includes evaluation years, the result diagnoses denominator contamination and is not a new test. Second, truth and prediction anomalies are separately demeaned within calendar year before MAE is computed; this removes constant and slower annual offsets while retaining within-year shape.

### 2.7 Donor falsification and best-available node importance

Donor information was tested against lagged, implausible-lead, station-identity-permuted, and seasonal-residual-permuted contrasts. Persistence of gain under physically implausible contrasts falsifies a downstream-transport interpretation and restricts the claim to shared predictive information.

Node importance was redefined at the matched target-gap unit as

$$\Delta_j=\min_m \operatorname{MAE}(m\mid j\ \text{failed})-\min_m \operatorname{MAE}(m\mid\text{full network}),$$

where climatology is included in both minima as a hard upper error cap. Thus the estimand asks how much the best achievable reconstruction deteriorates after a station fails. Negative values are retained as finite-sample evidence that a donor or model choice can be harmful; they are not interpreted as information created by failure.

### 2.8 Evaluate-once external confirmation

Before opening 2023--2025 performance, the external sites, periods, variables, nine-model roster, mask seed, 60 scenarios, and complete train-only predicted curves were fixed. The covariance budget classified 02334430 as memory-dominated and the other four sites as donor-dominated. The confirmatory question was qualitative: whether 02334430 showed the strongest decline and weakest long-gap recovery while the donor-dominated sites retained stronger long-gap recovery. No post-outcome numeric threshold is presented as preregistered. The run created a once-lock before model scoring and completed all 540 model--scenario units. No model or site was selected from confirmatory outcomes.

Because confirmation used one mask placement per cell, a separate post-freeze placement diagnostic was run only on the 2021--2022 external validation period. The same five sites, 30/90/180-day full-information blocks, nine-model roster, and 20 seeds (101--120) produced 2,700 station--gap--model--seed cells. The input was physically truncated at 31 December 2022; confirmatory outcomes and the once-lock were neither read nor modified. We report sample SD (ddof 1) for each fixed-model cell and, descriptively, for the best-roster envelope within each seed. Donor-minus-02334430 envelope differences are paired by seed. These validation SDs are a placement-noise scale, not confirmatory confidence intervals and not a second model-selection exercise.

### 2.9 Independently frozen national regulation panel

After the two case-study analyses, but before reading any national temperature-panel outcome, we froze an independent USGS/GAGES-II test (`regulation_panel_freeze_v1`; SHA-256 `260bd313...`). Its runtime path guard and static source audit prohibit the Chattahoochee data, results, and once-lock. USGS primary daily-mean water-temperature metadata and approved values for 2000--2019 were joined by exact station number to routed GAGES-II watershed attributes [@usgs2026waterapi; @falcone2011gagesii]. Eligible stream sites required one unspliced primary series and at least 10 calendar years with at least 300 approved days. The binary label was at least one upstream GAGES-II major dam in the 2009 snapshot; Euclidean nearest NID points were explicitly prohibited as upstream labels [@usace2026nid].

The primary predictor was the pre-existing memory--range index. The frozen primary analysis was unadjusted logistic regression with HC1 uncertainty plus leave-one-aggregated-ecoregion-out ROC AUC and 2,000 ecoregion-cluster bootstrap draws. A drainage-area/ecoregion-adjusted coefficient and a regulated-site profile in 0--5, 5--20, 20--50, 50--100, and greater than 100 km nearest-major-dam bins were sensitivities; no threshold was selected.

The modern USGS daily API returned HTTP 429 after 26 of 56 atomic batches and no API key was available. Before any panel metric, a transport amendment froze the official legacy `/dv` service as a fallback only for stations having exactly one frozen primary series; 22 multiple-series stations were excluded rather than spliced. Across 1,662,961 station-dates available from both transports, approved values agreed exactly. Results are labelled `transport_limited_maximum_legal_panel`; they do not claim a complete modern-API roster.

## 3. Results

### 3.1 A regulation-consistent thermal transition at P3

P3 annual endpoints shifted in 2015 (Figure 1; Table 2). In 2006--2014, its annual minimum was 8.7--10.3 degrees C and annual amplitude was 11.7--14.1 degrees C. In 2015--2020, minima were 11.5--12.5 degrees C and amplitudes were 9.6--10.7 degrees C. Relative to the 2006--2015 climatology, anomaly SD increased from 0.91 degrees C before impoundment to 1.96 degrees C afterward, and acf30 increased from 0.39 to 0.76. B1 and S2 showed no comparable endpoint shift: their pre/post anomaly SD values were 0.94/0.91 and 0.78/0.81 degrees C, and acf30 remained near 0.14/0.07 and 0.14/0.11.

The formal daily change date was method-sensitive. Pettitt estimated 26 May 2013 (95% 365-day moving-block residual-bootstrap interval, 14 May 2011 to 22 October 2013). The dependence-aware calendar-year permutation p value was 0.0088, but the interval did not contain 20 December 2014. Least-squares single segmentation instead estimated 18 October 2014 (interval, 16 April 2014 to 1 January 2015; year-block $p=0.0117$), and that interval did contain first-unit operation. In 2015, annual minimum was 2.8 degrees C above and amplitude 2.4 degrees C below their 2006--2014 medians, but annual Pettitt tests were not significant ($p=0.2208$ and $0.8607$) with only one post-commissioning fitting year. We therefore infer a statistically detectable but method-sensitive state change and temporal consistency in one sensitivity, not precise localization of commissioning or causal attribution by change-point analysis alone.

The covariance calculation classified B1 and S2 as donor-dominated and P3 as memory-dominated without dam information. P3 ranked first within the Jinsha network on the memory--range index. The same diagnostic independently selected Chattahoochee site 02334430, immediately below Buford Dam. Across the Chattahoochee fitting panel, observed temperature range increased downstream from 9.9 to 14.8, 18.0, 23.7, and 24.0 degrees C, whereas acf30 declined from 0.762 to 0.397, 0.377, 0.304, and 0.281. This is the expected signature of a regulated release re-equilibrating with the atmosphere downstream.

### 3.2 The budget predicts shape, but the ceiling claim is conditional on stationarity

The frozen donor $R^2$ was 0.464 at B1, 0.470 at S2, and 0.106 at P3. Best-envelope correlations with the predicted curve were 0.72, 0.94, and 0.95; mean absolute skill errors were 0.077, 0.085, and 0.122 (Figure 2). The best model exceeded the point prediction in 20 of 45 cells. Nine lower confidence bounds exceeded it, all at P3; none did so at the more stable B1 or S2. The data therefore do not falsify a stationary ceiling at B1/S2, and the original universal-ceiling statement is replaced by a conditional failure under distribution shift.

The expanded covariate regression raised $R^2$ only from 0.464 to 0.537 at B1, 0.470 to 0.532 at S2, and 0.106 to 0.148 at P3. The corresponding P3 long-gap skill approximation rose only from 0.055 to 0.077, excluding omission of measured air temperature and hydraulics as a sufficient explanation.

State control strongly changed the P3 conclusion. Re-scoring against a 2016--2020 climatology reduced lower-bound exceedances from nine to one; at 365 days, XGBoost changed from skill 0.209 against the old climatology to -0.588 against the state-matched climatology, while the recalibrated budget was 0.069. Annual demeaning was less decisive: P3 XGBoost retained skill 0.164 (95% interval 0.130--0.197) at 365 days. Thus the sustained offset explains much of the apparent long-gap advantage, but within-year structure also remains recoverable. The budget is a useful shape diagnostic, not a proven information-theoretic bound.

### 3.3 Relative skill represents tenths of a degree

Training climatology explained 97.0% of B1 temperature variance, 97.2% at S2, and 91.6% at P3. Across the dense design, climatology MAE ranged from 0.681 to 0.771 degrees C at B1, 0.648 to 0.704 degrees C at S2, and 1.218 to 1.347 degrees C at P3 (Figure 3; Table 4). A skill of 0.25 therefore usually represents an improvement of roughly 0.17--0.34 degrees C, not a multi-degree change.

Using the single corrected frontier path, random forest and XGBoost were right-censored at 365 days at B1 and S2, and XGBoost was right-censored at P3. Interpolation/Kalman frontiers occurred at 7.0--8.8 days at B1, 21.2--22.7 days at S2, and 93.1--160.0 days at P3. No fixed model was robustly superior to the validation-selected best-simple denominator across the full dense curve. Of 24 actual model-versus-climatology hypotheses, 14 passed BH correction. Seven had positive mean skill: random forest and XGBoost at B1; donor regression, random forest, and XGBoost at S2; and Kalman and XGBoost at P3. Seven additional rejections identified methods significantly worse than climatology. These directional results replace the former family of 27 artificial $p=1$ values.

### 3.4 Donor value reflects shared forcing; sensor costs are modest

Observed same-day donor information exceeded the station-identity permutation by 0.057 skill across 60 paired units ($p=0.000179$). However, gain persisted under identity permutation and implausible lags, triggering the preregistered `falsified_network_propagation` decision. Neighbouring stations therefore carry shared climatic or regulation information, but the experiment does not identify downstream heat transport.

The corrected node estimator changed both magnitude and interpretation (Figure 4; Table 5). Averaged over gap lengths, loss of S2 increased the best-achievable B1 MAE by 0.132 degrees C; loss of B1 increased S2 MAE by 0.070 degrees C. P3 loss cost B1 0.022 degrees C and S2 0.002 degrees C. For P3 recovery, loss of S2 cost 0.016 degrees C, while mean impacts of losing B1 or P3 itself were slightly negative (-0.001 and -0.004 degrees C). These are information values under model reselection, not failures of one implementation. The previous 2.42-degree C claim is withdrawn.

### 3.5 External confirmation transfers type, not absolute magnitude

The frozen qualitative type ordering was observed at 90 and 180 days (Figure 5). At 30 days, site 02334430 below Buford Dam ranked third when taking the best of the two frozen information conditions and second in the matched full-information curve; the type separation was not present. Its Kalman skill then declined from 0.536 at 30 days to 0.156 at 90 days and 0.141 at 180 days, consistent with the predicted memory-dominated decay. At 90 and 180 days it had the weakest recovery in the panel. In the matched full-information comparison, the four donor-dominated sites retained 180-day skill of 0.726, 0.555, 0.746, and 0.729. XGBoost or random forest was best at those long gaps.

The 20-seed validation diagnostic showed substantial placement variation. Across fixed non-climatology models, the median 180-day skill SD was 0.178; the best-roster envelope SD was 0.114 at 02334430 and 0.182, 0.122, 0.058, and 0.038 at the donor sites. More directly, paired donor-minus-02334430 envelope SDs were 0.128, 0.124, 0.117, and 0.109. The observed full-information 180-day donor advantages were 0.586, 0.414, 0.606, and 0.588, or 4.56, 3.33, 5.19, and 5.39 times those validation placement scales. Thus the long-gap separation is larger than placement variability measured on the same panel, but it remains one confirmatory placement rather than a confirmatory interval estimate.

The analytic magnitudes did not transfer exactly. It overpredicted best skill at 02334430 by 0.108--0.359 and at several downstream cells, while underpredicting some high-skill downstream cells. The external result therefore confirms the regulation-linked donor/memory shape distinction and its monitoring implication, not universal frontier locations.

### 3.6 National panel supports a distance gradient, not a standalone classifier

The frozen national flow discovered 5,707 temperature series, found 1,361 exact GAGES-II station overlaps and 1,344 stream sites, and retained 335 eligible stations (209 with and 126 without an upstream major dam). The primary unadjusted association was positive but uncertain: odds ratio 1.23 per index SD (95% CI 0.93--1.61; $p=0.144$). More importantly, pooled leave-one-ecoregion-out AUC was 0.407 (ecoregion-cluster bootstrap interval 0.222--0.515; Figure 6). The index alone therefore did not generalize as a national major-dam classifier.

The frozen sensitivities retained a localized signal. After drainage-area and ecoregion adjustment, the index odds ratio was 2.52 (1.18--5.36; $p=0.0167$), although a single-class Alaska ecoregion produced a fixed-effect separation warning. Among regulated watersheds, median memory--range index declined from 0.0110 for 83 stations within 5 km of a major dam to 0.00690 at 5--20 km, 0.00611 at 20--50 km, and 0.00463 at 50--100 km; median acf30 declined from 0.262 to 0.135. The greater-than-100-km bin had one station and was not interpreted. Thus case-study direction and the regulated-site distance profile agree, while cross-ecoregion binary discrimination does not.

## 4. Discussion

### 4.1 Reservoir regulation reorganizes recoverable information

The two networks tell the same mechanistic story. At P3 and immediately below Buford Dam, regulation suppresses or restructures the seasonal signal and extends thermal persistence. A gap can therefore be bridged more by the target's boundary memory than by simultaneous neighbouring anomalies. Downstream of Buford, temperature range recovers and acf30 declines while donor-dominated long-gap skill remains high. The covariance budget detects that reorganization without knowing where either dam is located.

The donor falsification result sharpens this interpretation. Donor value that survives impossible lags or station relabelling is evidence of common forcing, not advected heat. In a regulated network that shared source may include release schedules and basin-scale weather as well as ordinary seasonality. Recoverability is therefore a useful observational probe of river information structure, but it does not alone identify causal pathways.

The national panel bounds the generality of this mechanism. The monotone 0--100-km profile is consistent with downstream thermal re-equilibration, but the poor out-of-ecoregion AUC shows that the same index cannot be read as a geography-free dam detector. Climate, channel scale, release depth, dam operation, and network placement can produce overlapping covariance signatures. The adjusted association is supporting evidence, not a rescue of the failed primary classifier.

### 4.2 What remains of the analytic ceiling

The original ceiling language was too strong. All lower-bound violations occurred where calibration and evaluation crossed a thermal regime transition. Once the denominator and budget were matched to the later state, almost all violations disappeared. Yet annual demeaning left positive long-gap skill beyond the original prediction. These diagnostics support a conditional statement: the covariance budget forecasts qualitative curve shape and station type under a stated state, but its MAE conversion and additive information form require empirical calibration. We do not claim that a stationary information ceiling has been proved or disproved from three internal stations.

### 4.3 Monitoring-network consequences

Sensor protection should be based on the best achievable network response to failure. Under that estimand, S2 is the most valuable surviving node for B1, and B1 is the most valuable for S2, but the costs are approximately 0.13 and 0.07 degrees C rather than several degrees. P3 and Buford-type regulated reaches merit a different strategy: preserving observations at both sides of a gap and detecting thermal state changes may matter more than adding another distant donor.

The absolute scale is important. A climatology-only fill already has roughly 0.65--1.35 degrees C MAE in this case study, and the common gains are tenths of a degree. Statistical advantage is not equivalent to ecological or regulatory safety. No threshold was declared for habitat, management, or trend use, so no gap length is labelled automatically safe.

### 4.4 Scope and limitations

The Jinsha analysis has three stations on one river and no natural missing hydrological day. Controlled masks estimate recoverable information under specified outages, not the probability or geometry of field failures. The 2015 annual endpoint shift is temporally and physically consistent with Guanyinyan operation, but the primary daily Pettitt interval predates commissioning and causal attribution remains observational. The external confirmation has five sites on one mainstem and one frozen anchor per cell; it is a clean temporal/network confirmation, not five independent basins. The national panel uses 2009 routed dam attributes rather than time-varying operation or thermal-release records, and the official fallback excludes multiple-primary-series stations after modern API rate limiting.

The external train-only curves and donor/memory labels were frozen before confirmatory performance was opened, but no numeric effect threshold was frozen. The result is therefore confirmatory for the qualitative type ordering at 90 and 180 days, not for a minimum effect size or all tested gaps. Confirmation still has one mask placement per cell; the independent validation-period SD only supplies a noise scale. The Jinsha state-matched and annual-demeaned analyses are post-hoc diagnostics added after the frozen analysis and labelled as such. Deep models were excluded by stability rules, so this paper makes no claim about their general performance.

## 5. Conclusions

Reservoir regulation leaves a detectable local fingerprint in the information available to reconstruct stream temperature. In both detailed networks, the dam-proximal station is uniquely memory-dominated, and the national regulated-site profile weakens with distance from major dams. However, the index alone fails out-of-ecoregion dam classification. A covariance budget can therefore screen local monitoring structure before model fitting, provided state, geography, and absolute skill are calibrated rather than inferred from a universal cutoff.

## 6. Data and Code Availability

The analysed Jinsha daily hydrological records were supplied to the project and are attributed to the Chinese Hydrological Yearbook. Permission to redistribute the exact $T$, $F$, and $L$ files was not established. CMA humidity and sunshine and the WMO/CMA meteorological series are likewise restricted under the rights matrix. These inputs will be provided to editors and reviewers through AGU GEMS Data Files for Peer Review under the journal's confidential-review workflow; they are not “available upon request.” Aggregate tables and figures do not redistribute daily records.

USGS and NASA POWER inputs for the Chattahoochee confirmation are public-source observations archived with provenance. Original code is MIT-licensed. The public repository history was rewritten to code-only scope after a verified private bundle and commit map were created; the rights audit reports zero restricted tracked paths. An immutable archival DOI is still required before submission. The `CITATION.cff` DOI remains unset until a real archive record is minted; no DOI is invented in this manuscript.

The reproducible revision entry point is `scripts/34_run_major_revision.py`. Formal internal outputs are accepted only when `results/analysis/analysis_manifest.json` is complete; external evidence is accepted only with the complete once-lock and `completion_manifest.json`. The frozen prediction remains `results/predictions/recoverability_prediction_v1.json`.
