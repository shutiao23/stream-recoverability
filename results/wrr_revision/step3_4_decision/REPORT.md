# WRR Steps 3–4: benefit predictors and pre-fixed adopt/reject

Archived v14 P0 tables for the **current published recoverer**, plus Step-2
fair-recovery scores where they exist. Endpoint is placement-level MAE
benefit \(B = \mathrm{MAE}_\text{climatology} - \mathrm{MAE}_\text{model}\).
All-default is the required competitor (net \(B = 0\)). Spearman is not used
as a success criterion.

Predictors and the duration switch were fit on fitting-year history.
Each \(\tau\) was frozen by maximising historical net \(B\) on that same
history table, then applied once to outer evaluation placements.
Unsupported hierarchical-mean predictions map to reject.

Outputs live in this directory (`policy_metrics_*.csv`, `chosen_tau_*.csv`,
`placement_predictions_*.csv`, `reliability_*.csv`).

## 1. Identity: `diff` versus seasonal empirical

On evaluation rows where both exist, \(\max|\texttt{diff\_prediction} - \texttt{seasonal\_empirical}| = 8.88 \times 10^{-16}\)
on both `p0_first` and `p0_second` (`summary.json` field
`diff_equals_empirical_max_abs`; construction identity
`diff = default_difficulty - risk` is exactly 0).

They are the same estimator: station/duration/season mean of historical
benefit, with the same fallbacks. 365-day rows are missing from fitting
history, so both series are NaN there (2,880 first-panel rows, 2,299
second-panel rows). Those rows are unsupported and are rejected.

## 2. Evaluation policy, all placements

Rule reported below is `mean_gt_tau_supported_only` (adopt if predicted
benefit \(> \tau\) and, for `diff` / `r6_diff` / `seasonal_empirical`, the
hierarchical mean is supported at station or network×season). Net \(B\) is
the mean over **all** evaluation placements, with rejected cases scored as
0. All-default net is 0 by definition.

### p0_first (n = 28,728)

All-reconstruct net \(B = +0.122\) (already beats all-default). Harmful
share if every placement is reconstructed: 31.0%.

| predictor | history \(\tau\) | adopt rate | harmful among adopted | net \(B\) all cases | vs all-reconstruct | beats all-default? |
|---|---:|---:|---:|---:|---:|---|
| diff | 0.0 | 0.712 | 0.139 | **+0.487** | +0.122 | **yes** |
| r6_diff | 0.0 | 0.723 | 0.137 | +0.496 | +0.122 | **yes** |
| default_difficulty | −1.0 | 0.900 | 0.240 | +0.372 | +0.122 | **yes** |
| neg_risk | −1.0 | 0.573 | 0.115 | +0.415 | +0.122 | **yes** |
| seasonal_empirical | 0.0 | 0.712 | 0.139 | +0.487 | +0.122 | **yes** (identical to diff) |
| switch | −1.0 | 0.775 | 0.156 | +0.499 | +0.122 | **yes** |
| ridge_covariate | −0.1 | 0.742 | 0.145 | +0.498 | +0.122 | **yes** |

`mean_gt_tau` without the support gate is only slightly more aggressive
for diff (adopt 0.730, net +0.498). The conservative historical 0.2-quantile
rule also beats all-default (adopt 0.376, net +0.279, harmful 0.115).

### p0_second (n = 28,557)

All-reconstruct net \(B = -0.111\) (loses to all-default). Harmful share
if every placement is reconstructed: 36.4%. This is the panel where a
reject option can matter.

| predictor | history \(\tau\) | adopt rate | harmful among adopted | net \(B\) all cases | vs all-reconstruct | beats all-default? |
|---|---:|---:|---:|---:|---:|---|
| diff | 0.0 | 0.686 | 0.178 | **+0.409** | −0.111 | **yes** |
| r6_diff | 0.0 | 0.712 | 0.189 | +0.407 | −0.111 | **yes** |
| default_difficulty | 0.5 | 0.868 | 0.307 | +0.200 | −0.111 | **yes** |
| neg_risk | −1.0 | 0.489 | 0.164 | +0.306 | −0.111 | **yes** |
| seasonal_empirical | 0.0 | 0.686 | 0.178 | +0.409 | −0.111 | **yes** (identical to diff) |
| switch | −1.0 | 0.789 | 0.221 | +0.401 | −0.111 | **yes** |
| ridge_covariate | −0.2 | 0.739 | 0.197 | +0.411 | −0.111 | **yes** |

Every listed predictor’s frozen `mean_gt_tau_supported_only` rule beats
all-default on pooled MAE placements. Diff/seasonal_empirical, r6_diff,
switch, and ridge are within about 0.01 °C of each other. Default
difficulty is the weakest (still positive) because climatology MAE is
almost always \(> \tau\) and the rule therefore adopts too many long gaps.

Duration-stratified diff rule (same frozen \(\tau = 0\), supported only),
from `placement_predictions_*.csv`:

| duration | p0_first net | p0_first adopt | p0_second net | p0_second adopt |
|---:|---:|---:|---:|---:|
| 7 | +0.979 | 1.000 | +0.906 | 0.997 |
| 14 | +0.848 | 1.000 | +0.754 | 0.989 |
| 30 | +0.679 | 0.983 | +0.548 | 0.968 |
| 60 | +0.439 | 0.887 | +0.304 | 0.834 |
| 90 | +0.236 | 0.671 | +0.112 | 0.532 |
| 180 | **+0.0165** | 0.143 | **−0.0159** | 0.072 |
| 365 | 0 (all reject) | 0 | 0 (all reject) | 0 |

The pooled win is carried by short and medium gaps. 365-day rows have no
history support and contribute exactly the all-default score.

## 3. Chosen \(\tau\) from history

From `chosen_tau_p0_first.csv` and `chosen_tau_p0_second.csv`
(`selection = history_max_net`). Metrics in those files are **history**
net benefit used to pick \(\tau\), not evaluation performance.

| predictor | p0_first \(\tau\) | p0_first history net | p0_second \(\tau\) | p0_second history net |
|---|---:|---:|---:|---:|
| diff | 0.0 | +0.606 | 0.0 | +0.526 |
| r6_diff | 0.0 | +0.594 | 0.0 | +0.514 |
| default_difficulty | −1.0 | +0.469 | 0.5 | +0.322 |
| neg_risk | −1.0 | +0.499 | −1.0 | +0.383 |
| seasonal_empirical | 0.0 | +0.606 | 0.0 | +0.526 |
| switch | −1.0 | +0.581 | −1.0 | +0.490 |
| ridge_covariate | −0.1 | +0.586 | −0.2 | +0.505 |

History all-reconstruct was already positive (+0.469 first, +0.319 second),
so several component predictors selected the grid floor \(\tau = -1\)
(adopt unless the score is extremely negative). Diff/seasonal_empirical
selected \(\tau = 0\) on both panels.

History-only switch (`switch_rule_p0_*.csv`): `default_difficulty` for
7–90 d, `neg_risk` for 180 d, on both panels.

## 4. Reliability near zero and at 180 days

### Near zero (pooled durations)

Diff / seasonal_empirical reliability bins that straddle 0, from
`reliability_p0_*.csv`:

- **p0_first** bin \((-0.785,\ 0.0322]\): n = 2,539, predicted mean −0.260,
  realized mean −0.117, realized positive rate 0.491. Sign is right on
  average but the realized mean is closer to zero than the prediction.
- **p0_second** bin \((-0.105,\ 0.107]\): n = 2,674, predicted mean +0.012,
  realized mean +0.068, realized positive rate 0.629.

Slicing `|diff_prediction| \le 0.10` in `placement_predictions_*.csv`:

- p0_first: n = 1,331, predicted mean +0.010, realized mean +0.125,
  realized positive rate 0.642.
- p0_second: n = 2,388, predicted mean +0.006, realized mean +0.065,
  realized positive rate 0.629.

Near zero on the mixed-duration pool, realized benefit is still slightly
positive. That does not hold at 180 days (below).

Ridge is similar near zero. Default difficulty never approaches zero
(all predicted means \(> 0\)) and is not a sign classifier. Neg-risk is
almost always negative, so a \(\tau = -1\) rule is really “adopt short
gaps where model MAE is small,” not a calibrated benefit threshold.

### 180-day placements

| | p0_first 180 d | p0_second 180 d |
|---|---:|---:|
| n | 3,948 | 3,938 |
| all-reconstruct net | −0.897 | −1.477 |
| harmful if all-reconstruct | 0.722 | 0.832 |
| diff predicted mean | −0.921 | −1.304 |
| diff realized mean | −0.897 | −1.477 |
| diff predicted positive rate | 0.143 | 0.092 |
| diff realized positive rate | 0.278 | 0.168 |
| `|diff| ≤ 0.10` realized mean | −0.121 (n = 204) | −0.672 (n = 140) |
| `|diff| ≤ 0.10` realized positive rate | 0.476 | 0.307 |
| frozen diff rule net (supported, \(\tau=0\)) | **+0.0165** | **−0.0159** |
| adopted / harmful among adopted | 563 / 0.366 | 283 / 0.431 |
| beats all-default at 180 d? | yes (barely) | **no** |

At 180 d the mean prediction is strongly negative and matches the mean
realized loss in sign and rough magnitude. The failure is the **decision
boundary**: cases with predicted benefit near or slightly above zero are
still harmful on average, especially on the second panel. Adopting the
upper tail (\(\hat B > 0\)) therefore does not beat all-default on
second-panel 180 d.

No other frozen predictor beats all-default on second-panel 180 d either
(r6_diff net −0.053, neg_risk/switch −0.018, ridge −0.005, default
difficulty −1.444).

## 5. Step-2 recoverers (not the published recoverer)

`results/wrr_revision/step2_fair_recovery/placement_scores.csv` exists:
1 network, 4 stations, 328 even-placement history rows and 328 odd-placement
evaluation rows per recoverer. This is a tiny even/odd split, not a
held-out confirmation panel. MAE benefit again.

`mean_gt_tau_supported_only` with `diff`, frozen on the even placements:

| recoverer | \(\tau\) | adopt | harmful among adopted | net \(B\) | all-reconstruct | beats all-default? |
|---|---:|---:|---:|---:|---:|---|
| xgb_longblock_boundary | −1.0 | 1.000 | 0.037 | +0.844 | +0.844 | yes (adopts all) |
| xgb_longblock_noboundary | −1.0 | 1.000 | 0.040 | +0.831 | +0.831 | yes (adopts all) |
| xgb_neighbor_noboundary | −1.0 | 1.000 | 0.027 | +0.846 | +0.846 | yes (adopts all) |
| donor_only_ridge | 0.0 | 0.963 | 0.028 | +0.845 | +0.847 | yes |
| xgb_neighbor_boundary | 0.0 | 0.692 | 0.167 | +0.418 | +0.145 | yes |
| ridge_neighbor_boundary | 0.0 | 0.674 | 0.167 | +0.439 | +0.153 | yes |
| linear_interp | 0.0 | 0.570 | 0.299 | +0.267 | −0.310 | yes |
| smooth_climatology | 0.0 | 0.869 | 0.193 | +0.049 | +0.054 | yes |

Long-block and no-boundary models have strongly positive all-reconstruct
MAE benefit on this one network, so history selects \(\tau = -1\) and the
rule is “always reconstruct.” Neighbor-boundary XGB/ridge and linear
interpolation have a real reject region; linear interpolation’s
all-reconstruct MAE is negative and the frozen rule turns it positive.
Default difficulty **fails** the all-default test for linear interpolation
(net −0.143). These rows do not replace the P0 result for the published
recoverer.

## 6. Conclusion

**On the archived published recoverer, a pre-fixed adopt/reject rule does
beat all-default on pooled MAE placements.**

The rule is: fit the seasonal empirical / diff mean on fitting history,
freeze \(\tau = 0\) by historical net \(B\), reconstruct only if
\(\hat B > 0\) and the cell is supported, otherwise keep climatology.
Evaluation net MAE benefit is **+0.487 °C** on the first panel and
**+0.409 °C** on the second, versus 0 for all-default. On the second
panel the same rule also beats all-reconstruct (−0.111). Every other
history-fit predictor in the Step-3 roster also beats all-default on
that pooled MAE test. Diff and seasonal empirical are the same
estimator.

This does **not** mean the WRR decision problem is closed:

1. The quantity here is daily MAE on archived P0 placements, not the
   predeclared primary loss \(B_q\) (hottest-30 on a completed
   station-year).
2. At **180 days on the second panel**, the same frozen diff rule does
   **not** beat all-default (net −0.016, 43% of adopted cases harmful).
   Predictions near zero at that horizon are still negative on average.
3. Adopted-set harmful rates remain 14% (first) and 18% (second) even
   on the pooled MAE win.
4. Step-2 covers one network and cannot confirm a recoverer change.

The pooled MAE adopt/reject test asked in Step 4 is passed for the
current recoverer. The long-gap residual, and the thermal-regime
endpoint, are not.
