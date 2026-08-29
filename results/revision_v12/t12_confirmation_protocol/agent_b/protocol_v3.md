# Protocol v3: External-Confirmation Panel for Gap-Recoverability Transfer Claims (outcome-disjoint)

| field | value |
| --- | --- |
| protocol_id | `revision_v12_confirmation_panel_v3` |
| status | `planned_requires_external_registration_before_outcome_scoring` |
| target_journal | Water Resources Research |
| supersedes | `route_a_second_confirmation_v1` (+ `route_a_second_confirmation_v2_canada_quality_substitution`), which remain the archival records of the second panel (57 scored networks) |
| evidence_role | third, outcome-disjoint confirmation panel; externally timestamped before outcomes are opened |
| authoring agent | agent b (adversarial pair), `scripts/rev_v12_t12_protocol_b.py`, namespace `results/revision_v12/t12_confirmation_protocol/agent_b/` |
| frozen before | any v3 recovery outcome is viewed or scored (see External Timestamping) |

## 0. Why a v3 protocol and what it fixes

The v2 second confirmation was frozen by an **internal, hash-bound, same-commit
mechanism** (`package_manifest.json` → `second_confirmation.amendment_status`:
"internally frozen and hash_bound_before_scoring_same_commit_as_outcomes_not_external_preregistration").
The freeze, roster, and outcomes landed in the same commit, so an external
observer cannot verify that the rules preceded the outcomes. Reviewers require
an **externally verifiable** confirmation protocol. v3 therefore:

1. requires an **external timestamp** (separate public commit pushed to a
   public remote, or an OSF/Zenodo preregistration) **before any v3 outcome
   value is opened** (Section 11);
2. re-freezes the candidate, eligibility, independence, endpoint, abstention,
   and success-margin rules for a **new panel** that is outcome-disjoint from
   both prior panels;
3. adds a **network-bootstrap power analysis** (Section 3) whose numbers are
   frozen into the success margins before outcomes are opened;
4. defines a **model roster with per-model self-transfer stress curves**
   (Section 8) so transfer degradation is measured for every rostered model,
   not only the headline predictor.

## 1. Claims under test (unchanged from v1/v2)

- C1 network-level rank and domain-adapted calibration transfers.
- C2 simple descriptors do not dominate the fitting-period empirical-transfer predictor.
- C3 conformal risk control and real-data placement replay transfer to new domains.
- C4 domain and thermal-state calibration failure modes are bounded.

## 2. Independent unit, targets, and panel-size justification

- Independent unit: **river network** (a connected set of official daily
  water-temperature stations with a shared recovery-loss scoring protocol).
- Candidate floor: **150** candidate networks entering QC (invariant from v1).
- Retention fraction expectation: 0.5–0.8 (v2 realized 60/60 QC-arrivals, 57/60 scored).
- Target scored networks: **80–120**. Minimum valid scored networks for any
  primary analysis: **40** (invariant). Attrition-tolerant primary analysis:
  actual arrivals once ≥ 40 scored, with the realized panel size reported.

### 3. Power analysis and the 80–120 justification

Power analysis (agent b, `scripts/rev_v12_t12_protocol_b.py`) uses the second
panel's paired predictions
(`results/development_v11/second_confirmation/scoring/empirical_predictions.csv`
× `simple_predictions.csv`; 1,446 units; 57 networks; direct-support horizons
7/30/90/180 d; 874 direct-support units). For each simulated panel, networks
are resampled **with replacement** and units are **block-bootstrapped within
networks**; per-network paired endpoints are recomputed; the frozen test is a
**one-sided paired Wilcoxon across networks** (α = 0.05); power is the
fraction of 600 replicates with p < 0.05. Effect margins multiply each
network's observed effect (0.5x / 1x / 1.5x); margin 0x with random sign
flips calibrates test size (0.037–0.048 at n = 160, ≤ α).

Observed second-panel per-network effects (means): ΔRho **+0.036**
(median +0.021; 72% of networks positive); ΔNDCG **+0.0095**; ΔCapturedLoss
+0.012 at 5% budget, +0.013 at 10%, **−0.012 at 20%**, −0.014 at 30%.

| endpoint | power at 1x observed effect (n = 40 / 60 / 80 / 100 / 120 / 140 / 160) | n for 80% at 1x |
| --- | --- | --- |
| (a) network ΔRho | 0.80 / 0.94 / 0.98 / 0.99 / 1.00 / 1.00 / 1.00 | ≈ 40 |
| (c) ΔNDCG | 0.71 / 0.89 / 0.92 / 0.97 / 0.99 / 0.99 / 1.00 | ≈ 51 |
| (b) ΔCapturedLoss @5% | 0.37 / 0.50 / 0.58 / 0.65 / 0.73 / 0.81 / 0.83 | ≈ 140 |
| (b) ΔCapturedLoss @10% | 0.28 / 0.41 / 0.47 / 0.51 / 0.60 / 0.68 / 0.72 | not reached at 160 |
| (b) ΔCapturedLoss @20% | 0.17 / 0.22 / 0.27 / 0.30 / 0.35 / 0.37 / 0.44 | **unreachable** (see §12.3) |
| (b) ΔCapturedLoss @30% | 0.15 / 0.20 / 0.23 / 0.28 / 0.32 / 0.35 / 0.39 | unreachable |

Justification of **80–120 scored networks**:

1. Endpoints (a) and (c) — the ranking/selection core — reach 80% power at
   n ≈ 40–51 and ≥ 0.92 at n = 80; at n = 80–120 power is 0.92–1.00 even at
   **0.5x** the observed effect (ΔRho 0.97–1.00; NDCG 0.93–1.00). The target
   is 2–3× the minimum for these endpoints, absorbing attrition.
2. The 5%-budget prioritization arm reaches 80% only near n ≈ 140–160; the
   80–120 target gives it 0.58–0.73 power at the observed effect and is
   reported with realized power (co-primary with a frozen margin, §12.3).
3. 80–120 is also large enough that the required domain quotas (§4) can be
   met simultaneously, and large enough that the bootstrap panel-median
   ΔRho distribution concentrates above the frozen margin: median ≈ +0.035,
   25th percentile ≈ +0.028 at n = 80–120
   (`panel_effect_distribution.csv`).

## 4. Domain quotas

- Required domain groups: **united_states** plus **at least two non-US
  domains** (temperate official daily sources; e.g., czechia, norway, and any
  additional approved domain).
- Minimum networks per domain, at the target of ≥ 80 scored:
  - united_states: ≥ 40
  - each of the two non-US domains: ≥ 10
  - at least two non-US domains must jointly contribute ≥ 25 scored networks.
- No domain may exceed 70% of the scored panel.
- Roster freeze rule: complete strict-QC arrival rosters are frozen **by
  network_id, sorted**, before outcomes; domain counts in the frozen roster
  supersede the quotas only upward (more networks per domain is allowed;
  fewer is not).

## 5. Candidate, eligibility, QC, and attrition rules

1. Candidates come from official provider daily water-temperature sources
   with documented metadata (source audit per provider, as in v2).
2. Eligibility (frozen): ≥ 3 stations per network; ≥ 8 common years;
   metadata pilot passed; daily-concurrency QC passed **before** any outcome
   scoring (v2 rule retained).
3. Strict daily-QC qualification precedes roster freeze; unvalidated or
   un-checked provider observations do **not** qualify (the v2 Canada
   substitution is the precedent; any future substitution must itself be a
   written amendment, externally timestamped, and may not relax this rule).
4. Attrition is recorded in a flow table at two stages:
   - **pre-outcome attrition** (candidate → QC-qualified): reasons listed per network;
   - **scoring attrition** (QC-qualified → scored outcome): reasons listed per
     network; the primary analysis is run on all scored networks and repeated
     on the QC-qualified roster with missing outcomes imputed as abstained.
5. Minimum scored floor: 40 (invariant). Target band 80–120; the panel is
   closed when the band is reached or the candidate pool is exhausted.
6. **Evaluate-once self-destruct**: any network's outcome may be scored by
   this protocol exactly once; a scored v3 outcome is never reused by a
   later protocol.

### 5.1 QC-only reuse rule

Networks that passed QC in a prior panel (development, first confirmation,
or second confirmation) but produced **no scored recovery outcome** may be
reused as v3 candidates **only if**:

1. they are individually listed in the protocol as
   `qc_only_reused: [network_id, ...]` with the prior panel and QC record
   cited (v2 precedent: three first-confirmation QC-only networks);
2. they are **not** described as untouched metadata/QC candidates; and
3. the v3 roster otherwise remains disjoint from every development, first-
   confirmation, or second-confirmation network **for which a recovery
   outcome was scored**.

## 6. Independence rules (frozen)

- Roster disjointness: v3 scored networks are disjoint from all
  development/second-panel outcome-scored networks (see §5.1 exception).
- **No v3 recovery outcome may be computed or viewed before the external
  timestamp** (Section 11).
- Temperature values may not select networks (selection uses provider,
  station counts, and metadata only).
- Post-confirmation adaptation of models = a new confirmation (v1 rule).
- Open development replay is not confirmation (v1 rule).
- No model, endpoint, margin, or analysis change after external timestamp,
  except by a written, externally timestamped amendment that is itself
  registered before any affected outcome is scored.
- All v3 outcomes remain unviewed by the modeling team until the frozen
  pipeline runs; the pipeline binds input hashes (roster, protocol, baseline
  tables) into its output manifest.

## 7. Missingness mechanisms (frozen taxonomy)

Recovery outcomes are observed station-gap recoveries at the frozen gap
lengths {7, 14, 30, 60, 90, 180, 365} days. Each scored gap is tagged with
its recorded mechanism where available:

- `mechanical` — sensor/logger failure;
- `scheduled` — planned maintenance or seasonal removal;
- `sensor_failure` — instrument malfunction with QC flag;
- `aggregation_lag` — provider publication delay;
- `unspecified` — no mechanism recorded (must be reported separately and
  never merged with a mechanism class).

Missingness is treated as exogenous: gaps are not model-selected. The
protocol reports mechanism × outcome tables and mechanism-stratified
primary endpoints as sensitivity, never as a selection argument.

## 8. Model roster with self-transfer stress curves

Every rostered model is fit on the development fitting period and evaluated
on the **same** v3 scored units (identical outer gaps, identical units; no
selective abstention, §10). Each model additionally reports its **self-
transfer stress curve**: its metric as a function of transfer distance,
computed as leave-domain-out folds over the development fitting domains
(US / each non-US domain), i.e., the model's own performance degradation
when its fitting domains differ from the evaluation domain.

| roster position | model | role |
| --- | --- | --- |
| baseline (strongest comparator) | simple descriptors (frozen v11 feature set) | comparator for every paired endpoint |
| primary | fitting-period empirical-transfer predictor (frozen v11 curve; direct support at 7/30/90/180 d) | primary model |
| rostered | air2stream-8 equivalent (fixed independent subset + harmonized boundaries where data permit) | transfer diagnostic |
| rostered | seasonal-boundary ridge | transfer diagnostic |
| rostered | XGBoost (B ∪ D information condition) | transfer diagnostic |
| rostered | donor-BLUP ridge | transfer diagnostic |
| exploratory (not claim-bearing) | BiLSTM sensitivity (non-SOTA, nonconverged, bounded) | sensitivity |
| development-only | process-hybrid readiness | not scored on v3 |

The roster, hyperparameters, and fitted-checkpoint identifiers are frozen in
the registration archive; post-registration training is prohibited.

## 9. Primary and secondary endpoints

### 9.1 Primary endpoints (all frozen with tests and margins before outcomes)

All primary endpoints are **paired at network level** between the primary
model and the strongest baseline (simple descriptors). The unit of
inference is the network; the test is the one-sided paired Wilcoxon across
scored networks (α = 0.05), with effect-size margins as in Section 12.

- **(a) Network ΔRho (direct-support units)**. Per network, on direct-support
  units only (gap lengths 7/30/90/180 d): ρ(empirical prediction, observed
  recovery loss) − ρ(baseline prediction, observed recovery loss).
  Success: p < 0.05 **and** panel-median ΔRho ≥ +0.02.
- **(b) ΔCapturedLoss at budget B ∈ {5, 10, 20, 30}%**. Per network, select
  the top ⌈B × n⌉ units by predicted loss; captured fraction = (sum of
  observed loss in the selected set) / (total observed loss). Δ = empirical
  − baseline. The **head budget is 20%**; success requires p < 0.05 and
  panel-median Δ ≥ +0.02 at 20% (§12.3), with 5/10/30% reported on the same
  ladder.
- **(c) ΔNDCG**. Per network, NDCG with gain = observed recovery loss and
  log-2 discount, empirical vs baseline. Success: p < 0.05 and panel-median
  ΔNDCG ≥ +0.005.
- **(d) Thermal-metric protection**. Per network, paired Spearman between
  predicted loss and (i) observed summer-maximum daily temperature during the
  recovery window, and (ii) observed threshold-exceedance days (days above
  the fitting-period 95th percentile). Δ = empirical − baseline, per
  network; success: p < 0.05 and panel-median Δ ≥ +0.05 on both thermal
  metrics. (No second-panel guidance exists for (d); margins are set at a
  minimum meaningful magnitude and power is reported descriptively.)

### 9.2 Secondary endpoints

- Calibration: network-level slope in [0.90, 1.10] and intercept reporting.
- Interval: nominal 90% coverage, network-simultaneous band [0.85, 0.95],
  median width / median loss ≤ 2.0 (v1 rules; failed in v2, retained as
  falsifiable secondary).
- Triage: learn-then-test certified-set fraction under unsafe-loss c = 0.50
  and false-release cap 0.05 (v2 returned empty certified sets; retained).
- Placement replay: worst-target-MAE regret of simple-risk-minimax / greedy
  MI / QR-pivot / distance-even / random vs realized-outcome oracle at budget
  fractions 5/10/20/30% (gap 90 d), with regret margins reported, no
  confirmatory utility claim without a frozen margin (v2 direction was
  nonconfirmatory).
- Per-domain replication of endpoints (a)–(d) within US and each non-US domain.
- Mechanism-stratified endpoints (§7).

## 10. Abstention rules (frozen)

1. **Support tiers.** Units are scored in two disjoint tiers:
   - direct-support tier: horizons 7/30/90/180 d, empirical curve applies;
   - network-mean fallback tier: other horizons, network-mean prediction.
   Tiers are never merged; every reported metric states the tier.
2. **Extrapolation abstention.** A model abstains on units whose horizon lies
   outside its fitted range or whose network lies outside its fitted domain,
   unless a frozen fallback (network-mean) is licensed. The abstention rate
   is reported per model and per tier.
3. **Symmetry.** All rostered models are scored on the identical unit set;
   models may not selectively abstain to improve their metrics.
4. Abstained units count in the denominator of the reported
   coverage/availability statistics, and their counts are frozen in the
   registration.

## 11. External timestamping (the v3 fix)

The v2 flaw: freeze and outcomes shared one commit, so no external observer
can verify rule precedence. v3 requires, **before any v3 outcome is
computed or opened**, one of the following (recorded in this protocol and in
the registration archive):

1. **OSF or Zenodo preregistration**: a public registration containing (i)
   this protocol, (ii) the QC rules, (iii) the frozen model roster, (iv) the
   endpoint definitions and success margins, (v) the analysis pipeline, and
   (vi) the power-analysis table (`power_analysis.csv`) — with a minted DOI
   or permanent URL and a recorded registration timestamp; or
2. **Separate public commit**: a commit containing exactly the same frozen
   artifacts, pushed to the public remote as its own commit **before** the
   outcome-scoring run, whose SHA-256 and commit timestamp are recorded in
   the protocol; the outcome-scoring commit must be a **later, distinct
   commit** whose manifest binds the frozen-commit SHA-256.

The registration record (DOI/URL, timestamp, SHA-256 of the frozen archive)
is itself an artifact of this protocol and is deposited with the results.
Outcome files written before the registration timestamp invalidate the panel.

## 12. Success margins (frozen before outcomes; guidance from the power analysis)

All margins below are frozen **at registration**; the guidance values were
derived from the power analysis of the second panel (observed effect at 1x,
bootstrap distribution of the panel median, and the effect detectable at 80%
power; see `power_analysis_summary.json`).

### 12.1 Frozen margins

| endpoint | frozen success margin (panel median Δ) | guidance basis |
| --- | --- | --- |
| (a) ΔRho | ≥ +0.020 | ≈ half the observed mean (+0.036); ≈ p25 of the bootstrap panel median (+0.028) at n = 80–120 |
| (b) ΔCapturedLoss @20% | ≥ +0.020 capture fraction | minimum meaningful; observed 20% effect is null-to-negative (§12.3) |
| (c) ΔNDCG | ≥ +0.005 | ≈ observed mean (+0.0095); ≈ 2× p25 of bootstrap panel median (+0.0028) |
| (d) thermal Δ | ≥ +0.05 (both metrics) | minimum meaningful; no second-panel guidance exists |

Statistical success additionally requires the one-sided paired Wilcoxon
p < 0.05 for the endpoint. Endpoints (a) and (c) are the powered co-primaries;
(b) and (d) are co-primaries carried for falsification discipline with their
realized (possibly low) power disclosed.

### 12.2 Interpretation rules

- The panel-median Δ is computed on all scored networks (attrition-tolerant).
- A margin is **failed** if the panel-median Δ is below it, even when
  p < 0.05; both conditions are required.
- Margins are never relaxed post hoc; amendments may only tighten or
  register new disclosure endpoints.

### 12.3 Declared power limitation for (b) at 20% (disclosed, not hidden)

The second panel shows a **null-to-negative** 20%-budget capture effect
(mean −0.012; median 0.00; only 25% of networks positive). Consequence: no
feasible panel size reaches 80% power for this endpoint at the observed
effect — even a 10× margin multiplier yields ≤ 0.45 power at n = 160,
because scaling preserves the sign mixture. The protocol therefore:

- keeps 20% as the frozen head budget (no post-hoc budget substitution);
- does **not** claim the panel is powered for (b)@20%; the panel is sized
  for (a) and (c);
- pre-registers the +0.02 margin and reports the endpoint with its realized
  power and the full 5/10/20/30% ladder.

This is the adversarial-honest resolution: the endpoint stays falsifiable
instead of being silently replaced by the budgets where the second panel
looked favorable (5%: +0.012, 80% power only at n ≈ 140–160).

## 13. Analysis pipeline (ordered, gated)

1. Candidate assembly and provider source audits (per provider, as v2).
2. Metadata pilot and daily-concurrency QC (pre-outcome).
3. Roster freeze (sorted network_id list; domain counts recorded).
4. **External registration** (Section 11) — gate: nothing scored yet.
5. Outcome scoring with input-hash binding (roster, protocol, baseline
   tables, registration record).
6. Endpoint computation per the frozen definitions (tiers, budgets, margins).
7. Primary tests (one-sided paired Wilcoxon per endpoint) and margins.
8. Sensitivity: supported-only vs complete panel; pooled vs network-level;
   per-domain; per-mechanism; attrition flow table.
9. Model-roster self-transfer stress curves (§8).
10. Disclosure: all endpoints, margins, realized power, abstention and
    attrition tables, and the registration record — regardless of outcome.

## 14. v2 → v3 changes

| item | v2 (second panel) | v3 (this protocol) |
| --- | --- | --- |
| timestamping | internal, hash-bound, same commit as outcomes | external registration (OSF/Zenodo DOI or separate public commit) strictly before outcomes (§11) |
| panel | 60 attempted / 57 scored (US 35, CZ 15, NO 10) | 80–120 scored; US ≥ 40 + ≥ 2 non-US domains (§4) |
| endpoints | rank, calibration, intervals, triage, placement (mixed confirmatory status) | frozen paired network-level primaries (a) ΔRho, (b) ΔCapturedLoss ladder @5/10/20/30%, (c) ΔNDCG, (d) thermal protection; secondaries retained (§9) |
| power analysis | none (directional margins only) | network-bootstrap power curves, margins 0.5x/1x/1.5x, sizes 40–160, 80% power targets (§3) |
| success margins | not frozen for placement/utility claims | frozen before outcomes, with guidance values from the power analysis (§12) |
| abstention | fallback units reported separately | frozen support tiers + extrapolation abstention, symmetric across models (§10) |
| missingness | mechanism-agnostic | frozen mechanism taxonomy + stratified sensitivity (§7) |
| model roster | single headline model + comparators | every rostered model carries its own self-transfer stress curve (§8) |
| QC-only reuse | disclosed for 3 first-panel networks | explicit rule (§5.1), bounded and disclosed |

## 15. Artifacts bound to this protocol

- `scripts/rev_v12_t12_protocol_b.py` (power analysis; reproducible).
- `results/revision_v12/t12_confirmation_protocol/agent_b/power_analysis.csv`,
  `panel_effect_distribution.csv`, `power_analysis_summary.json`,
  `power_curve.png`.
- Registration archive (Section 11): this protocol, QC rules, roster rules,
  model roster, endpoint definitions, margins, pipeline, power tables.
