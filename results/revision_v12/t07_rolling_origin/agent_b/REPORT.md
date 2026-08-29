# Rolling-origin stability, history-length learning curve, and training-data comparability

Agent B (adversarial pair).  Revision v12, task t07.  Every number below was produced by running
`scripts/rev_v12_t07_rolling_origin_b.py` on the frozen development_v11 outputs; nothing is fabricated.

## Scope and subset

- First-panel (route-A confirmation) subset: the 20 networks with the longest temperature records
  among the 42 first-panel networks that have deployment placements in route_a_confirmation/
  placement_losses.csv (lubw_neckar, gkd_bayern_donau, gkd_bayern_fraenkische_saale, gkd_bayern_iller, gkd_bayern_inn, ...; see subset_networks.csv).
- Development subset for the learning curve: 8 long-record development networks
  (huc8_02040106, huc8_02040205, huc8_02050104, huc8_03050106, ...).
- Stress-curve machinery: parameterised copy of `fitting_period_empirical_losses` +
  `empirical_transfer_predictions` (scripts/124_run_reviewer_completion.py,
  src/stream_recoverability/experiments/recovery_roster.py).
- Determinism: the builder reproduces results/development_v11/reviewer_completion/
  confirmation_empirical_fit_losses.csv to ~5e-16 (verified on 4 networks), so the canonical
  numbers below are inherited by construction.

## Cross-checks

| scope | n | n_networks | pooled Spearman | network Spearman | calibration slope | R2 |
|---|---|---|---|---|---|---|
| first_panel_42_networks_canonical_existing | 780 | 42 | 0.934 | 0.922 | 0.864 | 0.812 |
| first_panel_42_networks_canonical_all_cells_with_fallback | 1440 | 42 | 0.633 | 0.767 | 0.829 | 0.145 |
| subset_20_canonical_from_existing_predictions | 8440 | 20 | 0.761 | 0.944 | 0.724 | 0.499 |
| subset_20_canonical_rerun | 8440 | 20 | 0.761 | 0.944 | 0.724 | 0.499 |

Requested cross-check targets: first panel 780 units pooled 0.934 / network 0.922 at the canonical 70% split;
complete panel (all cells with network-mean fallback) network 0.767.  Both are reproduced in the first two rows.
Rows 3-4 confirm the subset re-run matches the existing predictions restricted to the same 20 networks.

## 1. Rolling-origin evaluation across outer cutoffs (60/70/80% of years)

For each cutoff the stress curve is built only from earlier years (the recovery model fits on the first 70%
of the outer-training block, artificial gaps are scored in the following 30% of that block) and is then used
to predict the observed deployment losses in the later years (the remaining 100-C% of the record).
Metrics pool all directly supported cells across the 20-network subset:

| cutoff | n cells | n networks | pooled Spearman | network Spearman | calibration slope | R2 | RMSE | fit years (median) | eval years (median) |
|---|---|---|---|---|---|---|---|---|---|
| 0.60 | 5240 | 13 | 0.776 | 0.984 | 0.842 | 0.596 | 0.680 | 14 | 14 |
| 0.70 | 8440 | 20 | 0.761 | 0.944 | 0.724 | 0.499 | 0.699 | 16 | 10 |
| 0.80 | 5550 | 20 | 0.795 | 0.911 | 0.868 | 0.608 | 0.688 | 18 | 6 |

Per-cutoff per-network rows are in rolling_origin_cutoff_metrics.csv; per-cell predictions in
rolling_origin_predictions.csv; per-network mean predicted/observed losses in rolling_origin_network_ranks.csv.

Rank stability across cutoffs (per-network mean predicted loss, networks with supported cells in all three cutoffs):

- pairwise predicted-rank Spearman (0.60_vs_0.70): 0.802 (n_networks = 13)
- pairwise predicted-rank Spearman (0.70_vs_0.80): 0.808 (n_networks = 13)
- pairwise predicted-rank Spearman (0.60_vs_0.80): 0.538 (n_networks = 13)
- kendall_w_predicted_ranks: 0.811 (n_networks = 13)
- mean_pairwise_spearman_predicted_ranks: 0.716 (n_networks = 13)
- kendall_w_observed_ranks: 0.829 (n_networks = 13)

## 2. History-length learning curve

Canonical 70% outer split; the stress-curve model is fitted on the first N years of the outer-training
block (N = 2/4/6/8, or the canonical inner 70/30 split for `full`, ~49% of the record) and scores the
remaining years of that block; predictions transfer to the held-out last 30% of years.

| dataset | history level | n networks | n cells | pooled Spearman | network Spearman | calibration slope | R2 |
|---|---|---|---|---|---|---|---|
| first_panel | 2 | 20 | 8440 | 0.587 | 0.608 | 0.556 | -0.098 |
| first_panel | 4 | 20 | 8440 | 0.700 | 0.872 | 0.727 | 0.446 |
| first_panel | 6 | 20 | 8440 | 0.713 | 0.916 | 0.702 | 0.425 |
| first_panel | 8 | 20 | 8440 | 0.717 | 0.938 | 0.713 | 0.441 |
| first_panel | full | 20 | 8440 | 0.761 | 0.944 | 0.724 | 0.499 |
| development | 2 | 5 | 1300 | 0.570 | 0.700 | 0.628 | 0.019 |
| development | 4 | 7 | 1860 | 0.668 | 0.857 | 0.690 | 0.278 |
| development | 6 | 7 | 1860 | 0.667 | 0.679 | 0.851 | 0.405 |
| development | 8 | 7 | 1820 | 0.643 | 0.786 | 0.830 | 0.383 |
| development | full | 6 | 1700 | 0.677 | 0.943 | 0.856 | 0.566 |

- Minimum history for usable ranking (network Spearman >= 0.7), first_panel: 4.
- Minimum history for usable ranking (network Spearman >= 0.7), development: 2.
- Caveat: the development level-2 estimate is exactly 0.700 on only 5 networks; the robust headline is the
  first-panel level-4 finding (0.872 network Spearman on all 20 networks) and level-8/full convergence to
  0.94.
- Median full-history fit years: first panel 13, development 13.
- Figure: learning_curve.png.  Raw per-level metrics: learning_curve_metrics_first_panel.csv,
  learning_curve_metrics_development.csv, learning_curve_combined.csv; per-cell predictions in
  learning_curve_predictions_first_panel.csv / learning_curve_predictions_development.csv.

## 3. Training-data comparability (stress model ~49% vs deployment model 70%)

On identical evaluation placements (held-out last 30% of years) the recovery model was refitted twice per
station: on the stress-model training length (canonical inner-fit years, ~49% of the record, unmatched) and
on the deployment length (first 70% of the record, matched).  Both are out-of-sample for the evaluation period.

- pooled_spearman_mae49_vs_mae70: 0.9887 (n = 635, n_networks = 20)
- network_spearman_mae49_vs_mae70: 0.9805 (n = 635, n_networks = 20)
- calibration_slope_mae70_on_mae49: 0.9506 (n = 635, n_networks = 20)
- calibration_intercept_mae70_on_mae49: 0.0320 (n = 635, n_networks = 20)
- mean_paired_difference_mae49_minus_mae70: 0.0129 (n = 635, n_networks = 20)
- median_paired_difference_mae49_minus_mae70: 0.0077 (n = 635, n_networks = 20)
- mean_mae_49pct_model: 1.4093 (n = 635, n_networks = 20)
- mean_mae_70pct_model: 1.3964 (n = 635, n_networks = 20)

Per-gap-length detail (comparability_gap_lengths.csv):

| gap length | n | median MAE 49% model | median MAE 70% model | median difference | pooled Spearman |
|---|---|---|---|---|---|
| 7 | 98 | 0.476 | 0.439 | 0.015 | 0.943 |
| 14 | 98 | 0.603 | 0.593 | 0.008 | 0.947 |
| 30 | 98 | 0.754 | 0.748 | 0.002 | 0.967 |
| 60 | 98 | 0.988 | 1.013 | 0.000 | 0.967 |
| 90 | 98 | 1.224 | 1.252 | -0.003 | 0.957 |
| 180 | 87 | 2.580 | 2.548 | 0.023 | 0.943 |
| 365 | 58 | 4.795 | 4.635 | 0.032 | 0.865 |

Conclusion check - stress-curve predictions (canonical full level) evaluated against the deployment-file
observed losses, a matched 70%-length re-scored truth, and an unmatched 49%-length re-scored truth:

| truth | pooled Spearman | network Spearman | calibration slope | R2 | n | n_networks |
|---|---|---|---|---|---|---|
| deployment_file_observed | 0.954 | 0.970 | 0.820 | 0.896 | 346 | 20 |
| matched_70pct_truth | 0.954 | 0.970 | 0.820 | 0.896 | 346 | 20 |
| unmatched_49pct_truth | 0.958 | 0.962 | 0.861 | 0.916 | 346 | 20 |

## Files produced

- results/revision_v12/t07_rolling_origin/agent_b/REPORT.md
- results/revision_v12/t07_rolling_origin/agent_b/canonical_subset_crosscheck.csv
- results/revision_v12/t07_rolling_origin/agent_b/comparability_cells.csv
- results/revision_v12/t07_rolling_origin/agent_b/comparability_gap_lengths.csv
- results/revision_v12/t07_rolling_origin/agent_b/comparability_metrics.csv
- results/revision_v12/t07_rolling_origin/agent_b/comparability_stress_curve_check.csv
- results/revision_v12/t07_rolling_origin/agent_b/learning_curve.png
- results/revision_v12/t07_rolling_origin/agent_b/learning_curve_combined.csv
- results/revision_v12/t07_rolling_origin/agent_b/learning_curve_metrics_development.csv
- results/revision_v12/t07_rolling_origin/agent_b/learning_curve_metrics_first_panel.csv
- results/revision_v12/t07_rolling_origin/agent_b/learning_curve_predictions_development.csv
- results/revision_v12/t07_rolling_origin/agent_b/learning_curve_predictions_first_panel.csv
- results/revision_v12/t07_rolling_origin/agent_b/rolling_origin_cutoff_metrics.csv
- results/revision_v12/t07_rolling_origin/agent_b/rolling_origin_network_ranks.csv
- results/revision_v12/t07_rolling_origin/agent_b/rolling_origin_predictions.csv
- results/revision_v12/t07_rolling_origin/agent_b/rolling_origin_rank_stability.csv
- results/revision_v12/t07_rolling_origin/agent_b/subset_networks.csv

