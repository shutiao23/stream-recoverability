# Step 6 — ablations on the same complete-year panel

Same recoverers, information, weights, and 918 eval station-years as Step 5.
All scores are complete-year hottest-30 loss and harm. `diff` and seasonal
empirical mean are not treated as two methods.

| Ablation | Result |
|---|---|
| MAE labels vs thermal labels | MAE year-proxy \(B_q\) +0.329 vs always-simple +0.329 (Δ −0.0003). Thermal \(\tau\) +0.294, harm 0.14 vs 0.22. |
| Duration-season vs information-quality | Length/season ≤30 d JJA: \(B_q\) +0.013, adopt 0.05. Always-simple uses donor/air/flank diagnostics: \(B_q\) +0.329. |
| Predicted mean vs calibrated reject | Thermal \(\tau=0\) reject overlay vs always-simple: Δ −0.035 °C (inside ε = 0.05), harm 0.14 vs 0.22. |
| Same-adoption-rate random reject | Random at ~73% adopt: \(B_q\) +0.231 (fails ε), harm 0.16 vs thermal 0.14. |
| Full default | Always legal; \(B_q\) = 0; abs. error 0.77 °C. |
| Smooth climatology as full-year policy | Harmful (−0.023 °C). |

The calibrated overlay does not beat the simple policy on mean \(B_q\).
Harm reduction versus always-simple is not matched by random at the same
adoption rate; it is also not a length/season rule (that rule fails
non-inferiority). Unseen confirmation is required before any superior
decision-layer claim.
