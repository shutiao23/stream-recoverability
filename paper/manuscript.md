# Reservoir-Associated Thermal Structure Predicts Stream-Temperature Recoverability in the Jinsha and Chattahoochee Rivers

## Abstract

Reservoir releases can compress downstream thermal seasonality and extend persistence, but those changes are rarely connected to information for reconstructing monitoring outages. We use controlled gaps to probe that connection rather than rank imputation models. A train-only covariance heuristic separates simultaneous donor anomalies from local boundary memory at three Jinsha River stations. Batang and Shigu are donor-dominated, whereas dam-proximal Panzhihua is memory-dominated; this classification is unchanged from 14- to 90-day horizons. Panzhihua annual endpoints shift in 2015, although daily change dates are method-sensitive and do not establish reservoir causality. The frozen heuristic tracks internal best-envelope shape (correlations 0.72--0.95), but its magnitude is state-dependent. In a temporally held-out Chattahoochee evaluation, validation selects XGBoost at all five sites. The memory-dominated gauge below Buford Dam has skill -0.380 and -0.300 at 90 and 180 days, whereas four donor-dominated downstream sites retain 180-day skill of 0.555--0.746. A separate 335-station United States panel shows that the index alone does not classify upstream major-dam presence across ecoregions (frozen pooled leave-one-ecoregion-out AUC 0.407, 95% interval 0.222--0.515). A post-hoc within-fold diagnosis still finds no national skill (mean AUC 0.526) and a region-dependent direction (Northeast 0.755 versus Southeast Plains 0.132). The index median declines with distance within regulated watersheds. Reservoir-associated covariance structure can therefore screen local recoverability type, but it is neither a universal dam classifier nor an information-theoretic ceiling.

## 1. Introduction

A monitoring network contains information even when none of its sensors has failed. Its arrangement determines whether an outage can be reconstructed from seasonality, synchronous river stations, atmospheric forcing, hydraulics, or observations at the edges of a gap. We call this property *recoverability*: performance on a predeclared missing target under a stated outage geometry and information condition, relative to a named baseline. Controlled masking supplies known truth and can therefore measure information available for reconstruction without claiming to reproduce the frequency of field failures.

Continuous gaps can bias annual thermal statistics [@johnson2021datagap], and existing reconstructions use air temperature, discharge, seasonal structure, and spatially paired sensors [@li2017streamairimputation; @bal2023streamtemperature]. Yet a good reconstruction does not by itself explain why one reach depends on synchronous network observations while another depends on its own boundaries.

Reservoir operation provides a physical reason for that distinction. Release depth and storage state alter downstream seasonal amplitude and timing [@michie2020releases], and longitudinal observations show that thermal effects can attenuate downstream [@zhao2020danjiangkou]. Regional stream-air indicators can already identify dam-like thermal signatures without a dam map [@seyedhashemi2021thermalsignatures]. Our novelty is therefore not dam detection itself. We ask whether reservoir-associated thermal structure anticipates which information sources remain useful when observations are removed.

We address three questions. First, do dam-proximal stations in two detailed networks show a repeatable memory-dominated covariance type? Second, does a train-only covariance heuristic anticipate held-out long-gap recoverability without selecting a model on the scored event? Third, is the same fingerprint geographically portable, or does its interpretation require river and ecoregion context? The directional hypothesis is that compressed seasonal range and extended anomaly memory accompany greater boundary-memory dependence and weaker long-gap donor replacement near regulated releases.

We froze the heuristic at three Jinsha stations, evaluated structured 2018--2020 outages, and added explicitly post-hoc stationarity controls without altering that prediction. We then evaluated a five-site 2023--2025 Chattahoochee panel beginning below Buford Dam, using a fixed model chosen only from 2021--2022 validation placements. Finally, an independently frozen United States panel tested the geographic boundary. The design is an observational mechanism and scope test across two detailed networks plus a national diagnostic, not a causal reservoir experiment or a claim that one imputation model is generally best.

## 2. Methods

### 2.1 Study networks and regulation setting

The Jinsha stations, ordered downstream, were Batang (B1), Shigu (S2), and Panzhihua (P3), separated by 463 and 558 river km (Figure 1). Daily temperature ($T$), discharge ($F$), and level ($L$) covered 1 January 2006 through 31 December 2020. Station-matched meteorology comprised air temperature, precipitation, wind, relative humidity, and NASA POWER all-sky shortwave radiation. The hydrological records are attributed to the *Annual Hydrological Report of the People's Republic of China, Volume VI* [@wei2026flowcomposition; @wang2024yangtzetemperature]. The map uses documented station coordinates, the official 27-km Guanyinyan--P3 distance for interpretation, and a separate cartographic dam coordinate [@rccdams2026guanyinyan].

Guanyinyan is the last project in the planned middle-Jinsha cascade, has weekly regulation, and lies 27 km upstream of Panzhihua according to the national impoundment-stage environmental approval [@mee2014guanyinyan]. Its first unit began generation on 20 December 2014, three more units followed in 2015, and all five were operating in 2016 [@cdt2026guanyinyan; @nea2016powerreport]. We use those dates only to interpret an independently observed thermal transition; this observational design does not isolate the dam from every concurrent basin change.

The external panel comprised USGS sites 02334430, 02335000, 02335450, 02336000, and 02337170 on one Upper-to-Middle Chattahoochee mainstem network. Site 02334430 is 366 m below Buford Dam [@usgs1973buford]. Buford hydropower releases originate near the reservoir bottom and are cold relative to surface water during stratification [@usace2017buford]. External fitting, validation, and confirmatory periods were 2012--2020, 2021--2022, and 2023--2025.

### 2.2 Records, temporal separation, and controlled outages

Jinsha fitting, model-selection, and development-evaluation periods were 2006--2015, 2016--2017, and 2018--2020. The stored `test` label is a legacy alias of `development_test`; it is not an unseen confirmatory split. All scalers, climatologies, feature medians, and fitted models used the fitting period only.

The Jinsha $T$, $F$, and $L$ series contain no natural missing day in the 5,479-day study axis. Per-value provider quality flags were unavailable. Provenance reconciliation identified an 8.48-m B1 level datum step in 2019 and a 2013--2019 ordering discrepancy between supplied S2 hydrology and an external monthly archive. Values were not silently corrected: the primary version retains them with known-issue flags, and frozen versions exclude S2 hydrology, exclude B1 level, or apply a declared hypothetical B1 level shift. These sensitivities affect some covariate-dependent models but do not change the observation-only temperature type.

Artificial masks are controlled interventions used to measure network information; they do not estimate field-failure frequency. Masks hide only finite eligible values, are removed from every model input path, and span point gaps, contiguous blocks, compound $T+F+L$ outages, and matched network failures. The primary dense design has 15 block lengths from 1 to 365 days, three stations, and 20 frozen anchors (900 scenarios). The network design crosses four target-gap lengths with all eight failure subsets of B1, S2, and P3 (1,920 scenarios). These geometries are stress tests, not a fitted fault model.

### 2.3 Hydrothermal state and regulation fingerprint

We summarized annual minimum, maximum, mean, and amplitude directly in degrees C. Temperature anomalies subtract a fitting-period circular day-of-year median with a plus or minus seven-day window. For pre- and post-impoundment periods we report anomaly mean, standard deviation, lag-30 and lag-90 autocorrelation, skewness, and excess kurtosis.

We also estimated one post-hoc change in the complete 3,652-day P3 fitting-period anomaly series, requiring at least 365 days on each side. Pettitt's rank statistic was the primary estimator. Because lag-1 autocorrelation was 0.973, its iid asymptotic and day-permutation p values are reference calculations only; inference uses 9,999 permutations of intact calendar-year blocks. A segmentwise circular moving-block residual bootstrap with 5,000 draws and 365-day blocks supplies a date interval. Single least-squares binary segmentation under the same permutation and bootstrap settings is a method sensitivity. Annual minimum and amplitude Pettitt tests are reported separately, recognizing that the fitting period contains only one fully post-commissioning year.

For comparison across all eight stations, the data-derived memory--range index is

$$I_s=\frac{\operatorname{acf}_{30}(T'_s)}{\max(T_s)-\min(T_s)},$$

where the range and anomaly autocorrelation are computed only in the network's fitting period. This is a descriptive regulation fingerprint, not a universal classifier. We compare its within-network rank with the independently frozen donor/memory type and with distance or position relative to the regulating dam.

### 2.4 Frozen covariance heuristic

Exact calendar-day medians fitted within the declared calibration period were subtracted from target and donor temperatures. Simultaneous donor anomalies give $R^2_{\mathrm{donor}}$. Target anomaly memory at the mean distance from a uniformly distributed point inside a two-sided block to its nearest boundary is evaluated at $d/4$. The frozen heuristic is

$$R^2_{\mathrm{avail}}(d)=R^2_{\mathrm{donor}}+(1-R^2_{\mathrm{donor}})\rho^2(d/4),$$

$$\widehat{\operatorname{skill}}(d)=1-\sqrt{1-R^2_{\mathrm{avail}}(d)}.$$

The $d/4$ distance follows from averaging the nearest-boundary distance over a continuous block. The additive expression assumes that memory explains a fraction of variance remaining after donor information; donor and boundary signals are not empirically orthogonalized. The MAE conversion additionally assumes a common location--scale residual shape. Consequently, these equations define a screening heuristic, not a theorem, physical heat budget, or information ceiling. At 30 days, a station is donor-dominated when the donor component is at least the memory component, and memory-dominated otherwise. We also evaluate this label at 14, 60, and 90 days. The original 2006--2015 prediction was written before dense aggregation and was never altered.

To test omitted-variable sensitivity, we expanded the linear anomaly regression with same-site air temperature, $F$, and $L$, and donor-site air temperature and $F$. To test state dependence, we recalculated the heuristic for 2016--2017 (a leakage-free but short bridge) and for 2016--2020 (a post-hoc state-matched diagnostic that overlaps evaluation and is not predictive evidence).

### 2.5 Recovery models and evidence roster

The common baseline was a training-only circular plus or minus seven-day median climatology. The formal roster contained linear and PCHIP interpolation, a local-linear-trend Kalman smoother, air-only and air-plus-hydraulics ridge regressions, donor regression, random forest, and XGBoost. Offline recovery may use both boundaries of a historical gap.

Official BRITS, SAITS, and CSDI implementations and a multisource quantile model were evaluated during validation. Under the frozen stability rule, required seeds selecting before epoch 50 or hitting the 400-epoch cap could not enter the formal roster. None of the deep candidates entered; their architecture, training diagnostics, validation-only rankings, and information-group ablations are reported only in Supporting Information. No conclusion about the capability of deep imputation follows from excluded unstable runs.

### 2.6 Skill, absolute error, stationarity controls, and inference

For event $e$, skill relative to a named baseline is

$$\operatorname{skill}_e=1-\frac{\operatorname{MAE}_{e,\mathrm{model}}}{\operatorname{MAE}_{e,\mathrm{baseline}}}.$$

Every main curve and table also reports model MAE and baseline MAE in degrees C. The climatology denominator was withheld at or below 0.05 degrees C. The statistical frontier is the first gap at which the non-increasing 95% lower confidence curve ceases to exceed zero. It is not an ecological or operational safety threshold.

The two frontier denominators--climatology and the validation-selected best simple baseline--pass through one anchor/year, overlap-aware bootstrap implementation. All 27 climatology frontier cells are identical between the summary and dual-denominator tables.

Training seeds were averaged before inference. Frontier curves use 2,000 joint cross-gap resamples stratified by station and anchor year, with connected overlap components retained as blocks. For the model-versus-climatology family, one cross-gap mean per anchor/year is tested by the frozen two-sided Wilcoxon rule. Climatology self-comparisons are labelled `reference_not_tested`; they do not receive artificial $p=1$ values. Benjamini--Hochberg correction is applied across the 24 actual hypotheses.

Two post-hoc robustness scores address the P3 transition. First, fixed model predictions are re-scored against a 2016--2020 state-matched climatology while the heuristic is recalibrated to the same state. Because this climatology includes evaluation years, the result diagnoses denominator contamination and is not a new test. Second, truth and prediction anomalies are separately demeaned within calendar year before MAE is computed; this removes constant and slower annual offsets while retaining within-year shape.

### 2.7 Donor falsification and cross-fitted node importance

Donor information was tested against lagged, implausible-lead, station-identity-permuted, and seasonal-residual-permuted contrasts. Persistence of gain under physically implausible contrasts falsifies a downstream-transport interpretation and restricts the claim to shared predictive information.

Node importance avoids selecting a model on the event being scored. For every target, gap length, and failure set, we leave out one evaluation year, choose the lowest-mean-MAE roster model using the other two years, and score that fixed choice on all anchors in the held-out year. Climatology is an ordinary candidate, not an event-wise cap. Full- and failed-network errors are paired on the same target gap,

$$\Delta_j=\operatorname{MAE}(\widehat m_{-y,j}\mid j\ \text{failed},y)-\operatorname{MAE}(\widehat m_{-y,0}\mid\text{full network},y),$$

where $\widehat m_{-y,j}$ is selected without year $y$. We aggregate four gap lengths and bootstrap matched anchors within year. Because selection folds are drawn from development evaluation after the original analysis, this is an explicitly post-hoc, non-oracle sensitivity rather than independent confirmation. The former event-wise best envelope is retained only in Supporting Information.

### 2.8 Temporally held-out external evaluation

Before opening 2023--2025 performance, the external sites, periods, variables, nine-model roster, mask seed, 60 scenarios, and complete train-only predicted curves were fixed. The heuristic classified 02334430 as memory-dominated and the other four sites as donor-dominated. The run created a once-lock before model scoring and completed all 540 model--scenario units. The originally frozen best-roster envelope is retained as a descriptive estimand because it selects the maximum observed performance within a confirmatory cell.

Because that run used one mask placement per cell, a post-freeze diagnostic used only the 2021--2022 validation period. The same five sites, 30/90/180-day full-information blocks, nine-model roster, and 20 placements produced 2,700 cells; inputs were physically truncated before 2023, and confirmatory outputs were not read. For the non-oracle primary presentation, one fixed model per site is chosen by mean skill across all 60 validation site--gap--placement cells and then scored unchanged in 2023--2025. This selection rule was formulated after the confirmatory envelope had been observed, so it is labelled a post-hoc fixed-model sensitivity, not preregistration. Validation-period sample SD describes placement variation and is not a confirmatory confidence interval.

### 2.9 Independently frozen national regulation panel

After the two case-study analyses, but before reading any national temperature-panel outcome, we froze an independent USGS/GAGES-II test (`regulation_panel_freeze_v1`; SHA-256 `260bd313...`). Its runtime path guard and static source audit prohibit the Chattahoochee data, results, and once-lock. USGS primary daily-mean water-temperature metadata and approved values for 2000--2019 were joined by exact station number to routed GAGES-II watershed attributes [@usgs2026waterapi; @falcone2011gagesii]. Eligible stream sites required one unspliced primary series and at least 10 calendar years with at least 300 approved days. The binary label was at least one upstream GAGES-II major dam in the 2009 snapshot; Euclidean nearest NID points were explicitly prohibited as upstream labels [@usace2026nid].

The primary predictor was the pre-existing memory--range index. The frozen primary analysis was unadjusted logistic regression with HC1 uncertainty plus leave-one-aggregated-ecoregion-out ROC AUC and 2,000 ecoregion-cluster bootstrap draws. Pooled leave-one-ecoregion-out AUC is the frozen primary generalization metric; an AUC near 0.5 does not reopen the freeze. A drainage-area/ecoregion-adjusted coefficient and a regulated-site profile in 0--5, 5--20, 20--50, 50--100, and greater than 100 km nearest-major-dam bins were sensitivities; no threshold was selected.

A post-hoc diagnosis computed AUC inside each held-out ecoregion because pooled out-of-fold AUC under leave-one-group-out can attribute intercept and base-rate mismatch to discrimination. Single-predictor logistic intercepts are calibrated on complementary folds whose dam rate is near 60%, then scored on held-out ecoregions whose dam rates range from 0 to 0.95. This diagnosis does not replace or reopen the freeze.

The modern USGS daily API returned HTTP 429 after 26 of 56 atomic batches and no API key was available. Before any panel metric, a transport amendment froze the official legacy `/dv` service as a fallback only for stations having exactly one frozen primary series; 22 multiple-series stations were excluded rather than spliced. Across 1,662,961 station-dates available from both transports, approved values agreed exactly. Results are labelled `transport_limited_maximum_legal_panel`; they do not claim a complete modern-API roster.

### 2.10 Preregistered versus post-hoc analyses

The table below classifies the analyses that appear in the main text. Frozen items were written before the outcomes they constrain. Post-hoc items are labelled as such wherever they support a claim. The external validation-selected fixed-model rule is post-hoc; it is not preregistered confirmation.

| Analysis | Classification |
| --- | --- |
| Jinsha 2006--2015 covariance heuristic and donor/memory type | Frozen; written before dense aggregation |
| Formal nine-model roster after stability exclusion | Frozen |
| External sites, periods, masks, and train-only predicted curves | Frozen before 2023--2025 outcomes |
| Evaluate-once confirmatory lock | Frozen |
| National panel freeze v1 and transport amendment | Frozen before any panel metric |
| Unadjusted logistic regression and pooled leave-one-ecoregion-out AUC | Frozen primary national analysis |
| Drainage-area/ecoregion-adjusted logistic and regulated-site distance profile | Predeclared national sensitivities |
| Donor-falsification contrasts | Frozen |
| 2016--2017 and 2016--2020 state-matched heuristic and climatology | Post-hoc |
| Annual demeaning | Post-hoc |
| Expanded covariate budget | Post-hoc |
| P3 Pettitt and least-squares change-date | Post-hoc |
| Cross-fitted node importance | Post-hoc |
| External validation-selected fixed-model rule | Post-hoc; not preregistered confirmation |
| External 20-seed placement SD | Post-hoc |
| Within-fold leave-one-ecoregion-out AUC diagnosis | Post-hoc; this revision; does not reopen the freeze |

## 3. Results

### 3.1 A regulation-consistent thermal transition at P3

P3 annual endpoints shifted in 2015 (Figure 2; Table 2). In 2006--2014, its annual minimum was 8.7--10.3 degrees C and annual amplitude was 11.7--14.1 degrees C. In 2015--2020, minima were 11.5--12.5 degrees C and amplitudes were 9.6--10.7 degrees C. Relative to the 2006--2015 climatology, anomaly SD increased from 0.91 degrees C before impoundment to 1.96 degrees C afterward, and acf30 increased from 0.39 to 0.76. B1 and S2 showed no comparable endpoint shift: their pre/post anomaly SD values were 0.94/0.91 and 0.78/0.81 degrees C, and acf30 remained near 0.14/0.07 and 0.14/0.11. If the P3 transition were a basin-wide climate shift, B1 and S2 would have shown comparable increases in anomaly SD and acf30; they did not.

The formal daily change date was method-sensitive. Pettitt estimated 26 May 2013 (95% 365-day moving-block residual-bootstrap interval, 14 May 2011 to 22 October 2013). The dependence-aware calendar-year permutation p value was 0.0088, but the interval did not contain 20 December 2014. Least-squares single segmentation instead estimated 18 October 2014 (interval, 16 April 2014 to 1 January 2015; year-block $p=0.0117$), and that interval did contain first-unit operation. In 2015, annual minimum was 2.8 degrees C above and amplitude 2.4 degrees C below their 2006--2014 medians, but annual Pettitt tests were not significant ($p=0.2208$ and $0.8607$) with only one post-commissioning fitting year. We therefore infer a statistically detectable but method-sensitive state change and temporal consistency in one sensitivity, not precise localization of commissioning or causal attribution by change-point analysis alone.

The covariance calculation classified B1 and S2 as donor-dominated and P3 as memory-dominated without dam information. The labels were unchanged at 14, 30, 60, and 90 days. P3 ranked first within the Jinsha network on the memory--range index. The same diagnostic selected Chattahoochee site 02334430, immediately below Buford Dam, as the only memory-dominated site at all four horizons. Downstream, observed temperature range increased from 9.9 to 14.8, 18.0, 23.7, and 24.0 degrees C, whereas acf30 declined from 0.762 to 0.397, 0.377, 0.304, and 0.281. That pattern is consistent with, but does not by itself identify, thermal re-equilibration below a regulated release [@zhao2020danjiangkou; @seyedhashemi2021thermalsignatures].

### 3.2 The heuristic predicts shape but not a universal ceiling

The frozen donor $R^2$ was 0.464 at B1, 0.470 at S2, and 0.106 at P3. Best-envelope correlations with the predicted curve were 0.72, 0.94, and 0.95; mean absolute skill errors were 0.077, 0.085, and 0.122 (Figure 3). The best model exceeded the point heuristic in 20 of 45 cells. Nine lower confidence bounds exceeded it, all at P3; none did so at B1 or S2. These results support qualitative shape screening at B1/S2 but reject the original interpretation as a universal ceiling.

The expanded covariate regression raised $R^2$ only from 0.464 to 0.537 at B1, 0.470 to 0.532 at S2, and 0.106 to 0.148 at P3. The corresponding P3 long-gap skill approximation rose only from 0.055 to 0.077, excluding omission of measured air temperature and hydraulics as a sufficient explanation.

State control strongly changed the P3 conclusion. Re-scoring against a 2016--2020 climatology reduced lower-bound exceedances from nine to one; at 365 days, XGBoost changed from skill 0.209 against the old climatology to -0.588 against the state-matched climatology, while the recalibrated heuristic was 0.069. Annual demeaning was less decisive: P3 XGBoost retained skill 0.164 (95% interval 0.130--0.197) at 365 days. Thus the sustained offset explains much of the apparent long-gap advantage, but within-year structure also remains recoverable.

### 3.3 Relative skill represents tenths of a degree

Training climatology explained 97.0% of B1 temperature variance, 97.2% at S2, and 91.6% at P3. Across the dense design, climatology MAE ranged from 0.681 to 0.771 degrees C at B1, 0.648 to 0.704 degrees C at S2, and 1.218 to 1.347 degrees C at P3 (Figure 4; Table 4). A skill of 0.25 therefore usually represents an improvement of roughly 0.17--0.34 degrees C, not a multi-degree change.

Using the single corrected frontier path, random forest and XGBoost were right-censored at 365 days at B1 and S2, and XGBoost was right-censored at P3. Interpolation/Kalman frontiers occurred at 7.0--8.8 days at B1, 21.2--22.7 days at S2, and 93.1--160.0 days at P3. No fixed model was robustly superior to the validation-selected best-simple denominator across the full dense curve. Of 24 actual model-versus-climatology hypotheses, 14 passed BH correction. Seven had positive mean skill: random forest and XGBoost at B1; donor regression, random forest, and XGBoost at S2; and Kalman and XGBoost at P3. Seven additional rejections identified methods significantly worse than climatology. These directional results replace the former family of 27 artificial $p=1$ values.

### 3.4 Donor value reflects shared forcing; cross-fitted costs are modest

Observed same-day donor information exceeded the station-identity permutation by 0.057 skill across 60 paired units ($p=0.000179$). However, gain persisted under identity permutation and implausible lags, triggering the preregistered `falsified_network_propagation` decision. Synchronous stations therefore carry shared climatic or regulation information, but the experiment does not identify downstream heat transport.

The cross-fitted estimator changed both magnitude and interpretation (Figure 5; Table 5). Averaged over four gap lengths, losing S2 increased B1 MAE by 0.105 degrees C (95% bootstrap interval 0.044--0.169). B1 and P3 losses changed B1 MAE by -0.023 (-0.061--0.016) and -0.013 (-0.040--0.016) degrees C. For P3 recovery, B1 and S2 losses increased MAE by 0.058 (0.010--0.119) and 0.054 (0.012--0.113) degrees C. No S2-target contrast excluded zero. These are post-hoc policy sensitivities under leave-one-year-out selection, not causal station values or event-wise oracle minima.

### 3.5 Held-out long-gap ordering transfers, but magnitude does not

Mean performance over the 2021--2022 validation placements selected XGBoost at all five sites before the fixed-model sensitivity was scored in 2023--2025 (Figure 6). At site 02334430 below Buford Dam, its skill was -0.209, -0.380, and -0.300 at 30, 90, and 180 days. The four donor-dominated sites retained 180-day skill of 0.726, 0.555, 0.746, and 0.724. Thus the memory site was the weakest at both 90 and 180 days under one fixed model, without selecting the best model in each scored cell.

The 20-placement validation diagnostic showed substantial variation. For the selected XGBoost policy, 180-day skill SD was 0.175 at 02334430 and 0.180, 0.121, 0.058, and 0.043 at the donor sites. These are validation-period noise scales, not uncertainty intervals for the single 2023--2025 placement. The originally frozen best-roster envelope gave 02334430 skill 0.141 at 180 days, illustrating how within-cell outcome selection can make the same site appear more recoverable; that envelope is now descriptive only.

The heuristic predicted 0.414 skill at 180 days for 02334430 but the selected fixed model achieved -0.300. Exact magnitudes therefore did not transfer. The external result supports long-gap type ordering in one temporal/network evaluation, not a universal frontier or a causal regulation effect.

### 3.6 National panel supports a distance gradient, not a standalone classifier

The frozen national flow discovered 5,707 temperature series, found 1,361 exact GAGES-II station overlaps and 1,344 stream sites, and retained 335 eligible stations (209 with and 126 without an upstream major dam). The primary unadjusted association was positive but uncertain: odds ratio 1.23 per index SD (95% CI 0.93--1.61; $p=0.144$). More importantly, the frozen primary pooled leave-one-ecoregion-out AUC was 0.407 (ecoregion-cluster bootstrap interval 0.222--0.515; Figure 7). The index alone therefore did not generalize as a national major-dam classifier.

A post-hoc diagnosis then computed AUC inside each held-out ecoregion (Text S15; Table S8). Fold dam rates ranged from 0 (Alaska) to 0.95 (WestPlains). In this post-hoc diagnosis, the correlation between fold base rate and fold out-of-fold probability median was $-0.671$: the Alaska fold, with no regulated sites, had the highest median predicted probability (0.722), whereas WestPlains had the lowest (0.559) despite a 0.95 dam rate. Post-hoc mean and median within-fold AUC were 0.526 and 0.513. Four eastern and central folds had AUC 0.614--0.755 (NorthEast 0.755, $n=33$, base rate 0.727; EastHghlnds 0.742; CntlPlains 0.667; MxWdShld 0.614). The Southeast Plains reversed the case-study direction (AUC 0.132; $n=63$; base rate 0.508). That reversal is consistent with a mechanism sketch in which natural low-amplitude, long-memory regimes--groundwater influence, sluggish flow, and a warm climate--can reproduce the regulated signature; it is not a causal attribution. This geography is why within-climate comparisons such as Jinsha and Chattahoochee can hold while a national classifier fails. The post-hoc mean of 0.526 is still no national skill and does not replace the frozen primary.

The frozen sensitivities retained a localized signal. After drainage-area and ecoregion adjustment, the index odds ratio was 2.52 (1.18--5.36; $p=0.0167$), although a single-class Alaska ecoregion produced a fixed-effect separation warning. Among regulated watersheds, median memory--range index declined from 0.0110 for 83 stations within 5 km of a major dam to 0.00690 at 5--20 km, 0.00611 at 20--50 km, and 0.00463 at 50--100 km; median acf30 declined from 0.262 to 0.135. The greater-than-100-km bin had one station and was not interpreted. Thus case-study direction and the regulated-site distance profile agree, while cross-ecoregion binary discrimination does not.

## 4. Discussion

### 4.1 Reservoir-associated structure organizes recoverable information

The two networks show the same association: the dam-proximal station combines compressed seasonal range, extended persistence, and memory-dominated recoverability. Downstream of Buford, range increases and acf30 declines while fixed-model long-gap skill remains high. This direction agrees with observations that release depth and storage change downstream thermal amplitude [@michie2020releases], that dam effects attenuate longitudinally [@zhao2020danjiangkou], and that regional stream-air indicators can recover dam-like thermal signatures [@seyedhashemi2021thermalsignatures]. Our additional result is that the same structure anticipates information available during controlled outages. The observational design does not show that regulation alone caused either covariance pattern.

The donor falsification result sharpens this interpretation. Donor value that survives impossible lags or station relabelling is evidence of common forcing, not advected heat. In a regulated network that shared source may include release schedules and basin-scale weather as well as ordinary seasonality. The Jinsha sites are hundreds of river kilometres apart, so “donor” denotes synchronous predictive information rather than a neighbouring sensor or a travel-time mechanism. Recoverability is an observational probe of network information, not a causal pathway identifier.

The national panel bounds the generality of this mechanism. The monotone 0--100-km profile is consistent with downstream thermal re-equilibration. The frozen primary pooled leave-one-ecoregion-out AUC of 0.407 is partly a metric defect: pooling fold-calibrated probabilities across ecoregions whose dam rates range from 0 to 0.95 scores intercept mismatch as (anti)discrimination. A post-hoc within-fold diagnosis, however, still finds no national skill (mean AUC 0.526). The informative result of that diagnosis is region-dependent direction, including a reversal in the Southeast Plains. Climate, channel scale, groundwater and sluggish-flow regimes, release depth, dam operation, and network placement can produce overlapping covariance signatures. The adjusted association is supporting evidence, not a rescue of the primary national null.

### 4.2 What remains of the covariance heuristic

The original ceiling language was too strong. All lower-bound exceedances occurred where calibration and evaluation crossed a thermal transition. Once the denominator and heuristic were matched to the later state, almost all disappeared, yet annual demeaning left positive long-gap skill beyond the original prediction. The additive donor-plus-memory form is not an orthogonal variance decomposition, and its MAE conversion requires empirical calibration. It is useful as a qualitative screening curve and stable type label, not as an information-theoretic bound.

### 4.3 Monitoring-network consequences

The cross-fitted analysis and the case-study error scale give a limited planning signal rather than a ranking of sensors. In degrees C rather than skill:

1. Losing S2 raises B1 reconstruction MAE by 0.105 degrees C (95% interval 0.044--0.169).
2. At memory-dominated reaches, protect observations on both sides of a gap rather than adding a distant donor.
3. Typical model gains are tenths of a degree against climatology MAE of about 0.65--1.35 degrees C; statistical advantage is not an ecological safety threshold.
4. Detect thermal state changes; they can invert long-gap skill interpretations (P3 365-day XGBoost 0.209 to $-0.588$ under state-matched climatology).

These values depend on the three-station roster and post-hoc cross-fitting population. They motivate prospective validation of fallback policies, not immediate station removal or protection decisions. No threshold was declared for habitat, management, or trend use, so no gap length is labelled automatically safe.

### 4.4 Scope and limitations

The Jinsha analysis has three widely separated stations on one river and no natural missing hydrological day. Controlled masks estimate recoverable information under specified outages, not field-failure probability. The 2015 annual endpoint shift is physically consistent with Guanyinyan operation, but the primary daily Pettitt interval predates commissioning and causal attribution remains observational. Provider quality flags were unavailable, the B1 level datum changes, and S2 hydrology has a provenance discrepancy; frozen sensitivities and public aggregates expose rather than resolve those limitations. The external panel has five sites on one mainstem and one scored placement per cell, not five independent basins. The national panel uses 2009 routed dam attributes rather than time-varying release depth or operation. No reservoir operations or release-depth series were obtained, and we do not invert temperature for operations. The Buford operations literature already cited is engineering context, not this study's data.

The external train-only curves and donor/memory labels were frozen before 2023--2025 performance was opened, but no numeric effect threshold was frozen. The fixed-model selection rule was formulated afterward using only truncated 2021--2022 validation data. We therefore call it a held-out post-hoc sensitivity, not a preregistered confirmation. The validation-period SD supplies a placement scale rather than a confidence interval. Jinsha state controls, cross-fitted node importance, and the within-fold leave-one-ecoregion-out AUC diagnosis are also post-hoc. Deep models were excluded by stability rules, so no conclusion about their general capability follows.

## 5. Conclusions

Reservoir-associated thermal structure contains information about stream-temperature recoverability. In both detailed networks, the dam-proximal station is uniquely memory-dominated from 14- to 90-day horizons, and a fixed validation-selected model performs substantially worse there on long held-out gaps. National discrimination is not supported (frozen pooled leave-one-ecoregion-out AUC 0.407; post-hoc mean within-fold AUC 0.526). A post-hoc diagnosis finds that the fingerprint's direction is region-dependent, ranging from AUC 0.755 in the Northeast to 0.132 in the Southeast Plains, where natural low-amplitude long-memory regimes can reproduce the regulated signature. That geography is why within-climate case studies can hold while a national classifier fails. The covariance heuristic can therefore screen local monitoring structure before model fitting, provided state, geography, and absolute error are calibrated and no causal threshold is inferred from the index alone.

## 6. Data and Code Availability

The analysed Jinsha daily hydrological records were supplied to the project and are attributed to the Chinese Hydrological Yearbook. Permission to redistribute the exact $T$, $F$, and $L$ files was not established. CMA humidity and sunshine and the WMO/CMA meteorological series are likewise restricted under the rights matrix. Subject to written editor approval of this restricted third-party-data exception, the exact analysis inputs will be provided through AGU GEMS Data Files for Peer Review under the confidential-review workflow; they are not “available upon request.” The paper will not be submitted without that approval. Public aggregate tables and figures do not redistribute daily records.

USGS and NASA POWER inputs for the Chattahoochee evaluation are public-source observations archived with provenance. Original code is MIT-licensed. The public repository history was rewritten to code-only scope after a verified private bundle and commit map were created; the rights audit reports zero restricted tracked paths. An immutable archival DOI is still required before submission. The `CITATION.cff` DOI remains unset until a real archive record is minted; no DOI is invented in this manuscript.

The reproducible revision entry point is `scripts/34_run_major_revision.py`. Formal internal outputs are accepted only when `results/analysis/analysis_manifest.json` is complete; external evidence is accepted only with the complete once-lock and `completion_manifest.json`. The frozen prediction remains `results/predictions/recoverability_prediction_v1.json`.
