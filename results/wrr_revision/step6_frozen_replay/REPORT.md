# Freeze-aligned station-year replay — development panel

Primary endpoint: hottest consecutive 30-day mean benefit on completed
station-years, including unused budget and zero action. Inner-year history
uses the full duration grid. Default is climatology. Sparse-history copies
remain in `step6_frozen_replay_sparse_hist/`.

Parent recalculation of `station_year_replay.csv`: 11,066 cases, 42
networks, 222 stations.

## Case-weighted hottest-30 benefit (°C)

| strategy | hottest-30 | adopt rate |
|---|---:|---:|
| ranked \(\tau=0\) (frozen rule) | **+0.194** | 0.70 |
| always duration-switch, gated | +0.280 | 0.97 |
| always donor-only, gated | +0.278 | 0.97 |
| seasonal ≤30 d | +0.033 | — |
| all-default | 0 | 0 |

Network-unweighted: ranked +0.237, always-switch +0.277, always-donor
+0.275, seasonal +0.042. Ranked minus always-donor is **−0.084 °C**.
90% of networks have ranked hottest-30 > 0; 48% have ranked ≥ always-donor.

**Beats all-default and the ≤30 d seasonal rule. Does not beat gated
always-reconstruct.** The ranker is more conservative (adopt 0.70 vs 0.97)
and discards beneficial long gaps.

## Mixed 30/90/180 patterns (1,659 cases, all 42 networks)

Ranked **+0.272** (adopt 0.65) versus always-donor **+0.431** (adopt 0.97).
Ranking loses on the mixed pattern the review required keeping.

## Duration-stratified (archived evaluation placements)

| length | n cases | ranked | always-donor | seasonal ≤30 | ranked adopt | donor adopt |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | 1639 | +0.037 | +0.035 | +0.047 | 0.78 | 0.98 |
| 14 | 1617 | +0.042 | +0.048 | +0.048 | 0.76 | 0.98 |
| 30 | 1593 | +0.091 | +0.101 | +0.101 | 0.77 | 0.98 |
| 60 | 1537 | +0.275 | +0.314 | 0 | 0.76 | 0.98 |
| 90 | 1425 | +0.272 | +0.354 | 0 | 0.65 | 0.98 |
| 180 | 1003 | +0.339 | +0.596 | 0 | 0.55 | 0.97 |
| 365 | 523 | +0.520 | +0.924 | 0 | 0.54 | 0.94 |

First-panel evaluation gaps come from archived placements
(`ARCHIVED_GAPS`: 7, 14, 30, 60, 90, 180, 365). The 120- and 150-day
strata have only 35 cases (stations without an archive, generated locally)
and all-zero adopt; they are not a ranking result. Confirmation generated
the full grid, including 120/150.

Exceedance-days-20 (sensitivity): ranked +2.69 d, always-donor +3.99 d.

## Interpretation

On the design panel, a \(\tau=0\) benefit ranker is not the source of
thermal-regime gain. Always reconstructing donor-only (or the 7-day
duration switch) when donors and both flanks exist is stronger. The
surviving design pieces are the recoverer and the reject gates, not a
unique sorter. Confirmation (`step8_frozen_replay/`) is the held-out test
of that applicability claim.
