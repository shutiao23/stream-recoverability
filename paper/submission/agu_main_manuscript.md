---
title: "Reservoir-Associated Thermal Structure Predicts Stream-Temperature Recoverability in the Jinsha and Chattahoochee Rivers"
author:
  - "[Full author names and affiliations required]"
date: "Draft built from repository evidence"
keywords:
  - stream temperature
  - reservoir regulation
  - missing data
  - monitoring networks
  - thermal memory
---

# Title Page

**Authors and affiliations:** [AUTHOR INPUT REQUIRED]**Corresponding author:** [NAME, EMAIL, AND ORCID REQUIRED]

# Key Points

- Dam-proximal stations in two rivers rely more on local thermal memory during temperature-record outages.
- A fixed validation-selected model preserves the predicted long-gap ordering but not the predicted error magnitude.
- No national skill (frozen AUC 0.407; post-hoc mean 0.526); post-hoc direction is region-dependent and reverses in the Southeast Plains.


# Plain Language Summary

Reservoir releases can make downstream water temperatures less seasonal and more persistent. We tested whether those changes indicate which observations can reconstruct an outage in a temperature record. We temporarily hid known daily values at three Jinsha River stations and five Chattahoochee River stations, then compared information from other stations with information at the edges of each gap. In both rivers, the station closest below a major dam depended more on its own past and future boundaries, while stations farther away depended more on simultaneous network observations. A model chosen using earlier Chattahoochee data performed much worse on 90- and 180-day gaps at the station below Buford Dam than at four downstream stations. However, the calculation did not predict the exact error. Across 335 United States gauges, the same indicator weakened with distance below major dams but did not classify dams nationwide; in the Southeast Plains the direction even reversed. The indicator is therefore a local or regional screen that requires geographic context and local error testing. The study is observational: it does not show that a dam alone produced each temperature pattern, and it does not identify a safe gap length to reconstruct.


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

To test omitted-variable sensitivity, we expanded the linear anomaly regression with same-site air temperature, $F$, and $L$, and donor-site air temperature and $F$. To test state dependence, we recalculated the heuristic for 2016--2017 (a leakage-free but short post-hoc bridge; those years remain the frozen model-selection split) and for 2016--2020 (a post-hoc state-matched diagnostic that overlaps evaluation and is not predictive evidence).

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
| 2016--2017 as the model-selection / validation split | Frozen |
| 2016--2017 heuristic recalculation | Post-hoc; leakage-free bridge |
| 2016--2020 state-matched heuristic and climatology | Post-hoc |
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

A post-hoc diagnosis then computed AUC inside each held-out ecoregion (Text S15; Table S8). Fold dam rates ranged from 0 (Alaska) to 0.95 (WestPlains). In this post-hoc diagnosis, the correlation between fold base rate and fold out-of-fold probability median was $-0.671$: the Alaska fold, with no regulated sites, had the highest median predicted probability (0.722), whereas WestPlains had the lowest (0.559) despite a 0.95 dam rate. Post-hoc mean and median within-fold AUC were 0.526 and 0.513. Four eastern and central folds had AUC 0.614--0.755 (NorthEast 0.755, $n=33$, base rate 0.727; EastHghlnds 0.742; CntlPlains 0.667; MxWdShld 0.614). The Southeast Plains reversed the case-study direction (AUC 0.132; $n=63$; base rate 0.508). That reversal is consistent with a mechanism sketch in which natural low-amplitude, long-memory regimes--groundwater influence, sluggish flow, and a warm climate--can reproduce the regulated signature; it is not a causal attribution. The same geography is consistent with within-climate comparisons such as Jinsha and Chattahoochee holding while a national classifier fails. The post-hoc mean of 0.526 is still no national skill and does not replace the frozen primary.

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

Reservoir-associated thermal structure contains information about stream-temperature recoverability. In both detailed networks, the dam-proximal station is uniquely memory-dominated from 14- to 90-day horizons, and a fixed validation-selected model performs substantially worse there on long held-out gaps. National discrimination is not supported (frozen pooled leave-one-ecoregion-out AUC 0.407; post-hoc mean within-fold AUC 0.526). A post-hoc diagnosis finds that the fingerprint's direction is region-dependent, ranging from AUC 0.755 in the Northeast to 0.132 in the Southeast Plains. That reversal is consistent with a mechanism sketch in which natural low-amplitude, long-memory regimes can reproduce the regulated signature; it is not a causal attribution. The same geography is consistent with within-climate case studies holding while a national classifier fails. The covariance heuristic can therefore screen local monitoring structure before model fitting, provided state, geography, and absolute error are calibrated and no causal threshold is inferred from the index alone.


## Acknowledgments

**AUTHOR INPUT REQUIRED:** Insert all funding bodies, grant identifiers, in-kind support, and acknowledged contributors before submission.

## Conflict of Interest

**AUTHOR APPROVAL REQUIRED:** Replace this line with the final declaration approved by every author.

## Author Contributions

**AUTHOR INPUT REQUIRED:** Insert the approved CRediT contribution statement.

## 6. Open Research

The analysed Jinsha daily hydrological records were supplied to the project and are attributed to the Chinese Hydrological Yearbook. Permission to redistribute the exact $T$, $F$, and $L$ files was not established. CMA humidity and sunshine and the WMO/CMA meteorological series are likewise restricted under the rights matrix. Subject to written editor approval of this restricted third-party-data exception, the exact analysis inputs will be provided through AGU GEMS Data Files for Peer Review under the confidential-review workflow; they are not “available upon request.” The paper will not be submitted without that approval. Public aggregate tables and figures do not redistribute daily records.

USGS and NASA POWER inputs for the Chattahoochee evaluation are public-source observations archived with provenance. Original code is MIT-licensed. The public repository history was rewritten to code-only scope after a verified private bundle and commit map were created; the rights audit reports zero restricted tracked paths. An immutable archival DOI is still required before submission. The `CITATION.cff` DOI remains unset until a real archive record is minted; no DOI is invented in this manuscript.

The reproducible revision entry point is `scripts/34_run_major_revision.py`. Formal internal outputs are accepted only when `results/analysis/analysis_manifest.json` is complete; external evidence is accepted only with the complete once-lock and `completion_manifest.json`. The frozen prediction remains `results/predictions/recoverability_prediction_v1.json`.



# Tables

## Table 1
| station_id   |   median_annual_amplitude_degC |   training_observed_range_degC |   climatology_range_degC |   anomaly_sd_degC |   acf30 |   acf90 |   seasonal_variance_fraction |   R2_donor |   memory_component_30d |   donor_component_30d | recoverability_type   |   memory_range_index_per_degC | memory_range_index_definition                               |   memory_range_rank_within_network | network                     |   network_order | station_name                                       | regulation_context                | dam_distance_km   | dam_distance_basis                                                        |
|:-------------|-------------------------------:|-------------------------------:|-------------------------:|------------------:|--------:|--------:|-----------------------------:|-----------:|-----------------------:|----------------------:|:----------------------|------------------------------:|:------------------------------------------------------------|-----------------------------------:|:----------------------------|----------------:|:---------------------------------------------------|:----------------------------------|:------------------|:--------------------------------------------------------------------------|
| B1           |                          17.45 |                           20.5 |                    15.2  |             0.921 |   0.131 |   0.138 |                        0.97  |      0.464 |                  0.058 |                 0.464 | donor_dominated       |                         0.006 | acf30_divided_by_training_period_observed_temperature_range |                                  3 | Upper Jinsha                |               1 | Batang                                             | upstream of Guanyinyan            | undefined         | upstream; not used as a downstream distance                               |
| S2           |                          14.9  |                           16.5 |                    13.1  |             0.769 |   0.141 |   0.066 |                        0.972 |      0.47  |                  0.079 |                 0.47  | donor_dominated       |                         0.009 | acf30_divided_by_training_period_observed_temperature_range |                                  2 | Upper Jinsha                |               2 | Shigu                                              | upstream of Guanyinyan            | undefined         | upstream; not used as a downstream distance                               |
| P3           |                          13    |                           14.5 |                    11.75 |             1.159 |   0.59  |   0.125 |                        0.916 |      0.106 |                  0.553 |                 0.106 | memory_dominated      |                         0.041 | acf30_divided_by_training_period_observed_temperature_range |                                  1 | Upper Jinsha                |               3 | Panzhihua                                          | 27 km downstream of Guanyinyan    | 27.0              | MEE project description                                                   |
| 02334430     |                           5.3  |                            9.9 |                     4.2  |             0.936 |   0.762 |   0.516 |                        0.616 |      0.367 |                  0.507 |                 0.367 | memory_dominated      |                         0.077 | acf30_divided_by_training_period_observed_temperature_range |                                  1 | Upper--Middle Chattahoochee |               1 | CHATTAHOOCHEE RIVER AT BUFORD DAM, NEAR BUFORD, GA | 0.366 km below Buford Dam         | 0.366             | USGS 0.366 km for 02334430; otherwise straight-line proxy from that gauge |
| 02335000     |                          12.2  |                           14.8 |                     6.1  |             1.465 |   0.397 |   0.282 |                        0.649 |      0.853 |                  0.043 |                 0.853 | donor_dominated       |                         0.027 | acf30_divided_by_training_period_observed_temperature_range |                                  2 | Upper--Middle Chattahoochee |               2 | CHATTAHOOCHEE RIVER NEAR NORCROSS, GA              | downstream re-equilibration reach | 21.432            | USGS 0.366 km for 02334430; otherwise straight-line proxy from that gauge |
| 02335450     |                          13.2  |                           18   |                     7.9  |             1.772 |   0.377 |   0.276 |                        0.687 |      0.913 |                  0.027 |                 0.913 | donor_dominated       |                         0.021 | acf30_divided_by_training_period_observed_temperature_range |                                  3 | Upper--Middle Chattahoochee |               3 | CHATTAHOOCHEE RIVER ABOVE ROSWELL, GA              | downstream re-equilibration reach | 29.325            | USGS 0.366 km for 02334430; otherwise straight-line proxy from that gauge |
| 02336000     |                          19.2  |                           23.7 |                    13    |             2.219 |   0.304 |   0.236 |                        0.79  |      0.925 |                  0.019 |                 0.925 | donor_dominated       |                         0.013 | acf30_divided_by_training_period_observed_temperature_range |                                  4 | Upper--Middle Chattahoochee |               4 | CHATTAHOOCHEE RIVER AT ATLANTA, GA                 | downstream re-equilibration reach | 48.279            | USGS 0.366 km for 02334430; otherwise straight-line proxy from that gauge |
| 02337170     |                          20.6  |                           24   |                    15    |             2.207 |   0.281 |   0.261 |                        0.837 |      0.868 |                  0.031 |                 0.868 | donor_dominated       |                         0.012 | acf30_divided_by_training_period_observed_temperature_range |                                  5 | Upper--Middle Chattahoochee |               5 | CHATTAHOOCHEE RIVER NEAR FAIRBURN, GA              | downstream re-equilibration reach | 78.521            | USGS 0.366 km for 02334430; otherwise straight-line proxy from that gauge |
*Table 1. Eight-station regulation fingerprint.. Fitting-period observed range, climatological range, anomaly variability and memory, donor and memory budget components, covariance type, within-network memory--range rank, station order, and dam context.*

## Table 2
| station_id   |   year |   annual_minimum_degC |   annual_maximum_degC |   annual_mean_degC |   annual_amplitude_degC |   n_days |
|:-------------|-------:|----------------------:|----------------------:|-------------------:|------------------------:|---------:|
| B1           |   2006 |                   1   |                  20.6 |             10.254 |                    19.6 |      365 |
| B1           |   2007 |                   1.6 |                  18   |              9.761 |                    16.4 |      365 |
| B1           |   2008 |                   0.6 |                  18.1 |              9.028 |                    17.5 |      366 |
| B1           |   2009 |                   0.1 |                  18.5 |              9.482 |                    18.4 |      365 |
| B1           |   2010 |                   0.4 |                  18.6 |              9.369 |                    18.2 |      365 |
| B1           |   2011 |                   1   |                  17.7 |              9.18  |                    16.7 |      365 |
| B1           |   2012 |                   1.1 |                  18.2 |              9.398 |                    17.1 |      366 |
| B1           |   2013 |                   0.2 |                  18.2 |              9.625 |                    18   |      365 |
| B1           |   2014 |                   1.4 |                  18   |              9.282 |                    16.6 |      365 |
| B1           |   2015 |                   1   |                  18.4 |              9.633 |                    17.4 |      365 |
| B1           |   2016 |                   1.1 |                  18.6 |              9.956 |                    17.5 |      366 |
| B1           |   2017 |                   1.8 |                  18.5 |              9.858 |                    16.7 |      365 |
| B1           |   2018 |                   1.6 |                  17.7 |              9.895 |                    16.1 |      365 |
| B1           |   2019 |                   1.6 |                  18.6 |              9.792 |                    17   |      365 |
| B1           |   2020 |                   1.5 |                  18.1 |              9.759 |                    16.6 |      366 |
| S2           |   2006 |                   5.2 |                  20.5 |             12.706 |                    15.3 |      365 |
| S2           |   2007 |                   5.4 |                  19.5 |             12.613 |                    14.1 |      365 |
| S2           |   2008 |                   6   |                  18.5 |             12.064 |                    12.5 |      366 |
| S2           |   2009 |                   4.8 |                  20.3 |             12.677 |                    15.5 |      365 |
| S2           |   2010 |                   4.6 |                  19.9 |             12.378 |                    15.3 |      365 |
| S2           |   2011 |                   4.8 |                  19.3 |             12.294 |                    14.5 |      365 |
| S2           |   2012 |                   4.8 |                  19.7 |             12.133 |                    14.9 |      366 |
| S2           |   2013 |                   4.8 |                  19.7 |             12.253 |                    14.9 |      365 |
| S2           |   2014 |                   4.6 |                  19.3 |             12.304 |                    14.7 |      365 |
| S2           |   2015 |                   4   |                  19.6 |             12.65  |                    15.6 |      365 |
| S2           |   2016 |                   4.2 |                  19.3 |             12.539 |                    15.1 |      366 |
| S2           |   2017 |                   5   |                  19   |             12.486 |                    14   |      365 |
| S2           |   2018 |                   4.5 |                  19.1 |             12.422 |                    14.6 |      365 |
| S2           |   2019 |                   4   |                  19.5 |             12.293 |                    15.5 |      365 |
| S2           |   2020 |                   5   |                  18.9 |             12.417 |                    13.9 |      366 |
| P3           |   2006 |                   9.5 |                  23   |             16.494 |                    13.5 |      365 |
| P3           |   2007 |                   9.7 |                  22.6 |             16.264 |                    12.9 |      365 |
| P3           |   2008 |                   9.9 |                  21.6 |             15.81  |                    11.7 |      366 |
| P3           |   2009 |                   9.1 |                  22.2 |             16.219 |                    13.1 |      365 |
| P3           |   2010 |                   8.7 |                  22.8 |             16.135 |                    14.1 |      365 |
| P3           |   2011 |                   9.3 |                  21.6 |             16.173 |                    12.3 |      365 |
| P3           |   2012 |                  10.3 |                  22   |             16.048 |                    11.7 |      366 |
| P3           |   2013 |                   9.7 |                  22.9 |             16.696 |                    13.2 |      365 |
| P3           |   2014 |                   9.6 |                  23.2 |             16.946 |                    13.6 |      365 |
| P3           |   2015 |                  12.4 |                  23.1 |             17.832 |                    10.7 |      365 |
| P3           |   2016 |                  12   |                  22.3 |             17.508 |                    10.3 |      366 |
| P3           |   2017 |                  12.5 |                  22.3 |             17.438 |                     9.8 |      365 |
| P3           |   2018 |                  11.8 |                  22.4 |             16.81  |                    10.6 |      365 |
| P3           |   2019 |                  11.5 |                  21.8 |             16.642 |                    10.3 |      365 |
| P3           |   2020 |                  12.5 |                  22.1 |             17.689 |                     9.6 |      366 |
*Table 2. Annual Upper Jinsha thermal statistics.. Minimum, maximum, mean, and amplitude in degrees C for every station and year, 2006--2020.*

## Table 3
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
*Table 3. Frozen and stationarity-controlled covariance-heuristic evaluation.. Prediction correlation, mean absolute skill error, point exceedance count, and lower-confidence-bound exceedance count by station. The 2016--2017 and 2016--2020 rows are post-freeze diagnostics.*

## Table 4
| station_id   |   gap_length | validation_selected_model   |   validation_mean_MAE |   mean_skill |   skill_ci_lower |   skill_ci_upper |   mean_MAE_degC |   mean_climatology_MAE_degC | statistical_frontier_days   | statistical_frontier_censoring   |   n_anchors |   n_anchor_year_units |
|:-------------|-------------:|:----------------------------|----------------------:|-------------:|-----------------:|-----------------:|----------------:|----------------------------:|:----------------------------|:---------------------------------|------------:|----------------------:|
| B1           |           30 | xgboost                     |                 0.446 |        0.194 |            0.097 |            0.264 |           0.517 |                       0.757 | 365.0                       | right                            |          20 |                    20 |
| B1           |           90 | xgboost                     |                 0.446 |        0.198 |            0.07  |            0.227 |           0.502 |                       0.699 | 365.0                       | right                            |          20 |                    20 |
| B1           |          180 | xgboost                     |                 0.446 |        0.225 |            0.084 |            0.291 |           0.518 |                       0.718 | 365.0                       | right                            |          20 |                    20 |
| P3           |           30 | kalman                      |                 0.458 |        0.58  |            0.477 |            0.638 |           0.364 |                       1.306 | 159.992                     | undefined                        |          20 |                    20 |
| P3           |           90 | kalman                      |                 0.458 |        0.479 |            0.421 |            0.511 |           0.48  |                       1.296 | 159.992                     | undefined                        |          20 |                    20 |
| P3           |          180 | kalman                      |                 0.458 |       -0.045 |           -0.136 |            0.139 |           1.119 |                       1.218 | 159.992                     | undefined                        |          20 |                    20 |
| S2           |           30 | donor_regression            |                 0.357 |        0.183 |            0.038 |            0.347 |           0.539 |                       0.674 | undefined                   | left                             |          20 |                    20 |
| S2           |           90 | donor_regression            |                 0.357 |        0.173 |            0.03  |            0.301 |           0.552 |                       0.674 | undefined                   | left                             |          20 |                    20 |
| S2           |          180 | donor_regression            |                 0.357 |        0.183 |           -0.02  |            0.394 |           0.539 |                       0.651 | undefined                   | left                             |          20 |                    20 |
*Table 4. Validation-selected recoverability in relative and absolute units.. One block-recovery model per station is selected on 2016--2017 validation data and reported at 30, 90, and 180 days in 2018--2020. Columns give validation MAE, mean skill and 95% interval, model and climatology MAE, statistical frontier/censoring, and anchor counts.*

## Table 5
| experiment   | mask_type       | layout             | outage_mode   | overlap_ratio   | pattern   |   window_length | training_protocol   | fit_split   | tuning_split   | evaluation_split   | validation_scope       | target_station_id   | station_id   | target   | model               | failed_station_id   |   full_network_value |   failed_value |   impact |   impact_ci_lower |   impact_ci_upper | value_metric   | impact_definition                                        | selection_population             | evidence_role                   | formal_evidence   | eventwise_oracle_selection   | full_network_selected_model_counts                                | failed_selected_model_counts                                        |   n_gap_lengths |   n_anchor_years |   n_events | reason    |
|:-------------|:----------------|:-------------------|:--------------|:----------------|:----------|----------------:|:--------------------|:------------|:---------------|:-------------------|:-----------------------|:--------------------|:-------------|:---------|:--------------------|:--------------------|---------------------:|---------------:|---------:|------------------:|------------------:|:---------------|:---------------------------------------------------------|:---------------------------------|:--------------------------------|:------------------|:-----------------------------|:------------------------------------------------------------------|:--------------------------------------------------------------------|----------------:|-----------------:|-----------:|:----------|
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | B1                  | B1           | T        | cross_fitted_policy | B1                  |                0.52  |          0.497 |   -0.023 |            -0.061 |             0.016 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"donor_regression":30,"pchip":10,"random_forest":32,"xgboost":8} | {"pchip":10,"random_forest":46,"xgboost":24}                        |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | B1                  | B1           | T        | cross_fitted_policy | P3                  |                0.52  |          0.507 |   -0.013 |            -0.04  |             0.016 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"donor_regression":30,"pchip":10,"random_forest":32,"xgboost":8} | {"donor_regression":70,"pchip":10}                                  |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | B1                  | B1           | T        | cross_fitted_policy | S2                  |                0.52  |          0.625 |    0.105 |             0.044 |             0.169 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"donor_regression":30,"pchip":10,"random_forest":32,"xgboost":8} | {"air_only":38,"climatology":10,"kalman":10,"linear":12,"pchip":10} |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | P3                  | P3           | T        | cross_fitted_policy | B1                  |                0.489 |          0.547 |    0.058 |             0.01  |             0.119 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"kalman":54,"linear":6,"xgboost":20}                             | {"donor_regression":12,"kalman":62,"linear":6}                      |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | P3                  | P3           | T        | cross_fitted_policy | P3                  |                0.489 |          0.5   |    0.011 |             0.005 |             0.018 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"kalman":54,"linear":6,"xgboost":20}                             | {"kalman":54,"linear":6,"xgboost":20}                               |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | P3                  | P3           | T        | cross_fitted_policy | S2                  |                0.489 |          0.543 |    0.054 |             0.012 |             0.113 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"kalman":54,"linear":6,"xgboost":20}                             | {"air_only":12,"kalman":62,"linear":6}                              |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | S2                  | S2           | T        | cross_fitted_policy | B1                  |                0.487 |          0.51  |    0.023 |            -0.017 |             0.06  | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"donor_regression":10,"kalman":4,"pchip":20,"xgboost":46}        | {"air_hydro":29,"climatology":11,"kalman":20,"pchip":20}            |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | S2                  | S2           | T        | cross_fitted_policy | P3                  |                0.487 |          0.482 |   -0.005 |            -0.039 |             0.025 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"donor_regression":10,"kalman":4,"pchip":20,"xgboost":46}        | {"kalman":20,"pchip":20,"random_forest":8,"xgboost":32}             |               4 |                3 |         80 | undefined |
| SCI_NET      | matched_network | matched_target_gap | hydro-only    | undefined       | T         |             368 | seen_length         | train       | validation     | development_test   | development_evaluation | S2                  | S2           | T        | cross_fitted_policy | S2                  |                0.487 |          0.494 |    0.007 |            -0.01  |             0.023 | MAE            | leave_one_anchor_year_out_cross_fitted_failed_minus_full | development_evaluation_cross_fit | post_hoc_non_oracle_sensitivity | False             | False                        | {"donor_regression":10,"kalman":4,"pchip":20,"xgboost":46}        | {"donor_regression":15,"kalman":15,"pchip":20,"random_forest":30}   |               4 |                3 |         80 | undefined |
*Table 5. Leave-one-year-out cross-fitted node importance.. Full- and failed-network cross-fitted MAE, failed-minus-full difference, 95% stratified bootstrap interval, selected-model counts, four gap lengths, and matched event count by target and failed station.*



# Figures

## Figure 1
![Figure 1](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_01.png){ width=95% }
*Figure 1. Study networks, monitoring stations, and regulating dams.. (a) Jinsha River case-study stations and Guanyinyan Dam. B1, S2, and P3 are separated by 463 and 558 river km; straight connecting segments indicate station order rather than the detailed river centerline. (b) Upper-to-Middle Chattahoochee sites from immediately below Buford Dam through the Atlanta reach. Station coordinates are documented inventory locations. The Guanyinyan symbol uses a cartographic RCC-dam coordinate; the scientific distance context is the official 27 river km to P3. Basemap © OpenStreetMap contributors.*

## Figure 2
![Figure 2](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_02.png){ width=95% }
*Figure 2. Reservoir-associated thermal structure across two networks.. (a) Annual minimum stream temperature and (b) annual amplitude at B1, S2, and P3; the dashed line marks first-unit generation at Guanyinyan on 20 December 2014 and shading covers commissioning. The line is engineering context, not an estimated change date; formal method-sensitive results are in Figure S1. (c) Fitting-period temperature range versus lag-30 anomaly autocorrelation. Squares are memory-dominated and circles donor-dominated. (d) Chattahoochee downstream profile. Range increases and memory decreases away from Buford Dam. These are observational associations, not a causal heat-budget attribution.*

## Figure 3
![Figure 3](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_03.png){ width=95% }
*Figure 3. Frozen covariance heuristic and post-hoc thermal-state control.. Best-roster-envelope climatology-relative skill and the train-only heuristic at B1, S2, and P3. Red/black use the original 2006--2015 calibration and denominator; blue re-scores fixed predictions and recalibrates the heuristic to 2016--2020. The blue analysis overlaps evaluated years and diagnoses nonstationarity; it is not predictive evidence. Shading is the 95% anchor/year bootstrap interval for the original descriptive envelope.*

## Figure 4
![Figure 4](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_04.png){ width=95% }
*Figure 4. Recoverability in relative and absolute units.. Top: climatology-relative skill for five representative stable methods. Values below -0.5 are clipped for readability. Bottom: the same methods' MAE in degrees C, with paired training-climatology MAE shown as a black dashed line. All methods use common artificial cells.*

## Figure 5
![Figure 5](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_05.png){ width=95% }
*Figure 5. Cross-fitted node importance.. Mean failed-minus-full MAE after each singleton station failure, faceted by target and averaged over 10-, 30-, 90-, and 180-day gaps. For every target, gap, and failure set, the model is selected using the other two evaluation years and scored on the held-out year. Error bars are 95% matched-anchor bootstrap intervals stratified by year. The analysis is a post-hoc non-oracle sensitivity, not independent confirmation or a causal station value.*

## Figure 6
![Figure 6](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_06.png){ width=95% }
*Figure 6. Held-out Chattahoochee fixed-model evaluation.. Mean 2021--2022 validation performance across all gaps and placements selected XGBoost at every site. (a) Solid curves score that fixed model on the single 2023--2025 placement; dashed curves are frozen train-only heuristic predictions. Error bars are plus or minus one XGBoost placement SD from 20 validation masks and are not confidence intervals for the held-out point. (b) Fitting-period anomaly memory versus fixed-model 180-day skill. Red identifies memory-dominated site 02334430 below Buford Dam. The best-roster envelope is omitted from the main figure because it selects on the scored cell.*

## Figure 7
![Figure 7](/home/lzq/workspace/parttime/stream-recoverability/figures/main/figure_07.png){ width=95% }
*Figure 7. Independently frozen United States regulation-panel test.. (a) Memory--range index by 2009 GAGES-II upstream-major-dam label for 335 eligible stations. (b) Frozen leave-one-aggregated-ecoregion-out ROC curve; the frozen primary pooled AUC is 0.407 and the cluster-bootstrap interval includes 0.5, so standalone national discrimination is not supported. A post-hoc within-fold diagnosis is reported in Text S15 and Table S8 and still finds no national skill. (c) Within regulated watersheds, median index declines across 0--5, 5--20, 20--50, and 50--100 km nearest-major-dam bins; whiskers show the interquartile range. The greater-than-100-km bin contains one station and is not interpreted. Results use the transport-limited panel after a frozen official API fallback.*

