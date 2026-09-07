# Step 2 — fair recovery on 42 first-panel networks

Parent audit of `scripts/160_wrr_fair_recovery.py`. 42/42 networks, 219
stations, 303,426 placement-recoverer rows, 0 network failures.

Benefit is MAE climatology minus MAE recoverer on matched archived (and
generated 120/150 d) evaluation placements. Hottest-30 is the gap-centred
365-day thermal diagnostic, not yet the station-year replay.

## Result that kills the threshold law

The published neighbour-boundary trainer (`xgb_neighbor_boundary`) and the
ridge that shares its adjacent-day boundary feature collapse with duration.
Matched long-block training, and any model that never uses the target
boundary, do not.

Mean MAE benefit (°C):

| days | xgb neighbour+boundary | ridge neighbour+boundary | xgb long-block+boundary | xgb no boundary | donor-only ridge | linear interp |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | +1.00 | +1.01 | +0.91 | +0.91 | +0.94 | +0.83 |
| 30 | +0.75 | +0.75 | +0.88 | +0.89 | +0.91 | +0.40 |
| 90 | +0.37 | +0.36 | +0.87 | +0.88 | +0.90 | −0.20 |
| 180 | **−0.72** | **−0.76** | **+0.89** | **+0.91** | **+0.92** | −2.05 |
| 365 | **−2.16** | **−2.31** | **+0.92** | **+0.94** | **+0.95** | −4.55 |

Station-level observed MAE-benefit crossing: 81% for neighbour-boundary XGB,
82% for neighbour-boundary ridge, **4%** for long-block XGB, **2%** for
donor-only ridge. Non-crossers are right-censored at the last evaluated
length, not labelled as 365-day successes unless that length was scored.

Hottest-30 benefit at 180 d: neighbour-boundary XGB **−0.97 °C**; donor-only
**+0.43 °C**. Daily-MAE and thermal-regime signs agree here for the published
trainer; they do not salvage a universal day count.

## What is frozen for confirmation

From these development numbers only:

- Default remains day-of-year climatology.
- Simple alternative: `donor_only_ridge` at every duration.
- Duration switch (development winner): `ridge_neighbor_boundary` at 7 d,
  `donor_only_ridge` thereafter.
- The published `xgb_neighbor_boundary` is withdrawn as a general recoverer.
- Universal threshold law is withdrawn.
- If donors are co-missing or the right boundary is absent, reject to default.

Confirmation must not retune this list.
