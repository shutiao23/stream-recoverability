# Step 8 — hydrological hypotheses on complete-year \(B_q\)

Counterparts to the synthetic mechanism battery (`step7_mechanism/`), scored
on first-panel river complete years. Groups use training-period donor
correlation, GAGES regulation, or historical benefit terciles — not evaluation
thermal labels as deployment inputs.

## Deseasonalized donor synchrony vs long-gap donor-only \(B_q\)

| Synchrony (|r| ≥ 0.5) | Length | n station-years | network-equal \(B_q\) | harm |
|---|---|---:|---:|---:|
| high | long (≥120 d) | 468 | **+0.49** | 0.17 |
| high | short (≤45 d) | 71 | +0.02 | 0.11 |
| low | long | 46 | **−0.08** | 0.39 |
| low | short | 13 | −0.03 | 0.38 |

High training synchrony keeps donor-only useful at long gaps; low synchrony
does not. Short-gap donor-only is near zero in both bins (the thermal peak
often lies outside a short window). This is the hydrologic counterpart of
the synthetic “low memory / strong donor” versus weak-donor systems.

## Regulation

Always-simple eval \(B_q\): regulated +0.11 (14 networks, harm 0.33);
unmatched GAGES +0.46 (27 networks, harm 0.18); unregulated n=5 on one
network (illustrative only). Benefit calibrated on unmatched or mixed
rosters should not be assumed to transfer onto regulated rivers.

## Historical benefit terciles

Stations in the high historical-\(B_q\) tercile remain higher on eval
(+0.53) than the low tercile (+0.15). Rank transfers; 25 of 42 networks
move more than ε = 0.05 °C from hist to eval, so magnitude calibration
is not stable network-by-network.

Synthetic no-information-loss and high-memory scenarios remain in
`results/wrr_revision/step7_mechanism/`. They are not a universal
recoverability threshold.
