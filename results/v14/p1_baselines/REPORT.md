# v14 P1: Tier-0 baseline suite - report

All baselines are built strictly on the fitting-period rows
(inner year split) and applied forward to the outer
evaluation placements used by P0.  Benefit = MAE(climatology
default) - MAE(model).  Rho values are Spearman; levels:
placement_pooled (all direct placements of the horizon) and
network (network means over direct units).  Flat predictors
(global constant; duration-only inside a single duration)
have no variance and therefore NaN rho - they enter only via
the budget rows, where ties are broken by a seeded uniform
sample, i.e. the value of ignoring the ranking.

## 1. Second panel (prospective), placement-level rho

placement count per column: 7: n=4480, 14: n=4480, 30: n=4480, 60: n=4480, 90: n=4400, 180: n=3938, direct: n=26258

| predictor | 7 | 14 | 30 | 60 | 90 | 180 | direct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| diff | 0.297 | 0.319 | 0.303 | 0.327 | 0.371 | 0.556 | 0.547 |
| risk | 0.184 | 0.172 | 0.129 | -0.024 | -0.192 | -0.541 | -0.361 |
| duration | n/a | n/a | n/a | n/a | n/a | n/a | 0.516 |
| r6_diff | 0.226 | 0.256 | 0.237 | 0.285 | 0.331 | 0.353 | 0.523 |
| default_difficulty | 0.286 | 0.300 | 0.270 | 0.205 | 0.179 | -0.002 | 0.164 |
| rh_error | 0.005 | 0.001 | 0.004 | 0.028 | -0.079 | -0.524 | -0.489 |
| rh_benefit | 0.016 | 0.040 | 0.064 | 0.017 | 0.114 | 0.526 | 0.513 |
| amplitude | -0.185 | -0.187 | -0.122 | -0.054 | 0.003 | 0.238 | -0.068 |
| sd | 0.203 | 0.201 | 0.162 | 0.112 | 0.100 | -0.099 | 0.115 |
| global | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## 2. Second panel, network-level rho

| predictor | 7 | 14 | 30 | 60 | 90 | 180 | direct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| diff | 0.718 | 0.618 | 0.551 | 0.582 | 0.662 | 0.650 | 0.615 |
| risk | 0.508 | 0.476 | 0.327 | -0.054 | -0.366 | -0.593 | -0.089 |
| duration | n/a | n/a | n/a | n/a | n/a | n/a | 0.400 |
| r6_diff | 0.721 | 0.617 | 0.546 | 0.548 | 0.657 | 0.581 | 0.614 |
| default_difficulty | 0.722 | 0.663 | 0.562 | 0.302 | 0.295 | 0.087 | 0.488 |
| rh_error | 0.066 | -0.007 | 0.238 | -0.034 | -0.104 | -0.025 | -0.273 |
| rh_benefit | -0.165 | 0.029 | 0.000 | 0.224 | 0.155 | 0.001 | 0.328 |
| amplitude | -0.682 | -0.584 | -0.523 | -0.228 | 0.026 | 0.389 | -0.219 |
| sd | 0.726 | 0.608 | 0.542 | 0.247 | 0.114 | -0.254 | 0.314 |
| global | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## 3. Second panel: diff vs Tier-0 baselines, placement level

Where the differential curve beats the baseline (rho):

- horizon 7 (placement_pooled): diff beats risk by +0.113 rho (0.297 vs 0.184)
- horizon 7 (placement_pooled): diff beats r6_diff by +0.071 rho (0.297 vs 0.226)
- horizon 7 (placement_pooled): diff beats default_difficulty by +0.011 rho (0.297 vs 0.286)
- horizon 7 (placement_pooled): diff beats rh_error by +0.292 rho (0.297 vs 0.005)
- horizon 7 (placement_pooled): diff beats rh_benefit by +0.281 rho (0.297 vs 0.016)
- horizon 7 (placement_pooled): diff beats amplitude by +0.482 rho (0.297 vs -0.185)
- horizon 7 (placement_pooled): diff beats sd by +0.094 rho (0.297 vs 0.203)
- horizon 14 (placement_pooled): diff beats risk by +0.146 rho (0.319 vs 0.172)
- horizon 14 (placement_pooled): diff beats r6_diff by +0.062 rho (0.319 vs 0.256)
- horizon 14 (placement_pooled): diff beats default_difficulty by +0.018 rho (0.319 vs 0.300)
- horizon 14 (placement_pooled): diff beats rh_error by +0.318 rho (0.319 vs 0.001)
- horizon 14 (placement_pooled): diff beats rh_benefit by +0.279 rho (0.319 vs 0.040)
- horizon 14 (placement_pooled): diff beats amplitude by +0.506 rho (0.319 vs -0.187)
- horizon 14 (placement_pooled): diff beats sd by +0.118 rho (0.319 vs 0.201)
- horizon 30 (placement_pooled): diff beats risk by +0.175 rho (0.303 vs 0.129)
- horizon 30 (placement_pooled): diff beats r6_diff by +0.066 rho (0.303 vs 0.237)
- horizon 30 (placement_pooled): diff beats default_difficulty by +0.033 rho (0.303 vs 0.270)
- horizon 30 (placement_pooled): diff beats rh_error by +0.300 rho (0.303 vs 0.004)
- horizon 30 (placement_pooled): diff beats rh_benefit by +0.239 rho (0.303 vs 0.064)
- horizon 30 (placement_pooled): diff beats amplitude by +0.426 rho (0.303 vs -0.122)
- horizon 30 (placement_pooled): diff beats sd by +0.141 rho (0.303 vs 0.162)
- horizon 60 (placement_pooled): diff beats risk by +0.351 rho (0.327 vs -0.024)
- horizon 60 (placement_pooled): diff beats r6_diff by +0.043 rho (0.327 vs 0.285)
- horizon 60 (placement_pooled): diff beats default_difficulty by +0.122 rho (0.327 vs 0.205)
- horizon 60 (placement_pooled): diff beats rh_error by +0.300 rho (0.327 vs 0.028)
- horizon 60 (placement_pooled): diff beats rh_benefit by +0.311 rho (0.327 vs 0.017)
- horizon 60 (placement_pooled): diff beats amplitude by +0.382 rho (0.327 vs -0.054)
- horizon 60 (placement_pooled): diff beats sd by +0.215 rho (0.327 vs 0.112)
- horizon 90 (placement_pooled): diff beats risk by +0.563 rho (0.371 vs -0.192)
- horizon 90 (placement_pooled): diff beats r6_diff by +0.040 rho (0.371 vs 0.331)
- horizon 90 (placement_pooled): diff beats default_difficulty by +0.192 rho (0.371 vs 0.179)
- horizon 90 (placement_pooled): diff beats rh_error by +0.450 rho (0.371 vs -0.079)
- horizon 90 (placement_pooled): diff beats rh_benefit by +0.257 rho (0.371 vs 0.114)
- horizon 90 (placement_pooled): diff beats amplitude by +0.368 rho (0.371 vs 0.003)
- horizon 90 (placement_pooled): diff beats sd by +0.271 rho (0.371 vs 0.100)
- horizon 180 (placement_pooled): diff beats risk by +1.096 rho (0.556 vs -0.541)
- horizon 180 (placement_pooled): diff beats r6_diff by +0.203 rho (0.556 vs 0.353)
- horizon 180 (placement_pooled): diff beats default_difficulty by +0.558 rho (0.556 vs -0.002)
- horizon 180 (placement_pooled): diff beats rh_error by +1.080 rho (0.556 vs -0.524)
- horizon 180 (placement_pooled): diff beats rh_benefit by +0.029 rho (0.556 vs 0.526)
- horizon 180 (placement_pooled): diff beats amplitude by +0.318 rho (0.556 vs 0.238)
- horizon 180 (placement_pooled): diff beats sd by +0.654 rho (0.556 vs -0.099)
- horizon direct (placement_pooled): diff beats risk by +0.909 rho (0.547 vs -0.361)
- horizon direct (placement_pooled): diff beats duration by +0.032 rho (0.547 vs 0.516)
- horizon direct (placement_pooled): diff beats r6_diff by +0.025 rho (0.547 vs 0.523)
- horizon direct (placement_pooled): diff beats default_difficulty by +0.383 rho (0.547 vs 0.164)
- horizon direct (placement_pooled): diff beats rh_error by +1.037 rho (0.547 vs -0.489)
- horizon direct (placement_pooled): diff beats rh_benefit by +0.034 rho (0.547 vs 0.513)
- horizon direct (placement_pooled): diff beats amplitude by +0.616 rho (0.547 vs -0.068)
- horizon direct (placement_pooled): diff beats sd by +0.433 rho (0.547 vs 0.115)

Where the differential curve does NOT beat the baseline (rho):

- none at placement level

## 4. Second panel: diff vs Tier-0 baselines, network level

Where diff beats the baseline:

- horizon 7 (network): diff beats risk by +0.210 rho (0.718 vs 0.508)
- horizon 7 (network): diff beats rh_error by +0.652 rho (0.718 vs 0.066)
- horizon 7 (network): diff beats rh_benefit by +0.883 rho (0.718 vs -0.165)
- horizon 7 (network): diff beats amplitude by +1.400 rho (0.718 vs -0.682)
- horizon 14 (network): diff beats risk by +0.141 rho (0.618 vs 0.476)
- horizon 14 (network): diff beats r6_diff by +0.000 rho (0.618 vs 0.617)
- horizon 14 (network): diff beats rh_error by +0.625 rho (0.618 vs -0.007)
- horizon 14 (network): diff beats rh_benefit by +0.589 rho (0.618 vs 0.029)
- horizon 14 (network): diff beats amplitude by +1.202 rho (0.618 vs -0.584)
- horizon 14 (network): diff beats sd by +0.010 rho (0.618 vs 0.608)
- horizon 30 (network): diff beats risk by +0.224 rho (0.551 vs 0.327)
- horizon 30 (network): diff beats r6_diff by +0.004 rho (0.551 vs 0.546)
- horizon 30 (network): diff beats rh_error by +0.312 rho (0.551 vs 0.238)
- horizon 30 (network): diff beats rh_benefit by +0.550 rho (0.551 vs 0.000)
- horizon 30 (network): diff beats amplitude by +1.074 rho (0.551 vs -0.523)
- horizon 30 (network): diff beats sd by +0.009 rho (0.551 vs 0.542)
- horizon 60 (network): diff beats risk by +0.636 rho (0.582 vs -0.054)
- horizon 60 (network): diff beats r6_diff by +0.034 rho (0.582 vs 0.548)
- horizon 60 (network): diff beats default_difficulty by +0.280 rho (0.582 vs 0.302)
- horizon 60 (network): diff beats rh_error by +0.616 rho (0.582 vs -0.034)
- horizon 60 (network): diff beats rh_benefit by +0.359 rho (0.582 vs 0.224)
- horizon 60 (network): diff beats amplitude by +0.810 rho (0.582 vs -0.228)
- horizon 60 (network): diff beats sd by +0.335 rho (0.582 vs 0.247)
- horizon 90 (network): diff beats risk by +1.028 rho (0.662 vs -0.366)
- horizon 90 (network): diff beats r6_diff by +0.004 rho (0.662 vs 0.657)
- horizon 90 (network): diff beats default_difficulty by +0.366 rho (0.662 vs 0.295)
- horizon 90 (network): diff beats rh_error by +0.765 rho (0.662 vs -0.104)
- horizon 90 (network): diff beats rh_benefit by +0.506 rho (0.662 vs 0.155)
- horizon 90 (network): diff beats amplitude by +0.636 rho (0.662 vs 0.026)
- horizon 90 (network): diff beats sd by +0.548 rho (0.662 vs 0.114)
- horizon 180 (network): diff beats risk by +1.243 rho (0.650 vs -0.593)
- horizon 180 (network): diff beats r6_diff by +0.068 rho (0.650 vs 0.581)
- horizon 180 (network): diff beats default_difficulty by +0.563 rho (0.650 vs 0.087)
- horizon 180 (network): diff beats rh_error by +0.675 rho (0.650 vs -0.025)
- horizon 180 (network): diff beats rh_benefit by +0.648 rho (0.650 vs 0.001)
- horizon 180 (network): diff beats amplitude by +0.261 rho (0.650 vs 0.389)
- horizon 180 (network): diff beats sd by +0.904 rho (0.650 vs -0.254)
- horizon direct (network): diff beats risk by +0.704 rho (0.615 vs -0.089)
- horizon direct (network): diff beats duration by +0.215 rho (0.615 vs 0.400)
- horizon direct (network): diff beats r6_diff by +0.001 rho (0.615 vs 0.614)
- horizon direct (network): diff beats default_difficulty by +0.127 rho (0.615 vs 0.488)
- horizon direct (network): diff beats rh_error by +0.887 rho (0.615 vs -0.273)
- horizon direct (network): diff beats rh_benefit by +0.287 rho (0.615 vs 0.328)
- horizon direct (network): diff beats amplitude by +0.834 rho (0.615 vs -0.219)
- horizon direct (network): diff beats sd by +0.300 rho (0.615 vs 0.314)

Where diff does NOT beat the baseline:

- horizon 7 (network): diff does NOT beat r6_diff (delta -0.003, 0.718 vs 0.721)
- horizon 7 (network): diff does NOT beat default_difficulty (delta -0.004, 0.718 vs 0.722)
- horizon 7 (network): diff does NOT beat sd (delta -0.009, 0.718 vs 0.726)
- horizon 14 (network): diff does NOT beat default_difficulty (delta -0.046, 0.618 vs 0.663)
- horizon 30 (network): diff does NOT beat default_difficulty (delta -0.011, 0.551 vs 0.562)

## 5. Top-20% budget (second panel)

### budget 20%, horizon 7

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 896 | 1.219 | 0.094 |
| risk | 896 | 1.026 | 0.136 |
| duration | 896 | 0.875 | 0.113 |
| r6_diff | 896 | 1.150 | 0.089 |
| default_difficulty | 896 | 1.233 | 0.104 |
| rh_error | 896 | 1.000 | 0.112 |
| rh_benefit | 896 | 0.945 | 0.112 |
| amplitude | 896 | 0.656 | 0.109 |
| sd | 896 | 1.047 | 0.119 |
| global | 896 | 0.860 | 0.109 |

### budget 20%, horizon 14

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 896 | 1.086 | 0.084 |
| risk | 896 | 0.875 | 0.157 |
| duration | 896 | 0.763 | 0.118 |
| r6_diff | 896 | 1.023 | 0.068 |
| default_difficulty | 896 | 1.074 | 0.113 |
| rh_error | 896 | 0.856 | 0.136 |
| rh_benefit | 896 | 0.771 | 0.126 |
| amplitude | 896 | 0.564 | 0.127 |
| sd | 896 | 0.871 | 0.142 |
| global | 896 | 0.755 | 0.115 |

### budget 20%, horizon 30

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 896 | 0.840 | 0.109 |
| risk | 896 | 0.614 | 0.184 |
| duration | 896 | 0.551 | 0.162 |
| r6_diff | 896 | 0.774 | 0.119 |
| default_difficulty | 896 | 0.795 | 0.147 |
| rh_error | 896 | 0.600 | 0.176 |
| rh_benefit | 896 | 0.618 | 0.144 |
| amplitude | 896 | 0.467 | 0.163 |
| sd | 896 | 0.646 | 0.166 |
| global | 896 | 0.556 | 0.169 |

### budget 20%, horizon 60

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 896 | 0.630 | 0.147 |
| risk | 896 | 0.234 | 0.327 |
| duration | 896 | 0.325 | 0.254 |
| r6_diff | 896 | 0.602 | 0.152 |
| default_difficulty | 896 | 0.518 | 0.208 |
| rh_error | 896 | 0.343 | 0.227 |
| rh_benefit | 896 | 0.328 | 0.275 |
| amplitude | 896 | 0.312 | 0.256 |
| sd | 896 | 0.374 | 0.286 |
| global | 896 | 0.334 | 0.262 |

### budget 20%, horizon 90

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 880 | 0.380 | 0.251 |
| risk | 880 | -0.253 | 0.547 |
| duration | 880 | 0.033 | 0.401 |
| r6_diff | 880 | 0.367 | 0.255 |
| default_difficulty | 880 | 0.237 | 0.331 |
| rh_error | 880 | -0.143 | 0.516 |
| rh_benefit | 880 | 0.181 | 0.357 |
| amplitude | 880 | 0.087 | 0.412 |
| sd | 880 | 0.076 | 0.409 |
| global | 880 | 0.035 | 0.414 |

### budget 20%, horizon 180

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 788 | -0.637 | 0.628 |
| risk | 788 | -2.878 | 0.982 |
| duration | 788 | -1.330 | 0.819 |
| r6_diff | 788 | -0.862 | 0.714 |
| default_difficulty | 788 | -1.399 | 0.765 |
| rh_error | 788 | -2.503 | 0.952 |
| rh_benefit | 788 | -0.539 | 0.654 |
| amplitude | 788 | -0.994 | 0.821 |
| sd | 788 | -1.717 | 0.874 |
| global | 788 | -1.399 | 0.811 |

### budget 20%, horizon direct

| predictor | n | mean realized benefit | harmful rate |
|---|---|---|---|
| diff | 5252 | 0.922 | 0.129 |
| risk | 5252 | -0.970 | 0.685 |
| duration | 5252 | 0.883 | 0.106 |
| r6_diff | 5252 | 0.902 | 0.131 |
| default_difficulty | 5252 | 0.524 | 0.244 |
| rh_error | 5252 | -1.096 | 0.723 |
| rh_benefit | 5252 | 0.802 | 0.123 |
| amplitude | 5252 | 0.189 | 0.310 |
| sd | 5252 | 0.265 | 0.319 |
| global | 5252 | 0.226 | 0.310 |

### Pooled-direct budget verdicts

diff top-20%: mean realized benefit 0.922, harmful rate 0.129

pooled-direct budget: diff beats duration by +0.039 deg C (0.922 vs 0.883 mean benefit; harmful 0.129 vs 0.106)
pooled-direct budget: diff beats global by +0.696 deg C (0.922 vs 0.226 mean benefit; harmful 0.129 vs 0.310)
pooled-direct budget: diff beats rh_error by +2.019 deg C (0.922 vs -1.096 mean benefit; harmful 0.129 vs 0.723)
pooled-direct budget: diff beats rh_benefit by +0.120 deg C (0.922 vs 0.802 mean benefit; harmful 0.129 vs 0.123)
pooled-direct budget: diff beats amplitude by +0.734 deg C (0.922 vs 0.189 mean benefit; harmful 0.129 vs 0.310)
pooled-direct budget: diff beats sd by +0.658 deg C (0.922 vs 0.265 mean benefit; harmful 0.129 vs 0.319)
pooled-direct budget: diff beats default_difficulty by +0.399 deg C (0.922 vs 0.524 mean benefit; harmful 0.129 vs 0.244)
pooled-direct budget: diff beats r6_diff by +0.020 deg C (0.922 vs 0.902 mean benefit; harmful 0.129 vs 0.131)
pooled-direct budget: diff beats risk by +1.892 deg C (0.922 vs -0.970 mean benefit; harmful 0.129 vs 0.685)

## 5b. Interpretation notes (factual)

- Within any single duration the duration-only and global
  predictors are constant by construction, so the only
  honest per-duration comparisons are against the rankable
  baselines (rh_error, rh_benefit, amplitude, sd, r6_diff,
  default_difficulty); flat baselines enter via the budget
  rows where their ties are broken uniformly at random.
- Pooled across durations, diff and the duration-only /
  rh_benefit predictors rank almost identically at the
  placement level and by top-20% budget.
  * pooled placement rho: diff vs duration = +0.032 (0.547 vs 0.516); top-20% budget margin +0.039 deg C, harmful rate 0.129 vs 0.106
  * pooled placement rho: diff vs rh_benefit = +0.034 (0.547 vs 0.513); top-20% budget margin +0.120 deg C, harmful rate 0.129 vs 0.123
  * pooled placement rho: diff vs r6_diff = +0.025 (0.547 vs 0.523); top-20% budget margin +0.020 deg C, harmful rate 0.129 vs 0.131
  At the pooled level the differential curve therefore does
  not clearly outperform the duration-only and rh_benefit
  priors: its advantage is a small mean-benefit margin
  (0.899 vs 0.896 deg C) with a higher harmful rate
  (0.145 vs 0.104).  Its decisive advantage is per-duration
  ranking (see section 1) and the network level (section 2).

## 6. First panel (development), placement-level rho

placement count per column: 7: n=4380, 14: n=4380, 30: n=4380, 60: n=4380, 90: n=4380, 180: n=3948, direct: n=25848

| predictor | 7 | 14 | 30 | 60 | 90 | 180 | direct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| diff | 0.265 | 0.255 | 0.302 | 0.311 | 0.370 | 0.308 | 0.440 |
| risk | 0.134 | 0.105 | 0.044 | -0.051 | -0.227 | -0.373 | -0.290 |
| duration | n/a | n/a | n/a | n/a | n/a | n/a | 0.448 |
| r6_diff | 0.232 | 0.217 | 0.256 | 0.283 | 0.353 | 0.252 | 0.433 |
| default_difficulty | 0.257 | 0.246 | 0.252 | 0.231 | 0.170 | -0.112 | 0.158 |
| rh_error | 0.100 | 0.080 | 0.132 | 0.057 | 0.029 | -0.441 | -0.403 |
| rh_benefit | 0.013 | 0.002 | 0.112 | 0.029 | 0.025 | 0.445 | 0.443 |
| amplitude | 0.169 | 0.148 | 0.094 | 0.036 | -0.055 | -0.284 | 0.048 |
| sd | 0.243 | 0.220 | 0.147 | 0.112 | 0.055 | -0.186 | 0.104 |
| global | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

First panel: where diff does NOT beat a Tier-0 baseline (rho):

- horizon 180 (placement_pooled): diff does NOT beat rh_benefit (delta -0.138, 0.308 vs 0.445)
- horizon direct (placement_pooled): diff does NOT beat duration (delta -0.008, 0.440 vs 0.448)
- horizon direct (placement_pooled): diff does NOT beat rh_benefit (delta -0.003, 0.440 vs 0.443)

## 7. R&H gamma_m behaviour

### first panel

| variant | month | slope | intercept | n_gaps | n_placements |
|---|---|---|---|---|---|
| rh_error | 1 | 0.0026 | 0.3368 | 4 | 4710 |
| rh_error | 10 | 0.0068 | 0.2300 | 4 | 4284 |
| rh_error | 11 | 0.0063 | 0.2604 | 4 | 4153 |
| rh_error | 12 | 0.0042 | 0.3500 | 4 | 4019 |
| rh_error | 2 | 0.0027 | 0.3202 | 4 | 4216 |
| rh_error | 3 | 0.0054 | 0.2581 | 4 | 4538 |
| rh_error | 4 | 0.0069 | 0.2894 | 4 | 4433 |
| rh_error | 5 | 0.0077 | 0.2838 | 4 | 4629 |
| rh_error | 6 | 0.0061 | 0.3865 | 4 | 4885 |
| rh_error | 7 | 0.0023 | 0.4780 | 4 | 3827 |
| rh_error | 8 | 0.0022 | 0.4303 | 4 | 4414 |
| rh_error | 9 | 0.0049 | 0.2911 | 4 | 4881 |
| rh_error | global | 0.0048 | 0.3262 | 48 | 52989 |
| rh_benefit | 1 | -0.0033 | 0.6587 | 6 | 7106 |
| rh_benefit | 10 | -0.0126 | 1.0424 | 6 | 6768 |
| rh_benefit | 11 | -0.0100 | 0.8959 | 6 | 6275 |
| rh_benefit | 12 | -0.0082 | 0.9333 | 6 | 6227 |
| rh_benefit | 2 | -0.0029 | 0.7281 | 6 | 6501 |
| rh_benefit | 3 | -0.0079 | 1.0286 | 6 | 6897 |
| rh_benefit | 4 | -0.0137 | 1.2915 | 6 | 6720 |
| rh_benefit | 5 | -0.0174 | 1.4582 | 6 | 7343 |
| rh_benefit | 6 | -0.0145 | 1.2957 | 6 | 7405 |
| rh_benefit | 7 | -0.0068 | 0.9020 | 6 | 5803 |
| rh_benefit | 8 | -0.0072 | 0.9257 | 6 | 7130 |
| rh_benefit | 9 | -0.0109 | 1.0220 | 6 | 7613 |
| rh_benefit | global | -0.0096 | 1.0152 | 72 | 81788 |

rh_error monthly slopes: min 0.0022, max 0.0077, mean 0.0048 (12 months fitted monthly of 12)
rh_benefit monthly slopes: min -0.0174, max -0.0029, mean -0.0096 (12 months fitted monthly of 12)

### second panel

| variant | month | slope | intercept | n_gaps | n_placements |
|---|---|---|---|---|---|
| rh_error | 1 | 0.0024 | 0.4956 | 4 | 5966 |
| rh_error | 10 | 0.0075 | 0.3000 | 4 | 4988 |
| rh_error | 11 | 0.0063 | 0.3627 | 4 | 5351 |
| rh_error | 12 | 0.0047 | 0.4476 | 4 | 4913 |
| rh_error | 2 | 0.0017 | 0.5553 | 4 | 5225 |
| rh_error | 3 | 0.0052 | 0.3712 | 4 | 5581 |
| rh_error | 4 | 0.0071 | 0.2890 | 4 | 4900 |
| rh_error | 5 | 0.0072 | 0.3385 | 4 | 5420 |
| rh_error | 6 | 0.0056 | 0.4049 | 4 | 6179 |
| rh_error | 7 | 0.0019 | 0.4471 | 4 | 4560 |
| rh_error | 8 | 0.0033 | 0.3514 | 4 | 5124 |
| rh_error | 9 | 0.0057 | 0.2776 | 4 | 5656 |
| rh_error | global | 0.0049 | 0.3867 | 48 | 63863 |
| rh_benefit | 1 | -0.0058 | 0.6836 | 6 | 9222 |
| rh_benefit | 10 | -0.0175 | 1.2563 | 6 | 7993 |
| rh_benefit | 11 | -0.0141 | 0.9879 | 6 | 8164 |
| rh_benefit | 12 | -0.0107 | 0.8413 | 6 | 7458 |
| rh_benefit | 2 | -0.0054 | 0.8089 | 6 | 8087 |
| rh_benefit | 3 | -0.0119 | 1.0509 | 6 | 8595 |
| rh_benefit | 4 | -0.0183 | 1.3398 | 6 | 7474 |
| rh_benefit | 5 | -0.0203 | 1.4357 | 6 | 8383 |
| rh_benefit | 6 | -0.0144 | 1.1095 | 6 | 9268 |
| rh_benefit | 7 | -0.0071 | 0.7618 | 6 | 7186 |
| rh_benefit | 8 | -0.0082 | 0.8489 | 6 | 8027 |
| rh_benefit | 9 | -0.0132 | 1.0436 | 6 | 8585 |
| rh_benefit | global | -0.0122 | 1.0140 | 72 | 98442 |

rh_error monthly slopes: min 0.0017, max 0.0075, mean 0.0049 (12 months fitted monthly of 12)
rh_benefit monthly slopes: min -0.0203, max -0.0054, mean -0.0122 (12 months fitted monthly of 12)

### overlap checks, first panel (direct placements)

- rho(rh_benefit_prediction, duration_only_prediction) = 0.918 (Pearson 0.896): rh_benefit is the monthly-intercepted analogue of the plain duration-only curve; a high value confirms the R&H structure mostly reproduces the duration signal with a monthly offset.
- rho(rh_error_prediction, duration_only_prediction) = -0.914
- global constant (pooled fitting benefit mean) = 0.4685 deg C

### overlap checks, second panel (direct placements)

- rho(rh_benefit_prediction, duration_only_prediction) = 0.932 (Pearson 0.903): rh_benefit is the monthly-intercepted analogue of the plain duration-only curve; a high value confirms the R&H structure mostly reproduces the duration signal with a monthly offset.
- rho(rh_error_prediction, duration_only_prediction) = -0.910
- global constant (pooled fitting benefit mean) = 0.3193 deg C

## 8. Files

- rh_gamma_curve.csv, proxy_values.csv, placement_predictions_{first,second}.csv, unit_predictions_{first,second}.csv, metrics_table.csv, budget_within_duration.csv, sanity_checks.txt
