# REPORT — agent a (adversarial pair): v3 external-confirmation protocol + power analysis

Namespace: `results/revision_v12/t12_confirmation_protocol/agent_a/`
Branch: main (read-only everywhere except this namespace and the new script).

## Deliverables and paths

| Deliverable | Path |
| --- | --- |
| Protocol v3 (frozen rules, endpoints, margins, external timestamping) | `results/revision_v12/t12_confirmation_protocol/agent_a/protocol_v3.md` |
| Power analysis script | `scripts/rev_v12_t12_protocol_a.py` |
| Power curve figure (4 panels, 0.5x/1x/1.5x × sizes 40–160) | `results/revision_v12/t12_confirmation_protocol/agent_a/power_curve.png` |
| Power table (CSV) | `.../power_table.csv` |
| Bootstrap effect distribution (CSV) | `.../effect_bootstrap_distribution.csv` |
| Recommended sample sizes (JSON) | `.../recommended_sample_size.json` |
| Observed anchors (JSON) | `.../observed_effects.json` |
| Per-network deltas (CSV) | `.../per_network_observed_deltas.csv` |
| Open Research / external preregistration checklist | `.../open_research_checklist.md` |

## Recommended sample size

**120 scored networks** for 80% power at the observed effect, driven by the
binding primary endpoint (a), paired network-level ΔRho on direct-support units
(observed effect +0.038; power 0.72 @ N=80, 0.78 @ N=100, 0.87 @ N=120, 0.93 @
N=160; network-bootstrap t-test, α=0.05). Captured-loss and NDCG@5% endpoints
saturate (power ≥ 0.99 from N=40). Protocol target band: 80–120, where 80 is the
attrition-tolerant floor (0.72 power) and 120 the power-justified target.

## Key findings (adversarial check — these shaped the protocol)

1. **Within-network superiority over the simple baseline is NOT supported by the
   second panel and cannot be powered.** Paired per-network deltas, empirical
   minus simple: ΔRho all-units −0.093, ΔCapturedLoss@20% −0.127,
   ΔNDCG@20% −0.216. Power at any positive margin is 0.000 at every panel size.
   The protocol therefore freezes margins at 0 (direction-replication,
   diagnostics) for these comparisons and does not claim them.
2. **The empirical predictor's replicated advantage is (i) direct-support
   within-network ΔRho (+0.038) and (ii) budget prioritization vs random**
   (ΔCapturedLoss@20% +0.143; power 1.0). NDCG@≥10% vs random is negative
   (−0.67 @20%): top-k *set* beats random, but within-top-k *order* is
   tie-dominated — endpoint (c) is primary at 5% only, diagnostic at ≥10%.
3. **Pooled network-level ΔRho** (the manuscript headline: +0.53 observed) is
   attenuated to +0.33 under the unit block bootstrap; threshold-crossing power
   at margin +0.26 is 0.79 @ N=120 / 0.84 @ N=160 — kept as a secondary
   endpoint, explicitly not powered to reproduce the full +0.53 gap.
4. **Thermal endpoint cannot be powered for superiority** (proxy power max 0.70
   @ N=160); it is frozen as a protection floor (≥ −0.02, 5th percentile of the
   sparsity proxy distribution), scored only where temperature outcomes exist.

## Key protocol changes vs v2

- **External timestamping** (fixes the v2 same-commit flaw): separate public
  pre-outcome commit (protocol + roster + power analysis, no outcomes) → OSF/
  Zenodo registration with DOI → outcome commit referencing the DOI; readiness
  gate requires `external_registration_verified: true`. v2's
  `externally_verifiable_preregistration: false` / `separate_pre_outcome_commit:
  false` become true in the registration record.
- **Endpoints**: margins frozen before outcomes from the power analysis
  (0.5× anchors: (a) +0.019, (b) +0.072 @20%, (c)@5% +0.105, (d) floor −0.02);
  vs-simple within-network comparisons demoted to margin-0 diagnostics with
  documented power ≈ 0; budget levels 5/10/20/30% with per-level margins;
  NDCG tie-break rule frozen (longer gap first).
- **Abstention rules**: support tiers T1/T2/T3 (T3 extrapolation excluded from
  primaries), unit abstention via conformal-width cap (counted as zero captured
  loss), network abstention (< 3 T1 units), budget-level abstention threshold.
- **Panel**: target 80–120 scored networks (power-justified; v1 target 60–80
  with min 40 was underpowered for endpoint (a)), US ≥ 40 and ≤ 65%, ≥ 2 non-US
  domains with ≥ 15 each; QC-only-reuse rule retained with a 5-network cap;
  model roster with per-model self-transfer stress curves.

## Assumptions and caveats

- Power panels resample networks with replacement (infinite-superpopulation
  approximation; anchors from the 57-network second panel).
- Anchor effects are second-panel estimates; margins are guidance-frozen and
  may change only via a new externally registered pre-outcome amendment.
- Endpoint (d) has no thermal outcomes in the anchor table; the sparsity proxy
  (30% of direct-support units) is the documented stand-in.
- Script runtime ~7 min (B=250/cell, distribution bootstrap B=800, seed
  20260828, deterministic).
