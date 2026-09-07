# Step 8 — confirmation on 36 held-out networks

Design freeze: `results/wrr_revision/DESIGN_FREEZE.json` (written from the
42-network development panel only). Confirmation IDs are first-panel QC
directories that appear in neither `placement_losses.csv` (42 nets) nor
`placement_predictions_second.csv` (57 nets). Year filter: ≥4 train years
and ≥2 eval years. Parent recalculation below uses
`placement_scores.csv` after scoring all 36 eligible IDs (56,232 rows, 70
stations).

Inference is **network-level**: station means inside a network, then an
unweighted mean across networks that have that recoverer.

## Recoverer transfer

On **donor-available** stations, 180-day network-mean MAE / hottest-30
benefit (°C):

| recoverer | n networks | MAE \(B\) | hottest-30 \(B\) |
|---|---:|---:|---:|
| donor_only_ridge | 23 | +0.71 | +0.24 |
| xgb_neighbor_noboundary | 23 | +0.69 | +0.25 |
| xgb_longblock_noboundary | 23 | +0.67 | +0.26 |
| xgb_neighbor_boundary | (same stations) | negative, ~−2 | ~−1.6 |
| linear_interp | | ~−2.6 | ~−1.7 |

Observed crossing fractions over all scored stations: neighbour-boundary XGB
and ridge **0.89**, donor-only **0.03**, neighbour-no-boundary **0.03**.
Non-crossers are right-censored.

Eleven year-eligible networks are single-station (or have no eval-period
donor). Donor-only is undefined there. Under the freeze those cases reject to
climatology except the 7-day neighbour-boundary ridge. Mixing them into
`xgb_longblock_boundary` (which can still use a target boundary without
donors) lowers the all-station 180-day network mean to +0.45 °C; that is not
a same-information comparison with donor-only.

The neighbour versus donor/long-block split **reproduces** on held-out
networks. Confirmation does not retune the freeze.

## Yearly replay

Station-year hottest-30 under the frozen adopt/reject rule is a separate
artifact, `results/wrr_revision/step8_frozen_replay/`. Do not read this
placement table as that end-to-end test.
