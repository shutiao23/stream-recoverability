# Figure and table captions

## Main figures

**Figure 1. Study networks, monitoring stations, and regulating dams.** (a) Jinsha River case-study stations and Guanyinyan Dam. B1, S2, and P3 are separated by 463 and 558 river km; straight connecting segments indicate station order rather than the detailed river centerline. (b) Upper-to-Middle Chattahoochee sites from immediately below Buford Dam through the Atlanta reach. Station coordinates are documented inventory locations. The Guanyinyan symbol uses a cartographic RCC-dam coordinate; the scientific distance context is the official 27 river km to P3. Basemap © OpenStreetMap contributors.

**Figure 2. Reservoir-associated thermal structure across two networks.** (a) Annual minimum stream temperature and (b) annual amplitude at B1, S2, and P3; the dashed line marks first-unit generation at Guanyinyan on 20 December 2014 and shading covers commissioning. The line is engineering context, not an estimated change date; formal method-sensitive results are in Figure S1. (c) Fitting-period temperature range versus lag-30 anomaly autocorrelation. Squares are memory-dominated and circles donor-dominated. (d) Chattahoochee downstream profile. Range increases and memory decreases away from Buford Dam. These are observational associations, not a causal heat-budget attribution.

**Figure S1. P3 change-date sensitivity under serial dependence.** Daily fitting-period climatological anomalies and the Pettitt process, least-squares single-break score, 365-day residual-block bootstrap intervals, first-unit operation date, and annual endpoint series. Pettitt and least-squares dates differ; only the least-squares interval covers 20 December 2014.

**Figure 3. Frozen covariance heuristic and post-hoc thermal-state control.** Best-roster-envelope climatology-relative skill and the train-only heuristic at B1, S2, and P3. Red/black use the original 2006--2015 calibration and denominator; blue re-scores fixed predictions and recalibrates the heuristic to 2016--2020. The blue analysis overlaps evaluated years and diagnoses nonstationarity; it is not predictive evidence. Shading is the 95% anchor/year bootstrap interval for the original descriptive envelope.

**Figure 4. Recoverability in relative and absolute units.** Top: climatology-relative skill for five representative stable methods. Values below -0.5 are clipped for readability. Bottom: the same methods' MAE in degrees C, with paired training-climatology MAE shown as a black dashed line. All methods use common artificial cells.

**Figure 5. Cross-fitted node importance.** Mean failed-minus-full MAE after each singleton station failure, faceted by target and averaged over 10-, 30-, 90-, and 180-day gaps. For every target, gap, and failure set, the model is selected using the other two evaluation years and scored on the held-out year. Error bars are 95% matched-anchor bootstrap intervals stratified by year. The analysis is a post-hoc non-oracle sensitivity, not independent confirmation or a causal station value.

**Figure 6. Held-out Chattahoochee fixed-model evaluation.** Mean 2021--2022 validation performance across all gaps and placements selected XGBoost at every site. (a) Solid curves score that fixed model on the single 2023--2025 placement; dashed curves are frozen train-only heuristic predictions. Error bars are plus or minus one XGBoost placement SD from 20 validation masks and are not confidence intervals for the held-out point. (b) Fitting-period anomaly memory versus fixed-model 180-day skill. Red identifies memory-dominated site 02334430 below Buford Dam. The best-roster envelope is omitted from the main figure because it selects on the scored cell.

**Figure 7. Independently frozen United States regulation-panel test.** (a) Memory--range index by 2009 GAGES-II upstream-major-dam label for 335 eligible stations. (b) Frozen leave-one-aggregated-ecoregion-out ROC curve; the frozen primary pooled AUC is 0.407 and the cluster-bootstrap interval includes 0.5, so standalone national discrimination is not supported. A post-hoc within-fold diagnosis is reported in Text S15 and Table S8 and still finds no national skill. (c) Within regulated watersheds, median index declines across 0--5, 5--20, 20--50, and 50--100 km nearest-major-dam bins; whiskers show the interquartile range. The greater-than-100-km bin contains one station and is not interpreted. Results use the transport-limited panel after a frozen official API fallback.

## Main tables

**Table 1. Eight-station regulation fingerprint.** Fitting-period observed range, climatological range, anomaly variability and memory, donor and memory budget components, covariance type, within-network memory--range rank, station order, and dam context.

**Table 2. Annual Upper Jinsha thermal statistics.** Minimum, maximum, mean, and amplitude in degrees C for every station and year, 2006--2020.

**Table 3. Frozen and stationarity-controlled covariance-heuristic evaluation.** Prediction correlation, mean absolute skill error, point exceedance count, and lower-confidence-bound exceedance count by station. The 2016--2017 and 2016--2020 rows are post-freeze diagnostics.

**Table 4. Validation-selected recoverability in relative and absolute units.** One block-recovery model per station is selected on 2016--2017 validation data and reported at 30, 90, and 180 days in 2018--2020. Columns give validation MAE, mean skill and 95% interval, model and climatology MAE, statistical frontier/censoring, and anchor counts.

**Table 5. Leave-one-year-out cross-fitted node importance.** Full- and failed-network cross-fitted MAE, failed-minus-full difference, 95% stratified bootstrap interval, selected-model counts, four gap lengths, and matched event count by target and failed station.
