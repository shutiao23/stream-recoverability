# Step 5 — faults on 42 first-panel networks

Parent audit of `fault_scores.csv`: 42 networks, 52,140 rows.

Archived 30/90/180-day placements keep the Step-2 geometry. Donor-sync hides
every donor on the same window. Missing-right persistence uses only the left
flank. Transplanted rows copy historical missing-block lengths into evaluation
years. Heatwave fraction is the share of gap days above the training 90th
percentile; it is an evaluation mask, not a deployment input.

## Archived, donors present

At 180 d, donor-only ridge MAE benefit is **+0.92 °C** (hottest-30 **+0.43**).
Neighbour-boundary XGB is **−0.73 / −0.99**. Linear interpolation is **−2.05 /
−1.49**. This matches Step 2.

## Donor co-missing

The same 180-day gaps with donors hidden: donor-only **−3.07 °C**, long-block
XGB **−7.35 °C**, neighbour-boundary XGB **−3.52 °C**. Linear interpolation is
unchanged because it never used donors. The frozen rule therefore rejects to
climatology when synchronous donors are missing. That is a decision
contribution, not a ranking contribution.

## Missing right boundary

Left-only persistence versus climatology is **−4.54 °C** at 180 d for every
recoverer. Offline reconstruction that assumes a right flank cannot be
deployed on an open outage. Those cases reject to default.

## Transplanted historical geometry

With donors still observed, donor-only remains positive (mean MAE benefit
**+0.82 °C**). Donor-sync on transplanted geometry is again largely negative.

## Heatwave-overlapping gaps

4,266 rows with heatwave fraction ≥ 0.5: donor-only MAE benefit **+1.39 °C**,
hottest-30 **+0.63 °C**; neighbour-boundary hottest-30 is about 0. The
repaired recoverer does not uniquely fail on warm gaps in this mask.
