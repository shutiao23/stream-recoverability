# Step 4 — information-condition factorial

Development river networks. Donor-only is the negative control for the right
boundary. Unsupported methods map to day-of-year climatology (benefit 0).

## Right-boundary negative control

Donor-only prediction change when only the right flank is hidden:

- 8 ARSO networks, 27 stations: **0.0 °C**
- 17 NASA POWER networks, 95 stations: **0.0 °C**

Linear interpolation is unsupported without the right boundary. Donor-only
remains supported. The freeze rule “missing right boundary → reject every
recoverer” is not an experimental finding.

## Best simple treatment

### ARSO (no air; 8 networks)

| Information | 30 d | 90 d | 180 d |
|---|---|---|---|
| Donors present, with or without right | **donor-only +0.92** | **donor-only +0.90** | **donor-only +0.93** |
| No donors, right present | **linear interp +0.45** | smooth climatology +0.07 | smooth climatology +0.06 |
| No donors, no right | smooth climatology +0.05 | smooth climatology +0.07 | smooth climatology +0.06 |

### NASA POWER (17 first-panel networks, 5,268 placements)

Mean MAE benefit versus day-of-year climatology (°C):

| Recoverer | Donors present | No donors |
|---|---:|---:|
| donor-only | **+0.707** | unsupported → 0 |
| air ridge | +0.275 | **+0.275** |
| air2stream-3 (no discharge) | +0.222 | +0.222 |
| smooth climatology | +0.043 | +0.043 |
| lagged-air ridge | −0.705 | −0.705 |
| linear interp (30 d only, with right) | | **+0.306** at 30 d; harmful at 90/180 |

When donors are missing, air ridge is the best simple method at 90 and 180
days. At 30 days with a right flank, linear interpolation (+0.31) slightly
beats air ridge (+0.29). The 3-parameter air2stream runs without daily
discharge and is beneficial, but weaker than air ridge. Lagged-air ridge is
harmful and is not used.

## Information-conditioned simple policy (development, not yet unseen-confirmed)

1. Synchronous donors observed in the gap → donor-only, even if the right boundary is missing.
2. Else if air temperature is observed → air ridge, except 30-day gaps with both flanks, where linear interpolation is competitive.
3. Else if the gap is ≤30 d and both flanks exist → linear interpolation.
4. Else → smooth climatology.

Artifacts: `cell_scores_arso8.csv`, `cell_scores_power17.csv`,
`cell_scores_combined.csv`, `best_simple_by_cell.csv`,
`best_simple_by_cell_length.csv`.

## Partial donors and correlation quality

40 first-panel river networks, 215 stations, 149,652 gap-level rows
(`quality_cell_scores.csv`). Missing donor columns in the original all-donor
ridge are median-imputed; `donor_subset_ridge` is retrained on the donors
that remain visible. Weak donors have training-period deseasonalized
\(|r|<0.3\).

| Cell | Imputed full model | Retrained subset | Best simple |
|---|---:|---:|---|
| Half of donors hidden | **−1.56** | **+0.74** | subset ridge |
| Strong donors only | +0.86 | **+0.91** | subset ridge |
| Weak donors only | **−2.59** | +0.21 | **air ridge +0.26** |

Applicability: do not keep a full-roster donor model when some donors are
missing or weak. Retrain on the visible strong subset, or switch to air
ridge when only weak donors remain. This is a development information-quality
result, not a new confirmation claim.

