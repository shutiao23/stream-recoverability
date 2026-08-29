# REPORT — agent b (adversarial pair): v3 external-confirmation protocol + power analysis

Namespace: `results/revision_v12/t12_confirmation_protocol/agent_b/`
Script: `scripts/rev_v12_t12_protocol_b.py` (reproduce with
`PYTHONPATH=$PWD/src python3 scripts/rev_v12_t12_protocol_b.py`; ~8 min; no GPU).

## Deliverables

| artifact | path |
| --- | --- |
| Preregistered protocol v3 | `results/revision_v12/t12_confirmation_protocol/agent_b/protocol_v3.md` |
| Power analysis script | `scripts/rev_v12_t12_protocol_b.py` |
| Power table (long form) | `results/revision_v12/t12_confirmation_protocol/agent_b/power_analysis.csv` |
| Panel-effect sampling distribution | `results/revision_v12/t12_confirmation_protocol/agent_b/panel_effect_distribution.csv` |
| Summary JSON (recommended n, margins) | `results/revision_v12/t12_confirmation_protocol/agent_b/power_analysis_summary.json` |
| Power curve figure | `results/revision_v12/t12_confirmation_protocol/agent_b/power_curve.png` |
| Open-research checklist | `results/revision_v12/t12_confirmation_protocol/agent_b/open_research_checklist.md` |

## Recommended sample size for 80% power at the observed effect

**Endpoints (a) network ΔRho and (c) ΔNDCG: n ≈ 40 and n ≈ 51, respectively —
the protocol targets 80–120 scored networks** (2–3× the minimum, absorbing
attrition and giving ≥ 0.92 power even at 0.5x the observed effect). The
power analysis used the second panel's paired predictions (1,446 units; 57
networks; 874 direct-support units at horizons 7/30/90/180 d), resampling
networks with replacement and block-bootstrapping units within networks
(600 replicates per (size, margin); one-sided paired Wilcoxon across
networks, α = 0.05; null calibration 0.037–0.048).

Power at 1x observed effect (n = 40/60/80/100/120/140/160): ΔRho
0.80/0.94/0.98/0.99/1.00/1.00/1.00; ΔNDCG 0.71/0.89/0.92/0.97/0.99/0.99/1.00;
ΔCapturedLoss@5% 0.37/0.50/0.58/0.65/0.73/0.81/0.83; @20%
0.17/0.22/0.27/0.30/0.35/0.37/0.44 (never reaches 80%).

## Key protocol changes vs v2

1. **External timestamping** — the core fix. v2 froze internally in the same
   commit as the outcomes (`package_manifest.json` admits: "same_commit_as_
   outcomes_not_external_preregistration"). v3 requires an OSF/Zenodo
   registration (DOI) or a separate public commit pushed **before** any v3
   outcome is opened; the outcome commit must bind the frozen-commit SHA-256
   (protocol §11).
2. **Endpoints** — v2's mixed set (rank, calibration, intervals, triage,
   placement) becomes frozen paired network-level primaries: (a) ΔRho on
   direct-support units, (b) ΔCapturedLoss ladder @5/10/20/30% (head 20%),
   (c) ΔNDCG, (d) thermal-metric protection (summer max / threshold-
   exceedance days); v2's interval/triage/placement endpoints move to
   secondaries. Success = one-sided paired Wilcoxon p < 0.05 **and**
   panel-median Δ ≥ frozen margin (margins frozen before outcomes with
   power-derived guidance: ΔRho ≥ +0.02, ΔCapturedLoss@20% ≥ +0.02,
   ΔNDCG ≥ +0.005, thermal Δ ≥ +0.05).
3. **Power analysis** — new; v2 had no power basis. Panel 80–120 justified
   from network-bootstrap power curves; guidance margins are the bootstrap
   p25 of the panel median (ΔRho +0.028) and the 80%-detectable effects.
4. **Abstention** — frozen support tiers (direct-support horizons vs
   network-mean fallback, never merged) plus extrapolation abstention,
   symmetric across models.
5. **Model roster** — every rostered model (simple descriptors, empirical-
   transfer, air2stream-8 equivalent, seasonal-boundary ridge, XGBoost,
   donor-BLUP ridge; BiLSTM exploratory) must report its own self-transfer
   stress curve.
6. **Missingness taxonomy** — mechanisms (mechanical/scheduled/sensor_
   failure/aggregation_lag/unspecified) frozen with stratified sensitivity.
7. **QC-only reuse rule** — codified (bounded, disclosed, never described as
   untouched), preserving outcome-disjointness.

## Adversarial finding that must not be smoothed over

ΔCapturedLoss@20% is **null-to-negative** in the second panel (mean −0.012,
median 0.00, only 25% of networks positive). The power analysis shows no
feasible panel size reaches 80% power for it — even a 10× margin multiplier
caps power at ~0.45 because scaling preserves the sign mixture. Protocol v3
keeps 20% as the frozen head budget, powers the panel for (a)/(c), and
pre-registers the +0.02 margin with realized power disclosed, rather than
post-hoc substituting the favorable 5%/10% budgets (which reach 80% only at
n ≈ 140–160). This preserves falsification discipline.

## Validation performed

- Null calibration (margin 0, random sign flips): power 0.037–0.048 ≤ α.
- Direct-support alignment verified: 874 units; observed values identical
  between the two prediction tables; 7/30/90/180-d horizons only.
- Outputs regenerable in ~8 min, deterministic seed 11.
