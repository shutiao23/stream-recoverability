# REPORT — revision v12, t10 covariance-fix, agent A (adversarial pair)

## Bottom line

1. **Estimand established from source code.** The published mechanism
   numbers (conditional risk 0.379 -> 0.451 degC, realized MAE 0.544 ->
   4.719 degC, remainder 0.165 -> 4.268 degC) were reproduced exactly from
   `results/development_v11/reviewer_completion/mechanism_decomposition.csv`.
   The quantity labeled "conditional-variance lower bound" is
   `complete_operator_risk`, which the operator code
   (`src/stream_recoverability/analysis/conditional_observability.py`,
   `expected_gaussian_mae`) defines as the **expected Gaussian MAE**,
   sqrt(2/pi) x (mean per-day conditional SD). It is neither a variance nor
   a conditional SD. The paper's mechanism narrative therefore mislabels the
   estimand, and the "remainder as model error + drift" interpretation is
   overclaimed; the arithmetic itself is already MAE-consistent.

2. **Corrected horizon response (61 stations, all 7 horizons).** See
   `mechanism_horizon_corrected.csv` and `mechanism_horizon_response.png`.

   | days | cond SD | exp. MAE sqrt(2/pi)SD | realized MAE | realized RMSE | rem MAE | rem RMSE |
   |------|---------|------------------------|--------------|---------------|---------|----------|
      | 7 | 0.475 | 0.379 | 0.544 | 0.631 | 0.165 | 0.156 |
   | 14 | 0.512 | 0.408 | 0.667 | 0.798 | 0.258 | 0.287 |
   | 30 | 0.540 | 0.431 | 0.815 | 0.989 | 0.384 | 0.450 |
   | 60 | 0.554 | 0.442 | 0.975 | 1.188 | 0.534 | 0.634 |
   | 90 | 0.558 | 0.445 | 1.240 | 1.490 | 0.795 | 0.932 |
   | 180 | 0.563 | 0.449 | 2.432 | 2.849 | 1.983 | 2.286 |
   | 365 | 0.565 | 0.451 | 4.719 | 5.755 | 4.268 | 5.190 |
   If the published column is read literally as an SD (review reading), the
   corrected expected MAE is sqrt(2/pi)x0.379=0.303 degC (7 d) and
   sqrt(2/pi)x0.451=0.360 degC (365 d), with MAE remainders 0.242 and 4.359
   degC. Under the code reading the remainder is unchanged from the paper
   (0.165 -> 4.268 degC) but is correctly a MAE-scale excess over the
   Gaussian bound.

3. **Controlled Gaussian simulation** (`gaussian_known_covariance_simulation.csv`,
   `gaussian_plug_in_covariance_simulation.csv`, `simulation_figure.png`):
   with a known covariance and zero-mean Gaussian errors, Monte Carlo
   confirms E|e| = sqrt(2/pi) sigma and RMSE = sigma to <0.3% at n=10,000.
   With plug-in covariance estimated from M training pairs, the estimated
   conditional SD is downward-biased for small M (e.g., rho=0.9, M=5: mean
   ratio 0.71, underestimating 93% of replications; rho=0.5, M=5: mean ratio
   0.83, underestimating 82%), converging to the truth by M=1000. This is
   the finite-sample under-estimation channel that contributes to the
   realized-vs-bound gap.

4. **Incremental-value conclusion survives.** The operator's increment was
   recomputed in MAE-space on the same leave-one-network-out folds:
   - Nonlinear learned error model: R2 without/with operator = 0.7323 ->
     0.7432 (replication of `reviewer_completion/learned_error_model_predictions.csv`
     is exact, prediction-identical), increment 0.0109; under the
     expected-MAE transform (sqrt(2/pi) x column) and the SD-scale transform
     (column/sqrt(2/pi)) the increment is unchanged (0.0109) because a
     positive rescaling of a single feature cannot change tree splits.
   - Nested linear increment: 0.017096 as published (r2 0.679926 ->
     0.697023); refitting on the same leave-one-network-out folds with the
     fold-specific selected simple model and the scaled operator gives
     predictions identical to the published column (max abs diff ~1e-14) and
     an identical increment for the raw, expected-MAE, and SD-scale variants.
   - Network-random-intercept mixed model: marginal increment 0.009025 and
     conditional increment 0.001239 as published, unchanged under the
     transform (features are standardized before fitting).
   All increments remain far below the 0.05 threshold; the negative
   incremental conclusion does not depend on the estimand scale.

5. **Corrected interpretation text** (`corrected_mechanism_interpretation.md`)
   explains what the conditional SD can and cannot claim: a Gaussian
   optimal-prediction bound, not a general MAE lower bound; the remainder is
   not identifiable as model error + drift because it also contains
   covariance misspecification, parameter estimation error, non-Gaussianity,
   aggregation, and finite-sample error.

## Files written (namespace results/revision_v12/t10_covariance_fix/agent_a/)

- mechanism_replication_check.csv — exact reproduction of the published
  mechanism table plus realized RMSE
- mechanism_horizon_corrected.csv — corrected estimand decomposition by horizon
- mechanism_horizon_response.png — corrected horizon figure
- gaussian_known_covariance_simulation.csv — E|e| and RMSE under known covariance
- gaussian_plug_in_covariance_simulation.csv — plug-in covariance bias table
- simulation_figure.png — two-panel simulation figure
- incremental_value_mae_space.csv — operator increment tests (raw and transformed)
- corrected_mechanism_interpretation.md — corrected mechanism text for the manuscript
- reference_numbers.json — published increments used as reference
- REPORT.md — this file

## Methods and reproducibility

- Python: 3.11.7; numpy 1.26.4; pandas 2.1.4;
  sklearn sklearn; statsmodels
  statsmodels
- Seed: 0; MC repetitions: 3000 (plug-in), 2000 (known covariance)
- No existing files were modified; all inputs read-only from
  results/development_v11/.
