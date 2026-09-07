# Freeze-aligned station-year replay — confirmation (held-out)

Primary endpoint: hottest consecutive 30-day mean benefit on completed
station-years, including unused budget and zero action. Inner-year history
uses the full duration grid so unsupported rejection is not an artifact of
omitted lengths. Sparse-history copies remain in
`step8_frozen_replay_sparse_hist/`. Development: `step6_frozen_replay/`.

Parent recalculation of `station_year_replay.csv`: 2,512 cases, 36
networks, 70 stations.

## Case-weighted hottest-30 benefit (°C)

| strategy | hottest-30 | adopt rate |
|---|---:|---:|
| ranked \(\tau=0\) (frozen rule) | **+0.131** | 0.59 |
| always duration-switch, gated | +0.135 | 0.71 |
| always donor-only, gated | +0.133 | 0.67 |
| seasonal ≤30 d | +0.020 | — |
| all-default | 0 | 0 |

Network-unweighted: ranked +0.132, always-switch +0.140, always-donor
+0.138, seasonal +0.025. Ranked minus always-donor is **−0.0025 °C**.

**Beats all-default and the ≤30 d seasonal rule. Does not beat the simple
gated always-reconstruct rule.** Two-thirds of networks have ranked
hottest-30 > 0; 56% have ranked ≥ always-donor.

## Mixed 30/90/180 patterns (310 cases, all 36 networks)

Ranked **+0.188**, always-donor **+0.187**. Tied.

## Duration-stratified (generated full grid)

| length | ranked | always-donor | always-switch | seasonal ≤30 | ranked adopt | donor adopt |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | +0.035 | +0.023 | +0.041 | +0.041 | 0.83 | 0.69 |
| 14 | +0.034 | +0.035 | +0.035 | +0.035 | 0.54 | 0.69 |
| 30 | +0.084 | +0.082 | +0.082 | +0.082 | 0.58 | 0.68 |
| 60 | +0.105 | +0.101 | +0.101 | 0 | 0.58 | 0.67 |
| 90 | +0.172 | +0.181 | +0.181 | 0 | 0.62 | 0.68 |
| 120 | +0.155 | +0.165 | +0.165 | 0 | 0.57 | 0.67 |
| 150 | +0.171 | +0.188 | +0.188 | 0 | 0.60 | 0.66 |
| 180 | +0.170 | +0.184 | +0.184 | 0 | 0.48 | 0.63 |
| 365 | +0.366 | +0.369 | +0.369 | 0 | 0.37 | 0.56 |

Every duration has a non-zero ranked adopt rate. Filling history on all
lengths moved the pooled ranked mean from +0.070 (sparse history) to
+0.131, almost matching always-donor.

Exceedance-days-20 (sensitivity): ranked +2.08 d, always-donor +2.20 d.

Always-donor adopt is ~0.67 here versus ~0.97 on development because
single-station and no-donor confirmation networks fail the donor gate and
stay on climatology.

## Interpretation

On networks that did not participate in design choice, a pre-fixed recoverer
plus donor/right-boundary gates already improves hottest-30 relative to
all-default and a short-gap seasonal rule. Adding a \(\tau=0\) benefit
ranker does not improve on always reconstructing when those gates pass.
That is an applicability result, not a unique ranking algorithm.
