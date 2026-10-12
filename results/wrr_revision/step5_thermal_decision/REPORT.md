# Step 5 — complete-year hottest-30 decision labels

Development river complete calendar years only
(`evidence_use=design_development`). Recoverers are fit on early complete
years. Missingness is placed on later complete years. Tau is chosen on
held-out history years. Eval years are the internal test. The 846-case v16
subset and `candidate_unseen` were not used.

## Panel

- 42 first-panel river networks
- 918 eval station-years (network-equal means; reused masks in one year are
  one observation)
- Absolute default hottest-30 error: **0.77 °C**
- Labels: complete-year \(B_q\), not daily MAE

## Eval policies (network-equal \(B_q\), °C)

| Policy | \(B_q\) | 95% CI | vs always-simple | harm | adopt | abs. policy error |
|---|---:|---:|---:|---:|---:|---:|
| Oracle (undeployable) | +0.399 | 0.31–0.49 | +0.070 | 0.00 | 0.58 | 0.31 |
| Always donor-only | +0.330 | 0.23–0.44 | +0.001 | 0.17 | 0.90 | 0.36 |
| Always information-conditioned simple | +0.329 | 0.23–0.44 | 0 | 0.22 | 1.00 | 0.36 |
| MAE-label year proxy | +0.329 | 0.23–0.43 | −0.000 | 0.21 | 0.96 | 0.37 |
| Year thermal \(\tau=0\) | +0.294 | 0.20–0.40 | **−0.035** | **0.14** | 0.75 | 0.40 |
| Same-adoption-rate random | +0.231 | 0.16–0.31 | −0.098 | 0.16 | 0.73 | 0.48 |
| Length/season ≤30 d JJA | +0.013 | −0.01–0.03 | −0.316 | 0.02 | 0.05 | 0.74 |
| All default | 0 | — | −0.329 | 0 | 0 | 0.77 |
| Always smooth climatology | −0.023 | −0.04–−0.01 | −0.352 | 0.46 | 1.00 | 0.79 |

Overestimate / underestimate rates for always-simple: 0.34 / 0.47.
Severe underestimate (>1 °C): 0.07 (simple), 0.09 (thermal \(\tau\)),
0.26 (default).

## Reading (development, not unseen)

- Mean-benefit superiority of the calibrated layer **does not hold**.
- Risk-control package on this panel: thermal \(\tau\) is within 0.05 °C of
  always-simple, reduces harm relative to always-simple (0.14 vs 0.22), and
  is slightly better than same-adoption-rate random (0.14 vs 0.16). The
  length/season rule has lower raw harm because it almost never adopts and
  **fails** non-inferiority by 0.32 °C.
- MAE vs thermal labels: using MAE to pick a year-level \(\tau\) is
  indistinguishable from always-simple. Training the overlay on \(B_q\)
  is more conservative (adopt 0.75) and is the source of the harm drop.
- Remaining oracle headroom is about 0.07 °C from avoiding harmful adopts.
- Strong simple competitor remains the information-conditioned policy,
  which on this panel is essentially gated donor-only.

Tau freeze: `tau_freeze.json` (`tau_thermal=0`, `tau_mae=0`).
