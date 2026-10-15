# P1 group 3 — one rule, three transfers (measurement contract, time, thermal)

Script `scripts/318_wrr_p1_transfer_measurement.py` (sha256 `7da3a42cae479a9f`), git `8eade30bbf`, wall time **66.9 s**.

Rule held fixed throughout: the Step-2 fitted risk score (`HistGradientBoostingRegressor`, quantile 0.9, on the GENERIC+SUPPORT decision-time feature set) against the jittered `longest_run` length rule, at 70 % retention and a 0.5 °C failure tolerance. Contrast is **risk − length in percentage points**; negative means the fitted score has the lower failure rate.

Step-2 protocol check on the development panel: -6.20 pp [-7.09, -5.35] against the published −6.20 pp.

## Verdict

**At 70 % retention the operational design does not change the ranking conclusion.** On the manuscript's headline protocol the contrast is -6.20 pp [-7.18, -5.36]; on the shared late block it is -6.77 pp [-7.81, -5.73] under leave-one-year-out and -6.84 pp [-7.71, -5.75] under past-to-future. The paired difference is -0.07 pp [-0.33, 0.24] and 0.21 pp [-0.16, 0.38] on the common-deploy-date split (-6.33 pp [-7.44, -5.19]).

**At the 5 % risk target the operational design does change what can be promised.** The past-to-future score keeps 40.1 more points of retention than the length rule (0.812 vs 0.412), but the target set on the earlier block is not preserved: the achieved evaluation-block false-admit rate is 5.93 % for the fitted score against the 5 % promise, versus 4.40 % for the length rule.

**Every measurement-contract class keeps the sign, at different magnitudes:** documented_daily_mean -5.60 pp [-6.46, -4.84] on 84 networks; project_aggregated_subdaily -8.36 pp [-10.68, -4.87] on 14 networks; non_daily_reference_reading -11.36 pp (no interval) on 2 networks; undocumented -4.93 pp [-7.62, -2.52] on 10 networks.

**Warm years are not a failure mode for the rule:** the Step-5 anomalous-year stratum gives -7.69 pp [-8.89, -6.70] among hot years and -5.34 pp [-6.57, -4.25] among ordinary years.

## (a) Measurement-contract strata

Classification source: explicit provider mapping of measurement_provenance_dictionary.csv, cross-checked against the P0-06 coverage table.

| population | stratum | providers | cases | networks | risk fail @70 | length fail @70 | contrast (pp) | 95 % CI | risk ret @5 % | length ret @5 % |
|---|---|---|---|---|---|---|---|---|---|---|
| development_oof | all_providers | arso;chmi;foen;gkd_bayern;lubw;nve_hydapi;rws_waterwebservices;syke;usgs | 40704 | 110 | 0.0304 | 0.0924 | -6.20 | [-7.17, -5.35] | 0.775 | 0.465 |
| development_oof | documented_daily_mean | foen;gkd_bayern;lubw;nve_hydapi;usgs | 30289 | 84 | 0.0237 | 0.0797 | -5.60 | [-6.46, -4.84] | 0.801 | 0.550 |
| development_oof | project_aggregated_subdaily | chmi;rws_waterwebservices | 6321 | 14 | 0.0705 | 0.1541 | -8.36 | [-10.68, -4.87] | 0.648 | 0.177 |
| development_oof | non_daily_reference_reading | syke | 705 | 2 | 0.0974 | 0.2110 | -11.36 | too few networks for an interval (n=2 < 5) | 0.596 | 0.186 |
| development_oof | undocumented | arso | 3389 | 10 | 0.0164 | 0.0658 | -4.93 | [-7.62, -2.52] | 0.871 | 0.496 |
| wave2_oof_secondary_exploratory | all_providers | hubeau;uk_ea;usgs | 13017 | 49 | 0.0187 | 0.0834 | -6.47 | [-7.44, -5.58] | 0.797 | 0.556 |
| wave2_oof_secondary_exploratory | documented_daily_mean | uk_ea;usgs | 12282 | 45 | 0.0161 | 0.0806 | -6.46 | [-7.37, -5.44] | 0.804 | 0.569 |
| wave2_oof_secondary_exploratory | project_aggregated_subdaily | hubeau | 735 | 4 | 0.0623 | 0.1634 | -10.12 | too few networks for an interval (n=4 < 5) | 0.665 | 0.273 |
| wave2_oof_secondary_exploratory | non_daily_reference_reading | — | 0 | 0 | — | — | — | no cases in this class in this population | — | — |
| wave2_oof_secondary_exploratory | undocumented | — | 0 | 0 | — | — | — | no cases in this class in this population | — | — |

Per-provider rows are in `measurement_strata.csv` (`group_type=provider`).

### Cross-check against the parallel P0-06 coverage table

`measurement_contract_crosscheck.csv` reports, per provider, the explicit class used here, the dictionary evidence, the P0-06 class (`statistic_class`) and its station-level class (`statistic_class_cross_check`).

- providers disagreeing with the P0-06 dictionary-derived class: **0** (full agreement)
- providers disagreeing with the P0-06 station-level cross-check column: **4** — chmi, foen, gkd_bayern, lubw
- the P0-06 coverage table is being rebuilt by a parallel workstream; the sha256 above is of the exact bytes read by this run, and the classes scored here come from the explicit mapping, not from that table
- this run's four-class mapping agrees with P0-06's dictionary-derived statistic_class for every provider present in the two panels
- P0-06's station-level cross-check column disagrees with the class used here for chmi, foen, gkd_bayern, lubw: that column carries them as undocumented/unverified while the dictionary documents either a daily mean or a project-derived daily mean. This is an internal P0-06 conservatism difference, not a difference in the classes scored here
- no station-level cross-check row exists in P0-06 for hubeau, uk_ea, usgs, so that column could not be checked for them

## (b) Time transfer: past-to-future vs the current leave-one-year-out protocol

How to read the four estimands: `matched_retention_70` holds retention fixed at 70 % inside the evaluation block (pure ranking power); `transferred_threshold_at_70` applies a cut chosen on the calibration block, so the achieved evaluation retention is *not* controlled; `threshold_at_5pct_risk_target` compares failure rates at each rule's own calibrated 5 % cut, which is near zero by construction whenever calibration and evaluation are the same rows; `retention_gain_at_5pct_risk_target` is the informative number there — how many more records the fitted score keeps at the shared target.

| protocol | evaluation | estimand | train/eval cases | risk ret. | length ret. | risk fail | length fail | contrast (pp) | 95 % CI |
|---|---|---|---|---|---|---|---|---|---|
| network_clustered_oof_current_headline | full development panel | matched_retention_70_in_eval_block | 40704/40704 | 0.700 | 0.700 | 0.0304 | 0.0924 | -6.20 | [-7.18, -5.36] |
| network_clustered_oof_current_headline | full development panel | transferred_threshold_at_70_calibration_retention | 40704/40704 | 0.700 | 0.700 | 0.0304 | 0.0924 | -6.20 | [-7.14, -5.41] |
| network_clustered_oof_current_headline | full development panel | threshold_at_5pct_risk_target_from_calibration_block | 40704/40704 | 0.775 | 0.465 | 0.0500 | 0.0500 | 0.00 | [-0.01, 0.01] |
| network_clustered_oof_current_headline | full development panel | retention_gain_at_5pct_risk_target_from_calibration_block | 40704/40704 | 0.775 | 0.465 | 0.0500 | 0.0500 | 30.97 | [24.51, 41.83] |
| within_panel_leave_one_year_out_current | full development panel | matched_retention_70_in_eval_block | 40704/40704 | 0.700 | 0.700 | 0.0258 | 0.0924 | -6.66 | [-7.63, -5.78] |
| within_panel_leave_one_year_out_current | full development panel | transferred_threshold_at_70_calibration_retention | 40704/40704 | 0.700 | 0.700 | 0.0258 | 0.0924 | -6.66 | [-7.63, -5.80] |
| within_panel_leave_one_year_out_current | full development panel | threshold_at_5pct_risk_target_from_calibration_block | 40704/40704 | 0.790 | 0.465 | 0.0500 | 0.0500 | 0.00 | [-0.01, 0.01] |
| within_panel_leave_one_year_out_current | full development panel | retention_gain_at_5pct_risk_target_from_calibration_block | 40704/40704 | 0.790 | 0.465 | 0.0500 | 0.0500 | 32.46 | [26.32, 43.43] |
| within_panel_leave_one_year_out_current | per_station_late_block | matched_retention_70_in_eval_block | 40704/16405 | 0.700 | 0.700 | 0.0256 | 0.0933 | -6.77 | [-7.81, -5.73] |
| within_panel_leave_one_year_out_current | per_station_late_block | transferred_threshold_at_70_calibration_retention | 40704/16405 | 0.706 | 0.698 | 0.0272 | 0.0930 | -6.58 | [-7.72, -5.39] |
| within_panel_leave_one_year_out_current | per_station_late_block | threshold_at_5pct_risk_target_from_calibration_block | 40704/16405 | 0.790 | 0.463 | 0.0489 | 0.0448 | 0.42 | [-0.49, 1.02] |
| within_panel_leave_one_year_out_current | per_station_late_block | retention_gain_at_5pct_risk_target_from_calibration_block | 40704/16405 | 0.790 | 0.463 | 0.0489 | 0.0448 | 32.67 | [25.60, 46.01] |
| past_to_future_per_station_60_40 | each station's last 40 % of complete years | matched_retention_70_in_eval_block | 24299/16405 | 0.700 | 0.700 | 0.0249 | 0.0933 | -6.84 | [-7.71, -5.75] |
| past_to_future_per_station_60_40 | each station's last 40 % of complete years | transferred_threshold_at_70_calibration_retention | 24299/16405 | 0.712 | 0.697 | 0.0273 | 0.0928 | -6.55 | [-7.63, -5.39] |
| past_to_future_per_station_60_40 | each station's last 40 % of complete years | threshold_at_5pct_risk_target_from_calibration_block | 24299/16405 | 0.812 | 0.412 | 0.0593 | 0.0440 | 1.53 | [0.10, 2.69] |
| past_to_future_per_station_60_40 | each station's last 40 % of complete years | retention_gain_at_5pct_risk_target_from_calibration_block | 24299/16405 | 0.812 | 0.412 | 0.0593 | 0.0440 | 40.05 | [27.97, 49.15] |
| past_to_future_global_calendar_60_40 | every case with year > 2018 | matched_retention_70_in_eval_block | 25460/15244 | 0.700 | 0.700 | 0.0245 | 0.0878 | -6.33 | [-7.44, -5.19] |
| past_to_future_global_calendar_60_40 | every case with year > 2018 | transferred_threshold_at_70_calibration_retention | 25460/15244 | 0.725 | 0.684 | 0.0285 | 0.0850 | -5.65 | [-6.84, -4.43] |
| past_to_future_global_calendar_60_40 | every case with year > 2018 | threshold_at_5pct_risk_target_from_calibration_block | 25460/15244 | 0.818 | 0.406 | 0.0520 | 0.0434 | 0.86 | [-0.44, 2.24] |
| past_to_future_global_calendar_60_40 | every case with year > 2018 | retention_gain_at_5pct_risk_target_from_calibration_block | 25460/15244 | 0.818 | 0.406 | 0.0520 | 0.0434 | 41.12 | [29.57, 50.53] |
| past_to_future_per_station_60_40 minus leave_one_year_out | per-station late block | delta_matched_retention_70 | /16405 | n/a | n/a | n/a | n/a | -0.07 | [-0.33, 0.24] |
| past_to_future_global_calendar_60_40 minus leave_one_year_out | per-station late block | delta_matched_retention_70 | /15244 | n/a | n/a | n/a | n/a | 0.21 | [-0.16, 0.38] |
| past_to_future_per_station_60_40 minus network_clustered_oof_current | per-station late block | delta_matched_retention_70 | /16405 | n/a | n/a | n/a | n/a | -0.20 | [-0.59, 0.17] |

## (c) Warm-year strata

Hot/ordinary flags come from the project's own station-year exceedance columns (`truth_exceed_18`, `truth_exceed_20`) and from the Step-5 anomalous-year rule (`truth_hottest30 - clim_peak >= 1 °C`). Shares are of cases and of station-years. The within-station tercile definitions sit on an integer day count, so ties at the two-thirds quantile put more than a third of cases in the hot arm; the achieved shares are reported rather than assumed.

| definition | stratum | share of cases | share of station-years | cases | networks | contrast (pp) | 95 % CI |
|---|---|---|---|---|---|---|---|
| anomalous_warm_hottest30_minus_clim_peak_ge_1C | hot | 0.349 | 0.349 | 14198 | 104 | -7.69 | [-8.89, -6.70] |
| anomalous_warm_hottest30_minus_clim_peak_ge_1C | ordinary | 0.651 | 0.651 | 26506 | 110 | -5.34 | [-6.57, -4.25] |
| hot18_abs_ge_60d | hot | 0.477 | 0.472 | 19436 | 84 | -5.84 | [-6.76, -4.81] |
| hot18_abs_ge_60d | ordinary | 0.523 | 0.528 | 21268 | 81 | -6.58 | [-7.91, -5.57] |
| hot20_abs_ge_30d | hot | 0.428 | 0.422 | 17440 | 84 | -5.94 | [-6.97, -4.89] |
| hot20_abs_ge_30d | ordinary | 0.572 | 0.578 | 23264 | 84 | -6.49 | [-7.75, -5.48] |
| hot18_station_top_tercile | hot | 0.481 | 0.481 | 19561 | 110 | -6.78 | [-7.87, -5.69] |
| hot18_station_top_tercile | ordinary | 0.519 | 0.519 | 21143 | 95 | -5.70 | [-7.12, -4.59] |
| hot20_station_top_tercile | hot | 0.570 | 0.572 | 23211 | 110 | -7.13 | [-8.14, -6.10] |
| hot20_station_top_tercile | ordinary | 0.430 | 0.428 | 17493 | 91 | -4.99 | [-6.64, -3.75] |

## Event labels: what exists and what does not

- `private/gems_reviewer_bundle/data/processed/event_labels.parquet` — labelled daily panel with high_temperature and heatwave_min_3d columns. station ids are the anonymised GEMS benchmark ids, not river-temperature station ids, and the labelled variables are air temperature T and flow F; it cannot label a station-year of the WRR panel
- `results/wrr_revision/step5_failures/fault_scores.csv` — gap-segment diagnostic with a derived 'heatwave_fraction' column (share of gap days above the station's training 90th percentile of daily temperature). it is a derived warm-day overlap computed by the project, not a provider or third-party event label, and it does not identify heatwave episodes

No true heatwave/event label exists for the river-temperature panel. The only labelled event file in the repository is the anonymised GEMS benchmark panel. The thermal strata below are therefore warm-year strata and must not be read as an event-scale heatwave analysis.

## What this does and does not license

- the case table's reconstructor features were built under fit_protocol=leave_one_year_out, so the time-transfer rows are honest for the risk score's training block but remain an upper bound on a strictly prior-years deployment
- wave-2 rows are exploratory and do not retune or replace the wave-2 seal, which belongs to the frozen multi-method certificate screen
- no true heatwave event labels exist for this panel, so thermal strata are warm-year strata
- threshold-transfer intervals resample networks inside the calibration block as well as the evaluation block, so they carry threshold uncertainty as well as evaluation uncertainty

The repository's existing strictly-prior-years sensitivity (certificate screen, `results/v17_fitness/step13_prior_years/protocol_comparison.csv`) is the closest prior art to the time-transfer design here; it is quoted verbatim in `protocol_fingerprint.json` and was not re-run. Those rows score the frozen *certificate* screen, not the fitted risk score, so they are not directly comparable to the fitted-score contrasts above.

