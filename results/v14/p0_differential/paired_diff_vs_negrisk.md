# Round-2 S2: the differential curve against the sign-flipped legacy predictor (-risk)

network-cluster paired bootstrap on direct placement rows within (panel, duration); each draw resamples networks with replacement from that cell and recomputes placement-level Spearman of each predictor vs realized benefit over the resampled rows; delta = rho(diff) - rho(-risk) = rho(diff) + rho(risk); rho_negrisk = -rho_risk by construction (Spearman is odd under monotone sign change); CI = 2.5/97.5 percentiles of 2000 draws; ties averaged ranks; seed 20260903

rho(-risk) == -rho(risk) exactly, so the paired delta rho(diff) - rho(-risk) = rho(diff) + rho(risk) measures how much of the differential curve's within-duration ranking cannot be obtained by negating the archived model-error predictor.  Reviewer cells (REVIEW_v14_round2.md Major 3) reproduced in the point columns.

| panel | duration | n placements | rho(diff) | rho(risk) | rho(-risk) | rho(r6-diff) | diff - (-risk) | 95% CI | P(>0) |
|---|---|---|---|---|---|---|---|---|---|
| first | 7 | 4380 | 0.265 | 0.134 | -0.134 | 0.232 | +0.395 | [+0.293, +0.500] | 1.00 |
| first | 30 | 4380 | 0.302 | 0.044 | -0.044 | 0.256 | +0.344 | [+0.241, +0.458] | 1.00 |
| first | 90 | 4380 | 0.370 | -0.227 | 0.227 | 0.353 | +0.146 | [+0.064, +0.233] | 1.00 |
| first | 180 | 3948 | 0.308 | -0.373 | 0.373 | 0.252 | -0.058 | [-0.177, +0.020] | 0.10 |
| second | 7 | 4480 | 0.297 | 0.184 | -0.184 | 0.226 | +0.478 | [+0.364, +0.598] | 1.00 |
| second | 30 | 4480 | 0.303 | 0.129 | -0.129 | 0.237 | +0.430 | [+0.326, +0.537] | 1.00 |
| second | 90 | 4400 | 0.371 | -0.192 | 0.192 | 0.331 | +0.179 | [+0.116, +0.247] | 1.00 |
| second | 180 | 3938 | 0.556 | -0.541 | 0.541 | 0.353 | +0.015 | [-0.017, +0.049] | 0.82 |