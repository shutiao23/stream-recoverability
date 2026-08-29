# REPORT — revision v12, task 10, agent b (adversarial pair)

## Task
Fix the conditional-covariance estimand mismatch in the mechanism analysis
(conditional variance in °C² was subtracted directly from realized MAE in °C)
and re-derive the mechanism and incremental-value conclusions with the
Gaussian expected-MAE transform.

## 1. Reproduction of the mechanism claim (existing artifacts)

Recomputed exactly from `results/development_v11/station_gap_outcomes.csv`
+ `nested_lono_predictions.csv` (61-station roster complete at all 7 horizons,
427 rows) and `recovery_scoring/placement_losses.csv` (realized RMSE,
complete operator condition). The recomputed table reproduces the published
`reviewer_completion/mechanism_decomposition.csv` to floating-point precision
(asserted in-script).

Published claim: conditional variance 0.379 → 0.451, realized MAE 0.544 →
4.719, original (unit-mismatched) remainder 0.165 → 4.268. All reproduced.

## 2. Corrected estimand: conditional SD → Gaussian expected MAE and RMSE

For a zero-mean Gaussian error, E|e| = sqrt(2/π)·σ ≈ 0.798·σ and RMSE = σ.
Corrected horizon response (`mechanism_recomputed.csv`):

| gap (d) | cond. var (mean) | SD (mean of √var) | expected MAE | realized MAE | realized RMSE (pooled) | remainder MAE | remainder RMSE |
|---|---|---|---|---|---|---|---|
| 7 | 0.379 | 0.604 | 0.482 | 0.544 | 0.723 | 0.062 | 0.118 |
| 14 | 0.408 | 0.626 | 0.499 | 0.667 | 0.888 | 0.167 | 0.262 |
| 30 | 0.431 | 0.641 | 0.512 | 0.815 | 1.082 | 0.303 | 0.441 |
| 60 | 0.442 | 0.649 | 0.518 | 0.975 | 1.266 | 0.458 | 0.617 |
| 90 | 0.445 | 0.651 | 0.520 | 1.240 | 1.589 | 0.720 | 0.938 |
| 180 | 0.449 | 0.654 | 0.522 | 2.432 | 3.049 | 1.910 | 2.396 |
| 365 | 0.451 | 0.655 | 0.523 | 4.719 | 5.933 | 4.196 | 5.278 |

The corrected saturation claim: SD rises 0.604
→ 0.655 °C and Gaussian expected MAE
0.482 → 0.523 °C while
realized MAE rises 0.544 → 4.719 °C
and realized RMSE 0.723 → 5.933 °C.
Saturation survives but is smaller in relative magnitude than the raw °C²-vs-°C
comparison implied; the 365-day remainder is 4.20 °C
(MAE space) / 5.28 °C (RMSE space), not the
previously claimed 4.268 °C.
Under the manuscript's own aggregation (SD = sqrt of the mean variance) the
corrected bounds are 0.616 → 0.672 °C
and expected MAE 0.491 → 0.536 °C;
mean-of-per-unit-SD is lower by Jensen's inequality (0.604 vs 0.616 at 7 days),
and the corrected conclusions are unchanged under either aggregation.

## 3. Controlled Gaussian simulation (`simulation_gaussian_known.csv`,
`simulation_plugincov.csv`, `simulation_figure.png`)

- Known covariance, zero-mean Gaussian errors (n = 300,000 per configuration,
  4 σ values): realized E|e| matches sqrt(2/π)·σ and realized RMSE matches σ
  to within 0.5% (asserted).
- Plug-in covariance, finite training sample (n = 10…640, 500–3000 replicates,
  n_test = 5000): the plug-in conditional SD is a noisy estimator of σ. Small-n
  raw plug-in under-estimates σ on average (bias and 5–95% band reported;
  e.g. n = 10: mean σ̂ = 0.79·σ,
  under-estimates in 81% of
  replicates); the ridge-regularized plug-in is also below σ at n = 10
  (0.85·σ) but
  over-estimates at larger n (1.03·σ
  at n = 640); the raw plug-in converges to
  0.995·σ at n = 640.
  Direction of finite-sample bias therefore depends on the estimator and sample
  size: it is estimation error, not model error.

## 4. Incremental-value test in MAE space (`incremental_mae_space.csv`)

Same folds (leave-one-network-out) as the published tests; operator feature
transformed to expected-MAE scale c·√risk before fitting, plus a post-hoc
transform of the published out-of-fold predictions.

- Linear nested LONO: raw increment reproduced (0.0171 vs published
  0.01710); MAE-space increment = 0.0198 — still far below the 0.05
  threshold. Negative incremental conclusion survives.
- Mixed model (network random intercept): raw marginal-R² increment reproduced
  (0.0090 vs published 0.00903); MAE-space increment =
  0.0131.
- Learned HGB error model: refit reproduces the current artifact
  (R² 0.7323
  → 0.7432,
  raw increment 0.0109; with the expected-MAE-transformed operator
  feature the increment is 0.0109 (R²
  0.7323
  → 0.7432).
  Post-hoc transform of the published table predictions: increments reported in
  `incremental_mae_space.csv`; the operator's contribution remains small.
  Note: the manuscript's 0.701→0.704 predates the current artifact (0.7323→0.7432,
  reproduced here); either way the increment is ~0.01, far below the 0.05 gate.
- Conclusion: the negative incremental-value result survives the estimand fix
  under every specification tested.

## 5. Corrected interpretation text
`mechanism_interpretation_corrected.md` — 3 paragraphs as requested (Gaussian
optimal-prediction bound; not a MAE lower bound; remainder is a composite of
covariance misspecification, parameter-estimation error, non-Gaussianity,
aggregation, and recovery-model estimation error, and is not identifiable as
model error + drift).

## Files written
- `scripts/rev_v12_t10_covariance_fix_b.py`
- `results/revision_v12/t10_covariance_fix/agent_b/mechanism_recomputed.csv`
- `results/revision_v12/t10_covariance_fix/agent_b/simulation_gaussian_known.csv`
- `results/revision_v12/t10_covariance_fix/agent_b/simulation_plugincov.csv`
- `results/revision_v12/t10_covariance_fix/agent_b/simulation_figure.png`
- `results/revision_v12/t10_covariance_fix/agent_b/mechanism_corrected_curves.png`
- `results/revision_v12/t10_covariance_fix/agent_b/incremental_mae_space.csv`
- `results/revision_v12/t10_covariance_fix/agent_b/mechanism_interpretation_corrected.md`
- `results/revision_v12/t10_covariance_fix/agent_b/REPORT.md`

All numbers above come from the script's own computation on the cited
read-only artifacts; no numbers were taken from the manuscript.
