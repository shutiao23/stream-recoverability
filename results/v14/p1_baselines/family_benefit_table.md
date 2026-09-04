# Round-2 S3: three-family robustness of the duration rule (first panel)

Placement-level realized benefit over the calendar-day climatology default for three structurally different recovery-model families scored on the identical 28,728-placement first-panel geometry (archived roster: `results/development_v11/reviewer_completion/confirmation_model_roster_losses.csv`; climatology errors from `results/development_v11/route_a_confirmation/placement_losses.csv`).

Mean benefit, degC (network-cluster 95% CI, 2,000 draws, seed 20260903); harmful share in parentheses.

| model family | 7 d | 14 d | 30 d | 60 d | 90 d | 180 d | 365 d |
|---|---|---|---|---|---|---|---|
| donor_blup_ridge | +0.954 [+0.84, +1.06] (8.7%) | +0.833 [+0.73, +0.93] (9.0%) | +0.679 [+0.59, +0.77] (11.6%) | +0.494 [+0.40, +0.58] (18.6%) | +0.301 [+0.18, +0.41] (28.6%) | -0.859 [-1.09, -0.66] (70.3%) | -2.527 [-2.92, -2.15] (91.9%) |
| xgboost_b_d | +0.979 [+0.87, +1.09] (8.0%) | +0.848 [+0.76, +0.93] (8.5%) | +0.684 [+0.62, +0.75] (10.8%) | +0.479 [+0.40, +0.55] (19.2%) | +0.260 [+0.16, +0.35] (30.0%) | -0.897 [-1.17, -0.67] (72.2%) | -2.502 [-2.82, -2.11] (93.6%) |
| seasonal_boundary_ridge | +0.814 [+0.70, +0.93] (14.4%) | +0.627 [+0.54, +0.71] (18.5%) | +0.401 [+0.35, +0.46] (25.8%) | +0.129 [+0.08, +0.18] (39.4%) | -0.143 [-0.22, -0.08] (53.1%) | -1.852 [-2.10, -1.62] (91.5%) | -4.307 [-4.66, -3.91] (99.9%) |

All three families reproduce the sign flip (positive benefit at short gaps, negative at 180/365 d).  The two strong families (deployment xgboost_b_d and the neighbor-station ridge donor_blup_ridge) flip between 90 and 180 d; the seasonal-boundary ridge flips between 60 and 90 d.  Where unit sizes are equal (n = 20 placements per unit at 7/14/30/60/90 d), the deployment family's placement-level means coincide with the unit-mean Table 2 first-panel rows; at 180 d unit sizes vary, so the placement-level mean (-0.897) differs from the unit-level mean (-0.885) - the table's aggregation level is named in the definition column.