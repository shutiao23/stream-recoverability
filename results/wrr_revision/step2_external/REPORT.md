# External-information group (NASA POWER T2M)

Scored only where POWER air temperature exists on first-panel USGS/HUC
networks. Discharge was not present, so `air_flow_ridge` and `air2stream`
were not fit. Same archived placements as Step 2. This group is **not**
mixed into the same-information ranking.

17 networks, 95 stations at 7–90 d; 14 networks at 180 d.

Mean MAE benefit (°C):

| days | air_ridge | donor_only_ridge |
|---:|---:|---:|
| 7 | +0.29 | +0.70 |
| 90 | +0.28 | +0.71 |
| 180 | +0.25 | +0.70 |
| 365 | +0.27 | +0.80 |

Air ridge stays positive and does not collapse with duration. It is weaker
than synchronous donors on the same gaps. Hottest-30 at 180 d: air +0.03 °C,
donor-only +0.16 °C. Adding air is extra information, not a replacement for
the donor-only recoverer when donors exist.
