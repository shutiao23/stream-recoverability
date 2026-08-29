# REPORT — Agent B (adversarial pair): same-unit paired baseline comparison, second panel

Task: `t01_paired_comparison` — 57-network outcome-disjoint second confirmation panel.
All numbers below were produced by `scripts/rev_v12_t01_paired_comparison_b.py` (run with
`PYTHONPATH=$PWD/src python3`, seed 20260828, 2000 network bootstrap draws). Nothing was
taken from the paper or from stored summaries except the comparison columns in `t1_*`
(stored values are reproduced exactly, shown side by side).

## 1. Reproduction of second-panel headline numbers (T1)

Equal-network-weighted calibration; same definition as `point_prediction_metrics`.

| subset | station-gap rho | network rho | slope | intercept | R2 | RMSE | stored (summary.json) |
|---|---|---|---|---|---|---|---|
| direct 874 (gap in {7,30,90,180}) | 0.945345 | 0.804900 | 0.938331 | 0.138323 | 0.81323 | 0.45535 | 0.945345 / 0.804900 / 0.938331 |
| all 1446 | 0.739923 | 0.715452 | 0.950251 | 0.286205 | 0.23847 | 1.32011 | 0.739923 / 0.715452 / 0.950251 |

Reproduction is exact to all printed digits. R2/RMSE were not in the stored summary and are new.

## 2. Fitting-period-only simple-descriptor predictor (T2)

- Feature code path: exact reuse of `route_a_confirmation.simple_predictors` (scripts 115/124/131):
  training-year-split anomalies, `acf_only(phi, gap)`, year-block-LOO `donor_r2_only`,
  `additive_d_over_4_heuristic(donor_r2, rho_{gap/4})`, `nearest_donor_correlation`, computed on
  panels from `results/development_v11/second_confirmation/daily_qc/` (42 networks) with the
  script-131 `panel_path` fallback to `confirmation_daily_qc/` (15 chmi networks, documented in
  `t2_check_summary.json`).
- Column set: `gap_length, acf_only, donor_r2_only, additive_d_over_4_heuristic,
  nearest_donor_correlation` — the LONO-selected simple model
  (`nested_lono_predictions.csv selected_simple_model` mode). Season columns are not in the
  model (consistent with scripts 115/131).
- Coefficients: equal-network-weighted OLS (weights 1/count, matching `fit_route_a_model`/script-124 `_weighted_fit`).

| fit | intercept | gap_length | acf_only | donor_r2_only | d/4 heuristic | nearest_donor_corr | n / networks |
|---|---|---|---|---|---|---|---|
| development only (validation) | 2.465180 | 0.014061 | -2.081635 | 2.517986 | -3.070673 | -0.794207 | 1260 / 55 |
| **fitting period (dev + first panel)** | **2.146826** | **0.011943** | **-1.506063** | **2.047831** | **-2.629572** | **-0.716972** | **2700 / 97** |

Validation: dev-only fit reproduces the stored route-A model exactly (intercept and coefficient
differences = 0.0); recomputed features match stored features to <= 1.1e-16; dev-only model
predictions match stored route-A predictions to <= 8.9e-16; stored route-A metrics reproduced
(1446: 0.819095 / 0.614078 / 1.017432). Second-panel predictions: `second_panel_simple_predictions.csv` (1446 units, 57 networks).

## 3. Same-unit paired comparison (T3)

Same units, same networks, both methods.

| subset | method | station rho | network rho | slope | intercept | R2 | RMSE |
|---|---|---|---|---|---|---|---|
| 874 | empirical | 0.945345 | 0.804900 | 0.938331 | 0.138323 | 0.81323 | 0.45535 |
| 874 | simple (fit-period) | 0.845875 | 0.247537 | 1.157066 | -0.046502 | 0.64773 | 0.62537 |
| 1446 | empirical | 0.739923 | 0.715452 | 0.950251 | 0.286205 | 0.23847 | 1.32011 |
| 1446 | simple (fit-period) | 0.834626 | 0.604615 | 1.150317 | -0.054773 | 0.75641 | 0.74661 |

Paired DeltaRho (rho_empirical - rho_simple), 2000-draw network bootstrap, paired on identical draws:

| subset | DeltaRho station [95% CI] | P(>0) | DeltaRho network [95% CI] | P(>0) |
|---|---|---|---|---|
| 874 | +0.09947 [0.06084, 0.14857] | 1.000 | +0.55736 [0.30366, 0.82082] | 1.000 |
| 1446 | -0.09470 [-0.15693, -0.02425] | 0.006 | +0.11084 [-0.12366, 0.36595] | 0.828 |

Marginal bootstrap CIs (874): empirical network rho 0.6663–0.9007, simple network rho -0.0233–0.5026.

Fraction of networks where within-network empirical rho > simple rho: 874 → 41/57 (0.7193),
median per-network delta +0.0210; 1446 → 1/57 (0.0175), median delta -0.2406.

Provider blocks (network-level rho; empirical / simple): 874: US 0.75293 / 0.19428,
CZ 0.93214 / 0.71429, NO 0.81818 / 0.61212; 1446: US 0.63600 / 0.45968, CZ 0.94286 / 0.72857,
NO 0.72121 / 0.76970. Empirical leads in 5 of 6 block/subset cells; NO on 1446 is the exception.
Full table incl. station-gap rho, slope, R2, RMSE: `t3_provider_block_metrics.csv`.

## 4. Per-horizon network-level Spearman (T4), same subsets

| horizon | n units | empirical station / network | simple station / network |
|---|---|---|---|
| 7 | 224 | 0.913291 / 0.932072 | 0.408632 / 0.374449 |
| 30 | 224 | 0.903917 / 0.915673 | 0.255751 / 0.152969 |
| 90 | 220 (56 net) | 0.872911 / 0.864798 | 0.277061 / 0.042925 |
| 180 | 206 (53 net) | 0.682676 / 0.659410 | 0.338791 / 0.164006 |

Empirical dominates at every horizon (full metrics incl. slope/R2/RMSE: `t4_per_horizon_metrics.csv`).

## 5. Within-network decomposition of the empirical predictor (T5)

| subset | method | per-network rho median (Q1, Q3) | residualized pooled rho | station rho | network rho | R2 | RMSE |
|---|---|---|---|---|---|---|---|
| 874 | empirical | 0.9650 (0.9441, 0.9824) | 0.93590 | 0.945345 | 0.804900 | 0.81323 | 0.45535 |
| 874 | simple | 0.9371 (0.9091, 0.9624) | 0.89577 | 0.845875 | 0.247537 | 0.64773 | 0.62537 |
| 874 | network-mean-only | — | — | 0.32570 | 1.00000* | 0.10679 | 0.99580 |
| 1446 | empirical | 0.6825 (0.6597, 0.7205) | 0.60729 | 0.739923 | 0.715452 | 0.23847 | 1.32011 |
| 1446 | simple | 0.9381 (0.8947, 0.9616) | 0.90755 | 0.834626 | 0.604615 | 0.75641 | 0.74661 |
| 1446 | network-mean-only | — | — | 0.30911 | 1.00000* | 0.08649 | 1.44585 |

*Network-mean-only network rho is tautologically 1 (it is the observed network mean), so the
informative comparison is at station-gap level.

Interpretation: the network-level 0.805 does NOT reflect persistent network difficulty only.
Network-mean-only (pure between-network difficulty) explains station-gap rho 0.326, whereas the
empirical predictor reaches 0.945 with a residualized (within-network, network means removed)
rho of 0.936 and per-network rho median 0.965 (57/57 networks computable). The empirical
predictor thus orders stations within networks; network-level aggregation mildly compresses it.
On the full 1446 the empirical predictor's within-network rho collapses (0.683 median, residualized
0.607) precisely on the fallback units (14/60/365) where the prediction is the within-network
constant (network-mean fallback); the direct-horizon subset is the fair, supported comparison.

## 6. How this feeds the revision

1. The original "simple 0.819/0.614/1.017" comparison was NOT on the same subset as the
   empirical 0.740/0.715/0.950 (stored simple was fit on development only and compared at face
   value). With same units and a fitting-period-only fit, the direct-horizon comparison is
   unambiguous: empirical wins on station-gap rho (+0.099, CI excludes 0), network rho
   (+0.557, CI excludes 0), slope-to-1, R2, RMSE, and in 72% of networks.
2. On all 1446 the simple model is better at station-gap level (DeltaRho -0.095, CI excludes 0)
   but the empirical predictor is still favored at network level (+0.111, CI includes 0): the
   statement must be subset-scoped — the empirical advantage lives on the direct-horizon
   supported units, and the fallback (network-mean) units should be reported separately or
   dropped, not pooled.
3. The decomposition (T5) supports a within-network claim: rank ordering is genuine per
   network, not an artifact of network difficulty, so the network-level 0.805 understates the
   empirical predictor's ordering skill.

## 7. Limitations

- Bootstrap CIs are network-cluster paired; they cover resampling uncertainty, not
  model-selection or feature-reconstruction uncertainty.
- 15/57 panels (all chmi) come from the first-panel QC fallback (same code path as script 131);
  feature values were verified bit-identical to the stored route-A features there.
- The simple model's slope >1 on 874 (1.157) is a fitting-period vs evaluation domain shift;
  the dev-only variant gives slope 1.053 — refitting on dev+first does not fix slope inflation.
- R2/RMSE are unweighted unit-level; slope/intercept are equal-network-weighted.
- Per-horizon 90/180 use 56/53 networks (some networks lack those units); per-network rho
  uses >=2 units per network (57/57 valid on both subsets).

## Artifacts (all under `results/revision_v12/t01_paired_comparison/agent_b/`)

- `t1_headline_reproduction.csv`, `crosscheck_stored_route_a_simple.csv`
- `t2_coefficients.json`, `t2_fit_validation.json`, `t2_check_summary.json`,
  `t2_feature_and_model_check.csv`, `second_panel_simple_predictions.csv`
- `t3_paired_metrics.csv`, `t3_within_network_beat_fraction.csv`, `t3_bootstrap_draws.csv` (4000 rows),
  `t3_bootstrap_ci.csv`, `t3_provider_block_metrics.csv`
- `t4_per_horizon_metrics.csv`, `t5_within_network_decomposition.csv`
- `analysis_summary.json` (machine-readable, all of the above)
- Script: `scripts/rev_v12_t01_paired_comparison_b.py` (runtime ~3 min)
