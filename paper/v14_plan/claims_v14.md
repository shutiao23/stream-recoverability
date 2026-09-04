# Claim matrix v14: differential (benefit) stress testing

Supersedes `paper/development_v13/claim_matrix_v13.md` for the v14 program. The estimand
changed: v13 ranked **loss** (MAE of the recovery model); v14 ranks **realized benefit**
`B = MAE(default handling) − MAE(model)`, positive when reconstruction beats the default.
No v13 loss-ranking claim is carried forward as evidence of benefit; the v13 record is spun
off as the negative-result note (`paper/v14_plan/negative_result_note.md`) and cited as the
prior work we no longer claim.

Evidence roles (unchanged vocabulary; Pfister & Kirchner \cite{pfister2017debates} defense
applies): **frozen** (internal, hash-bound; not externally verifiable preregistration),
**exploratory / descriptive** (P0-era and earlier analyses on already-scored panels),
**confirmatory** (only protocol-v5 gated endpoints on a prospective, externally registered
panel — none exist yet). Status column vocabulary: confirmatory (gated in protocol v5 §3),
exploratory (hypothesis-forming), descriptive (context/boundary).

## Master matrix

| # | Claim | Status | Evidence artifact paths | Boundaries | NO-GO triggers |
| --- | --- | --- | --- | --- | --- |
| C1 | Within duration strata (7/30/90/180 d) and fixed treatment budgets B ∈ {10, 20, 30}%, ranking gaps by the differential (predicted benefit) curve yields higher mean realized benefit than gap-length-only, random, and v13 risk-curve rankings. | **confirmatory** (protocol v5 primary; no outcome yet) | Protocol: `paper/v14_plan/protocol_v5.md` §2.2/§3. P0 evidence base (exploratory): `results/v14/p0_differential/budget_within_duration.csv`, `budget_curve.csv`, `paired_bootstrap.csv`, `REPORT.md` §4–5 | Within-stratum only; harmful rate reported with every mean; comparators scored on identical placements; cross-duration rows are a labeled diagnostic only | G2′/G3′ failure at frozen margins (protocol v5 §3.1); Plan-B if network ρ in 0.25–0.35 band in ≥ 2 strata; harmful rate of treated set > stratum rate → Plan-B harm-failure for that stratum |
| C2 | The differential curve ranks realized benefit positively per duration on outcome-disjoint networks (direction replication, zero margin). | **confirmatory** (protocol v5 G1′/S1) | P0 replication targets (exploratory): `results/v14/p0_differential/metrics_by_horizon.csv`, `derived_network_level.csv`, `season_loo_upper.csv`, `gates.json`, `REPORT.md` Table 1 | Per-duration placement ρ 0.297/0.319/0.303/0.327/0.371/0.556 and network ρ 0.718/0.618/0.551/0.582/0.662/0.650 on the second panel (six-duration grid, 2026-09-04) are replication *targets*, not margins; no cross-duration pooling | G1′ failure (network ρ < 0.35 or CI lower ≤ 0 in ≥ 3 of 4 strata); overall NO-GO if network ρ < 0.25 in ≥ 3 strata (Plan C) |
| C3 | Where the recovery model is net-harmful against the default (observed at 180 d), benefit ranking selects a least-harmful treatment set. | **confirmatory** (protocol v5 S2′/S2, 180-d stratum only) | P0 evidence base: `budget_within_duration.csv` (180-d rows), `REPORT.md` §4 | Applies only to strata with μ_g ≤ 0; treated harmful rate must not exceed the stratum's own rate | S2′ failure: h_{180,0.20}(diff) > h_180 or CI on (μ_20 − μ_180) includes 0 |
| C4 | P0 gates passed under the archived definitions on the outcome-disjoint second panel: direction replication 4/4 durations; paired Δρ vs v13 risk curve +1.087 [1.019, 1.156]; cross-duration top-20% mean realized benefit 0.899 vs 0.051 °C panel mean with harmful 14.5% vs 36.7%. Six-duration regeneration (2026-09-04): direction replication 6/6; pooled old-G2 Δρ +0.908 [0.845, 0.970]; cross-duration top-20% diff 0.922 vs 0.217 °C panel mean, harmful 12.9% vs 30.8% random-fifth. **updated 2026-09-03:** within this row the old-G2 and old-G3 results are re-marked **DIAGNOSTIC** / **VOIDED** (cross-reference: protocol_v5.md "Gate revision log (2026-09-03)"; `results/v14/p0_differential/GATE_REVISION_v2.md`, `gates_v2.json`); the standing P0 verdicts are rows C-G2′/C-G3′ below. | **descriptive** (frozen internal panel; exploratory relative to v5); **updated 2026-09-03** (archived record re-marked; historical `gates.json` verdict unchanged) | `results/v14/p0_differential/gates.json`, `REPORT.md` §1–2, `metrics_by_horizon.csv`, `paired_bootstrap.csv`, `budget_curve.csv`, `sanity_checks.txt`; revision: `GATE_REVISION_v2.md`, `gates_v2.json` | Second panel is internally frozen but not externally verifiable preregistration; P0 numbers license the v5 registration, they do not confirm it; archived `gates.json`/`REPORT.md` remain the untouched historical record | None (already realized; reported as context with the 0.25–0.35 partial-band and 14.5%-near-cap disclosures) |
| C5 | Cross-duration budget curves are dominated by the gap-length scale (0.891 vs 0.922 °C at top-20% on the six-duration grid, +0.031 °C, with gap-length composition 85/15% vs 38/26/15/10/7/4%); protocol v5 must budget within duration strata. | **descriptive** (methodological boundary) | `budget_curve.csv`, `REPORT.md` §5; protocol v5 §2.2 | Forbids cross-duration pooling for any claim; pooled placement ρ 0.547 and budget rows appear only as diagnostics | n/a (a reporting constraint, not a claim) |
| C6 | First-panel (development) differential results are directionally consistent with the second panel. | **exploratory** | `REPORT.md` §6, `metrics_by_horizon.csv` (first rows), `unit_predictions_first.csv` | Development panel: descriptive only; per-duration ρ 0.263/0.302/0.369/0.315; realized benefit mean +0.286 °C, 29.2% harmful | Not gated |
| C7 | The differential curve beats every Tier-0 benefit baseline (global constant, gap length, R&H γ_m \cite{richardson2007longgaps}, r6-diff, default-difficulty, signal proxies). | **exploratory → gated at P1** (PLAN §4.1) | [PENDING] `results/v14/p1_baselines/REPORT.md`, `rh_gamma_curve.csv`, per-unit predictions | R&H γ_m is implemented from \cite{richardson2007longgaps} and applied prospectively; Tier-3 random/oracle brackets with E-AURC \cite{geifman2017selective} | P1 gate: failure to beat any Tier-0 baseline stops the P1 claim (PLAN §2) |
| C8 | Decision-layer value: at least one value curve (EC(ξ)/δ, risk–coverage/E-AURC, η envelope) is positive over its realistic range. | **exploratory → gated at P2** (PLAN §5) | [PENDING] `results/v14/p2_decision/REPORT.md` | Framing per Laio & Tamea \cite{laio2007verification} with the CRPS integral identity; Laugesen defense \cite{laugesen2023flexiblevalue}; η ∈ [0, 1] envelopes, never point estimates (\cite{verkade2011floodwarning}; \cite{khader2013voi}); REV reported with fixed-threshold value loss \cite{roulin2007skill} | P2 gate: no positive value curve → decision claims downgraded to descriptive |
| C9 | Differential advantage over r6-diff is larger in the thermal-drift stratum than in the stable stratum (model conditionality realized under regime shift). | **exploratory** (directional hypothesis pre-registered in protocol v5 S7; no hard gate) | Stratification frozen: `results/v14/p3_drift/README.md`, `network_drift_covariates.csv` (stable 19 / moderate 19 / drift 19); [PENDING] `results/v14/p3_boundaries/REPORT.md` | Either outcome reportable (PLAN §6.1); drift covariates are fitting-vs-evaluation thermal-range, variance-ratio, and donor-correlation signals | None (no hard gate); a null is a publishable boundary statement |
| C10 | Downstream: reconstruction benefit versus the third default (linear interpolation) and the 180/365-d legs are scored; benefit does not claim to cover its own high-risk region (28.9% loss mass at long gaps) without 180-d coverage. | **exploratory** ([PENDING] P4) | [PENDING] `results/v14/p4_downstream/REPORT.md`; P0 partial: `differential_fitting_losses_{first,second}_linear_interp.csv` (interpolation default scored at the fitting level) | no-fill is uncomputable at the placement level (MAE undefined) and enters only at downstream-metric level | Not gated |
| C-G2′ | The differential curve beats the r6-diff station-history baseline at placement level within duration strata (paired network-cluster bootstrap delta of diff over r6_diff; PASS if CI lower > 0). | **updated 2026-09-03; re-evaluated 2026-09-04 on the six-duration grid** (exploratory; standing P0 verdict under redefined G2) | `results/v14/p0_differential/paired_diff_vs_r6.csv` (canonical), `gates_v2.json`; cross-ref protocol_v5.md "Gate revision log (2026-09-03)" and GATE_REVISION_v2.md §4a (round-2 extension) | Placement-within-duration only (r6_diff is constant within (station, duration) and cannot rank placements there); 10 of 12 panel-duration cells pass with cluster CI excluding zero (all six second-panel cells); boundary: the two crossing cells — first-panel 60 d CI [−0.010, +0.068] and first-panel 90 d CI [−0.022, +0.056] — are reported honestly | A cell with cluster CI lower ≤ 0 fails that cell; 10/12 passes are reported with the crossing cells disclosed |
| C-G3′ | Within-duration-stratum top-20% budget: the differential curve's mean realized benefit exceeds duration-only and r6_diff within each duration stratum. | **updated 2026-09-03; re-evaluated 2026-09-04 on the six-duration grid** (exploratory; standing P0 verdict under redefined G3) | `results/v14/p0_differential/budget_within_duration.csv`, `gates_v2.json`; cross-ref protocol_v5.md "Gate revision log (2026-09-03)" and GATE_REVISION_v2.md §4a | Margins over duration-only +0.22/+0.28/+0.24/+0.32/+0.32/+1.01 °C at 7/14/30/60/90/180 d with network-cluster CIs > 0 (P(>0) = 1 in all six); margins over r6_diff +0.066/+0.069/+0.067/+0.026/+0.013/+0.226 °C; harmful rates per duration 9.4%/8.4%/10.9%/14.7%/25.1%/62.7%, never a single pooled number | A stratum whose margin CI lower ≤ 0 fails that stratum (none observed) |
| C-RN | Reporting-norms set (binding on all v14 rows, incl. C1–C10): main reporting level = placement-within-duration; effect sizes as differences, never ratios (17.6×-style ratios over near-zero denominators are prohibited); cross-duration pooled numbers always reported beside duration-only and labeled duration-confounded; harmful rates per duration, never a single pooled number; three-level decomposition (network-inter / within-network across-duration / within-network within-duration) always reported; **norm (v), added 2026-09-04:** every benefit statement names its default handling (calendar-day climatology unless stated) — a benefit figure without its default is not reportable. | **updated 2026-09-03; extended 2026-09-04** (normative; no evidence content) | WORKPLAN_v14.md §1.4; protocol_v5.md §4.4 and "Gate revision log (2026-09-03)"; manuscript §2.7 | A formatting/evidence constraint, not a claim; violation invalidates the reporting status of the affected claim | n/a |
| C-UC | Unit-level aggregation erases the differential curve's seasonal increment over r6_diff: first-30 d unit-level delta −0.012 with P(>0) = 0.045, versus a positive placement-level within-duration delta — the increment exists only at placement level within duration strata. | **updated 2026-09-03** (diagnostic) | `results/v14/p0_differential/paired_diff_vs_r6_unit_diagnostic.csv` | Aggregation-level diagnostic explaining why the canonical comparison (C-G2′) is placement-within-duration; does not weaken the placement-level result | n/a (diagnostic) |
| C-R2A | Cross-model-family robustness of the duration rule: three structurally different recovery-model families (deployment xgboost_b_d, donor_station ridge donor_blup_ridge, seasonal_boundary_ridge) scored on the identical 28,728-placement first-panel geometry against the climatology default all reproduce the sign flip — positive mean benefit through 60–90 d, negative at 180/365 d — with the two strong families flipping between 90 and 180 d and the ridge between 60 and 90 d; the deployment family column reproduces the Table 2 first-panel means wherever unit sizes are equal. | **added 2026-09-04** (exploratory; standing robustness evidence) | `results/v14/p1_baselines/family_benefit_table.csv` (scripts/151); roster `results/development_v11/reviewer_completion/confirmation_model_roster_losses.csv`; reviewer-reproduced (REVIEW_v14_round2.md Major 4) | First panel only (roster geometry); robustness claim is limited to the three tested families — Tier-1 trivial fills and Tier-2 air2stream/Mohseni rosters were NOT executed and are not claimed; benefit is over the climatology default | n/a (no gate; a §2.8/§4.8(iii) boundary discipline) |
| C-R2B | The differential curve's irreplaceable ranking range is the positive-benefit regime (7–60 d): paired placement-level deltas of diff over the sign-flipped legacy predictor (−risk) are +0.395 [+0.293, +0.500] / +0.357 [+0.260, +0.459] / +0.344 [+0.241, +0.458] (first) and +0.478 [+0.364, +0.598] / +0.488 [+0.376, +0.606] / +0.430 [+0.326, +0.537] (second) at 7/14/30 d, and +0.260 [+0.141, +0.376] (first) / +0.302 [+0.211, +0.394] (second) at 60 d (P(>0) = 1.00 in all six), while at 180 d the delta collapses (−0.058 [−0.177, +0.020] first; +0.015 [−0.017, +0.049] second, P(>0) = 0.82) — a sign-flipped error predictor suffices at long gaps but ranks with the wrong sign or not at all at short ones. | **added 2026-09-04** (exploratory; re-frames the C2/C-G2′ emphasis — 7/30 d is the paper's core ranking claim, 180 d is the harm-avoidance claim C3) | `results/v14/p0_differential/paired_diff_vs_negrisk.csv` (scripts/150); mechanism in manuscript §4.2 | placement-within-duration, direct placements only; ρ(−risk) = −ρ(risk) by construction; the v5 G1′/G2′ gates and their thresholds are unchanged — this row re-positions emphasis, it does not re-open gates | n/a (evidence-scope row; the first-panel 180-d delta being negative is reported, not hidden) |

## C1 detail — within-stratum budget superiority (confirmatory, protocol v5 primary)

**Evidence required (prospective panel):** per-stratum treated-set means and harmful rates
for every predictor × B ∈ {10, 20, 30}%; per-network paired differences; 95%
network-cluster bootstrap CIs (2,000 draws within provider strata); frozen tie-break rules.

**P0 evidence base (exploratory; second panel, B = 0.20, `budget_within_duration.csv`):**
mean realized benefit °C (harmful rate) for the differential curve: 7 d 1.219 (9.4%);
30 d 0.840 (10.9%); 90 d 0.380 (25.1%); 180 d −0.636 (62.7%). Comparators at 90 d:
duration-only 0.056 (44.2%), r6-diff 0.367 (25.5%), risk −0.256 (54.9%); at 180 d:
duration-only −1.647 (85.5%), r6-diff −0.862 (71.4%), risk −2.881 (98.2%). Cross-duration
top-20% (diagnostic, six-duration grid 2026-09-04): diff 0.922 (12.9%) vs duration 0.891
(10.8%) vs panel mean 0.217 °C (30.8% harmful random-fifth; archived four-duration
values 0.899 (14.5%) vs 0.891 vs 0.051 °C in REVIEW_v14.md) — `budget_curve.csv`,
`REPORT.md` §2/§5.

**Boundaries.** (i) Claims are per duration stratum; the 180-d stratum with μ ≤ 0 is read
through the harm-avoidance gate (C3), not the ratio gate. (ii) Every mean must be paired
with its harmful rate. (iii) Duration-only within a stratum is realized by frozen random
tie-breaking (gap length is constant within the stratum). (iv) Comparators are scored on
identical placement subsets.

**NO-GO triggers (frozen, protocol v5 §3).** G2′ CI not entirely above zero in ≥ 2 strata;
G3′ (μ_20 ≥ 1.3·μ_g and h_20 < 15%) not met in ≥ 2 strata with μ_g > 0; Plan-B downgrade
in the 0.25–0.35 band; any stratum whose treated harmful rate exceeds its own h_g is a
harm-failure for that stratum.

## C2 detail — direction replication (confirmatory, protocol v5 G1′/S1)

**Evidence required:** per-duration placement-level and network-level Spearman with cluster
bootstrap CIs; paired Δρ vs the v13 risk curve per duration; network ρ ≥ 0.35 with CI lower
> 0 in ≥ 2 of 4 durations.

**P0 targets (second panel; exploratory):**

| Duration | Placement ρ | Network ρ [CI] | Risk placement ρ | Season-LOO upper |
| --- | --- | --- | --- | --- |
| 7 d | 0.297 | 0.718 [0.550, 0.824] | 0.184 | 0.240 |
| 14 d | 0.319 | 0.618 [0.414, 0.765] | 0.172 | 0.300 |
| 30 d | 0.303 | 0.551 [0.280, 0.753] | 0.129 | 0.295 |
| 60 d | 0.327 | 0.582 [0.358, 0.759] | −0.024 | 0.380 |
| 90 d | 0.371 | 0.662 [0.443, 0.814] | −0.192 | 0.414 |
| 180 d | 0.556 | 0.650 [0.443, 0.790] | −0.541 | 0.734 |
| direct pooled (diagnostic) | 0.547 | 0.615 [0.398, 0.765] | −0.361 | 0.595 |

Sources: `REPORT.md` Table 1; `derived_network_level.csv`; `gates.json`;
`metrics_by_horizon.csv`; `season_loo_upper.csv`. Placement-level CIs:
`metrics_by_horizon.csv` `diff_ci_lower/upper` (placement-pooled rows per duration).

**Boundaries.** Zero margin (replication, not superiority — the v3/v4 ±0.019/0.038-style
margins are superseded); no cross-duration pooling; 7/30-d placement-level band
0.25–0.35 is a Plan-B trigger, driven by small realized-benefit spread at short durations,
not harmful treatments (`REPORT.md` §3). Round-2 reading (2026-09-04, C-R2B): within the
band the differential curve is the only tested instrument that ranks benefit in the right
direction — the Plan-B trigger concerns the network-level gate, not placement ρ, and the
band is presented as the method's irreplaceable range (manuscript §3.3, §4.7).

## C3 detail — harm avoidance at 180 d (confirmatory, protocol v5 S2′)

**Evidence required:** h and μ of the treated sets at B ∈ {10, 20, 30}% vs h_180 and μ_180
with network-cluster CI on (μ_20 − μ_180); the treated set's harmful rate must not exceed
the stratum's own rate.

**P0 evidence base (exploratory):** 180-d stratum: panel μ = −1.477 °C, 83% harmful; top-20%
by the differential curve −0.636 °C (63% harmful) vs duration-only −1.647 °C (86%) and risk
−2.881 °C (98%); at 90 d top-20% +0.380 °C (25%) vs duration-only +0.056 °C (44%) and risk
−0.256 °C (55%) — `budget_within_duration.csv`, `REPORT.md` §4.

**Boundaries.** Confined to net-harmful strata (observed at 180 d); it is an avoidance
claim, not a claim that long-gap treatment becomes beneficial on average.

## Non-claims (frozen; NOT allowed language)

- **No loss-ranking claims.** No v13 loss claim (pooled 0.945, network 0.80, r6 near-tie,
  CapturedLoss@20% 0.337) is evidence of benefit; these are the negative-result note's
  content (`paper/v14_plan/negative_result_note.md`).
- **No "more accurate" claim vs Johnson et al.** \cite{johnson2021datagap} — the increment
  is model-conditional + benefit-oriented.
- **No cross-duration pooled claims** (ρ or budget). Pooled rows (0.547; 0.922 vs 0.891 °C on
  the six-duration grid; archived four-duration 0.607 / 0.899 vs 0.891 in the round-1 record)
  are diagnostics labeled as such.
- **No rank-superiority over station history at the pooled level.** Placement-pooled paired
  Δρ vs duration-only +0.0022 [−0.028, +0.035] spans zero (`paired_bootstrap.csv`);
  per-stratum budget separation (C1) is the claim, not pooled rank.
- **No 365-day or extrapolated-horizon claims** without real same-horizon fitting support.
- **No "preregistered confirmation" for internal panels.** Second-panel results are
  hash-bound, same-commit → not externally verifiable preregistration (wording frozen);
  confirmatory status requires protocol v5's external OSF/Zenodo registration.
- **No model-selection claims** (PLAN §5.6): two-sentence negative only (oracle space
  0.100 °C; 54:45 family split; coverage-floor criteria 10–12% < 20% success line).
- **No self-transfer for the BiLSTM** (harmonization decision #2): cross-instance,
  illustrative only, 0.28–0.69 range.
- **No missingness matched-strength claims** outside the harmonized canonical SI table
  (harmonization decision #1; donor-sync 0.490 [−0.236, 0.925] at n=12 is a wide-interval
  value).
- **No conditional-covariance "lower bound"** — expected Gaussian MAE only
  (harmonization decision #1-note/claim C2d of v13), now the Zaoui-theoretical baseline
  \cite{zaoui2020rejectoption} in P2.
- **No value claims without the η response-effectiveness caveat** and Laugesen
  \cite{laugesen2023flexiblevalue} potential-value labeling.
- **No "~60-d operating rule" claim** (added 2026-09-04): the ~60-d figure and its "internal sub-grid analysis" have no reproducible artifact in `results/v14/` and are contradicted by the observed 60-d placement benefit (+0.48/+0.32 °C, 19.2%/26.6% harmful); threshold claims are the two scale-specific interval statements of manuscript §3.1 (MAE-scale crossing 91–105 d with bootstrap CI; downstream family medians 39–60 d), and the Johnson m_max = 49 d comparison is an interval-bracketing statement, never a point convergence.
- **No Tier-1/Tier-2 recovery-robustness claim** (added 2026-09-04): mean/median fill, LOCF, linear interpolation, climatology, donor-with-offset, air-temperature regression, air2stream and Mohseni rosters were not executed in this revision; model-family robustness is limited to the three archived roster families of C-R2A.
- **No automatic filling or station removal** supported by present evidence.

## Reporting order (Results of the v14 manuscript)

1. C6 (development panel, descriptive) → 2. C4/C2 (second-panel direction replication and
gates) → 3. sign reversal vs the v13 risk curve (Δρ +0.908 [0.845, 0.970] on the six-duration grid; archived four-duration +1.087 [1.019, 1.156] in REVIEW_v14.md) → 4. C1
(within-duration budgets, Table 3 of the skeleton) → 5. C3 (harm avoidance at 90/180 d) →
6. [PENDING P1] C7 → 7. [PENDING P2] C8 → 8. [PENDING P3] C9 → 9. [PENDING P4] C10.
C5 and the evidence-role labels govern the language of every row.
