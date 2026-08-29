# Corrected mechanism interpretation: the conditional SD is a Gaussian optimal-prediction bound, not a MAE lower bound

The mechanism analysis compares an analytic risk quantity with a realized error
quantity, and the original comparison mixed units: `complete_operator_risk` is a
conditional *variance* in °C², while `realized_loss` is a conditional *mean
absolute error* in °C. The estimand-correct comparison must put the analytic
quantity on the realized-loss scale first. Under the operator's own Gaussian
covariance model, the optimal predictor's error is zero-mean Gaussian with
conditional standard deviation σ, so its RMSE is σ and its expected absolute
error is E|e| = sqrt(2/π)·σ ≈ 0.798σ. On the fixed 61-station roster the
conditional SD rises from 0.604 °C at 7 days to 0.655 °C at 365 days
(from the reported variances 0.379→0.451 °C²), and the Gaussian
expected MAE rises from 0.482 to 0.523 °C. Realized MAE rises from
0.544 to 4.719 °C and realized RMSE (placement-pooled) from 0.723
to 5.933 °C. The qualitative mechanism claim survives: the conditional
risk still saturates (σ moves by 0.051 °C) while realized error
grows by an order of magnitude. But the saturation is smaller in relative terms
than the raw variance comparison suggested, and the realized-error floor
0.523 °C at 365 days is closer to realized error than the previously
reported "0.451 °C".

After the corrected transform, the remainder shrinks: the 7-day remainder is
0.54 − 0.482 = 0.062 °C in MAE space (against 0.165 °C under
the unit-mismatched subtraction) and grows to 4.72 − 0.523 =
4.20 °C at 365 days; in RMSE space it grows from 0.723 − 0.604 =
0.118 °C to 5.933 − 0.655 = 5.28 °C. A controlled
Gaussian simulation confirms the transform: with known covariance and
zero-mean Gaussian errors, realized E|e| matches sqrt(2/π)·σ and realized RMSE
matches σ to three digits. The same simulation shows that the plug-in
conditional SD estimated from a finite training sample is itself a noisy
estimator of σ: with n = 10 training rows the raw
plug-in SD averages 0.79σ
(under-estimating in 81% of
replicates, 5–95% band 0.42–
1.19); a
ridge-regularized plug-in is also below σ at small n (0.85σ
at n = 10) but over-estimates at larger n
(1.03σ at n = 640);
the raw plug-in converges to 0.995σ.

What the corrected comparison can and cannot claim. It can claim that the
conditional SD is a Gaussian optimal-prediction bound: under the operator's
covariance model and Gaussianity, no predictor can achieve RMSE below σ or MAE
below sqrt(2/π)·σ, and the realized errors of the recovery model are consistent
with (indeed above) that floor. It cannot claim that the difference
(MAE − sqrt(2/π)·σ, or RMSE − σ) is identifiable as "model error plus seasonal
drift". The remainder is a composite of at least five estimand-level
components: (i) covariance misspecification — the trained covariance is a model
of the gap process, not the true process; (ii) parameter estimation error —
the conditional SD is itself a plug-in estimate whose finite-sample bias can
run in either direction depending on the estimator and the sample size (raw
plug-in under-estimates at every n; ridge regularization under-estimates at
small n and over-estimates at larger n, per the simulation above); (iii)
non-Gaussianity — the sqrt(2/π) factor is exact only for Gaussian errors, and
heavy-tailed recovery-model errors make the realized MAE exceed the Gaussian
expectation even at correct σ; (iv) aggregation — the horizon means pool
stations, seasons, placements, and networks with different conditional
variances, so the mean realized MAE exceeds the transform of the mean variance
by Jensen's inequality; and (v) estimation error of the recovery model itself —
realized loss is the empirical error of a fitted XGBoost with finite training
data, which is bounded below by (i.e. above) the optimal predictor's risk.
The growing remainder therefore documents a growing gap between the fitted
recovery model and the Gaussian-optimal predictor, but it does not
arithmetically decompose into model error and drift, and it cannot be read as
evidence about drift specifically.
