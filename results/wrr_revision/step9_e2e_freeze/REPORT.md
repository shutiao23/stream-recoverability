# Step 9 — end-to-end freeze (development)

Frozen before unseen confirmation. The development panel was used to choose
tau and the information-conditioned simple recoverer; it cannot confirm a
superior decision layer.

| Item | Frozen value |
|---|---|
| Recoverer | information-conditioned simple: donors → donor-only (right optional); else air ridge if air, except ≤30 d with both flanks → linear interpolation; else smooth climatology |
| Default | day-of-year climatology |
| Diagnostics | donors present, right present, air present, gap length, training donor \|r\| |
| Calibration | year-level thermal \(\tau=0\) overlay (`tau_freeze.json`); hierarchical mean of historical complete-year \(B_q\) |
| Failure | harm = \(B_q<0\) vs climatology; severe underestimate = hottest-30 more than 1.0 °C low |
| Weights | network-equal mean of station-years; one year is one observation |
| Budget | none; full default is legal |

Development eval (918 station-years, 42 networks): always-simple \(B_q\)
+0.329 °C vs thermal overlay +0.294 °C (Δ −0.035, inside ε = 0.05);
harm 0.22 vs 0.14. Mean-benefit superiority fails. Risk-control flags pass
on this panel but are **not** a confirmation claim.

Deploy until unseen is scored: the information-conditioned simple policy,
not the overlay.

**After unseen confirmation** (36 networks, 82 eval station-years): the
overlay Δ versus always-simple is −0.086 °C (outside ε). Paper claim:
training-mismatch diagnosis plus simple-method applicability. No superior
decision layer.

