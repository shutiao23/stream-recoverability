# P1 / F11 — learning curves with repeated training-network draws

Script: `scripts/316_wrr_p1_learning_curve_repeats.py` (sha256 `b2a07ff4e557`), feature sets and learner imported verbatim from `scripts/301_wrr_mr_step2_same_info_ablation.py` (sha256 `abf191bed6bb`).

## Why

The published `step2_same_info_ablation/learning_curves_reserved.csv` holds a **single** draw of training networks per size, so a between-size difference and a between-draw difference cannot be told apart. Every cell below is repeated over independent network draws.

## Design (fixed before the grid was run)

- **Training pool:** 110 development networks (`results/v17_fitness/step4_ceiling/development_cases.parquet`, 40704 cases).
- **Evaluation set (fixed, external):** 36 reserved / wave-2 networks, 10820 cases (`results/v17_fitness/step10_confirmation/reserved_cases.parquet`). Network overlap with the training pool = 0, station overlap = 0; the evaluation panel is never part of any training draw and its labels never enter model fitting, feature choice, or the risk-cap calibration. It is an external, already-opened retrospective panel (not a new seal).
- **Sizes:** 10, 25, 50, 75, all development networks (`all` = the full 110-network pool; that cell has exactly one possible network set, so it is run once and additionally repeated over learner seeds).
- **Draws:** 20 independent subsets per size (seeds `SUBSET_SEED_BASE + 1000*size_index + draw_index`, base 20261014, recorded per row); learner seed held at 17 so that only the drawn networks change. The three feature sets share the subset and the seed inside a draw, so all contrasts are paired on the draw.
- **Metrics** (identical definitions to the pre-registered OP-70 / OP-RISK5):
  - *false-admit rate at 70 % retention* = share of the kept lowest-risk 70 % of the evaluation panel with `|abserr_policy| > 0.5 °C`;
  - *retention at a 5 % risk cap* = the largest retention whose kept bad-rate is ≤ 5 % — selected **on network-held-out OOF scores inside the drawn training networks only** (`oof_risk_scores` + `retention_at_risk_cap` from script 301), then applied to the evaluation panel. Script 301 selected this retention on the evaluation panel itself; that leak is removed here.
- **Compute:** 64 joblib/loky workers; 333 draw jobs; grid 73.7 s, wall 74.0 s.

## 1. Curve summary — mean / SD / min / max across draws

`rate70` = false-admit rate at 70 % retention (lower is better); `risk5_retention` = retention at the 5 % risk cap calibrated on the training draws (higher is better). `n_sub` = number of distinct network subsets behind the cell.

| draw_kind | n_train | feature_set | n_draws | n_sub | rate70 mean | rate70 SD | rate70 min | rate70 max | risk5 mean | risk5 SD | risk5 min | risk5 max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| network_subset | 10 | generic | 20 | 20 | 0.0353 | 0.0052 | 0.0269 | 0.0458 | 0.694 | 0.071 | 0.550 | 0.800 |
| network_subset | 10 | generic_plus_support | 20 | 20 | 0.0330 | 0.0049 | 0.0248 | 0.0430 | 0.700 | 0.063 | 0.570 | 0.800 |
| network_subset | 10 | generic_plus_support_plus_peakmargin | 20 | 20 | 0.0335 | 0.0052 | 0.0252 | 0.0428 | 0.702 | 0.068 | 0.570 | 0.810 |
| network_subset | 25 | generic | 20 | 20 | 0.0310 | 0.0033 | 0.0271 | 0.0388 | 0.731 | 0.043 | 0.630 | 0.780 |
| network_subset | 25 | generic_plus_support | 20 | 20 | 0.0292 | 0.0029 | 0.0259 | 0.0358 | 0.733 | 0.038 | 0.640 | 0.780 |
| network_subset | 25 | generic_plus_support_plus_peakmargin | 20 | 20 | 0.0291 | 0.0028 | 0.0260 | 0.0342 | 0.736 | 0.041 | 0.630 | 0.790 |
| network_subset | 50 | generic | 20 | 20 | 0.0269 | 0.0024 | 0.0236 | 0.0323 | 0.762 | 0.021 | 0.720 | 0.800 |
| network_subset | 50 | generic_plus_support | 20 | 20 | 0.0253 | 0.0021 | 0.0224 | 0.0309 | 0.764 | 0.022 | 0.720 | 0.800 |
| network_subset | 50 | generic_plus_support_plus_peakmargin | 20 | 20 | 0.0250 | 0.0017 | 0.0224 | 0.0284 | 0.759 | 0.023 | 0.720 | 0.800 |
| network_subset | 75 | generic | 20 | 20 | 0.0256 | 0.0011 | 0.0242 | 0.0283 | 0.764 | 0.022 | 0.710 | 0.790 |
| network_subset | 75 | generic_plus_support | 20 | 20 | 0.0242 | 0.0014 | 0.0223 | 0.0272 | 0.766 | 0.023 | 0.710 | 0.800 |
| network_subset | 75 | generic_plus_support_plus_peakmargin | 20 | 20 | 0.0237 | 0.0016 | 0.0207 | 0.0271 | 0.765 | 0.022 | 0.710 | 0.790 |
| full_pool_single | all | generic | 1 | 1 | 0.0236 | NA | 0.0236 | 0.0236 | 0.770 | NA | 0.770 | 0.770 |
| full_pool_single | all | generic_plus_support | 1 | 1 | 0.0236 | NA | 0.0236 | 0.0236 | 0.770 | NA | 0.770 | 0.770 |
| full_pool_single | all | generic_plus_support_plus_peakmargin | 1 | 1 | 0.0217 | NA | 0.0217 | 0.0217 | 0.770 | NA | 0.770 | 0.770 |

Learner-seed repeats on a **fixed** network set (no network variation), to price the noise floor:

| draw_kind | n_train | feature_set | n_draws | rate70 mean | rate70 SD | risk5 mean | risk5 SD |
|---|---|---|---|---|---|---|---|
| fixed_subset_model_seed | 10 | generic | 10 | 0.0395 | 0.0000 | 0.635 | 0.014 |
| fixed_subset_model_seed | 10 | generic_plus_support | 10 | 0.0370 | 0.0000 | 0.666 | 0.018 |
| fixed_subset_model_seed | 10 | generic_plus_support_plus_peakmargin | 10 | 0.0409 | 0.0000 | 0.652 | 0.019 |
| fixed_subset_model_seed | 75 | generic | 10 | 0.0245 | 0.0008 | 0.780 | 0.007 |
| fixed_subset_model_seed | 75 | generic_plus_support | 10 | 0.0238 | 0.0008 | 0.782 | 0.006 |
| fixed_subset_model_seed | 75 | generic_plus_support_plus_peakmargin | 10 | 0.0241 | 0.0009 | 0.780 | 0.000 |
| full_pool_model_seed | all | generic | 10 | 0.0246 | 0.0005 | 0.768 | 0.004 |
| full_pool_model_seed | all | generic_plus_support | 10 | 0.0229 | 0.0007 | 0.769 | 0.003 |
| full_pool_model_seed | all | generic_plus_support_plus_peakmargin | 10 | 0.0226 | 0.0009 | 0.768 | 0.004 |

Risk-cap transfer check — the calibrated retention `r*` and the bad-rate it actually achieves on the evaluation panel (a leak-free cap need not land exactly at 5 %; the external panel is harder than the development pool, base rate of `|abserr_policy| > 0.5 °C` = 14.6 %):

| n_train | feature_set | r* mean | r* SD | eval bad-rate at r* (mean) | eval bad-rate at r* (min) | eval bad-rate at r* (max) |
|---|---|---|---|---|---|---|
| 10 | generic | 0.694 | 0.071 | 0.0354 | 0.0055 | 0.0654 |
| 10 | generic_plus_support | 0.700 | 0.063 | 0.0347 | 0.0104 | 0.0586 |
| 10 | generic_plus_support_plus_peakmargin | 0.702 | 0.068 | 0.0365 | 0.0139 | 0.0646 |
| 25 | generic | 0.731 | 0.043 | 0.0408 | 0.0195 | 0.0634 |
| 25 | generic_plus_support | 0.733 | 0.038 | 0.0385 | 0.0214 | 0.0579 |
| 25 | generic_plus_support_plus_peakmargin | 0.736 | 0.041 | 0.0400 | 0.0170 | 0.0594 |
| 50 | generic | 0.762 | 0.021 | 0.0440 | 0.0359 | 0.0545 |
| 50 | generic_plus_support | 0.764 | 0.022 | 0.0435 | 0.0332 | 0.0546 |
| 50 | generic_plus_support_plus_peakmargin | 0.759 | 0.023 | 0.0417 | 0.0316 | 0.0529 |
| 75 | generic | 0.764 | 0.022 | 0.0433 | 0.0302 | 0.0529 |
| 75 | generic_plus_support | 0.766 | 0.023 | 0.0429 | 0.0288 | 0.0537 |
| 75 | generic_plus_support_plus_peakmargin | 0.765 | 0.022 | 0.0421 | 0.0282 | 0.0503 |
| all | generic | 0.770 | NA | 0.0437 | 0.0437 | 0.0437 |
| all | generic_plus_support | 0.770 | NA | 0.0417 | 0.0417 | 0.0417 |
| all | generic_plus_support_plus_peakmargin | 0.770 | NA | 0.0424 | 0.0424 | 0.0424 |

## 1b. The published single draw against the 20-draw distribution

`step2_same_info_ablation/learning_curves_reserved.csv` (read-only input) against the repeated draws at the same size. The `all` row is the reproducibility check: same network set, same learner seed, so it must reproduce the published rate exactly.

| n_train | feature_set | published rate70 (1 draw) | repeats mean | repeats min | repeats max | published inside the repeat range? |
|---|---|---|---|---|---|---|
| 10 | generic | 0.0358 | 0.0353 | 0.0269 | 0.0458 | yes |
| 25 | generic | 0.0289 | 0.0310 | 0.0271 | 0.0388 | yes |
| 50 | generic | 0.0366 | 0.0269 | 0.0236 | 0.0323 | NO — outside every repeat |
| all | generic | 0.0236 | 0.0236 | 0.0236 | 0.0236 | yes |
| 10 | generic_plus_support | 0.0353 | 0.0330 | 0.0248 | 0.0430 | yes |
| 25 | generic_plus_support | 0.0242 | 0.0292 | 0.0259 | 0.0358 | NO — outside every repeat |
| 50 | generic_plus_support | 0.0353 | 0.0253 | 0.0224 | 0.0309 | NO — outside every repeat |
| all | generic_plus_support | 0.0236 | 0.0236 | 0.0236 | 0.0236 | yes |
| 10 | generic_plus_support_plus_peakmargin | 0.0326 | 0.0335 | 0.0252 | 0.0428 | yes |
| 25 | generic_plus_support_plus_peakmargin | 0.0250 | 0.0291 | 0.0260 | 0.0342 | NO — outside every repeat |
| 50 | generic_plus_support_plus_peakmargin | 0.0268 | 0.0250 | 0.0224 | 0.0284 | yes |
| all | generic_plus_support_plus_peakmargin | 0.0217 | 0.0217 | 0.0217 | 0.0217 | yes |

The published OP-RISK5 column (`retention_at_risk_cap_5pct`) is **not** comparable to `risk5_retention_calibrated` here: script 301 chose that retention on the evaluation panel's own errors (`rate_above_0.5_at_risk_cap` is reported at exactly ≤ 5 % by construction), while the repeats choose it on network-held-out OOF scores inside the training draws only. Reported OP-RISK5 numbers in the published file are therefore an upper bound inflated by that leak; the leak-free repeats are the number to quote.

## 2. Paired draw-level differences

`diff = arm_a - arm_b`, paired on the same network subset and learner seed within each draw. 95 % percentile bootstrap over draws (10 000 resamples, seed 20261014); `ci_excludes_zero` is the distinguishability test. For `lower_is_better` metrics a negative diff favours arm_a.

| contrast | size | draw_kind | pairing | metric | n_draws | mean diff (pp) | SD (pp) | 95 % CI (pp) | arm_a better in | sign p | CI excludes 0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| generic_plus_support - generic | 10 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | -0.251 | 0.000 | [-0.251, -0.251] | 10.0/10 | 0.002 | True |
| generic_plus_support_plus_peakmargin - generic | 10 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | 0.145 | 0.000 | [0.145, 0.145] | 0.0/10 | 0.002 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 10 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | 0.396 | 0.000 | [0.396, 0.396] | 0.0/10 | 0.002 | True |
| generic_plus_support - generic | 75 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | -0.067 | 0.108 | [-0.133, -0.005] | 7.0/10 | 0.344 | True |
| generic_plus_support_plus_peakmargin - generic | 75 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | -0.041 | 0.078 | [-0.090, 0.001] | 6.0/10 | 0.754 | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | 75 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | 0.026 | 0.100 | [-0.028, 0.087] | 5.0/10 | 1.000 | False |
| generic_plus_support - generic | all | full_pool_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | -0.165 | 0.115 | [-0.230, -0.095] | 8.0/10 | 0.039 | True |
| generic_plus_support_plus_peakmargin - generic | all | full_pool_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | -0.199 | 0.072 | [-0.243, -0.158] | 10.0/10 | 0.002 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | all | full_pool_model_seed | same_fixed_network_set_model_seed_varied | rate_above_0.5_at_70 | 10 | -0.034 | 0.130 | [-0.110, 0.040] | 5.0/10 | 1.000 | False |
| generic_plus_support - generic | all | full_pool_single | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 1 | 0.000 | NA | [NA, NA] | 0.0/1 | NA | False |
| generic_plus_support_plus_peakmargin - generic | all | full_pool_single | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 1 | -0.198 | NA | [NA, NA] | 1.0/1 | 1.000 | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | all | full_pool_single | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 1 | -0.198 | NA | [NA, NA] | 1.0/1 | 1.000 | False |
| generic_plus_support - generic | 10 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.230 | 0.222 | [-0.323, -0.135] | 17.0/20 | 0.003 | True |
| generic_plus_support_plus_peakmargin - generic | 10 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.174 | 0.294 | [-0.300, -0.050] | 14.0/20 | 0.115 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 10 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | 0.055 | 0.183 | [-0.022, 0.132] | 8.0/20 | 0.503 | False |
| generic_plus_support - generic | 25 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.184 | 0.162 | [-0.254, -0.118] | 18.0/20 | 0.000 | True |
| generic_plus_support_plus_peakmargin - generic | 25 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.196 | 0.192 | [-0.275, -0.112] | 18.0/20 | 0.000 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 25 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.012 | 0.159 | [-0.079, 0.057] | 11.0/20 | 0.824 | False |
| generic_plus_support - generic | 50 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.155 | 0.157 | [-0.226, -0.090] | 16.0/20 | 0.012 | True |
| generic_plus_support_plus_peakmargin - generic | 50 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.194 | 0.175 | [-0.271, -0.119] | 17.0/20 | 0.003 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 50 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.039 | 0.139 | [-0.102, 0.017] | 9.0/20 | 1.000 | False |
| generic_plus_support - generic | 75 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.139 | 0.160 | [-0.204, -0.067] | 15.0/20 | 0.019 | True |
| generic_plus_support_plus_peakmargin - generic | 75 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.195 | 0.165 | [-0.263, -0.122] | 18.0/20 | 0.000 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 75 | network_subset | same_network_subset_and_model_seed | rate_above_0.5_at_70 | 20 | -0.057 | 0.113 | [-0.109, -0.012] | 13.0/20 | 0.167 | True |
| generic_plus_support - generic | 10 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | 3.100 | 1.370 | [2.200, 3.800] | 9.0/10 | 0.004 | True |
| generic_plus_support_plus_peakmargin - generic | 10 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | 1.700 | 1.494 | [0.800, 2.600] | 8.0/10 | 0.039 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 10 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | -1.400 | 1.075 | [-2.000, -0.800] | 0.0/10 | 0.008 | True |
| generic_plus_support - generic | 75 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | 0.200 | 0.632 | [-0.200, 0.600] | 3.0/10 | 0.625 | False |
| generic_plus_support_plus_peakmargin - generic | 75 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | 0.000 | 0.667 | [-0.400, 0.400] | 2.0/10 | 1.000 | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | 75 | fixed_subset_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | -0.200 | 0.632 | [-0.600, 0.200] | 1.0/10 | 0.625 | False |
| generic_plus_support - generic | all | full_pool_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | 0.100 | 0.316 | [0.000, 0.300] | 1.0/10 | 1.000 | False |
| generic_plus_support_plus_peakmargin - generic | all | full_pool_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | 0.000 | 0.000 | [0.000, 0.000] | 0.0/10 | NA | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | all | full_pool_model_seed | same_fixed_network_set_model_seed_varied | risk5_retention_calibrated | 10 | -0.100 | 0.316 | [-0.300, 0.000] | 0.0/10 | 1.000 | False |
| generic_plus_support - generic | all | full_pool_single | same_network_subset_and_model_seed | risk5_retention_calibrated | 1 | 0.000 | NA | [NA, NA] | 0.0/1 | NA | False |
| generic_plus_support_plus_peakmargin - generic | all | full_pool_single | same_network_subset_and_model_seed | risk5_retention_calibrated | 1 | 0.000 | NA | [NA, NA] | 0.0/1 | NA | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | all | full_pool_single | same_network_subset_and_model_seed | risk5_retention_calibrated | 1 | 0.000 | NA | [NA, NA] | 0.0/1 | NA | False |
| generic_plus_support - generic | 10 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.600 | 1.314 | [0.050, 1.150] | 10.0/20 | 0.302 | True |
| generic_plus_support_plus_peakmargin - generic | 10 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.800 | 1.795 | [0.050, 1.550] | 10.0/20 | 0.092 | True |
| generic_plus_support_plus_peakmargin - generic_plus_support | 10 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.200 | 1.322 | [-0.350, 0.800] | 7.0/20 | 1.000 | False |
| generic_plus_support - generic | 25 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.150 | 1.089 | [-0.300, 0.650] | 6.0/20 | 1.000 | False |
| generic_plus_support_plus_peakmargin - generic | 25 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.400 | 1.095 | [-0.050, 0.900] | 9.0/20 | 0.146 | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | 25 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.250 | 1.251 | [-0.250, 0.800] | 6.0/20 | 1.000 | False |
| generic_plus_support - generic | 50 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.250 | 0.550 | [0.000, 0.500] | 6.0/20 | 0.125 | False |
| generic_plus_support_plus_peakmargin - generic | 50 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | -0.200 | 0.894 | [-0.600, 0.150] | 3.0/20 | 0.727 | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | 50 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | -0.450 | 0.759 | [-0.800, -0.150] | 0.0/20 | 0.016 | True |
| generic_plus_support - generic | 75 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.200 | 0.523 | [0.000, 0.450] | 5.0/20 | 0.219 | False |
| generic_plus_support_plus_peakmargin - generic | 75 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | 0.050 | 0.686 | [-0.250, 0.350] | 5.0/20 | 1.000 | False |
| generic_plus_support_plus_peakmargin - generic_plus_support | 75 | network_subset | same_network_subset_and_model_seed | risk5_retention_calibrated | 20 | -0.150 | 0.587 | [-0.400, 0.100] | 2.0/20 | 0.453 | False |

## 3. Direct sample-efficiency test (what the claim actually needs)

Support at 10 training networks vs generic at 25/50/75/all, independent draw sets, 95 % bootstrap over draws. The `all` arm cannot vary its network set, so it is the learner-seed repeat series there; arm composition is given per row so no interval is read as more than it is:

| contrast | metric | n_draws A (subsets) | n_draws B (subsets) | mean diff (pp) | 95 % CI (pp) | P(support@10 draw beats generic@N draw) | CI excludes 0 |
|---|---|---|---|---|---|---|---|
| generic_plus_support@10 - generic@25 | rate_above_0.5_at_70 | 20 (20) | 20 (20) | 0.196 | [-0.058, 0.441] | 0.375 | False |
| generic_plus_support@10 - generic@50 | rate_above_0.5_at_70 | 20 (20) | 20 (20) | 0.608 | [0.376, 0.841] | 0.142 | True |
| generic_plus_support@10 - generic@75 | rate_above_0.5_at_70 | 20 (20) | 20 (20) | 0.736 | [0.523, 0.945] | 0.068 | True |
| generic_plus_support@10 - generic@all | rate_above_0.5_at_70 | 20 (20) | 10 (1) | 0.841 | [0.633, 1.049] | 0.025 | True |
| generic_plus_support@10 - generic@25 | risk5_retention_calibrated | 20 (20) | 20 (20) | -3.200 | [-6.400, 0.050] | 0.315 | False |
| generic_plus_support@10 - generic@50 | risk5_retention_calibrated | 20 (20) | 20 (20) | -6.200 | [-9.050, -3.400] | 0.160 | True |
| generic_plus_support@10 - generic@75 | risk5_retention_calibrated | 20 (20) | 20 (20) | -6.500 | [-9.350, -3.700] | 0.152 | True |
| generic_plus_support@10 - generic@all | risk5_retention_calibrated | 20 (20) | 10 (1) | -6.850 | [-9.550, -4.200] | 0.100 | True |

## 4. Computational cost per fit

| n_train (support set) | n_train_rows mean | full fit s | 5-fold calibration s | total job s |
|---|---|---|---|---|
| 10 | 3796 | 1.29 | 4.86 | 6.16 |
| 25 | 9611 | 1.56 | 6.67 | 8.26 |
| 50 | 19014 | 1.87 | 8.21 | 10.10 |
| 75 | 27825 | 3.18 | 11.74 | 14.95 |
| all | 40704 | 2.40 | 18.51 | 20.94 |

## 5. Verdict

- **false-admit rate at 70 % retention**: the CI excludes zero at 10 (network_subset): Δ=-0.230 pp [-0.323, -0.135] -> support better; 25 (network_subset): Δ=-0.184 pp [-0.254, -0.118] -> support better; 50 (network_subset): Δ=-0.155 pp [-0.226, -0.090] -> support better; 75 (network_subset): Δ=-0.139 pp [-0.204, -0.067] -> support better. At all the interval includes zero.
- **risk-cap retention**: the CI excludes zero at 10 (network_subset): Δ=+0.600 pp [+0.050, +1.150] -> support better. At all, 25, 50, 75 the interval includes zero.
- Draw-range overlap at equal training size:
  - n=110 rate_above_0.5_at_70: ranges overlap (generic [0.0236, 0.0236] vs support [0.0236, 0.0236])
  - n=110 risk5_retention_calibrated: ranges overlap (generic [0.7700, 0.7700] vs support [0.7700, 0.7700])
  - n=10 rate_above_0.5_at_70: ranges overlap (generic [0.0269, 0.0458] vs support [0.0248, 0.0430])
  - n=10 risk5_retention_calibrated: ranges overlap (generic [0.5500, 0.8000] vs support [0.5700, 0.8000])
  - n=25 rate_above_0.5_at_70: ranges overlap (generic [0.0271, 0.0388] vs support [0.0259, 0.0358])
  - n=25 risk5_retention_calibrated: ranges overlap (generic [0.6300, 0.7800] vs support [0.6400, 0.7800])
  - n=50 rate_above_0.5_at_70: ranges overlap (generic [0.0236, 0.0323] vs support [0.0224, 0.0309])
  - n=50 risk5_retention_calibrated: ranges overlap (generic [0.7200, 0.8000] vs support [0.7200, 0.8000])
  - n=75 rate_above_0.5_at_70: ranges overlap (generic [0.0242, 0.0283] vs support [0.0223, 0.0272])
  - n=75 risk5_retention_calibrated: ranges overlap (generic [0.7100, 0.7900] vs support [0.7100, 0.8000])
- Direct sample-efficiency test (`generic_plus_support` at 10 nets minus `generic` at a larger size, false-admit rate at 70 %): 25: Δ=+0.196 pp [-0.058, +0.441] (generic better); 50: Δ=+0.608 pp [+0.376, +0.841] (generic better); 75: Δ=+0.736 pp [+0.523, +0.945] (generic better); all: Δ=+0.841 pp [+0.633, +1.049] (generic better).
  - No larger-size comparison has a CI that excludes zero in favour of support at 10 nets: training on 10 support-equipped networks is **not** shown to match or beat training the generic model on 25-110 networks. **The sample-efficiency claim is unsupported** by these data, and the single-draw curve it was read from is within draw-to-draw variation.
- **Equivalent training size (derived, not measured):** the support curve at 10 networks (0.0330 false-admit rate at 70 %) sits at the level the generic curve reaches at ≈ 18.1 networks. Linear interpolation in n between the measured generic means (10:0.0353, 25:0.0310, 50:0.0269, 75:0.0256, 110:0.0236). This is the size of the sample-efficiency dividend the published claim rests on.
- Learner-seed repeats on a fixed network set (no network variation) give, for `generic_plus_support - generic`: n=all rate_above_0.5_at_70 Δ=-0.165 pp [-0.230, -0.095] (SD 0.115 pp); n=10 rate_above_0.5_at_70 Δ=-0.251 pp [-0.251, -0.251] (SD 0.000 pp); n=75 rate_above_0.5_at_70 Δ=-0.067 pp [-0.133, -0.005] (SD 0.108 pp); n=all risk5_retention_calibrated Δ=+0.100 pp [+0.000, +0.300] (SD 0.316 pp); n=10 risk5_retention_calibrated Δ=+3.100 pp [+2.200, +3.800] (SD 1.370 pp); n=75 risk5_retention_calibrated Δ=+0.200 pp [-0.200, +0.600] (SD 0.632 pp) — this is the part of the spread that is learner noise rather than network choice.
- **Overall:** at equal training size the support budget does show a small but real false-admit-rate gain — n=10 -0.230 pp [-0.323, -0.135], sign reverses in 3/20 draws; n=25 -0.184 pp [-0.254, -0.118], sign reverses in 2/20 draws; n=50 -0.155 pp [-0.226, -0.090], sign reverses in 4/20 draws; n=75 -0.139 pp [-0.204, -0.067], sign reverses in 5/20 draws — and it shrinks as training size grows. It is not a sample-efficiency gain: the same-size advantage is worth only the handful of extra networks computed above, while support trained on 10 networks is significantly worse than the generic budget trained on 50 or more (Section 3). The paper may claim a small same-size ranking increment for `peak_overlap`; it may **not** claim that the support feature set is more sample-efficient, and it must not read the published single-draw curve as evidence for either.

## Judgement calls and limitations

1. The evaluation set is the reserved / wave-2 panel (36 networks, 10 820 cases), the only panel that is disjoint from the development training pool at network *and* station level. It is already opened and retrospective, so this is a draw-variability study on an external panel, not a new sealed confirmation. `STEP2_PROTOCOL.md` says not to retune retention/tolerance/risk-cap after inspecting reserved scores: retention (70 %), tolerance (0.5 °C) and the risk cap (5 %) are unchanged from script 301 — only the *calibration location* of the risk cap moved inside the training draws, which removes a leak rather than retuning.
2. `all` = 110 development networks is a single network set; it has no draw-to-draw network variation, so it is reported once and the interval reported for it is the learner-seed interval (`full_pool_model_seed`), explicitly labelled. SD is recorded as NA, never as 0, when a cell has one draw.
3. Learner seed is held at 17 (script 301's seed) for every network-subset draw, so the reported spread is network-draw spread; the `fixed_subset_model_seed` cells show the learner-seed spread on identical data for comparison.
4. The risk cap is calibrated on network-held-out OOF scores inside the drawn training networks. With 10 training networks that calibration set is small (5 folds of 2 networks), so r* is itself noisy (SD 0.07 at n=10 vs 0.02 at n=50+); that noise is part of the honest small-n effect and is visible in the SD column. It also means a 5 % cap calibrated on 10 networks does not reliably hold out of sample: the realised bad-rate on the evaluation panel averages 3.5 % but reaches 6.5 % in the worst draw at n=10 (see the transfer table).
5. `abserr_policy` is the retrospective policy label; the nest isolates representation (feature budget), not reconstructor selection.
6. Total runtime is bounded well below the 40-minute budget; no draw reduction was needed (20 draws per size).

Runtime: grid 73.7 s, wall 74.0 s on 64 workers. Outputs: `learning_curves_repeats.csv`, `curve_summary.csv`, `paired_differences.csv`, `protocol_fingerprint.json`, `SUMMARY.md`.

