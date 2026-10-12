# F11 — sensor-noise sensitivity, regenerated under one locked method

The published `results/v17_fitness/step22_robustness/noise_sensitivity.json` was produced before `noise_sensitivity` in `scripts/202_v17_robustness.py` was fixed (commit a9a7ad99cf). In the published version the clean arm used the information-conditioned simple policy while the perturbed certificate arm was evaluated on a different method's error, so part of the published noise effect was a method change. The pre-fix bytes are preserved under `amendments/step22_noise_pre_fix/` (sha256 in `sha256.json`); the numbers below supersede them.

## Headline: old versus new, same locked method

| panel | arm | old published (points) | new, fixed (points) | change | n cases | n evaluated |
|---|---|---|---|---|---|---|
| development | clean | 6.3209 | 5.9839 | -0.3369 | 40,704 | 40,704 |
| development | noisy | 6.2050 | 6.0331 | -0.1720 | 40,704 | 40,704 |
| reserved | clean | 7.0636 | 6.2054 | -0.8582 | 10,820 | 10,820 |
| reserved | noisy | 6.6675 | 6.2186 | -0.4489 | 10,820 | 10,820 |

The sensor-noise movement of the contrast under the fixed method is **development** +0.0491 points (+0.82 %); **reserved** +0.0132 points (+0.21 %). Mean absolute error of the certificate's chosen method, clean versus perturbed: **development** 0.2361 -> 0.2363 °C; **reserved** 0.2077 -> 0.2080 °C.

## Which choice moved each number

Re-instating the two pre-fix choices on the frozen inputs reproduces the published artifact exactly (worst gap 0.0e+00), so the difference below is a code change and not a data change. Only two evaluations moved:

| panel | quantity | evaluated pre-fix | evaluated fixed | pre-fix | fixed |
|---|---|---|---|---|---|
| development | length rule at 70, clean | policy error | certificate_choice error | 0.092549 | 0.089180 |
| development | certificate rule at 70, clean | certificate_abs_error | certificate_choice case error | 0.029341 | 0.029341 |
| development | length rule at 70, perturbed | policy noisy error | certificate_choice noisy error | 0.093146 | 0.089566 |
| development | certificate rule at 70, perturbed | policy noisy error | certificate_choice noisy error | 0.031095 | 0.029235 |
| reserved | length rule at 70, clean | policy error | certificate_choice error | 0.095986 | 0.087404 |
| reserved | certificate rule at 70, clean | certificate_abs_error | certificate_choice case error | 0.025350 | 0.025350 |
| reserved | length rule at 70, perturbed | policy noisy error | certificate_choice noisy error | 0.094666 | 0.086612 |
| reserved | certificate rule at 70, perturbed | policy noisy error | certificate_choice noisy error | 0.027990 | 0.024426 |

`certificate_abs_error` is identical to the certificate's chosen method's case error on every row (40,704 development rows and 10,820 reserved rows, maximum absolute difference 0.0e+00), so the clean certificate rate cannot move and does not.

## Does the qualitative conclusion survive the sensor noise?

- **development**: the 0.15 C independent Gaussian perturbation moves the contrast by +0.0491 points (paired clustered 95% interval [-0.0357, +0.1499] over 40,704 cases, retained set identical to the clean arm), and the change is not distinguishable from zero. The perturbed contrast itself is 6.0331 points with clustered 95% interval [5.3118, 6.6939], so it stays positive with a clustered 95% interval above zero.
- **reserved**: the 0.15 C independent Gaussian perturbation moves the contrast by +0.0132 points (paired clustered 95% interval [-0.1747, +0.1851] over 10,820 cases, retained set identical to the clean arm), and the change is not distinguishable from zero. The perturbed contrast itself is 6.2186 points with clustered 95% interval [4.7978, 7.3304], so it stays positive with a clustered 95% interval above zero.

Timing beats outage length by roughly six points on both panels in every arm, which is the sense in which the qualitative conclusion survives the sensor error.

## Extra error models at the same locked method

Contrast = (consequential-error rate of the outage-length rule at 70 % retention) - (rate of the certificate rule), in percentage points, both ranked with the frozen certificate and evaluated with the perturbed error column of the certificate's chosen reconstruction. Intervals are clustered by network, 1000 bootstrap draws.

| panel | scenario | spec | contrast | 95% CI | change vs clean | n evaluated | n retained | retained set == clean |
|---|---|---|---|---|---|---|---|---|
| development | clean | unperturbed reference series | 5.9839 | [5.2246, 6.6340] | +0.0000 | 40,704 | 28,493 | True |
| development | iid_0.15 | replica of the frozen 0.15 C iid Gaussian process (validation anchor) | 6.0331 | [5.3118, 6.6939] | +0.0491 | 40,704 | 28,493 | True |
| development | bias_p0.15 | +0.15 C all year | 5.9278 | [5.2039, 6.5826] | -0.0562 | 40,704 | 28,493 | True |
| development | bias_p0.30 | +0.30 C all year | 6.0611 | [5.3286, 6.7853] | +0.0772 | 40,704 | 28,493 | True |
| development | bias_p0.50 | +0.50 C all year | 6.0120 | [5.2327, 6.7219] | +0.0281 | 40,704 | 28,493 | True |
| development | bias_m0.15 | -0.15 C all year | 6.0752 | [5.3210, 6.7369] | +0.0913 | 40,704 | 28,493 | True |
| development | bias_m0.30 | -0.30 C all year | 5.9769 | [5.2439, 6.6747] | -0.0070 | 40,704 | 28,493 | True |
| development | bias_m0.50 | -0.50 C all year | 6.0015 | [5.2170, 6.7769] | +0.0175 | 40,704 | 28,493 | True |
| development | ar1_r0.70_sd0.15 | stationary AR(1) daily error, rho 0.7, marginal sd 0.15 C | 5.9523 | [5.2213, 6.5817] | -0.0316 | 40,704 | 28,493 | True |
| development | step_p0.30_midyear | +0.30 C from day-of-year 183 (device replaced mid-year) | 6.2121 | [5.5051, 6.9757] | +0.2281 | 40,704 | 28,493 | True |
| development | drift_0_to_p0.30 | monotone drift 0 to +0.30 C across the calendar year | 5.9208 | [5.1958, 6.6458] | -0.0632 | 40,704 | 28,493 | True |
| reserved | clean | unperturbed reference series | 6.2054 | [4.7464, 7.4246] | +0.0000 | 10,820 | 7,574 | True |
| reserved | iid_0.15 | replica of the frozen 0.15 C iid Gaussian process (validation anchor) | 6.2186 | [4.7978, 7.3304] | +0.0132 | 10,820 | 7,574 | True |
| reserved | bias_p0.15 | +0.15 C all year | 6.1526 | [4.7502, 7.3734] | -0.0528 | 10,820 | 7,574 | True |
| reserved | bias_p0.30 | +0.30 C all year | 6.2054 | [5.0800, 7.3023] | +0.0000 | 10,820 | 7,574 | True |
| reserved | bias_p0.50 | +0.50 C all year | 6.0074 | [4.7405, 7.1347] | -0.1980 | 10,820 | 7,574 | True |
| reserved | bias_m0.15 | -0.15 C all year | 6.4959 | [5.1583, 7.7120] | +0.2905 | 10,820 | 7,574 | True |
| reserved | bias_m0.30 | -0.30 C all year | 6.6940 | [5.4545, 7.8705] | +0.4885 | 10,820 | 7,574 | True |
| reserved | bias_m0.50 | -0.50 C all year | 7.2353 | [6.1980, 8.2156] | +1.0298 | 10,820 | 7,574 | True |
| reserved | ar1_r0.70_sd0.15 | stationary AR(1) daily error, rho 0.7, marginal sd 0.15 C | 6.1922 | [4.7177, 7.4761] | -0.0132 | 10,820 | 7,574 | True |
| reserved | step_p0.30_midyear | +0.30 C from day-of-year 183 (device replaced mid-year) | 6.4299 | [5.1702, 7.7193] | +0.2245 | 10,820 | 7,574 | True |
| reserved | drift_0_to_p0.30 | monotone drift 0 to +0.30 C across the calendar year | 6.1394 | [4.7030, 7.4483] | -0.0660 | 10,820 | 7,574 | True |

The clean error column is the same in every row of a panel (the clean errors do not depend on the error model) and each scenario's error column is finite exactly where the clean column is, which is what keeps the retained set fixed. The perturbation does move the *absolute* error even where it leaves the contrast alone: on development the mean absolute error of the certificate's chosen method rises from 0.2361 C clean to 0.2976 C under `bias_p0.50`. Full columns in `scenario_contrasts.csv`.

## Checks run in code

- Rebuilt case table versus frozen `step3_cases/cases.parquet`: 51,524 keys compared, 392,214 values, max absolute difference 0.0e+00, NaN-position mismatches 0.
- The replica error process (`iid_0.15`, frozen seed tag `sensor`) reproduces the frozen `abserr_noisy_*` columns exactly, so the extended error models run through the same instrument.
- The replica branch reproduces the fixed-function iid contrast exactly: development 6.033061 vs 6.033061 points; reserved 6.218643 vs 6.218643 points.
- The retained case set at 70 % retention is asserted identical between the clean arm and every perturbed arm, for both the certificate rule and the outage-length rule (all rows above are `True`).
- The retained-set mirror used for those assertions is asserted equal to the imported `_rate_locked` rate for every arm (max absolute gap 0.0e+00).

## Error processes as realized

Statistics are computed inside each sampled station-year and averaged across series; a constant process has no within-series sd and no defined autocorrelation.

| scenario | spec | within-series sd (C) | mean abs offset (C) | lag-1 autocorr | constant series |
|---|---|---|---|---|---|
| iid_0.15 | replica of the frozen 0.15 C iid Gaussian process (validation anchor) | 0.1504 | 0.0068 | +0.002 | 0/60 |
| bias_p0.15 | +0.15 C all year | 0.0000 | 0.1500 | n/a | 60/60 |
| bias_p0.30 | +0.30 C all year | 0.0000 | 0.3000 | n/a | 60/60 |
| bias_p0.50 | +0.50 C all year | 0.0000 | 0.5000 | n/a | 60/60 |
| bias_m0.15 | -0.15 C all year | 0.0000 | 0.1500 | n/a | 60/60 |
| bias_m0.30 | -0.30 C all year | 0.0000 | 0.3000 | n/a | 60/60 |
| bias_m0.50 | -0.50 C all year | 0.0000 | 0.5000 | n/a | 60/60 |
| ar1_r0.70_sd0.15 | stationary AR(1) daily error, rho 0.7, marginal sd 0.15 C | 0.1496 | 0.0147 | +0.699 | 0/60 |
| step_p0.30_midyear | +0.30 C from day-of-year 183 (device replaced mid-year) | 0.1502 | 0.1505 | +0.995 | 0/60 |
| drift_0_to_p0.30 | monotone drift 0 to +0.30 C across the calendar year | 0.0870 | 0.1500 | +1.000 | 0/60 |

## How hard each process hits the endpoint

`H(truth + eps) - H(truth)` over every case, where `H` is the hottest-30-day mean. The same daily sd does not mean the same perturbation of a thirty-day mean.

| scenario | spec | mean delta (C) | sd of delta (C) | sd relative to iid 0.15 |
|---|---|---|---|---|
| iid_0.15 | replica of the frozen 0.15 C iid Gaussian process (validation anchor) | +0.0012 | 0.0275 | 1.00x |
| bias_p0.15 | +0.15 C all year | +0.1500 | 0.0000 | 0.00x |
| bias_p0.30 | +0.30 C all year | +0.3000 | 0.0000 | 0.00x |
| bias_p0.50 | +0.50 C all year | +0.5000 | 0.0000 | 0.00x |
| bias_m0.15 | -0.15 C all year | -0.1500 | 0.0000 | 0.00x |
| bias_m0.30 | -0.30 C all year | -0.3000 | 0.0000 | 0.00x |
| bias_m0.50 | -0.50 C all year | -0.5000 | 0.0000 | 0.00x |
| ar1_r0.70_sd0.15 | stationary AR(1) daily error, rho 0.7, marginal sd 0.15 C | +0.0041 | 0.0619 | 2.25x |
| step_p0.30_midyear | +0.30 C from day-of-year 183 (device replaced mid-year) | +0.2742 | 0.0583 | 2.12x |
| drift_0_to_p0.30 | monotone drift 0 to +0.30 C across the calendar year | +0.1729 | 0.0166 | 0.61x |

## What was and was not changed

Read-only: every `results/v17_fitness/**` artifact, the sealed confirmation inputs, `paper/**`.
New: `scripts/246_wrr_noise_recompute.py`, `src/stream_recoverability/experiments/wrr_submission_ready/noise_scenarios.py`, and this amendment directory. `scripts/202_v17_robustness.py` is imported, never edited; its sha256 is recorded in `summary.json`.

## Caveats

- the perturbation is applied to the reference series and to the observed days of the completed year; the estimator's fill values stay those fitted on the clean record (the convention of the frozen construction), so this measures sensitivity to reference-series error, not error propagating into the reconstruction
- the error processes are independent across station-years and share one draw per station-year across that year's outage realizations, exactly as the frozen iid process does
- the whole-year bias cancels between estimate and reference on observed days and does not cancel across filled days: it raises the absolute error without moving the contrast much; a bias that also shifted the filled days would be a larger perturbation and is not claimed here
- clustered intervals resample networks (development: 110, reserved: 36) with 1000 draws; they describe between-network uncertainty, not the uncertainty of one station
- the step is placed at day-of-year 183 (2 July) for every year, so it always lands in the warm season; a step at another date is a different scenario
- the ranking is the frozen certificate's, so the retained case set is fixed by design in every arm (and is asserted identical). This measures whether sensor error changes the tolerance-exceedance contrast *among the retained cases*, not whether a certificate rebuilt from perturbed data would retain a different set; the latter cannot be compared on the same case set and is out of scope for this amendment
- the AR(1) and mid-year-step processes perturb the thirty-day endpoint roughly twice as strongly as the iid process at the same marginal daily sd (endpoint table above), so their null results are the stronger evidence; the whole-year biases are exact constant shifts of the endpoint rather than spreads
