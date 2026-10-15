# P0-03 — the final admission rule on the monitoring-calendar replay

`scripts/312_wrr_p0_03_final_method_replay.py` (sha256 `091dacad26794f3b…`), git HEAD `8eade30bbf5f82b9af3b7900de81e52707e8af47`, runtime 185.9 s, generated 2026-10-15T11:07:29.251320+00:00.

## 1. What was replayed, and on how many units

- **418 candidate groups** (14 networks, 22 stations, {'source_gap_run': 241, 'source_calendar_union': 177}); **1254 candidate-level rows** are implied by the three co-failure levels, but the levels are repeated measures on the same group and are stored as suffixed columns of one row: the number of experiments is the number of groups, **not** groups x 3.
- cross-year groups (gap placed on the continuous multi-year axis and evaluated in both affected calendar years): **22**.
- gap-length assertions: **pass** (418 groups, 18 cross-year pairs).
- co-failure levels: target_only (0.0), partial_donor_failure (0.5), all_donor_failure (1.0) donors masked with the target calendar.
- co-failure realisation: {"target_only": {"mean_donors_cofailed": 0.0, "median_donors_cofailed": 0.0, "min_donors_cofailed": 0, "max_donors_cofailed": 0, "mean_visible_donors": 2.272727272727273, "share_zero_visible_donors": 0.019138755980861243, "share_strict_partial": NaN}, "partial_donor_failure": {"mean_donors_cofailed": 1.507177033492823, "median_donors_cofailed": 2.0, "min_donors_cofailed": 1, "max_donors_cofailed": 2, "mean_visible_donors": 0.8899521531100478, "share_zero_visible_donors": 0.18660287081339713, "share_strict_partial": 0.8708133971291866}, "all_donor_failure": {"mean_donors_cofailed": 2.471291866028708, "median_donors_cofailed": 3.0, "min_donors_cofailed": 1, "max_donors_cofailed": 5, "mean_visible_donors": 0.0, "share_zero_visible_donors": 1.0, "share_strict_partial": NaN}}; 54 of 418 groups have a single donor, and for those the 'partial' level necessarily co-fails that donor and reproduces the all-donor condition (the strict-partial share is reported above);
- placement reduction: at most 4 longest runs per source year per station, at most 4 source years per station, at most 3 target anchor years per source year, at most 2 stations per network; every method scores every candidate in the resulting pool (no per-method sub-sampling).

## 2. Threshold paths actually used

- the parallel workstream file exists: **True** (`results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds/final_admission_thresholds.json`, sha256 `c7033a61d7ba5ae7…`, scripts/311_wrr_p0_02_frozen_risk_thresholds.py).
- its `calibrated_bound` thresholds live in the units of `results/v17_fitness/step6_screen/development_certificates.parquet`.  That table cannot be reproduced with the current `screen.py`: on its fold 0 the maximum absolute bound difference is **1.2031796926834244 °C** and only **0.7912109375** of the certificate choices agree, so numerically transferring its threshold into this script's bounds is not sound (the code changed after the table was built).  The literal transfer is nevertheless reported as the labelled secondary row `final_rule_literal_p002_tau`.
- **primary path**: the p0_02 pre-registered *rule* (largest calibration retention in a 0.10..0.95 grid whose calibration false-admit rate plus a one-sided 95 % network-clustered bootstrap upper bound is <= 5 %; admit iff score <= threshold; if nothing qualifies, admit nothing) re-implemented in these units, with a per-held-out-network three-way network-disjoint split of the labelled corpus (65 networks for the certificate heads / 22 for the conformal scale / 22 for the threshold); the held-out network is in none of them.
- the two simple rules **do** consume the parallel workstream's frozen per-fold thresholds ({"length_rule": {"0": 30.87809571665732, "1": 30.560995989441253, "2": 30.51846681073136, "3": 30.858153810778685, "4": 30.82699631661753}, "peak_window_rule": {"0": 0.5006144682598739, "1": 0.500734552138818, "2": 0.5001706866859715, "3": 0.4674299640898077, "4": 0.5007172127221903}}) because their units (days, peak-window share) are transferable; the published fixed limits (49 d, 140 d, 10 % overlap) are reported next to them as secondary rows.
- primary thresholds per held-out network: {"chmi_morava": 0.4601, "gkd_bayern_iller": 0.6961, "huc8_03110206": 0.7053, "nve_basin_26": 0.6743, "nve_basin_88": 0.4221, "usgs2_huc2_08": 0.6577, "usgs2_huc2_15": 0.7194, "usgs2_huc4_0601": 0.6191, "usgs2_huc4_1901": 0.6107, "usgs2_huc6_020502": 0.6275, "usgs2_huc6_070900": 0.5513, "usgs2_huc6_071300": 0.5449, "usgs2_huc6_120301": 0.5388, "usgs2_huc6_180400": 0.5476}
- no replay label entered threshold selection; `truth_invariance_verified` = True.

## 3. Failure modes and error, per method and per co-failure level

All shares below are over the same candidate pool (denominator = 418 groups, one row per group, levels as repeated measures).

         cofail_level                      method  n_candidates  n_groups  n_networks  n_decided  decided_share  usable_share  strict_ok_share  consequential_error_rate_among_available  mean_abserr_among_available  consequential_error_rate_over_all_candidates  share_mode_degenerate_donor  share_mode_observed_window_only  share_mode_abstain
          target_only                  final_rule           418       418          14        390       0.933014      0.933014         0.933014                                  0.010256                     0.025442                                      0.076555                     0.043062                         0.000000            0.023923
          target_only               final_rule_fb           418       418          14        402       0.961722      0.961722         0.933014                                  0.014925                     0.034589                                      0.052632                     0.000000                         0.028708            0.038278
          target_only       final_rule_point_risk           418       418          14        393       0.940191      0.940191         0.940191                                  0.015267                     0.029124                                      0.074163                     0.043062                         0.000000            0.016746
          target_only final_rule_literal_p002_tau           418       418          14        390       0.933014      0.933014         0.933014                                  0.007692                     0.023906                                      0.074163                     0.043062                         0.000000            0.023923
          target_only            peak_window_rule           418       418          14        394       0.942584      0.942584         0.942584                                  0.007614                     0.029089                                      0.064593                     0.000000                         0.000000            0.057416
          target_only                 length_rule           418       418          14        325       0.777512      0.777512         0.777512                                  0.000000                     0.023281                                      0.222488                     0.000000                         0.000000            0.222488
          target_only      peak_window_rule_pub10           418       418          14        334       0.799043      0.799043         0.799043                                  0.000000                     0.012372                                      0.200957                     0.000000                         0.000000            0.200957
          target_only           length_rule_pub49           418       418          14        382       0.913876      0.913876         0.913876                                  0.007853                     0.029281                                      0.093301                     0.000000                         0.000000            0.086124
          target_only          length_rule_pub140           418       418          14        409       0.978469      0.978469         0.978469                                  0.017115                     0.043704                                      0.038278                     0.000000                         0.000000            0.021531
          target_only            donor_ridge_path           418       418          14        368       0.880383      0.880383         0.880383                                  0.013587                     0.039619                                      0.131579                     0.119617                         0.000000            0.000000
          target_only          observed_days_path           418       418          14        412       0.985646      0.985646         0.000000                                  0.072816                     0.183026                                      0.086124                     0.000000                         0.985646            0.014354
          target_only            frozen_cert_rule           418       418          14        387       0.925837      0.925837         0.925837                                  0.007752                     0.026407                                      0.081340                     0.055024                         0.000000            0.019139
partial_donor_failure                  final_rule           418       418          14        395       0.944976      0.944976         0.944976                                  0.005063                     0.021872                                      0.059809                     0.000000                         0.000000            0.055024
partial_donor_failure               final_rule_fb           418       418          14        395       0.944976      0.944976         0.944976                                  0.005063                     0.021872                                      0.059809                     0.000000                         0.000000            0.055024
partial_donor_failure       final_rule_point_risk           418       418          14        400       0.956938      0.956938         0.956938                                  0.010000                     0.025957                                      0.052632                     0.000000                         0.000000            0.043062
partial_donor_failure final_rule_literal_p002_tau           418       418          14        396       0.947368      0.947368         0.947368                                  0.005051                     0.021817                                      0.057416                     0.000000                         0.000000            0.052632
partial_donor_failure            peak_window_rule           418       418          14        394       0.942584      0.942584         0.942584                                  0.005076                     0.032341                                      0.062201                     0.000000                         0.000000            0.057416
partial_donor_failure                 length_rule           418       418          14        325       0.777512      0.777512         0.777512                                  0.000000                     0.026289                                      0.222488                     0.000000                         0.000000            0.222488
partial_donor_failure      peak_window_rule_pub10           418       418          14        334       0.799043      0.799043         0.799043                                  0.000000                     0.014206                                      0.200957                     0.000000                         0.000000            0.200957
partial_donor_failure           length_rule_pub49           418       418          14        382       0.913876      0.913876         0.913876                                  0.005236                     0.032255                                      0.090909                     0.000000                         0.000000            0.086124
partial_donor_failure          length_rule_pub140           418       418          14        409       0.978469      0.978469         0.978469                                  0.014670                     0.047941                                      0.035885                     0.000000                         0.000000            0.021531
partial_donor_failure            donor_ridge_path           418       418          14        320       0.765550      0.765550         0.765550                                  0.021875                     0.056959                                      0.251196                     0.234450                         0.000000            0.000000
partial_donor_failure          observed_days_path           418       418          14        412       0.985646      0.985646         0.000000                                  0.072816                     0.183026                                      0.086124                     0.000000                         0.985646            0.014354
partial_donor_failure            frozen_cert_rule           418       418          14        397       0.949761      0.949761         0.949761                                  0.010076                     0.024893                                      0.059809                     0.000000                         0.000000            0.050239
    all_donor_failure                  final_rule           418       418          14        395       0.944976      0.944976         0.944976                                  0.005063                     0.022792                                      0.059809                     0.000000                         0.000000            0.055024
    all_donor_failure               final_rule_fb           418       418          14        395       0.944976      0.944976         0.944976                                  0.005063                     0.022792                                      0.059809                     0.000000                         0.000000            0.055024
    all_donor_failure       final_rule_point_risk           418       418          14        401       0.959330      0.959330         0.959330                                  0.009975                     0.028139                                      0.050239                     0.000000                         0.000000            0.040670
    all_donor_failure final_rule_literal_p002_tau           418       418          14        396       0.947368      0.947368         0.947368                                  0.005051                     0.022735                                      0.057416                     0.000000                         0.000000            0.052632
    all_donor_failure            peak_window_rule           418       418          14        394       0.942584      0.942584         0.942584                                  0.010152                     0.026468                                      0.066986                     0.000000                         0.000000            0.057416
    all_donor_failure                 length_rule           418       418          14        325       0.777512      0.777512         0.777512                                  0.000000                     0.015498                                      0.222488                     0.000000                         0.000000            0.222488
    all_donor_failure      peak_window_rule_pub10           418       418          14        334       0.799043      0.799043         0.799043                                  0.000000                     0.006084                                      0.200957                     0.000000                         0.000000            0.200957
    all_donor_failure           length_rule_pub49           418       418          14        382       0.913876      0.913876         0.913876                                  0.010471                     0.027148                                      0.095694                     0.000000                         0.000000            0.086124
    all_donor_failure          length_rule_pub140           418       418          14        409       0.978469      0.978469         0.978469                                  0.024450                     0.039869                                      0.045455                     0.000000                         0.000000            0.021531
    all_donor_failure            donor_ridge_path           418       418          14          0       0.000000      0.000000         0.000000                                       NaN                          NaN                                      1.000000                     1.000000                         0.000000            0.000000
    all_donor_failure          observed_days_path           418       418          14        412       0.985646      0.985646         0.000000                                  0.072816                     0.183026                                      0.086124                     0.000000                         0.985646            0.014354
    all_donor_failure            frozen_cert_rule           418       418          14        403       0.964115      0.964115         0.964115                                  0.019851                     0.033180                                      0.055024                     0.000000                         0.000000            0.035885

### 3b. Estimator-level availability (donor reconstruction is never substituted)

         cofail_level              estimator  n_candidates  n_available  available_share  consequential_error_rate_among_available  mean_abserr_among_available  consequential_error_rate_over_all_candidates
          target_only        doy_climatology           418          418         1.000000                                  0.040670                 7.464103e-02                                      0.040670
          target_only     smooth_climatology           418          418         1.000000                                  0.043062                 7.361386e-02                                      0.043062
          target_only          linear_interp           418          366         0.875598                                  0.038251                 7.263221e-02                                      0.157895
          target_only              air_ridge           418           12         0.028708                                  0.000000                 1.184238e-15                                      0.971292
          target_only          observed_days           418          412         0.985646                                  0.072816                 1.830257e-01                                      0.086124
          target_only observed_strict_window           418          412         0.985646                                  0.135922                 2.386579e-01                                      0.148325
          target_only            donor_ridge           418          368         0.880383                                  0.013587                 3.961855e-02                                      0.131579
partial_donor_failure        doy_climatology           418          418         1.000000                                  0.040670                 7.464103e-02                                      0.040670
partial_donor_failure     smooth_climatology           418          418         1.000000                                  0.043062                 7.361386e-02                                      0.043062
partial_donor_failure          linear_interp           418          366         0.875598                                  0.038251                 7.263221e-02                                      0.157895
partial_donor_failure              air_ridge           418           12         0.028708                                  0.000000                 1.184238e-15                                      0.971292
partial_donor_failure          observed_days           418          412         0.985646                                  0.072816                 1.830257e-01                                      0.086124
partial_donor_failure observed_strict_window           418          412         0.985646                                  0.135922                 2.386579e-01                                      0.148325
partial_donor_failure            donor_ridge           418          320         0.765550                                  0.021875                 5.695892e-02                                      0.251196
    all_donor_failure        doy_climatology           418          418         1.000000                                  0.040670                 7.464103e-02                                      0.040670
    all_donor_failure     smooth_climatology           418          418         1.000000                                  0.043062                 7.361386e-02                                      0.043062
    all_donor_failure          linear_interp           418          366         0.875598                                  0.038251                 7.263221e-02                                      0.157895
    all_donor_failure              air_ridge           418           12         0.028708                                  0.000000                 1.184238e-15                                      0.971292
    all_donor_failure          observed_days           418          412         0.985646                                  0.072816                 1.830257e-01                                      0.086124
    all_donor_failure observed_strict_window           418          412         0.985646                                  0.135922                 2.386579e-01                                      0.148325
    all_donor_failure            donor_ridge           418            0         0.000000                                       NaN                          NaN                                      1.000000

### 3c. What the old donor column actually contained (F04)

         cofail_level  cofail_fraction  n_candidate_level_rows  n_donor_available  n_donor_unavailable  share_donor_unavailable  n_no_donor_model_formed  n_old_probe_would_report_a_number  share_of_degenerate_where_old_probe_reported_a_number  mean_abserr_old_probe_reported_as_donor_ridge  mean_abserr_labelled_observed_days_on_degenerate  mean_abserr_donor_when_available  n_rows_where_chosen_estimator_was_donor_ridge_but_unavailable  n_rows_where_strict_rule_abstained  n_rows_where_labelled_fallback_was_used
          target_only              0.0                     418                368                   50                 0.119617                        8                                 46                                               0.920000                                       0.716598                                          0.609895                          0.039619                                                             18                                  10                                       12
partial_donor_failure              0.5                     418                320                   98                 0.234450                       78                                 95                                               0.969388                                       0.244792                                          0.195335                          0.056959                                                              0                                  23                                        0
    all_donor_failure              1.0                     418                  0                  418                 1.000000                      418                                412                                               0.985646                                       0.238658                                          0.183026                               NaN                                                              0                                  23                                        0

## 4. Degenerate-donor accounting

- cases where the donor reconstructor could not be formed: {"target_only": {"donor_ridge_path": 50, "final_rule": 18, "final_rule_abstain": 10, "final_rule_fb_observed_window_only": 12}, "partial_donor_failure": {"donor_ridge_path": 98, "final_rule": 0, "final_rule_abstain": 23, "final_rule_fb_observed_window_only": 0}, "all_donor_failure": {"donor_ridge_path": 418, "final_rule": 0, "final_rule_abstain": 23, "final_rule_fb_observed_window_only": 0}}
- the strict final rule treats them as **not admitted** (`degenerate_donor`); the donor estimate stays NaN and is never replaced by a hottest fully observed window;
- the labelled fallback variant `final_rule_fb` reports them as `observed_window_only`, i.e. the incumbent `observed_days` estimator named as itself; the donor rows and the observed-window rows are never merged;
- degenerate-donor rows whose certificate pick was `donor_ridge` but whose estimate could not be formed: [18, 0, 0] (('target_only', 'partial_donor_failure', 'all_donor_failure'));
- the old probe would have reported a hottest fully observed window mean under the donor name for [46, 95, 412] of [50, 98, 418] donor-unavailable rows, at mean |error| [0.7166, 0.2448, 0.2387] C, against a true donor error of [0.0396, 0.057, nan] C on the rows where donors were available.

## 5. Final rule vs the simple rules (network-clustered bootstrap)

Absolute admission (each rule at its own frozen / calibrated threshold):

                level                        statistic_label                                  contrast  point_pp  ci_low_pp  ci_high_pp  n_clusters  draws  excludes_zero_95
    all_donor_failure                admissible_record_share  final_rule__minus__final_rule_point_risk    -0.957     -2.659       0.000          14   2000             False
    all_donor_failure                admissible_record_share            final_rule__minus__length_rule    16.268      9.762      24.253          14   2000              True
    all_donor_failure                admissible_record_share      final_rule__minus__length_rule_pub49     3.589      0.000       9.327          14   2000             False
    all_donor_failure                admissible_record_share       final_rule__minus__peak_window_rule     0.718      0.000       1.418          14   2000             False
    all_donor_failure                admissible_record_share final_rule__minus__peak_window_rule_pub10    14.115      6.687      19.919          14   2000              True
    all_donor_failure                admissible_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
    all_donor_failure                admissible_record_share    final_rule_fb__minus__peak_window_rule     0.718      0.000       1.402          14   2000             False
    all_donor_failure                admissible_record_share      peak_window_rule__minus__length_rule    15.550      9.322      22.826          14   2000              True
    all_donor_failure consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk    -0.491     -1.940       0.000          14   2000             False
    all_donor_failure consequential_error_rate_among_decided            final_rule__minus__length_rule     0.506      0.000       2.174          14   2000             False
    all_donor_failure consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49    -0.541     -1.237       0.000          14   2000             False
    all_donor_failure consequential_error_rate_among_decided       final_rule__minus__peak_window_rule    -0.509     -1.193       0.000          14   2000             False
    all_donor_failure consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     0.506      0.000       2.083          14   2000             False
    all_donor_failure consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
    all_donor_failure consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule    -0.509     -1.183       0.000          14   2000             False
    all_donor_failure consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     1.015      0.000       2.537          14   2000             False
    all_donor_failure                        strict_ok_share  final_rule__minus__final_rule_point_risk    -1.435     -4.348       0.000          14   2000             False
    all_donor_failure                        strict_ok_share            final_rule__minus__length_rule    16.746     10.022      24.562          14   2000              True
    all_donor_failure                        strict_ok_share      final_rule__minus__length_rule_pub49     3.110      0.000       9.059          14   2000             False
    all_donor_failure                        strict_ok_share       final_rule__minus__peak_window_rule     0.239      0.000       0.809          14   2000             False
    all_donor_failure                        strict_ok_share final_rule__minus__peak_window_rule_pub10    14.593      7.158      20.467          14   2000              True
    all_donor_failure                        strict_ok_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
    all_donor_failure                        strict_ok_share    final_rule_fb__minus__peak_window_rule     0.239      0.000       0.850          14   2000             False
    all_donor_failure                        strict_ok_share      peak_window_rule__minus__length_rule    16.507      9.641      24.697          14   2000              True
    all_donor_failure                    usable_record_share  final_rule__minus__final_rule_point_risk    -1.435     -4.313       0.000          14   2000             False
    all_donor_failure                    usable_record_share            final_rule__minus__length_rule    16.746     10.395      25.263          14   2000              True
    all_donor_failure                    usable_record_share      final_rule__minus__length_rule_pub49     3.110      0.000       8.935          14   2000             False
    all_donor_failure                    usable_record_share       final_rule__minus__peak_window_rule     0.239      0.000       0.820          14   2000             False
    all_donor_failure                    usable_record_share final_rule__minus__peak_window_rule_pub10    14.593      7.395      20.664          14   2000              True
    all_donor_failure                    usable_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
    all_donor_failure                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.239      0.000       0.840          14   2000             False
    all_donor_failure                    usable_record_share      peak_window_rule__minus__length_rule    16.507      9.855      24.265          14   2000              True
partial_donor_failure                admissible_record_share  final_rule__minus__final_rule_point_risk    -0.718     -2.174       0.000          14   2000             False
partial_donor_failure                admissible_record_share            final_rule__minus__length_rule    16.268      9.893      24.176          14   2000              True
partial_donor_failure                admissible_record_share      final_rule__minus__length_rule_pub49     3.110      0.000       9.185          14   2000             False
partial_donor_failure                admissible_record_share       final_rule__minus__peak_window_rule     0.239      0.000       0.809          14   2000             False
partial_donor_failure                admissible_record_share final_rule__minus__peak_window_rule_pub10    14.115      6.919      19.806          14   2000              True
partial_donor_failure                admissible_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
partial_donor_failure                admissible_record_share    final_rule_fb__minus__peak_window_rule     0.239      0.000       0.817          14   2000             False
partial_donor_failure                admissible_record_share      peak_window_rule__minus__length_rule    16.029      9.638      23.621          14   2000              True
partial_donor_failure consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk    -0.494     -1.871       0.000          14   2000             False
partial_donor_failure consequential_error_rate_among_decided            final_rule__minus__length_rule     0.506      0.000       2.089          14   2000             False
partial_donor_failure consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49    -0.017     -0.122       0.000          14   2000             False
partial_donor_failure consequential_error_rate_among_decided       final_rule__minus__peak_window_rule    -0.001     -0.009       0.000          14   2000             False
partial_donor_failure consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     0.506      0.000       2.121          14   2000             False
partial_donor_failure consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
partial_donor_failure consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule    -0.001     -0.010       0.000          14   2000             False
partial_donor_failure consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     0.508      0.000       2.041          14   2000             False
partial_donor_failure                        strict_ok_share  final_rule__minus__final_rule_point_risk    -1.196     -4.143       0.000          14   2000             False
partial_donor_failure                        strict_ok_share            final_rule__minus__length_rule    16.746     10.169      24.437          14   2000              True
partial_donor_failure                        strict_ok_share      final_rule__minus__length_rule_pub49     3.110      0.000       8.696          14   2000             False
partial_donor_failure                        strict_ok_share       final_rule__minus__peak_window_rule     0.239      0.000       0.831          14   2000             False
partial_donor_failure                        strict_ok_share final_rule__minus__peak_window_rule_pub10    14.593      7.329      20.549          14   2000              True
partial_donor_failure                        strict_ok_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
partial_donor_failure                        strict_ok_share    final_rule_fb__minus__peak_window_rule     0.239      0.000       0.787          14   2000             False
partial_donor_failure                        strict_ok_share      peak_window_rule__minus__length_rule    16.507     10.144      24.700          14   2000              True
partial_donor_failure                    usable_record_share  final_rule__minus__final_rule_point_risk    -1.196     -4.001       0.000          14   2000             False
partial_donor_failure                    usable_record_share            final_rule__minus__length_rule    16.746      9.971      24.294          14   2000              True
partial_donor_failure                    usable_record_share      final_rule__minus__length_rule_pub49     3.110      0.000       8.667          14   2000             False
partial_donor_failure                    usable_record_share       final_rule__minus__peak_window_rule     0.239      0.000       0.796          14   2000             False
partial_donor_failure                    usable_record_share final_rule__minus__peak_window_rule_pub10    14.593      6.382      20.740          14   2000              True
partial_donor_failure                    usable_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
partial_donor_failure                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.239      0.000       0.790          14   2000             False
partial_donor_failure                    usable_record_share      peak_window_rule__minus__length_rule    16.507     10.192      24.192          14   2000              True
          target_only                admissible_record_share  final_rule__minus__final_rule_point_risk    -0.239     -0.827       0.000          14   2000             False
          target_only                admissible_record_share            final_rule__minus__length_rule    14.593      7.900      22.294          14   2000              True
          target_only                admissible_record_share      final_rule__minus__length_rule_pub49     1.675     -1.604       7.945          14   2000             False
          target_only                admissible_record_share       final_rule__minus__peak_window_rule    -1.196     -2.693       0.643          14   2000             False
          target_only                admissible_record_share final_rule__minus__peak_window_rule_pub10    12.440      6.319      17.706          14   2000              True
          target_only                admissible_record_share          final_rule_fb__minus__final_rule     2.392      0.602       4.592          14   2000              True
          target_only                admissible_record_share    final_rule_fb__minus__peak_window_rule     1.196      0.241       2.603          14   2000              True
          target_only                admissible_record_share      peak_window_rule__minus__length_rule    15.789      9.544      23.057          14   2000              True
          target_only consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk    -0.501     -2.066       0.003          14   2000             False
          target_only consequential_error_rate_among_decided            final_rule__minus__length_rule     1.026      0.000       3.637          14   2000             False
          target_only consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49     0.240     -0.424       1.579          14   2000             False
          target_only consequential_error_rate_among_decided       final_rule__minus__peak_window_rule     0.264     -0.402       1.580          14   2000             False
          target_only consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     1.026      0.000       3.604          14   2000             False
          target_only consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.467     -0.021       1.707          14   2000             False
          target_only consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule     0.731     -0.399       3.291          14   2000             False
          target_only consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     0.761      0.000       2.284          14   2000             False
          target_only                        strict_ok_share  final_rule__minus__final_rule_point_risk    -0.718     -2.229       0.000          14   2000             False
          target_only                        strict_ok_share            final_rule__minus__length_rule    15.550      8.010      24.504          14   2000              True
          target_only                        strict_ok_share      final_rule__minus__length_rule_pub49     1.914     -1.563       8.076          14   2000             False
          target_only                        strict_ok_share       final_rule__minus__peak_window_rule    -0.957     -2.586       1.791          14   2000             False
          target_only                        strict_ok_share final_rule__minus__peak_window_rule_pub10    13.397      6.325      19.702          14   2000              True
          target_only                        strict_ok_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   2000             False
          target_only                        strict_ok_share    final_rule_fb__minus__peak_window_rule    -0.957     -2.588       1.858          14   2000             False
          target_only                        strict_ok_share      peak_window_rule__minus__length_rule    16.507      9.443      24.343          14   2000              True
          target_only                    usable_record_share  final_rule__minus__final_rule_point_risk    -0.718     -2.105       0.000          14   2000             False
          target_only                    usable_record_share            final_rule__minus__length_rule    15.550      8.823      24.399          14   2000              True
          target_only                    usable_record_share      final_rule__minus__length_rule_pub49     1.914     -1.572       8.551          14   2000             False
          target_only                    usable_record_share       final_rule__minus__peak_window_rule    -0.957     -2.570       1.807          14   2000             False
          target_only                    usable_record_share final_rule__minus__peak_window_rule_pub10    13.397      6.885      19.738          14   2000              True
          target_only                    usable_record_share          final_rule_fb__minus__final_rule     2.871      1.058       5.238          14   2000              True
          target_only                    usable_record_share    final_rule_fb__minus__peak_window_rule     1.914      0.000       5.373          14   2000             False
          target_only                    usable_record_share      peak_window_rule__minus__length_rule    16.507      9.693      24.638          14   2000              True

The decision-relevant combination is `admissible_record_share` (a record the agency can use: produced and within 0.5 C).  `usable_record_share` counts produced records whatever their error; `consequential_error_rate_among_decided` is the precision of the cases each rule decides, with different denominators by construction.

Matched decision counts (forced-decision ranking view, abstention disallowed):

                level                        statistic_label                                  contrast  point_pp  ci_low_pp  ci_high_pp  n_clusters  draws  excludes_zero_95
    all_donor_failure consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided            final_rule__minus__length_rule     0.000     -4.705       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49     0.000     -0.386       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided       final_rule__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     0.000     -4.767       0.000          14   1000             False
    all_donor_failure                    usable_record_share  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share            final_rule__minus__length_rule     0.000      0.000       6.020          14   1000             False
    all_donor_failure                    usable_record_share      final_rule__minus__length_rule_pub49     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share       final_rule__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share final_rule__minus__peak_window_rule_pub10     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share      peak_window_rule__minus__length_rule     0.000      0.000       7.607          14   1000             False
partial_donor_failure consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided            final_rule__minus__length_rule     0.000     -6.486       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided       final_rule__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     0.000     -6.017       0.000          14   1000             False
partial_donor_failure                    usable_record_share  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share            final_rule__minus__length_rule     0.000      0.000       6.779          14   1000             False
partial_donor_failure                    usable_record_share      final_rule__minus__length_rule_pub49     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share       final_rule__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share final_rule__minus__peak_window_rule_pub10     0.000      0.000       0.008          14   1000             False
partial_donor_failure                    usable_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share      peak_window_rule__minus__length_rule     0.000      0.000       4.638          14   1000             False
          target_only consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
          target_only consequential_error_rate_among_decided            final_rule__minus__length_rule     1.024     -5.103       2.333          14   1000             False
          target_only consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49     1.024      0.000       2.362          14   1000             False
          target_only consequential_error_rate_among_decided       final_rule__minus__peak_window_rule     1.024      0.000       2.455          14   1000             False
          target_only consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     1.024      0.000       2.350          14   1000             False
          target_only consequential_error_rate_among_decided          final_rule_fb__minus__final_rule    -1.024     -2.439       0.000          14   1000             False
          target_only consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
          target_only consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     0.000     -6.567       0.000          14   1000             False
          target_only                    usable_record_share  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
          target_only                    usable_record_share            final_rule__minus__length_rule    -1.024     -2.349       4.616          14   1000             False
          target_only                    usable_record_share      final_rule__minus__length_rule_pub49    -1.024     -2.353       0.000          14   1000             False
          target_only                    usable_record_share       final_rule__minus__peak_window_rule    -1.024     -2.553       0.000          14   1000             False
          target_only                    usable_record_share final_rule__minus__peak_window_rule_pub10    -1.024     -2.474       0.000          14   1000             False
          target_only                    usable_record_share          final_rule_fb__minus__final_rule     1.024      0.000       2.533          14   1000             False
          target_only                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.000      0.000       0.000          14   1000             False
          target_only                    usable_record_share      peak_window_rule__minus__length_rule     0.000      0.000       5.831          14   1000             False
    all_donor_failure consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided            final_rule__minus__length_rule   -17.215    -26.144     -10.613          14   1000              True
    all_donor_failure consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49    -3.797     -9.867      -0.436          14   1000              True
    all_donor_failure consequential_error_rate_among_decided       final_rule__minus__peak_window_rule    -0.759     -1.460       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10   -14.937    -20.768      -7.310          14   1000              True
    all_donor_failure consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule    -0.759     -1.471       0.000          14   1000             False
    all_donor_failure consequential_error_rate_among_decided      peak_window_rule__minus__length_rule   -16.456    -25.158      -9.685          14   1000              True
    all_donor_failure                    usable_record_share  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share            final_rule__minus__length_rule    17.722     11.178      26.441          14   1000              True
    all_donor_failure                    usable_record_share      final_rule__minus__length_rule_pub49     3.291      0.000      10.101          14   1000             False
    all_donor_failure                    usable_record_share       final_rule__minus__peak_window_rule     0.253      0.000       0.907          14   1000             False
    all_donor_failure                    usable_record_share final_rule__minus__peak_window_rule_pub10    15.443      7.880      22.224          14   1000              True
    all_donor_failure                    usable_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
    all_donor_failure                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.253      0.000       0.885          14   1000             False
    all_donor_failure                    usable_record_share      peak_window_rule__minus__length_rule    17.468      9.850      27.158          14   1000              True
partial_donor_failure consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided            final_rule__minus__length_rule   -17.215    -26.351     -10.180          14   1000              True
partial_donor_failure consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49    -3.291     -9.395       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided       final_rule__minus__peak_window_rule    -0.253     -0.926       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10   -14.937    -21.214      -7.614          14   1000              True
partial_donor_failure consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule    -0.253     -0.912       0.000          14   1000             False
partial_donor_failure consequential_error_rate_among_decided      peak_window_rule__minus__length_rule   -16.962    -25.000     -10.444          14   1000              True
partial_donor_failure                    usable_record_share  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share            final_rule__minus__length_rule    17.722     10.890      27.452          14   1000              True
partial_donor_failure                    usable_record_share      final_rule__minus__length_rule_pub49     3.291      0.000       9.607          14   1000             False
partial_donor_failure                    usable_record_share       final_rule__minus__peak_window_rule     0.253      0.000       0.864          14   1000             False
partial_donor_failure                    usable_record_share final_rule__minus__peak_window_rule_pub10    15.443      8.331      21.952          14   1000              True
partial_donor_failure                    usable_record_share          final_rule_fb__minus__final_rule     0.000      0.000       0.000          14   1000             False
partial_donor_failure                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.253      0.000       0.906          14   1000             False
partial_donor_failure                    usable_record_share      peak_window_rule__minus__length_rule    17.468     10.508      27.130          14   1000              True
          target_only consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
          target_only consequential_error_rate_among_decided            final_rule__minus__length_rule   -12.564    -22.472      -4.735          14   1000              True
          target_only consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49     1.282     -6.437       5.240          14   1000             False
          target_only consequential_error_rate_among_decided       final_rule__minus__peak_window_rule     3.333      0.298       6.275          14   1000              True
          target_only consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10   -10.256    -16.482      -4.407          14   1000              True
          target_only consequential_error_rate_among_decided          final_rule_fb__minus__final_rule    -2.564     -4.634      -0.608          14   1000              True
          target_only consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule     0.769     -0.547       2.375          14   1000             False
          target_only consequential_error_rate_among_decided      peak_window_rule__minus__length_rule   -15.897    -25.285      -8.696          14   1000              True
          target_only                    usable_record_share  final_rule__minus__final_rule_point_risk     0.000      0.000       0.000          14   1000             False
          target_only                    usable_record_share            final_rule__minus__length_rule    13.333      4.949      24.814          14   1000              True
          target_only                    usable_record_share      final_rule__minus__length_rule_pub49    -1.282     -4.956       6.377          14   1000             False
          target_only                    usable_record_share       final_rule__minus__peak_window_rule    -3.333     -6.131      -0.643          14   1000              True
          target_only                    usable_record_share final_rule__minus__peak_window_rule_pub10    11.026      4.529      17.082          14   1000              True
          target_only                    usable_record_share          final_rule_fb__minus__final_rule     2.564      0.651       4.843          14   1000              True
          target_only                    usable_record_share    final_rule_fb__minus__peak_window_rule    -0.769     -2.410       0.008          14   1000             False
          target_only                    usable_record_share      peak_window_rule__minus__length_rule    16.667      8.778      26.256          14   1000              True

Pooled view (each co-failure level difference averaged inside the group first, so the three levels are not pseudo-replicates):

             level                        statistic_label                                  contrast  point_pp  ci_low_pp  ci_high_pp  n_clusters  draws  excludes_zero_95
pooled_group_equal                admissible_record_share  final_rule__minus__final_rule_point_risk    -0.638     -1.714       0.000          14   1000             False
pooled_group_equal                admissible_record_share            final_rule__minus__length_rule    15.710      9.014      23.276          14   1000              True
pooled_group_equal                admissible_record_share      final_rule__minus__length_rule_pub49     2.791     -0.246       8.624          14   1000             False
pooled_group_equal                admissible_record_share       final_rule__minus__peak_window_rule    -0.080     -0.619       0.402          14   1000             False
pooled_group_equal                admissible_record_share final_rule__minus__peak_window_rule_pub10    13.557      6.745      19.134          14   1000              True
pooled_group_equal                admissible_record_share          final_rule_fb__minus__final_rule     0.797      0.206       1.542          14   1000              True
pooled_group_equal                admissible_record_share    final_rule_fb__minus__peak_window_rule     0.718      0.097       1.497          14   1000              True
pooled_group_equal                admissible_record_share      peak_window_rule__minus__length_rule    15.789      9.648      22.757          14   1000              True
pooled_group_equal consequential_error_rate_among_decided  final_rule__minus__final_rule_point_risk    -0.495     -1.876       0.001          14   1000             False
pooled_group_equal consequential_error_rate_among_decided            final_rule__minus__length_rule     0.679      0.000       2.587          14   1000             False
pooled_group_equal consequential_error_rate_among_decided      final_rule__minus__length_rule_pub49    -0.106     -0.497       0.469          14   1000             False
pooled_group_equal consequential_error_rate_among_decided       final_rule__minus__peak_window_rule    -0.082     -0.497       0.527          14   1000             False
pooled_group_equal consequential_error_rate_among_decided final_rule__minus__peak_window_rule_pub10     0.679      0.000       2.641          14   1000             False
pooled_group_equal consequential_error_rate_among_decided          final_rule_fb__minus__final_rule     0.156     -0.007       0.574          14   1000             False
pooled_group_equal consequential_error_rate_among_decided    final_rule_fb__minus__peak_window_rule     0.074     -0.476       1.017          14   1000             False
pooled_group_equal consequential_error_rate_among_decided      peak_window_rule__minus__length_rule     0.761      0.000       2.326          14   1000             False
pooled_group_equal                    usable_record_share  final_rule__minus__final_rule_point_risk    -1.116     -3.345       0.000          14   1000             False
pooled_group_equal                    usable_record_share            final_rule__minus__length_rule    16.348     10.025      24.679          14   1000              True
pooled_group_equal                    usable_record_share      final_rule__minus__length_rule_pub49     2.711     -0.481       8.696          14   1000             False
pooled_group_equal                    usable_record_share       final_rule__minus__peak_window_rule    -0.159     -0.703       0.731          14   1000             False
pooled_group_equal                    usable_record_share final_rule__minus__peak_window_rule_pub10    14.195      7.016      20.145          14   1000              True
pooled_group_equal                    usable_record_share          final_rule_fb__minus__final_rule     0.957      0.343       1.750          14   1000              True
pooled_group_equal                    usable_record_share    final_rule_fb__minus__peak_window_rule     0.797      0.000       2.077          14   1000             False
pooled_group_equal                    usable_record_share      peak_window_rule__minus__length_rule    16.507      9.830      24.638          14   1000              True

## 6. Verdict under all-donor failure

- among decided cases (different denominators): final rule minus peak-window rule = -0.51 pp [-1.19, +0.00]; minus length rule = +0.51 pp [+0.00, +2.17] (positive means the final rule has the higher consequential-error rate);
- usable-record share (records produced): final rule minus peak-window rule = +0.24 pp [+0.00, +0.82]; minus length rule = +16.75 pp [+10.39, +25.26];
- admissible-record share (produced AND within 0.5 C): final rule minus the frozen-threshold peak-window rule = +0.72 pp [+0.00, +1.42]; minus the frozen-threshold length rule = +16.27 pp [+9.76, +24.25]; versus the published 49 d length rule = +3.59 pp [+0.00, +9.33] (error rate among decided -0.54 pp [-1.24, +0.00]);
- over ALL candidates with failures counted as failures: final rule 0.0598 vs peak-window 0.0670 vs length 0.2225 (abstention is a lost record, not a free option);
- decided shares under all-donor failure: final 0.9450, peak 0.9426, length 0.7775; strict `ok` shares: final 0.9450, peak 0.9426, length 0.7775.
- realised consequential-error rate among the final rule's decided cases: target-only 0.0103, partial 0.0051, all-donor 0.0051 against the 5% calibration cap (the threshold transfers conservatively or not, and this is the check);

**Reading:** under all-donor failure the final rule is a statistical tie with the frozen-threshold peak-window rule on both measures (admissible-record share +0.72 pp [+0.00, +1.42]; consequential-error rate among decided -0.51 pp [-1.19, +0.00]), and it retains +16.27 pp [+9.76, +24.25] more admissible records than the frozen-threshold length rule at a +0.51 pp [+0.00, +2.17] consequential-error cost among decided cases.  Its decided share is the highest of the three (0.9450 vs 0.9426 and 0.7775), so it does not win by abstaining more.

## 7. What would falsify the claim that the final rule is usable on real calendars

1. A cross-fitted calibrated threshold whose consequential-error rate among decided replay cases exceeds the 5% calibration cap by more than the clustered interval allows under target-only failure.
2. An admissible-record share under all-donor failure at or below the simple rules'.
3. A donor-path error among the cases where donors are available that is no better than the labelled observed-days estimator on the same cases (then the donor reconstructor earns nothing).
4. A degenerate-donor share large enough that the strict rule mostly abstains when neighbours fail.
5. Cross-year gaps behaving differently from within-year gaps of the same length (the requirement that motivated the continuous-axis placement) in the direction of worse error.

## 8. What this does NOT prove

- the replay transplants real incomplete-year calendars onto other years of the same station; it is not a real outage at that station;
- the calibrated thresholds are transferred from designed-outage development cases to real calendars, and the designed corpus is what sets the 5% risk cap;
- co-failure is imposed by masking donor columns with the target calendar, not by observing real simultaneous neighbour failures;
- the final rule is a per-fold refit certificate (three-way network-disjoint split), not the frozen step-9 joblib object; the frozen object appears only as the secondary frozen_cert_rule row;
- no statement about operational monitoring admission; offline archive repair only;
- the replay networks are development networks, so this is an internal cross-fitted probe, not a sealed confirmation panel;
- the co-failure levels are repeated measures on the same group and are never independent replicates;
- it does not prove that real simultaneous neighbour outages look like the imposed calendar co-failure;
- it does not prove anything about operational (near-real-time) monitoring admission;
- it does not establish a universal threshold: the calibrated thresholds are fold-specific (14 values) and are not tuned on the replay.

