# Step 2 protocol — same-info strong baseline (pre-registered)

**Parent:** `PROPOSITION_TABLE.md` claim **C1**  
**Locked commit baseline:** `53c88cc`  
**Do not retune** retention, tolerance, or risk-cap after inspecting reserved / wave-2 nested scores.

## Estimand

On a fixed candidate set of designed outage cases, compare **risk ranking** rules that share the same learner capacity and training budget, differing only in whether engineered **target-support** features are available.

## Operating points (frozen before test look)

| Name | Definition |
|---|---|
| OP-70 | Keep lowest-risk 70%; report rate of \|error\| > 0.5 °C among kept |
| OP-RISK5 | Maximum retention such that kept consequential-error rate ≤ 5%; report retention |

Primary contrasts at both OPs (network-clustered paired bootstrap):

1. `generic_plus_support` − `peak_overlap_rule`
2. `generic_plus_support` − `generic`
3. `generic_plus_support_plus_peakmargin` − `generic_plus_support`
4. Descriptive only (already known): full certificate vs length rule

## Feature budgets

| Set | Features |
|---|---|
| `generic` | `longest_run`, `total_missing`, `missing_fraction`, `n_runs`, `warm_observed_fraction`, `month_sin`, `month_cos`, donor block, `train_resid_sd`, `seasonal_amplitude`, `train_metric_sd`, `n_complete_years`, `record_years`, `left_flank`, `right_flank`, `air_available`, `estimator_disagreement` |
| `+support` | generic + `peak_overlap` |
| `+peak_margin` | +support + `observed_peak_margin`, `observed_peak`, `has_complete_window` |
| `full_screen_features` | `SCREEN_FEATURES` (reference; includes clim_peak etc.) |

**Explicit exclusion from `generic`:** `peak_overlap` and any feature that is only a rewrite of hidden support share.

**Note:** true calendar monthly visibility fractions are not stored on the case table; `warm_observed_fraction` + month-of-longest-run harmonics stand in. If support still wins, the claim is stronger; if not, recompute monthly fractions before abandoning C1.

## Learner

Single-head `HistGradientBoostingRegressor` (quantile loss at coverage 0.9) predicting `abserr_policy`, identical hyperparameters to the certificate upper head (`max_depth=4`, `max_iter=350`, `learning_rate=0.06`, `min_samples_leaf=40`). Ranking score = predicted risk (lower kept first). No reconstructor selection in this nest — isolates representation. Reconstructor-selection increment remains the existing `certificate` vs `certificate_screen_only` gap (~0.26 pp on wave-2).

## Partitions

| Role | Networks |
|---|---|
| Development OOF attribution | 110 development nets, GroupKFold by network (5 folds); within each train fold, 30% networks for conformal-free fit only (no cal needed for ranking) |
| Learning curves | Fit on {10,25,50,all} random development nets (seed 17); calibration unused for ranking; **test = reserved 36 nets** (opened retrospective — label as such) |
| Wave-2 | Optional apply of development-fit models later; do not retune |

## Rule baselines (unchanged)

`length_rule`, `warm_coverage_rule`, `peak_overlap_rule`, `estimator_disagreement` (jittered ties as in `frontier.screening_scores`).

## Success / failure (from proposition table)

- **Success:** network CI for Δ(OP-70) vs peak-overlap excludes 0 in the beneficial direction **and** OP-RISK5 retains ≥ +5 pp vs that baseline; support vs generic shows beneficial CI or clear small-n learning-curve separation.
- **Failure narrowing:** if vs peak-overlap gain is tiny/unstable → peak-overlap (or warm rule) becomes primary method in the paper; ML screen becomes extension/upper bound.

## Outputs

`results/wrr_submission_ready/major_revision_20261014/step2_same_info_ablation/`:

- `frontiers_oof.csv`, `operating_points.csv`, `contrasts_network_ci.json`
- `learning_curves.csv`, `SUMMARY.md`, `protocol_fingerprint.json`
