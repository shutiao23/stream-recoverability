# T01 Same-Unit Paired Baseline Comparison — Second Panel (Agent A, adversarial pair)

## 1. Methods

- **Empirical predictor**: frozen second-panel predictions, `results/development_v11/second_confirmation/scoring/empirical_predictions.csv` (fitting-period empirical transfer; direct-horizon 7/30/90/180, network-mean fallback elsewhere). Read-only.
- **Simple predictor (rebuilt)**: linear model on `gap_length, acf_only, donor_r2_only, additive_d_over_4_heuristic, nearest_donor_correlation` — the exact route-A column set and equal-network weighting (`w = 1/n_network`; root weights; matches `fit_route_a_model` in `src/.../route_a_confirmation.py` and `_weighted_fit` in `scripts/124_run_reviewer_completion.py`).
  - `simple_fitperiod`: coefficients fit on **fitting-period only** = development (55 networks, 1,260 units) + first panel (42 networks, 1,440 units) = 97 networks, 2,700 units.
  - `simple_devonly`: development-only fit (reproduces the archived model; sensitivity).
- **Features**: recomputed from daily-QC panels (`second_confirmation/daily_qc/networks/`, CHMI from `confirmation_daily_qc/`) with the exact `simple_predictors()` code path used by `scripts/131_run_second_confirmation.py`. Bit-level agreement with archived `scoring/simple_predictions.csv` (max |diff| ≤ 1.1e-16 on all 4 numeric features, Pearson = 1.0, donor sets 1446/1446 exact). No feature was dropped.
- **Metrics**: station-gap Spearman (pooled units); network Spearman (Spearman over network means); calibration = equal-network-weighted OLS of observed on predicted (slope/intercept); R2, RMSE (pooled). Network bootstrap (2,000 draws, seed 0, resample 57 networks with replacement, relabel draws) computes both methods on the **same** resampled networks (paired). Within-network Spearman requires ≥4 units and nonzero within-network variance in both arrays; residualized Spearman = pooled Spearman after subtracting network means.

Script: `scripts/rev_v12_t01_paired_comparison_a.py`; output: `results/revision_v12/t01_paired_comparison/agent_a/` (predictions.csv, same_subset_metrics.csv, paired_bootstrap.csv, beat_fraction.csv, provider_sensitivity.csv, per_horizon_network_spearman.csv, within_network_decomposition.csv, model_coefficients.csv, feature_recomputation_check.csv, feature_recompute_timing.csv, summary.json).

## 2. Reproduction of headline numbers (pipeline validation)

| Check | n | station-gap ρ | network ρ | slope | R2 | RMSE |
|---|---|---|---|---|---|---|
| Second panel, empirical, direct horizons | 874 | 0.9453 | 0.8049 | 0.9383 | 0.8132 | 0.455 |
| Second panel, empirical, all units | 1446 | 0.7399 | 0.7155 | 0.9503 | 0.2385 | 1.320 |
| Second panel, archived simple (dev-only), all units | 1446 | 0.8191 | 0.6141 | 1.0174 | 0.7836 | 0.704 |
| First panel, empirical, direct supported (external check) | 780 | 0.9341 | 0.9219 | 0.8636 | 0.8120 | 0.362 |

Matches manuscript claims (0.945/0.805/0.938; 0.740/0.715/0.950; 0.819/0.614/1.017; first panel 0.934/0.922/R2 0.812/RMSE 0.362). Fallback count 572/1446, direct 874. Dev-only refit on recomputed features reproduces archived `predicted_loss` to 8.9e-16 and archived coefficients exactly (intercept 2.465180, coefs 0.014061/−2.081635/2.517986/−3.070673/−0.794207).

## 3. Same-unit comparison (the fix: identical subsets for both methods)

Coefficients (equal-network OLS): fit-period (97 networks): intercept 2.1468, coefs 0.01194/−1.5061/2.0478/−2.6296/−0.7170. Dev-only (55 networks): intercept 2.4652, coefs 0.01406/−2.0816/2.5180/−3.0707/−0.7942.

| Subset | Method | station-gap ρ | network ρ | calib slope | calib int | R2 | RMSE |
|---|---|---|---|---|---|---|---|
| direct 874 | empirical | **0.9453** | **0.8049** | **0.9383** | 0.1383 | **0.8132** | **0.455** |
| direct 874 | simple_fitperiod | 0.8459 | 0.2475 | 1.1571 | −0.0465 | 0.6477 | 0.625 |
| direct 874 | simple_devonly | 0.8323 | 0.2769 | 1.0528 | −0.0378 | 0.6769 | 0.599 |
| all 1446 | empirical | 0.7399 | **0.7155** | 0.9503 | 0.2862 | 0.2385 | 1.320 |
| all 1446 | simple_fitperiod | **0.8346** | 0.6046 | 1.1503 | −0.0548 | **0.7564** | **0.747** |
| all 1446 | simple_devonly | 0.8191 | 0.6141 | 1.0174 | −0.0115 | 0.7836 | 0.704 |

## 4. Paired DeltaRho (empirical − simple_fitperiod), 2,000-network bootstrap, 95% CI

| Subset | Δ station-gap ρ (95% CI) | Δ network ρ (95% CI) | Δ calib slope (95% CI) |
|---|---|---|---|
| direct 874 | **+0.0982 [0.0589, 0.1420]** | **+0.5522 [0.3088, 0.8135]** | −0.2210 [−0.3436, −0.0999] |
| all 1446 | −0.0965 [−0.1580, −0.0275] | +0.1088 [−0.1262, 0.3560] | −0.2010 [−0.3195, −0.0842] |

Bootstrap means (empirical / simple): station-gap 0.9449 / 0.8467 (direct), 0.7388 / 0.8353 (all); network 0.7975 / 0.2453 (direct), 0.7066 / 0.5978 (all). Fraction of draws with positive Δ: station-gap 1.000 (direct), 0.002 (all); network 1.000 (direct), 0.810 (all). No degenerate draws skipped.

**Headline**: on the same 874 direct-horizon units, the empirical predictor wins both ranking metrics with CIs excluding zero; on the same 1,446 units the empirical network-level advantage (Δ = +0.109) is directionally positive but its CI includes zero, and the simple model recovers better station-gap ranking (CI excludes zero) because the empirical network-mean fallback (572 constant rows) penalizes pooled rank and destroys within-network rank (below).

## 5. Beat fraction (within-network Spearman, empirical > simple)

| Subset | networks both defined | fraction empirical beats | median within-ρ empirical | median within-ρ simple |
|---|---|---|---|---|
| direct 874 | 57/57 | **0.719** | 0.965 | 0.937 |
| all 1446 | 57/57 | 0.018 | 0.682 | 0.938 |

On the full panel the fallback design (constant network-mean rows) collapses empirical within-network Spearman; on direct-horizon units the empirical predictor orders better inside ~72% of networks.

## 6. Per-horizon network-level Spearman (same units)

| Horizon | n units | networks | empirical | simple_fitperiod | simple_devonly |
|---|---|---|---|---|---|
| 7 | 224 | 57 | **0.9321** | 0.3744 | 0.2771 |
| 30 | 224 | 57 | **0.9157** | 0.1530 | 0.1053 |
| 90 | 220 | 56 | **0.8648** | 0.0429 | 0.0781 |
| 180 | 206 | 53 | **0.6594** | 0.1640 | 0.2025 |

Empirical dominates at every horizon; advantage is largest at short horizons and smallest (still positive) at 180 days.

## 7. Provider-block sensitivity (same units)

| Subset | Block | Empirical ρ-station / ρ-network / slope | Simple-fit-period ρ-station / ρ-network / slope |
|---|---|---|---|
| direct | CZ chmi (15 net, 276) | 0.9699 / 0.9321 / 1.0494 | 0.9295 / 0.7143 / 1.2199 |
| direct | NO nve (10 net, 164) | 0.9593 / 0.8182 / 1.0920 | 0.8624 / 0.6121 / 1.2570 |
| direct | US usgs (32 net, 434) | 0.9136 / 0.7529 / 0.8461 | 0.8131 / 0.1943 / 1.0902 |
| all | CZ chmi (15 net, 478) | 0.6936 / 0.9429 / 1.0985 | 0.9280 / 0.7286 / 1.3165 |
| all | NO nve (10 net, 265) | 0.7722 / 0.7212 / 1.1038 | 0.8747 / 0.7697 / 1.1158 |
| all | US usgs (32 net, 703) | 0.7213 / 0.6360 / 0.8266 | 0.7776 / 0.4597 / 1.0128 |

Direct subset: empirical wins network-level ranking in all three blocks (largest gap in US: 0.753 vs 0.194). Full panel: empirical network-level ahead in CZ and US, slightly behind in NO (0.721 vs 0.770); simple wins station-gap rank in all blocks on the full panel (fallback artifact).

## 8. Within-network decomposition of the empirical predictor (task 5)

| Quantity | direct 874 | all 1446 |
|---|---|---|
| Per-network Spearman median (IQR), empirical | 0.965 (0.944–0.982) | 0.682 (0.660–0.720) |
| Per-network Spearman median (IQR), simple_fitperiod | 0.937 (0.909–0.962) | 0.938 (0.895–0.962) |
| Residualized (network-demeaned) pooled Spearman, empirical | 0.9359 | 0.6073 |
| Residualized pooled Spearman, simple_fitperiod | 0.8958 | 0.9076 |
| Raw pooled Spearman, empirical | 0.9453 | 0.7399 |
| Network-mean-only predictor (in-sample benchmark) pooled ρ | 0.3257 | 0.3091 |

**Answer**: network-level ρ = 0.805 does **not** come from persistent network difficulty. A predictor that only separates network means (perfect in-sample network-mean-only) reaches pooled ρ = 0.326, i.e. between-network difficulty explains little of the ranking. The empirical predictor's residualized (within-network) ρ = 0.936 is nearly identical to its raw pooled ρ = 0.945 on the direct subset, and per-network Spearman is high (median 0.965). The empirical predictor's power is within-network station-horizon ordering, aggregated upward; 0.805 is the network-level expression of that ordering, and it is strongest at short horizons (0.93 at 7 days → 0.66 at 180 days).

## 9. Limitations

- Fit-period simple model fitted on dev + first panel is not fully "frozen": coefficients (2.1468, …) were estimated here from archived outcomes, not from an archived frozen artifact; however the dev-only refit reproduces the archived model bit-exactly, so the code path is faithful.
- Within-network Spearman on the full 1,446 subset is distorted by constant network-mean fallback rows for the empirical predictor (ties); the direct-874 columns are the clean comparison.
- Network bootstrap resamples networks but does not re-estimate the empirical transfer curve or the simple coefficients (both frozen/fitting-period); CIs cover sampling of the 57-network panel only.
- 180-day horizon covers 53 networks (some lack long-gap scored units).
- Provider blocks are small (10–32 networks); block-level ρ are descriptive only.

## 10. How this feeds the revision

- Replaces the unequal-subset comparison (simple on 1,446 vs empirical on 874) with same-unit paired estimates and CIs: empirical wins network-level rank on the direct subset (Δ +0.55, CI excludes 0) and directionally on the full panel (Δ +0.11, CI includes 0); the simple model wins station-gap rank on the full panel only through the fallback artifact.
- Per-horizon table shows the empirical advantage is not an artifact of one horizon.
- Within-network decomposition reframes the network-level 0.805: it reflects within-network ordering, not persistent network difficulty (network-mean-only benchmark ρ = 0.326).
