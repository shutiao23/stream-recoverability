# Protocol v3 — externally registered third-panel confirmation of stream-recovery predictors

- protocol_id: `route_a_third_confirmation_v3`
- status: **frozen draft, pending external registration (not yet outcome-opened)**
- parent: `configs/route_a_second_confirmation_protocol.yaml` (v1) + `configs/route_a_second_confirmation_amendment_v2.yaml` (v2)
- evidence_status_parent: `results/development_v11/second_confirmation/scoring/summary.json` (57 scored networks, 1,446 units)
- target_journal: Water Resources Research
- power_analysis: `results/revision_v12/t12_confirmation_protocol/agent_a/power_table.csv`, `power_curve.png`, `observed_effects.json`, `effect_bootstrap_distribution.csv`, `recommended_sample_size.json`
- analysis_script: `scripts/rev_v12_t12_protocol_a.py`
- independent_unit: river network (as in v1)

---

## 0. Purpose and the v2 flaw this protocol fixes

The v2 confirmation was internally hash-bound and frozen before recovery scoring, but the amendment and the outcomes entered version control **in the same commit**, so its timing is an internal provenance claim, not an externally verifiable preregistration (see `results/development_v11/second_confirmation/amendment_registration_record.json` and SI Text S17).

Protocol v3 fixes this by requiring, **before any third-panel recovery outcome is opened**:

1. a **separate public commit** containing this protocol, the exact roster, all endpoint definitions, and the power analysis (no outcome files, no outcome-derived artifacts);
2. an **external registration** (OSF preregistration or Zenodo deposit) of that commit's content with a minted DOI/handle, recorded in this repository by a registration record file;
3. an **outcome-scoring commit** that references the registration DOI and is created only after the DOI exists.

No v3 analysis step may read, merge, or reference any outcome file before step 2 is verified by the readiness gate (`readiness.json` with `external_registration_verified: true`).

---

## 1. Evidence separation and independence rules

- `independent_unit`: river network.
- **Outcome-disjoint panel**: every network in the third-panel roster must be disjoint from
  - all development outcome networks (`results/development_v11/station_gap_outcomes.csv`),
  - all 42 first-panel scored networks (`results/development_v11/route_a_confirmation/predictions.csv`),
  - all 57 second-panel scored networks (`results/development_v11/second_confirmation/frozen_scoring_roster_v2.csv` + `scoring/` outcomes).
- **QC-only-reuse rule (inherited from v2, tightened)**: a network that passed source/QC in an earlier panel but produced **no recovery outcome there** may be reused. It must (i) be disclosed in the flow table as `qc_only_reuse=true`, (ii) never be described as an untouched metadata/QC candidate, (iii) **not** count toward domain quota floors, and (iv) be capped at 5 networks per panel. The v2 precedents are `huc8_17090012`, `usgs_red_river_of_the_north_huc4_0902`, `usgs_snake_river_huc4_1705`.
- **Temperature values may not select networks** (v1/v2 invariant). Thermal covariates may be used only inside the thermal-metric endpoint (d) after roster freeze.
- No outcome, interval, or placement value from any earlier panel may be used to select, augment, or re-order the third-panel roster.
- Any amendment to this protocol (roster change, margin change, endpoint change) requires a new amendment record **and** a new external registration before scoring; there is no post-outcome amendment path.

---

## 2. Panel design and sample-size justification

| Quantity | Value | Source |
| --- | --- | --- |
| Candidate floor | 150 networks | v1 invariant (unchanged) |
| Expected retention | 0.50 (candidate → scored) | v1 invariant (unchanged) |
| **Target scored networks** | **80–120** | power analysis (below) |
| Attrition-tolerant minimum for primary analysis | 80 scored networks | power analysis (below) |
| Hard power floor | 120 scored networks | 80% power at observed effect for primary (a) |

**Justification from the power analysis** (network bootstrap over the 57-network second panel; one-sided network-level t-test, α=0.05; `power_curve.png`, `power_table.csv`):

- The binding endpoint is primary (a), paired network-level ΔRho on direct-support units, whose observed effect is +0.038. Power at that effect is 0.72 (N=80), 0.78 (N=100), **0.87 (N=120)**, 0.93 (N=160). Recommended N = **120** for 80% power at the observed effect.
- Endpoints (b) (captured-loss vs random at 20%) and (c) at 5% budget saturate power ≥ 0.99 already at N=40, so they do not constrain N.
- The 80 lower bound is the attrition-tolerant floor: a panel of 80 scored networks still has 72% power at the observed primary effect; if the achieved panel is between 80 and 120, power is reported from the curve for the achieved size and the claim is downgraded accordingly (no post-hoc margin loosening).
- 120 is also the practical cap for feasibility/domain quotas; larger panels add little primary power (0.87 → 0.93).

**Domain quotas** (exact counts frozen at roster registration, consistent with target 80–120):

- `united_states`: ≥ 40 networks and ≤ 65% of the panel.
- At least **2 non-US domains**; each non-US domain ≥ 15 networks; non-US total ≥ 30.
- Eligible non-US domains are the validation-grade providers already assessed in SI Text S17 (e.g., Czechia CHMI, Norway NVE, and any additional provider that passes the frozen strict daily-QC rule). No Canada substitution is made unless a validated multi-station Canadian daily source passes the frozen daily-QC rule; an unvalidated source is ineligible by the v2 precedent.

**Attrition-tolerant primary analysis**: primary endpoints are evaluated on the actual scored-arrival roster whenever ≥ 80 networks score; every attrition row is reported in the flow table (Section 6).

---

## 3. Candidate, eligibility, and attrition rules

1. **Source eligibility**: providers accessed through official public download surfaces only (USGS, NASA POWER, CHMI, NVE, ARSO, GKD, LUBW, RWS, FOEN, ECCC, eHYD, SYKE, etc. as audited in SI Text S17). A source that states its observations are not validated or checked is ineligible (v2 precedent).
2. **Strict daily QC** (unchanged from v2): daily concurrency checked before outcome scoring; ≥ 3 stations per network; ≥ 8 common years; positive and complete same-site approved daily discharge where used; finite daily air temperature at station coordinates.
3. **Scoreable-gap eligibility**: a network must have at least one scoreable evaluation gap (defined as in v2 readiness; a network with no scoreable B+D evaluation gap is a scoring attrition).
4. **Roster freeze**: the complete strict-QC arrival roster with exact per-domain counts is frozen in a hash-bound CSV (`frozen_scoring_roster_v3.csv`) inside the **separate pre-outcome commit**; counts are the frozen roster, not post-hoc increases of the 80 minimum.
5. **Attrition classes** (each reported as a count in the flow table):
   - `source_qc_attrition` (provider coverage/QC; treated as MNAR at source level),
   - `scoreable_gap_attrition` (no B+D evaluation gap),
   - `thermal_outcome_attrition` (temperature outcomes unavailable for endpoint (d)),
   - `abstention_attrition` (unit/budget abstentions under Section 7).
6. **No evaluate-once self-destruct relaxation**: endpoints are scored exactly once; a failed endpoint cannot be re-scored under a redefined margin.

---

## 4. Endpoints

### 4.1 Primary endpoints (each with a frozen margin; margins were derived from the power analysis and are fixed before outcomes)

Common definitions:
- Units are station-gap rows with observed recovery loss (same definition as second-panel scoring).
- **Support tiers** per unit: T1 direct-support (gap horizon in {7,30,90,180} with a same-horizon fitting-period curve), T2 network-mean fallback, T3 extrapolation beyond fitted-horizon range. See Section 7.
- **Tie-break rule (frozen)**: within equal predicted values, units sort by descending gap length, then by station id, then by original row order (`tie_break_jitter` in the power script implements this deterministically).
- Baseline ("strongest tested baseline"): the simple-descriptor model (`predicted_loss`, as scored in the second panel).
- All paired deltas are per-network differences; inference is a one-sided network-level t-test (α=0.05) on the panel mean, plus a network bootstrap CI.

| # | Endpoint | Definition | Frozen margin | Guidance source |
| --- | --- | --- | --- | --- |
| (a) | **ΔRho direct-support** | mean over networks of [Spearman(empirical, observed) − Spearman(simple, observed)] on **T1 direct-support units** only | **+0.019** (0.5× observed anchor 0.038) | power: 80% at N=100 for 0.5×; 80% at N=120 for 1×; anchor distribution CI [0.006, 0.084] |
| (b) | **ΔCapturedLoss@b** | per network, captured fraction of realized loss in the top ceil(b·n) units ranked by the empirical predictor, **minus the random-prioritization baseline (k/n)**; budgets **b ∈ {5%, 10%, 20%, 30%}**; primary registration at 20% | b=5%: +0.039; b=10%: +0.054; b=20%: **+0.072**; b=30%: +0.120 (each 0.5× its anchor) | anchors +0.078/+0.108/+0.143/+0.240; power ≥0.99 at N=40 for every budget |
| (c) | **ΔNDCG@b** | per network, NDCG@b of the empirical ranking minus E[NDCG@b of a random ranking] (= mean gain·D_k/IDCG), budgets 5/10/20/30% | b=5%: **+0.105** (0.5× anchor +0.209); b=10/20/30%: **0** (direction-replication; see note) | second-panel anchors are **negative** at b≥10% (−0.06, −0.67, −1.31); power for any positive margin is ≈0 at all feasible N, so those budget levels are diagnostic only |
| (d) | **Thermal-metric protection** | ΔRho (same paired definition as (a)) restricted to **thermal-stress units** (units whose evaluation window overlaps June–August or contains ≥ 5 days above the network 95th-percentile daily maximum temperature, scored only where temperature outcomes exist) | **≥ −0.02** (protection floor, no-sign-reversal) | sparsity proxy (30% of T1 units) anchor distribution: mean +0.063, sd 0.051, 5th pct −0.020; superiority power never reaches 0.8 at any feasible N (max 0.70 at N=160), so the endpoint is a protection floor, not a superiority margin |

Note on (c) at b≥10%: the second-panel anchor is negative because the empirical predictor's within-budget ordering is dominated by tied predictions (network-mean fallback and saturated curve values); its top-k **set** beats random (endpoint (b)) while its within-top-k **order** does not. The frozen margin is 0, and the analysis reports the signed bootstrap distribution. This negative anchor is a finding, not a bug; it is pre-registered so that a positive third-panel result at any budget is confirmatory, and a negative one is a documented replication of the second-panel diagnostic.

### 4.2 Secondary endpoints

1. Pooled network-level ΔRho headline (network-mean predictions vs network-mean outcomes, T1 units): success margin **+0.26** (0.5× the observed pooled delta +0.53, and 0.8× the bootstrap-attenuated mean +0.33); threshold-crossing power 0.79 (N=120) and 0.84 (N=160) — reported, but the margin of +0.53 (full observed gap) is explicitly not powered (probability ≈ 0.03).
2. Calibration slope and intercept on T1 units (equal-network weighting; band [0.90, 1.10] reported, not gated).
3. Interval efficiency (nominal 90% coverage, network-simultaneous band [0.85, 0.95], median width ≤ 2× median loss) — reported; v2 failed this.
4. Triage endpoint: exact 5% false-release rule; success = nonempty certified set — reported; v2 released nothing.
5. Placement replay (networks with ≥ 5 target stations): simple-risk minimax mean regret vs random at 20% budget, margin 0 (direction-replication; v2 was 6.0% directional without a margin).
6. Domain adaptation: slope by domain and the ΔRho anchor by domain (descriptive, effect-modification only).
7. Model-roster stress: for each recovery model in Section 5, the fitting-period empirical curve evaluated against that model's own third-panel recovery losses (self-transfer stress curve); Spearman reported per model with its own baseline comparison.

---

## 5. Model roster (each model with its own self-transfer stress curve)

All models are evaluated on identical outer gaps and identical third-panel outcomes; no model's outcomes may be used to select networks or set margins.

| Model | Role | Self-transfer stress curve |
| --- | --- | --- |
| Simple descriptors | strongest tested baseline | fitting-period descriptor losses vs own third-panel losses (descriptors have no curve; comparison is the v1/v2 simple `predicted_loss`) |
| Empirical transfer (fitting-period curve) | primary predictor | fitting-period empirical curve vs third-panel recovery losses of the same recovery model |
| XGBoost recovery model | roster member | fitting-period empirical curve vs own XGBoost third-panel losses |
| BiLSTM (bounded, non-SOTA disclaimer as in v11) | roster member | fitting-period empirical curve vs own BiLSTM third-panel losses; epoch-cap and non-convergence rates reported |
| air2stream-equivalent (published 8-parameter equation, harmonized daily boundaries) | roster member | fitting-period empirical curve vs own air2stream-equivalent third-panel losses |

Each self-transfer curve must be computed inside the fitting record with the model's own training split; stress = loss of rank/calibration when the curve is applied to its own model's held-out outcomes. `B+O` (bounded + optimist) and full-roster caveats from the manuscript apply.

---

## 6. Missingness mechanisms and attrition flow table

| Attrition class | Assumed mechanism | Recorded per class |
| --- | --- | --- |
| source_qc_attrition | MNAR at provider/source level (coverage, QC flags) | networks by provider and domain |
| scoreable_gap_attrition | MAR given network record length | networks, and unit counts |
| thermal_outcome_attrition | MNAR/MAR (seasonal coverage, provider temperature availability) | networks; endpoint (d) is scored only when ≥ 20 networks retain thermal outcomes, else reported `not_achieved` with the reason |
| abstention_attrition (Section 7) | decision-rule-induced | units by tier and budget level |

The flow table (`attrition_flow_v3.csv`) reports: candidates → QC-arrivals → frozen roster → scored → excluded-by-class, with counts by domain. Missingness is audited for association with predictors (e.g., network mean loss) in a pre-frozen audit, and any correlation is reported in the manuscript.

---

## 7. Abstention rules (support tiers + extrapolation)

- **T1 direct-support**: gap horizon has a same-horizon fitting-period curve (7/30/90/180). Primary endpoints (a), (b), (c), (d) are computed on T1 units only for (a)/(d); (b)/(c) use the full unit set (prioritization operates on the full panel).
- **T2 network-mean fallback**: units scored with the fitting-period network mean; included in (b)/(c) with the tie-break rule; excluded from (a)/(d).
- **T3 extrapolation**: any prediction outside the fitted horizon range or donor-mean extrapolation. **T3 units are excluded from all primary endpoints** and their counts are reported.
- **Unit abstention**: a predictor may abstain on a unit whose conformal interval width exceeds 2× the median interval width of its own fitting-period distribution (frozen cap). Abstained selections count as zero captured loss in (b) and zero gain in (c) — abstention never inflates a budget endpoint.
- **Network abstention**: networks with < 3 T1 units abstain from (a)/(d) and are counted in the flow table; they remain in the scored roster for (b)/(c).
- **Budget-level abstention**: at any budget level b, if ≥ 30% of networks abstain (as above), the level is reported `not_scored` rather than pooled with partial abstention; the 20% level is the primary registration.

---

## 8. Analysis pipeline and external timestamping

Pipeline (each stage gated):

1. **Readiness**: candidate arrival, strict QC, domain quotas verified; `readiness.json` with `external_registration_verified: false`.
2. **Freeze** (separate public commit #1, before any outcome scoring): this protocol, `frozen_scoring_roster_v3.csv`, endpoint definitions, margins table (Section 4), power analysis artifacts (this namespace), and `data_rights`/provider treatment notes. Commit message records the protocol id and UTC time. **No outcome file may be present in this commit.**
3. **External registration**: deposit commit #1 content (or the OSF preregistration form built from it) at OSF or Zenodo; obtain handle/DOI. Record it in `registration_record_v3.json` (fields: registry, DOI, registration URL, registration UTC, commit hash of the registered tree, sha256 of the registered files).
4. **Authorization**: `readiness.json` flips to `external_registration_verified: true` only when the registration record exists and its file hashes match commit #1.
5. **Outcome scoring** (separate public commit #2): scoring runs, summaries, flow table, and this protocol's outcome section, referencing the registration DOI.
6. **Primary analysis**: per-endpoint one-sided network-level t-tests plus network-bootstrap 95% CIs against the frozen margins; sensitivity: T1-only vs full panel, per-domain, per-model; attrition flow table; no margin or endpoint changes.
7. **Reporting**: success/failure per endpoint, power table for the achieved N, downgrade statements where applicable.

**External timestamping requirements (fixes the v2 same-commit flaw):**

- Commit #1 must be pushed to the public remote and its hash recorded in the registration before any third-panel outcome is scored; the outcome commit (#2) must reference the DOI.
- The registration record must state `separate_pre_outcome_commit: true` and `externally_verifiable_preregistration: true` — the explicit opposite of the v2 record fields.
- If the roster must change between commits #1 and #2, a new amendment + new registration is required (no partial registration).
- The manuscript must describe the third panel as externally registered with a DOI, replacing the current SI Text S17 sentence that the v2 "amendment and results share one commit."

---

## 9. Frozen success margins (summary table, fixed before outcomes)

| Endpoint | Frozen margin | Achieved-power note |
| --- | --- | --- |
| (a) ΔRho T1 | ≥ +0.019, one-sided p < 0.05 | 0.87 at N=120 (1× anchor); 0.80 at N=100 (0.5×) |
| (b) ΔCapturedLoss@5/10/20/30% vs random | ≥ +0.039 / +0.054 / +0.072 / +0.120 | ≥ 0.99 at N=40 |
| (c) ΔNDCG@5% vs random | ≥ +0.105 | ≥ 0.99 at N=40 |
| (c) ΔNDCG@10/20/30% vs random | ≥ 0 (replication) | power ≈ 0 (negative anchors) |
| (d) ΔRho thermal protection | ≥ −0.02 | ≈ 0.95 at N≥80 (floor, not superiority) |
| Secondary: pooled network-level ΔRho T1 | ≥ +0.26 | 0.79 at N=120; 0.84 at N=160 |
| Diagnostic (not gated): (a-all), (b vs simple), (c vs simple) | margin 0, power ≈ 0 documented | negative anchors |

Margins are derived from the network-bootstrap power analysis of the second panel (`observed_effects.json`, `power_table.csv`, `power_curve.png`); they are guidance-frozen numbers and may be changed only by a new externally registered amendment **before** outcomes.

---

## 10. Power analysis provenance

- Input: `results/development_v11/second_confirmation/scoring/empirical_predictions.csv` (1,446 units, 57 networks) merged with `simple_predictions.csv` (baseline), 1,446 rows matched.
- Method: network bootstrap (networks resampled with replacement; unit rows block-bootstrapped within networks), panels of 40–160 networks, effect scales 0.5×/1×/1.5× of the signed observed anchor, one-sided network-level t-test α=0.05 (B=250 per cell; distribution bootstrap B=800), seed 20260828.
- Outputs: `power_curve.png`, `power_table.csv`, `effect_bootstrap_distribution.csv`, `recommended_sample_size.json`, `observed_effects.json`, `per_network_observed_deltas.csv`.
- Key anchors: (a) +0.038 (CI [0.006, 0.084]); (b)@20% +0.143; (c)@5% +0.209; (c)@20% −0.666; pooled network-level +0.528 observed / +0.325 bootstrap-attenuated; thermal proxy +0.063 (p5 −0.020).
