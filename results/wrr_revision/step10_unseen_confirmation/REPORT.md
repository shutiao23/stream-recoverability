# Step 10 — unseen confirmation

Reserved pool: Step-1 `candidate_unseen` river complete station-years
(37 networks, 293 station-years). Not used for recoverer choice, tau, or
hierarchical means. 36 networks produced 82 eval station-years after the
pre-declared fit/hist/eval split and placement constraints. One network
yielded no scorable year.

Frozen tau and development history were applied without retuning
(`year_thermal_tau_frozen`).

## Network-equal complete-year \(B_q\) (°C)

| Policy | \(B_q\) | 95% CI | vs simple | harm | adopt | abs. default | abs. policy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Oracle | +0.227 | 0.12–0.36 | +0.081 | 0.00 | 0.54 | 0.97 | 0.64 |
| Always donor-only | +0.175 | 0.07–0.31 | +0.029 | 0.11 | 0.59 | 0.97 | 0.69 |
| Always simple | +0.146 | 0.03–0.29 | 0 | 0.38 | 1.00 | 0.97 | 0.72 |
| Frozen thermal overlay | +0.060 | −0.01–0.18 | **−0.086** | 0.06 | 0.16 | 0.97 | 0.87 |
| All default | 0 | — | −0.146 | 0 | 0 | 0.97 | 0.97 |
| Smooth climatology | −0.037 | −0.07–−0.01 | −0.183 | 0.51 | 1.00 | 0.97 | 1.01 |

Over/under for always-simple: 0.40 / 0.52. Severe underestimate: 0.17
(simple), 0.24 (overlay), 0.28 (default).

## Verdict

- Mean-benefit superiority of the overlay: **fails**.
- Risk control: harm falls (0.06 vs 0.38) but mean \(B_q\) is 0.086 °C
  worse than the simple competitor, outside ε = 0.05 °C. **Fails.**
- Paper claim: **training-mismatch diagnosis plus simple-method
  applicability**. Do not claim a superior decision layer.

On this panel gated donor-only (+0.175) is at least as strong as the
broader information-conditioned simple policy (+0.146). The overlay’s harm
drop comes with an adoption rate of 0.16 and is not a successful
non-inferior risk-control rule.
